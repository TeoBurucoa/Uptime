from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    """Une ligne du fichier de domaines."""

    protocol: str
    domain: str
    to_email: str
    label: str

    @property
    def key(self) -> str:
        return f"{self.protocol}|{self.domain}"
