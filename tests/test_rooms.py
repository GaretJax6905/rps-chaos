"""Online rooms: unit checks on rooms.py and integration checks through Flask."""

# pytest injects fixtures by name.
# pylint: disable=missing-function-docstring,redefined-outer-name

import pytest

import app as web
import rooms


@pytest.fixture(autouse=True)
def empty_rooms():
    rooms.reset()
    yield
    rooms.reset()


@pytest.fixture
def client():
    web.app.config.update(TESTING=True)
    return web.app.test_client()


# ---------- unit ----------


@pytest.mark.unit
def test_moves_stay_hidden_until_both_lock_in():
    code, alice = rooms.create("classic", 3, "Alice", now=0)
    bob = rooms.join(code, "Bob", now=1)
    after_alice = rooms.submit(code, alice, "rock", now=2)
    bob_view = rooms.state(code, bob, now=3)
    assert after_alice["your_move"] == "rock"
    assert bob_view["opponent_locked"] is True
    assert "rock" not in str({k: v for k, v in bob_view.items() if k != "moves"})


@pytest.mark.unit
def test_round_resolves_from_each_players_side():
    code, alice = rooms.create("classic", 3, "Alice", now=0)
    bob = rooms.join(code, "Bob", now=0)
    rooms.submit(code, alice, "paper", now=0)
    bob_view = rooms.submit(code, bob, "rock", now=0)
    assert bob_view["last"]["moves"] == ["paper", "rock"]
    assert bob_view["last"]["winner"] == 0
    assert bob_view["last"]["explanation"] == "Paper covers rock"
    assert bob_view["scores"] == [1, 0]
    assert bob_view["you"] == 1


@pytest.mark.unit
def test_match_ends_at_target_and_rematch_needs_both():
    code, alice = rooms.create("spock", 1, "", now=0)
    bob = rooms.join(code, "", now=0)
    rooms.submit(code, alice, "spock", now=0)
    done = rooms.submit(code, bob, "rock", now=0)
    assert done["status"] == "finished"
    assert done["winner"] == 0
    assert done["names"] == ["Player 1", "Player 2"]
    with pytest.raises(rooms.RoomError):
        rooms.submit(code, alice, "rock", now=0)
    assert rooms.rematch(code, alice, now=0)["scores"] == [1, 0]
    assert rooms.rematch(code, bob, now=0)["scores"] == [0, 0]


@pytest.mark.unit
def test_third_player_and_strangers_are_refused():
    code, _ = rooms.create("classic", 3, "A", now=0)
    rooms.join(code, "B", now=0)
    with pytest.raises(rooms.RoomError) as full:
        rooms.join(code, "C", now=0)
    assert full.value.status == 409
    with pytest.raises(rooms.RoomError) as stranger:
        rooms.state(code, "not-a-token", now=0)
    assert stranger.value.status == 403


@pytest.mark.unit
def test_rooms_expire():
    code, token = rooms.create("classic", 3, "A", now=0)
    rooms.create("classic", 3, "B", now=rooms.EXPIRE_AFTER + 1)
    with pytest.raises(rooms.RoomError) as gone:
        rooms.state(code, token, now=rooms.EXPIRE_AFTER + 2)
    assert gone.value.status == 404


# ---------- integration ----------


@pytest.mark.integration
def test_share_link_page_carries_room_code(client):
    page = client.get("/r/abcd").get_data(as_text=True)
    assert '"room": "ABCD"' in page


@pytest.mark.integration
def test_full_online_round_over_http(client):
    created = client.post("/api/rooms", json={"mode": "classic", "name": "Tom"})
    code = created.get_json()["room"]["code"]
    host = {"X-Player-Token": created.get_json()["token"]}
    joined = client.post(f"/api/rooms/{code}/join", json={"name": "Mercedes"})
    guest = {"X-Player-Token": joined.get_json()["token"]}
    assert joined.get_json()["room"]["names"] == ["Tom", "Mercedes"]

    client.post(f"/api/rooms/{code}/move", json={"move": "scissors"}, headers=host)
    room = client.post(
        f"/api/rooms/{code}/move", json={"move": "paper"}, headers=guest
    ).get_json()["room"]
    assert room["scores"] == [1, 0]
    assert room["last"]["explanation"] == "Scissors cuts paper"

    polled = client.get(f"/api/rooms/{code}", headers=host).get_json()["room"]
    assert polled["round"] == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/api/rooms", {"mode": "chess"}, 400),
        ("/api/rooms", {"mode": "classic", "target": 99}, 400),
        ("/api/rooms/ZZZZ/join", {}, 404),
    ],
)
def test_bad_room_requests(client, path, body, status):
    response = client.post(path, json=body)
    assert response.status_code == status
    assert response.get_json()["error"]


@pytest.mark.integration
def test_illegal_online_move_and_double_lock(client):
    created = client.post("/api/rooms", json={"mode": "classic"}).get_json()
    code, host = created["room"]["code"], {"X-Player-Token": created["token"]}
    early = client.post(f"/api/rooms/{code}/move", json={"move": "rock"}, headers=host)
    assert early.status_code == 400  # no opponent yet
    client.post(f"/api/rooms/{code}/join", json={})
    bad = client.post(f"/api/rooms/{code}/move", json={"move": "spock"}, headers=host)
    assert bad.status_code == 400
    client.post(f"/api/rooms/{code}/move", json={"move": "rock"}, headers=host)
    again = client.post(f"/api/rooms/{code}/move", json={"move": "rock"}, headers=host)
    assert again.status_code == 409


@pytest.mark.integration
def test_shot_clock_heals_boss_through_api(client, monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(web, "clock", lambda: now["t"])
    client.post("/api/new", json={"mode": "classic", "shot_clock": True})
    with client.session_transaction() as session:
        game = session["game"]
        game["boss_hp"] = 1
        session["game"] = game
    now["t"] += 1.5 + 5 + 3  # grace + limit + one regen
    state = client.get("/api/state").get_json()["state"]
    assert state["healed"] == 2
    assert state["boss_hp"] == 3
    assert state["clock"]["on"] is True
    client.post("/api/clock/restart")
    assert client.get("/api/state").get_json()["state"]["clock"]["left"] == 5


@pytest.mark.integration
def test_pwa_files_are_served(client):
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.get_json()["display"] == "standalone"
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert b"/api/" in worker.data
