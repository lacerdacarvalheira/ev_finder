"""
EV Finder — Cache de odds e rastreamento de movimento de linha.

Cache: evita gastar requests repetindo a mesma busca em < CACHE_TTL segundos.
Snapshots: salva histórico de odds a cada busca para análise de movimento.
"""
import json
import os
import time
from datetime import datetime, timezone
from loguru import logger

_DIR          = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE   = os.path.join(_DIR, "odds_cache.json")
_HISTORY_FILE = os.path.join(_DIR, "line_history.json")
CACHE_TTL     = 300  # 5 minutos


def _parse_ts(iso_str: str) -> float:
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


# ─── Cache de API ─────────────────────────────────────────────────────────────

def _cache_key(sport_key: str, markets: list[str]) -> str:
    return f"{sport_key}|{','.join(sorted(markets))}"


def get_cached(sport_key: str, markets: list[str]) -> list[dict] | None:
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        entry = cache.get(_cache_key(sport_key, markets))
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
    except Exception as e:
        logger.warning(f"[line_cache] get_cached falhou: {e}")
    return None


def set_cache(sport_key: str, markets: list[str], data: list[dict]) -> None:
    cache: dict = {}
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
    # remove entradas expiradas antes de salvar
    now = time.time()
    cache = {k: v for k, v in cache.items() if now - v.get("ts", 0) < CACHE_TTL * 2}
    cache[_cache_key(sport_key, markets)] = {"ts": now, "data": data}
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.warning(f"[line_cache] set_cache falhou: {e}")


def get_cache_age(sport_key: str, markets: list[str]) -> int | None:
    """Idade do cache em segundos, ou None se não existe."""
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        entry = cache.get(_cache_key(sport_key, markets))
        if entry:
            return int(time.time() - entry["ts"])
    except Exception:
        pass
    return None


def invalidate_cache() -> None:
    try:
        if os.path.exists(_CACHE_FILE):
            os.remove(_CACHE_FILE)
    except Exception:
        pass


# ─── Histórico de odds (movimento de linha) ───────────────────────────────────

def save_snapshot(events: list[dict]) -> None:
    """Salva um snapshot das odds atuais para rastrear movimento de linha."""
    history: dict = {}
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    ts = datetime.now(timezone.utc).isoformat()

    for ev in events:
        gid = ev.get("id", "")
        if not gid:
            continue

        if gid not in history:
            history[gid] = {
                "home":           ev.get("home_team"),
                "away":           ev.get("away_team"),
                "commence_time":  ev.get("commence_time"),
                "snapshots":      [],
            }

        snap: dict = {"ts": ts, "odds": {}}
        for bk in ev.get("bookmakers", []):
            bk_key = bk["key"]
            snap["odds"][bk_key] = {}
            for mkt in bk.get("markets", []):
                mkt_key = mkt["key"]
                # salva todos os outcomes, incluindo point para handicap e totals
                snap["odds"][bk_key][mkt_key] = [
                    {"name": o["name"], "price": o["price"], "point": o.get("point")}
                    for o in mkt.get("outcomes", [])
                ]

        history[gid]["snapshots"].append(snap)
        # Manter no máximo 48 snapshots por jogo (~24h a cada 30min)
        if len(history[gid]["snapshots"]) > 48:
            history[gid]["snapshots"] = history[gid]["snapshots"][-48:]

    # remove jogos cujo commence_time passou há mais de 7 dias
    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    history = {
        gid: data for gid, data in history.items()
        if _parse_ts(data.get("commence_time", "")) > cutoff
    }

    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f)
    except Exception as e:
        logger.warning(f"[line_cache] save_snapshot falhou: {e}")


def get_line_history(game_id: str) -> dict:
    if not os.path.exists(_HISTORY_FILE):
        return {}
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history.get(game_id, {})
    except Exception:
        return {}


def detect_steam_moves(game_id: str, bookmaker: str = "pinnacle",
                       min_pp: float = 3.0) -> list[dict]:
    """
    Detecta steam moves: mudanças de probabilidade >= min_pp entre os dois
    últimos snapshots. Retorna lista ordenada por magnitude de movimento.
    """
    history   = get_line_history(game_id)
    snapshots = history.get("snapshots", [])
    if len(snapshots) < 2:
        return []

    snap_prev = snapshots[-2]
    snap_curr = snapshots[-1]
    prev_bk   = snap_prev.get("odds", {}).get(bookmaker, {})
    curr_bk   = snap_curr.get("odds", {}).get(bookmaker, {})

    moves = []
    for mkt_key in set(prev_bk) & set(curr_bk):
        prev_map = {o["name"]: o["price"] for o in prev_bk.get(mkt_key, [])}
        curr_map = {o["name"]: o["price"] for o in curr_bk.get(mkt_key, [])}

        for name in set(prev_map) & set(curr_map):
            p_then = prev_map[name]
            p_now  = curr_map[name]
            if p_then <= 1.0 or p_now <= 1.0:
                continue
            prob_then = 1.0 / p_then
            prob_now  = 1.0 / p_now
            pp        = (prob_now - prob_then) * 100

            if abs(pp) >= min_pp:
                moves.append({
                    "market":     mkt_key,
                    "outcome":    name,
                    "price_then": round(p_then, 3),
                    "price_now":  round(p_now,  3),
                    "prob_then":  round(prob_then * 100, 1),
                    "prob_now":   round(prob_now  * 100, 1),
                    "pp_move":    round(pp, 1),
                    "direction":  "↑ Steam" if pp > 0 else "↓ Drift",
                })

    moves.sort(key=lambda x: abs(x["pp_move"]), reverse=True)
    return moves
