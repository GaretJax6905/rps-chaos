"""Start the game locally. Saved Python changes restart the server."""

import os

from app import app

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5050")),
        debug=False,
        use_reloader=True,
    )
