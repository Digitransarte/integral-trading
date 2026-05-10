"""
Integral Trading — Configuração Global
Lê variáveis de ambiente do ficheiro .env na raiz do projecto.
"""
import os
from pathlib import Path

# Carregar .env automaticamente se existir
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "integral_trading.db"
STRATEGIES_DIR = DATA_DIR / "strategies"

POLYGON_API_KEY   = os.getenv("POLYGON_API_KEY",   "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY",    "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

ALPACA_PAPER    = True
ALPACA_BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"

MAX_POSITION_SIZE_PCT = 0.05
MAX_OPEN_POSITIONS    = 10
DEFAULT_STOP_LOSS_PCT = 0.08
DEFAULT_LOOKBACK_DAYS = 365
MARKET_OPEN    = "09:30"
MARKET_CLOSE   = "16:00"
TIMEZONE       = "America/New_York"
API_HOST       = "0.0.0.0"
API_PORT       = 8000
DASHBOARD_PORT = 8501
