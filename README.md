# EV Finder — Copa do Mundo 2026

Ferramenta pessoal para identificar apostas com **Valor Esperado positivo (EV+)** comparando odds de casas de apostas com as odds da Pinnacle (referência sharp).

> **Uso pessoal e educacional.** Não garante lucro. Apostas envolvem risco.

---

## Funcionalidades

| Aba | O que faz |
|-----|-----------|
| 🔍 Buscar EV+ | Calcula EV de cada mercado comparando com Pinnacle sem vig; sugere Kelly |
| ⚡ Arbitragem | Detecta oportunidades de arb e avisa sobre mercados correlacionados |
| 📅 Jogos de Hoje | Cards com análise dos jogos do dia e classificação ESPN |
| 📊 Comparativo de Odds | Tabela de odds por casa + gráfico de movimento de linha + steam moves |
| 📋 Tracker | Registra apostas, calcula ROI, exporta CSV, backtest por tipo |
| 📈 Simulação | Monte Carlo de variância + calculadora Kelly para portfólio |
| 📉 Analytics | Calibração de EV, ROI cumulativo, bankroll real vs esperado, CLV |
| 👁️ Watchlist | Alerta quando odds alvo são encontradas numa busca |

---

## Pré-requisitos

- Python 3.11+
- Chave de API: [The Odds API](https://the-odds-api.com) — plano gratuito (500 req/mês)

---

## Instalação local

```bash
git clone https://github.com/lacerdacarvalheira/ev_finder.git
cd ev_finder

# cria ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
streamlit run app.py
```

Acesse em `http://localhost:8501`. Cole sua chave da API na sidebar e salve.

---

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `ODDS_API_KEY` | Chave The Odds API (alternativa ao campo na sidebar) |
| `TELEGRAM_TOKEN` | Token do bot para alertas (opcional) |
| `TELEGRAM_CHAT_ID` | Chat ID para receber alertas (opcional) |

```bash
# Windows PowerShell
$env:ODDS_API_KEY = "sua_chave_aqui"
streamlit run app.py
```

---

## Deploy no Streamlit Community Cloud (gratuito)

1. Faça fork do repositório no GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io) e conecte o repositório
3. Em **Settings → Secrets**, adicione:

```toml
ODDS_API_KEY = "sua_chave_aqui"

# Opcional
TELEGRAM_TOKEN   = ""
TELEGRAM_CHAT_ID = ""
```

4. Clique em **Deploy** — o app ficará acessível em qualquer dispositivo

---

## Estrutura do projeto

```
ev_finder/
├── app.py                  # UI principal — sidebar e roteamento de abas
├── tabs/                   # Um módulo por aba (render(cfg: dict))
│   ├── ev_tab.py
│   ├── arb_tab.py
│   ├── today_tab.py
│   ├── compare_tab.py
│   ├── tracker_tab.py
│   ├── sim_tab.py
│   ├── analytics_tab.py
│   └── watchlist_tab.py
├── ev_calculator.py        # Remoção de vig, EV, Kelly bruto
├── arb_finder.py           # Detecção de arbitragem + correlações
├── bet_tracker.py          # CRUD apostas em SQLite (bets.db)
├── line_cache.py           # Cache de odds + histórico + steam moves
├── live_data.py            # Standings ESPN (cache 1h)
├── odds_api.py             # Cliente The Odds API com retry
├── models.py               # Pydantic: Event, Bookmaker, Market, Outcome
├── notifications.py        # Alertas Telegram
├── watchlist.py            # CRUD watchlist em JSON
├── game_analyst.py         # Análise e recomendação de jogos
├── utils.py                # Funções utilitárias + logger loguru
├── test_core.py            # Suite de testes (python test_core.py)
└── requirements.txt
```

---

## Testes

```bash
python test_core.py
```

Suite standalone sem dependências externas. Cobre EV, Kelly, DNB, vig removal, arb, watchlist, steam moves e calibração.

---

## Fórmulas

**EV+**
```
EV = prob_real × odd_casa - 1
```
onde `prob_real` vem das odds da Pinnacle após remoção de vig.

**Kelly**
```
kelly = EV / (odd - 1)
```
Use frações de Kelly (¼ ou ½) para gestão de risco.

**DNB (Draw No Bet)**
```
prob_dnb = prob_fav / (1 - prob_empate)
```

---

## Aviso legal

Ferramenta para uso pessoal e educacional. O autor não se responsabiliza por perdas financeiras. Verifique as leis de apostas da sua jurisdição antes de usar.
