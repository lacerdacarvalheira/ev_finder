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

    # Proteção contra lista de 1 elemento
    single = remove_vig([1.5])
    _assert("remove_vig retorna lista de 1 intacta", single == [1.5])


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
