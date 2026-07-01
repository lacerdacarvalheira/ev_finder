"""EV Finder — Tab: Buscar EV+"""
import time

import pandas as pd
import streamlit as st

from utils import hours_until, urgency_badge


def render(cfg: dict) -> None:
    api_key        = cfg["api_key"]
    min_ev_pct     = cfg["min_ev_pct"]
    kelly_frac     = cfg["kelly_frac"]
    bankroll       = cfg["bankroll"]
    odd_range      = cfg["odd_range"]
    alert_threshold = cfg["alert_threshold"]
    sound_alerts   = cfg["sound_alerts"]
    auto_refresh   = cfg["auto_refresh"]
    has_autorefresh = cfg["has_autorefresh"]
    refresh_interval = cfg["refresh_interval"]
    kelly_label    = cfg["kelly_label"]

    if not api_key:
        st.info(
            "### 👈 Como começar\n\n"
            "1. Acesse **[the-odds-api.com](https://the-odds-api.com)** → **Get API Key**\n"
            "2. Crie conta gratuita (sem cartão)\n"
            "3. Cole a chave na barra lateral → 💾 Salvar\n"
            "4. Clique em 🔍 **Buscar Oportunidades**\n\n"
            "_Plano gratuito: **500 requisições/mês** — cada busca via cache não consome req._"
        )
        return

    if "results" not in st.session_state:
        st.info("Configure as ligas e clique em **🔍 Buscar Oportunidades** na barra lateral.")
        return

    # — Alerta visual + sonoro —
    _alert_n = st.session_state.get("_alert_count", 0)
    _alert_b = st.session_state.get("_alert_best", 0.0)
    if _alert_n > 0 and _alert_b >= alert_threshold:
        st.error(
            f"🚨 **{_alert_n} oportunidade(s) com EV ≥ {alert_threshold}%!** "
            f"Melhor EV encontrado: **+{_alert_b:.1f}%**"
        )
        if sound_alerts and st.session_state.pop("_alert_play", False):
            st.html("""
            <script>
            try {
              const ctx = new (window.AudioContext || window.webkitAudioContext)();
              [[800,0],[1050,0.18],[800,0.36]].forEach(([f,t]) => {
                const o = ctx.createOscillator(), g = ctx.createGain();
                o.connect(g); g.connect(ctx.destination);
                o.frequency.value = f; g.gain.value = 0.25;
                o.start(ctx.currentTime + t);
                o.stop(ctx.currentTime + t + 0.15);
              });
            } catch(e) {}
            </script>
            """)

    all_opps     = st.session_state["results"]
    events_count = st.session_state.get("events_count", 0)
    min_ev_used  = st.session_state.get("min_ev_used", min_ev_pct)

    # Auto-refresh info
    if auto_refresh and has_autorefresh:
        last_t = st.session_state.get("last_search_time", 0)
        if last_t:
            elapsed = int(time.time() - last_t)
            remaining_secs = max(0, refresh_interval * 60 - elapsed)
            st.caption(
                f"🔄 Auto-refresh ativo — próxima busca em "
                f"**{remaining_secs // 60}m {remaining_secs % 60}s**"
            )

    # Aplica filtro de odds
    odd_min, odd_max = odd_range
    opps = [o for o in all_opps if odd_min <= o["Odd Casa"] <= odd_max]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jogos analisados", events_count)
    c2.metric(
        "Oportunidades EV+", len(opps),
        delta=f"{len(opps) - len(all_opps)} filtro odds" if len(opps) != len(all_opps) else None,
    )
    c3.metric("EV mínimo", f"{min_ev_used}%")
    c4.metric("Melhor EV", f"{opps[0]['EV (%)']:.2f}%" if opps else "—")

    st.divider()

    if not opps:
        if all_opps:
            st.info(
                f"Nenhuma oportunidade no intervalo **{odd_min:.2f}–{odd_max:.2f}**. "
                f"Há {len(all_opps)} oportunidade(s) fora desse intervalo — ajuste o slider."
            )
        else:
            st.info(
                f"Nenhuma oportunidade com EV ≥ {min_ev_used}% encontrada. "
                "Tente reduzir o EV mínimo ou buscar mais perto do horário dos jogos."
            )
        return

    # ─── Filtros avançados ────────────────────────────────────────────────────
    with st.expander("🔎 Filtros avançados", expanded=False):
        fa1, fa2, fa3 = st.columns(3)
        _search = fa1.text_input("Buscar time", placeholder="ex: Brasil, France…",
                                  key="ev_search").strip().lower()
        _casas_all     = sorted({o["Casa"]    for o in opps})
        _mercados_all  = sorted({o["Mercado"] for o in opps})
        _sel_casas     = fa2.multiselect("Casa", _casas_all, default=[],
                                          placeholder="Todas", key="ev_casas")
        _sel_mercados  = fa3.multiselect("Mercado", _mercados_all, default=[],
                                          placeholder="Todos", key="ev_mercados")

    # aplica filtros
    n_before = len(opps)
    if _search:
        opps = [o for o in opps if _search in o["Jogo"].lower()]
    if _sel_casas:
        opps = [o for o in opps if o["Casa"] in _sel_casas]
    if _sel_mercados:
        opps = [o for o in opps if o["Mercado"] in _sel_mercados]

    n_filtered = n_before - len(opps)
    _filter_label = (
        f"✅ {len(opps)} oportunidade(s) "
        + (f"| {n_filtered} filtradas" if n_filtered else f"| odds {odd_min:.2f}–{odd_max:.2f}")
    )
    st.success(_filter_label)

    if not opps:
        st.info("Nenhuma oportunidade com os filtros aplicados.")
        return

    # Aplica Kelly e bankroll
    df = pd.DataFrame(opps)
    df["Kelly (%)"]   = (df["Kelly bruto (%)"] * kelly_frac).round(2)
    df["Apostar (R$)"] = (bankroll * df["Kelly (%)"] / 100).round(2)

    # Urgência
    df["Urgência"] = df["commence_time_raw"].apply(
        lambda x: urgency_badge(hours_until(x))
    )

    # Ordenação
    sort_by = st.selectbox(
        "Ordenar por",
        ["EV (%) ↓", "Urgência (jogo mais próximo)", "Odd Casa ↑"],
        index=0,
    )
    if sort_by == "Urgência (jogo mais próximo)":
        df["_hours"] = df["commence_time_raw"].apply(lambda x: hours_until(x) or 9999)
        df = df.sort_values("_hours").drop(columns=["_hours"])
    elif sort_by == "Odd Casa ↑":
        df = df.sort_values("Odd Casa")

    display_cols = [
        "Urgência", "EV (%)", "Prob. Real (%)", "Kelly (%)", "Apostar (R$)",
        "Casa", "Jogo", "Horário (BRT)", "Mercado", "Seleção",
        "Odd Casa", "Odd Pinnacle (fair)",
    ]

    def _ev_color(val: float) -> str:
        if val >= 15: return "background-color:#155724;color:white;font-weight:bold"
        if val >= 10: return "background-color:#1e7e34;color:white;font-weight:bold"
        if val >= 7:  return "background-color:#28a745;color:white"
        return "background-color:#c3e6cb;color:#155724"

    styled = df[display_cols].style.map(_ev_color, subset=["EV (%)"])

    st.dataframe(
        styled,
        width='stretch',
        hide_index=True,
        column_config={
            "EV (%)":              st.column_config.NumberColumn(format="%.2f%%"),
            "Prob. Real (%)":      st.column_config.NumberColumn(format="%.1f%%"),
            "Kelly (%)":           st.column_config.NumberColumn(format="%.2f%%"),
            "Apostar (R$)":        st.column_config.NumberColumn(format="R$ %.2f"),
            "Odd Casa":            st.column_config.NumberColumn(format="%.3f"),
            "Odd Pinnacle (fair)": st.column_config.NumberColumn(format="%.3f"),
            "Urgência":            st.column_config.TextColumn(help="Tempo até o jogo começar"),
        },
    )

    # Análise individual
    st.subheader("🔎 Análise detalhada")
    st.caption("Selecione uma oportunidade para ver a análise e registrar a aposta.")

    for i, row in enumerate(df.to_dict("records")):
        prob    = row["Prob. Real (%)"]
        ev      = row["EV (%)"]
        odd_c   = row["Odd Casa"]
        odd_f   = row["Odd Pinnacle (fair)"]
        casa    = row["Casa"]
        sel     = row["Seleção"]
        urgencia = row["Urgência"]
        kelly_r = round(row["Kelly bruto (%)"] * kelly_frac, 2)
        valor_r = round(bankroll * kelly_r / 100, 2)

        with st.expander(
            f"{urgencia}  #{i+1}  {row['Jogo']} — {sel} ({casa}) | EV: +{ev:.1f}%"
        ):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(
                    f"A Pinnacle precifica **{sel}** com **{prob:.1f}% de chance real**.  \n"
                    f"A {casa} paga **{odd_c:.3f}**, odd justa seria **{odd_f:.3f}**.  \n"
                    f"**+{ev:.2f}% EV** — a cada R$100 apostados nesta seleção ao longo do tempo, "
                    f"retorno esperado de **R${100 * (1 + ev/100):.0f}**."
                )
                st.markdown(
                    f"**Kelly ({kelly_label}):** {kelly_r:.2f}% = **R$ {valor_r:.2f}** "
                    f"(bankroll: R$ {bankroll:,.0f})"
                )
            with col_b:
                if st.button("➕ Registrar aposta", key=f"reg_{i}"):
                    st.session_state["pending_bet"] = {
                        "jogo":      row["Jogo"],
                        "mercado":   row["Mercado"],
                        "selecao":   sel,
                        "odd":       odd_c,
                        "stake":     valor_r,
                        "ev_pct":    ev,
                        "prob_real": prob,
                        "casa":      casa,
                    }
                    st.toast("Aposta copiada! Vá para a aba 📋 Tracker.", icon="📋")

    st.divider()
    st.caption(
        "⚠️ Ferramenta pessoal e educacional. EV+ não garante lucro individual. "
        "Jogue com responsabilidade."
    )
