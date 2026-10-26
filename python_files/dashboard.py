from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from storage import Database

logger = logging.getLogger(__name__)

HTML_PATH = Path(__file__).with_name("dashboard.html")


class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    db_path: str
    frequency_seconds: int
    retain_days: int


class StatusHandler(BaseHTTPRequestHandler):
    server: ReusableServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, "text/html; charset=utf-8", HTML_PATH.read_bytes())
            return
        if path == "/api/status":
            payload = Database(Path(self.server.db_path)).snapshot(
                self.server.frequency_seconds,
                self.server.retain_days,
            )
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self._send(404, "text/plain; charset=utf-8", b"Introuvable")

    def log_message(self, fmt: str, *args) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Client déconnecté pendant l'envoi.")


def make_server(db_path: Path, host: str, port: int, frequency: int, retain_days: int) -> ReusableServer:
    server = ReusableServer((host, port), StatusHandler)
    server.db_path = str(db_path)
    server.frequency_seconds = frequency
    server.retain_days = retain_days
    return server


def serve(db_path: Path, host: str, port: int, frequency: int, retain_days: int, on_ready=None) -> None:
    try:
        server = make_server(db_path, host, port, frequency, retain_days)
    except OSError as exc:
        logger.error("Impossible d'écouter sur %s:%s (%s)", host, port, exc)
        raise SystemExit(1) from exc

    bound_port = server.server_address[1]
    visible_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{visible_host}:{bound_port}"
    logger.info("Interface disponible sur %s", url)
    if on_ready is not None:
        on_ready(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
