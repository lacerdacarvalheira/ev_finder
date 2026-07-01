"""
EV Finder — Tracker de Apostas (SQLite)
Auto-migra bets.json existente na primeira execução.
"""
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime
from loguru import logger

_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(_DIR, "bets.db")
BETS_JSON = os.path.join(_DIR, "bets.json")


# ─── Conexão ──────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Inicialização ────────────────────────────────────────────────────────────

def init_db():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            data           TEXT    NOT NULL,
            jogo           TEXT    NOT NULL,
            mercado        TEXT,
            selecao        TEXT,
            odd            REAL,
            stake          REAL,
            ev_pct         REAL,
            prob_real      REAL,
            casa           TEXT,
            resultado      TEXT    DEFAULT 'pendente',
            lucro          REAL,
            odd_fechamento REAL,
            clv            REAL,
            tipo_rec       TEXT
        )""")
        # Migração: adiciona tipo_rec se a tabela já existe sem ela
        try:
            conn.execute("ALTER TABLE bets ADD COLUMN tipo_rec TEXT")
        except Exception:
            pass


def _migrate_json():
    if not os.path.exists(BETS_JSON):
        return
    with _conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] > 0:
            return
    try:
        with open(BETS_JSON, "r", encoding="utf-8") as f:
            bets = json.load(f)
    except Exception as e:
        logger.warning(f"[bet_tracker] migração bets.json falhou: {e}")
        return
    with _conn() as conn:
        for b in bets:
            conn.execute(
                "INSERT INTO bets (data,jogo,mercado,selecao,odd,stake,ev_pct,"
                "prob_real,casa,resultado,lucro) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (b.get("data"), b.get("jogo"), b.get("mercado"), b.get("selecao"),
                 b.get("odd"), b.get("stake"), b.get("ev_pct"), b.get("prob_real"),
                 b.get("casa"), b.get("resultado", "pendente"), b.get("lucro")),
            )


init_db()
_migrate_json()


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def load_bets() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM bets ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]


def add_bet(jogo: str, mercado: str, selecao: str, odd: float,
            stake: float, ev_pct: float, prob_real: float, casa: str,
            tipo_rec: str | None = None) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO bets (data,jogo,mercado,selecao,odd,stake,ev_pct,"
            "prob_real,casa,resultado,tipo_rec) VALUES (?,?,?,?,?,?,?,?,?,'pendente',?)",
            (datetime.now().strftime("%d/%m/%Y %H:%M"),
             jogo, mercado, selecao,
             round(float(odd), 3), round(float(stake), 2),
             round(float(ev_pct), 2), round(float(prob_real), 1), casa, tipo_rec),
        )


def update_result(index: int, resultado: str,
                  odd_fechamento: float | None = None) -> None:
    bets = load_bets()
    if not (0 <= index < len(bets)):
        return
    bet = bets[index]

    lucro: float | None = None
    if resultado == "ganhou":
        lucro = round(bet["stake"] * (bet["odd"] - 1), 2)
    elif resultado == "perdeu":
        lucro = round(-bet["stake"], 2)

    clv: float | None = None
    if odd_fechamento and odd_fechamento > 1.001:
        clv = round((bet["odd"] / odd_fechamento - 1) * 100, 2)

    with _conn() as conn:
        conn.execute(
            "UPDATE bets SET resultado=?,lucro=?,odd_fechamento=?,clv=? WHERE id=?",
            (resultado, lucro, odd_fechamento, clv, bet["id"]),
        )


def delete_bet(index: int) -> None:
    bets = load_bets()
    if not (0 <= index < len(bets)):
        return
    with _conn() as conn:
        conn.execute("DELETE FROM bets WHERE id=?", (bets[index]["id"],))


# ─── Estatísticas ─────────────────────────────────────────────────────────────

def calc_stats(bets: list[dict]) -> dict:
    resolved = [b for b in bets if b["resultado"] in ("ganhou", "perdeu")]
    pending  = [b for b in bets if b["resultado"] == "pendente"]

    if not resolved:
        return {
            "total": len(bets), "resolvidas": 0, "pendentes": len(pending),
            "ganhos": 0, "taxa_acerto": 0.0,
            "total_apostado": 0.0, "lucro_total": 0.0, "roi": 0.0,
            "clv_medio": None,
        }

    ganhos         = sum(1 for b in resolved if b["resultado"] == "ganhou")
    total_apostado = sum(b["stake"] for b in resolved)
    lucro_total    = sum(b["lucro"] for b in resolved if b["lucro"] is not None)
    clv_vals       = [b["clv"] for b in resolved if b.get("clv") is not None]

    return {
        "total":          len(bets),
        "resolvidas":     len(resolved),
        "pendentes":      len(pending),
        "ganhos":         ganhos,
        "taxa_acerto":    round(ganhos / len(resolved) * 100, 1),
        "total_apostado": round(total_apostado, 2),
        "lucro_total":    round(lucro_total, 2),
        "roi":            round(lucro_total / total_apostado * 100, 1) if total_apostado > 0 else 0.0,
        "clv_medio":      round(sum(clv_vals) / len(clv_vals), 2) if clv_vals else None,
    }


def calc_stats_by(bets: list[dict], field: str) -> list[dict]:
    """Retorna lista de stats agrupados por 'mercado', 'casa', etc."""
    groups: dict[str, list] = defaultdict(list)
    for b in bets:
        key = b.get(field) or "—"
        groups[key].append(b)

    rows = []
    for key, group in groups.items():
        s = calc_stats(group)
        rows.append({
            field.capitalize(): key,
            "Apostas":    s["resolvidas"],
            "Acerto (%)": s["taxa_acerto"],
            "Apostado (R$)": s["total_apostado"],
            "Lucro (R$)": s["lucro_total"],
            "ROI (%)":    s["roi"],
        })
    rows.sort(key=lambda r: r["ROI (%)"], reverse=True)
    return rows
