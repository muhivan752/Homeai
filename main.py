# main.py
# Entry point HomeAI backend
# FINAL – bootstrap cleaned & deterministic

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=True  # set False in production
    )
