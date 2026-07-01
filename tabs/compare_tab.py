"""EV Finder — Tab: Comparativo de Odds"""
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from line_cache import get_line_history
from odds_api import MARKET_OPTIONS
from utils import remove_vig


def render(cfg: dict) -> None:
    all_events = st.session_state.get("all_events", [])

    if not all_events:
        st.info("Faça uma busca primeiro para carregar os jogos.")
        return

    game_labels  = [f"{e['home_team']} vs {e['away_team']}" for e in all_events]
    selected_game = st.selectbox("Selecione o jogo", game_labels)
    event = all_events[game_labels.index(selected_game)]

    market_key = st.selectbox(
        "Mercado",
        options=[k for k in MARKET_OPTIONS if k in
                 {m["key"] for b in event.get("bookmakers", []) for m in b.get("markets", [])}],
        format_func=lambda k: MARKET_OPTIONS[k],
    )

    bookmakers    = event.get("bookmakers", [])
    outcomes_set: list[str] = []
    bookie_data: dict[str, dict[str, float]] = {}

    for bk in bookmakers:
        bk_name = bk.get("title", bk["key"])
        for mkt in bk.get("markets", []):
            if mkt["key"] != market_key:
                continue
            bookie_data[bk_name] = {}
            for o in mkt["outcomes"]:
                label = o["name"]
                if "point" in o:
                    label = f"{o['name']} {o['point']}"
                if label not in outcomes_set:
                    outcomes_set.append(label)
                bookie_data[bk_name][label] = o["price"]

    if not bookie_data:
        st.warning("Nenhuma odd disponível para este jogo/mercado.")
        return

    pin_data = bookie_data.get("Pinnacle", {})
    pin_fair: dict[str, float] = {}
    if pin_data:
        names      = list(pin_data.keys())
        fair_probs = remove_vig(list(pin_data.values()))
        pin_fair   = {n: round(1 / p, 3) for n, p in zip(names, fair_probs)}

    rows = []
    for outcome in outcomes_set:
        row: dict = {"Resultado": outcome}
        if outcome in pin_fair:
            row["Pinnacle (fair)"] = pin_fair[outcome]
        for bk_name, odds in bookie_data.items():
            row[bk_name] = odds.get(outcome, None)
        rows.append(row)

    comp_df    = pd.DataFrame(rows).set_index("Resultado")
    bookie_cols = [c for c in comp_df.columns if c != "Pinnacle (fair)"]

    def highlight_best(row):
        styles = [""] * len(row)
        vals   = [(i, v) for i, v in enumerate(row) if v is not None and row.index[i] in bookie_cols]
        if vals:
            best_i = max(vals, key=lambda x: x[1])[0]
            styles[best_i] = "background-color:#28a745;color:white;font-weight:bold"
        if "Pinnacle (fair)" in row.index:
            styles[list(row.index).index("Pinnacle (fair)")] = "background-color:#0d6efd;color:white"
        return styles

    styled_comp = comp_df.style.apply(highlight_best, axis=1).format("{:.3f}", na_rep="—")

    st.subheader(f"📊 {selected_game} — {MARKET_OPTIONS.get(market_key, market_key)}")
    st.dataframe(styled_comp, use_container_width=True)
    st.caption(
        "🟦 **Azul** = Odd justa Pinnacle (sem vig). "
        "🟩 **Verde** = Melhor odd disponível. "
        "Verde > Azul = valor esperado positivo."
    )

    # Movimento de linha
    st.divider()
    st.subheader("📉 Movimento de Linha")
    game_id   = event.get("id", "")
    history   = get_line_history(game_id) if game_id else {}
    snapshots = history.get("snapshots", [])

    if len(snapshots) < 2:
        st.caption(
            "Histórico insuficiente. O movimento de linha é construído a cada busca — "
            "faça buscas ao longo do tempo para ver como as odds evoluem."
        )
    else:
        outcome_series: dict[str, list] = {}
        for snap in snapshots:
            ts_raw = snap.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_raw)
            except Exception:
                continue
            pin_mkts = snap.get("odds", {}).get("pinnacle", {})
            for o in pin_mkts.get(market_key, []):
                name = o["name"]
                if name not in outcome_series:
                    outcome_series[name] = []
                outcome_series[name].append((ts, o["price"]))

        if outcome_series:
            fig_lm = go.Figure()
            for name, series in outcome_series.items():
                xs = [p[0] for p in series]
                ys = [p[1] for p in series]
                fig_lm.add_trace(go.Scatter(
                    x=xs, y=ys,
                    mode="lines+markers",
                    name=name,
                    line=dict(width=2),
                    marker=dict(size=6),
                ))
            fig_lm.update_layout(
                xaxis_title="Horário (UTC)",
                yaxis_title="Odd Pinnacle",
                height=280,
                legend=dict(orientation="h", yanchor="bottom", y=1.01),
                margin=dict(l=0, r=0, t=30, b=0),
                hovermode="x unified",
            )
            st.plotly_chart(fig_lm, use_container_width=True)
            st.caption(f"Fonte: Pinnacle | {len(snapshots)} pontos de dados coletados")
        else:
            st.caption("Sem dados da Pinnacle para este mercado no histórico.")
