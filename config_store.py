"""
EV Finder — Config compartilhado (config.json) e movimentos de saldo.

Movimento de saldo: quando uma aposta é registrada numa casa rastreada nas
bancas, o valor apostado sai do saldo (fica "congelado" na pendente); ao
marcar GANHOU o retorno (stake × odd) volta para o saldo; PERDEU não devolve.
"""
import json
import os

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


def aplicar_movimento_banca(casa: str, delta: float) -> float | None:
    """
    Soma delta ao saldo da casa nas bancas do config e recalcula o total.
    Retorna o novo saldo, ou None se a casa não está nas bancas (nada muda).
    O saldo nunca fica negativo.
    """
    if not casa or abs(delta) < 0.005:
        return None
    cfg = load_config()
    bankrolls = cfg.get("bankrolls") or {}
    if casa not in bankrolls:
        return None
    novo = max(0.0, round(bankrolls[casa] + delta, 2))
    bankrolls[casa] = novo
    cfg["bankrolls"] = bankrolls
    cfg["bankroll"]  = round(sum(bankrolls.values()), 2)
    save_config(cfg)
    return novo


def mover_saldo_ui(casa: str, delta: float) -> float | None:
    """Aplica o movimento e agenda a atualização do widget de saldo da
    sidebar para o próximo rerun do Streamlit."""
    novo = aplicar_movimento_banca(casa, delta)
    if novo is not None:
        import streamlit as st
        st.session_state.setdefault("_saldo_updates", {})[casa] = novo
    return novo
