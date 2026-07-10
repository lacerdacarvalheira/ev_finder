"""EV Finder — Tab: Tracker de Apostas"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bet_tracker import (
    add_bet, calc_stats, calc_stats_by, congelado, delete_bet, load_bets,
    update_result,
)
from config_store import mover_saldo_ui
from utils import (
    lucro_em_unidades, movimento_delete, movimento_resultado, unit_value,
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

    _uval  = unit_value(cfg.get("bankroll") or 0, cfg.get("unit_pct", 1.0))
    _units = lucro_em_unidades(lucro, _uval)
    if _units is not None:
        st.markdown(
            f"{'🟢' if _units >= 0 else '🔴'} Resultado em unidades: "
            f"**{_units:+.2f}u** &nbsp;·&nbsp; 1u = R$ {_uval:,.2f} "
            f"({cfg.get('unit_pct', 1.0):g}% da banca total)"
        )

    _cong = congelado(bets)
    _cong_total = round(sum(_cong.values()), 2)
    if _cong_total > 0:
        _cong_det = " · ".join(f"{c}: R$ {v:,.2f}" for c, v in _cong.items())
        st.markdown(
            f"🧊 Congelado em {stats['pendentes']} pendente(s): "
            f"**R$ {_cong_total:,.2f}** ({_cong_det})"
        )

    st.divider()

    pending = st.session_state.get("pending_bet", {})
    _casas_cfg = list((cfg.get("bankrolls") or {}).keys())
    with st.expander("➕ Registrar nova aposta", expanded=bool(pending)):
        with st.form("form_bet", clear_on_submit=True):
            fc1, fc2, fc3 = st.columns(3)
            stake = fc1.number_input("Valor apostado (R$)", min_value=0.01,
                                     value=float(pending.get("stake", 10.0)),
                                     step=1.0, format="%.2f")
            _casa_pend = pending.get("casa", "")
            _opcoes    = _casas_cfg + ["Outra…"]
            _idx       = _opcoes.index(_casa_pend) if _casa_pend in _opcoes else 0
            casa_sel = fc2.selectbox(
                "Casa de aposta", _opcoes, index=_idx,
                help="Nas casas das suas bancas, o valor é descontado do saldo "
                     "e fica congelado até você marcar o resultado.",
            )
            odd = fc3.number_input("Odd", min_value=1.01,
                                   value=float(pending.get("odd", 2.0)),
                                   step=0.01, format="%.3f")
            jogo = st.text_input(
                "Descrição (opcional)", value=pending.get("jogo", ""),
                placeholder="Ex.: França vence a Espanha",
                help="Para você achar a aposta depois. Vazio = data e hora.",
            )
            casa_outra = st.text_input("Nome da casa (só se escolheu 'Outra…')",
                                       value="" if _casa_pend in _opcoes else _casa_pend)

            submitted = st.form_submit_button("💾 Registrar aposta", type="primary")
            if submitted:
                casa = casa_outra.strip() if casa_sel == "Outra…" else casa_sel
                if not casa:
                    st.warning("Escolha a casa de aposta (ou preencha o nome em 'Outra…').")
                else:
                    from datetime import datetime as _dt
                    _desc = jogo.strip() or f"Aposta {_dt.now():%d/%m %H:%M}"
                    novo_saldo = mover_saldo_ui(casa, -stake)
                    add_bet(
                        _desc, pending.get("mercado", ""),
                        pending.get("selecao") or "—", odd, stake,
                        float(pending.get("ev_pct", 0.0)),
                        float(pending.get("prob_real", 50.0)),
                        casa, tipo_rec=pending.get("tipo_rec") or ("EV+" if pending else "Manual"),
                        debitado=novo_saldo is not None,
                    )
                    st.session_state.pop("pending_bet", None)
                    if novo_saldo is not None:
                        st.toast(
                            f"Aposta registrada! 🧊 R$ {stake:,.2f} congelado — "
                            f"saldo {casa}: R$ {novo_saldo:,.2f}", icon="✅",
                        )
                    else:
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
                    if bet.get("debitado"):
                        _mov  = movimento_resultado("pendente", "ganhou", bet["stake"], bet["odd"])
                        _novo = mover_saldo_ui(bet["casa"], _mov)
                        if _novo is not None:
                            st.toast(f"+R$ {_mov:,.2f} de volta no saldo da "
                                     f"{bet['casa']} (R$ {_novo:,.2f})", icon="💰")
                    st.rerun()
                if br2.button("❌ Perdeu", key=f"lose_{real_idx}"):
                    update_result(real_idx, "perdeu", odd_close if odd_close > 1.0 else None)
                    # stake já saiu do saldo no registro — perdeu não devolve nada
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
                if bet.get("debitado"):
                    _mov = movimento_delete(res, bet["stake"], bet["odd"])
                    mover_saldo_ui(bet["casa"], _mov)
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
        st.plotly_chart(fig_pnl, width='stretch')

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
                width='stretch',
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
        width='stretch',
    )
