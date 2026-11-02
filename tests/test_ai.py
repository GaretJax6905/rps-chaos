"""Unit checks for ORACLE's brain, the boss strategies, and the battle state."""

# pytest injects fixtures by name.
# pylint: disable=missing-function-docstring,redefined-outer-name

import random

import pytest

import battle
import bosses
import brain

pytestmark = pytest.mark.unit


def rounds(*moves, outcome="tie"):
    return [{"player": m, "computer": m, "outcome": outcome, "boss": 0} for m in moves]


# ---------- brain ----------


def test_brain_waits_for_three_rounds():
    read = brain.predict("classic", rounds("rock", "rock"))
    assert read["prediction"] is None
    assert read["counter"] is None
    assert "1 more round" in read["insight"]


def test_brain_catches_a_rock_spammer():
    read = brain.predict("classic", rounds("rock", "rock", "rock", "rock"))
    assert read["prediction"] == "rock"
    assert read["counter"] == "paper"
    assert read["confidence"] > 0.5


def test_brain_catches_a_cycle():
    history = rounds(*["rock", "paper", "scissors"] * 3, "rock")
    read = brain.predict("classic", history)
    assert read["prediction"] == "paper"
    assert read["counter"] == "scissors"


def test_brain_counter_in_spock_mode_beats_the_prediction():
    read = brain.predict("spock", rounds("lizard", "lizard", "lizard", "lizard"))
    assert read["prediction"] == "lizard"
    assert read["counter"] in ("rock", "scissors")


# ---------- bosses ----------


def test_mirror_copies_your_last_move():
    move, thought = bosses.choose(
        "mirror", "classic", rounds("paper"), random.Random(1)
    )
    assert move == "paper"
    assert "paper" in thought


def test_cycler_follows_the_move_order():
    moves = [
        bosses.choose("cycler", "spock", rounds(*["rock"] * n), random.Random(0))[0]
        for n in range(6)
    ]
    assert moves == ["rock", "paper", "scissors", "lizard", "spock", "rock"]


def test_contrarian_beats_a_repeat():
    move, _ = bosses.choose("contrarian", "classic", rounds("rock"), random.Random(0))
    assert move == "paper"


def test_rocky_loves_rock():
    rng = random.Random(42)
    picks = [bosses.choose("rocky", "classic", [], rng)[0] for _ in range(200)]
    assert picks.count("rock") > 120


def test_oracle_counters_a_pattern():
    move, thought = bosses.choose(
        "oracle",
        "classic",
        rounds("scissors", "scissors", "scissors"),
        random.Random(0),
    )
    assert move == "rock"
    assert "predicted scissors" in thought


# ---------- battle state ----------


@pytest.fixture
def fixed_boss(monkeypatch):
    """Make every boss play the move stored in ``fixed_boss['move']``."""
    choice = {"move": "scissors"}
    monkeypatch.setattr(
        bosses, "choose", lambda *_args: (choice["move"], "Fixed for the test.")
    )
    return choice


def test_win_damages_boss(fixed_boss):
    state = battle.new_game("classic")
    result = battle.play_round(state, "rock", random.Random(0))
    assert result["outcome"] == "win"
    assert result["explanation"] == "Rock crushes scissors"
    assert state["boss_hp"] == bosses.BOSSES[0]["hp"] - 1
    assert state["stats"]["streak"] == 1
    assert fixed_boss["move"] == "scissors"


def test_loss_damages_player(fixed_boss):
    state = battle.new_game("classic")
    fixed_boss["move"] = "paper"
    battle.play_round(state, "rock", random.Random(0))
    assert state["player_hp"] == battle.PLAYER_HP - 1
    assert state["stats"]["losses"] == 1


def test_defeating_a_boss_advances_and_heals(fixed_boss):
    state = battle.new_game("classic")
    state["player_hp"] = 2
    for _ in range(bosses.BOSSES[0]["hp"]):
        result = battle.play_round(state, "rock", random.Random(0))
    assert result["defeated"] == "rocky"
    assert state["boss"] == 1
    assert state["boss_hp"] == bosses.BOSSES[1]["hp"]
    assert state["player_hp"] == battle.PLAYER_HP
    assert fixed_boss


def test_beating_every_boss_makes_you_champion(fixed_boss):
    state = battle.new_game("classic")
    total = sum(b["hp"] for b in bosses.BOSSES)
    for _ in range(total):
        battle.play_round(state, "rock", random.Random(0))
    assert state["status"] == "champion"
    assert fixed_boss


def test_running_out_of_health_ends_the_run(fixed_boss):
    state = battle.new_game("classic")
    fixed_boss["move"] = "paper"
    for _ in range(battle.PLAYER_HP):
        battle.play_round(state, "rock", random.Random(0))
    assert state["status"] == "lost"
    with pytest.raises(ValueError):
        battle.play_round(state, "rock", random.Random(0))


def test_illegal_move_changes_nothing(fixed_boss):
    state = battle.new_game("classic")
    with pytest.raises(ValueError):
        battle.play_round(state, "lizard", random.Random(0))
    assert not state["history"]
    assert fixed_boss


def test_oracle_sees_the_whole_run_but_others_only_their_fight(monkeypatch):
    seen = {}

    def spy(boss_id, _mode, history, _rng, _phase):
        seen[boss_id] = len(history)
        return "scissors", ""

    monkeypatch.setattr(bosses, "choose", spy)
    state = battle.new_game("classic")
    state["history"] = rounds("rock", "paper")  # two rounds against boss 0
    state["boss"] = 1
    battle.play_round(state, "rock", random.Random(0))
    assert seen["mirror"] == 0
    state["boss"] = 4
    battle.play_round(state, "rock", random.Random(0))
    assert seen["oracle"] == 3
