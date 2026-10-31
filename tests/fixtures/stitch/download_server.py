"""Loopback-only signed-URL fixture; never contacts an external service."""

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    """Serve a redirect, normal bytes, or a synthetic HTTP error."""

    def do_GET(self):
        """Respond using only controlled test data."""
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header(
                "Location", "/asset?token=redirect-capability#redirect-fragment"
            )
            self.end_headers()
        elif self.path.startswith("/error"):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"synthetic-capability")
        else:
            body = b"local asset bytes"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *_args):
        """Keep test server access logs from echoing synthetic signed URLs."""


server = HTTPServer(("127.0.0.1", 0), Handler)
Path(sys.argv[1]).write_text(str(server.server_port))
server.serve_forever()
