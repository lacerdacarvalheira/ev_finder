"""EV Finder — Tab: Watchlist de Odds Alvo"""
import streamlit as st

from watchlist import add_watch, check_hits, load_watchlist, remove_watch


def render(cfg: dict) -> None:
    st.subheader("👁️ Watchlist de Odds")
    st.caption(
        "Registre uma seleção e a odd mínima desejada. "
        "A cada busca, o sistema avisa se essa odd foi encontrada no mercado."
    )

    # ─── Alertas ativos ───────────────────────────────────────────────────────
    all_opps = st.session_state.get("results", [])
    if all_opps:
        hits = check_hits(all_opps)
        if hits:
            st.error(f"🎯 **{len(hits)} alvo(s) atingido(s) na última busca!**")
            for h in hits:
                opp = h["opp"]
                with st.container(border=True):
                    hc1, hc2, hc3 = st.columns([3, 2, 2])
                    hc1.markdown(f"**{h['selecao']}** — {h['jogo']}")
                    hc1.caption(f"{h['mercado']} @ {opp.get('Casa','?')}")
                    hc2.metric("Odd encontrada", f"{opp.get('Odd Casa', 0):.3f}",
                               delta=f"+{opp.get('Odd Casa',0) - h['odd_alvo']:.3f} acima do alvo")
                    hc3.metric("EV", f"+{opp.get('EV (%)', 0):.1f}%")

                    if st.button("➕ Registrar aposta", key=f"wl_reg_{h['id']}"):
                        st.session_state["pending_bet"] = {
                            "jogo":      opp.get("Jogo", ""),
                            "mercado":   opp.get("Mercado", ""),
                            "selecao":   opp.get("Seleção", ""),
                            "odd":       opp.get("Odd Casa", 2.0),
                            "stake":     round(cfg["bankroll"] * opp.get("Kelly bruto (%)", 2) / 100 * cfg["kelly_frac"], 2),
                            "ev_pct":    opp.get("EV (%)", 0),
                            "prob_real": opp.get("Prob. Real (%)", 50),
                            "casa":      opp.get("Casa", ""),
                        }
                        st.toast("Aposta copiada! Vá para a aba 📋 Tracker.", icon="📋")
        else:
            st.success("✅ Nenhum alvo da watchlist atingido na última busca.")

    st.divider()

    # ─── Adicionar alvo ───────────────────────────────────────────────────────
    with st.expander("➕ Adicionar à watchlist", expanded=True):
        with st.form("form_watchlist", clear_on_submit=True):
            wc1, wc2 = st.columns(2)
            w_jogo    = wc1.text_input("Jogo (opcional)", placeholder="ex: Brasil vs França")
            w_selecao = wc2.text_input("Seleção *", placeholder="ex: Brasil, Over 2.5, Sim")
            wc3, wc4 = st.columns(2)
            w_mercado  = wc3.text_input("Mercado", placeholder="ex: Resultado Final (1X2)")
            w_odd_alvo = wc4.number_input("Odd alvo mínima", min_value=1.01,
                                           value=2.0, step=0.01, format="%.3f")

            if st.form_submit_button("👁️ Adicionar alerta", type="primary"):
                if w_selecao.strip():
                    add_watch(w_jogo.strip(), w_mercado.strip(),
                              w_selecao.strip(), w_odd_alvo)
                    st.toast(f"Alerta para '{w_selecao}' @ {w_odd_alvo:.3f} adicionado!", icon="👁️")
                    st.rerun()
                else:
                    st.warning("Preencha pelo menos a Seleção.")

    st.divider()

    # ─── Lista de alertas ─────────────────────────────────────────────────────
    items = load_watchlist()
    if not items:
        st.caption("Nenhum alerta configurado. Adicione acima.")
        return

    st.subheader(f"📋 Alertas configurados ({len(items)})")
    for item in reversed(items):
        with st.container(border=True):
            ic1, ic2, ic3 = st.columns([4, 2, 1])
            with ic1:
                st.markdown(f"**{item['selecao']}**")
                parts = [item.get("jogo",""), item.get("mercado","")]
                desc  = "  •  ".join(p for p in parts if p)
                if desc:
                    st.caption(desc)
                st.caption(f"Adicionado em {item['criado']}")
            with ic2:
                st.metric("Odd alvo", f"{item['odd_alvo']:.3f}")
            with ic3:
                if st.button("🗑️", key=f"wl_del_{item['id']}",
                             help="Remover alerta"):
                    remove_watch(item["id"])
                    st.rerun()
