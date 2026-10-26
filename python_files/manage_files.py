from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FAIL_FOLDER = ROOT / "email_fail"


def create_email_fail_file(
    error_msg: str,
    current_time: str,
    to_email: str,
    fail_folder: str | None = None,
) -> Path:
    """Enregistre un e-mail qui n'a pas pu partir."""
    folder = Path(fail_folder) if fail_folder else DEFAULT_FAIL_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe(to_email)}-{_safe(current_time)}.txt"
    filepath = folder / filename
    filepath.write_text(
        "Ce message aurait dû être envoyé à "
        f"{to_email}, mais l'envoi a échoué :\n{error_msg}\n",
        encoding="utf-8",
    )
    logger.error("Échec d'envoi conservé dans %s", filepath)
    return filepath


def _safe(value: str) -> str:
    cleaned = [char if char.isalnum() or char in "._-" else "_" for char in value]
    return "".join(cleaned)[:80] or "inconnu"
