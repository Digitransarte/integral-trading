# Integral Trading

Sistema de análise e decisão de trading. Actualmente em **paper trading** (Alpaca Paper API).

## Stack
- **Dashboard**: Streamlit (`dashboard/app.py`, páginas em `dashboard/pages/`)
- **API**: FastAPI (`api/main.py`, rotas em `api/routes/`)
- **Engine**: lógica de análise e decisão em `engine/`
- **DB**: SQLite em `data/integral_trading.db`
- **Config**: todas as chaves em `.env` → lidas por `config.py`

## APIs externas
- **Polygon** — dados de mercado (`POLYGON_API_KEY`)
- **Anthropic** — decisões qualitativas no `engine/decision_engine.py` (`ANTHROPIC_API_KEY`)
- **Alpaca** — execução paper trading (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`)

## Como correr
```bash
# Dashboard Streamlit (porta 8501)
streamlit run dashboard/app.py

# API FastAPI (porta 8000)
uvicorn api.main:app --reload

# Scripts autónomos
python run_scanner.py
python run_tracker.py
python scheduled_scan.py
```

## Estrutura do engine
| Ficheiro | Responsabilidade |
|---|---|
| `decision_engine.py` | Pipeline EP: filtros → catalisador → macro → decisão Claude |
| `nci_analyzer.py` | Análise técnica NCI/SMC multi-timeframe (D/H4/H1) |
| `scanner.py` | Scan de oportunidades no universo de activos |
| `regime_detector.py` | Detecção de regime de mercado |
| `macro_analyzer.py` | Contexto macro (DXY, yields, VIX) |
| `backtester.py` / `nci_backtester.py` | Backtesting de estratégias |
| `database.py` | Acesso SQLite centralizado |
| `data_feed.py` | Feed de dados via Polygon |

## Estratégias
- **EP** (Earnings Play): config em `data/strategies/ep_default.yaml`, especialista em `engine/specialists/ep_specialist.py`, conhecimento em `knowledge/ep_strategy.py`
- **NCI/SMC**: config em `knowledge/nci_strategy.json`, conhecimento em `knowledge/smc_knowledge.json`

## Regras críticas
1. **NUNCA** fazer `git push` sem confirmação explícita
2. **NUNCA** modificar `.env` — só `.env.example`
3. **NUNCA** apagar ficheiros em `data/` sem confirmação
4. **NUNCA** fazer deploy direto para o VPS — esse passo é sempre manual via SSH
5. **NÃO** criar ficheiros `.bak` — usar `git stash` ou commits intermédios
6. Modificações ao `engine/` podem afectar decisões de trading — rever com atenção antes de commitar

## Produção
VPS Hetzner. Deploy feito manualmente após revisão: `git push` local → SSH no VPS → `git pull` + restart serviços.
