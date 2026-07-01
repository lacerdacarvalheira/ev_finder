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
    # ── Referência ───────────────────────────────────────────────────────────
    "pinnacle":         "Pinnacle",
    # ── Disponíveis no tier atual da API ────────────────────────────────────
    "betfair_ex_eu":    "Betfair Exchange",
    "williamhill":      "William Hill",
    "betclic_fr":       "Betclic",
    "sport888":         "888sport",
    "betsson":          "Betsson",
    "marathonbet":      "Marathonbet",
    "nordicbet":        "NordicBet",
    "leovegas_se":      "LeoVegas",
    "matchbook":        "Matchbook",
    "unibet_fr":        "Unibet (FR)",
    "unibet_nl":        "Unibet (NL)",
    "unibet_se":        "Unibet (SE)",
    "winamax_fr":       "Winamax (FR)",
    "winamax_de":       "Winamax (DE)",
    "tipico_de":        "Tipico",
    "codere_it":        "Codere",
    "onexbet":          "1xBet",
    "pmu_fr":           "PMU (FR)",
    "betanysports":     "BetAnything",
    "betonlineag":      "BetOnline.ag",
    "mybookieag":       "MyBookie.ag",
    "gtbets":           "GTbets",
    "everygame":        "Everygame",
    # ── Casas fora do tier atual (mantidas como opções) ──────────────────────
    "bet365":           "Bet365",
    "betano":           "Betano",
    "superbet":         "Superbet",
    "unibet_eu":        "Unibet",
    "bwin":             "bwin",
    "betway":           "Betway",
    "draftkings":       "DraftKings",
    "fanduel":          "FanDuel",
    "1xbet":            "1xBet (alt)",
    "888sport":         "888sport (alt)",
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
