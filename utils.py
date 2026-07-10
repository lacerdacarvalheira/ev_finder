"""
EV Finder — Utilitários compartilhados.
Centraliza constantes e helpers usados em múltiplos módulos.
"""
import os
from datetime import datetime, timezone, timedelta
from loguru import logger

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ev_finder.log")
logger.add(_LOG_FILE, rotation="1 week", retention="4 weeks", level="WARNING")

BRT = timezone(timedelta(hours=-3))

# ── Unidades ──────────────────────────────────────────────────────────────────
# 1 unidade = percentual da banca total; múltiplos padrão para dimensionar stakes.
UNIT_MULTIPLES = [0.25, 0.50, 0.75, 1.0, 1.25, 1.5]


def unit_value(bankroll: float, unit_pct: float = 1.0) -> float:
    """Valor de 1 unidade em R$ (unit_pct % da banca total)."""
    return round(bankroll * unit_pct / 100.0, 2)


def lucro_em_unidades(lucro: float, unit_val: float) -> float | None:
    """Converte lucro em R$ para unidades. None se a unidade for inválida."""
    if not unit_val or unit_val <= 0:
        return None
    return round(lucro / unit_val, 2)

BOOKIE_NAMES: dict[str, str] = {
    # ── Referência ───────────────────────────────────────────────────────────
    "pinnacle":         "Pinnacle",
    # ── Disponíveis no tier atual da API ────────────────────────────────────
    "betfair_ex_eu":    "Betfair Exchange",
    "williamhill":      "William Hill",
    "betclic_fr":       "Betclic",
    "sport888":         "888sport",
    "betsson":          "Betsson",
    "marathonbet":      "Marathonbet",
    "nordicbet":        "NordicBet",
    "leovegas_se":      "LeoVegas",
    "matchbook":        "Matchbook",
    "unibet_fr":        "Unibet (FR)",
    "unibet_nl":        "Unibet (NL)",
    "unibet_se":        "Unibet (SE)",
    "winamax_fr":       "Winamax (FR)",
    "winamax_de":       "Winamax (DE)",
    "tipico_de":        "Tipico",
    "codere_it":        "Codere",
    "onexbet":          "1xBet",
    "pmu_fr":           "PMU (FR)",
    "betanysports":     "BetAnything",
    "betonlineag":      "BetOnline.ag",
    "mybookieag":       "MyBookie.ag",
    "gtbets":           "GTbets",
    "everygame":        "Everygame",
    # ── Casas fora do tier atual (mantidas como opções) ──────────────────────
    "bet365":           "Bet365",
    "betano":           "Betano",
    "superbet":         "Superbet",
    "unibet_eu":        "Unibet",
    "bwin":             "bwin",
    "betway":           "Betway",
    "draftkings":       "DraftKings",
    "fanduel":          "FanDuel",
    "1xbet":            "1xBet (alt)",
    "888sport":         "888sport (alt)",
}


def bookie_display(key: str, fallback: str = "") -> str:
    return BOOKIE_NAMES.get(key, fallback or key)


def format_brt(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(BRT).strftime("%d/%m %H:%M")
    except Exception:
        return iso_str


def hours_until(iso_str: str) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        from datetime import timezone as _tz
        return (dt - datetime.now(_tz.utc)).total_seconds() / 3600
    except Exception:
        return None


# ─── Glossário de ajuda ───────────────────────────────────────────────────────

GLOSSARY: dict[str, str] = {
    "Probabilidade justa": (
        "A chance real estimada de um resultado acontecer, calculada a partir das "
        "odds da Pinnacle depois de remover a margem da casa. Se a prob justa é 70%, "
        "a odd justa é 1/0,70 = 1,43."
    ),
    "Vig (margem)": (
        "A \"taxa\" embutida nas odds. As probabilidades implícitas de um jogo sempre "
        "somam mais de 100% — o excesso é o lucro da casa. Ex.: se somam 105%, a "
        "margem é ~5%."
    ),
    "Devig": (
        "O processo de remover a margem das odds para chegar na probabilidade justa. "
        "O app usa o *power method*, que corrige a distorção que favorece azarões."
    ),
    "EV (Valor Esperado)": (
        "Quanto você espera ganhar ou perder em média por aposta, no longo prazo. "
        "EV +5% significa: apostando R$100 nessa situação muitas vezes, o lucro médio "
        "tende a R$5 por aposta. EV negativo = prejuízo médio garantido no longo prazo."
    ),
    "Line shopping": (
        "Comparar a odd do mesmo resultado em várias casas e apostar sempre na maior. "
        "É a forma mais simples de reduzir (ou zerar) a margem que você paga."
    ),
    "Stake fixa (flat)": (
        "Apostar sempre o mesmo valor (ex.: 2% da banca) independente da confiança. "
        "Simples e resistente a erros de estimativa."
    ),
    "Kelly": (
        "Fórmula que calcula a fração ideal da banca a apostar com base no seu EV. "
        "Maximiza crescimento no longo prazo, mas é agressiva: qualquer erro na "
        "estimativa de probabilidade vira aposta grande demais. Por isso se usa "
        "Kelly fracionado (¼)."
    ),
    "Longshot": (
        "Azarão de odd alta (ex.: 15.0+). As casas embutem margem extra nesses "
        "mercados, então o EV aparente costuma ser inflado."
    ),
    "Drawdown": (
        "A queda da banca do pico até o fundo durante uma sequência ruim. Toda "
        "estratégia tem drawdowns — o importante é dimensionar o stake para "
        "sobreviver a eles."
    ),
    "CLV (Closing Line Value)": (
        "Comparação entre a odd que você pegou e a odd no fechamento do mercado. "
        "Bater a linha de fechamento consistentemente é o melhor indicador de que "
        "sua estratégia tem valor real — melhor que o lucro de curto prazo."
    ),
    "Sequência de derrotas": (
        "Mesmo com 70% de acerto, perder 3–4 seguidas em 100 apostas é "
        "matematicamente esperado. Não é sinal de que a estratégia quebrou — é "
        "variância normal."
    ),
    "Steam move": (
        "Movimento rápido e forte de uma odd, geralmente causado por dinheiro "
        "profissional. Indica que a probabilidade real mudou."
    ),
}


def help_icon(term: str, key: str | None = None):
    """Renderiza um popover ❓ com a explicação do termo do GLOSSARY."""
    import streamlit as st
    text = GLOSSARY.get(term)
    if not text:
        return
    try:
        with st.popover("❓", use_container_width=False):
            st.markdown(f"**{term}**\n\n{text}")
    except AttributeError:
        # Streamlit < 1.31 — fallback
        with st.expander("❓"):
            st.markdown(f"**{term}**\n\n{text}")


def urgency_badge(hours: float | None) -> str:
    if hours is None: return "—"
    if hours < 0:     return "🔴 Ao vivo"
    if hours < 1:     return f"🔴 {int(hours * 60)}min"
    if hours < 3:     return f"🟠 {hours:.1f}h"
    if hours < 12:    return f"🟡 {hours:.0f}h"
    if hours < 48:    return f"⬜ {hours:.0f}h"
    return f"⬜ {hours / 24:.0f}d"


# ─── Devig ────────────────────────────────────────────────────────────────────
# Método padrão do app. Alterável via set_devig_method() (sidebar do app.py).
_DEVIG_METHOD = "power"


def set_devig_method(method: str) -> None:
    """Define o método global de devig: 'power' ou 'multiplicative'."""
    global _DEVIG_METHOD
    if method in ("power", "multiplicative"):
        _DEVIG_METHOD = method


def get_devig_method() -> str:
    return _DEVIG_METHOD


def remove_vig_multiplicative(prices: list[float]) -> list[float] | None:
    """Devig por normalização proporcional (legado). None se len < 2."""
    if not prices or len(prices) < 2:
        return None
    safe  = [max(p, 1.001) for p in prices]
    raw   = [1.0 / p for p in safe]
    total = sum(raw)
    if total <= 0:
        return [1.0 / len(prices)] * len(prices)
    return [p / total for p in raw]


def remove_vig_power(prices: list[float]) -> list[float] | None:
    """
    Devig pelo power method: encontra k tal que sum((1/odd_i)^k) = 1.
    Corrige o favorite-longshot bias da normalização proporcional
    (que subestima favoritos e superestima azarões). None se len < 2.
    """
    if not prices or len(prices) < 2:
        return None
    from scipy.optimize import brentq

    safe = [max(p, 1.001) for p in prices]
    raw  = [1.0 / p for p in safe]
    booksum = sum(raw)
    if booksum <= 1.0:
        # Mercado sem margem ou dado inconsistente: normalização simples
        return [r / booksum for r in raw] if booksum > 0 else None

    f = lambda k: sum(r ** k for r in raw) - 1.0
    # f(1) = booksum - 1 > 0; f cresce negativa com k. Expande o teto se preciso.
    hi = 10.0
    while f(hi) > 0 and hi < 1e6:
        hi *= 10
    try:
        k = brentq(f, 1.0, hi)
    except ValueError:
        logger.warning(f"[utils] remove_vig_power: brentq falhou para {prices}, usando multiplicativo")
        return remove_vig_multiplicative(prices)
    return [r ** k for r in raw]


def remove_vig(prices: list[float], method: str | None = None) -> list[float] | None:
    """
    Remove a margem (vig) das odds, retornando probabilidades justas.
    Despacha para o método global (power por padrão) ou o `method` passado.
    Retorna None se len(prices) < 2 — call sites devem tratar explicitamente.
    """
    m = method or _DEVIG_METHOD
    if m == "power":
        return remove_vig_power(prices)
    return remove_vig_multiplicative(prices)


def derive_two_way_from_3way(fair_probs: dict[str, float],
                              home: str, away: str) -> dict[str, dict[str, float]]:
    """
    Deriva probs justas de Empate Anula (DNB) e Dupla Chance (DC)
    a partir do 3-way (h2h) devigado — o mercado mais líquido da Pinnacle.

    fair_probs: {home_name: p, "Draw": p, away_name: p}
    Retorna {"dnb": {nome: prob}, "dc": {alias: prob}} com aliases múltiplos
    para casar com as convenções de nome das casas ("1X", "Home/Draw", etc).
    """
    p_home = fair_probs.get(home, 0.0)
    p_draw = fair_probs.get("Draw", 0.0)
    p_away = fair_probs.get(away, 0.0)

    dnb: dict[str, float] = {}
    no_draw = p_home + p_away
    if no_draw > 0:
        dnb[home] = p_home / no_draw
        dnb[away] = p_away / no_draw

    dc: dict[str, float] = {}
    dc_1x = p_home + p_draw
    dc_12 = p_home + p_away
    dc_x2 = p_draw + p_away
    for alias in ("1X", f"{home}/Draw", f"Draw/{home}", f"{home} or Draw", f"Draw or {home}"):
        dc[alias] = dc_1x
    for alias in ("12", f"{home}/{away}", f"{home} or {away}"):
        dc[alias] = dc_12
    for alias in ("X2", f"Draw/{away}", f"{away}/Draw", f"Draw or {away}", f"{away} or Draw"):
        dc[alias] = dc_x2

    return {"dnb": dnb, "dc": dc}
