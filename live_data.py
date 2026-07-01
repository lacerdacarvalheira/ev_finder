"""
EV Finder — Dados ao vivo via ESPN API pública (sem chave necessária).
Fornece: placar, minuto, posse, finalizações, gols e estatísticas do torneio.
"""
import time
import requests
from difflib import SequenceMatcher

_ESPN_BASE  = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_LEAGUE_SLUGS = [
    "fifa.world",
    "world-cup",
    "usa.ncaa.w.soccer",  # fallback genérico (nunca deve chegar aqui)
]
_TIMEOUT = 8

_STAT_LABELS = {
    "possessionPct":      "Posse de bola",
    "totalShots":         "Finalizações",
    "shotsOnTarget":      "Chutes a gol",
    "blockedShots":       "Bloqueados",
    "foulsCommitted":     "Faltas",
    "yellowCards":        "Cartões amarelos",
    "redCards":           "Cartões vermelhos",
    "offsides":           "Impedimentos",
    "cornerKicks":        "Escanteios",
    "saves":              "Defesas do goleiro",
}


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _get(path: str, params: dict | None = None) -> dict | None:
    for slug in _LEAGUE_SLUGS:
        try:
            url  = f"{_ESPN_BASE}/{slug}/{path}"
            resp = requests.get(url, params=params or {}, timeout=_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return None


# ─── Scoreboard ───────────────────────────────────────────────────────────────

def fetch_scoreboard() -> list[dict]:
    """Retorna lista de jogos do dia (ativos e recentes)."""
    data = _get("scoreboard")
    if not data:
        return []

    events = []
    for ev in data.get("events", []):
        comp        = ev.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        status = ev.get("status", {})
        stype  = status.get("type", {})
        state  = stype.get("name", "")

        events.append({
            "espn_id":    ev.get("id", ""),
            "home_team":  home.get("team", {}).get("displayName", ""),
            "away_team":  away.get("team", {}).get("displayName", ""),
            "home_score": home.get("score", "0"),
            "away_score": away.get("score", "0"),
            "home_logo":  home.get("team", {}).get("logo", ""),
            "away_logo":  away.get("team", {}).get("logo", ""),
            "clock":      status.get("displayClock", ""),
            "period":     status.get("period", 0),
            "state":      state,
            "state_desc": stype.get("shortDetail", ""),
            "is_live":    state in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME",
                                    "STATUS_END_PERIOD"),
            "is_done":    stype.get("completed", False),
        })
    return events


def find_espn_event(home: str, away: str,
                    scoreboard: list[dict]) -> dict | None:
    """Casa ESPN melhor correspondente para home vs away."""
    best_score = 0.0
    best       = None
    for ev in scoreboard:
        s1 = _sim(home, ev["home_team"]) + _sim(away, ev["away_team"])
        s2 = _sim(home, ev["away_team"]) + _sim(away, ev["home_team"])
        s  = max(s1, s2)
        if s > best_score and s > 1.1:
            best_score = s
            best       = ev
    return best


# ─── Detalhes do jogo (stats + gols) ─────────────────────────────────────────

def fetch_game_detail(espn_id: str) -> dict:
    """
    Retorna dict com:
        stats   — {team_name: {stat_label: value}}
        goals   — lista de {team, clock, scorer, assist}
        events  — cartões, substituições
    """
    data = _get("summary", {"event": espn_id})
    if not data:
        return {}

    # — Stats do boxscore —
    boxscore = data.get("boxscore", {})
    stats: dict = {}
    for td in boxscore.get("teams", []):
        name  = td.get("team", {}).get("displayName", "?")
        s: dict = {}
        for stat in td.get("statistics", []):
            key   = stat.get("name", "")
            label = _STAT_LABELS.get(key, key)
            s[label] = stat.get("displayValue", "—")
        stats[name] = s

    # — Gols / eventos de pontuação —
    goals = []
    for play in data.get("plays", []):
        if not play.get("scoringPlay", False):
            continue
        participants = play.get("participants", [])
        scorer = participants[0].get("athlete", {}).get("displayName", "") if participants else ""
        assist = participants[1].get("athlete", {}).get("displayName", "") if len(participants) > 1 else ""
        goals.append({
            "team":   play.get("team", {}).get("displayName", ""),
            "clock":  play.get("clock", {}).get("displayValue", ""),
            "scorer": scorer,
            "assist": assist,
            "text":   play.get("text", ""),
        })

    # — Últimos eventos relevantes (cartões, substituições) —
    events_list = []
    for play in data.get("plays", [])[-15:]:
        ptype = play.get("type", {}).get("text", "")
        if any(k in ptype.lower() for k in ("card", "substitut", "yellow", "red")):
            events_list.append({
                "clock": play.get("clock", {}).get("displayValue", ""),
                "team":  play.get("team", {}).get("displayName", ""),
                "text":  play.get("text", ""),
            })

    # — Estatísticas do torneio (forma) —
    tournament_stats: dict = {}
    for team in data.get("standings", {}).get("entries", []):
        tname = team.get("team", {}).get("displayName", "")
        ts: dict = {}
        for stat in team.get("stats", []):
            name_s = stat.get("shortDisplayName", stat.get("name", ""))
            ts[name_s] = stat.get("displayValue", "—")
        tournament_stats[tname] = ts

    return {
        "stats":            stats,
        "goals":            goals,
        "events":           events_list,
        "tournament_stats": tournament_stats,
    }


# ─── Stats do torneio por time (acumuladas) ───────────────────────────────────

def fetch_team_tournament_stats(team_name: str) -> dict:
    """
    Tenta buscar estatísticas acumuladas do time no torneio.
    Retorna dict de stats ou {} se indisponível.
    """
    # ESPN athletes/teams endpoint for world cup
    data = _get("teams", {"limit": 200})
    if not data:
        return {}

    teams = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
    best_score = 0.0
    team_id    = None
    for t in teams:
        name = t.get("team", {}).get("displayName", "")
        s    = _sim(team_name, name)
        if s > best_score and s > 0.7:
            best_score = s
            team_id    = t.get("team", {}).get("id")

    if not team_id:
        return {}

    detail = _get(f"teams/{team_id}")
    if not detail:
        return {}

    return detail.get("team", {}).get("record", {})


# ─── Standings / Forma ────────────────────────────────────────────────────────

_standings_cache: dict = {"data": None, "ts": 0.0}
_STANDINGS_TTL = 3600  # 1 hora


def fetch_standings() -> dict[str, dict]:
    """
    Retorna standings do torneio como {team_name: {W, D, L, GF, GA, GD, form}}.
    Cache de 1 hora — um único request por hora independente de quantos jogos são analisados.
    """
    now = time.time()
    if _standings_cache["data"] is not None and now - _standings_cache["ts"] < _STANDINGS_TTL:
        return _standings_cache["data"]

    # Tenta o endpoint de standings da ESPN
    data = None
    for slug in _LEAGUE_SLUGS[:2]:
        try:
            url  = f"https://site.api.espn.com/apis/v2/sports/soccer/{slug}/standings"
            resp = requests.get(url, timeout=_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                break
        except Exception:
            continue

    if not data:
        return {}

    result: dict[str, dict] = {}
    for group in data.get("children", [data]):
        for entry in group.get("standings", {}).get("entries", []):
            team_name = entry.get("team", {}).get("displayName", "")
            if not team_name:
                continue
            stats_raw: dict = {}
            for stat in entry.get("stats", []):
                abbrev = stat.get("abbreviation", "")
                val    = stat.get("value")
                stats_raw[abbrev] = val

            result[team_name] = {
                "W":    int(stats_raw.get("W",  0) or 0),
                "D":    int(stats_raw.get("D",  0) or 0),
                "L":    int(stats_raw.get("L",  0) or 0),
                "GF":   int(stats_raw.get("PF", stats_raw.get("GF", 0)) or 0),
                "GA":   int(stats_raw.get("PA", stats_raw.get("GA", 0)) or 0),
                "Pts":  int(stats_raw.get("PTS", stats_raw.get("Pts", 0)) or 0),
            }

    _standings_cache["data"] = result
    _standings_cache["ts"]   = now
    return result


def get_team_standings(team_name: str, standings: dict[str, dict] | None = None) -> dict | None:
    """Retorna stats de um time pelo nome (fuzzy match). standings pode ser pré-carregado."""
    if standings is None:
        standings = fetch_standings()
    if not standings:
        return None

    best_score = 0.0
    best_entry = None
    for name, stats in standings.items():
        s = _sim(team_name, name)
        if s > best_score and s > 0.6:
            best_score = s
            best_entry = stats

    return best_entry


def format_team_record(stats: dict | None) -> str:
    """Formata record de um time como '3W-1D-0L | 8-3 GD:+5'."""
    if not stats:
        return "—"
    w, d, l = stats.get("W", 0), stats.get("D", 0), stats.get("L", 0)
    gf, ga  = stats.get("GF", 0), stats.get("GA", 0)
    pts     = stats.get("Pts", 0)
    gd      = gf - ga
    return f"{w}V {d}E {l}D | {gf}:{ga} (GD {gd:+d}) | {pts}pts"
