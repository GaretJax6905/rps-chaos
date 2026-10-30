"""Real Chromium journeys: pick a mode, play rounds, beat a boss, use the keyboard."""

# pytest injects fixtures by name.
# pylint: disable=redefined-outer-name

import pytest
from playwright.sync_api import Page, expect

import app as web

pytestmark = pytest.mark.e2e


@pytest.fixture
def boss_move(monkeypatch):
    """Fix only the boss's move; real rules, HTTP, and session still run."""
    move = {"value": "scissors"}
    monkeypatch.setattr(web.bosses, "choose", lambda *_a: (move["value"], "Test."))
    return move


def test_classic_round_and_boss_defeat(page: Page, live_server, boss_move):
    """Win three rounds with the mouse and see the first boss fall."""
    page.goto(live_server)
    page.get_by_role("button", name="Rock Paper Scissors The original").click()
    expect(page.locator("#boss-name")).to_have_text("Rocky Boulderson")
    expect(page.locator(".move")).to_have_count(3)

    page.locator('.move[data-move="rock"]').click()
    expect(page.locator("#banner-title")).to_have_text("You win!")
    expect(page.locator("#banner-detail")).to_have_text("Rock crushes scissors")
    expect(page.locator("#stat-wins")).to_have_text("1")

    boss_move["value"] = "rock"
    page.locator('.move[data-move="paper"]').click()
    expect(page.locator("#stat-wins")).to_have_text("2")
    page.locator('.move[data-move="paper"]').click()

    expect(page.get_by_role("dialog")).to_contain_text("Boss defeated!")
    page.get_by_role("button", name="Fight Mirror Max").click()
    expect(page.locator("#boss-name")).to_have_text("Mirror Max")


def test_spock_mode_with_keyboard(page: Page, live_server, boss_move):
    """Choose Lizard Spock with key 2, then play Spock with the K key."""
    page.goto(live_server)
    page.keyboard.press("2")
    expect(page.locator(".move")).to_have_count(5)

    page.keyboard.press("k")
    expect(page.locator("#banner-detail")).to_have_text("Spock smashes scissors")

    boss_move["value"] = "rock"
    page.keyboard.press("s")
    expect(page.locator("#banner-title")).to_have_text("Rocky Boulderson wins")
    expect(page.locator("#stat-losses")).to_have_text("1")


def test_losing_every_heart_shows_game_over(page: Page, live_server, boss_move):
    """Five losses end the run, and Try again starts fresh."""
    boss_move["value"] = "paper"
    page.goto(live_server)
    page.keyboard.press("1")
    expect(page.locator(".move")).to_have_count(3)
    for count in range(1, 6):
        page.keyboard.press("r")
        expect(page.locator("#stat-losses")).to_have_text(str(count))
    expect(page.get_by_role("dialog")).to_contain_text("Game over")
    page.get_by_role("button", name="Try again").click()
    expect(page.locator("#stat-losses")).to_have_text("0")
