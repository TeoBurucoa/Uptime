from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator

from models import Target

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    target_key TEXT PRIMARY KEY,
    protocol TEXT NOT NULL,
    domain TEXT NOT NULL,
    label TEXT NOT NULL,
    to_email TEXT NOT NULL,
    position INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_key TEXT NOT NULL REFERENCES targets(target_key),
    checked_at TEXT NOT NULL,
    is_up INTEGER NOT NULL,
    status_code INTEGER,
    latency_ms INTEGER,
    detail TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checks_target_time
    ON checks (target_key, checked_at);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_key TEXT NOT NULL REFERENCES targets(target_key),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    detail TEXT NOT NULL,
    alert_sent INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_incident
    ON incidents (target_key) WHERE ended_at IS NULL;
"""


class Outcome(str, Enum):
    OK = "ok"
    ALERT = "alert"
    STILL_DOWN = "still_down"
    RECOVERY = "recovery"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA)
            _ensure_alert_sent(conn)
            conn.commit()
            conn.execute("PRAGMA journal_mode = WAL")
        finally:
            conn.close()

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def replace_active_targets(self, targets: list[Target]) -> None:
        with self.session() as conn:
            conn.execute("UPDATE targets SET active = 0")
            for position, target in enumerate(targets):
                conn.execute(
                    """
                    INSERT INTO targets (
                        target_key, protocol, domain, label, to_email, position, active
                    ) VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(target_key) DO UPDATE SET
                        protocol = excluded.protocol,
                        domain = excluded.domain,
                        label = excluded.label,
                        to_email = excluded.to_email,
                        position = excluded.position,
                        active = 1
                    """,
                    (
                        target.key,
                        target.protocol,
                        target.domain,
                        target.label,
                        target.to_email,
                        position,
                    ),
                )

    def record(
        self,
        target: Target,
        *,
        is_up: bool,
        status_code: int | None,
        latency_ms: int | None,
        detail: str,
        checked_at: str,
    ) -> tuple[Outcome, str | None]:
        """Enregistre une mesure et ouvre ou ferme l'incident correspondant."""
        short_detail = " ".join(detail.split())[:300]
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO checks (
                    target_key, checked_at, is_up, status_code, latency_ms, detail
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    target.key,
                    checked_at,
                    1 if is_up else 0,
                    status_code,
                    latency_ms,
                    short_detail,
                ),
            )
            incident = conn.execute(
                """
                SELECT id, started_at FROM incidents
                WHERE target_key = ? AND ended_at IS NULL
                """,
                (target.key,),
            ).fetchone()

            if is_up and incident:
                conn.execute(
                    "UPDATE incidents SET ended_at = ? WHERE id = ?",
                    (checked_at, incident["id"]),
                )
                return Outcome.RECOVERY, incident["started_at"]
            if is_up:
                return Outcome.OK, None
            if incident:
                return Outcome.STILL_DOWN, incident["started_at"]

            try:
                conn.execute(
                    """
                    INSERT INTO incidents (target_key, started_at, detail)
                    VALUES (?, ?, ?)
                    """,
                    (target.key, checked_at, short_detail),
                )
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    """
                    SELECT started_at FROM incidents
                    WHERE target_key = ? AND ended_at IS NULL
                    """,
                    (target.key,),
                ).fetchone()
                started = existing["started_at"] if existing else checked_at
                return Outcome.STILL_DOWN, started
            return Outcome.ALERT, checked_at

    def alert_was_sent(self, target_key: str) -> bool:
        with self.session() as conn:
            row = conn.execute(
                """
                SELECT alert_sent FROM incidents
                WHERE target_key = ? AND ended_at IS NULL
                """,
                (target_key,),
            ).fetchone()
        return bool(row and row["alert_sent"])

    def mark_alert_sent(self, target_key: str) -> None:
        with self.session() as conn:
            conn.execute(
                """
                UPDATE incidents SET alert_sent = 1
                WHERE target_key = ? AND ended_at IS NULL
                """,
                (target_key,),
            )

    def prune(self, retain_days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).replace(microsecond=0)
        cutoff_text = _iso(cutoff)
        with self.session() as conn:
            conn.execute("DELETE FROM checks WHERE checked_at < ?", (cutoff_text,))
            conn.execute(
                "DELETE FROM incidents WHERE ended_at IS NOT NULL AND ended_at < ?",
                (cutoff_text,),
            )

    def snapshot(self, frequency_seconds: int, retain_days: int, timeline_limit: int = 60) -> dict:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        since = _iso(now - timedelta(hours=24))
        with self.session() as conn:
            targets = conn.execute(
                """
                SELECT * FROM targets
                WHERE active = 1
                ORDER BY position, target_key
                """
            ).fetchall()
            payload = []
            for target in targets:
                key = target["target_key"]
                recent = conn.execute(
                    """
                    SELECT checked_at, is_up, latency_ms, detail
                    FROM checks
                    WHERE target_key = ?
                    ORDER BY checked_at DESC, id DESC
                    LIMIT ?
                    """,
                    (key, timeline_limit),
                ).fetchall()
                recent = list(reversed(recent))
                uptime_24h, samples_24h = _ratio(conn, key, since)
                uptime_all, samples_all = _ratio(conn, key, None)
                incident = conn.execute(
                    """
                    SELECT started_at, detail FROM incidents
                    WHERE target_key = ? AND ended_at IS NULL
                    """,
                    (key,),
                ).fetchone()
                last = recent[-1] if recent else None
                payload.append(
                    {
                        "protocol": target["protocol"],
                        "domain": target["domain"],
                        "label": target["label"],
                        "to_email": target["to_email"],
                        "is_up": None if last is None else bool(last["is_up"]),
                        "last_checked_at": None if last is None else last["checked_at"],
                        "latency_ms": None if last is None else last["latency_ms"],
                        "detail": None if last is None else last["detail"],
                        "uptime_24h": uptime_24h,
                        "uptime_all": uptime_all,
                        "samples_24h": samples_24h,
                        "samples_all": samples_all,
                        "incident_started_at": None if incident is None else incident["started_at"],
                        "timeline": [
                            {
                                "checked_at": row["checked_at"],
                                "up": bool(row["is_up"]),
                                "latency_ms": row["latency_ms"],
                                "detail": row["detail"],
                            }
                            for row in recent
                        ],
                    }
                )
        return {
            "generated_at": _iso(now),
            "frequency_seconds": frequency_seconds,
            "retain_days": retain_days,
            "targets": payload,
        }


def _ratio(conn: sqlite3.Connection, key: str, since: str | None) -> tuple[float | None, int]:
    if since is None:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(is_up), 0) AS up
            FROM checks WHERE target_key = ?
            """,
            (key,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(is_up), 0) AS up
            FROM checks WHERE target_key = ? AND checked_at >= ?
            """,
            (key, since),
        ).fetchone()
    count = int(row["n"])
    if count == 0:
        return None, 0
    return float(row["up"]) / count, count


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_alert_sent(conn: sqlite3.Connection) -> None:
    """Ajoute le suivi d'envoi sur une base créée avant cette colonne."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(incidents)")}
    if "alert_sent" not in columns:
        conn.execute(
            "ALTER TABLE incidents ADD COLUMN alert_sent INTEGER NOT NULL DEFAULT 0"
        )
