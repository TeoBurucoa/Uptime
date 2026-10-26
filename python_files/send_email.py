from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from email.mime.text import MIMEText

from manage_files import create_email_fail_file

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(
    from_email: str,
    password: str,
    to_email: str,
    domain: str,
    message: str,
    current_time: str,
    event_type: str,
    check_type: str,
    libelle: str,
    fail_folder: str | None = None,
) -> bool:
    """Envoie une alerte ou un message de rétablissement via Gmail."""
    if event_type == "alert":
        subject = f"Alerte : {libelle} - {domain} est DOWN - {check_type}"
    elif event_type == "recovery":
        subject = f"UP : {libelle} - {domain} est de nouveau UP - {check_type}"
    else:
        logger.error("Type d'événement inconnu : %s", event_type)
        return False

    msg = MIMEText(message, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    last_error = "Gmail a fermé la connexion avant la fin de l'envoi"
    for attempt in range(2):
        try:
            _deliver(from_email, password, msg)
            logger.info("E-mail %s envoyé à %s", event_type, to_email)
            return True
        except smtplib.SMTPAuthenticationError as exc:
            last_error = f"mot de passe d'application refusé ({exc.smtp_code})"
            break
        except smtplib.SMTPServerDisconnected:
            last_error = "Gmail a fermé la connexion avant la fin de l'envoi"
            if attempt == 0:
                logger.info("Nouvel essai d'envoi vers %s.", to_email)
                continue
        except Exception as exc:
            last_error = str(exc)
            break

    error_msg = f"Échec de l'e-mail {event_type} vers {to_email} : {last_error}"
    logger.error(error_msg)
    create_email_fail_file(error_msg, current_time, to_email, fail_folder)
    return False


def _deliver(from_email: str, password: str, msg: MIMEText) -> None:
    context = ssl.create_default_context()
    with _open_smtp(timeout=20) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(from_email, password)
        server.send_message(msg)


def _open_smtp(timeout: float) -> smtplib.SMTP:
    """Ouvre une session Gmail en IPv4.

    Sous WSL, IPv6 vers smtp.gmail.com est souvent injoignable. Le client
    SMTP standard peut alors garder une socket déjà fermée.
    """
    try:
        return _SMTP4(SMTP_SERVER, SMTP_PORT, timeout=timeout)
    except OSError as exc:
        logger.info("IPv4 indisponible vers %s (%s), nouvel essai.", SMTP_SERVER, exc)
        return smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=timeout)


class _SMTP4(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        last_error: Exception | None = None
        records = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        for family, socktype, proto, _canon, sockaddr in records:
            sock = socket.socket(family, socktype, proto)
            if timeout is not None:
                sock.settimeout(timeout)
            try:
                sock.connect(sockaddr)
                return sock
            except OSError as exc:
                last_error = exc
                sock.close()
        raise OSError(f"Connexion IPv4 impossible vers {host}:{port}") from last_error
