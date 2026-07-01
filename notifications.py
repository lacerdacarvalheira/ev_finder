"""
EV Finder — Notificações opcionais via Telegram.
Configurar: telegram_token e telegram_chat_id em config.json (ou no sidebar).
Obter token: fale com @BotFather no Telegram.
Obter chat_id: envie /start para o bot e acesse:
  https://api.telegram.org/bot<TOKEN>/getUpdates
"""
import requests
from utils import logger

_TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 5


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Envia mensagem via Telegram. Retorna True se bem-sucedido."""
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            _TELEGRAM_URL.format(token=token),
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"[notifications] Telegram HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"[notifications] Telegram falhou: {e}")
        return False


def format_ev_alert(opportunities: list[dict], threshold: float) -> str:
    """Formata mensagem de alerta EV+ para Telegram (HTML)."""
    n = len(opportunities)
    best = opportunities[0]
    lines = [
        f"🔍 <b>EV Finder — {n} oportunidade(s) com EV ≥ {threshold:.0f}%</b>",
        "",
        f"🏆 <b>Melhor:</b> {best.get('Seleção', '?')} @ {best.get('Casa', '?')}",
        f"   Odd: <b>{best.get('Odd Casa', 0):.3f}</b>  |  EV: <b>+{best.get('EV (%)', 0):.1f}%</b>",
        f"   Jogo: {best.get('Jogo', '?')} — {best.get('Horário (BRT)', '?')}",
    ]
    if n > 1:
        lines.append("")
        for opp in opportunities[1:4]:
            lines.append(
                f"• {opp.get('Seleção', '?')} @ {opp.get('Casa', '?')} "
                f"(EV +{opp.get('EV (%)', 0):.1f}%)"
            )
        if n > 4:
            lines.append(f"… +{n - 4} oportunidade(s) adicionais")
    return "\n".join(lines)
