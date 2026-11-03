"""v3: power-ups between bosses, Peek, Endless mode tiers, and scoring."""

# pytest injects fixtures by name.
# pylint: disable=missing-function-docstring,redefined-outer-name

import random

import pytest

import app as web
import battle
import bosses


@pytest.fixture
def boss_move(monkeypatch):
    move = {"value": "scissors"}
    monkeypatch.setattr(bosses, "choose", lambda *_a: (move["value"], "Test."))
    return move


def beat_current_boss(state):
    """Win rounds (boss plays scissors) until the current boss falls."""
    while not state["offer"] and state["status"] == "playing":
        battle.play_round(state, "rock", random.Random(0))


# ---------- unit: power-ups ----------


@pytest.mark.unit
@pytest.mark.usefixtures("boss_move")
def test_must_choose_powerup_before_next_round():
    state = battle.new_game("classic")
    beat_current_boss(state)
    assert set(state["offer"]) <= set(battle.POWERUPS)
    with pytest.raises(ValueError, match="power-up"):
        battle.play_round(state, "rock", random.Random(0))
    with pytest.raises(ValueError):
        battle.choose_powerup(state, "not-offered")


@pytest.mark.unit
def test_shield_blocks_one_loss(boss_move):
    state = battle.new_game("classic")
    state["items"]["shield"] = 1
    boss_move["value"] = "paper"
    first = battle.play_round(state, "rock", random.Random(0))
    second = battle.play_round(state, "rock", random.Random(0))
    assert first["shielded"] is True and second["shielded"] is False
    assert state["player_hp"] == battle.PLAYER_HP - 1


@pytest.mark.unit
@pytest.mark.usefixtures("boss_move")
def test_double_strike_deals_two_damage_once():
    state = battle.new_game("classic")
    state["boss"], state["boss_hp"] = 4, 5
    state["items"]["double"] = 1
    first = battle.play_round(state, "rock", random.Random(0))
    second = battle.play_round(state, "rock", random.Random(0))
    assert (first["damage"], second["damage"]) == (2, 1)
    assert state["boss_hp"] == 2


@pytest.mark.unit
def test_heal_and_vitality():
    state = battle.new_game("classic")
    state["player_hp"] = 1
    state["offer"] = ["heal"]
    battle.choose_powerup(state, "heal")
    assert state["player_hp"] == battle.PLAYER_HP
    state["offer"] = ["vitality"]
    battle.choose_powerup(state, "vitality")
    assert (state["player_max"], state["player_hp"]) == (6, 6)


@pytest.mark.unit
def test_peek_reveals_the_move_the_boss_then_plays(monkeypatch):
    picks = iter(["paper", "rock"])
    monkeypatch.setattr(bosses, "choose", lambda *_a: (next(picks), "Hmm."))
    state = battle.new_game("classic")
    with pytest.raises(ValueError, match="Peek"):
        battle.use_peek(state, random.Random(0))
    state["items"]["peek"] = 1
    seen = battle.use_peek(state, random.Random(0))
    assert seen == "paper"
    assert battle.use_peek(state, random.Random(0)) == "paper"  # no double charge
    result = battle.play_round(state, "scissors", random.Random(0))
    assert result["computer"] == "paper"
    assert result["outcome"] == "win"
    assert state["items"]["peek"] == 0


# ---------- unit: endless ----------


@pytest.mark.unit
def test_endless_bosses_loop_in_tougher_tiers():
    first, sixth, eleventh = (bosses.boss_for(i) for i in (0, 5, 10))
    assert first["name"] == "Rocky Boulderson" and first["tier"] == 1
    assert sixth["name"] == "Rocky Boulderson II"
    assert sixth["hp"] == first["hp"] + 2
    assert eleventh["name"] == "Rocky Boulderson III"
    assert eleventh["title"].startswith("Tier 3")


@pytest.mark.unit
@pytest.mark.usefixtures("boss_move")
def test_endless_continues_past_oracle_and_scores():
    state = battle.new_game("classic", endless=True)
    for _ in range(6):
        beat_current_boss(state)
        battle.choose_powerup(state, state["offer"][0])
    assert state["status"] == "playing"
    assert state["boss"] == 6
    assert battle.current_boss(state)["name"] == "Mirror Max II"
    wins = state["stats"]["wins"]
    assert battle.score(state) == 6 * battle.POINTS_PER_BOSS + wins * 10


@pytest.mark.unit
@pytest.mark.usefixtures("boss_move")
def test_shot_clock_pauses_while_choosing_powerup():
    state = battle.new_game("classic", shot_clock=True, now=0)
    beat_current_boss(state)
    assert battle.apply_delay(state, 999) == 0


# ---------- integration ----------


@pytest.fixture
def client():
    web.app.config.update(TESTING=True)
    return web.app.test_client()


@pytest.mark.integration
@pytest.mark.usefixtures("boss_move")
def test_powerup_and_peek_over_http(client):
    client.post("/api/new", json={"mode": "classic", "endless": True})
    for _ in range(3):
        data = client.post("/api/play", json={"move": "rock"}).get_json()
    state = data["state"]
    assert data["round"]["defeated"] == "rocky"
    assert state["endless"] is True and state["boss"]["count"] is None
    assert len(state["offer"]) == 3
    blocked = client.post("/api/play", json={"move": "rock"})
    assert blocked.status_code == 400

    with client.session_transaction() as session:
        game = session["game"]
        game["offer"] = ["peek", "shield", "heal"]
        session["game"] = game
    picked = client.post("/api/powerup", json={"id": "peek"}).get_json()
    assert picked["state"]["items"]["peek"] == 1
    peeked = client.post("/api/peek", json={}).get_json()
    assert peeked["move"] == "scissors"
    assert peeked["state"]["peeked"] == "scissors"
    bad = client.post("/api/powerup", json={"id": "heal"})
    assert bad.status_code == 400


@pytest.mark.integration
def test_old_session_is_upgraded(client):
    with client.session_transaction() as session:
        session["game"] = {
            "mode": "classic",
            "boss": 0,
            "boss_hp": 3,
            "player_hp": 5,
            "status": "playing",
            "history": [],
            "stats": {"rounds": 0, "wins": 0, "losses": 0, "ties": 0, "streak": 0},
        }
    state = client.get("/api/state").get_json()["state"]
    assert state["items"] == {"shield": 0, "double": 0, "peek": 0}
    assert state["score"] == 0
