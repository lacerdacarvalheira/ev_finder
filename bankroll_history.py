"""
EV Finder — Histórico de bancas (SQLite, mesma base bets.db)

Cada "💾 Salvar bancas" registra um snapshot com data. Comparando a variação
da banca com o lucro das apostas resolvidas no mesmo período, separamos o que
foi depósito/saque do que foi resultado de apostas.
"""
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

_DIR     = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(_DIR, "bets.db")
DATE_FMT = "%d/%m/%Y %H:%M"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_history():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bankroll_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            data      TEXT NOT NULL,
            bankrolls TEXT NOT NULL,
            total     REAL NOT NULL,
            nota      TEXT
        )""")


def load_history() -> list[dict]:
    init_history()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bankroll_history ORDER BY id ASC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["bankrolls"] = json.loads(d["bankrolls"])
        except Exception:
            d["bankrolls"] = {}
        out.append(d)
    return out


def add_snapshot(bankrolls: dict, total: float,
                 nota: str | None = None) -> dict | None:
    """
    Registra um snapshot das bancas. Se for idêntico ao último, não grava
    e retorna None. Caso contrário retorna os deltas vs o último registro.
    """
    hist = load_history()
    last = hist[-1] if hist else None
    bankrolls = {k: round(float(v), 2) for k, v in bankrolls.items()}
    total     = round(float(total), 2)

    if last and last["total"] == total and last["bankrolls"] == bankrolls:
        return None

    with _conn() as conn:
        conn.execute(
            "INSERT INTO bankroll_history (data,bankrolls,total,nota) "
            "VALUES (?,?,?,?)",
            (datetime.now().strftime(DATE_FMT),
             json.dumps(bankrolls, ensure_ascii=False), total, nota),
        )

    if last is None:
        return {"primeiro": True, "delta_total": 0.0,
                "deltas": {}, "data_anterior": None}

    casas  = set(bankrolls) | set(last["bankrolls"])
    deltas = {c: round(bankrolls.get(c, 0.0) - last["bankrolls"].get(c, 0.0), 2)
              for c in casas}
    return {
        "primeiro":      False,
        "delta_total":   round(total - last["total"], 2),
        "deltas":        {c: d for c, d in deltas.items() if d != 0},
        "data_anterior": last["data"],
    }


def delete_snapshot(snap_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM bankroll_history WHERE id=?", (snap_id,))


def _parse_dt(s: str):
    for fmt in (DATE_FMT, "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


def serie_diaria(history: list[dict], ate: date | None = None) -> dict:
    """
    Valor da banca por dia: o último snapshot de cada dia vale para o dia;
    dias sem registro herdam o valor anterior (forward-fill), do 1º snapshot
    até 'ate' (default: hoje). Retorna {date: total}.
    """
    por_dia: dict[date, float] = {}
    for h in history:  # ordenado por id — o último do dia sobrescreve
        dt = _parse_dt(h["data"])
        if dt is not None:
            por_dia[dt.date()] = h["total"]
    if not por_dia:
        return {}

    inicio = min(por_dia)
    fim    = ate or date.today()
    serie: dict[date, float] = {}
    atual  = por_dia[inicio]
    d = inicio
    while d <= fim:
        atual = por_dia.get(d, atual)
        serie[d] = atual
        d += timedelta(days=1)
    return serie


def analise_evolucao(history: list[dict], bets: list[dict]) -> dict | None:
    """
    Compara a variação da banca (1º → último snapshot) com o lucro das
    apostas resolvidas no período. A diferença é depósito/saque líquido.
    Precisa de >= 2 snapshots.
    """
    if len(history) < 2:
        return None

    first, last = history[0], history[-1]
    variacao = round(last["total"] - first["total"], 2)
    t0 = _parse_dt(first["data"])

    lucro = 0.0
    n_resolvidas = 0
    for b in bets:
        if b.get("resultado") not in ("ganhou", "perdeu") or b.get("lucro") is None:
            continue
        bd = _parse_dt(b.get("data") or "")
        if t0 is not None and bd is not None and bd < t0:
            continue
        lucro += b["lucro"]
        n_resolvidas += 1
    lucro = round(lucro, 2)

    depositos = round(variacao - lucro, 2)
    base = first["total"]
    return {
        "banca_inicial":      base,
        "banca_atual":        last["total"],
        "variacao":           variacao,
        "crescimento_pct":    round(variacao / base * 100, 2) if base > 0 else None,
        "lucro_apostas":      lucro,
        "n_resolvidas":       n_resolvidas,
        "depositos_liquidos": depositos,
        "roi_banca":          round(lucro / base * 100, 2) if base > 0 else None,
        "desde":              first["data"],
        "ate":                last["data"],
        "n_registros":        len(history),
    }
