"""Click-to-run launcher for the Agent Assurance Harness HTTP API.

Run this file directly (PyCharm green arrow, or `python run_server.py`). It starts a
FastAPI/uvicorn server on http://localhost:8000 serving /api/* for the Possible_UI
frontend (whose Vite dev proxy forwards /api -> :8000).

Equivalent command line: `uvicorn aah.api.server:app --reload --port 8000`.
"""

import uvicorn

if __name__ == "__main__":
    # Import via string so uvicorn's --reload style also works if enabled later.
    uvicorn.run("aah.api.server:app", host="127.0.0.1", port=8000, reload=False)
