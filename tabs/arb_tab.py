"""EV Finder — Tab: Arbitragem"""
import pandas as pd
import streamlit as st

from arb_finder import find_arbs, stakes_for_bankroll
from odds_api import MARKET_OPTIONS, OddsAPIClient, OddsAPIError


def render(cfg: dict) -> None:
    api_key             = cfg["api_key"]
    bankroll            = cfg["bankroll"]
    selected_league_keys = cfg["selected_league_keys"]

    st.subheader("⚡ Arbitragem (Surebet)")
    st.caption(
        "Encontra oportunidades onde a soma das probabilidades implícitas das melhores odds "
        "entre todas as casas é **menor que 100%** — garantindo lucro independente do resultado."
    )

    col_arb1, col_arb2, col_arb3 = st.columns([2, 2, 2])
    with col_arb1:
        arb_min_profit = st.number_input(
            "Lucro mínimo (%)", min_value=0.0, max_value=10.0, value=0.0, step=0.05,
            help="0% mostra tudo, inclusive quasi-arbs. Arb real começa em ~0.2%.",
        )
    with col_arb2:
        arb_stake = st.number_input(
            "Total a investir (R$)", min_value=10.0, value=float(bankroll), step=50.0,
            help="O sistema calcula quanto apostar em cada casa para garantir o lucro.",
        )
    with col_arb3:
        arb_source = st.radio(
            "Fonte dos dados",
            ["Reusar busca EV+", "Nova busca (consome quota)"],
            help="'Reusar' usa os dados já carregados — grátis. 'Nova busca' garante dados frescos.",
        )

    arb_search_btn = st.button(
        "⚡ Buscar Arbitragens",
        type="primary",
        width='stretch',
        disabled=not api_key,
    )

    if not api_key:
        st.warning("Configure sua chave da API na barra lateral para usar esta aba.")

    arb_results_key = "arb_results"
    arb_diag_key    = "arb_diag"

    if arb_search_btn:
        with st.spinner("Analisando odds em todas as casas..."):
            try:
                if arb_source == "Reusar busca EV+" and st.session_state.get("all_events"):
                    _arb_events = st.session_state["all_events"]
                    _from_cache_label = "dados da busca EV+ (sem nova requisição)"
                    _skipped: list[str] = []
                else:
                    _arb_client  = OddsAPIClient(api_key)
                    _arb_events  = []
                    _arb_markets = list(MARKET_OPTIONS.keys())
                    _skipped     = []

                    for sport_key in selected_league_keys:
                        _evs = _arb_client.get_odds(sport_key, _arb_markets, use_cache=False)
                        _arb_events.extend(_evs)
                        _skipped.extend(getattr(_arb_client, "skipped_markets", []))

                    st.session_state["quota_remaining"] = _arb_client.requests_remaining
                    _from_cache_label = "nova busca ao vivo"

                n_events  = len(_arb_events)
                n_bk_set  = set()
                n_mkt_set = set()
                for _ev in _arb_events:
                    for _bk in _ev.get("bookmakers", []):
                        n_bk_set.add(_bk["key"])
                        for _mk in _bk.get("markets", []):
                            n_mkt_set.add(_mk["key"])

                st.session_state[arb_diag_key] = {
                    "eventos":     n_events,
                    "casas":       len(n_bk_set),
                    "mercados":    len(n_mkt_set),
                    "fonte":       _from_cache_label,
                    "casas_lista": sorted(n_bk_set),
                    "skipped":     list(set(_skipped)),
                }
                st.session_state[arb_results_key] = find_arbs(_arb_events, min_profit=0.0)

            except OddsAPIError as e:
                st.error(str(e))

    arb_list = st.session_state.get(arb_results_key, [])
    arb_diag = st.session_state.get(arb_diag_key)

    if arb_diag:
        with st.expander("🔍 Diagnóstico da última busca", expanded=arb_diag["eventos"] == 0):
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("Jogos carregados", arb_diag["eventos"])
            dc2.metric("Casas com odds",   arb_diag["casas"])
            dc3.metric("Mercados cobertos", arb_diag["mercados"])
            st.caption(f"Fonte: {arb_diag['fonte']}")
            if arb_diag["casas_lista"]:
                st.caption(f"Casas: {', '.join(arb_diag['casas_lista'])}")
            if arb_diag["skipped"]:
                st.caption(f"Mercados ignorados: {', '.join(arb_diag['skipped'])}")
            if arb_diag["eventos"] == 0:
                st.warning("Nenhum jogo encontrado. Verifique se há jogos disponíveis na liga selecionada.")
            elif arb_diag["casas"] < 3:
                st.warning(
                    f"Apenas {arb_diag['casas']} casa(s) — arbs são raros com poucas casas. "
                    "O plano gratuito da API tem cobertura limitada de bookmakers."
                )

    filtered_arb_list = [a for a in arb_list if a["Lucro (%)"] >= arb_min_profit]

    if not arb_diag:
        st.info(
            "Clique em **⚡ Buscar Arbitragens** para escanear as odds.\n\n"
            "**Dica:** Arbs reais geralmente têm 0.2%–1.5% de lucro. "
            "Acima de 3% quase sempre é erro de dados — confira sempre no site antes de apostar."
        )
    elif not filtered_arb_list:
        st.warning(
            f"Nenhuma arbitragem encontrada ({len(arb_list)} combinações analisadas). "
            "Isso é normal — mercados eficientes raramente têm arbs. "
            "Tente 0.0% no filtro para ver todas as combinações."
        )
    else:
        n_total    = len(filtered_arb_list)
        best_arb   = filtered_arb_list[0]
        avg_profit = sum(a["Lucro (%)"] for a in filtered_arb_list) / n_total
        n_juicy    = sum(1 for a in filtered_arb_list if a["Lucro (%)"] >= 1.0)

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Arbs encontradas", n_total)
        mc2.metric("Melhor lucro",     f"{best_arb['Lucro (%)']:.3f}%")
        mc3.metric("Lucro médio",      f"{avg_profit:.3f}%")
        mc4.metric("Acima de 1%",      n_juicy)

        st.divider()

        arb_filter = st.slider(
            "Filtrar por lucro mínimo (%)",
            min_value=0.0,
            max_value=max(5.0, best_arb["Lucro (%)"] + 0.5),
            value=float(arb_min_profit), step=0.05,
            key="arb_filter_slider",
        )
        displayed_arbs = [a for a in filtered_arb_list if a["Lucro (%)"] >= arb_filter]
        st.caption(f"Exibindo **{len(displayed_arbs)}** de {n_total} oportunidades.")

        for arb in displayed_arbs:
            profit  = arb["Lucro (%)"]
            lucro_r = round(arb_stake * profit / 100, 2)
            badge   = "🔴" if profit >= 2.0 else ("🟠" if profit >= 1.0 else ("🟡" if profit >= 0.5 else "🟢"))

            with st.container(border=True):
                hc1, hc2, hc3 = st.columns([4, 2, 2])
                with hc1:
                    st.markdown(f"**{arb['Jogo']}**")
                    st.caption(f"{arb['Liga']}  •  {arb['Horário (BRT)']}  •  {arb['Mercado']}")
                with hc2:
                    st.metric(f"{badge} Lucro garantido", f"{profit:.3f}%")
                with hc3:
                    st.metric("Lucro em R$", f"R$ {lucro_r:.2f}")

                stake_rows = stakes_for_bankroll(arb, arb_stake)
                df_stakes  = pd.DataFrame([{
                    "Seleção":      o["nome"],
                    "Casa":         o["casa"],
                    "Odd":          o["odds"],
                    "Apostar (R$)": o["stake_r"],
                    "Retorno (R$)": o["retorno_r"],
                    "% do total":   o["stake_pct"],
                } for o in stake_rows])
                st.dataframe(
                    df_stakes, width='stretch', hide_index=True,
                    column_config={
                        "Odd":          st.column_config.NumberColumn(format="%.3f"),
                        "Apostar (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                        "Retorno (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                        "% do total":   st.column_config.NumberColumn(format="%.2f%%"),
                    },
                )
                casas_list = list({o["casa"] for o in arb["Outcomes"]})
                if len(casas_list) == 1:
                    st.warning(
                        f"⚠️ Todas as odds são da mesma casa ({casas_list[0]}) — pode ser erro de dados."
                    )

                if arb.get("correlated_warning"):
                    st.warning(f"⚠️ **Correlação detectada:** {arb['correlated_warning']}")

        st.divider()
        st.caption(
            "⚠️ Arbs fecham em minutos. Execute as apostas simultaneamente. "
            "Casas detectam arbitradores e podem limitar sua conta. "
            "Confirme as odds no site antes de apostar."
        )
