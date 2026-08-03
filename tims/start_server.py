import os
import socket
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent
os.chdir(PROJECT_ROOT)


def find_free_port(start=8000, end=8100):
    preferred = os.getenv("PORT")
    if preferred:
        try:
            return int(preferred)
        except ValueError:
            pass

    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise RuntimeError("No free local port found between 8000 and 8100")


port = find_free_port()
print(f"Starting TIMS backend on http://127.0.0.1:{port}")
uvicorn.run("backend.main:app", host="127.0.0.1", port=port, reload=False)
