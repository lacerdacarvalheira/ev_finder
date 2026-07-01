"""EV Finder — Tab: Tracker de Apostas"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bet_tracker import (
    add_bet, calc_stats, calc_stats_by, delete_bet, load_bets, update_result,
)


def render(cfg: dict) -> None:
    st.subheader("📋 Tracker de Apostas")

    bets  = load_bets()
    stats = calc_stats(bets)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total apostas",  stats["total"])
    m2.metric("Taxa de acerto", f"{stats['taxa_acerto']:.1f}%")
    m3.metric("Total apostado", f"R$ {stats['total_apostado']:,.2f}")
    lucro = stats["lucro_total"]
    m4.metric("Lucro/Prejuízo", f"R$ {lucro:+,.2f}", delta=f"{lucro:+.2f}")
    roi_val = stats["roi"]
    m5.metric("ROI real",       f"{roi_val:+.1f}%", delta=f"{roi_val:+.1f}%")
    clv_val = stats["clv_medio"]
    m6.metric(
        "CLV médio",
        f"{clv_val:+.2f}%" if clv_val is not None else "—",
        help="Closing Line Value médio. Positivo = você bate a linha de fechamento sistematicamente.",
    )

    st.divider()

    pending = st.session_state.get("pending_bet", {})
    with st.expander("➕ Registrar nova aposta", expanded=bool(pending)):
        with st.form("form_bet", clear_on_submit=True):
            fc1, fc2 = st.columns(2)
            jogo    = fc1.text_input("Jogo",    value=pending.get("jogo", ""))
            casa    = fc2.text_input("Casa",    value=pending.get("casa", ""))
            fc3, fc4 = st.columns(2)
            mercado = fc3.text_input("Mercado", value=pending.get("mercado", ""))
            selecao = fc4.text_input("Seleção", value=pending.get("selecao", ""))
            fc5, fc6, fc7, fc8 = st.columns(4)
            odd    = fc5.number_input("Odd",           min_value=1.01, value=float(pending.get("odd",      2.0)),  step=0.01, format="%.3f")
            stake  = fc6.number_input("Stake (R$)",    min_value=0.01, value=float(pending.get("stake",   10.0)),  step=1.0,  format="%.2f")
            ev_pct = fc7.number_input("EV (%)",        min_value=0.0,  value=float(pending.get("ev_pct",   0.0)),  step=0.1,  format="%.2f")
            prob_r = fc8.number_input("Prob. Real (%)", min_value=0.0, value=float(pending.get("prob_real", 50.0)), step=0.5,  format="%.1f")

            tipo_rec = st.selectbox(
                "Tipo de recomendação",
                ["—", "EV+", "🛡️ Segura", "💡 Valor", "⚡ Sharp", "🔗 Combo", "Manual"],
                index=0,
                help="Classifica a origem desta aposta para análise de desempenho por tipo.",
            )

            submitted = st.form_submit_button("💾 Salvar aposta", type="primary")
            if submitted and jogo and selecao:
                _tipo = None if tipo_rec == "—" else tipo_rec
                add_bet(jogo, mercado, selecao, odd, stake, ev_pct, prob_r, casa, tipo_rec=_tipo)
                st.session_state.pop("pending_bet", None)
                st.toast("Aposta registrada!", icon="✅")
                st.rerun()

    st.divider()

    if not bets:
        st.info("Nenhuma aposta registrada ainda. Use o formulário ou clique em ➕ na aba EV+.")
        return

    st.subheader(f"Histórico ({len(bets)} apostas)")

    for i, bet in enumerate(reversed(bets)):
        real_idx  = len(bets) - 1 - i
        res       = bet["resultado"]
        icon      = {"ganhou": "✅", "perdeu": "❌", "pendente": "⏳"}.get(res, "❓")
        lucro_str = f"R$ {bet['lucro']:+.2f}" if bet["lucro"] is not None else "—"
        clv_str   = f"CLV: {bet['clv']:+.2f}%" if bet.get("clv") is not None else ""

        with st.expander(
            f"{icon} {bet['data']} | {bet['jogo']} | {bet['selecao']} @ {bet['odd']:.3f} | "
            f"Stake: R$ {bet['stake']:.2f} | {lucro_str}  {clv_str}"
        ):
            bc1, bc2, bc3, bc4 = st.columns(4)
            bc1.write(f"**Casa:** {bet['casa']}")
            bc2.write(f"**Mercado:** {bet['mercado']}")
            bc3.write(f"**EV na entrada:** +{bet['ev_pct']:.2f}%")
            bc4.write(f"**Prob. real:** {bet['prob_real']:.1f}%")

            if res == "pendente":
                st.markdown("**Marcar resultado:**")
                br1, br2, br3 = st.columns([1, 1, 2])
                odd_close = br3.number_input(
                    "Odd fechamento (CLV)",
                    min_value=0.0, max_value=100.0,
                    value=0.0, step=0.01, format="%.3f",
                    key=f"close_{real_idx}",
                    help="Odd da Pinnacle no fechamento do mercado. Calcula o CLV automaticamente.",
                )
                if br1.button("✅ Ganhou", key=f"win_{real_idx}"):
                    update_result(real_idx, "ganhou", odd_close if odd_close > 1.0 else None)
                    st.rerun()
                if br2.button("❌ Perdeu", key=f"lose_{real_idx}"):
                    update_result(real_idx, "perdeu", odd_close if odd_close > 1.0 else None)
                    st.rerun()
            else:
                if bet.get("odd_fechamento"):
                    st.caption(
                        f"Odd entrada: {bet['odd']:.3f} | "
                        f"Odd fechamento: {bet['odd_fechamento']:.3f} | "
                        f"CLV: {bet['clv']:+.2f}%"
                        if bet.get("clv") is not None else
                        f"Odd entrada: {bet['odd']:.3f} | "
                        f"Odd fechamento: {bet['odd_fechamento']:.3f}"
                    )

            if st.button("🗑️ Deletar", key=f"del_{real_idx}"):
                delete_bet(real_idx)
                st.rerun()

    # P&L cumulativo
    resolved_bets = [b for b in bets if b["resultado"] in ("ganhou", "perdeu")]
    if len(resolved_bets) >= 2:
        st.divider()
        st.subheader("📈 P&L Cumulativo")
        lucros_cum = pd.Series([b["lucro"] for b in resolved_bets]).cumsum()
        colors_pnl = ["green" if v >= 0 else "red" for v in lucros_cum]
        fig_pnl = go.Figure()
        fig_pnl.add_trace(go.Scatter(
            y=lucros_cum, mode="lines+markers",
            line=dict(width=2, color="green"),
            marker=dict(color=colors_pnl, size=7),
            name="P&L cumulativo",
        ))
        fig_pnl.add_hline(y=0, line_dash="dash", line_color="grey")
        fig_pnl.update_layout(
            xaxis_title="Apostas resolvidas",
            yaxis_title="P&L (R$)",
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_pnl, use_container_width=True)

    # ROI por segmento
    if resolved_bets:
        st.divider()
        st.subheader("📊 ROI por Segmento")
        seg_tab1, seg_tab2 = st.tabs(["Por Mercado", "Por Casa"])

        def _render_segment_table(rows: list[dict], col_name: str):
            if not rows:
                st.caption("Sem dados resolvidos ainda.")
                return
            df_seg = pd.DataFrame(rows)

            def _roi_bg(val):
                if val > 0: return "background-color:#c3e6cb;color:#155724"
                if val < 0: return "background-color:#f5c6cb;color:#721c24"
                return ""

            st.dataframe(
                df_seg.style.map(_roi_bg, subset=["ROI (%)"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ROI (%)":       st.column_config.NumberColumn(format="%.1f%%"),
                    "Acerto (%)":    st.column_config.NumberColumn(format="%.1f%%"),
                    "Apostado (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Lucro (R$)":    st.column_config.NumberColumn(format="R$ %.2f"),
                },
            )

        with seg_tab1:
            _render_segment_table(calc_stats_by(bets, "mercado"), "Mercado")
        with seg_tab2:
            _render_segment_table(calc_stats_by(bets, "casa"), "Casa")

    # Backtest por tipo de recomendação
    has_tipo = any(b.get("tipo_rec") for b in resolved_bets) if resolved_bets else False
    if has_tipo:
        st.divider()
        st.subheader("🎯 Desempenho por Tipo de Recomendação")
        st.caption("Mostra a eficácia de cada tipo de recomendação — útil para calibrar o que confiar mais.")
        _render_segment_table(calc_stats_by(resolved_bets, "tipo_rec"), "Tipo_rec")

    st.divider()
    csv_bytes = pd.DataFrame(bets).to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Exportar apostas (CSV)",
        data=csv_bytes,
        file_name="apostas.csv",
        mime="text/csv",
        use_container_width=True,
    )
