"""
EV Finder — Módulo de acesso à The Odds API
Ferramenta pessoal e educacional — não para uso comercial.
"""
import requests
from typing import Optional
from utils import logger

BASE_URL = "https://api.the-odds-api.com/v4"

# Ligas de futebol disponíveis na API
# A Copa do Mundo 2026 pode aparecer sob uma das duas chaves abaixo dependendo da API —
# selecione ambas para garantir cobertura total.
SOCCER_LEAGUES: dict[str, str] = {
    "soccer_fifa_world_cup":                "Copa do Mundo FIFA 2026",
    "soccer_brazil_campeonato":             "Brasileirão Série A",
    "soccer_brazil_campeonato_b":           "Brasileirão Série B",
    "soccer_copa_libertadores":             "Copa Libertadores",
    "soccer_conmebol_copa_sudamericana":    "Copa Sul-Americana",
    "soccer_epl":                           "Premier League (Inglaterra)",
    "soccer_spain_la_liga":                 "La Liga (Espanha)",
    "soccer_italy_serie_a":                 "Serie A (Itália)",
    "soccer_germany_bundesliga":            "Bundesliga (Alemanha)",
    "soccer_france_ligue_one":              "Ligue 1 (França)",
    "soccer_uefa_champs_league":            "Champions League",
    "soccer_uefa_europa_league":            "Europa League",
    "soccer_usa_mls":                       "MLS (EUA)",
}

# Nomes legíveis por chave de casa de apostas
BOOKMAKER_DISPLAY: dict[str, str] = {
    # ── Referência / vig source ───────────────────────────────────────────────
    "pinnacle":         "Pinnacle",
    # ── Disponíveis no tier atual da API ─────────────────────────────────────
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
    # ── Casas fora do tier atual (mantidas como opções) ───────────────────────
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

# Mercados suportados e seus nomes em português
MARKET_OPTIONS: dict[str, str] = {
    # ── Mercados principais ──────────────────────────────
    "h2h":               "Resultado Final (1X2)",
    "spreads":           "Handicap Asiático",
    "totals":            "Total de Gols (todas as linhas)",
    "draw_no_bet":       "Empate Anula (DNB)",
    # ── Mercados secundários ─────────────────────────────
    "btts":              "Ambas Marcam (Sim/Não)",
    "doubleChance":      "Dupla Chance",
    "alternate_totals":  "Total de Gols (linhas alt.)",
    "alternate_spreads": "Handicap Asiático (alt.)",
    "team_totals":       "Gols por Time (O/U)",
    # ── Mercados de 1° tempo ─────────────────────────────
    "h2h_1st_half":      "Resultado 1° Tempo",
    "totals_1st_half":   "Total Gols 1° Tempo",
}

PINNACLE_KEY = "pinnacle"


def _validate_events(raw: list) -> list:
    """Valida eventos com pydantic — descarta entradas malformadas, registra warnings."""
    try:
        from models import Event
    except ImportError:
        return raw

    valid = []
    for item in raw:
        try:
            valid.append(Event.model_validate(item).model_dump())
        except Exception as e:
            event_id = item.get("id", "?") if isinstance(item, dict) else "?"
            logger.warning(f"[odds_api] evento {event_id} descartado: {e}")
    return valid


class OddsAPIError(Exception):
    pass


class OddsAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.requests_remaining: Optional[str] = None
        self.requests_used: Optional[str] = None

    def _get(self, path: str, params: dict):
        params["apiKey"] = self.api_key
        try:
            resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=20)
        except requests.exceptions.Timeout:
            raise OddsAPIError(
                "Tempo limite excedido ao conectar com a API. "
                "Verifique sua conexão com a internet."
            )
        except requests.exceptions.ConnectionError:
            raise OddsAPIError(
                "Sem conexão com a internet ou a API está fora do ar. "
                "Verifique sua rede e tente novamente."
            )

        self.requests_remaining = resp.headers.get("x-requests-remaining", "?")
        self.requests_used = resp.headers.get("x-requests-used", "?")

        if resp.status_code == 401:
            raise OddsAPIError(
                "Chave de API inválida ou expirada. "
                "Verifique em: https://the-odds-api.com/account"
            )
        if resp.status_code == 422:
            msg = resp.json().get("message", "Parâmetro inválido")
            raise OddsAPIError(f"Erro na requisição: {msg}")
        if resp.status_code == 429:
            raise OddsAPIError(
                "Limite de 500 requisições gratuitas atingido este mês. "
                "Aguarde a renovação mensal ou faça upgrade em the-odds-api.com"
            )
        if resp.status_code != 200:
            raise OddsAPIError(
                f"Erro inesperado da API (HTTP {resp.status_code}). "
                "Tente novamente mais tarde."
            )

        return resp.json()

    def get_odds(self, sport_key: str, markets: list[str],
                 use_cache: bool = True) -> list[dict]:
        """
        Busca odds de todos os bookmakers disponíveis para uma liga.
        Verifica cache (TTL 5min) antes de fazer request.
        Se um mercado não for suportado, remove-o automaticamente e tenta de novo.
        """
        from line_cache import get_cached, set_cache

        self.skipped_markets: list[str] = []
        self.from_cache = False

        if use_cache:
            cached = get_cached(sport_key, markets)
            if cached is not None:
                self.from_cache = True
                return cached

        remaining = list(markets)

        while remaining:
            try:
                params = {
                    "regions": "eu",
                    "markets": ",".join(remaining),
                    "oddsFormat": "decimal",
                }
                result = self._get(f"sports/{sport_key}/odds", params)
                result = _validate_events(result)
                set_cache(sport_key, remaining, result)
                return result
            except OddsAPIError as e:
                bad = self._bad_market(str(e), remaining)
                if bad:
                    self.skipped_markets.append(bad)
                    remaining.remove(bad)
                    continue
                raise

        return []

    @staticmethod
    def _bad_market(error_msg: str, markets: list[str]) -> Optional[str]:
        """Extract the unsupported market name from a 422 error message."""
        for m in markets:
            if m in error_msg:
                return m
        return None
