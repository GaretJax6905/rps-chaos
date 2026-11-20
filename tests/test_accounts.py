"""Review 2 slice: sign up / sign in -> finish a ladder run -> saved once -> reopen."""

import sqlite3

import pytest

import accounts
import app as web
import battle

PASSWORD = "correct-horse-1"


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch):
    """A test client backed by a fresh SQLite file."""
    monkeypatch.setitem(web.app.config, "TESTING", True)
    monkeypatch.setitem(web.app.config, "DATABASE", str(tmp_path / "test.db"))
    with web.app.test_client() as test_client:
        yield test_client


def _register(client, email="tom@example.com", password=PASSWORD):
    return client.post(
        "/register",
        data={"email": email, "password": password, "display_name": "Tom"},
    )


def _finish_run(client, outcome="lost"):
    """Start a real ladder run, then push it to its last round on the server."""
    assert client.post("/api/new", json={"mode": "classic"}).status_code == 200
    with client.session_transaction() as sess:
        state = sess["game"]
        state["stats"]["bosses"] = 2
        state["stats"]["wins"] = 7
        if outcome == "lost":
            state["player_hp"] = 1
        sess["game"] = state
    # Keep playing until the server itself ends the run.
    for _ in range(200):
        response = client.post("/api/play", json={"move": "rock"})
        body = response.get_json()
        if body["state"]["status"] in ("champion", "lost"):
            return body
    pytest.fail("The run never finished.")
    return None


def test_register_sign_out_sign_in(client):
    """Join and return: register, sign out, sign back in."""
    assert _register(client).status_code == 302
    assert client.get("/dashboard").status_code == 200
    client.post("/logout")
    assert client.get("/dashboard").status_code == 302
    response = client.post(
        "/login", data={"email": "tom@example.com", "password": PASSWORD}
    )
    assert response.status_code == 302
    assert b"Tom's runs" in client.get("/dashboard").data


def test_duplicate_email_and_wrong_password_show_errors(client):
    """Clear errors, and no session is created on failure."""
    _register(client)
    client.post("/logout")
    duplicate = _register(client, email="TOM@example.com")
    assert duplicate.status_code == 400
    assert b"already exists" in duplicate.data
    wrong = client.post(
        "/login", data={"email": "tom@example.com", "password": "not-it-at-all"}
    )
    assert wrong.status_code == 401
    assert b"Wrong email or password" in wrong.data
    assert client.get("/api/results").status_code == 401


def test_only_a_password_hash_is_stored(client):
    """The database never holds the plain password."""
    _register(client)
    db = sqlite3.connect(web.app.config["DATABASE"])
    stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
    db.close()
    assert PASSWORD not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))


def test_finished_run_is_saved_once_and_reopens(client):
    """Play and save, then re-send the finishing request: still one result."""
    _register(client)
    body = _finish_run(client)
    assert body["saved"] is True
    # Re-sending a move after the run ended must not add a second result.
    again = client.post("/api/play", json={"move": "rock"})
    assert again.get_json().get("saved") in (None, False)
    with client.session_transaction() as sess:
        state = sess["game"]
    db = accounts.connect(web.app.config["DATABASE"])
    assert accounts.save_run(db, 1, state, battle.score(state)) is False
    db.close()
    results = client.get("/api/results").get_json()
    assert results["summary"]["played"] == 1
    assert results["runs"][0]["outcome"] == "lost"
    assert results["runs"][0]["bosses_beaten"] == 2


def test_saved_run_survives_a_restart(client):
    """Reopen the saved result from a brand-new connection (server restart)."""
    _register(client)
    _finish_run(client)
    client.post("/logout")
    with web.app.test_client() as fresh:
        fresh.post("/login", data={"email": "tom@example.com", "password": PASSWORD})
        page = fresh.get("/dashboard")
    assert page.status_code == 200
    assert b'id="played">1<' in page.data


def test_client_cannot_send_its_own_score(client):
    """A score in the request body is ignored; the server computes it."""
    _register(client)
    client.post("/api/new", json={"mode": "classic"})
    client.post("/api/play", json={"move": "rock", "score": 999999})
    assert client.get("/api/results").get_json()["summary"]["best"] < 999999


def test_signed_out_runs_are_not_saved(client):
    """Playing without an account still works but saves nothing."""
    body = _finish_run(client)
    assert body["saved"] is None
    _register(client)
    assert client.get("/api/results").get_json()["summary"]["played"] == 0


def test_players_only_see_their_own_runs(client):
    """Account B's dashboard does not show account A's runs."""
    _register(client)
    _finish_run(client)
    client.post("/logout")
    _register(client, email="other@example.com")
    results = client.get("/api/results").get_json()
    assert results["summary"]["played"] == 0
    assert not results["runs"]


def test_new_account_sees_empty_state(client):
    """Friendly empty dashboard for a brand-new account."""
    _register(client)
    assert b"No saved runs yet" in client.get("/dashboard").data
