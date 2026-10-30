"""Unit checks for both rulesets, with every matchup written out literally."""

# pylint: disable=missing-function-docstring

import pytest

import rules

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("player", "computer", "expected"),
    [
        ("rock", "rock", "tie"),
        ("rock", "paper", "lose"),
        ("rock", "scissors", "win"),
        ("paper", "rock", "win"),
        ("paper", "paper", "tie"),
        ("paper", "scissors", "lose"),
        ("scissors", "rock", "lose"),
        ("scissors", "paper", "win"),
        ("scissors", "scissors", "tie"),
    ],
)
def test_classic_rules(player, computer, expected):
    assert rules.determine_winner("classic", player, computer) == expected


SPOCK_TABLE = {
    # player:   rock    paper   scissors lizard  spock
    "rock": ("tie", "lose", "win", "win", "lose"),
    "paper": ("win", "tie", "lose", "lose", "win"),
    "scissors": ("lose", "win", "tie", "win", "lose"),
    "lizard": ("lose", "win", "lose", "tie", "win"),
    "spock": ("win", "lose", "win", "lose", "tie"),
}
SPOCK_CASES = [
    (player, computer, row[i])
    for player, row in SPOCK_TABLE.items()
    for i, computer in enumerate(("rock", "paper", "scissors", "lizard", "spock"))
]


@pytest.mark.parametrize(("player", "computer", "expected"), SPOCK_CASES)
def test_spock_rules(player, computer, expected):
    assert rules.determine_winner("spock", player, computer) == expected


def test_every_spock_move_beats_two_and_loses_to_two():
    for move in rules.moves_for("spock"):
        results = [rules.determine_winner("spock", move, o) for o in SPOCK_TABLE]
        assert results.count("win") == 2
        assert results.count("lose") == 2


@pytest.mark.parametrize(
    ("mode", "player", "computer", "sentence"),
    [
        ("classic", "paper", "rock", "Paper covers rock"),
        ("classic", "paper", "scissors", "Scissors cuts paper"),
        ("spock", "spock", "rock", "Spock vaporizes rock"),
        ("spock", "paper", "lizard", "Lizard eats paper"),
    ],
)
def test_explain_names_the_winner(mode, player, computer, sentence):
    assert rules.explain(mode, player, computer) == sentence


def test_explain_tie():
    assert "stalemate" in rules.explain("classic", "rock", "rock")


def test_counters():
    assert rules.counters("classic", "rock") == ("paper",)
    assert rules.counters("spock", "rock") == ("paper", "spock")


def test_lizard_is_illegal_in_classic():
    with pytest.raises(ValueError):
        rules.determine_winner("classic", "lizard", "rock")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        rules.moves_for("chess")
