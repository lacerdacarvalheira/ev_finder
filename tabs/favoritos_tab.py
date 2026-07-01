"""
EV Finder — Tab: Modo Favoritos

Lista diária de favoritos de odd baixa em que a melhor odd do mercado paga
pelo menos a probabilidade justa (EV >= ev_floor via line shopping).

O que este modo NÃO faz:
- Não promete crescimento diário — mostra a distribuição de resultados.
- Não usa Kelly (variância de Kelly com prob estimada é desnecessária aqui).
- Não sugere múltiplas com 3+ pernas (máximo dupla).
- Não inclui mercados de nicho como referência de prob justa.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bet_tracker import add_bet
from game_analyst import favoritos_do_dia, pior_sequencia_esperada
from utils import help_icon


def render(cfg: dict) -> None:
    bankroll = cfg["bankroll"]
    selected_bookmaker_keys = cfg.get("selected_bookmaker_keys") or None

    tcol, hcol1, hcol2 = st.columns([10, 1, 1])
    tcol.subheader("⭐ Modo Favoritos")
    with hcol1:
        help_icon("Probabilidade justa")
    with hcol2:
        help_icon("Line shopping")

    st.info(
        "Favoritos de odd baixa não são lucro garantido. Este modo só lista "
        "seleções em que a melhor odd do mercado paga a probabilidade justa ou "
        "mais (EV ≥ 0). Ainda assim, sequências de derrota são estatisticamente "
        "normais — veja o Painel de Risco abaixo."
    )

    with st.expander("ℹ️ Como funciona"):
        st.markdown(
            "1. A probabilidade justa vem do 3-way da Pinnacle, devigado pelo "
            "*power method* (corrige o viés que subestima favoritos).\n"
            "2. Empate Anula e Dupla Chance são **derivados** do 3-way — o mercado "
            "mais líquido — em vez de devigados separadamente.\n"
            "3. A seleção só entra na lista se a **melhor odd** entre as casas "
            "selecionadas pagar pelo menos a odd justa (line shopping ⇒ EV ≥ 0).\n\n"
            "**O que este modo NÃO faz:**\n"
            "- Não promete crescimento diário — mostra a distribuição de resultados.\n"
            "- Não usa Kelly — stake fixa é mais robusta a erros de estimativa aqui.\n"
            "- Não sugere múltiplas com 3+ pernas.\n"
            "- Não usa mercados de nicho como referência de probabilidade."
        )

    if "all_events" not in st.session_state or not st.session_state["all_events"]:
        st.info("Faça uma busca na barra lateral primeiro para carregar os jogos.")
        return

    all_events = st.session_state["all_events"]

    # ── Filtros ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([4, 4, 4])
    with fc1:
        pcol, picol = st.columns([8, 1])
        min_prob = pcol.slider("Prob. justa mínima (%)", 50, 90, 65, key="fav_min_prob")
        with picol:
            help_icon("Probabilidade justa", key="fav_prob_help")
    ev_floor = fc2.slider("Tolerância de EV (%)", -2.0, 5.0, 0.0, step=0.5,
                           key="fav_ev_floor",
                           help="0 = odd precisa pagar pelo menos a justa. "
                                "Negativo aceita pagar um pouco de vig.")
    stake_pct = fc3.slider("% da banca por aposta (flat)", 0.5, 5.0, 2.0, step=0.5,
                            key="fav_stake_pct")

    stake_valor = round(bankroll * stake_pct / 100, 2)

    favoritos = favoritos_do_dia(
        all_events,
        min_prob=min_prob / 100,
        ev_floor=ev_floor / 100,
        bookmaker_filter=selected_bookmaker_keys,
    )

    if not favoritos:
        st.warning(
            f"Nenhum favorito com prob ≥ {min_prob}% em que a melhor odd pague "
            f"a probabilidade justa (EV ≥ {ev_floor:+.1f}%). Isso é normal — "
            "mercados eficientes raramente pagam odd justa em favoritos. "
            "Tente reduzir a prob mínima ou aceitar uma tolerância de EV negativa."
        )
        _painel_risco([], min_prob / 100, stake_pct / 100, bankroll)
        return

    st.success(f"✅ **{len(favoritos)} seleção(ões)** passaram em todos os critérios.")

    df = pd.DataFrame(favoritos)
    display_cols = ["Jogo", "Seleção", "Mercado", "Prob. justa (%)", "Odd justa",
                    "Melhor odd", "Casa", "EV (%)", "Horário (BRT)"]

    from utils import GLOSSARY
    st.dataframe(
        df[display_cols],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Prob. justa (%)": st.column_config.NumberColumn(
                format="%.1f%%", help=GLOSSARY["Probabilidade justa"]),
            "Odd justa":  st.column_config.NumberColumn(format="%.3f"),
            "Melhor odd": st.column_config.NumberColumn(
                format="%.3f", help=GLOSSARY["Line shopping"]),
            "EV (%)":     st.column_config.NumberColumn(
                format="%+.2f%%", help=GLOSSARY["EV (Valor Esperado)"]),
        },
    )

    # ── Registro com um clique ────────────────────────────────────────────────
    st.markdown(f"**Stake flat:** {stake_pct:.1f}% da banca = **R$ {stake_valor:.2f}** por aposta")
    for i, f in enumerate(favoritos):
        rc1, rc2 = st.columns([8, 2])
        rc1.markdown(
            f"{f['Horário (BRT)']} — **{f['Seleção']}** ({f['Mercado']}) "
            f"@ {f['Melhor odd']:.3f} na {f['Casa']} · "
            f"prob {f['Prob. justa (%)']:.1f}% · EV {f['EV (%)']:+.2f}%"
        )
        if rc2.button("➕ Registrar", key=f"fav_reg_{i}"):
            add_bet(
                jogo=f["Jogo"], mercado=f["Mercado"], selecao=f["Seleção"],
                odd=f["Melhor odd"], stake=stake_valor,
                ev_pct=f["EV (%)"], prob_real=f["Prob. justa (%)"],
                casa=f["Casa"], tipo_rec="favoritos",
            )
            st.toast(f"Aposta registrada (modo favoritos): {f['Seleção']}", icon="⭐")

    # ── Dupla do dia ──────────────────────────────────────────────────────────
    _melhores_por_jogo: dict = {}
    for f in favoritos:
        eid = f["event_id"]
        if eid not in _melhores_por_jogo or f["EV (%)"] > _melhores_por_jogo[eid]["EV (%)"]:
            _melhores_por_jogo[eid] = f

    distintos = sorted(_melhores_por_jogo.values(), key=lambda x: x["EV (%)"], reverse=True)
    if len(distintos) >= 2:
        d1, d2 = distintos[0], distintos[1]
        p1 = d1["Prob. justa (%)"] / 100
        p2 = d2["Prob. justa (%)"] / 100
        prob_comb = p1 * p2
        odd_comb  = d1["Melhor odd"] * d2["Melhor odd"]
        ev_comb   = prob_comb * odd_comb - 1
        with st.expander("🤝 Dupla do dia (2 melhores de jogos diferentes)"):
            dc1, dc2 = st.columns([10, 1])
            dc1.markdown(
                f"- **{d1['Seleção']}** ({d1['Jogo']}) @ {d1['Melhor odd']:.3f} — "
                f"prob {d1['Prob. justa (%)']:.1f}%\n"
                f"- **{d2['Seleção']}** ({d2['Jogo']}) @ {d2['Melhor odd']:.3f} — "
                f"prob {d2['Prob. justa (%)']:.1f}%\n\n"
                f"**Odd combinada:** {odd_comb:.3f}× · "
                f"**Prob. de bater:** {prob_comb*100:.1f}% · "
                f"**EV:** {ev_comb*100:+.2f}%"
            )
            with dc2:
                help_icon("EV (Valor Esperado)", key="fav_dupla_ev")
            st.caption(
                "⚠️ A probabilidade combinada assume independência entre os jogos. "
                "Máximo dupla neste modo — triplas ou mais multiplicam a variância."
            )

    st.divider()
    _painel_risco(favoritos, min_prob / 100, stake_pct / 100, bankroll)


# ─── Painel de Risco ──────────────────────────────────────────────────────────

def _painel_risco(favoritos: list[dict], p_piso: float,
                  stake_frac: float, bankroll: float) -> None:
    rt, rh1, rh2 = st.columns([10, 1, 1])
    rt.subheader("🛡️ Painel de Risco")
    with rh1:
        help_icon("Drawdown", key="fav_dd_help")
    with rh2:
        help_icon("Sequência de derrotas", key="fav_seq_help")

    if favoritos:
        p_media   = sum(f["Prob. justa (%)"] for f in favoritos) / len(favoritos) / 100
        odd_media = sum(f["Melhor odd"] for f in favoritos) / len(favoritos)
    else:
        p_media   = p_piso
        odd_media = 1.0 / p_piso  # odd justa do piso como proxy

    reds_por_20   = 20 * (1 - p_media)
    greens_por_red = 1.0 / (odd_media - 1) if odd_media > 1.001 else float("inf")
    pior_seq      = pior_sequencia_esperada(p_media, 100)

    m1, m2, m3 = st.columns(3)
    m1.metric("Reds esperados",
              f"~{reds_por_20:.0f} a cada 20 apostas",
              help=f"Com prob média de {p_media*100:.0f}% por aposta.")
    m2.metric("Custo de 1 red",
              f"~{greens_por_red:.1f} greens",
              help=f"1 derrota @ odd média {odd_media:.2f} apaga o lucro de "
                   f"~{greens_por_red:.1f} vitórias do mesmo stake.")
    m3.metric("Pior sequência provável",
              f"~{pior_seq} derrotas seguidas",
              help="Em 100 apostas, uma sequência desse tamanho é esperada — "
                   "não é azar anormal.")

    st.caption(
        f"Com prob média de **{p_media*100:.0f}%** por aposta, espere "
        f"**~{reds_por_20:.0f} derrotas a cada 20 apostas**. "
        f"1 derrota @ odd média {odd_media:.2f} apaga o lucro de "
        f"**~{greens_por_red:.1f} greens** do mesmo stake. "
        f"Em 100 apostas, uma sequência de **~{pior_seq} derrotas seguidas** "
        "é esperada, não é azar anormal."
    )

    # ── Simulador de 30 dias (Monte Carlo) ────────────────────────────────────
    st.markdown("#### 📆 Simulador de 30 dias")
    sc1, sc2 = st.columns(2)
    apostas_dia = sc1.number_input("Apostas por dia", min_value=1, max_value=10,
                                    value=2, key="fav_bets_day")
    n_sims = sc2.selectbox("Simulações", [1_000, 5_000, 10_000], index=2,
                            key="fav_n_sims")

    if st.button("▶️ Simular 30 dias", key="fav_sim_btn"):
        n_bets = 30 * int(apostas_dia)
        stake  = bankroll * stake_frac
        rng    = np.random.default_rng(7)

        wins    = rng.random((n_sims, n_bets)) < p_media
        profits = np.where(wins, stake * (odd_media - 1), -stake)
        finais  = bankroll + profits.sum(axis=1)

        p5, p25, p50, p75, p95 = np.percentile(finais, [5, 25, 50, 75, 95])
        prob_vermelho = float(np.mean(finais < bankroll)) * 100

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=finais,
            nbinsx=60,
            marker=dict(color="#0d6efd", line=dict(color="#ffffff", width=1)),
            name="Saldo final",
            hovertemplate="Saldo: R$ %{x:,.0f}<br>Simulações: %{y}<extra></extra>",
        ))
        for px, lbl in [(p5, "P5"), (p25, "P25"), (p50, "Mediana"),
                        (p75, "P75"), (p95, "P95")]:
            fig.add_vline(x=px, line_dash="dash", line_color="#6c757d", line_width=1,
                          annotation_text=f"{lbl}: R${px:,.0f}",
                          annotation_position="top",
                          annotation_font_size=10,
                          annotation_font_color="#495057")
        fig.add_vline(x=bankroll, line_dash="dot", line_color="#212529", line_width=2,
                      annotation_text="Banca inicial",
                      annotation_position="bottom right",
                      annotation_font_color="#212529")
        fig.update_layout(
            title=f"Distribuição do saldo após 30 dias ({n_sims:,} simulações)",
            xaxis_title="Saldo final (R$)",
            yaxis_title="Nº de simulações",
            showlegend=False,
            height=420,
            margin=dict(l=0, r=0, t=80, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#e9ecef"),
            yaxis=dict(gridcolor="#e9ecef"),
        )
        st.plotly_chart(fig, use_container_width=True)

        r1, r2, r3 = st.columns(3)
        r1.metric("Mediana", f"R$ {p50:,.0f}",
                  delta=f"{(p50/bankroll - 1)*100:+.1f}%")
        r2.metric("Cenário ruim realista (P5)", f"R$ {p5:,.0f}",
                  delta=f"{(p5/bankroll - 1)*100:+.1f}%", delta_color="inverse")
        r3.metric("Prob. de terminar no vermelho", f"{prob_vermelho:.0f}%")

        st.caption(
            f"Parâmetros: {apostas_dia} aposta(s)/dia × 30 dias, prob média "
            f"{p_media*100:.0f}%, odd média {odd_media:.2f}, stake flat "
            f"R$ {stake:.2f} ({stake_frac*100:.1f}% da banca). "
            "A distribuição mostra o intervalo realista — não só a média."
        )
