import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from flask import Flask, send_from_directory  # noqa: E402

import db  # noqa: E402
import seed  # noqa: E402
from api import api_bp  # noqa: E402

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")


def create_app():
    db.init()
    if seed.run():
        print("[store] seeded demo data", flush=True)

    app = Flask(__name__, static_folder=None)
    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return send_from_directory(PUBLIC_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        # Unknown paths fall through to the shell so the client router owns
        # deep links like /store/inventory on a hard refresh.
        full = os.path.join(PUBLIC_DIR, filename)
        if os.path.isfile(full):
            return send_from_directory(PUBLIC_DIR, filename)
        return send_from_directory(PUBLIC_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT") or 3000)
    print(f"Store showcase running at http://localhost:{port}", flush=True)
    app.run(host="127.0.0.1", port=port, threaded=True)
