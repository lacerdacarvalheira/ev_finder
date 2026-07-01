"""EV Finder — Tab: Simulação de Variância (Monte Carlo)"""
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
