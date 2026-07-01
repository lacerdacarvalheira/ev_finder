"""EV Finder — Tab: Analytics de Performance"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bet_tracker import calc_stats, load_bets


def render(cfg: dict) -> None:
    st.subheader("📊 Analytics de Performance")

    bets     = load_bets()
    resolved = [b for b in bets if b["resultado"] in ("ganhou", "perdeu")]

    if len(resolved) < 3:
        st.info(
            "Registre e resolva pelo menos **3 apostas** para ver os analytics.\n\n"
            "Os gráficos mostram calibração de EV, ROI acumulado e análise de CLV."
        )
        return

    stats = calc_stats(bets)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Apostas resolvidas", stats["resolvidas"])
    c2.metric("ROI real",           f"{stats['roi']:+.1f}%",
              delta=f"{stats['roi']:+.1f}%")
    c3.metric("Taxa de acerto",     f"{stats['taxa_acerto']:.1f}%")
    c4.metric("Lucro total",        f"R$ {stats['lucro_total']:+,.2f}")
    c5.metric("CLV médio",
              f"{stats['clv_medio']:+.2f}%" if stats["clv_medio"] is not None else "—",
              help="CLV positivo = você bate a linha de fechamento sistematicamente (edge real).")

    st.divider()

    # ─── Calibração de EV ─────────────────────────────────────────────────────
    st.subheader("🎯 Calibração de EV")
    st.caption(
        "Taxa de acerto real por faixa de EV vs esperado pela Pinnacle. "
        "Barras verdes acima das azuis = você está capturando edge real."
    )

    ev_buckets = [
        (0,  3,  "1–3%"),
        (3,  5,  "3–5%"),
        (5,  10, "5–10%"),
        (10, 15, "10–15%"),
        (15, 100,"15%+"),
    ]
    calib_rows = []
    for lo, hi, label in ev_buckets:
        bucket = [b for b in resolved if lo <= (b.get("ev_pct") or 0) < hi]
        if not bucket:
            continue
        n_win     = sum(1 for b in bucket if b["resultado"] == "ganhou")
        win_real  = n_win / len(bucket) * 100
        win_exp   = sum(b.get("prob_real") or 50 for b in bucket) / len(bucket)
        total_st  = sum(b.get("stake") or 0 for b in bucket)
        roi       = sum(b.get("lucro") or 0 for b in bucket) / total_st * 100 if total_st > 0 else 0
        calib_rows.append({
            "Faixa EV": label,
            "Apostas":  len(bucket),
            "Acerto real (%)":     round(win_real, 1),
            "Acerto esperado (%)": round(win_exp, 1),
            "Diferença (pp)":      round(win_real - win_exp, 1),
            "ROI (%)":             round(roi, 1),
        })

    if calib_rows:
        fig_cal = go.Figure()
        lbls    = [r["Faixa EV"] for r in calib_rows]
        fig_cal.add_trace(go.Bar(
            name="Acerto real", x=lbls,
            y=[r["Acerto real (%)"] for r in calib_rows],
            marker_color="#28a745",
        ))
        fig_cal.add_trace(go.Bar(
            name="Esperado (Pinnacle)", x=lbls,
            y=[r["Acerto esperado (%)"] for r in calib_rows],
            marker_color="#0d6efd", opacity=0.6,
        ))
        fig_cal.update_layout(
            barmode="group", yaxis_title="Taxa de acerto (%)",
            height=300,
            legend=dict(orientation="h", yanchor="bottom", y=1.01),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_cal, width='stretch')

        def _diff_bg(v):
            if v > 2:  return "background-color:#c3e6cb;color:#155724"
            if v < -2: return "background-color:#f5c6cb;color:#721c24"
            return ""

        def _roi_bg(v):
            if v > 0:  return "background-color:#c3e6cb;color:#155724"
            if v < 0:  return "background-color:#f5c6cb;color:#721c24"
            return ""

        st.dataframe(
            pd.DataFrame(calib_rows)
              .style.map(_diff_bg, subset=["Diferença (pp)"])
              .map(_roi_bg,  subset=["ROI (%)"]),
            width='stretch', hide_index=True,
            column_config={
                "Acerto real (%)":     st.column_config.NumberColumn(format="%.1f%%"),
                "Acerto esperado (%)": st.column_config.NumberColumn(format="%.1f%%"),
                "Diferença (pp)":      st.column_config.NumberColumn(format="%+.1f"),
                "ROI (%)":             st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )

    st.divider()

    # ─── ROI cumulativo ────────────────────────────────────────────────────────
    st.subheader("📈 ROI Cumulativo")

    running_l = 0.0
    running_a = 0.0
    roi_curve = []
    for b in resolved:
        running_l += b.get("lucro") or 0
        running_a += b.get("stake") or 0
        roi_curve.append(running_l / running_a * 100 if running_a > 0 else 0)

    final_roi    = roi_curve[-1]
    line_color   = "#28a745" if final_roi >= 0 else "#dc3545"

    fig_roi = go.Figure()
    fig_roi.add_trace(go.Scatter(
        x=list(range(1, len(roi_curve) + 1)),
        y=roi_curve,
        mode="lines+markers",
        line=dict(width=2, color=line_color),
        marker=dict(size=5),
        name="ROI cumulativo (%)",
        hovertemplate="Aposta %{x}<br>ROI: %{y:.1f}%<extra></extra>",
    ))
    fig_roi.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5)
    fig_roi.update_layout(
        xaxis_title="Apostas resolvidas",
        yaxis_title="ROI cumulativo (%)",
        height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig_roi, width='stretch')

    # ─── Bankroll real vs esperado ─────────────────────────────────────────────
    bankroll = cfg["bankroll"]
    bk_real  = [bankroll]
    bk_exp   = [bankroll]
    for b in resolved:
        bk_real.append(bk_real[-1] + (b.get("lucro") or 0))
        ev_frac = (b.get("ev_pct") or 0) / 100
        bk_exp.append(bk_exp[-1] * (1 + ev_frac * (b.get("stake") or 0) / max(bk_exp[-1], 1)))

    x_bk = list(range(len(bk_real)))
    fig_bk = go.Figure()
    fig_bk.add_trace(go.Scatter(x=x_bk, y=bk_real, mode="lines",
                                line=dict(width=2, color="#28a745"), name="Bankroll real"))
    fig_bk.add_trace(go.Scatter(x=x_bk, y=bk_exp, mode="lines",
                                line=dict(width=2, color="#0d6efd", dash="dash"), name="Esperado (EV)"))
    fig_bk.add_hline(y=bankroll, line_dash="dot", line_color="grey", opacity=0.4,
                     annotation_text="Bankroll inicial")
    fig_bk.update_layout(
        xaxis_title="Apostas resolvidas",
        yaxis_title="Bankroll (R$)",
        height=280,
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        margin=dict(l=0, r=0, t=30, b=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig_bk, width='stretch')

    # ─── CLV Analysis ─────────────────────────────────────────────────────────
    clv_bets = [b for b in resolved if b.get("clv") is not None]
    if len(clv_bets) >= 3:
        st.divider()
        _clv_t, _clv_h = st.columns([11, 1])
        _clv_t.subheader("🎲 Luck vs Skill — CLV Analysis")
        with _clv_h:
            from utils import help_icon
            help_icon("CLV (Closing Line Value)", key="analytics_clv_help")
        st.caption(
            "**CLV positivo** = você apostou antes que as odds caíssem → edge real, não sorte.  \n"
            "Se o ROI é positivo mas o CLV é negativo, pode ser variância favorável — cuidado."
        )

        clv_vals   = [b["clv"] for b in clv_bets]
        mean_clv   = sum(clv_vals) / len(clv_vals)
        pos_count  = sum(1 for v in clv_vals if v > 0)

        fig_clv = go.Figure()
        fig_clv.add_trace(go.Bar(
            x=list(range(1, len(clv_vals) + 1)),
            y=clv_vals,
            marker_color=["#28a745" if v >= 0 else "#dc3545" for v in clv_vals],
            name="CLV por aposta (%)",
        ))
        fig_clv.add_hline(y=0, line_dash="dash", line_color="grey")
        fig_clv.add_hline(y=mean_clv, line_dash="dot", line_color="#0d6efd",
                          annotation_text=f"Média: {mean_clv:+.2f}%",
                          annotation_position="right")
        fig_clv.update_layout(
            xaxis_title="Apostas com CLV registrado",
            yaxis_title="CLV (%)",
            height=260,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_clv, width='stretch')

        col_l, col_r = st.columns(2)
        col_l.metric("CLV médio",                f"{mean_clv:+.2f}%")
        col_r.metric("Apostas com CLV positivo", f"{pos_count}/{len(clv_vals)} ({pos_count/len(clv_vals)*100:.0f}%)")

        if mean_clv > 1:
            st.success("✅ CLV médio positivo — evidência de edge real na escolha de timing.")
        elif mean_clv < -1:
            st.warning("⚠️ CLV médio negativo — você costuma apostar tarde (odds já caíram).")
        else:
            st.info("CLV próximo de zero — timing neutro.")

    st.divider()
    st.caption(
        "Analytics calculados sobre apostas resolvidas no Tracker. "
        "Mínimo 10+ apostas para calibração confiável."
    )
