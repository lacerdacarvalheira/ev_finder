"""
EV Finder — Módulo de Arbitragem (Surebet)
Encontra oportunidades de lucro garantido comparando as melhores odds
de cada outcome entre todas as casas disponíveis.
"""
from collections import defaultdict
from utils import bookie_display, format_brt

# Exchanges usam lay odds (você é a casa) — não são back odds e criam arbs falsas.
# Pinnacle é o livro sharp de referência — incluí-la como lado de arb arrisca limitação da conta.
_EXCLUDE_FROM_ARB = {"betfair_ex_eu", "matchbook", "pinnacle"}

# Pares de mercados estatisticamente correlacionados no mesmo jogo.
# Se o usuário apostar em DUAS arbs do mesmo jogo em mercados deste conjunto, os
# outcomes são correlacionados — o lucro "garantido" pode deixar de existir.
_CORRELATED_PAIRS: frozenset = frozenset({
    frozenset({"totals",       "btts"}),
    frozenset({"totals",       "spreads"}),
    frozenset({"totals",       "team_totals"}),
    frozenset({"totals",       "alternate_totals"}),
    frozenset({"totals",       "totals_1st_half"}),
    frozenset({"h2h",          "doubleChance"}),
    frozenset({"h2h",          "draw_no_bet"}),
    frozenset({"btts",         "draw_no_bet"}),
    frozenset({"alternate_totals", "alternate_spreads"}),
})

_MARKET_LABELS = {
    "h2h":             "Resultado Final (1X2)",
    "spreads":         "Handicap Asiático",
    "alternate_spreads": "Alt. Handicap Asiático",
    "totals":          "Total de Gols",
    "alternate_totals": "Alt. Total de Gols",
    "btts":            "Ambas Marcam (Sim/Não)",
    "doubleChance":    "Dupla Chance",
    "draw_no_bet":     "Empate Anula (DNB)",
    "h2h_1st_half":    "Resultado 1° Tempo",
    "totals_1st_half": "Total Gols 1° Tempo",
    "team_totals":     "Gols do Time",
}


def _fmt_time(iso_str: str) -> str:
    return format_brt(iso_str)


def _bk(key: str, title: str) -> str:
    return bookie_display(key, title)


def _market_label(mkey: str, point) -> str:
    base = _MARKET_LABELS.get(mkey, mkey)
    if point is None:
        return base
    if "Total" in base or "Gols" in base:
        return f"{base} (O/U {point})"
    if "Handicap" in base:
        sign = "+" if point > 0 else ""
        return f"{base} ({sign}{point})"
    return f"{base} ({point})"


def _find_best_per_outcome(raw_outcomes: list[dict]) -> dict[str, dict]:
    """Retorna {name: {price, bookmaker}} com a melhor odd por outcome."""
    best: dict[str, dict] = {}
    for o in raw_outcomes:
        name = o["name"]
        if name not in best or o["price"] > best[name]["price"]:
            best[name] = {"price": o["price"], "bookmaker": o["bookmaker"]}
    return best


def _calc_arb(best: dict[str, dict]) -> dict | None:
    """
    Calcula se há arbitragem dado {name: {price, bookmaker}}.
    Retorna dict com lucro_pct e stakes, ou None se não há arb.
    """
    if len(best) < 2:
        return None

    names   = list(best.keys())
    sum_inv = sum(1.0 / best[n]["price"] for n in names)

    if sum_inv >= 1.0:
        return None

    profit_pct = (1.0 / sum_inv - 1.0) * 100

    outcomes = []
    for name in names:
        o = best[name]
        stake_pct = (1.0 / o["price"]) / sum_inv * 100
        outcomes.append({
            "nome":      name,
            "odds":      round(o["price"], 3),
            "casa":      o["bookmaker"],
            "stake_pct": round(stake_pct, 2),
        })

    return {
        "lucro_pct": round(profit_pct, 3),
        "sum_inv":   round(sum_inv, 6),
        "outcomes":  outcomes,
    }


def find_arbs(events: list[dict], min_profit: float = 0.0) -> list[dict]:
    """
    Varre todos os eventos e mercados buscando oportunidades de arbitragem.
    Retorna lista ordenada por lucro_pct (maior primeiro).
    """
    results = []

    for event in events:
        home         = event.get("home_team", "?")
        away         = event.get("away_team", "?")
        game_label   = f"{home} vs {away}"
        commence_raw = event.get("commence_time", "")
        horario      = _fmt_time(commence_raw)
        liga         = event.get("sport_title", "")
        bookmakers   = event.get("bookmakers", [])

        # Agrupa todos os outcomes por (market_key, point) entre todas as casas
        market_pool: dict = defaultdict(list)
        for bk in bookmakers:
            if bk["key"] in _EXCLUDE_FROM_ARB:
                continue
            bk_name = _bk(bk["key"], bk.get("title", bk["key"]))
            for mkt in bk.get("markets", []):
                mkey = mkt["key"]
                for o in mkt.get("outcomes", []):
                    point = o.get("point")
                    market_pool[(mkey, point)].append({
                        "name":      o["name"],
                        "price":     o["price"],
                        "bookmaker": bk_name,
                    })

        for (mkey, point), raw in market_pool.items():
            best = _find_best_per_outcome(raw)
            arb  = _calc_arb(best)
            if arb is None or arb["lucro_pct"] < min_profit:
                continue

            results.append({
                "Jogo":             game_label,
                "Liga":             liga,
                "Horário (BRT)":    horario,
                "Mercado":          _market_label(mkey, point),
                "Lucro (%)":        arb["lucro_pct"],
                "Outcomes":         arb["outcomes"],
                "commence_time_raw": commence_raw,
                "_sum_inv":         arb["sum_inv"],
                "_mkey":            mkey,
                "correlated_warning": None,
            })

    # Detecta arbs correlacionadas dentro do mesmo jogo
    from collections import defaultdict as _dd
    by_game: dict = _dd(list)
    for r in results:
        by_game[r["Jogo"]].append(r)

    for game_arbs in by_game.values():
        if len(game_arbs) < 2:
            continue
        mkeys = [a["_mkey"] for a in game_arbs]
        for i, a1 in enumerate(game_arbs):
            for a2 in game_arbs[i + 1:]:
                if frozenset({a1["_mkey"], a2["_mkey"]}) in _CORRELATED_PAIRS:
                    msg = (
                        f"Mercados correlacionados com **{a2['Mercado']}** "
                        f"neste mesmo jogo. Apostar em ambos não garante lucro duplo — "
                        f"os resultados influenciam-se mutuamente."
                    )
                    a1["correlated_warning"] = msg
                    a2["correlated_warning"] = (
                        f"Mercados correlacionados com **{a1['Mercado']}** "
                        f"neste mesmo jogo. Apostar em ambos não garante lucro duplo — "
                        f"os resultados influenciam-se mutuamente."
                    )

    results.sort(key=lambda x: x["Lucro (%)"], reverse=True)
    return results


def stakes_for_bankroll(arb: dict, total_stake: float) -> list[dict]:
    """Calcula stakes em R$ dado o total a investir."""
    return [
        {
            **o,
            "stake_r": round(total_stake * o["stake_pct"] / 100, 2),
            "retorno_r": round(total_stake * o["stake_pct"] / 100 * o["odds"], 2),
        }
        for o in arb["Outcomes"]
    ]
