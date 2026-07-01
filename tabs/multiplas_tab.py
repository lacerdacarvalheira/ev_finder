"""EV Finder — Tab: Apostas Múltiplas (Parlays)"""
from functools import reduce
from itertools import combinations
import operator

import pandas as pd
import streamlit as st


# ─── Helpers ─────────────────────────────────────────────────────────────────

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
    st.caption(
        "⚠️ Prob. de bater assume **independência** entre os jogos. "
        "Múltiplas têm variância muito maior que apostas simples — use Kelly fracionado."
    )
