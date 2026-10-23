from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from manage_time import format_duration
from models import Target
from probes import ProbeResult, probe_target
from send_email import send_email
from storage import Database, Outcome
from txt_to_list import load_targets

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
HTTPS_ERRORS = ROOT / "txt_files" / "erreur_https.txt"
PING_ERRORS = ROOT / "txt_files" / "erreur_ping.txt"


class Monitor:
    def __init__(
        self,
        db: Database,
        domains_path: Path,
        from_email: str,
        password: str,
        frequency: int,
        retain_days: int,
        probe=probe_target,
        mailer=send_email,
    ):
        self.db = db
        self.domains_path = Path(domains_path)
        self.from_email = from_email
        self.password = password
        self.frequency = frequency
        self.retain_days = retain_days
        self.probe = probe
        self.mailer = mailer
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def publish_targets(self) -> list[Target]:
        targets = load_targets(str(self.domains_path))
        self.db.replace_active_targets(targets)
        return targets

    def run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.run_once()
            except Exception:
                logger.exception("Le cycle de contrôle a échoué.")
            remaining = self.frequency - (time.monotonic() - started)
            if remaining > 0 and self._stop.wait(remaining):
                return

    def run_once(self) -> None:
        targets = self.publish_targets()
        if not targets:
            logger.warning("Aucune cible valide dans %s", self.domains_path)
            return

        now_local = datetime.now().astimezone().replace(microsecond=0)
        checked_at = now_local.astimezone(timezone.utc).isoformat()
        local_time = now_local.strftime("%Y-%m-%d %H:%M:%S")
        reachable = 0

        for target in targets:
            try:
                result = self.probe(
                    target.protocol,
                    target.domain,
                    str(HTTPS_ERRORS),
                    str(PING_ERRORS),
                )
                outcome, incident_start = self.db.record(
                    target,
                    is_up=result.is_up,
                    status_code=result.status_code,
                    latency_ms=result.latency_ms,
                    detail=result.detail,
                    checked_at=checked_at,
                )
            except Exception:
                logger.exception("Échec du contrôle de %s", target.domain)
                continue

            if result.is_up:
                reachable += 1
                logger.info("%s OK %s (%s ms)", target.protocol, target.domain, result.latency_ms)
            else:
                logger.error("%s DOWN %s — %s", target.protocol, target.domain, result.detail)

            self._notify(target, result, outcome, incident_start, checked_at, local_time)

        self.db.prune(self.retain_days)
        logger.info("Cycle terminé : %s/%s joignables.", reachable, len(targets))

    def _notify(
        self,
        target: Target,
        result: ProbeResult,
        outcome: Outcome,
        incident_start: str | None,
        checked_at: str,
        local_time: str,
    ) -> None:
        if outcome is Outcome.STILL_DOWN and not self.db.alert_was_sent(target.key):
            outcome = Outcome.ALERT
        if outcome is Outcome.ALERT:
            started = local_time
            if incident_start:
                started = datetime.fromisoformat(incident_start).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            message = (
                f"{target.label} ({target.protocol} {target.domain}) est inaccessible "
                f"depuis le {started}.\n{result.detail}"
            )
            event_type = "alert"
        elif outcome is Outcome.RECOVERY:
            seconds = _duration_seconds(incident_start, checked_at)
            message = (
                f"{target.label} ({target.protocol} {target.domain}) est de nouveau accessible "
                f"le {local_time}.\nDurée de l'incident : {format_duration(seconds)}."
            )
            event_type = "recovery"
        else:
            return

        try:
            delivered = bool(
                self.mailer(
                    from_email=self.from_email,
                    password=self.password,
                    to_email=target.to_email,
                    domain=target.domain,
                    message=message,
                    current_time=local_time,
                    event_type=event_type,
                    check_type=target.protocol,
                    libelle=target.label,
                )
            )
        except Exception:
            logger.exception("Échec de notification pour %s", target.domain)
            return
        if delivered and event_type == "alert":
            self.db.mark_alert_sent(target.key)


def _duration_seconds(started_at: str | None, ended_at: str) -> float:
    if not started_at:
        return 0
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
    return max(0.0, (ended - started).total_seconds())
