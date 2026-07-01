"""EV Finder — Tab: Simulação de Variância (Monte Carlo) + Kelly Portfólio"""
import numpy as np
import plotly.graph_objects as go
import streamlit as st


def render(cfg: dict) -> None:
    bankroll  = cfg["bankroll"]
    kelly_map = cfg["kelly_map"]

    st.subheader("📈 Simulação de Variância (Monte Carlo)")
    st.caption(
        "Simula centenas de caminhos possíveis do seu bankroll com base em EV e probabilidade. "
        "Mostra o intervalo realista de resultados — não só a linha do valor esperado."
    )

    sc1, sc2 = st.columns(2)
    with sc1:
        sim_ev   = st.number_input("EV da aposta (%)",     min_value=1.0, max_value=50.0, value=5.0,  step=0.5)
        sim_prob = st.number_input("Prob. real (%)",        min_value=5.0, max_value=95.0, value=50.0, step=1.0)
        sim_bank = st.number_input("Bankroll inicial (R$)", min_value=100.0, value=float(bankroll), step=100.0)
    with sc2:
        sim_bets  = st.slider("Número de apostas",    min_value=10, max_value=500, value=100)
        sim_sims  = st.slider("Número de simulações", min_value=50, max_value=500, value=200)
        sim_kelly_label = st.selectbox("Fração Kelly (simulação)", list(kelly_map.keys()), index=0, key="sim_kelly")
        sim_kelly_frac  = kelly_map[sim_kelly_label]

    if st.button("▶️ Simular", type="primary"):
        ev_dec   = sim_ev / 100
        prob_dec = sim_prob / 100
        odd      = (1 + ev_dec) / prob_dec
        kelly_b  = ev_dec / (odd - 1)
        kelly_s  = kelly_b * sim_kelly_frac

        st.info(
            f"**Odd implícita:** {odd:.3f} | "
            f"**Kelly bruto:** {kelly_b*100:.2f}% | "
            f"**Stake por aposta:** {kelly_s*100:.2f}% do bankroll atual"
        )

        rng   = np.random.default_rng(42)
        paths = np.empty((sim_sims, sim_bets + 1))
        paths[:, 0] = sim_bank

        for s in range(sim_sims):
            for b in range(sim_bets):
                bank  = paths[s, b]
                stake = bank * kelly_s
                if rng.random() < prob_dec:
                    paths[s, b + 1] = bank + stake * (odd - 1)
                else:
                    paths[s, b + 1] = bank - stake

        x       = np.arange(sim_bets + 1)
        p10     = np.percentile(paths, 10, axis=0)
        p90     = np.percentile(paths, 90, axis=0)
        median  = np.median(paths, axis=0)
        ev_line = sim_bank * ((1 + ev_dec) ** (kelly_s * x))

        fig = go.Figure()
        for s in range(min(sim_sims, 100)):
            fig.add_trace(go.Scatter(
                x=x, y=paths[s],
                mode="lines",
                line=dict(width=0.5, color="rgba(150,150,150,0.15)"),
                showlegend=False,
                hoverinfo="skip",
            ))
        fig.add_trace(go.Scatter(
            x=np.concatenate([x, x[::-1]]),
            y=np.concatenate([p90, p10[::-1]]),
            fill="toself",
            fillcolor="rgba(40,167,69,0.15)",
            line=dict(width=0),
            name="Intervalo 10-90%",
        ))
        fig.add_trace(go.Scatter(x=x, y=median,
            mode="lines", line=dict(width=2.5, color="#0d6efd"), name="Mediana"))
        fig.add_trace(go.Scatter(x=x, y=ev_line,
            mode="lines", line=dict(width=2, color="#28a745", dash="dash"), name="Valor esperado"))
        fig.add_hline(y=sim_bank, line_dash="dot", line_color="grey", opacity=0.5,
                      annotation_text="Bankroll inicial", annotation_position="right")
        fig.update_layout(
            xaxis_title="Número de apostas",
            yaxis_title="Bankroll (R$)",
            height=480,
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
            margin=dict(l=0, r=0, t=40, b=0),
            hovermode="x unified",
        )
        st.plotly_chart(fig, width='stretch')

        final_vals = paths[:, -1]
        sr1, sr2, sr3, sr4 = st.columns(4)
        sr1.metric("Mediana final",          f"R$ {np.median(final_vals):,.0f}")
        sr2.metric("Pior 10%",               f"R$ {np.percentile(final_vals, 10):,.0f}")
        sr3.metric("Melhor 10%",             f"R$ {np.percentile(final_vals, 90):,.0f}")
        sr4.metric("% simulações com lucro", f"{np.mean(final_vals > sim_bank) * 100:.0f}%")

        st.caption(
            "A simulação usa apostas proporcionais ao bankroll atual (Kelly composto). "
            "Mesmo com EV positivo, há caminhos de perda — isso é variância normal. "
            "Quanto maior o número de apostas, mais o resultado converge para o valor esperado."
        )

    st.divider()

    # ─── Kelly Portfólio ──────────────────────────────────────────────────────
    st.subheader("🗂️ Kelly Portfólio — Múltiplas Apostas Simultâneas")
    st.caption(
        "Quando você tem várias apostas EV+ ao mesmo tempo, o Kelly individual de cada uma "
        "superestima quanto apostar — o bankroll é compartilhado. "
        "Este calculador ajusta proporcionalmente para que as stakes totais não ultrapassem "
        "uma fração segura do bankroll."
    )

    pf_bank  = st.number_input("Bankroll disponível (R$)", min_value=10.0,
                                value=float(bankroll), step=100.0, key="pf_bank")
    pf_frac  = st.slider("Fração máxima do bankroll a alocar (%)",
                          min_value=5, max_value=50, value=20, key="pf_frac",
                          help="Limite total de exposição simultânea. Kelly puro pode recomendar >100% — nunca faça isso.")

    st.markdown("**Apostas no portfólio:**")

    if "pf_bets" not in st.session_state:
        st.session_state["pf_bets"] = [{"ev": 5.0, "odd": 2.0, "label": "Aposta 1"}]

    pf_bets = st.session_state["pf_bets"]

    cols_h = st.columns([3, 2, 2, 1])
    cols_h[0].markdown("**Descrição**")
    cols_h[1].markdown("**EV (%)**")
    cols_h[2].markdown("**Odd**")

    for i, bet in enumerate(pf_bets):
        bc1, bc2, bc3, bc4 = st.columns([3, 2, 2, 1])
        bet["label"] = bc1.text_input("", value=bet["label"], key=f"pf_lab_{i}",
                                       label_visibility="collapsed")
        bet["ev"]    = bc2.number_input("", min_value=0.1, max_value=100.0,
                                         value=float(bet["ev"]), step=0.5,
                                         key=f"pf_ev_{i}", label_visibility="collapsed",
                                         format="%.1f")
        bet["odd"]   = bc3.number_input("", min_value=1.01, max_value=50.0,
                                          value=float(bet["odd"]), step=0.01,
                                          key=f"pf_odd_{i}", label_visibility="collapsed",
                                          format="%.3f")
        if bc4.button("🗑️", key=f"pf_del_{i}") and len(pf_bets) > 1:
            pf_bets.pop(i)
            st.rerun()

    if st.button("➕ Adicionar aposta ao portfólio"):
        pf_bets.append({"ev": 5.0, "odd": 2.0, "label": f"Aposta {len(pf_bets)+1}"})
        st.rerun()

    if st.button("📊 Calcular Kelly Portfólio", type="primary"):
        # Kelly bruto por aposta
        kellys_raw = []
        for bet in pf_bets:
            ev_dec = bet["ev"] / 100
            odd    = max(bet["odd"], 1.001)
            k      = ev_dec / (odd - 1)
            kellys_raw.append(max(k, 0))

        total_kelly = sum(kellys_raw)
        max_alloc   = pf_frac / 100

        # Escala para não passar do limite
        if total_kelly > max_alloc:
            scale = max_alloc / total_kelly
        else:
            scale = 1.0

        rows = []
        for bet, k_raw in zip(pf_bets, kellys_raw):
            k_adj   = k_raw * scale
            stake_r = pf_bank * k_adj
            rows.append({
                "Aposta":          bet["label"],
                "Odd":             round(bet["odd"], 3),
                "EV (%)":          round(bet["ev"], 1),
                "Kelly bruto (%)": round(k_raw * 100, 2),
                "Kelly ajustado (%)": round(k_adj * 100, 2),
                "Stake (R$)":      round(stake_r, 2),
            })

        import pandas as pd
        df_pf = pd.DataFrame(rows)

        st.dataframe(df_pf, width='stretch', hide_index=True,
            column_config={
                "Odd":                st.column_config.NumberColumn(format="%.3f"),
                "EV (%)":             st.column_config.NumberColumn(format="%.1f%%"),
                "Kelly bruto (%)":    st.column_config.NumberColumn(format="%.2f%%"),
                "Kelly ajustado (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Stake (R$)":         st.column_config.NumberColumn(format="R$ %.2f"),
            })

        total_stake = sum(r["Stake (R$)"] for r in rows)
        exp_lucro   = sum(r["Stake (R$)"] * r["EV (%)"] / 100 for r in rows)
        kp1, kp2, kp3 = st.columns(3)
        kp1.metric("Total alocado",  f"R$ {total_stake:.2f}",
                   help=f"{total_stake/pf_bank*100:.1f}% do bankroll")
        kp2.metric("% do bankroll",  f"{total_stake/pf_bank*100:.1f}%")
        kp3.metric("Lucro esperado", f"R$ {exp_lucro:+.2f}")

        if scale < 1.0:
            st.info(
                f"⚠️ Kelly bruto total era **{total_kelly*100:.1f}%** — maior que o limite de {pf_frac}%. "
                f"Stakes reduzidas proporcionalmente (fator {scale:.2f}×)."
            )
