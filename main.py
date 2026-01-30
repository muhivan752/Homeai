# main.py
# Entry point HomeAI backend
# FINAL – bootstrap cleaned & deterministic

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug
    )
