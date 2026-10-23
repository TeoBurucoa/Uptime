from __future__ import annotations


def format_duration(seconds: float) -> str:
    """Convertit une durée en texte court, par exemple « 2 jours 4 heures »."""
    remaining = max(0, int(seconds))
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, secs = divmod(remaining, 60)

    parts: list[str] = []
    if days:
        parts.append(_unit(days, "jour", "jours"))
    if hours:
        parts.append(_unit(hours, "heure", "heures"))
    if minutes:
        parts.append(_unit(minutes, "minute", "minutes"))
    if secs or not parts:
        parts.append(_unit(secs, "seconde", "secondes"))
    return " ".join(parts)


def _unit(value: int, singular: str, plural: str) -> str:
    word = singular if value == 1 else plural
    return f"{value} {word}"
