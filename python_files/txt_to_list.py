from __future__ import annotations

import logging
from pathlib import Path

from models import Target

logger = logging.getLogger(__name__)

VALID_PROTOCOLS = {"HTTP", "HTTPS", "PING"}


def txt_to_list(file_path: str) -> list[Target]:
    """Lit le fichier de cibles. Les lignes vides et les commentaires sont ignorés."""
    return load_targets(file_path)


def load_targets(file_path: str) -> list[Target]:
    path = Path(file_path)
    text = path.read_text(encoding="utf-8-sig")
    by_key: dict[str, Target] = {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            logger.warning(
                "Ligne %s ignorée : 4 colonnes attendues (protocole | domaine | email | libellé).",
                lineno,
            )
            continue

        protocol, domain, email, label = parts
        protocol = protocol.upper()
        domain = _normalize_domain(domain)
        if protocol not in VALID_PROTOCOLS:
            logger.warning("Ligne %s ignorée : protocole inconnu %r.", lineno, protocol)
            continue
        if not domain or any(char.isspace() for char in domain):
            logger.warning("Ligne %s ignorée : domaine invalide.", lineno)
            continue
        if not _looks_like_email(email):
            logger.warning("Ligne %s ignorée : e-mail invalide.", lineno)
            continue

        target = Target(
            protocol=protocol,
            domain=domain,
            to_email=email,
            label=label or domain,
        )
        if target.key in by_key:
            logger.warning("Ligne %s : la cible %s remplace la précédente.", lineno, target.key)
        by_key[target.key] = target

    return list(by_key.values())


def get_status_info(file_path: str, status_code: int) -> str:
    """Retourne le libellé associé à un code HTTP ou ping."""
    path = Path(file_path)
    wanted = str(status_code)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return f"{wanted} — description indisponible"

    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 2 and parts[0] == wanted:
            return f"{parts[0]} — {parts[1]}"
    return f"{wanted} — code non documenté"


def _normalize_domain(domain: str) -> str:
    value = domain.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.strip()
    host, separator, rest = value.partition("/")
    return host.lower() + (separator + rest if separator else "")


def _looks_like_email(value: str) -> bool:
    if value.count("@") != 1:
        return False
    local, host = value.split("@")
    return bool(local and host and "." in host and " " not in value)
