"""EV Finder — Tab: Analytics de Performance"""
import calendar as _cal
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bankroll_history import (
    analise_evolucao, delete_snapshot, load_history, serie_diaria, _parse_dt,
)
from bet_tracker import calc_stats, load_bets

# Paleta categórica validada (CVD-safe, ordem fixa — cor segue a entidade)
_COR_TOTAL = "#2a78d6"
_COR_CASA  = {
    "Superbet": "#1baf7a",
    "Bet365":   "#eda100",
    "Betano":   "#008300",
}
_COR_FALLBACK = "#898781"


def _render_evolucao_banca(bets: list[dict]) -> None:
    st.subheader("🏦 Evolução da Banca")

    history = load_history()
    if not history:
        st.info(
            "Sem histórico ainda. Cada **💾 Salvar bancas** na barra lateral "
            "registra um snapshot — a partir do 2º registro você vê aqui a "
            "evolução, quanto veio de lucro e quanto foi depósito."
        )
        return

    analise = analise_evolucao(history, bets)

    if analise is None:
        st.caption(
            f"1 registro salvo ({history[0]['data']} — R$ {history[0]['total']:,.2f}). "
            "Salve de novo quando a banca mudar para ver a evolução."
        )
        _render_calendario_banca(history)
        return

    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Banca atual", f"R$ {analise['banca_atual']:,.2f}",
              delta=f"{analise['crescimento_pct']:+.1f}%"
                    if analise["crescimento_pct"] is not None else None)
    e2.metric("Variação total", f"R$ {analise['variacao']:+,.2f}",
              help=f"Desde o 1º registro em {analise['desde']} "
                   f"(R$ {analise['banca_inicial']:,.2f}).")
    e3.metric("Lucro em apostas", f"R$ {analise['lucro_apostas']:+,.2f}",
              help=f"{analise['n_resolvidas']} aposta(s) resolvida(s) no Tracker "
                   "dentro do período do histórico.")
    e4.metric("Depósitos/saques", f"R$ {analise['depositos_liquidos']:+,.2f}",
              help="Variação da banca menos o lucro das apostas = dinheiro que "
                   "entrou ou saiu por fora (depósitos, saques, bônus).")
    e5.metric("ROI sobre a banca", f"{analise['roi_banca']:+.2f}%"
              if analise["roi_banca"] is not None else "—",
              help="Lucro das apostas ÷ banca inicial do período. Diferente do "
                   "ROI sobre valor apostado mostrado abaixo.")

    _dep = analise["depositos_liquidos"]
    if abs(_dep) >= 0.01:
        _verbo = "depositou" if _dep > 0 else "sacou"
        st.caption(
            f"Do total de **R$ {analise['variacao']:+,.2f}** de variação, "
            f"**R$ {analise['lucro_apostas']:+,.2f}** veio das apostas registradas "
            f"e você {_verbo} **R$ {abs(_dep):,.2f}** por fora. O ROI acima "
            "considera só o lucro das apostas — depósito não é lucro."
        )

    # ── Gráfico de evolução ───────────────────────────────────────────────────
    datas  = [_parse_dt(h["data"]) or h["data"] for h in history]
    totais = [h["total"] for h in history]
    casas  = sorted({c for h in history for c in h["bankrolls"]})

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=datas, y=totais,
        mode="lines+markers", line=dict(width=2.5, color=_COR_TOTAL, shape="hv"),
        marker=dict(size=8), name="Total",
        hovertemplate="%{x|%d/%m %H:%M}<br>Total: R$ %{y:,.2f}<extra></extra>",
    ))
    for casa in casas:
        vals = [h["bankrolls"].get(casa) for h in history]
        if not any(v for v in vals if v):
            continue
        fig.add_trace(go.Scatter(
            x=datas, y=vals,
            mode="lines+markers",
            line=dict(width=1.5, color=_COR_CASA.get(casa, _COR_FALLBACK), shape="hv"),
            marker=dict(size=6), name=casa,
            hovertemplate=f"{casa}: R$ %{{y:,.2f}}<extra></extra>",
        ))
    fig.update_layout(
        height=340,
        margin=dict(l=0, r=0, t=10, b=0),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
        yaxis_title="Saldo (R$)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#e1e0d9"),
        yaxis=dict(gridcolor="#e1e0d9"),
    )
    st.plotly_chart(fig, width='stretch')

    _render_calendario_banca(history)

    # ── Tabela do histórico ───────────────────────────────────────────────────
    with st.expander(f"📜 Registros do histórico ({len(history)})"):
        rows = []
        prev_total = None
        for h in history:
            row = {"Data": h["data"]}
            for casa in casas:
                row[casa] = h["bankrolls"].get(casa, 0.0)
            row["Total"]   = h["total"]
            row["Δ Total"] = round(h["total"] - prev_total, 2) if prev_total is not None else None
            prev_total = h["total"]
            rows.append(row)
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, width='stretch',
            column_config={
                **{c: st.column_config.NumberColumn(format="R$ %.2f") for c in casas},
                "Total":   st.column_config.NumberColumn(format="R$ %.2f"),
                "Δ Total": st.column_config.NumberColumn(format="R$ %+.2f"),
            },
        )
        if st.button("🗑️ Apagar último registro", key="bh_del_last",
                     help="Use se salvou por engano. Apaga só o registro mais recente."):
            delete_snapshot(history[-1]["id"])
            st.rerun()


_MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
_DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _render_calendario_banca(history: list[dict]) -> None:
    """Calendário mensal: valor total da banca em cada dia (forward-fill),
    célula colorida pela variação do dia (verde subiu / vermelho caiu)."""
    st.markdown("#### 📅 Calendário da banca")

    serie = serie_diaria(history)
    if not serie:
        return

    meses  = sorted({(d.year, d.month) for d in serie})
    labels = [f"{_MESES_PT[m - 1]} {y}" for y, m in meses]

    sc1, sc2, sc3 = st.columns([4, 4, 4])
    sel = sc1.selectbox("Mês", labels, index=len(labels) - 1, key="bh_cal_mes")
    ano, mes = meses[labels.index(sel)]

    n_dias      = _cal.monthrange(ano, mes)[1]
    primeiro_wd = date(ano, mes, 1).weekday()  # 0 = segunda
    n_semanas   = (primeiro_wd + n_dias + 6) // 7

    # Métricas do mês
    dias_mes  = [d for d in serie if d.year == ano and d.month == mes]
    fim_mes   = serie[max(dias_mes)]
    vespera   = date(ano, mes, 1) - timedelta(days=1)
    base_mes  = serie.get(vespera, serie[min(dias_mes)])
    var_mes   = round(fim_mes - base_mes, 2)
    sc2.metric("Banca no fim do mês", f"R$ {fim_mes:,.2f}")
    sc3.metric("Variação no mês", f"R$ {var_mes:+,.2f}",
               delta=f"{var_mes / base_mes * 100:+.1f}%" if base_mes > 0 else None)

    # Grade do calendário
    z       = [[None] * 7 for _ in range(n_semanas)]
    customs = [[["", 0.0, 0.0]] * 7 for _ in range(n_semanas)]
    customs = [[list(c) for c in row] for row in customs]
    annotations = []

    for dia in range(1, n_dias + 1):
        d   = date(ano, mes, dia)
        idx = primeiro_wd + dia - 1
        row, col = idx // 7, idx % 7

        # número do dia (canto superior esquerdo, sempre visível)
        annotations.append(dict(
            x=_DIAS_SEMANA[col], y=row, xref="x", yref="y",
            text=str(dia), showarrow=False,
            xshift=-30, yshift=24,
            font=dict(size=10, color="#898781"),
        ))

        total = serie.get(d)
        if total is None:
            continue
        ant   = serie.get(d - timedelta(days=1))
        delta = round(total - ant, 2) if ant is not None else 0.0
        z[row][col]       = delta
        customs[row][col] = [d.strftime("%d/%m/%Y"), total, delta]
        annotations.append(dict(
            x=_DIAS_SEMANA[col], y=row, xref="x", yref="y",
            text=f"<b>R$ {total:,.0f}</b>"
                 + (f"<br><span style='font-size:9px'>{delta:+,.0f}</span>"
                    if abs(delta) >= 0.01 else ""),
            showarrow=False,
            font=dict(size=11, color="#212529"),
        ))

    max_abs = max((abs(v) for r in z for v in r if v is not None), default=0) or 1.0

    fig = go.Figure(go.Heatmap(
        z=z, x=_DIAS_SEMANA, y=list(range(n_semanas)),
        customdata=customs,
        hovertemplate="%{customdata[0]}<br>Total: R$ %{customdata[1]:,.2f}"
                      "<br>Δ dia: R$ %{customdata[2]:+,.2f}<extra></extra>",
        colorscale=[[0.0, "#e8909a"], [0.5, "#f0efec"], [1.0, "#8fce9f"]],
        zmin=-max_abs, zmax=max_abs,
        xgap=3, ygap=3,
        showscale=False, hoverongaps=False,
    ))
    fig.update_xaxes(side="top", showgrid=False, zeroline=False, fixedrange=True,
                     tickfont=dict(size=11, color="#898781"))
    fig.update_yaxes(autorange="reversed", visible=False, fixedrange=True)
    fig.update_layout(
        height=60 + 76 * n_semanas,
        margin=dict(l=0, r=0, t=30, b=0),
        annotations=annotations,
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})

    st.caption(
        "Cada célula mostra o total da banca no dia (verde = dia positivo, "
        "vermelho = negativo, cinza = sem mudança). Dias sem registro herdam "
        "o último valor salvo — salve as bancas com frequência para o "
        "calendário ficar fiel."
    )


def render(cfg: dict) -> None:
    st.subheader("📊 Analytics de Performance")

    bets     = load_bets()
    resolved = [b for b in bets if b["resultado"] in ("ganhou", "perdeu")]

    _render_evolucao_banca(bets)
    st.divider()

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
