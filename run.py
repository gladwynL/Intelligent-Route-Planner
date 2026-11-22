"""Start the Intelligent Route Planning System locally.

    python run.py            -> http://127.0.0.1:8000
"""
import os

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f" * Intelligent Route Planner running on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
