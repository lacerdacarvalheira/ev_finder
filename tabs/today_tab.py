"""EV Finder — Tab: Jogos de Hoje"""
import time as _time
from datetime import datetime

import pandas as pd
import streamlit as st

from game_analyst import analyze_game, get_today_events, recommend_bets
from line_cache import get_line_history
from live_data import (
    fetch_game_detail, fetch_scoreboard, fetch_standings,
    find_espn_event, format_team_record, get_team_standings,
)
from utils import BRT as _BRT, hours_until, urgency_badge


def render(cfg: dict) -> None:
    bankroll   = cfg["bankroll"]
    kelly_frac = cfg["kelly_frac"]

    all_events_today = st.session_state.get("all_events", [])

    if not all_events_today:
        st.info(
            "### 👈 Busque primeiro\n\n"
            "Clique em **🔍 Buscar Oportunidades** na barra lateral para carregar os jogos. "
            "Esta aba mostra automaticamente os jogos que acontecem **hoje** com análise completa."
        )
        return

    today_events = get_today_events(all_events_today)
    all_opps_now = st.session_state.get("results", [])
    today_brt    = datetime.now(_BRT)

    st.subheader(f"📅 Jogos de Hoje — {today_brt.strftime('%d/%m/%Y')}")

    if not today_events:
        st.warning(
            "Nenhum jogo encontrado para hoje nas ligas selecionadas. "
            "Verifique se selecionou as ligas corretas na barra lateral."
        )
        return

    st.success(f"**{len(today_events)} jogo(s)** acontecendo hoje nas ligas selecionadas.")
    st.caption(
        "Análise baseada em probabilidades reais da Pinnacle (sharp book), "
        "melhores odds disponíveis e movimento de linha. Atualiza a cada busca."
    )

    # Ordenar por horário
    _REC_ORDER = {"strong": 0, "value": 1, "value_small": 2, "watch": 3, "neutral": 4}
    sort_today = st.radio(
        "Ordenar por",
        ["Horário", "Melhor oportunidade"],
        horizontal=True,
    )

    # Carrega standings uma vez para todos os jogos (cache de 1h)
    _standings = fetch_standings()

    analyses = []
    for ev in today_events:
        gid     = ev.get("id", "")
        history = get_line_history(gid) if gid else {}
        result  = analyze_game(ev, all_opps_now, history)
        analyses.append((ev, result))

    if sort_today == "Melhor oportunidade":
        analyses.sort(key=lambda x: _REC_ORDER.get(x[1]["recommendation"], 9))

    for ev, ana in analyses:
        home   = ev.get("home_team", "?")
        away   = ev.get("away_team", "?")
        league = ev.get("sport_title", "")
        ct_raw = ev.get("commence_time", "")
        hours  = hours_until(ct_raw)
        urgency = urgency_badge(hours)

        # Cor do card pela recomendação
        _rec_colors = {
            "strong":      "🔥",
            "value":       "💚",
            "value_small": "🟡",
            "watch":       "👀",
            "neutral":     "⚪",
        }
        rec_icon = _rec_colors.get(ana["recommendation"], "⚪")

        with st.container(border=True):
            # Cabeçalho do jogo
            h1, h2 = st.columns([4, 1])
            with h1:
                st.markdown(f"### {rec_icon} {home} vs {away}")
                # Record do torneio (ESPN standings)
                _home_rec = get_team_standings(home, _standings)
                _away_rec = get_team_standings(away, _standings)
                if _home_rec or _away_rec:
                    st.caption(
                        f"{league}  •  {urgency}  •  "
                        f"**{home}:** {format_team_record(_home_rec)}  "
                        f"|  **{away}:** {format_team_record(_away_rec)}"
                    )
                else:
                    st.caption(f"{league}  •  {urgency}")
            with h2:
                if hours is not None and hours >= 0:
                    try:
                        dt = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
                        kick = dt.astimezone(_BRT).strftime("%H:%M BRT")
                    except Exception:
                        kick = "—"
                    st.metric("Início", kick)

            # Probabilidades
            probs = ana["probs"]
            if probs:
                st.markdown("**Probabilidades reais (Pinnacle, sem vig):**")
                prob_cols = st.columns(len(probs))
                sorted_outcomes = sorted(
                    probs.items(),
                    key=lambda x: (x[0] != home, x[0] == "Draw"),
                )
                for col, (name, pdata) in zip(prob_cols, sorted_outcomes):
                    col.metric(
                        label=name if name != "Draw" else "Empate",
                        value=f"{pdata['prob']:.1f}%",
                        help=f"Odd justa: {pdata['fair_odd']:.3f}",
                    )
                st.divider()

            # Tabela de melhores odds
            best_h2h = ana["best_h2h"]
            best_tot = ana["best_totals"]

            # ── Tabela de melhores odds (1X2 + O/U) ─────────────────────
            if best_h2h or best_tot:
                st.markdown("**🎯 Melhores odds — Resultado (1X2) e Total de Gols:**")

                def _ev_str(ev_val):
                    if ev_val is None:    return "—"
                    if ev_val > 0:        return f"+{ev_val:.1f}% ✅"
                    return f"{ev_val:.1f}%"

                table_rows = []
                for name in [home, "Draw", away]:
                    info = best_h2h.get(name, {})
                    if not info:
                        continue
                    table_rows.append({
                        "Mercado": "1X2",
                        "Seleção": "Empate" if name == "Draw" else name,
                        "Melhor Odd": info.get("price"),
                        "Casa": info.get("bookmaker", "—"),
                        "Odd Justa": f"{info['fair_odd']:.3f}" if info.get("fair_odd") else "—",
                        "EV": _ev_str(info.get("ev")),
                    })
                for label, info in best_tot.items():
                    if not info:
                        continue
                    table_rows.append({
                        "Mercado": "O/U",
                        "Seleção": label,
                        "Melhor Odd": info.get("price"),
                        "Casa": info.get("bookmaker", "—"),
                        "Odd Justa": f"{info['fair_odd']:.3f}" if info.get("fair_odd") else "—",
                        "EV": _ev_str(info.get("ev")),
                    })

                if table_rows:
                    def _color_ev_cell(val):
                        if isinstance(val, str) and "✅" in val:
                            return "background-color:#c3e6cb;color:#155724;font-weight:bold"
                        if isinstance(val, str) and val.startswith("-"):
                            return "background-color:#f5c6cb;color:#721c24"
                        return ""
                    st.dataframe(
                        pd.DataFrame(table_rows).style.map(_color_ev_cell, subset=["EV"]),
                        width='stretch', hide_index=True,
                        column_config={"Melhor Odd": st.column_config.NumberColumn(format="%.3f")},
                    )

            # ── Outras oportunidades EV+ (todos os mercados) ─────────────
            ev_all_game = ana["ev_opps"]
            if ev_all_game:
                by_market: dict = {}
                for o in ev_all_game:
                    m = o["Mercado"]
                    if m not in by_market:
                        by_market[m] = []
                    by_market[m].append(o)

                mkt_tabs_labels = list(by_market.keys())[:6]
                if mkt_tabs_labels:
                    st.markdown("**💡 Todas as oportunidades EV+ neste jogo:**")
                    mkt_tabs = st.tabs(mkt_tabs_labels)
                    for tab_m, label_m in zip(mkt_tabs, mkt_tabs_labels):
                        with tab_m:
                            rows_m = by_market[label_m]
                            df_m = pd.DataFrame([{
                                "Seleção":    r["Seleção"],
                                "Casa":       r["Casa"],
                                "Odd":        r["Odd Casa"],
                                "Odd Justa":  r["Odd Pinnacle (fair)"],
                                "EV (%)":     r["EV (%)"],
                                "Prob. (%)":  r["Prob. Real (%)"],
                                "Kelly (%)":  round(r["Kelly bruto (%)"] * kelly_frac, 2),
                                "Apostar (R$)": round(bankroll * r["Kelly bruto (%)"] * kelly_frac / 100, 2),
                            } for r in rows_m])
                            def _ev_bg(v):
                                if v >= 10: return "background-color:#155724;color:white;font-weight:bold"
                                if v >= 5:  return "background-color:#28a745;color:white"
                                return "background-color:#c3e6cb;color:#155724"
                            st.dataframe(
                                df_m.style.map(_ev_bg, subset=["EV (%)"]),
                                width='stretch', hide_index=True,
                                column_config={
                                    "Odd":        st.column_config.NumberColumn(format="%.3f"),
                                    "Odd Justa":  st.column_config.NumberColumn(format="%.3f"),
                                    "EV (%)":     st.column_config.NumberColumn(format="%.2f%%"),
                                    "Apostar (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                                },
                            )

            # Análise textual
            st.divider()
            st.markdown("**📊 Análise:**")
            for line in ana["analysis_lines"]:
                st.markdown(f"- {line}")

            # Recomendação EV
            st.divider()
            rec = ana["recommendation"]
            if rec == "strong":
                st.error(ana["rec_text"])
            elif rec in ("value", "value_small"):
                st.success(ana["rec_text"])
            elif rec == "watch":
                st.warning(ana["rec_text"])
            else:
                st.info(ana["rec_text"])

            # ── Recomendações de apostas ──────────────────────────────────
            bet_recs = recommend_bets(ev, ana)
            if bet_recs:
                st.divider()
                st.markdown("### 🎯 Apostas Recomendadas")
                st.caption(
                    "Sugestões baseadas em probabilidades Pinnacle, mercado de gols, "
                    "linha afiada e padrões estatísticos. Não exige EV+ — foco em risco/retorno."
                )

                _conf_color = {"alta": "🟢", "media": "🟡", "baixa": "🔴"}
                _tipo_label = {
                    "segura": "🛡️ Segura",
                    "valor":  "💡 Valor",
                    "sharp":  "⚡ Sharp",
                    "combo":  "🔗 Combo",
                }

                for br in bet_recs:
                    conf_icon  = _conf_color.get(br["confianca"], "⚪")
                    tipo_label = _tipo_label.get(br["tipo"], br["tipo"])
                    ev_str     = (f"  •  EV **{br['ev_pct']:+.1f}%**" if br.get("ev_pct") is not None else "")
                    prob_str   = f"{br['prob_est']:.0f}%"

                    with st.container(border=True):
                        rc1, rc2, rc3, rc4 = st.columns([3, 2, 1, 1])
                        with rc1:
                            st.markdown(f"**{br['selecao']}**")
                            st.caption(f"{br['mercado']}  •  {tipo_label}")
                        with rc2:
                            st.caption("Melhor odd")
                            if br.get("ev_pct") and br["ev_pct"] > 0:
                                st.markdown(f"**:green[{br['best_odd']:.3f}]** @ {br['best_bookie']}")
                            else:
                                st.markdown(f"**{br['best_odd']:.3f}** @ {br['best_bookie']}")
                        with rc3:
                            st.metric("Prob.", prob_str)
                        with rc4:
                            st.metric(f"{conf_icon} Confiança", br["confianca"].capitalize())

                        st.markdown(f"*{br['motivo']}*{ev_str}")

                        if br["tipo"] == "combo":
                            apostar_combo = round(bankroll * kelly_frac * 0.25 / 100 * 100, 2)
                            st.caption(f"💰 Sugestão: apostar R$ {apostar_combo:.2f} (0.25% Kelly composto)")

            # ── Dados ao vivo / estatísticas ─────────────────────────────
            with st.expander("🔴 Dados ao vivo & estatísticas", expanded=False):
                _sb_key = "espn_scoreboard"
                if _sb_key not in st.session_state:
                    st.session_state[_sb_key] = None
                    st.session_state["espn_sb_ts"] = 0.0

                _sb_age = _time.time() - st.session_state.get("espn_sb_ts", 0)

                col_fetch, col_info = st.columns([1, 3])
                if col_fetch.button("🔄 Buscar", key=f"live_{ev.get('id','')}"):
                    with st.spinner("Buscando dados ESPN..."):
                        sb = fetch_scoreboard()
                        st.session_state[_sb_key] = sb
                        st.session_state["espn_sb_ts"] = _time.time()
                elif _sb_age < 120 and st.session_state[_sb_key] is not None:
                    sb = st.session_state[_sb_key]
                    col_info.caption(f"Dados de {int(_sb_age)}s atrás")
                else:
                    sb = None

                if sb is not None:
                    espn_ev = find_espn_event(home, away, sb)
                    if espn_ev:
                        # Placar e status
                        st.markdown("---")
                        sc1, sc2, sc3 = st.columns([2, 1, 2])
                        sc1.metric(espn_ev["home_team"], espn_ev["home_score"])
                        sc2.markdown(
                            f"<div style='text-align:center;padding-top:28px;font-size:18px;'>"
                            f"{'🔴 AO VIVO' if espn_ev['is_live'] else ('✅ FIM' if espn_ev['is_done'] else '⏳')}"
                            f"<br><small>{espn_ev.get('state_desc','')}</small></div>",
                            unsafe_allow_html=True,
                        )
                        sc3.metric(espn_ev["away_team"], espn_ev["away_score"])

                        # Detalhes (stats + gols)
                        detail = fetch_game_detail(espn_ev["espn_id"])

                        if detail.get("goals"):
                            st.markdown("**⚽ Gols:**")
                            for g in detail["goals"]:
                                scorer_str = f" — {g['scorer']}" if g["scorer"] else ""
                                assist_str = f" (assist: {g['assist']})" if g["assist"] else ""
                                st.markdown(
                                    f"&nbsp;&nbsp;`{g['clock']}`  {g['team']}{scorer_str}{assist_str}"
                                )

                        stats = detail.get("stats", {})
                        if stats:
                            st.markdown("**📊 Estatísticas:**")
                            team_names = list(stats.keys())
                            if len(team_names) >= 2:
                                t1, t2 = team_names[0], team_names[1]
                                s1_data, s2_data = stats[t1], stats[t2]
                                common_keys = [k for k in s1_data if k in s2_data]
                                priority = ["Posse de bola", "Finalizações",
                                            "Chutes a gol", "Escanteios",
                                            "Faltas", "Cartões amarelos"]
                                show_keys = [k for k in priority if k in common_keys] + \
                                            [k for k in common_keys if k not in priority]
                                show_keys = show_keys[:8]

                                stat_rows = [
                                    {"Estatística": k,
                                     t1: s1_data.get(k, "—"),
                                     t2: s2_data.get(k, "—")}
                                    for k in show_keys
                                ]
                                if stat_rows:
                                    st.dataframe(
                                        pd.DataFrame(stat_rows),
                                        width='stretch',
                                        hide_index=True,
                                    )

                        if detail.get("events"):
                            st.markdown("**📋 Eventos recentes:**")
                            for ev_item in detail["events"][-5:]:
                                st.caption(
                                    f"`{ev_item['clock']}` {ev_item['team']} — {ev_item['text']}"
                                )
                    else:
                        st.caption("Jogo não encontrado no ESPN. Pode ainda não estar indexado.")
                else:
                    st.caption(
                        "Clique em **🔄 Buscar** para carregar placar ao vivo, "
                        "gols e estatísticas via ESPN (gratuito, sem chave)."
                    )

            # ── Link rápido para registrar ────────────────────────────────
            ev_opps = ana["ev_opps"]
            if ev_opps:
                best_ev = ev_opps[0]
                if st.button(
                    f"➕ Registrar: {best_ev['Seleção']} @ {best_ev['Casa']} "
                    f"({best_ev['Odd Casa']:.3f})",
                    key=f"today_reg_{ev.get('id','')}",
                ):
                    kelly_b = best_ev["Kelly bruto (%)"] / 100
                    st.session_state["pending_bet"] = {
                        "jogo":      f"{home} vs {away}",
                        "mercado":   best_ev["Mercado"],
                        "selecao":   best_ev["Seleção"],
                        "odd":       best_ev["Odd Casa"],
                        "stake":     round(bankroll * kelly_b * kelly_frac, 2),
                        "ev_pct":    best_ev["EV (%)"],
                        "prob_real": best_ev["Prob. Real (%)"],
                        "casa":      best_ev["Casa"],
                    }
                    st.toast("Aposta copiada! Vá para a aba 📋 Tracker.", icon="📋")
