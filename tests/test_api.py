"""Integration checks: real Flask requests and JSON responses, no browser."""

# pylint: disable=redefined-outer-name,missing-function-docstring

import pytest

import app as web

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    web.app.config.update(TESTING=True)
    return web.app.test_client()


@pytest.fixture
def boss_plays_scissors(monkeypatch):
    monkeypatch.setattr(web.bosses, "choose", lambda *_args: ("scissors", "Snip."))


def test_page_offers_both_modes(client):
    page = client.get("/").get_data(as_text=True)
    assert 'data-mode="classic"' in page
    assert 'data-mode="spock"' in page
    assert "ORACLE" in page


def test_new_game_starts_against_first_boss(client):
    response = client.post("/api/new", json={"mode": "spock"})
    state = response.get_json()["state"]
    assert response.status_code == 200
    assert state["moves"] == ["rock", "paper", "scissors", "lizard", "spock"]
    assert state["boss"]["id"] == "rocky"
    assert state["player_hp"] == state["player_max"]


@pytest.mark.parametrize("body", [{}, {"mode": "chess"}, None])
def test_unknown_mode_is_rejected(client, body):
    response = client.post("/api/new", json=body)
    assert response.status_code == 400
    assert "Choose a game mode" in response.get_json()["error"]


def test_play_before_starting_is_rejected(client):
    response = client.post("/api/play", json={"move": "rock"})
    assert response.status_code == 400
    assert "Start a game" in response.get_json()["error"]


@pytest.mark.parametrize("move", ["lizard", "", None, "<script>"])
def test_illegal_move_in_classic_is_rejected(client, move):
    client.post("/api/new", json={"mode": "classic"})
    response = client.post("/api/play", json={"move": move})
    assert response.status_code == 400
    assert "Choose one of" in response.get_json()["error"]


@pytest.mark.usefixtures("boss_plays_scissors")
def test_round_uses_real_rules_and_updates_session(client):
    client.post("/api/new", json={"mode": "classic"})
    data = client.post("/api/play", json={"move": "rock"}).get_json()
    assert data["round"]["outcome"] == "win"
    assert data["round"]["explanation"] == "Rock crushes scissors"
    assert data["state"]["boss_hp"] == data["state"]["boss"]["hp"] - 1
    again = client.get("/api/state").get_json()["state"]
    assert again["stats"]["wins"] == 1


@pytest.mark.usefixtures("boss_plays_scissors")
def test_spock_move_works_in_spock_mode(client):
    client.post("/api/new", json={"mode": "spock"})
    data = client.post("/api/play", json={"move": "spock"}).get_json()
    assert data["round"]["outcome"] == "win"
    assert data["round"]["explanation"] == "Spock smashes scissors"


@pytest.mark.usefixtures("boss_plays_scissors")
def test_oracle_hides_its_prediction_during_its_fight(client):
    client.post("/api/new", json={"mode": "classic"})
    with client.session_transaction() as session:
        game = session["game"]
        game["boss"] = 4
        game["boss_hp"] = 5
        session["game"] = game
    for _ in range(4):
        data = client.post("/api/play", json={"move": "rock"}).get_json()
    assert data["state"]["brain"]["locked"] is True
    assert data["state"]["brain"]["prediction"] is None
