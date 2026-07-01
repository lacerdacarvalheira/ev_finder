"""
EV Finder — Watchlist de odds alvo.
Registra pares (seleção + odd alvo) para alertar quando encontrados numa busca.
"""
import json
import os
from datetime import datetime

_DIR            = os.path.dirname(os.path.abspath(__file__))
_WATCHLIST_FILE = os.path.join(_DIR, "watchlist.json")


def load_watchlist() -> list[dict]:
    if not os.path.exists(_WATCHLIST_FILE):
        return []
    try:
        with open(_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def add_watch(jogo: str, mercado: str, selecao: str, odd_alvo: float) -> None:
    items  = load_watchlist()
    new_id = max((i.get("id", 0) for i in items), default=0) + 1
    items.append({
        "id":        new_id,
        "jogo":      jogo,
        "mercado":   mercado,
        "selecao":   selecao,
        "odd_alvo":  round(float(odd_alvo), 3),
        "criado":    datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    _save(items)


def remove_watch(watch_id: int) -> None:
    items = [i for i in load_watchlist() if i.get("id") != watch_id]
    _save(items)


def check_hits(opportunities: list[dict]) -> list[dict]:
    """
    Retorna lista de watches que foram atingidos pelas oportunidades atuais.
    Match: selecao (case-insensitive substring) e Odd Casa >= odd_alvo * 0.98.
    """
    hits = []
    for item in load_watchlist():
        sel_lower = item["selecao"].lower()
        for opp in opportunities:
            opp_sel = opp.get("Seleção", "").lower()
            opp_jog = opp.get("Jogo", "").lower()
            if (sel_lower in opp_sel or sel_lower in opp_jog) and \
                    opp.get("Odd Casa", 0) >= item["odd_alvo"] * 0.98:
                hits.append({**item, "opp": opp})
                break
    return hits


def _save(items: list[dict]) -> None:
    with open(_WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
