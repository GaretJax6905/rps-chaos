"""Online two-player rooms, kept in memory (one server process).

Each player gets a secret token when creating/joining. A player's move stays
hidden from the other player until both have locked in. Rooms expire after
a period of inactivity. Times are passed in so tests control the clock.
"""

import secrets
import threading

import rules

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L
CODE_LENGTH = 4
EXPIRE_AFTER = 2 * 60 * 60
MAX_ROOMS = 500
NAME_LIMIT = 16
TARGETS = (1, 2, 3, 5)


class RoomError(Exception):
    """A request that cannot be honored; ``status`` is the HTTP status to use."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


_rooms = {}
_lock = threading.Lock()


def _clean_name(name, fallback):
    name = " ".join(str(name or "").split())[:NAME_LIMIT]
    return name or fallback


def _expire(now):
    for code in [c for c, r in _rooms.items() if now - r["touched"] > EXPIRE_AFTER]:
        del _rooms[code]


def _new_code():
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in _rooms:
            return code


def _get(code, now):
    room = _rooms.get(str(code).upper())
    if room is None:
        raise RoomError("That room doesn't exist or has expired.", 404)
    room["touched"] = now
    return room


def _seat(room, token):
    for seat, player in enumerate(room["players"]):
        if player and secrets.compare_digest(player["token"], str(token or "")):
            return seat
    raise RoomError("You're not a player in this room.", 403)


def create(mode, target, name, now):
    """Open a room and seat the creator as player 1. Returns (code, token)."""
    rules.moves_for(mode)
    if target not in TARGETS:
        raise RoomError(
            f"Pick a match length: first to {', '.join(map(str, TARGETS))}."
        )
    with _lock:
        _expire(now)
        if len(_rooms) >= MAX_ROOMS:
            raise RoomError("The server is full right now. Try again soon.", 503)
        code = _new_code()
        token = secrets.token_urlsafe(16)
        _rooms[code] = {
            "code": code,
            "mode": mode,
            "target": target,
            "players": [{"token": token, "name": _clean_name(name, "Player 1")}, None],
            "moves": [None, None],
            "scores": [0, 0],
            "round": 0,
            "last": None,
            "rematch": [False, False],
            "touched": now,
        }
        return code, token


def join(code, name, now):
    """Seat a second player. Returns their token."""
    with _lock:
        room = _get(code, now)
        if room["players"][1] is not None:
            raise RoomError("This room already has two players.", 409)
        token = secrets.token_urlsafe(16)
        room["players"][1] = {"token": token, "name": _clean_name(name, "Player 2")}
        return token


def _winner(room):
    for seat in (0, 1):
        if room["scores"][seat] >= room["target"]:
            return seat
    return None


def submit(code, token, move, now):
    """Lock in a move. Resolves the round when both players have moved."""
    with _lock:
        room = _get(code, now)
        seat = _seat(room, token)
        if room["players"][1] is None:
            raise RoomError("Wait for your opponent to join.")
        if _winner(room) is not None:
            raise RoomError("This match is over. Ask for a rematch!")
        if move not in rules.moves_for(room["mode"]):
            raise RoomError(
                f"Choose one of: {', '.join(rules.moves_for(room['mode']))}."
            )
        if room["moves"][seat] is not None:
            raise RoomError("You already locked in a move this round.", 409)
        room["moves"][seat] = move
        if None not in room["moves"]:
            _resolve(room)
        return view(room, seat)


def _resolve(room):
    first, second = room["moves"]
    outcome = rules.determine_winner(room["mode"], first, second)
    winner = {"win": 0, "lose": 1, "tie": None}[outcome]
    if winner is not None:
        room["scores"][winner] += 1
    room["round"] += 1
    room["last"] = {
        "round": room["round"],
        "moves": [first, second],
        "winner": winner,
        "explanation": rules.explain(room["mode"], first, second),
    }
    room["moves"] = [None, None]
    room["rematch"] = [False, False]


def rematch(code, token, now):
    """Vote for a rematch; when both vote, scores reset."""
    with _lock:
        room = _get(code, now)
        seat = _seat(room, token)
        if _winner(room) is None:
            raise RoomError("The match isn't over yet.")
        room["rematch"][seat] = True
        if all(room["rematch"]):
            room["scores"] = [0, 0]
            room["rematch"] = [False, False]
            room["last"] = None
        return view(room, seat)


def state(code, token, now):
    """The room as one player sees it."""
    with _lock:
        room = _get(code, now)
        return view(room, _seat(room, token))


def view(room, seat):
    """Shape a room for one seat. Never reveals the other player's pending move."""
    other = 1 - seat
    winner = _winner(room)
    if room["players"][1] is None:
        status = "waiting"
    elif winner is not None:
        status = "finished"
    else:
        status = "playing"
    return {
        "code": room["code"],
        "mode": room["mode"],
        "moves": list(rules.moves_for(room["mode"])),
        "target": room["target"],
        "you": seat,
        "names": [p["name"] if p else None for p in room["players"]],
        "scores": list(room["scores"]),
        "round": room["round"],
        "status": status,
        "winner": winner,
        "your_move": room["moves"][seat],
        "opponent_locked": room["moves"][other] is not None,
        "last": room["last"],
        "rematch": {"you": room["rematch"][seat], "opponent": room["rematch"][other]},
    }


def reset():
    """Remove every room (used by tests)."""
    with _lock:
        _rooms.clear()
