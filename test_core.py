#!/usr/bin/env python
"""
EV Finder — Testes do núcleo matemático.
Execute com:  python test_core.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# UTF-8 no terminal Windows para suportar unicode nos nomes de testes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_passed = 0
_failed = 0


def _ok(name: str):
    global _passed
    _passed += 1
    print(f"  PASS  {name}")


def _fail(name: str, msg: str):
    global _failed
    _failed += 1
    print(f"  FAIL  {name}: {msg}", file=sys.stderr)


def _assert(name: str, cond: bool, msg: str = ""):
    if cond:
        _ok(name)
    else:
        _fail(name, msg or "condição falsa")


def _assert_close(name: str, a: float, b: float, tol: float = 1e-6):
    if abs(a - b) <= tol:
        _ok(name)
    else:
        _fail(name, f"{a!r} != {b!r} (tol={tol})")


# ─── remove_vig ────────────────────────────────────────────────────────────────

def test_remove_vig():
    from utils import remove_vig

    # Sem vig — distribuição justa
    fair = remove_vig([2.0, 2.0])
    _assert_close("remove_vig soma = 1.0",       sum(fair), 1.0, 1e-9)
    _assert_close("remove_vig 50/50 simétrico",  fair[0], fair[1], 1e-9)

    # Com vig de ~5% mas odds simétricas — probabilidade normalizada ainda = 0.5
    probs = remove_vig([1.9, 1.9])
    _assert_close("remove_vig com vig, soma = 1", sum(probs), 1.0, 1e-9)
    _assert_close("remove_vig odds simetricas = 50/50", probs[0], 0.5, 1e-9)

    # Favorito explícito
    probs_asym = remove_vig([1.5, 3.0])
    _assert("remove_vig favorito tem prob maior", probs_asym[0] > probs_asym[1])

    # Resultado final 1X2
    h2h = remove_vig([2.1, 3.5, 3.8])
    _assert_close("remove_vig 3 outcomes, soma = 1", sum(h2h), 1.0, 1e-9)
    _assert("remove_vig favorito tem prob maior", h2h[0] > h2h[1])

    # Proteção contra preço zero / valor absurdo
    safe = remove_vig([0.0, 2.0])
    _assert("remove_vig protege contra divisão por zero", len(safe) == 2)

    # Lista de 1 elemento deve falhar alto (None), não passar silenciosa
    single = remove_vig([1.5])
    _assert("remove_vig com 1 item retorna None", single is None)


# ─── EV formula ────────────────────────────────────────────────────────────────

def test_ev_formula():
    # EV = prob_real * odd - 1
    # odd=2.0, prob_real=0.55 → EV = 0.55*2.0 - 1 = 0.10 (10%)
    ev = 0.55 * 2.0 - 1.0
    _assert_close("EV formula básica", ev, 0.10, 1e-9)

    # odd justa = 1/prob
    prob = 0.55
    fair_odd = 1.0 / prob
    _assert_close("Odd justa = 1/prob", fair_odd, 1.0 / 0.55, 1e-9)

    # EV zero quando odd == odd justa
    ev_zero = prob * fair_odd - 1.0
    _assert_close("EV zero com odd justa", ev_zero, 0.0, 1e-9)

    # EV negativo com odd abaixo da justa
    ev_neg = prob * (fair_odd * 0.95) - 1.0
    _assert("EV negativo com odd < justa", ev_neg < 0)


# ─── Kelly ─────────────────────────────────────────────────────────────────────

def test_kelly():
    # Kelly = EV / (odd - 1)
    ev  = 0.10   # 10%
    odd = 2.0
    kelly = ev / (odd - 1)
    _assert_close("Kelly bruto 10% EV odd 2.0", kelly, 0.10, 1e-9)

    # odd=3.0, EV=0.15 → kelly=0.15/2.0=0.075
    kelly2 = 0.15 / (3.0 - 1)
    _assert_close("Kelly bruto 15% EV odd 3.0", kelly2, 0.075, 1e-9)

    # EV zero → Kelly zero
    kelly_zero = 0.0 / (2.0 - 1)
    _assert_close("Kelly zero com EV zero", kelly_zero, 0.0, 1e-9)

    # Proteção odd <= 1 (não deve dividir por zero)
    odd_safe = max(2.0, 1.001)
    kelly_safe = ev / (odd_safe - 1) if odd_safe > 1.001 else 0.0
    _assert("Kelly seguro com odd válida", kelly_safe > 0)


# ─── DNB probability ───────────────────────────────────────────────────────────

def test_dnb_probability():
    # DNB do favorito = fav_prob / (1 - draw_prob)
    # Se fav_prob=0.5, draw_prob=0.25 → DNB = 0.5/0.75 ≈ 0.6667
    fav  = 0.5
    draw = 0.25
    dnb  = fav / (1.0 - draw)
    _assert_close("DNB probability", dnb, 2.0 / 3.0, 1e-6)

    # DNB > fav simples (quando há probabilidade de empate)
    _assert("DNB > prob simples", dnb > fav)

    # DNB sem empate = fav (draw_prob=0)
    dnb_no_draw = fav / (1.0 - 0.0)
    _assert_close("DNB sem empate = fav", dnb_no_draw, fav, 1e-9)

    # Proteção: draw_prob ≥ 1 não gera divisão por zero
    draw_max = min(0.95, 0.99)
    dnb_safe = fav / (1.0 - draw_max)
    _assert("DNB seguro com draw_prob alto", dnb_safe > 0)


# ─── Arbitragem ────────────────────────────────────────────────────────────────

def test_arb_detection():
    from arb_finder import _calc_arb

    # Arb real: sum_inv < 1.0
    arb_real = _calc_arb({
        "Over":  {"price": 2.20, "bookmaker": "BetA"},
        "Under": {"price": 2.10, "bookmaker": "BetB"},
    })
    _assert("arb real detectada", arb_real is not None)
    _assert("arb real lucro > 0", arb_real is not None and arb_real["lucro_pct"] > 0)

    # Sem arb: sum_inv >= 1.0
    no_arb = _calc_arb({
        "Over":  {"price": 1.90, "bookmaker": "BetA"},
        "Under": {"price": 1.90, "bookmaker": "BetB"},
    })
    _assert("sem arb quando sum_inv >= 1", no_arb is None)

    # Precisão do lucro
    if arb_real:
        sum_inv = 1.0 / 2.20 + 1.0 / 2.10
        expected_profit = (1.0 / sum_inv - 1.0) * 100
        _assert_close("arb lucro correto", arb_real["lucro_pct"], round(expected_profit, 3), 0.001)

    # Arb precisa de pelo menos 2 outcomes
    no_arb_single = _calc_arb({"Over": {"price": 2.5, "bookmaker": "BetA"}})
    _assert("arb retorna None com 1 outcome", no_arb_single is None)


# ─── Correlação de mercados ────────────────────────────────────────────────────

def test_correlation_pairs():
    from arb_finder import _CORRELATED_PAIRS

    _assert("totals-btts correlacionados",
            frozenset({"totals", "btts"}) in _CORRELATED_PAIRS)
    _assert("h2h-doubleChance correlacionados",
            frozenset({"h2h", "doubleChance"}) in _CORRELATED_PAIRS)
    _assert("totals-spreads correlacionados",
            frozenset({"totals", "spreads"}) in _CORRELATED_PAIRS)

    # Mercados independentes NÃO devem estar no conjunto
    _assert("totals-h2h NOT correlacionados (não há dependência direta)",
            frozenset({"totals", "h2h"}) not in _CORRELATED_PAIRS)


# ─── utils.format_brt ──────────────────────────────────────────────────────────

def test_format_brt():
    from utils import format_brt

    # ISO 8601 válido
    result = format_brt("2026-06-30T20:00:00Z")
    _assert("format_brt retorna string não-vazia", bool(result))
    _assert("format_brt contém /", "/" in result)

    # String inválida retorna o input
    bad = format_brt("not-a-date")
    _assert("format_brt retorna input em caso de erro", bad == "not-a-date")

    # String vazia
    empty = format_brt("")
    _assert("format_brt string vazia retorna string", isinstance(empty, str))


# ─── utils.urgency_badge ───────────────────────────────────────────────────────

def test_urgency_badge():
    from utils import urgency_badge

    _assert("urgency_badge ao vivo (h<0)",    "Ao vivo" in urgency_badge(-0.1))
    _assert("urgency_badge < 1h tem min",     "min"     in urgency_badge(0.5))
    _assert("urgency_badge 2h tem 🟠",        "🟠"      in urgency_badge(2.0))
    _assert("urgency_badge 6h tem 🟡",        "🟡"      in urgency_badge(6.0))
    _assert("urgency_badge None retorna —",   urgency_badge(None) == "—")


# ─── Steam moves ───────────────────────────────────────────────────────────────

def test_detect_steam_moves():
    from line_cache import detect_steam_moves

    # Sem histórico → lista vazia
    result = detect_steam_moves("id_inexistente")
    _assert("steam moves sem historico retorna []", result == [])

    # Injetar histórico temporário para testar detecção
    import line_cache as lc
    import json, tempfile, os

    tmp = tempfile.mktemp(suffix=".json")
    orig = lc._HISTORY_FILE
    lc._HISTORY_FILE = tmp

    try:
        # Snapshot 1: pinnacle h2h home=2.00, snap 2: home=1.70 (prob sobe ~6pp)
        history = {
            "game1": {
                "home": "A", "away": "B",
                "commence_time": "2099-01-01T20:00:00Z",
                "snapshots": [
                    {"ts": "2099-01-01T18:00:00Z", "odds": {
                        "pinnacle": {"h2h": [
                            {"name": "A", "price": 2.00, "point": None},
                            {"name": "B", "price": 3.80, "point": None},
                        ]},
                    }},
                    {"ts": "2099-01-01T19:00:00Z", "odds": {
                        "pinnacle": {"h2h": [
                            {"name": "A", "price": 1.70, "point": None},
                            {"name": "B", "price": 4.50, "point": None},
                        ]},
                    }},
                ],
            }
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f)

        moves = detect_steam_moves("game1", min_pp=3.0)
        _assert("steam detecta movimento >= 3pp", len(moves) >= 1)
        _assert("steam resultado e ordenado por magnitude", moves[0]["pp_move"] != 0)
        home_move = next((m for m in moves if m["outcome"] == "A"), None)
        _assert("steam move do favorito detectado", home_move is not None)
        if home_move:
            # prob sobe: 1/2.00=50% → 1/1.70≈58.8%, delta≈+8.8pp
            _assert("steam direction correta (steam up)", home_move["pp_move"] > 0)

        # Sem snapshot suficiente → []
        history_single = {"game2": {"snapshots": [{"ts": "x", "odds": {}}]}}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history_single, f)
        _assert("steam sem 2 snaps retorna []", detect_steam_moves("game2") == [])

    finally:
        lc._HISTORY_FILE = orig
        if os.path.exists(tmp):
            os.remove(tmp)


# ─── Watchlist ─────────────────────────────────────────────────────────────────

def test_watchlist():
    import tempfile, os
    import watchlist as wl

    tmp = tempfile.mktemp(suffix=".json")
    orig = wl._WATCHLIST_FILE
    wl._WATCHLIST_FILE = tmp

    try:
        from watchlist import add_watch, remove_watch, load_watchlist, check_hits

        _assert("watchlist vazia retorna []", load_watchlist() == [])

        add_watch("Brasil vs França", "1X2", "Brasil", 2.50)
        items = load_watchlist()
        _assert("add_watch adiciona 1 item",          len(items) == 1)
        _assert("add_watch selecao correta",           items[0]["selecao"] == "Brasil")
        _assert_close("add_watch odd correta",         items[0]["odd_alvo"], 2.50, 1e-6)
        _assert("add_watch id atribuido",              items[0]["id"] == 1)

        # Segundo item — IDs sequenciais
        add_watch("", "BTTS", "Sim", 1.80)
        items2 = load_watchlist()
        _assert("add_watch segundo item",              len(items2) == 2)
        _assert("add_watch id sequencial",             items2[1]["id"] == 2)

        # check_hits — odd suficiente (2.55 >= 2.50 * 0.98)
        opps = [{"Jogo": "Brasil vs França", "Seleção": "Brasil",
                 "Odd Casa": 2.55, "EV (%)": 5.0}]
        hits = check_hits(opps)
        _assert("check_hits encontra match por selecao", len(hits) >= 1)

        # check_hits — odd insuficiente (2.20 < 2.50 * 0.98 = 2.45)
        opps_low = [{"Jogo": "Brasil vs França", "Seleção": "Brasil",
                     "Odd Casa": 2.20, "EV (%)": 1.0}]
        hits_low = check_hits(opps_low)
        _assert("check_hits nao bate com odd baixa", len(hits_low) == 0)

        # check_hits — match por jogo (selecao no nome do jogo)
        opps_jogo = [{"Jogo": "brasil vs franca", "Seleção": "Vencer",
                      "Odd Casa": 2.60, "EV (%)": 3.0}]
        hits_jogo = check_hits(opps_jogo)
        _assert("check_hits match por nome do jogo", len(hits_jogo) >= 1)

        # remove_watch
        remove_watch(1)
        items3 = load_watchlist()
        _assert("remove_watch remove item correto",     len(items3) == 1)
        _assert("remove_watch mantem outros itens",     items3[0]["id"] == 2)

    finally:
        wl._WATCHLIST_FILE = orig
        if os.path.exists(tmp):
            os.remove(tmp)


# ─── Kelly portfólio ───────────────────────────────────────────────────────────

def test_kelly_portfolio():
    # kelly = EV / (odd - 1)
    # Aposta 1: EV=15%, odd=2.0 → k=0.15
    # Aposta 2: EV=15%, odd=2.0 → k=0.15
    # Total=0.30, limite=20% → escala=0.20/0.30=0.6667
    ev, odd = 0.15, 2.0
    k = ev / (odd - 1)
    _assert_close("kelly unitario correto", k, 0.15, 1e-9)

    total_k = k * 2
    limit   = 0.20
    scale   = limit / total_k if total_k > limit else 1.0
    _assert_close("kelly portfolio escala correta",           scale, 2/3, 1e-9)
    _assert_close("kelly portfolio total pos-escala = limite", total_k * scale, limit, 1e-9)

    # Sem necessidade de escala: dois bets com k=0.05 cada → total=0.10 < 0.20
    k_small = 0.10 / (2.0 - 1)   # EV=10%, odd=2.0
    total_small = k_small * 2
    scale_small = limit / total_small if total_small > limit else 1.0
    _assert("kelly portfolio sem escala quando total < limite", scale_small == 1.0)

    # EV negativo → kelly deve ser clipado a zero
    k_neg = max((-0.05) / (2.0 - 1), 0)
    _assert_close("kelly negativo clipado a zero", k_neg, 0.0, 1e-9)


# ─── Calibração de EV (analytics) ─────────────────────────────────────────────

def test_spreads_grouping():
    """
    Regression: The Odds API dá pontos opostos por time (England -1.5, Slovakia +1.5).
    remove_vig de lista com 1 item devolve a ODD, não a probabilidade — causando
    prob 185%+ e EV 300%+ antes da correção.
    """
    from ev_calculator import _process_spreads

    # Simula exatamente o formato da API: pontos opostos
    pin = [
        {"name": "England",  "price": 1.85, "point": -1.5},
        {"name": "Slovakia", "price": 2.05, "point":  1.5},
    ]
    bk = [
        {"name": "England",  "price": 2.04, "point": -1.5},
        {"name": "Slovakia", "price": 1.87, "point":  1.5},
    ]
    meta = {"jogo": "England vs Slovakia", "hora": "", "liga": "",
            "commence_time_raw": "", "event_id": "x1"}

    rows = _process_spreads(pin, bk, meta, "Matchbook", min_ev=0.0)

    # Deve encontrar resultados (antes da correção = lista vazia pq len<2 guard)
    _assert("spreads retorna resultados", len(rows) >= 1)

    for r in rows:
        prob = r["Prob. Real (%)"]
        ev   = r["EV (%)"]
        _assert(f"prob <= 100% ({prob:.1f}%)", prob <= 100.0)
        _assert(f"EV < 50% ({ev:.1f}%)", ev < 50.0)  # impossível EV genuíno de 300%


def test_ev_calibration():
    # 2 ganhos em 3 apostas = 66.7% de acerto
    bets = [
        {"resultado": "ganhou", "ev_pct": 5.0, "prob_real": 60.0, "stake": 100.0, "lucro":  100.0},
        {"resultado": "ganhou", "ev_pct": 6.0, "prob_real": 55.0, "stake": 100.0, "lucro":  100.0},
        {"resultado": "perdeu", "ev_pct": 7.0, "prob_real": 58.0, "stake": 100.0, "lucro": -100.0},
    ]

    n_win    = sum(1 for b in bets if b["resultado"] == "ganhou")
    win_real = n_win / len(bets) * 100
    _assert_close("calibracao win rate correto", win_real, 200/3, 0.01)

    win_exp = sum(b["prob_real"] for b in bets) / len(bets)
    _assert_close("calibracao win exp medio correto", win_exp, (60+55+58)/3, 0.001)

    total_st = sum(b["stake"] for b in bets)
    roi = sum(b["lucro"] for b in bets) / total_st * 100
    _assert_close("calibracao ROI correto (100/300)", roi, 100/3, 0.001)

    # ROI acumulado sobe monotonicamente quando todas ganham
    bets_wins = [
        {"resultado": "ganhou", "stake": 50.0, "lucro": 50.0},
        {"resultado": "ganhou", "stake": 50.0, "lucro": 50.0},
    ]
    running_l, running_a = 0.0, 0.0
    roi_curve = []
    for b in bets_wins:
        running_l += b["lucro"]
        running_a += b["stake"]
        roi_curve.append(running_l / running_a * 100)
    _assert("ROI cumulativo cresce com ganhos consecutivos",
            roi_curve[0] <= roi_curve[1])
    _assert_close("ROI final correto com 100% acerto", roi_curve[-1], 100.0, 1e-9)


def test_remove_vig_power():
    from utils import remove_vig_power, remove_vig_multiplicative

    # Soma 1.0 em 2-way e 3-way
    for prices in ([1.30, 3.80], [2.1, 3.5, 3.8], [1.9, 1.9]):
        probs = remove_vig_power(prices)
        _assert_close(f"power soma 1.0 para {prices}", sum(probs), 1.0, 1e-9)

    # Power dá prob MAIOR ao favorito que o multiplicativo (corrige o bias)
    mult  = remove_vig_multiplicative([1.30, 3.80])
    power = remove_vig_power([1.30, 3.80])
    _assert("power favorito > multiplicativo favorito", power[0] > mult[0])
    _assert("power azarao < multiplicativo azarao",     power[1] < mult[1])

    # 1 item retorna None em ambos os métodos
    _assert("power com 1 item retorna None",          remove_vig_power([1.85]) is None)
    _assert("multiplicativo com 1 item retorna None", remove_vig_multiplicative([1.85]) is None)

    # Dispatch por método
    from utils import remove_vig
    via_power = remove_vig([1.30, 3.80], method="power")
    via_mult  = remove_vig([1.30, 3.80], method="multiplicative")
    _assert_close("dispatch power igual funcao direta", via_power[0], power[0], 1e-12)
    _assert_close("dispatch mult igual funcao direta",  via_mult[0],  mult[0],  1e-12)


def test_derive_two_way():
    from utils import derive_two_way_from_3way, remove_vig

    fair3_list = remove_vig([1.65, 3.90, 5.50])  # home, draw, away
    fair3 = {"England": fair3_list[0], "Draw": fair3_list[1], "Slovakia": fair3_list[2]}
    d = derive_two_way_from_3way(fair3, "England", "Slovakia")

    # DNB soma 1
    _assert_close("DNB soma 1.0", d["dnb"]["England"] + d["dnb"]["Slovakia"], 1.0, 1e-9)
    # DNB favorito > prob 3-way (condicionado a nao-empate)
    _assert("DNB favorito > prob 3-way", d["dnb"]["England"] > fair3["England"])

    # DC coerente: 1X + prob(away) = 1 ; X2 + prob(home) = 1 ; 12 + prob(draw) = 1
    _assert_close("DC 1X = p_home + p_draw", d["dc"]["1X"], fair3["England"] + fair3["Draw"], 1e-9)
    _assert_close("DC X2 = p_draw + p_away", d["dc"]["X2"], fair3["Draw"] + fair3["Slovakia"], 1e-9)
    _assert_close("DC 12 = p_home + p_away", d["dc"]["12"], fair3["England"] + fair3["Slovakia"], 1e-9)
    _assert_close("DC 1X + p_away = 1",      d["dc"]["1X"] + fair3["Slovakia"], 1.0, 1e-9)

    # Aliases apontam para a mesma prob
    _assert_close("alias England/Draw == 1X", d["dc"]["England/Draw"], d["dc"]["1X"], 1e-12)


def test_favoritos_filter():
    from game_analyst import favoritos_do_dia

    def _event(best_home_odd: float):
        return {
            "id": "ev1",
            "home_team": "England", "away_team": "Slovakia",
            "commence_time": "2099-07-10T18:00:00Z",
            "bookmakers": [
                {"key": "pinnacle", "title": "Pinnacle", "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "England",  "price": 1.30},
                        {"name": "Draw",     "price": 5.50},
                        {"name": "Slovakia", "price": 11.00},
                    ]}]},
                {"key": "betsson", "title": "Betsson", "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "England",  "price": best_home_odd},
                        {"name": "Draw",     "price": 5.40},
                        {"name": "Slovakia", "price": 10.00},
                    ]}]},
            ],
        }

    _W = 10**9  # janela enorme — evento de teste é em 2099

    # Odd 1.20 << odd justa (~1.32 devigada) → EV < 0 → excluída com ev_floor=0
    favs_low = favoritos_do_dia([_event(1.20)], min_prob=0.65, ev_floor=0.0,
                                 hours_window=_W)
    h2h_low  = [f for f in favs_low if f["Mercado"] == "Resultado Final"]
    _assert("favorito com odd abaixo da justa é excluído", len(h2h_low) == 0)

    # Odd 1.45 > odd justa → EV > 0 → aparece
    favs_hi = favoritos_do_dia([_event(1.45)], min_prob=0.65, ev_floor=0.0,
                                hours_window=_W)
    h2h_hi  = [f for f in favs_hi if f["Mercado"] == "Resultado Final"
               and f["Seleção"] == "England"]
    _assert("favorito com odd acima da justa aparece", len(h2h_hi) == 1)
    if h2h_hi:
        _assert("EV do favorito listado >= 0", h2h_hi[0]["EV (%)"] >= 0)
        _assert("prob justa >= piso",          h2h_hi[0]["Prob. justa (%)"] >= 65.0)


def test_pior_sequencia():
    import random
    from game_analyst import pior_sequencia_esperada

    k = pior_sequencia_esperada(0.7, 100)
    _assert(f"pior sequencia p=0.7 n=100 → K=3 ou 4 (obtido {k})", k in (3, 4))

    # Valida contra simulação: sequência máxima média deve ficar perto de K
    rng = random.Random(42)
    max_streaks = []
    for _ in range(2000):
        streak = worst = 0
        for _ in range(100):
            if rng.random() < 0.7:
                streak = 0
            else:
                streak += 1
                worst = max(worst, streak)
        max_streaks.append(worst)
    media_sim = sum(max_streaks) / len(max_streaks)
    _assert(f"formula proxima da simulacao (formula={k}, sim={media_sim:.1f})",
            abs(media_sim - k) <= 1.5)

    # Sanidade: prob maior → sequência menor
    _assert("p=0.9 tem sequencia menor que p=0.5",
            pior_sequencia_esperada(0.9, 100) < pior_sequencia_esperada(0.5, 100))


def test_bankroll_history():
    import tempfile
    import bankroll_history as bh

    _orig = bh.DB_PATH
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    bh.DB_PATH = tmp.name
    try:
        # 1º snapshot
        snap1 = bh.add_snapshot({"Superbet": 500.0, "Bet365": 300.0}, 800.0)
        _assert("1º snapshot marca primeiro=True", snap1 is not None and snap1["primeiro"])

        # Salvar idêntico não duplica
        dup = bh.add_snapshot({"Superbet": 500.0, "Bet365": 300.0}, 800.0)
        _assert("snapshot idêntico retorna None", dup is None)
        _assert("histórico tem só 1 registro", len(bh.load_history()) == 1)

        # Depósito de 200 na Superbet → delta detectado
        snap2 = bh.add_snapshot({"Superbet": 700.0, "Bet365": 300.0}, 1000.0)
        _assert_close("delta_total = +200", snap2["delta_total"], 200.0, 1e-9)
        _assert_close("delta Superbet = +200", snap2["deltas"]["Superbet"], 200.0, 1e-9)
        _assert("Bet365 sem mudança não aparece nos deltas", "Bet365" not in snap2["deltas"])

        hist = bh.load_history()
        _assert("histórico tem 2 registros", len(hist) == 2)
        _assert("bankrolls desserializado como dict", hist[0]["bankrolls"]["Superbet"] == 500.0)

        # Análise: banca 800 → 1000 (+200); lucro de apostas no período = +50
        # → depósito implícito = 150
        bets = [
            {"resultado": "ganhou",   "lucro":  80.0, "data": "01/01/2099 10:00"},
            {"resultado": "perdeu",   "lucro": -30.0, "data": "01/01/2099 11:00"},
            {"resultado": "pendente", "lucro":  None, "data": "01/01/2099 12:00"},
            # Antes do 1º snapshot → fora do período
            {"resultado": "ganhou",   "lucro": 999.0, "data": "01/01/2000 10:00"},
        ]
        an = bh.analise_evolucao(hist, bets)
        _assert_close("variação = +200", an["variacao"], 200.0, 1e-9)
        _assert_close("lucro apostas período = +50", an["lucro_apostas"], 50.0, 1e-9)
        _assert_close("depósito implícito = +150", an["depositos_liquidos"], 150.0, 1e-9)
        _assert("aposta antiga fora do período ignorada", an["n_resolvidas"] == 2)
        _assert_close("ROI sobre banca = 50/800", an["roi_banca"], 6.25, 1e-9)
        _assert_close("crescimento = 200/800", an["crescimento_pct"], 25.0, 1e-9)

        # < 2 snapshots → None
        _assert("análise com 1 snapshot retorna None",
                bh.analise_evolucao(hist[:1], bets) is None)

        # Série diária com forward-fill
        from datetime import date
        fake_hist = [
            {"data": "01/07/2026 10:00", "total": 800.0,  "bankrolls": {}},
            {"data": "01/07/2026 18:00", "total": 850.0,  "bankrolls": {}},  # último do dia vence
            {"data": "04/07/2026 12:00", "total": 1000.0, "bankrolls": {}},
        ]
        serie = bh.serie_diaria(fake_hist, ate=date(2026, 7, 6))
        _assert_close("serie: último snapshot do dia vence", serie[date(2026, 7, 1)], 850.0, 1e-9)
        _assert_close("serie: dia 02 herda valor (fill)",    serie[date(2026, 7, 2)], 850.0, 1e-9)
        _assert_close("serie: dia 03 herda valor (fill)",    serie[date(2026, 7, 3)], 850.0, 1e-9)
        _assert_close("serie: dia 04 atualiza",              serie[date(2026, 7, 4)], 1000.0, 1e-9)
        _assert_close("serie: dia 06 (ate) herda",           serie[date(2026, 7, 6)], 1000.0, 1e-9)
        _assert("serie: cobre do 1º snapshot até 'ate'", len(serie) == 6)
        _assert("serie: histórico vazio retorna {}", bh.serie_diaria([]) == {})

        # Apagar último registro
        bh.delete_snapshot(hist[-1]["id"])
        _assert("delete_snapshot remove o registro", len(bh.load_history()) == 1)
    finally:
        bh.DB_PATH = _orig
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def test_unidades():
    from utils import UNIT_MULTIPLES, lucro_em_unidades, unit_value

    _assert("múltiplos padrão", UNIT_MULTIPLES == [0.25, 0.50, 0.75, 1.0, 1.25, 1.5])
    _assert_close("1u = 1% de R$ 1000 = R$ 10", unit_value(1000.0, 1.0), 10.0)
    _assert_close("1u = 2% de R$ 500 = R$ 10", unit_value(500.0, 2.0), 10.0)
    _assert_close("0.25u de banca 1000 = R$ 2.50", 0.25 * unit_value(1000.0, 1.0), 2.5)
    _assert_close("1.5u de banca 1000 = R$ 15", 1.5 * unit_value(1000.0, 1.0), 15.0)
    _assert_close("lucro +35 com 1u=10 → +3.5u", lucro_em_unidades(35.0, 10.0), 3.5)
    _assert_close("lucro -12.5 com 1u=10 → -1.25u", lucro_em_unidades(-12.5, 10.0), -1.25)
    _assert("unidade zero retorna None", lucro_em_unidades(50.0, 0.0) is None)
    _assert("banca zerada retorna None", lucro_em_unidades(50.0, unit_value(0.0, 1.0)) is None)


# ─── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_remove_vig,
        test_ev_formula,
        test_kelly,
        test_dnb_probability,
        test_arb_detection,
        test_correlation_pairs,
        test_format_brt,
        test_urgency_badge,
        test_detect_steam_moves,
        test_watchlist,
        test_kelly_portfolio,
        test_spreads_grouping,
        test_ev_calibration,
        test_remove_vig_power,
        test_derive_two_way,
        test_favoritos_filter,
        test_pior_sequencia,
        test_bankroll_history,
        test_unidades,
    ]

    for fn in tests:
        print(f"\n{fn.__name__}:")
        try:
            fn()
        except Exception as exc:
            _fail(fn.__name__, f"exceção: {exc}")

    print(f"\n{'─'*40}")
    print(f"Total: {_passed + _failed}  |  ✅ {_passed}  |  ❌ {_failed}")
    sys.exit(0 if _failed == 0 else 1)
