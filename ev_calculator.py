"""
EV Finder — Cálculo de Valor Esperado (Expected Value)
Ferramenta pessoal e educacional — não para uso comercial.

Mercados suportados:
  h2h, totals (todas as linhas), spreads (handicap asiático),
  btts, doubleChance, draw_no_bet, h2h_1st_half, totals_1st_half,
  team_totals, alternate_totals, alternate_spreads
"""
from collections import defaultdict
from utils import BRT, bookie_display, format_brt, remove_vig

_MAX_ODD_RATIO = 2.0   # Odd > 2× a odd justa = provável erro de dados


def _format_time(iso_str: str) -> str:
    return format_brt(iso_str)


def _bookie_display(key: str, fallback: str) -> str:
    return bookie_display(key, fallback)


def _make_row(game, horario, liga, mercado, selecao,
              odd_casa, true_prob, bookie, ev, commence_time_raw="", event_id=""):
    kelly_bruto = ev / (odd_casa - 1) if odd_casa > 1.001 else 0.0
    return {
        "EV (%)":               round(ev * 100, 2),
        "Prob. Real (%)":       round(true_prob * 100, 1),
        "Kelly bruto (%)":      round(max(0.0, kelly_bruto) * 100, 2),
        "Casa":                 bookie,
        "Jogo":                 game,
        "Horário (BRT)":        horario,
        "Liga":                 liga,
        "Mercado":              mercado,
        "Seleção":              selecao,
        "Odd Casa":             round(odd_casa, 3),
        "Odd Pinnacle (fair)":  round(1.0 / true_prob, 3),
        "commence_time_raw":    commence_time_raw,
        "event_id":             event_id,
    }


def _safe_append(rows, meta, mercado, selecao, price, prob, bookie, ev):
    """Adiciona linha ao resultado com sanity check de ratio."""
    if price > (1.0 / prob) * _MAX_ODD_RATIO:
        return
    if ev >= 0:
        rows.append(_make_row(
            meta["jogo"], meta["hora"], meta["liga"],
            mercado, selecao, price, prob, bookie, ev,
            meta.get("commence_time_raw", ""),
            meta.get("event_id", ""),
        ))


# ─── Processadores ───────────────────────────────────────────────────────────

def _process_h2h(pin, bk, meta, bookie, min_ev,
                 market_label="Resultado Final (1X2)"):
    pin_map = {o["name"]: o["price"] for o in pin}
    if len(pin_map) < 2:
        return []
    fair = dict(zip(pin_map.keys(), remove_vig(list(pin_map.values()))))
    rows = []
    for o in bk:
        name, price = o["name"], o["price"]
        prob = fair.get(name)
        if prob is None:
            continue
        ev = (prob * price) - 1
        if ev >= min_ev:
            _safe_append(rows, meta, market_label, name, price, prob, bookie, ev)
    return rows


def _process_totals(pin, bk, meta, bookie, min_ev,
                    market_prefix="Total de Gols"):
    """
    Processa TODAS as linhas de gols disponíveis (1.5, 2.5, 3.5, 4.5…).
    Anteriormente só processava a linha 2.5.
    """
    pin_by_line: dict = defaultdict(list)
    for o in pin:
        if o.get("point") is not None:
            pin_by_line[o["point"]].append(o)

    bk_by_line: dict = defaultdict(list)
    for o in bk:
        if o.get("point") is not None:
            bk_by_line[o["point"]].append(o)

    rows = []
    for point, pin_outcomes in pin_by_line.items():
        if len(pin_outcomes) < 2:
            continue
        bk_outcomes = bk_by_line.get(point, [])
        if not bk_outcomes:
            continue

        pin_map = {o["name"]: o["price"] for o in pin_outcomes}
        fair    = dict(zip(pin_map.keys(), remove_vig(list(pin_map.values()))))

        for o in bk_outcomes:
            name, price = o["name"], o["price"]
            prob = fair.get(name)
            if prob is None:
                continue
            ev = (prob * price) - 1
            if ev >= min_ev:
                label = f"{name} {point} gols"
                _safe_append(rows, meta,
                             f"{market_prefix} (O/U {point})",
                             label, price, prob, bookie, ev)
    return rows


def _process_spreads(pin, bk, meta, bookie, min_ev,
                     market_label="Handicap Asiático"):
    """
    Handicap asiático — emparelha linhas pelo valor do ponto.
    Ex: Home -0.5 @ 1.85 vs Away +0.5 @ 2.05 (Pinnacle)
        Home -0.5 @ 1.96 (Bookmaker) → EV calculado
    """
    pin_by_pt: dict = defaultdict(dict)
    for o in pin:
        pt = o.get("point")
        if pt is not None:
            pin_by_pt[pt][o["name"]] = o["price"]

    bk_by_pt: dict = defaultdict(dict)
    for o in bk:
        pt = o.get("point")
        if pt is not None:
            bk_by_pt[pt][o["name"]] = o["price"]

    rows = []
    for point, pin_pair in pin_by_pt.items():
        if len(pin_pair) < 2:
            continue
        bk_pair = bk_by_pt.get(point)
        if not bk_pair:
            continue

        names = list(pin_pair.keys())
        fair  = dict(zip(names, remove_vig([pin_pair[n] for n in names])))

        for name, price in bk_pair.items():
            prob = fair.get(name)
            if prob is None:
                continue
            ev = (prob * price) - 1
            if ev >= min_ev:
                sign  = "+" if point > 0 else ""
                label = f"{name} {sign}{point}"
                _safe_append(rows, meta, market_label, label, price, prob, bookie, ev)
    return rows


def _process_twoway(pin, bk, meta, bookie, min_ev, market_label):
    if len(pin) < 2:
        return []
    pin_map = {o["name"]: o["price"] for o in pin}
    fair    = dict(zip(pin_map.keys(), remove_vig(list(pin_map.values()))))
    rows = []
    for o in bk:
        name, price = o["name"], o["price"]
        prob = fair.get(name)
        if prob is None:
            continue
        ev = (prob * price) - 1
        if ev >= min_ev:
            _safe_append(rows, meta, market_label, name, price, prob, bookie, ev)
    return rows


# ─── Mapa de mercados ─────────────────────────────────────────────────────────

_MARKET_DISPATCH = {
    "h2h":                    lambda p, b, m, bk, ev: _process_h2h(p, b, m, bk, ev),
    "totals":                 lambda p, b, m, bk, ev: _process_totals(p, b, m, bk, ev),
    "alternate_totals":       lambda p, b, m, bk, ev: _process_totals(p, b, m, bk, ev, "Alt. Total de Gols"),
    "spreads":                lambda p, b, m, bk, ev: _process_spreads(p, b, m, bk, ev),
    "alternate_spreads":      lambda p, b, m, bk, ev: _process_spreads(p, b, m, bk, ev, "Alt. Handicap Asiático"),
    "btts":                   lambda p, b, m, bk, ev: _process_twoway(p, b, m, bk, ev, "Ambas Marcam"),
    "doubleChance":           lambda p, b, m, bk, ev: _process_twoway(p, b, m, bk, ev, "Dupla Chance"),
    "draw_no_bet":            lambda p, b, m, bk, ev: _process_twoway(p, b, m, bk, ev, "Empate Anula (DNB)"),
    "h2h_1st_half":           lambda p, b, m, bk, ev: _process_h2h(p, b, m, bk, ev, "Resultado 1° Tempo"),
    "totals_1st_half":        lambda p, b, m, bk, ev: _process_totals(p, b, m, bk, ev, "Total Gols 1° Tempo"),
    "team_totals":            lambda p, b, m, bk, ev: _process_totals(p, b, m, bk, ev, "Gols do Time"),
    "h2h_lay":                lambda p, b, m, bk, ev: _process_h2h(p, b, m, bk, ev, "Lay (Exchange)"),
}


# ─── Função principal ─────────────────────────────────────────────────────────

def find_opportunities(events: list[dict], min_ev: float = 0.05) -> list[dict]:
    all_rows: list[dict] = []

    for event in events:
        bookmakers = event.get("bookmakers", [])
        pinnacle   = next((b for b in bookmakers if b["key"] == "pinnacle"), None)
        if pinnacle is None:
            continue

        pin_markets = {m["key"]: m["outcomes"] for m in pinnacle.get("markets", [])}

        meta = {
            "jogo":              f"{event.get('home_team','?')} vs {event.get('away_team','?')}",
            "hora":              _format_time(event.get("commence_time", "")),
            "liga":              event.get("sport_title", ""),
            "commence_time_raw": event.get("commence_time", ""),
            "event_id":          event.get("id", ""),
        }

        for bookie in bookmakers:
            if bookie["key"] == "pinnacle":
                continue
            bookie_name = _bookie_display(bookie["key"],
                                          bookie.get("title", bookie["key"]))

            for market in bookie.get("markets", []):
                mkey         = market["key"]
                pin_outcomes = pin_markets.get(mkey)
                handler      = _MARKET_DISPATCH.get(mkey)

                if pin_outcomes is None or handler is None:
                    continue

                rows = handler(pin_outcomes, market["outcomes"], meta, bookie_name, min_ev)
                all_rows.extend(rows)

    all_rows.sort(key=lambda r: r["EV (%)"], reverse=True)
    return all_rows
