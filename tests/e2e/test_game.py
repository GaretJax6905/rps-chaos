"""Real Chromium journeys through every way to play."""

# pytest injects fixtures by name.
# pylint: disable=redefined-outer-name

import re

import pytest
from playwright.sync_api import Browser, Page, expect

import app as web
import battle
import rooms

pytestmark = pytest.mark.e2e


@pytest.fixture
def boss_move(monkeypatch):
    """Fix only the boss's move; real rules, HTTP, and session still run."""
    move = {"value": "scissors"}
    monkeypatch.setattr(web.bosses, "choose", lambda *_a: (move["value"], "Test."))
    return move


@pytest.fixture(autouse=True)
def empty_rooms():
    """Start and end every browser test with no online rooms."""
    rooms.reset()
    yield
    rooms.reset()


def test_ladder_round_phase_two_and_boss_defeat(page: Page, live_server, boss_move):
    """Beat Rocky with the mouse: phase 2 at half health, then the next boss."""
    page.goto(live_server)
    page.get_by_role("button", name=re.compile("Boss Ladder")).click()
    expect(page.locator("#boss-name")).to_have_text("Rocky Boulderson")
    expect(page.locator("#moves .move")).to_have_count(3)

    page.locator('#moves .move[data-move="rock"]').click()
    expect(page.locator("#banner-title")).to_have_text("You win!")
    expect(page.locator("#banner-detail")).to_have_text("Rock crushes scissors")

    page.locator('#moves .move[data-move="rock"]').click()
    expect(page.locator("#boss-title")).to_contain_text("PHASE 2")
    expect(page.locator("#arena")).to_have_class(re.compile("phase2"))

    boss_move["value"] = "rock"
    page.locator('#moves .move[data-move="paper"]').click()
    expect(page.get_by_role("dialog")).to_contain_text("Boss defeated!")
    expect(page.locator(".offer-card")).to_have_count(3)
    page.locator(".offer-card").first.click()
    expect(page.locator("#boss-name")).to_have_text("Mirror Max")
    expect(page.locator("#banner-title")).to_have_text("New challenger!")


def test_spock_ladder_with_keyboard(page: Page, live_server, boss_move):
    """Pick Lizard Spock, start the ladder with key 1, then play Spock with K."""
    page.goto(live_server)
    page.locator('input[name="ruleset"][value="spock"]').check()
    page.keyboard.press("1")
    expect(page.locator("#moves .move")).to_have_count(5)
    page.keyboard.press("k")
    expect(page.locator("#banner-detail")).to_have_text("Spock smashes scissors")
    boss_move["value"] = "rock"
    page.keyboard.press("s")
    expect(page.locator("#banner-title")).to_have_text("Rocky Boulderson wins")


def test_losing_every_heart_shows_game_over(page: Page, live_server, boss_move):
    """Five losses end the run, and Try again starts fresh."""
    boss_move["value"] = "paper"
    page.goto(live_server)
    page.keyboard.press("1")
    expect(page.locator("#moves .move")).to_have_count(3)
    for count in range(1, 6):
        page.keyboard.press("r")
        expect(page.locator("#stat-losses")).to_have_text(str(count))
    expect(page.get_by_role("dialog")).to_contain_text("Game over")
    page.get_by_role("button", name="Try again").click()
    expect(page.locator("#stat-losses")).to_have_text("0")


def test_shot_clock_heals_the_boss(page: Page, live_server, boss_move, monkeypatch):
    """Stall after a win and the boss heals back for delay of game."""
    monkeypatch.setattr(battle, "CLOCK_LIMIT", 0.6)
    monkeypatch.setattr(battle, "CLOCK_REGEN", 0.6)
    monkeypatch.setattr(battle, "CLOCK_GRACE", 0.0)
    page.goto(live_server)
    page.get_by_label(re.compile("Shot clock")).check()
    page.keyboard.press("1")
    expect(page.locator("#shotclock")).to_be_visible()
    page.keyboard.press("r")
    expect(page.locator("#boss-hpbar")).to_have_attribute("aria-valuenow", "2")
    expect(page.locator("#banner-title")).to_have_text("Delay of game!", timeout=8000)
    expect(page.locator("#boss-hpbar")).to_have_attribute("aria-valuenow", "3")
    assert boss_move["value"] == "scissors"


def test_same_device_match(page: Page, live_server):
    """Two players share one screen; the first pick is hidden behind a hand-off."""
    page.goto(live_server)
    page.keyboard.press("3")
    page.get_by_label("Player 1 name").fill("Tom")
    page.get_by_label("Player 2 name").fill("Mercedes")
    page.get_by_role("button", name="Start match").click()
    expect(page.locator("#duel-title")).to_have_text("Tom, pick your move")

    page.locator('#duel-moves .move[data-move="rock"]').click()
    expect(page.get_by_role("dialog")).to_contain_text("Pass to Mercedes")
    page.get_by_role("button", name="I'm Mercedes — ready").click()
    expect(page.locator("#duel-title")).to_have_text("Mercedes, pick your move")
    expect(page.locator("#duel-pick0")).not_to_contain_text("rock")

    page.locator('#duel-moves .move[data-move="scissors"]').click()
    expect(page.locator("#duel-title")).to_have_text("Tom wins the round!")
    expect(page.locator("#duel-score0")).to_have_text("1")


def test_online_match_between_two_browsers(browser: Browser, live_server):
    """Two separate browser sessions play over the share link."""
    host = browser.new_context().new_page()
    host.goto(live_server)
    host.keyboard.press("4")
    host.get_by_label("Your name").fill("Tom")
    host.get_by_role("button", name="Create room").click()
    link = host.locator("#share-link")
    expect(link).to_have_value(re.compile(r"/r/[A-Z0-9]{4}$"))
    url = link.input_value()

    guest = browser.new_context().new_page()
    guest.goto(url)
    guest.get_by_label("Your name").fill("Mercedes")
    guest.get_by_role("button", name="Join match").click()
    expect(guest.locator("#duel-name1")).to_have_text("Tom")
    expect(host.locator("#duel-name1")).to_have_text("Mercedes")
    expect(host.locator("#share")).to_be_hidden()

    host.locator('#duel-moves .move[data-move="paper"]').click()
    expect(guest.locator("#duel-lock1")).to_have_text("Locked in ✓")
    guest.locator('#duel-moves .move[data-move="rock"]').click()

    expect(host.locator("#duel-title")).to_have_text("You win the round!")
    expect(guest.locator("#duel-title")).to_have_text("Tom wins the round")
    expect(guest.locator("#duel-detail")).to_have_text("Paper covers rock")
    expect(host.locator("#duel-score0")).to_have_text("1")
    expect(guest.locator("#duel-score1")).to_have_text("1")


def test_endless_powerup_and_arcade_high_score(page: Page, live_server, boss_move):
    """Beat a boss, pick a power-up by key, get knocked out, enter initials."""
    page.goto(live_server)
    expect(page.locator("#hiscore-list")).to_contain_text("No scores yet")
    page.keyboard.press("2")
    expect(page.locator("#hud-mode")).to_contain_text("Endless")
    for _ in range(3):
        page.keyboard.press("r")
        page.wait_for_timeout(1000)
    expect(page.locator(".offer-card")).to_have_count(3)
    page.keyboard.press("1")
    expect(page.get_by_role("dialog")).to_be_hidden()
    expect(page.locator("#banner-title")).to_have_text("New challenger!")
    expect(page.locator("#boss-name")).to_have_text("Mirror Max")
    expect(page.locator("#hud-score")).to_have_text("130")

    boss_move["value"] = "paper"
    for losses in range(1, 9):
        page.keyboard.press("r")
        expect(page.locator("#stat-losses")).to_have_text(str(losses))
        page.wait_for_timeout(900)
        if page.get_by_role("dialog").is_visible():
            break
    expect(page.get_by_role("dialog")).to_contain_text("NEW HIGH SCORE!")
    page.get_by_label("Your name for the high score board").fill("tom")
    page.get_by_role("button", name="Save score").click()
    expect(page.get_by_role("dialog")).to_contain_text("You're #1!")
    page.get_by_role("dialog").get_by_role("button", name="Menu").click()
    board = page.locator("#hiscore-list")
    expect(board).to_contain_text("TOM")
    expect(board).to_contain_text("130")


def test_join_online_room_by_typing_the_code(browser: Browser, live_server):
    """A friend who already has the game open joins with the 4-character code."""
    host = browser.new_context().new_page()
    host.goto(live_server)
    host.keyboard.press("4")
    host.get_by_label("Your name").fill("Tom")
    host.get_by_role("button", name="Create room").click()
    code = host.locator("#share-code")
    expect(code).to_have_text(re.compile(r"^[A-Z0-9]{4}$"))
    room = code.inner_text()

    guest = browser.new_context().new_page()
    guest.goto(live_server)
    guest.keyboard.press("4")
    guest.get_by_label("Your name").fill("Mercedes")
    code_box = guest.get_by_label("Room code", exact=True)

    code_box.fill("AB")
    guest.get_by_role("button", name="Join room").click()
    expect(guest.locator("#code-error")).to_contain_text("4 letters")

    code_box.fill("ZZZZ" if room != "ZZZZ" else "YYYY")
    guest.get_by_role("button", name="Join room").click()
    expect(guest.locator("#code-error")).to_contain_text("doesn't exist")

    code_box.fill(room.lower())
    expect(code_box).to_have_value(room)
    guest.get_by_role("button", name="Join room").click()
    expect(guest.locator("#duel-name1")).to_have_text("Tom")
    expect(host.locator("#duel-name1")).to_have_text("Mercedes")
    expect(guest).to_have_url(re.compile(f"/r/{room}$"))
