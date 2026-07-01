"""EV Finder — Tab: Apostas Múltiplas (Parlays)"""
from functools import reduce
from itertools import combinations
import operator

import pandas as pd
import streamlit as st

from utils import remove_vig, format_brt, hours_until


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _all_outcomes_today(events: list[dict], markets: list[str] | None = None) -> list[dict]:
    """
    Extrai todos os outcomes de hoje com probabilidade justa (via Pinnacle).
    Retorna também a melhor odd disponível em outros bookmakers.
    """
    if markets is None:
        markets = ["h2h"]

    _MARKET_LABELS = {
        "h2h":       "Resultado Final",
        "draw_no_bet": "Empate Anula",
        "btts":      "Ambas Marcam",
        "totals":    "Total de Gols",
        "spreads":   "Handicap",
    }

    rows = []
    for event in events:
        commence = event.get("commence_time", "")
        h = hours_until(commence)
        if h is None or h < -4 or h > 48:
            continue

        bookmakers = event.get("bookmakers", [])
        pinnacle   = next((b for b in bookmakers if b["key"] == "pinnacle"), None)
        if not pinnacle:
            continue

        jogo    = f"{event.get('home_team','?')} vs {event.get('away_team','?')}"
        horario = format_brt(commence)
        eid     = event.get("id", jogo)

        for mkt in pinnacle.get("markets", []):
            mkey = mkt["key"]
            if mkey not in markets:
                continue
            pin_outcomes = mkt.get("outcomes", [])
            if len(pin_outcomes) < 2:
                continue

            # Para totals/spreads precisamos agrupar por linha — usa só h2h por padrão
            if mkey in ("totals", "spreads"):
                continue  # complexo demais para o modo prob, skip

            prices     = [o["price"] for o in pin_outcomes]
            fair_probs = remove_vig(prices)
            label      = _MARKET_LABELS.get(mkey, mkey)

            for o, prob in zip(pin_outcomes, fair_probs):
                name = o["name"]
                # Melhor odd disponível em outros bookmakers
                best_odd, best_bk = 1.0, "—"
                for bk in bookmakers:
                    if bk["key"] == "pinnacle":
                        continue
                    for bk_mkt in bk.get("markets", []):
                        if bk_mkt["key"] != mkey:
                            continue
                        for bo in bk_mkt.get("outcomes", []):
                            if bo["name"] == name and bo["price"] > best_odd:
                                best_odd = bo["price"]
                                best_bk  = bk.get("title", bk["key"])

                rows.append({
                    "Jogo":             jogo,
                    "Horário":          horario,
                    "Mercado":          label,
                    "Seleção":          name,
                    "Prob. (%)":        round(prob * 100, 1),
                    "Melhor Odd":       round(best_odd, 3) if best_odd > 1.0 else None,
                    "Casa":             best_bk,
                    "event_id":         eid,
                    "commence_time":    commence,
                })

    rows.sort(key=lambda x: (x["commence_time"], -x["Prob. (%)"]))
    return rows


def _parlay_stats_prob(rows: list[dict]) -> dict:
    """Versão para modo probabilidade — usa 'Prob. (%)' em vez de 'Prob. Real (%)'."""
    probs        = [r["Prob. (%)"] / 100 for r in rows]
    odds         = [r["Melhor Odd"] or 1.0 for r in rows]
    prob_combined = reduce(operator.mul, probs, 1.0)
    odd_combined  = reduce(operator.mul, odds,  1.0)
    ev            = prob_combined * odd_combined - 1
    return {
        "prob_bater":    round(prob_combined * 100, 2),
        "odd_combinada": round(odd_combined, 3),
        "ev_pct":        round(ev * 100, 2),
    }


def _parlay_stats(rows: list[dict]) -> dict:
    probs = [r["Prob. Real (%)"] / 100 for r in rows]
    odds  = [r["Odd Casa"] for r in rows]
    prob_combined = reduce(operator.mul, probs, 1.0)
    odd_combined  = reduce(operator.mul, odds,  1.0)
    ev    = prob_combined * odd_combined - 1
    kelly = ev / (odd_combined - 1) if odd_combined > 1.001 else 0.0
    return {
        "odd_combinada": round(odd_combined, 3),
        "prob_bater":    round(prob_combined * 100, 2),
        "ev_pct":        round(ev * 100, 2),
        "kelly_bruto":   round(max(0.0, kelly) * 100, 4),
    }


def _has_same_event(rows: list[dict]) -> bool:
    ids = [r.get("event_id") or r["Jogo"] for r in rows]
    return len(ids) != len(set(ids))


def _diverse_pool(opps: list[dict], max_per_event: int = 2) -> list[dict]:
    """Round-robin across events: pega as N melhores apostas de cada jogo."""
    by_event: dict[str, list[dict]] = {}
    for o in opps:
        key = o.get("event_id") or o["Jogo"]
        by_event.setdefault(key, []).append(o)
    pool: list[dict] = []
    for rank in range(max_per_event):
        for bets in by_event.values():
            if rank < len(bets):
                pool.append(bets[rank])
    return pool


def _ev_bg(val: float) -> str:
    if val >= 15: return "background-color:#155724;color:white;font-weight:bold"
    if val >= 10: return "background-color:#1e7e34;color:white;font-weight:bold"
    if val >=  5: return "background-color:#28a745;color:white"
    if val >=  0: return "background-color:#c3e6cb;color:#155724"
    return "background-color:#f8d7da;color:#721c24"


# ─── Render ───────────────────────────────────────────────────────────────────

def render(cfg: dict) -> None:
    bankroll    = cfg["bankroll"]
    kelly_frac  = cfg["kelly_frac"]
    kelly_label = cfg["kelly_label"]

    st.subheader("🎰 Apostas Múltiplas")
    st.caption(
        "Combine seleções EV+ numa múltipla. "
        "A probabilidade de bater assume **independência** entre os jogos."
    )

    if "results" not in st.session_state or not st.session_state["results"]:
        st.info("Faça uma busca na aba **🔍 Buscar EV+** primeiro.")
        return

    opps: list[dict] = st.session_state["results"]

    # ── Builder Manual ────────────────────────────────────────────────────────
    st.markdown("### 🏗️ Montador de Múltipla")

    # Labels únicos por índice
    def _label(i: int, o: dict) -> str:
        return (
            f"#{i+1}  {o['Jogo']}  |  {o['Seleção']}  @  {o['Casa']}"
            f"  |  odd {o['Odd Casa']:.2f}  |  EV {o['EV (%)']:+.1f}%"
        )

    options      = [_label(i, o) for i, o in enumerate(opps)]
    idx_by_label = {_label(i, o): i for i, o in enumerate(opps)}

    selected_labels = st.multiselect(
        "Selecione as apostas para combinar",
        options=options,
        placeholder="Escolha 2 ou mais seleções…",
        key="multiplas_select",
    )

    if len(selected_labels) >= 2:
        sel_rows = [opps[idx_by_label[l]] for l in selected_labels]
        s = _parlay_stats(sel_rows)
        kelly_val = round(s["kelly_bruto"] * kelly_frac, 4)
        apostar   = round(bankroll * kelly_val / 100, 2)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Odd Combinada",   f"{s['odd_combinada']:.2f}×")
        m2.metric("Prob. de Bater",  f"{s['prob_bater']:.2f}%")
        m3.metric("EV da Múltipla",  f"{s['ev_pct']:+.2f}%",
                  delta_color="normal" if s["ev_pct"] >= 0 else "inverse")
        m4.metric(f"Apostar ({kelly_label})", f"R$ {apostar:.2f}")

        if _has_same_event(sel_rows):
            st.warning(
                "⚠️ Duas ou mais seleções pertencem ao **mesmo jogo** — "
                "resultados são correlacionados e a prob. real pode ser diferente."
            )

        if s["ev_pct"] < 0:
            st.warning(
                f"Esta combinação tem EV **{s['ev_pct']:+.2f}%**. "
                "Seleções individuais podem ter EV+ mas a múltipla pode não ter — "
                "o impacto da vig se multiplica."
            )
        else:
            retorno = 100 * (1 + s["ev_pct"] / 100)
            st.success(
                f"✅ EV **{s['ev_pct']:+.2f}%** — retorno esperado de "
                f"**R$ {retorno:.0f}** por cada R$ 100 apostados a longo prazo."
            )

        detail_df = pd.DataFrame([{
            "Jogo":      r["Jogo"],
            "Seleção":   r["Seleção"],
            "Casa":      r["Casa"],
            "Odd":       r["Odd Casa"],
            "Prob. (%)": r["Prob. Real (%)"],
            "EV (%)":    r["EV (%)"],
        } for r in sel_rows])

        st.dataframe(
            detail_df,
            hide_index=True,
            column_config={
                "Odd":       st.column_config.NumberColumn(format="%.3f"),
                "Prob. (%)": st.column_config.NumberColumn(format="%.1f%%"),
                "EV (%)":    st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )

        if st.button("➕ Registrar múltipla no Tracker", key="reg_multipla"):
            st.session_state["pending_bet"] = {
                "jogo":      " + ".join(r["Jogo"] for r in sel_rows),
                "mercado":   "Múltipla",
                "selecao":   " × ".join(r["Seleção"] for r in sel_rows),
                "odd":       s["odd_combinada"],
                "stake":     apostar,
                "ev_pct":    s["ev_pct"],
                "prob_real": s["prob_bater"],
                "casa":      " / ".join(sorted({r["Casa"] for r in sel_rows})),
            }
            st.toast("Múltipla copiada para o Tracker!", icon="📋")

    elif len(selected_labels) == 1:
        st.info("Selecione ao menos **2 seleções** para montar uma múltipla.")

    st.divider()

    # ── Sugestões Automáticas ─────────────────────────────────────────────────
    st.markdown("### 🤖 Melhores Combinações do Dia")

    # Perfis predefinidos
    _PERFIS = {
        "🛡️ Conservador":  dict(min_prob_sel=40, min_prob_parlay=15, max_odd_sel=3.5,  min_ev=0),
        "⚖️ Moderado":     dict(min_prob_sel=25, min_prob_parlay= 8, max_odd_sel=6.0,  min_ev=0),
        "🚀 Agressivo":    dict(min_prob_sel=10, min_prob_parlay= 2, max_odd_sel=15.0, min_ev=0),
        "⚙️ Personalizado": None,
    }
    perfil_key = st.radio(
        "Perfil de risco",
        list(_PERFIS.keys()),
        index=1,
        horizontal=True,
        key="m_perfil",
    )

    # Linha de configuração
    if perfil_key == "⚙️ Personalizado":
        fc1, fc2, fc3, fc4 = st.columns(4)
        min_prob_sel    = fc1.slider("Prob. mín. por seleção (%)", 5,  90, 25, key="m_min_prob_sel",
                                     help="Remove longshots — ex: 40% exclui odds > 2.50")
        min_prob_parlay = fc2.slider("Prob. mín. da múltipla (%)", 1,  60, 8,  key="m_min_prob_par",
                                     help="Prob. mínima de toda a combinação bater")
        max_odd_sel     = fc3.slider("Odd máxima por seleção",     1.1, 20.0, 6.0, step=0.5,
                                     key="m_max_odd_sel",
                                     help="Limita o risco por perna da múltipla")
        min_ev_m        = fc4.slider("EV mínimo da múltipla (%)",  -10, 30, 0, key="m_min_ev_cust")
    else:
        p = _PERFIS[perfil_key]
        min_prob_sel, min_prob_parlay, max_odd_sel, min_ev_m = (
            p["min_prob_sel"], p["min_prob_parlay"], p["max_odd_sel"], p["min_ev"]
        )
        st.caption(
            f"Prob. mín./seleção: **{min_prob_sel}%** · "
            f"Prob. mín. da múltipla: **{min_prob_parlay}%** · "
            f"Odd máx./seleção: **{max_odd_sel:.1f}×**"
        )

    c_legs, c_ord = st.columns([1, 2])
    n_legs   = c_legs.radio("Pernas", [2, 3], horizontal=True, key="m_legs")
    ordem_by = c_ord.radio(
        "Ordenar por",
        ["EV ↓ (melhor valor)", "Prob. ↓ (mais provável de bater)"],
        horizontal=True, key="m_ordem",
    )

    # Monta pool diverso e aplica filtros por seleção
    raw_pool = _diverse_pool(opps, max_per_event=2)
    pool     = [o for o in raw_pool
                if o["Prob. Real (%)"] >= min_prob_sel
                and o["Odd Casa"] <= max_odd_sel]
    n_jogos  = len({o.get("event_id") or o["Jogo"] for o in pool})

    if not pool:
        st.warning(
            f"Nenhuma seleção com prob ≥ {min_prob_sel}% e odd ≤ {max_odd_sel:.1f}× "
            "nos dados atuais. Reduza os filtros ou troque para perfil **Agressivo**."
        )
    else:
        st.caption(
            f"Pool filtrado: **{len(pool)} seleções** de **{n_jogos} jogos** "
            f"(prob ≥ {min_prob_sel}%, odd ≤ {max_odd_sel:.1f}×)."
        )

        combos: list[dict] = []
        for combo in combinations(pool, n_legs):
            if _has_same_event(list(combo)):
                continue
            s = _parlay_stats(list(combo))
            if s["ev_pct"] < min_ev_m:
                continue
            if s["prob_bater"] < min_prob_parlay:
                continue
            combos.append({
                "EV (%)":          s["ev_pct"],
                "Odd Comb.":       s["odd_combinada"],
                "Prob. Bater (%)": s["prob_bater"],
                "Seleções":        " + ".join(c["Seleção"] for c in combo),
                "Casas":           " / ".join(sorted({c["Casa"] for c in combo})),
                "_rows":           list(combo),
            })

        sort_key = "EV (%)" if "EV" in ordem_by else "Prob. Bater (%)"
        combos.sort(key=lambda x: x[sort_key], reverse=True)
        top = combos[:15]

        if not top:
            st.info(
                f"Nenhuma combinação com os filtros atuais "
                f"(prob/seleção ≥ {min_prob_sel}%, prob/múltipla ≥ {min_prob_parlay}%). "
                "Tente o perfil **Moderado** ou **Agressivo**."
            )
        else:
            st.caption(f"**{len(combos)}** combinações válidas — exibindo as **{len(top)} melhores**.")

            display_df = pd.DataFrame([{k: v for k, v in c.items() if not k.startswith("_")}
                                        for c in top])
            styled = display_df.style.map(_ev_bg, subset=["EV (%)"])
            st.dataframe(
                styled,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "EV (%)":          st.column_config.NumberColumn(format="%+.2f%%"),
                    "Odd Comb.":       st.column_config.NumberColumn(format="%.2f×"),
                    "Prob. Bater (%)": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

            st.markdown("#### Detalhes e registro")
            for i, c in enumerate(top[:5]):
                kelly_c   = (c["EV (%)"] / 100) / (c["Odd Comb."] - 1) * kelly_frac \
                            if c["Odd Comb."] > 1.001 else 0.0
                apostar_c = round(bankroll * max(0.0, kelly_c), 2)
                with st.expander(
                    f"#{i+1}  EV {c['EV (%)']:+.2f}%  |  odd {c['Odd Comb.']:.2f}×  "
                    f"|  prob {c['Prob. Bater (%)']:.2f}%  |  {c['Seleções'][:70]}"
                ):
                    for r in c["_rows"]:
                        st.markdown(
                            f"- **{r['Seleção']}** ({r['Casa']}) — "
                            f"odd {r['Odd Casa']:.3f} · prob {r['Prob. Real (%)']:.1f}% · "
                            f"EV {r['EV (%)']:+.2f}%"
                        )
                    st.markdown(
                        f"**Aposta sugerida ({kelly_label}):** R$ {apostar_c:.2f}  \n"
                        f"*Retorno esperado por R$ 100: R$ {100 * (1 + c['EV (%)'] / 100):.0f}*"
                    )
                    if st.button("➕ Registrar no Tracker", key=f"reg_auto_m_{i}"):
                        rows_c = c["_rows"]
                        st.session_state["pending_bet"] = {
                            "jogo":      " + ".join(r["Jogo"] for r in rows_c),
                            "mercado":   "Múltipla",
                            "selecao":   " × ".join(r["Seleção"] for r in rows_c),
                            "odd":       c["Odd Comb."],
                            "stake":     apostar_c,
                            "ev_pct":    c["EV (%)"],
                            "prob_real": c["Prob. Bater (%)"],
                            "casa":      c["Casas"],
                        }
                        st.toast("Múltipla copiada para o Tracker!", icon="📋")

    st.divider()

    # ── Modo Probabilidade — todos os jogos de hoje ───────────────────────────
    st.markdown("### 🎲 Combinações por Probabilidade — Todos os Jogos")
    st.caption(
        "Ignora EV — usa probabilidades justas do Pinnacle para **todos** os jogos do dia. "
        "Útil para encontrar combinações com boa chance de acertar, independente do valor."
    )

    all_events = st.session_state.get("all_events", [])
    if not all_events:
        st.info("Faça uma busca primeiro para carregar os jogos de hoje.")
    else:
        # Mercados disponíveis (só os que o _all_outcomes_today suporta)
        _MKT_OPTS = {"h2h": "Resultado Final (1X2)", "draw_no_bet": "Empate Anula", "btts": "Ambas Marcam"}
        pb_mkts = st.multiselect(
            "Mercados",
            options=list(_MKT_OPTS.keys()),
            default=["h2h"],
            format_func=lambda k: _MKT_OPTS[k],
            key="pb_mkts",
        )
        if not pb_mkts:
            pb_mkts = ["h2h"]

        all_out = _all_outcomes_today(all_events, markets=pb_mkts)

        if not all_out:
            st.warning("Nenhum jogo encontrado para hoje (próximas 48h) com dados do Pinnacle.")
        else:
            n_jogos_hoje = len({r["event_id"] for r in all_out})
            st.caption(f"**{len(all_out)} outcomes** de **{n_jogos_hoje} jogos** disponíveis.")

            pb_c1, pb_c2, pb_c3 = st.columns(3)
            pb_legs     = pb_c1.radio("Pernas", [2, 3], horizontal=True, key="pb_legs")
            pb_min_sel  = pb_c2.slider("Prob. mín. por seleção (%)", 5, 90, 40, key="pb_min_sel",
                                        help="Ex: 40% = apenas favoritos com >40% de chance")
            pb_min_tot  = pb_c3.slider("Prob. mín. da múltipla (%)", 1, 60, 15, key="pb_min_tot")

            # Pool filtrado
            pb_pool = [r for r in all_out if r["Prob. (%)"] >= pb_min_sel]
            n_pool_jogos = len({r["event_id"] for r in pb_pool})

            if not pb_pool:
                st.info(f"Nenhuma seleção com prob ≥ {pb_min_sel}%. Reduza o filtro.")
            else:
                st.caption(
                    f"Pool: **{len(pb_pool)} seleções** de **{n_pool_jogos} jogos** "
                    f"(prob ≥ {pb_min_sel}%)."
                )

                # Gera combinações
                pb_combos = []
                for combo in combinations(pb_pool, pb_legs):
                    ids = [r["event_id"] for r in combo]
                    if len(ids) != len(set(ids)):
                        continue
                    s = _parlay_stats_prob(list(combo))
                    if s["prob_bater"] < pb_min_tot:
                        continue
                    pb_combos.append({
                        "Prob. Bater (%)": s["prob_bater"],
                        "Odd Comb.":       s["odd_combinada"],
                        "EV (%)":          s["ev_pct"],
                        "Seleções":        " + ".join(r["Seleção"] for r in combo),
                        "Horários":        " | ".join(r["Horário"] for r in combo),
                        "_rows":           list(combo),
                    })

                pb_combos.sort(key=lambda x: x["Prob. Bater (%)"], reverse=True)
                top_pb = pb_combos[:20]

                if not top_pb:
                    st.info(
                        f"Nenhuma combinação de {pb_legs} seleções com prob ≥ {pb_min_tot}%. "
                        "Reduza os filtros."
                    )
                else:
                    st.caption(
                        f"**{len(pb_combos)}** combinações válidas — "
                        f"exibindo as **{len(top_pb)} mais prováveis**."
                    )

                    def _prob_bg(val: float) -> str:
                        if val >= 60: return "background-color:#155724;color:white;font-weight:bold"
                        if val >= 40: return "background-color:#1e7e34;color:white;font-weight:bold"
                        if val >= 25: return "background-color:#28a745;color:white"
                        if val >= 15: return "background-color:#c3e6cb;color:#155724"
                        return ""

                    pb_df = pd.DataFrame([
                        {k: v for k, v in c.items() if not k.startswith("_")}
                        for c in top_pb
                    ])
                    pb_styled = pb_df.style.map(_prob_bg, subset=["Prob. Bater (%)"])

                    st.dataframe(
                        pb_styled,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Prob. Bater (%)": st.column_config.NumberColumn(format="%.1f%%"),
                            "Odd Comb.":       st.column_config.NumberColumn(format="%.2f×"),
                            "EV (%)":          st.column_config.NumberColumn(format="%+.1f%%"),
                        },
                    )

                    st.markdown("#### Detalhes")
                    for i, c in enumerate(top_pb[:5]):
                        ev_icon = "✅" if c["EV (%)"] >= 0 else "⚠️"
                        with st.expander(
                            f"#{i+1}  {c['Prob. Bater (%)']:.1f}% de bater  |  "
                            f"odd {c['Odd Comb.']:.2f}×  |  {c['Seleções'][:70]}"
                        ):
                            for r in c["_rows"]:
                                best = f"odd {r['Melhor Odd']:.2f} @ {r['Casa']}" \
                                       if r["Melhor Odd"] else "sem odd disponível"
                                st.markdown(
                                    f"- **{r['Seleção']}** ({r['Jogo']}, {r['Horário']})  \n"
                                    f"  Prob. Pinnacle: **{r['Prob. (%)']}%** · {best}"
                                )
                            st.markdown(
                                f"{ev_icon} EV estimado: **{c['EV (%)']:+.1f}%** "
                                f"(com as melhores odds disponíveis)"
                            )
                            if st.button("➕ Registrar no Tracker", key=f"reg_pb_{i}"):
                                rows_c = c["_rows"]
                                st.session_state["pending_bet"] = {
                                    "jogo":      " + ".join(r["Jogo"] for r in rows_c),
                                    "mercado":   "Múltipla",
                                    "selecao":   " × ".join(r["Seleção"] for r in rows_c),
                                    "odd":       c["Odd Comb."],
                                    "stake":     0.0,
                                    "ev_pct":    c["EV (%)"],
                                    "prob_real": c["Prob. Bater (%)"],
                                    "casa":      " / ".join(sorted({r["Casa"] for r in rows_c if r["Casa"] != "—"})),
                                }
                                st.toast("Múltipla copiada para o Tracker!", icon="📋")

    st.divider()
    st.caption(
        "⚠️ Prob. de bater assume **independência** entre os jogos. "
        "Múltiplas têm variância muito maior que apostas simples — use Kelly fracionado."
    )
