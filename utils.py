"""
EV Finder — Utilitários compartilhados.
Centraliza constantes e helpers usados em múltiplos módulos.
"""
import os
from datetime import datetime, timezone, timedelta
from loguru import logger

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ev_finder.log")
logger.add(_LOG_FILE, rotation="1 week", retention="4 weeks", level="WARNING")

BRT = timezone(timedelta(hours=-3))

BOOKIE_NAMES: dict[str, str] = {
    "pinnacle":         "Pinnacle",
    "bet365":           "Bet365",
    "betano":           "Betano",
    "superbet":         "Superbet",
    "betfair_ex_eu":    "Betfair Exchange",
    "unibet_eu":        "Unibet",
    "williamhill":      "William Hill",
    "bwin":             "bwin",
    "1xbet":            "1xBet",
    "marathonbet":      "Marathonbet",
    "betway":           "Betway",
    "nordicbet":        "NordicBet",
    "betsson":          "Betsson",
    "888sport":         "888sport",
    "draftkings":       "DraftKings",
    "fanduel":          "FanDuel",
}


def bookie_display(key: str, fallback: str = "") -> str:
    return BOOKIE_NAMES.get(key, fallback or key)


def format_brt(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(BRT).strftime("%d/%m %H:%M")
    except Exception:
        return iso_str


def hours_until(iso_str: str) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        from datetime import timezone as _tz
        return (dt - datetime.now(_tz.utc)).total_seconds() / 3600
    except Exception:
        return None


def urgency_badge(hours: float | None) -> str:
    if hours is None: return "—"
    if hours < 0:     return "🔴 Ao vivo"
    if hours < 1:     return f"🔴 {int(hours * 60)}min"
    if hours < 3:     return f"🟠 {hours:.1f}h"
    if hours < 12:    return f"🟡 {hours:.0f}h"
    if hours < 48:    return f"⬜ {hours:.0f}h"
    return f"⬜ {hours / 24:.0f}d"


def remove_vig(prices: list[float]) -> list[float]:
    if len(prices) < 2:
        return prices
    safe  = [max(p, 1.001) for p in prices]
    raw   = [1.0 / p for p in safe]
    total = sum(raw)
    if total <= 0:
        return [1.0 / len(prices)] * len(prices)
    return [p / total for p in raw]
