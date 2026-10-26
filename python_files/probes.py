from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass

import requests

from txt_to_list import get_status_info

USER_AGENT = "UptimeMonitor/1.0"


@dataclass(frozen=True)
class ProbeResult:
    is_up: bool
    status_code: int | None
    latency_ms: int | None
    detail: str


def probe_target(
    protocol: str,
    domain: str,
    https_errors: str,
    ping_errors: str,
    timeout: float = 10,
) -> ProbeResult:
    """Teste une cible une seule fois, quel que soit son état précédent."""
    kind = protocol.upper()
    if kind in {"HTTP", "HTTPS"}:
        return _probe_http(kind, domain, https_errors, timeout)
    if kind == "PING":
        return _probe_ping(domain, ping_errors, timeout)
    return ProbeResult(False, None, None, f"Protocole inconnu : {protocol}")


def _probe_http(protocol: str, domain: str, error_file: str, timeout: float) -> ProbeResult:
    url = f"{protocol.lower()}://{domain}"
    started = time.perf_counter()
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as exc:
        latency = _elapsed_ms(started)
        reason = str(exc).strip().splitlines()
        short = (reason[0] if reason else exc.__class__.__name__)[:240]
        return ProbeResult(False, None, latency, f"Connexion impossible : {short}")

    latency = _elapsed_ms(started)
    code = response.status_code
    if 200 <= code < 400:
        return ProbeResult(True, code, latency, f"HTTP {code}")
    return ProbeResult(False, code, latency, get_status_info(error_file, code))


def _probe_ping(domain: str, error_file: str, timeout: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        output = subprocess.run(
            _ping_command(domain),
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(False, None, int(timeout * 1000), "Ping sans réponse (délai dépassé)")
    except OSError as exc:
        return ProbeResult(False, None, None, f"Ping impossible : {exc}")

    latency = _elapsed_ms(started)
    if output.returncode == 0:
        return ProbeResult(True, 0, latency, "Ping OK")
    return ProbeResult(False, output.returncode, latency, get_status_info(error_file, output.returncode))


def _ping_command(domain: str) -> list[str]:
    if platform.system().lower() == "windows":
        return ["ping", "-n", "1", "-w", "5000", domain]
    return ["ping", "-c", "1", "-W", "5", domain]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
