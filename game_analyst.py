"""
EV Finder — Análise de jogos do dia.
Gera análise textual baseada em probabilidades da Pinnacle, melhores odds,
oportunidades EV+ e movimento de linha.
"""
from datetime import datetime
from utils import BRT as _BRT, bookie_display, format_brt


def is_today_brt(iso_str: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(_BRT).date() == datetime.now(_BRT).date()
    except Exception:
        return False


def get_today_events(all_events: list[dict]) -> list[dict]:
    return sorted(
        [e for e in all_events if is_today_brt(e.get("commence_time", ""))],
        key=lambda e: e.get("commence_time", ""),
    )


def _bookie_name(key: str, title: str) -> str:
    return bookie_display(key, title)


def analyze_game(event: dict, all_opportunities: list[dict],
                 line_history: dict) -> dict:
    """
    Retorna análise completa de um jogo.

    Returns dict:
        probs         — {outcome_name: {prob, fair_odd}}
        best_h2h      — {outcome_name: {price, bookmaker, ev}}
        best_totals   — {label: {price, bookmaker}}
        ev_opps       — lista de oportunidades EV+ deste jogo (qualquer mercado)
        analysis_lines — lista de strings de análise
        recommendation — "strong" | "value" | "watch" | "neutral"
        rec_text      — texto da recomendação final
        line_moves    — lista de strings de movimento de linha
        sharp_signal  — nome da seleção que recebeu dinheiro afiado (ou "")
    """
    from utils import remove_vig

    home = event.get("home_team", "?")
    away = event.get("away_team", "?")
    game_label = f"{home} vs {away}"
    bookmakers = event.get("bookmakers", [])

    # ── Pinnacle como referência ────────────────────────────────────────────
    pinnacle = next((b for b in bookmakers if b["key"] == "pinnacle"), None)
    pin_markets: dict = {}
    if pinnacle:
        pin_markets = {m["key"]: m["outcomes"] for m in pinnacle.get("markets", [])}

    # ── Probabilidades 1X2 (sem vig) ────────────────────────────────────────
    probs: dict = {}
    h2h_outcomes = pin_markets.get("h2h", [])
    if h2h_outcomes:
        names  = [o["name"] for o in h2h_outcomes]
        prices = [o["price"] for o in h2h_outcomes]
        fair_p = remove_vig(prices)
        for name, prob in zip(names, fair_p):
            probs[name] = {
                "prob":     round(prob * 100, 1),
                "fair_odd": round(1.0 / prob, 3),
            }

    # ── Melhores odds por resultado (1X2) ────────────────────────────────────
    best_h2h: dict = {}
    for bk in bookmakers:
        if bk["key"] == "pinnacle":
            continue
        bk_name = _bookie_name(bk["key"], bk.get("title", ""))
        for mkt in bk.get("markets", []):
            if mkt["key"] != "h2h":
                continue
            for o in mkt["outcomes"]:
                name, price = o["name"], o["price"]
                if name not in best_h2h or price > best_h2h[name]["price"]:
                    fair_odd = probs.get(name, {}).get("fair_odd")
                    prob_val = probs.get(name, {}).get("prob", 0) / 100
                    ev = round((prob_val * price - 1) * 100, 2) if prob_val else None
                    best_h2h[name] = {"price": price, "bookmaker": bk_name,
                                      "ev": ev, "fair_odd": fair_odd}

    # ── Melhores odds Over/Under 2.5 ─────────────────────────────────────────
    best_totals: dict = {}
    pin_totals = [o for o in pin_markets.get("totals", []) if o.get("point") == 2.5]
    if pin_totals:
        pin_tot_map = {o["name"]: o["price"] for o in pin_totals}
        if len(pin_tot_map) >= 2:
            fair_tot = dict(zip(
                pin_tot_map.keys(),
                remove_vig(list(pin_tot_map.values()))
            ))
            for bk in bookmakers:
                if bk["key"] == "pinnacle":
                    continue
                bk_name = _bookie_name(bk["key"], bk.get("title", ""))
                for mkt in bk.get("markets", []):
                    if mkt["key"] != "totals":
                        continue
                    for o in mkt["outcomes"]:
                        if o.get("point") != 2.5:
                            continue
                        name, price = o["name"], o["price"]
                        label = f"{name} 2.5"
                        prob_val = fair_tot.get(name, 0)
                        ev = round((prob_val * price - 1) * 100, 2) if prob_val else None
                        fair_odd = round(1 / prob_val, 3) if prob_val else None
                        if label not in best_totals or price > best_totals[label]["price"]:
                            best_totals[label] = {
                                "price": price, "bookmaker": bk_name,
                                "ev": ev, "fair_odd": fair_odd,
                                "prob": round(prob_val * 100, 1),
                            }

    # ── EV+ deste jogo ───────────────────────────────────────────────────────
    event_id = event.get("id", "")
    if event_id:
        ev_opps = [o for o in all_opportunities if o.get("event_id") == event_id]
    else:
        # fallback para string se o evento não tiver ID (dados legados)
        ev_opps = [o for o in all_opportunities if o.get("Jogo") == game_label]
    ev_h2h     = [o for o in ev_opps if "1X2"     in o.get("Mercado", "")]
    ev_spreads = [o for o in ev_opps if "Handicap" in o.get("Mercado", "")]
    ev_totals  = [o for o in ev_opps if "Total"   in o.get("Mercado", "")]
    ev_dnb     = [o for o in ev_opps if "DNB"     in o.get("Mercado", "") or "Anula" in o.get("Mercado", "")]
    ev_ht      = [o for o in ev_opps if "1°"      in o.get("Mercado", "") or "Tempo" in o.get("Mercado", "")]
    ev_other   = [o for o in ev_opps if o not in ev_h2h and o not in ev_spreads
                  and o not in ev_totals and o not in ev_dnb and o not in ev_ht]
    ev_all     = sorted(ev_opps, key=lambda x: x["EV (%)"], reverse=True)

    # ── Movimento de linha ────────────────────────────────────────────────────
    line_moves: list[str] = []
    sharp_signal = ""
    snapshots = line_history.get("snapshots", [])
    if len(snapshots) >= 2:
        first_pin = snapshots[0].get("odds", {}).get("pinnacle", {}).get("h2h", [])
        last_pin  = snapshots[-1].get("odds", {}).get("pinnacle", {}).get("h2h", [])
        if first_pin and last_pin:
            first_map = {o["name"]: o["price"] for o in first_pin}
            last_map  = {o["name"]: o["price"] for o in last_pin}
            for name, price_now in last_map.items():
                price_then = first_map.get(name)
                if not price_then or price_then <= 1:
                    continue
                # movimento em pontos de probabilidade (mais preciso que % de odd)
                prob_then = 1.0 / price_then
                prob_now  = 1.0 / price_now
                prob_move = prob_now - prob_then  # positivo = encurtou (favorito)
                if abs(prob_move) >= 0.03:
                    arrow = "↓" if price_now < price_then else "↑"
                    pct   = abs(price_now - price_then) / price_then * 100
                    line_moves.append(
                        f"{name}: {price_then:.2f} → {price_now:.2f} "
                        f"({arrow} {pct:.1f}% | {abs(prob_move)*100:.1f}pp)"
                    )
                    if prob_move >= 0.03:  # encurtou ≥3pp = dinheiro afiado entrou
                        sharp_signal = name

    # ── Texto de análise ─────────────────────────────────────────────────────
    lines: list[str] = []

    if probs:
        sorted_p = sorted(probs.items(), key=lambda x: x[1]["prob"], reverse=True)
        fav_name, fav_d = sorted_p[0]
        und_name, und_d = sorted_p[-1]
        gap = fav_d["prob"] - und_d["prob"]

        if gap < 5:
            lines.append(
                f"**Jogo extremamente equilibrado.** Pinnacle aponta {fav_d['prob']:.1f}% "
                f"para {fav_name} e {und_d['prob']:.1f}% para {und_name} — diferença de "
                f"apenas {gap:.1f}%. Alta variância: qualquer resultado é razoavelmente provável."
            )
        elif gap < 15:
            lines.append(
                f"**Favorito leve:** Pinnacle coloca {fav_name} na frente com {fav_d['prob']:.1f}% "
                f"(odd justa {fav_d['fair_odd']:.2f}) contra {und_d['prob']:.1f}% do {und_name}. "
                "Desequilíbrio moderado — o azarão ainda pode ter valor."
            )
        else:
            lines.append(
                f"**Favorito claro:** {fav_name} com {fav_d['prob']:.1f}% de probabilidade real "
                f"(odd justa {fav_d['fair_odd']:.2f}). {und_name} tem apenas {und_d['prob']:.1f}% — "
                "apostas no azarão são de alto risco e baixa frequência de acerto."
            )

        # Empate
        draw_d = probs.get("Draw", {})
        if draw_d:
            if draw_d["prob"] > 28:
                lines.append(
                    f"O empate tem **{draw_d['prob']:.1f}%** de chance real — acima da média "
                    "histórica para Copa do Mundo (~26%). Verifique se há EV disponível no empate."
                )
            elif draw_d["prob"] < 20:
                lines.append(
                    f"Empate improvável ({draw_d['prob']:.1f}%) — o mercado está apostando "
                    "em decisão entre os times."
                )

    # EV disponível
    if ev_all:
        best = ev_all[0]
        lines.append(
            f"**Melhor EV neste jogo:** {best['Seleção']} @ {best['Casa']} "
            f"odd **{best['Odd Casa']:.3f}** (justa {best['Odd Pinnacle (fair)']:.3f}) "
            f"→ **EV +{best['EV (%)']:.1f}%**."
        )
        if best["EV (%)"] > 10:
            lines.append(
                "⚠️ EV acima de 10% pode indicar erro temporário de precificação "
                "ou limitação de liquidez — se for genuíno, **aposte rápido**."
            )
        if len(ev_all) > 1:
            outros = [
                f"{o['Seleção']} @ {o['Casa']} (+{o['EV (%)']:.1f}%)"
                for o in ev_all[1:3]
            ]
            lines.append(f"Também com valor: {', '.join(outros)}.")
    else:
        lines.append(
            "Nenhuma oportunidade EV+ acima do mínimo configurado neste jogo. "
            "O mercado está razoavelmente eficiente — aguarde aproximação do jogo, "
            "pois as odds podem melhorar."
        )

    # O/U insights — todas as linhas disponíveis
    if ev_totals:
        best_tot = ev_totals[0]
        lines.append(
            f"**Gols ({best_tot['Mercado']}):** {best_tot['Seleção']} "
            f"@ {best_tot['Casa']} odd {best_tot['Odd Casa']:.2f} "
            f"(prob. {best_tot['Prob. Real (%)']:.0f}% → EV **+{best_tot['EV (%)']:.1f}%**)."
        )
        if len(ev_totals) > 1:
            outras_linhas = list({o["Mercado"] for o in ev_totals[1:]})[:3]
            lines.append(f"Outras linhas com valor: {', '.join(outras_linhas)}.")
    elif best_totals:
        over  = best_totals.get("Over 2.5", {})
        under = best_totals.get("Under 2.5", {})
        if over.get("ev", 0) > 0:
            lines.append(
                f"**Over 2.5:** {over['price']:.2f} @ {over['bookmaker']} "
                f"(prob. {over.get('prob', 0):.0f}% → EV **+{over['ev']:.1f}%**)."
            )
        elif under and under.get("ev", 0) > 0:
            lines.append(
                f"**Under 2.5:** {under['price']:.2f} @ {under['bookmaker']} "
                f"(prob. {under.get('prob', 0):.0f}% → EV **+{under['ev']:.1f}%**)."
            )

    # Handicap asiático
    if ev_spreads:
        best_sp = ev_spreads[0]
        lines.append(
            f"**Handicap Asiático:** {best_sp['Seleção']} @ {best_sp['Casa']} "
            f"odd {best_sp['Odd Casa']:.2f} → EV **+{best_sp['EV (%)']:.1f}%**. "
            "Handicap elimina o risco de empate e pode ter odds melhores que o 1X2."
        )

    # Empate Anula (DNB)
    if ev_dnb:
        best_dnb = ev_dnb[0]
        lines.append(
            f"**Empate Anula (DNB):** {best_dnb['Seleção']} @ {best_dnb['Casa']} "
            f"odd {best_dnb['Odd Casa']:.2f} → EV **+{best_dnb['EV (%)']:.1f}%**. "
            "DNB reduz o risco: empate devolve o dinheiro."
        )

    # 1° Tempo
    if ev_ht:
        best_ht = ev_ht[0]
        lines.append(
            f"**1° Tempo ({best_ht['Mercado']}):** {best_ht['Seleção']} "
            f"@ {best_ht['Casa']} odd {best_ht['Odd Casa']:.2f} → EV **+{best_ht['EV (%)']:.1f}%**."
        )

    # Movimento de linha
    if line_moves:
        lines.append(f"**Movimento de linha (Pinnacle):** {'; '.join(line_moves)}.")
        if sharp_signal:
            lines.append(
                f"A odd de {sharp_signal} caiu >3% — sinal de **dinheiro afiado** "
                "nesta seleção. Queda de linha Pinnacle é geralmente um indicador confiável "
                "de expectativa do mercado atuando."
            )

    # ── Recomendação ─────────────────────────────────────────────────────────
    recommendation = "neutral"
    rec_text = ""

    if ev_all and sharp_signal:
        best = ev_all[0]
        recommendation = "strong"
        rec_text = (
            f"🔥 **SINAL FORTE:** {best['Seleção']} @ {best['Casa']} "
            f"— EV +{best['EV (%)']:.1f}% com confirmação de movimento de linha "
            f"na mesma direção. Kelly: veja aba EV+."
        )
    elif ev_all and ev_all[0]["EV (%)"] >= 7:
        best = ev_all[0]
        recommendation = "value"
        rec_text = (
            f"💚 **VALOR CLARO:** {best['Seleção']} @ {best['Casa']} "
            f"— EV +{best['EV (%)']:.1f}%. Edge matemático sólido, sem linha confirmando mas "
            "os números estão a favor."
        )
    elif ev_all:
        best = ev_all[0]
        recommendation = "value_small"
        rec_text = (
            f"🟡 **PEQUENO VALOR:** {best['Seleção']} @ {best['Casa']} "
            f"— EV +{best['EV (%)']:.1f}%. Aposte conservadoramente (1/4 Kelly)."
        )
    elif sharp_signal:
        recommendation = "watch"
        rec_text = (
            f"👀 **MOVIMENTO DETECTADO:** Linha de {sharp_signal} caiu na Pinnacle. "
            "Fique de olho — pode aparecer valor nas outras casas em breve."
        )
    else:
        recommendation = "neutral"
        rec_text = "⚪ Mercado eficiente. Sem edge claro identificado — aguarde ou pule este jogo."

    return {
        "probs":          probs,
        "best_h2h":       best_h2h,
        "best_totals":    best_totals,
        "ev_opps":        ev_all,
        "ev_h2h":         ev_h2h,
        "ev_spreads":     ev_spreads,
        "ev_totals":      ev_totals,
        "ev_dnb":         ev_dnb,
        "ev_ht":          ev_ht,
        "ev_other":       ev_other,
        "analysis_lines": lines,
        "recommendation": recommendation,
        "rec_text":       rec_text,
        "line_moves":     line_moves,
        "sharp_signal":   sharp_signal,
    }


# ─── Recomendações de apostas ─────────────────────────────────────────────────

def recommend_bets(event: dict, analysis: dict) -> list[dict]:
    """
    Gera recomendações de apostas para um jogo com base em:
    - Probabilidades Pinnacle (sem vig)
    - Mercados de gols (totals) para inferir placar esperado
    - Linha afiada (sharp signal)
    - Odds disponíveis nos bookmakers
    - Padrões estatísticos de Copa do Mundo

    Cada recomendação retorna:
        mercado, selecao, best_odd, best_bookie, fair_odd,
        prob_est (%), confianca, tipo, motivo, ev_pct, combo_ok
    """
    from utils import remove_vig
    from collections import defaultdict

    home       = event.get("home_team", "?")
    away       = event.get("away_team", "?")
    bookmakers = event.get("bookmakers", [])
    probs      = analysis.get("probs", {})
    sharp      = analysis.get("sharp_signal", "")
    line_moves = analysis.get("line_moves", [])
    ev_opps    = analysis.get("ev_opps", [])

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _best_odd_for(market_key: str, outcome_name: str,
                      point=None) -> tuple[float, str]:
        """Retorna (melhor_odd, bookmaker) para um outcome específico."""
        best_p, best_bk = 0.0, "—"
        for bk in bookmakers:
            if bk["key"] == "pinnacle":
                continue
            for mkt in bk.get("markets", []):
                if mkt["key"] != market_key:
                    continue
                for o in mkt.get("outcomes", []):
                    if o["name"] != outcome_name:
                        continue
                    if point is not None and o.get("point") != point:
                        continue
                    if o["price"] > best_p:
                        best_p  = o["price"]
                        best_bk = _bookie_name(bk["key"], bk.get("title", ""))
        return best_p, best_bk

    def _rec(mercado, selecao, best_odd, best_bk, prob_est,
             confianca, tipo, motivo, combo_ok=True):
        fair_odd = round(1.0 / (prob_est / 100), 3) if prob_est > 0 else 0.0
        ev_pct   = round((prob_est / 100 * best_odd - 1) * 100, 2) if best_odd > 1 else None
        return {
            "mercado":    mercado,
            "selecao":    selecao,
            "best_odd":   round(best_odd, 3),
            "best_bookie": best_bk,
            "fair_odd":   fair_odd,
            "prob_est":   round(prob_est, 1),
            "confianca":  confianca,   # "alta" | "media" | "baixa"
            "tipo":       tipo,        # "segura" | "valor" | "sharp" | "combo"
            "motivo":     motivo,
            "ev_pct":     ev_pct,
            "combo_ok":   combo_ok,
        }

    recs: list[dict] = []

    # ── 1. Resultado mais provável ────────────────────────────────────────────
    if probs:
        sorted_p  = sorted(probs.items(), key=lambda x: x[1]["prob"], reverse=True)
        fav, fdata = sorted_p[0]
        fav_prob   = fdata["prob"]
        fav_fair   = fdata["fair_odd"]

        odd, bk = _best_odd_for("h2h", fav)
        if odd > 1:
            conf = "alta" if fav_prob >= 60 else ("media" if fav_prob >= 50 else "baixa")
            recs.append(_rec(
                "Resultado Final (1X2)", fav, odd, bk, fav_prob, conf, "segura",
                f"Pinnacle aponta {fav_prob:.0f}% — favorito mais provável. "
                f"Odd justa: {fav_fair:.2f}.",
                combo_ok=fav_prob >= 55,
            ))

        # Double Chance favorito + empate (cobertura maior)
        if len(sorted_p) == 3:
            draw_prob = probs.get("Draw", {}).get("prob", 0)
            dc_prob   = fav_prob + draw_prob
            dc_name   = f"1X" if fav == home else "X2"
            odd_dc, bk_dc = _best_odd_for("doubleChance", dc_name)
            if odd_dc > 1 and dc_prob >= 65:
                conf = "alta" if dc_prob >= 75 else "media"
                recs.append(_rec(
                    "Dupla Chance", dc_name, odd_dc, bk_dc, dc_prob, conf, "segura",
                    f"Cobre vitória de {fav} OU empate ({dc_prob:.0f}% de cobertura). "
                    "Boa opção quando o favorito não é dominante.",
                    combo_ok=dc_prob >= 70,
                ))

        # Draw No Bet (favorito — sem risco de empate)
        odd_dnb, bk_dnb = _best_odd_for("draw_no_bet", fav)
        if odd_dnb > 1 and fav_prob >= 52:
            draw_p = probs.get("Draw", {}).get("prob", 0) / 100
            # prob correta: vitória condicionada a universo sem empate
            dnb_prob = (fav_prob / 100 / (1 - draw_p)) * 100 if draw_p < 1 else fav_prob
            recs.append(_rec(
                "Empate Anula (DNB)", fav, odd_dnb, bk_dnb, round(dnb_prob, 1),
                "media", "segura",
                f"Aposta no {fav} com seguro: empate devolve o dinheiro. "
                "Menor odd que 1X2 mas muito menos risco.",
                combo_ok=False,
            ))

    # ── 2. Mercado de gols (Over/Under) ──────────────────────────────────────
    pinnacle = next((b for b in bookmakers if b["key"] == "pinnacle"), None)
    if pinnacle:
        pin_totals_map: dict = defaultdict(list)
        for mkt in pinnacle.get("markets", []):
            if mkt["key"] != "totals":
                continue
            for o in mkt.get("outcomes", []):
                if o.get("point") is not None:
                    pin_totals_map[o["point"]].append(o)

        # Estima gols esperados usando os mercados Pinnacle
        xg_data: list[tuple] = []
        for pt, outcomes in sorted(pin_totals_map.items()):
            if len(outcomes) < 2:
                continue
            names  = [o["name"] for o in outcomes]
            prices = [o["price"] for o in outcomes]
            fair_p = remove_vig(prices)
            over_p = next((p for n, p in zip(names, fair_p) if "Over" in n), None)
            if over_p:
                xg_data.append((pt, over_p))

        # Expected goals estimado: ponto onde Over prob ≈ 50%
        xg_est = None
        for i in range(len(xg_data) - 1):
            pt_low, p_low   = xg_data[i]
            pt_high, p_high = xg_data[i + 1]
            if p_low >= 0.5 >= p_high:
                # interpolação linear
                xg_est = pt_low + (pt_high - pt_low) * (p_low - 0.5) / (p_low - p_high)
                break
        if xg_est is None and xg_data:
            xg_est = xg_data[-1][0] if xg_data[-1][1] > 0.5 else xg_data[0][0]

        # Recomenda Over 1.5 se xg esperado for alto
        over15_data = next(((pt, outcomes) for pt, outcomes in pin_totals_map.items()
                            if pt == 1.5), None)
        if over15_data:
            pt15, outs15 = over15_data
            names15  = [o["name"] for o in outs15]
            prices15 = [o["price"] for o in outs15]
            fair15   = dict(zip(names15, remove_vig(prices15)))
            over15_p = fair15.get("Over", 0) * 100
            odd15, bk15 = _best_odd_for("totals", "Over", 1.5)
            if odd15 > 1 and over15_p >= 75:
                conf = "alta" if over15_p >= 85 else "media"
                xg_str = f" (gols esperados ~{xg_est:.1f})" if xg_est else ""
                recs.append(_rec(
                    "Total de Gols (O/U 1.5)", "Over 1.5", odd15, bk15, over15_p,
                    conf, "segura",
                    f"Pinnacle aponta {over15_p:.0f}% de chance de pelo menos 2 gols{xg_str}. "
                    "Over 1.5 é historicamente seguro em Copa do Mundo (~85% das partidas).",
                    combo_ok=True,
                ))

        # Recomenda Over 2.5 se xg > 2.7
        over25_data = next(((pt, outcomes) for pt, outcomes in pin_totals_map.items()
                            if pt == 2.5), None)
        if over25_data:
            pt25, outs25 = over25_data
            names25  = [o["name"] for o in outs25]
            prices25 = [o["price"] for o in outs25]
            fair25   = dict(zip(names25, remove_vig(prices25)))
            over25_p = fair25.get("Over", 0) * 100
            under25_p = fair25.get("Under", 0) * 100
            odd25, bk25 = _best_odd_for("totals", "Over", 2.5)
            odd_u25, bk_u25 = _best_odd_for("totals", "Under", 2.5)

            if odd25 > 1 and over25_p >= 55:
                recs.append(_rec(
                    "Total de Gols (O/U 2.5)", "Over 2.5", odd25, bk25, over25_p,
                    "media", "valor",
                    f"Mercado aponta {over25_p:.0f}% para +3 gols. "
                    + (f"Gols esperados ~{xg_est:.1f} — jogo aberto." if xg_est and xg_est > 2.5 else "Jogo equilibrado favorece mais gols."),
                    combo_ok=over25_p >= 60,
                ))
            elif odd_u25 > 1 and under25_p >= 60:
                recs.append(_rec(
                    "Total de Gols (O/U 2.5)", "Under 2.5", odd_u25, bk_u25, under25_p,
                    "media", "segura",
                    f"Mercado aponta {under25_p:.0f}% para menos de 3 gols. "
                    + (f"Gols esperados ~{xg_est:.1f} — jogo fechado." if xg_est and xg_est < 2.5 else "Favorito dominante tende a controlar o jogo."),
                    combo_ok=under25_p >= 65,
                ))

    # ── 3. Handicap asiático (quando há favorito claro) ──────────────────────
    if probs:
        sorted_p  = sorted(probs.items(), key=lambda x: x[1]["prob"], reverse=True)
        fav, fdata = sorted_p[0]
        fav_prob   = fdata["prob"]

        if fav_prob >= 58 and pinnacle:
            for mkt in pinnacle.get("markets", []):
                if mkt["key"] != "spreads":
                    continue
                # The Odds API: England -1.5 e Slovakia +1.5 são lados opostos
                # da mesma linha. Agrupa por abs(point) para parear corretamente.
                by_line: dict = defaultdict(dict)
                for o in mkt.get("outcomes", []):
                    pt = o.get("point")
                    if pt is not None:
                        by_line[abs(pt)][o["name"]] = {"price": o["price"], "point": pt}

                for line_key, entries in sorted(by_line.items()):
                    if line_key not in (0.5, 1.0, 1.5):
                        continue
                    if len(entries) < 2:
                        continue
                    fav_entry = entries.get(fav)
                    if not fav_entry or fav_entry["point"] >= 0:
                        continue  # favorito deve ter handicap negativo
                    names_p  = list(entries.keys())
                    prices_p = [entries[n]["price"] for n in names_p]
                    fair_sp  = dict(zip(names_p, remove_vig(prices_p)))
                    fav_fair_sp = fair_sp.get(fav, 0)
                    fav_pt   = fav_entry["point"]
                    odd_sp, bk_sp = _best_odd_for("spreads", fav, fav_pt)
                    if odd_sp > 1 and fav_fair_sp >= 0.50:
                        sign = f"{fav_pt:+g}"
                        recs.append(_rec(
                            "Handicap Asiático", f"{fav} {sign}", odd_sp, bk_sp,
                            fav_fair_sp * 100, "media", "valor",
                            f"Com {fav_prob:.0f}% de chance de vitória, {fav} {sign} "
                            f"elimina o risco de empate e ainda tem probabilidade razoável. "
                            "Boa relação risco/retorno.",
                            combo_ok=fav_fair_sp >= 0.55,
                        ))
                    break  # só primeiro ponto válido

    # ── 4. Sinal afiado (sharp money) ────────────────────────────────────────
    if sharp:
        ev_sharp = next((o for o in ev_opps if o.get("Seleção") == sharp or sharp in o.get("Seleção", "")), None)
        odd_sh, bk_sh = _best_odd_for("h2h", sharp)
        prob_sh = probs.get(sharp, {}).get("prob", 0)
        if odd_sh > 1:
            recs.append(_rec(
                "Resultado Final (1X2)", sharp, odd_sh, bk_sh, prob_sh,
                "media", "sharp",
                f"A linha da Pinnacle caiu em {sharp} — sinal de apostadores profissionais "
                "(sharp money) posicionando nesta seleção. Movimento de linha é um dos "
                "indicadores mais confiáveis do mercado.",
                combo_ok=False,
            ))

    # ── 5. BTTS (ambas marcam) ────────────────────────────────────────────────
    if pinnacle:
        for mkt in pinnacle.get("markets", []):
            if mkt["key"] != "btts":
                continue
            names_b  = [o["name"] for o in mkt.get("outcomes", [])]
            prices_b = [o["price"] for o in mkt.get("outcomes", [])]
            if len(names_b) < 2:
                break
            fair_b  = dict(zip(names_b, remove_vig(prices_b)))
            yes_p   = fair_b.get("Yes", 0) * 100
            no_p    = fair_b.get("No",  0) * 100
            odd_yes, bk_yes = _best_odd_for("btts", "Yes")
            odd_no,  bk_no  = _best_odd_for("btts", "No")

            # BTTS Sim: quando jogo é equilibrado e ambos times têm poder ofensivo
            if yes_p >= 55 and odd_yes > 1:
                recs.append(_rec(
                    "Ambas Marcam (Sim/Não)", "Sim", odd_yes, bk_yes, yes_p,
                    "media" if yes_p >= 62 else "baixa", "valor",
                    f"Pinnacle aponta {yes_p:.0f}% de chance de ambos os times marcarem. "
                    "Funciona bem em jogos equilibrados com alta intensidade ofensiva.",
                    combo_ok=yes_p >= 60,
                ))
            # BTTS Não: quando favorito muito dominante ou jogo defensivo esperado
            elif no_p >= 65 and odd_no > 1:
                recs.append(_rec(
                    "Ambas Marcam (Sim/Não)", "Não", odd_no, bk_no, no_p,
                    "media", "segura",
                    f"Pinnacle aponta {no_p:.0f}% de chance de pelo menos um time não marcar. "
                    "Comum quando há grande diferença de nível entre os times.",
                    combo_ok=no_p >= 70,
                ))
            break

    # ── 6. Sugestão de combo ──────────────────────────────────────────────────
    combo_candidates = [r for r in recs if r["combo_ok"] and r["prob_est"] >= 60
                        and r["tipo"] in ("segura", "valor")]
    if len(combo_candidates) >= 2:
        c1, c2 = combo_candidates[:2]
        combo_odd = round(c1["best_odd"] * c2["best_odd"], 3)
        combo_prob = round(c1["prob_est"] * c2["prob_est"] / 100, 1)
        recs.append({
            "mercado":     "💡 Combo Sugerido",
            "selecao":     f"{c1['selecao']}  +  {c2['selecao']}",
            "best_odd":    combo_odd,
            "best_bookie": f"{c1['best_bookie']} + {c2['best_bookie']}",
            "fair_odd":    round(100 / combo_prob, 3) if combo_prob > 0 else 0,
            "prob_est":    combo_prob,
            "confianca":   "media" if combo_prob >= 50 else "baixa",
            "tipo":        "combo",
            "motivo":      (f"Combine **{c1['mercado']} → {c1['selecao']}** ({c1['prob_est']:.0f}%) "
                            f"com **{c2['mercado']} → {c2['selecao']}** ({c2['prob_est']:.0f}%). "
                            f"Odd combinada: {combo_odd:.2f} | Prob. conjunta estimada: {combo_prob:.0f}%."),
            "ev_pct":      None,
            "combo_ok":    False,
        })

    # Ordena: segura > sharp > valor > combo, depois por prob
    _order = {"segura": 0, "sharp": 1, "valor": 2, "combo": 3}
    recs.sort(key=lambda r: (_order.get(r["tipo"], 9), -r["prob_est"]))
    return recs
