"""
EV Finder — Identificador de Apostas com Valor Esperado Positivo
Ferramenta pessoal e educacional — não para uso comercial.
"""
import json
import os
import time

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except ImportError:
    _HAS_AUTOREFRESH = False
    def st_autorefresh(*a, **kw): return 0  # noqa: E731

from tabs import arb_tab, compare_tab, ev_tab, sim_tab, today_tab, tracker_tab
from bet_tracker import calc_stats, load_bets
from ev_calculator import find_opportunities
from line_cache import get_cache_age, save_snapshot
from odds_api import MARKET_OPTIONS, SOCCER_LEAGUES, OddsAPIClient, OddsAPIError

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="EV Finder — Copa 2026",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


config = load_config()


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configurações")

    # — API Key —
    st.subheader("🔑 API Key")
    _env_key = os.environ.get("ODDS_API_KEY", "")
    api_key = st.text_input(
        "The Odds API Key",
        value=_env_key or config.get("api_key", ""),
        type="password",
        placeholder="Cole sua chave ou defina ODDS_API_KEY no ambiente...",
    )
    if st.button("💾 Salvar chave", use_container_width=True):
        save_config({**config, "api_key": api_key})
        st.toast("Chave salva!", icon="✅")

    st.divider()

    # — Bankroll & Kelly —
    st.subheader("💰 Bankroll & Kelly")
    bankroll = st.number_input(
        "Bankroll total (R$)",
        min_value=10.0, max_value=1_000_000.0,
        value=float(config.get("bankroll", 1000)),
        step=100.0,
    )
    if st.button("💾 Salvar bankroll", use_container_width=True):
        save_config({**config, "bankroll": bankroll})
        st.toast(f"Bankroll de R$ {bankroll:,.0f} salvo!", icon="✅")

    kelly_map = {
        "1/4 Kelly (conservador)": 0.25,
        "1/2 Kelly (moderado)":    0.5,
        "Kelly integral (agressivo)": 1.0,
    }
    kelly_label = st.selectbox("Fração Kelly", list(kelly_map.keys()), index=0)
    kelly_frac  = kelly_map[kelly_label]

    st.divider()

    # — Busca —
    st.subheader("🔍 Busca de Odds")
    league_names     = list(SOCCER_LEAGUES.values())
    default_leagues  = ["Copa do Mundo FIFA 2026"]
    selected_display = st.multiselect(
        "Ligas",
        options=league_names,
        default=[l for l in default_leagues if l in league_names],
        key="league_select_wc",
    )
    selected_league_keys = [k for k, v in SOCCER_LEAGUES.items() if v in selected_display]

    selected_market_keys = st.multiselect(
        "Mercados",
        options=list(MARKET_OPTIONS.keys()),
        default=["h2h", "totals", "spreads", "draw_no_bet", "btts", "doubleChance"],
        format_func=lambda k: MARKET_OPTIONS[k],
        help="Mercados não suportados são ignorados automaticamente.",
    )

    min_ev_pct = st.slider("EV mínimo (%)", min_value=1, max_value=30, value=3)

    odd_range = st.slider(
        "Intervalo de odds",
        min_value=1.01, max_value=20.0,
        value=(1.20, 6.0),
        step=0.05,
        format="%.2f",
    )

    search_btn = st.button(
        "🔍 Buscar Oportunidades",
        type="primary",
        use_container_width=True,
        disabled=not api_key,
    )

    if "quota_remaining" in st.session_state:
        rem = st.session_state["quota_remaining"]
        color = "🟢" if str(rem).isdigit() and int(rem) > 100 else "🔴"
        st.metric("Requisições restantes", f"{color} {rem}")
        if str(rem).isdigit() and int(rem) < 50:
            st.warning(f"⚠️ Só {rem} requisições restantes!")

    st.divider()

    # — Auto-refresh —
    st.subheader("🔄 Auto-refresh")
    auto_refresh = st.toggle(
        "Ativar auto-refresh",
        value=config.get("auto_refresh_enabled", False),
        help="Busca odds automaticamente em segundo plano.",
    )
    refresh_interval = 5
    _auto_count = 0

    if auto_refresh:
        refresh_interval = st.slider("Intervalo (min)", 1, 30,
                                     value=config.get("refresh_interval_min", 5))
        if _HAS_AUTOREFRESH:
            _auto_count = st_autorefresh(
                interval=refresh_interval * 60 * 1000,
                key="autorefresh_component",
            )
        else:
            st.caption("⚠️ Instale `streamlit-autorefresh` para usar esta função.")
        # Salva preferência
        if auto_refresh != config.get("auto_refresh_enabled") or \
                refresh_interval != config.get("refresh_interval_min"):
            save_config({**config,
                         "auto_refresh_enabled": auto_refresh,
                         "refresh_interval_min": refresh_interval})

    st.divider()

    # — Alertas —
    st.subheader("🚨 Alertas")
    alert_threshold = st.slider(
        "Alertar quando EV ≥ (%)",
        min_value=3, max_value=30, value=config.get("alert_threshold", 10),
        help="Exibe aviso visual e sonoro quando uma oportunidade ultrapassar este EV.",
    )
    sound_alerts = st.toggle("Alertas sonoros", value=config.get("sound_alerts", True))
    if alert_threshold != config.get("alert_threshold") or \
            sound_alerts != config.get("sound_alerts"):
        save_config({**config, "alert_threshold": alert_threshold, "sound_alerts": sound_alerts})

    st.divider()

    # — Telegram —
    st.subheader("📲 Telegram (opcional)")
    tg_token   = st.text_input(
        "Bot Token",
        value=config.get("telegram_token", ""),
        type="password",
        placeholder="123456789:AAF...",
        help="Obtenha em @BotFather. Deixe vazio para desativar.",
    )
    tg_chat_id = st.text_input(
        "Chat ID",
        value=config.get("telegram_chat_id", ""),
        placeholder="-100123456789",
        help="ID do seu chat ou grupo. Envie /start para o bot e acesse getUpdates.",
    )
    if st.button("💾 Salvar Telegram", use_container_width=True):
        save_config({**config, "telegram_token": tg_token, "telegram_chat_id": tg_chat_id})
        st.toast("Configuração Telegram salva!", icon="📲")


# ─── Auto-trigger logic ───────────────────────────────────────────────────────
_ar_prev = st.session_state.get("_ar_prev", -1)
_ar_fired = (
    auto_refresh and
    _auto_count > 0 and
    _auto_count != _ar_prev and
    bool(selected_league_keys) and
    bool(selected_market_keys) and
    bool(api_key)
)
st.session_state["_ar_prev"] = _auto_count

_do_search = search_btn or _ar_fired

# ─── Cabeçalho ───────────────────────────────────────────────────────────────
st.title("🏆 EV Finder — Copa do Mundo FIFA 2026")
st.warning(
    "**⚠️ Jogo Responsável:** Ferramenta educacional e pessoal. "
    "EV positivo é vantagem de **longo prazo** — apostas individuais têm variância. "
    "Aposte só o que pode perder. Ajuda: **188** (CVV).",
    icon="🎗️",
)

# ─── Dashboard rápido ─────────────────────────────────────────────────────────
_bets_all  = load_bets()
_stats_all = calc_stats(_bets_all)

d1, d2, d3, d4, d5 = st.columns(5)
d1.metric("Bankroll (R$)", f"{bankroll:,.0f}")
d2.metric(
    "Apostas pendentes",
    _stats_all["pendentes"],
    help="Apostas registradas aguardando resultado.",
)
if _stats_all["resolvidas"] > 0:
    _roi_delta = f"{_stats_all['roi']:+.1f}%"
    d3.metric("ROI real", f"{_stats_all['roi']:+.1f}%", delta=_roi_delta)
    d4.metric(
        "CLV médio",
        f"{_stats_all['clv_medio']:+.2f}%" if _stats_all["clv_medio"] is not None else "—",
        help="Closing Line Value médio. Positivo = você consistently bate o mercado.",
    )
else:
    d3.metric("ROI real", "—")
    d4.metric("CLV médio", "—")
d5.metric("Req. restantes", st.session_state.get("quota_remaining", "—"))

st.divider()

# ─── Busca ────────────────────────────────────────────────────────────────────
if _do_search:
    if not selected_league_keys:
        st.sidebar.warning("Selecione ao menos uma liga.")
    elif not selected_market_keys:
        st.sidebar.warning("Selecione ao menos um mercado.")
    else:
        client = OddsAPIClient(api_key)
        all_events: list[dict] = []
        errors: list[str] = []

        with st.status(
            "🔄 Buscando odds..." if not _ar_fired else "🔄 Auto-refresh em andamento...",
            expanded=True,
        ) as status:
            for sport_key in selected_league_keys:
                league_name = SOCCER_LEAGUES[sport_key]
                st.write(f"📡 **{league_name}**...")
                try:
                    events = client.get_odds(sport_key, selected_market_keys)
                    all_events.extend(events)

                    if client.from_cache:
                        age = get_cache_age(sport_key, selected_market_keys) or 0
                        st.write(f"   ⚡ {len(events)} jogo(s) — cache ({age}s atrás, sem request gasto)")
                    else:
                        st.write(f"   ✅ {len(events)} jogo(s) — dados frescos da API")

                    if client.skipped_markets:
                        skipped = [MARKET_OPTIONS.get(m, m) for m in client.skipped_markets]
                        st.write(f"   ⚠️ Ignorados: {', '.join(skipped)}")
                except OddsAPIError as e:
                    errors.append(f"**{league_name}:** {e}")
                    st.write(f"   ❌ {e}")
                time.sleep(0.3)

            st.session_state["quota_remaining"] = client.requests_remaining
            status.update(label="✅ Concluído!", state="complete")

        for err in errors:
            st.warning(f"⚠️ {err}")

        if all_events:
            opps = find_opportunities(all_events, min_ev=min_ev_pct / 100)
            st.session_state["results"]           = opps
            st.session_state["all_events"]        = all_events
            st.session_state["events_count"]      = len(all_events)
            st.session_state["min_ev_used"]       = min_ev_pct
            st.session_state["last_search_time"]  = time.time()
            # Salva snapshot para movimento de linha
            save_snapshot(all_events)
            # Flag de alerta
            high_ev = [o for o in opps if o["EV (%)"] >= alert_threshold]
            st.session_state["_alert_count"] = len(high_ev)
            st.session_state["_alert_best"]  = opps[0]["EV (%)"] if opps else 0.0
            st.session_state["_alert_play"]  = bool(high_ev)

            # Notificação Telegram
            _tg_token = config.get("telegram_token", "")
            _tg_chat  = config.get("telegram_chat_id", "")
            if high_ev and _tg_token and _tg_chat:
                from notifications import format_ev_alert, send_telegram
                send_telegram(_tg_token, _tg_chat,
                               format_ev_alert(high_ev, alert_threshold))
        else:
            st.error("Nenhum jogo encontrado. Verifique a chave de API e as ligas.")

        st.rerun()

# ─── Abas ─────────────────────────────────────────────────────────────────────
tab_ev, tab_today, tab_arb, tab_compare, tab_tracker, tab_sim = st.tabs([
    "🔍 Buscar EV+",
    "📅 Jogos de Hoje",
    "⚡ Arbitragem",
    "📊 Comparativo de Odds",
    "📋 Tracker de Apostas",
    "📈 Simulação de Variância",
])

_cfg = {
    "api_key":               api_key,
    "bankroll":              bankroll,
    "kelly_frac":            kelly_frac,
    "kelly_label":           kelly_label,
    "kelly_map":             kelly_map,
    "min_ev_pct":            min_ev_pct,
    "odd_range":             odd_range,
    "alert_threshold":       alert_threshold,
    "sound_alerts":          sound_alerts,
    "auto_refresh":          auto_refresh,
    "has_autorefresh":       _HAS_AUTOREFRESH,
    "refresh_interval":      refresh_interval,
    "selected_league_keys":  selected_league_keys,
}

with tab_ev:
    ev_tab.render(_cfg)

with tab_arb:
    arb_tab.render(_cfg)

with tab_today:
    today_tab.render(_cfg)

with tab_compare:
    compare_tab.render(_cfg)

with tab_tracker:
    tracker_tab.render(_cfg)

with tab_sim:
    sim_tab.render(_cfg)