from __future__ import annotations

import json
import smtplib
import socket
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from dashboard import make_server
from main import _open_host_browser
from manage_files import create_email_fail_file
from manage_time import format_duration
from models import Target
from monitor import Monitor
from probes import ProbeResult, probe_target
from send_email import send_email
from storage import Database, Outcome
from txt_to_list import get_status_info, load_targets


class ParserTests(unittest.TestCase):
    def test_keeps_valid_rows_and_skips_the_rest(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "domains.txt"
            path.write_text(
                "\n".join(
                    [
                        "# commentaire",
                        "",
                        "https | https://Example.com/health | first@example.com | Un",
                        "https | example.com/health | second@example.com | Deux",
                        "ping | 127.0.0.1 | loop@example.com | Loopback",
                        "http | example.com | pas-un-email | Site",
                        "ftp | example.com | a@example.com | X",
                        "http | seulement trois | colonnes",
                    ]
                ),
                encoding="utf-8",
            )
            targets = load_targets(str(path))

        self.assertEqual(
            [(item.protocol, item.domain, item.to_email, item.label) for item in targets],
            [
                ("HTTPS", "example.com/health", "second@example.com", "Deux"),
                ("PING", "127.0.0.1", "loop@example.com", "Loopback"),
            ],
        )
        self.assertEqual(targets[0].key, "HTTPS|example.com/health")
        self.assertNotEqual(Target("HTTP", "a.com", "a@b.co", "A").key, Target("HTTPS", "a.com", "a@b.co", "A").key)

    def test_status_info_uses_the_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "codes.txt"
            path.write_text("404 | Introuvable\n", encoding="utf-8")
            self.assertEqual(get_status_info(str(path), 404), "404 — Introuvable")
            self.assertIn("non documenté", get_status_info(str(path), 418))
            self.assertIn("indisponible", get_status_info(str(Path(folder) / "absent.txt"), 500))


class StorageTests(unittest.TestCase):
    def test_incident_opens_once_and_uptime_uses_a_24h_window(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "uptime.db")
            target = Target("HTTPS", "example.com", "ops@example.com", "Example")
            other = Target("HTTP", "example.com", "ops@example.com", "Example HTTP")
            db.replace_active_targets([target, other])
            old = _iso(datetime.now(timezone.utc) - timedelta(hours=48))
            now = _iso(datetime.now(timezone.utc))

            first = db.record(target, is_up=False, status_code=500, latency_ms=20, detail="panne", checked_at=old)
            second = db.record(target, is_up=False, status_code=500, latency_ms=20, detail="panne", checked_at=old)
            third = db.record(target, is_up=True, status_code=200, latency_ms=10, detail="HTTP 200", checked_at=now)
            db.record(other, is_up=True, status_code=200, latency_ms=5, detail="HTTP 200", checked_at=now)

            self.assertEqual(first[0], Outcome.ALERT)
            self.assertEqual(second[0], Outcome.STILL_DOWN)
            self.assertEqual(third[0], Outcome.RECOVERY)

            snapshot = db.snapshot(frequency_seconds=300, retain_days=30)
            https = snapshot["targets"][0]
            http = snapshot["targets"][1]
            self.assertEqual(https["samples_all"], 3)
            self.assertEqual(https["samples_24h"], 1)
            self.assertEqual(https["uptime_24h"], 1)
            self.assertAlmostEqual(https["uptime_all"], 1 / 3)
            self.assertIsNone(https["incident_started_at"])
            self.assertEqual(http["uptime_24h"], 1)
            self.assertNotEqual(https["protocol"], http["protocol"])

    def test_old_database_receives_the_alert_column(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "uptime.db"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE incidents (
                    id INTEGER PRIMARY KEY,
                    target_key TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    detail TEXT NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()

            Database(path)
            conn = sqlite3.connect(path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(incidents)")]
            conn.close()

        self.assertIn("alert_sent", columns)


class MonitorTests(unittest.TestCase):
    def test_alert_is_sent_once_until_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            domains = Path(folder) / "domains.txt"
            domains.write_text(
                "https | example.com/health | ops@example.com | Example\n",
                encoding="utf-8",
            )
            db = Database(Path(folder) / "uptime.db")
            results = [
                ProbeResult(False, 500, 30, "HTTP 500"),
                ProbeResult(False, 500, 30, "HTTP 500"),
                ProbeResult(True, 200, 12, "HTTP 200"),
            ]
            sent = []

            def probe(protocol, domain, https_errors, ping_errors, timeout=10):
                return results.pop(0)

            def mailer(**kwargs):
                sent.append(kwargs)
                self.assertNotIn("secret-password", kwargs["message"])
                return True

            monitor = Monitor(
                db=db,
                domains_path=domains,
                from_email="from@example.com",
                password="secret-password",
                frequency=300,
                retain_days=30,
                probe=probe,
                mailer=mailer,
            )
            monitor.run_once()
            monitor.run_once()
            monitor.run_once()

        self.assertEqual([item["event_type"] for item in sent], ["alert", "recovery"])
        self.assertIn("Durée de l'incident", sent[1]["message"])

    def test_failed_alert_is_sent_again_while_the_target_is_down(self):
        with tempfile.TemporaryDirectory() as folder:
            domains = Path(folder) / "domains.txt"
            domains.write_text(
                "https | example.com/health | ops@example.com | Example\n",
                encoding="utf-8",
            )
            db = Database(Path(folder) / "uptime.db")
            down = ProbeResult(False, 500, 30, "HTTP 500")
            answers = iter([False, True])
            sent = []

            def probe(protocol, domain, https_errors, ping_errors, timeout=10):
                return down

            def mailer(**kwargs):
                sent.append(kwargs["event_type"])
                return next(answers)

            monitor = Monitor(
                db=db,
                domains_path=domains,
                from_email="from@example.com",
                password="secret-password",
                frequency=300,
                retain_days=30,
                probe=probe,
                mailer=mailer,
            )
            monitor.run_once()
            monitor.run_once()
            monitor.run_once()

        self.assertEqual(sent, ["alert", "alert"])


class ProbeTests(unittest.TestCase):
    def test_http_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Path(folder) / "http.txt"
            catalog.write_text("503 | Service indisponible\n", encoding="utf-8")

            class Response:
                def __init__(self, status_code):
                    self.status_code = status_code

            with patch("probes.requests.get", return_value=Response(204)):
                up = probe_target("HTTP", "example.com", str(catalog), str(catalog), timeout=1)
            with patch("probes.requests.get", return_value=Response(503)):
                down = probe_target("HTTPS", "example.com/health", str(catalog), str(catalog), timeout=1)

        self.assertTrue(up.is_up)
        self.assertEqual(up.detail, "HTTP 204")
        self.assertFalse(down.is_up)
        self.assertIn("Service indisponible", down.detail)

    def test_local_http_and_closed_port(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _QuietOkHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            up = probe_target("HTTP", f"127.0.0.1:{port}", "absent.txt", "absent.txt", timeout=2)
        finally:
            server.shutdown()
            server.server_close()

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            closed = sock.getsockname()[1]
        down = probe_target("HTTP", f"127.0.0.1:{closed}", "absent.txt", "absent.txt", timeout=1)

        self.assertTrue(up.is_up)
        self.assertFalse(down.is_up)
        self.assertIn("Connexion impossible", down.detail)


class EmailTests(unittest.TestCase):
    def test_failure_is_stored_without_the_password(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("send_email._open_smtp", side_effect=OSError("réseau indisponible")):
                sent = send_email(
                    from_email="from@example.com",
                    password="secret-password",
                    to_email="ops@example.com",
                    domain="example.com",
                    message="Exemple",
                    current_time="2026-10-22 22:00:00",
                    event_type="alert",
                    check_type="HTTPS",
                    libelle="Example",
                    fail_folder=folder,
                )
            written = list(Path(folder).glob("*.txt"))
            self.assertFalse(sent)
            self.assertEqual(len(written), 1)
            content = written[0].read_text(encoding="utf-8")
            self.assertNotIn("secret-password", content)
            self.assertIn("ops@example.com", content)

    def test_closed_connection_is_retried_once(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("send_email._deliver", side_effect=smtplib.SMTPServerDisconnected()) as deliver:
                sent = send_email(
                    from_email="from@example.com",
                    password="secret-password",
                    to_email="ops@example.com",
                    domain="example.com",
                    message="Exemple",
                    current_time="2026-10-22 22:00:00",
                    event_type="alert",
                    check_type="HTTPS",
                    libelle="Example",
                    fail_folder=folder,
                )
            content = next(Path(folder).glob("*.txt")).read_text(encoding="utf-8")
        self.assertFalse(sent)
        self.assertEqual(deliver.call_count, 2)
        self.assertIn("Gmail a fermé la connexion", content)
        self.assertNotIn("secret-password", content)

    def test_fail_file_helper(self):
        with tempfile.TemporaryDirectory() as folder:
            path = create_email_fail_file("boom", "2026-10-22 22:00:00", "ops@example.com", folder)
            self.assertTrue(path.is_file())


class BrowserTests(unittest.TestCase):
    def test_wsl_uses_the_windows_browser(self):
        with patch("main._is_wsl", return_value=True), patch(
            "main._open_windows_browser", return_value=True
        ) as windows, patch("main.webbrowser.open") as linux:
            self.assertTrue(_open_host_browser("http://127.0.0.1:8080"))
        windows.assert_called_once_with("http://127.0.0.1:8080")
        linux.assert_not_called()


class DashboardTests(unittest.TestCase):
    def test_page_and_api_show_each_target(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "uptime.db")
            up = Target("HTTPS", "ok.example", "up@example.com", "Site OK")
            down = Target("PING", "10.0.0.8", "down@example.com", "Serveur KO")
            waiting = Target("HTTP", "new.example", "new@example.com", "Nouveau <script>")
            db.replace_active_targets([up, down, waiting])
            now = _iso(datetime.now(timezone.utc))
            earlier = _iso(datetime.now(timezone.utc) - timedelta(minutes=10))
            db.record(up, is_up=True, status_code=200, latency_ms=40, detail="HTTP 200", checked_at=earlier)
            db.record(up, is_up=True, status_code=200, latency_ms=42, detail="HTTP 200", checked_at=now)
            db.record(down, is_up=False, status_code=1, latency_ms=1000, detail="hôte injoignable", checked_at=now)

            server = make_server(db.path, "127.0.0.1", 0, 300, 30)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base, timeout=5) as response:
                    html = response.read().decode("utf-8")
                with urlopen(base + "/api/status", timeout=5) as response:
                    payload = json.load(response)
            finally:
                server.shutdown()
                server.server_close()

        self.assertIn("Uptime sur 24 heures", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual([item["label"] for item in payload["targets"]], ["Site OK", "Serveur KO", "Nouveau <script>"])
        self.assertEqual(payload["targets"][0]["uptime_24h"], 1)
        self.assertEqual(payload["targets"][1]["uptime_24h"], 0)
        self.assertIsNone(payload["targets"][2]["is_up"])
        self.assertEqual(payload["targets"][2]["timeline"], [])
        self.assertIn("Nouveau <script>", json.dumps(payload))
        self.assertNotIn("Nouveau <script>", html)


class DurationTests(unittest.TestCase):
    def test_french_duration(self):
        self.assertEqual(format_duration(0), "0 secondes")
        self.assertEqual(format_duration(61), "1 minute 1 seconde")
        self.assertEqual(format_duration(300), "5 minutes")


class _QuietOkHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    unittest.main()
