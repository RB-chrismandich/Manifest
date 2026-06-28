"""Stub HTTP + HTML server for executor tests (``api`` and ``ui`` step types).

Stdlib-only (no Flask/uvicorn). Serves a handful of deterministic endpoints plus
one *eventually-consistent* endpoint (``/webhooks/last``) that 500s until the
N-th call, to exercise the opt-in ``retry`` path. Start it with the
``run_stub_server`` context manager, which binds an ephemeral port and yields the
base URL.
"""

from __future__ import annotations

import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

PAGE_HTML = """<!doctype html>
<html><head><title>Invoice 1001</title></head>
<body>
  <h1 id="title">Invoice 1001</h1>
  <span data-test="amount">$100.00</span>
  <a id="link" href="/invoices/1001">view invoice</a>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    # Class-level counter for the eventually-consistent webhook (retry test).
    webhook_calls = 0
    webhook_ready_after = 2

    def log_message(self, *args):  # pragma: no cover - silence test noise
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, text: str) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            return self._json(200, {"ok": True})
        if self.path == "/page" or self.path.startswith("/invoices/"):
            return self._html(200, PAGE_HTML)
        if self.path == "/webhooks/last":
            cls = type(self)
            cls.webhook_calls += 1
            if cls.webhook_calls >= cls.webhook_ready_after:
                return self._json(200, {"delivered": True})
            return self._json(500, {"delivered": False})
        return self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            json.loads(raw or b"{}")
        except json.JSONDecodeError:
            pass
        if self.path == "/login":
            # Return a session id derived server-side; never echo the secret token.
            return self._json(200, {"session_id": "sess-abc123"})
        if self.path == "/invoices":
            return self._json(201, {"id": 1001, "amount": "$100.00"})
        return self._json(404, {"error": "not found"})


@contextlib.contextmanager
def run_stub_server() -> Iterator[str]:
    """Run the stub server on an ephemeral port; yield its base URL."""
    _Handler.webhook_calls = 0  # reset flaky counter per server instance
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
