#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dashboard import serve
from monitor import Monitor
from storage import Database

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Surveille des domaines et affiche leur uptime."
    )
    parser.add_argument("--domains", required=True, help="Fichier texte des cibles")
    parser.add_argument("--from-email", required=True, help="Adresse Gmail d'envoi")
    parser.add_argument(
        "--password",
        nargs="?",
        const="",
        default=None,
        help="Mot de passe d'application. Sans valeur, il est demandé au clavier.",
    )
    parser.add_argument(
        "--frequency",
        type=int,
        default=300,
        help="Secondes entre deux contrôles (défaut : 300)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Adresse de l'interface web")
    parser.add_argument("--port", type=int, default=8080, help="Port de l'interface web")
    parser.add_argument(
        "--db",
        default=str(ROOT / "data" / "uptime.db"),
        help="Base SQLite des mesures",
    )
    parser.add_argument(
        "--retain-days",
        type=int,
        default=30,
        help="Jours d'historique conservés (défaut : 30)",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Ne lance que les contrôles, sans interface",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="N'ouvre pas le navigateur automatiquement",
    )
    return parser


def resolve_password(value: str | None) -> str:
    if value:
        return value
    if sys.stdin.isatty():
        typed = getpass.getpass("Mot de passe de l'e-mail d'envoi : ")
        if typed:
            return typed
    logger.error(
        "Mot de passe e-mail manquant. Passez-le avec --password, "
        "ou lancez la commande dans un terminal pour le saisir."
    )
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    domains = Path(args.domains).expanduser().resolve()
    if not domains.is_file():
        logger.error("Fichier de domaines introuvable : %s", domains)
        return 1
    if args.frequency < 5:
        logger.error("La fréquence doit être d'au moins 5 secondes.")
        return 1
    if not 0 <= args.port <= 65535:
        logger.error("Port invalide : %s", args.port)
        return 1
    if args.retain_days < 1:
        logger.error("La rétention doit être d'au moins 1 jour.")
        return 1

    password = resolve_password(args.password)
    db_path = Path(args.db).expanduser().resolve()
    database = Database(db_path)
    monitor = Monitor(
        db=database,
        domains_path=domains,
        from_email=args.from_email,
        password=password,
        frequency=args.frequency,
        retain_days=args.retain_days,
    )
    monitor.publish_targets()
    logger.info("Mesures enregistrées dans %s", db_path)

    if args.no_dashboard:
        try:
            monitor.run()
        except KeyboardInterrupt:
            logger.info("Arrêt demandé.")
        finally:
            monitor.stop()
        return 0

    worker = threading.Thread(target=_run_monitor, args=(monitor,), name="uptime-monitor", daemon=True)
    worker.start()

    def on_ready(url: str) -> None:
        if args.no_browser or args.host not in {"127.0.0.1", "localhost", "::1"}:
            return
        threading.Thread(target=_open_browser, args=(url,), name="open-browser", daemon=True).start()

    try:
        serve(db_path, args.host, args.port, args.frequency, args.retain_days, on_ready=on_ready)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé.")
    finally:
        monitor.stop()
    return 0


def _run_monitor(monitor: Monitor) -> None:
    try:
        monitor.run()
    except Exception:
        logger.exception("Le moniteur s'est arrêté.")


def _open_browser(url: str) -> None:
    time.sleep(0.4)
    if _open_host_browser(url):
        return
    logger.info("Ouvrez %s dans le navigateur.", url)


def _open_host_browser(url: str) -> bool:
    if _is_wsl():
        return _open_windows_browser(url)
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def _open_windows_browser(url: str) -> bool:
    cmd = shutil.which("cmd.exe")
    if not cmd:
        return False
    try:
        completed = subprocess.run(
            [cmd, "/c", "start", "", url],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return completed.returncode == 0


if __name__ == "__main__":
    sys.exit(main())
