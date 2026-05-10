"""
Integral Trading — Data Feed
Camada única de dados. Polygon + yfinance fallback.
Compatível com yfinance >= 0.2.50 (MultiIndex columns).

Suporte de intervalos:
  Diário:    get_bars(ticker, days, interval="1d")
  Intraday:  get_bars_intraday(ticker, interval="1h"|"4h"|"15m", days=30)
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Mapeamento de intervalos yfinance e limites de histórico
_INTERVAL_MAX_DAYS = {
    "1m":  7,
    "5m":  60,
    "15m": 60,
    "30m": 60,
    "1h":  720,   # yfinance limite real é 730 — usar 720 para margem (clock skew)
    "4h":  720,   # yfinance não tem 4h nativo — resample de 1h
    "1d":  None,  # sem limite prático
    "1wk": None,
}

# Mapeamento global: spot → ticker yfinance funcional (diário + intraday)
# GC=F (ouro futuros) replica XAUUSD=X com diferença mínima
_TICKER_MAP = {
    "XAUUSD=X": "GC=F",   # Ouro spot → futuros COMEX
    "XAGUSD=X": "SI=F",   # Prata spot → futuros COMEX
    "XPTUSD=X": "PL=F",   # Platina spot → futuros
    "XPDUSD=X": "PA=F",   # Paládio spot → futuros
}
# Alias para compatibilidade (intraday já usava este nome)
_INTRADAY_TICKER_MAP = _TICKER_MAP


class DataFeed:
    def __init__(self, polygon_key: str = ""):
        self.polygon_key  = polygon_key
        self._use_polygon = bool(polygon_key)

    # ─────────────────────────────────────────────────────────────────────────
    # API pública — barras diárias
    # ─────────────────────────────────────────────────────────────────────────

    def get_bars(self, ticker: str, days: int = 365, interval: str = "1d",
                 end_date: Optional[datetime] = None) -> pd.DataFrame:
        """Barras diárias (ou qualquer intervalo >= 1d)."""
        resolved = _TICKER_MAP.get(ticker, ticker)
        end   = end_date or datetime.utcnow()
        start = end - timedelta(days=days)
        return self._yfinance_bars(resolved, start, end, interval)

    def get_current_price(self, ticker: str) -> Optional[float]:
        try:
            df = self.get_bars(ticker, days=5)
            return float(df["close"].iloc[-1]) if not df.empty else None
        except Exception as e:
            logger.error("Erro preco " + ticker + ": " + str(e))
            return None

    def get_avg_volume(self, ticker: str, days: int = 20) -> Optional[float]:
        df = self.get_bars(ticker, days=days + 5)
        if df.empty or len(df) < 5:
            return None
        return float(df["volume"].tail(days).mean())

    def get_multiple_prices(self, tickers: list) -> dict:
        """Preços actuais para múltiplos tickers de uma vez."""
        result = {}
        try:
            data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
            if data is None or data.empty:
                return result
            if isinstance(data.columns, pd.MultiIndex):
                top = data.columns.get_level_values(0)
                if "Close" in top:
                    close = data["Close"]
                else:
                    return result
                for ticker in tickers:
                    if ticker in close.columns:
                        p = close[ticker].dropna()
                        if not p.empty:
                            result[ticker] = float(p.iloc[-1])
            else:
                data.columns = [str(c).lower() for c in data.columns]
                if "close" in data.columns and len(tickers) == 1:
                    p = data["close"].dropna()
                    if not p.empty:
                        result[tickers[0]] = float(p.iloc[-1])
        except Exception as e:
            logger.error("Erro get_multiple_prices: " + str(e))
        return result

    def get_daily_bars(self, tickers: list) -> dict:
        """High, low e close do dia actual para múltiplos tickers."""
        result = {}
        try:
            data = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
            if data is None or data.empty:
                return result

            if isinstance(data.columns, pd.MultiIndex):
                for ticker in tickers:
                    try:
                        high  = data["High"][ticker].dropna()
                        low   = data["Low"][ticker].dropna()
                        close = data["Close"][ticker].dropna()
                        if not high.empty:
                            result[ticker] = {
                                "high":  float(high.iloc[-1]),
                                "low":   float(low.iloc[-1]),
                                "close": float(close.iloc[-1]),
                            }
                    except Exception:
                        continue
            else:
                data.columns = [str(c).lower() for c in data.columns]
                if len(tickers) == 1 and "high" in data.columns:
                    result[tickers[0]] = {
                        "high":  float(data["high"].dropna().iloc[-1]),
                        "low":   float(data["low"].dropna().iloc[-1]),
                        "close": float(data["close"].dropna().iloc[-1]),
                    }
        except Exception as e:
            logger.error("Erro get_daily_bars: " + str(e))
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # API pública — barras intraday (H4 / H1 / M15)
    # ─────────────────────────────────────────────────────────────────────────

    def get_bars_intraday(self, ticker: str, interval: str = "1h",
                          days: int = 30) -> Optional[pd.DataFrame]:
        """
        Barras intraday para análise multi-timeframe.

        Intervalos suportados: "15m", "1h", "4h"

        "4h" é obtido por resample de barras "1h".
        Retorna None se os dados não estiverem disponíveis.

        Limites yfinance:
          15m → máx 60 dias de histórico
          1h  → máx 730 dias de histórico
          4h  → mesmo limite que 1h (resample)
        """
        if interval not in _INTERVAL_MAX_DAYS:
            logger.warning("Intervalo não suportado: " + interval)
            return None

        # Resolver ticker — metais spot não suportam intraday
        fetch_ticker = _INTRADAY_TICKER_MAP.get(ticker, ticker)

        # "4h" — busca como "1h" e faz resample
        fetch_interval = "1h" if interval == "4h" else interval

        max_days = _INTERVAL_MAX_DAYS[fetch_interval]
        if max_days is not None:
            days = min(days, max_days)

        end   = datetime.utcnow()
        start = end - timedelta(days=days)

        df = self._yfinance_bars(fetch_ticker, start, end, fetch_interval)

        if df is None or df.empty:
            logger.warning("Sem dados intraday para " + ticker +
                           " (fetch: " + fetch_ticker + " " + fetch_interval + ")")
            return None

        # Resample 1h → 4h se necessário
        if interval == "4h":
            df = self._resample_to_4h(df)
            if df is None or df.empty:
                return None

        return df

    def get_multi_timeframe(self, ticker: str) -> dict:
        """
        Retorna dados para análise NCI em múltiplos timeframes.

        Retorna:
          {
            "daily": pd.DataFrame,   # 150 dias
            "h4":    pd.DataFrame,   # 90 dias em barras 4h
            "h1":    pd.DataFrame,   # 30 dias em barras 1h
            "m15":   pd.DataFrame,   # 7 dias em barras 15m  (pode ser None)
          }
        """
        result = {}

        # Daily — 150 dias para SMA50 fiável
        result["daily"] = self.get_bars(ticker, days=150)

        # H4 — 90 dias
        result["h4"] = self.get_bars_intraday(ticker, interval="4h", days=90)

        # H1 — 30 dias
        result["h1"] = self.get_bars_intraday(ticker, interval="1h", days=30)

        # M15 — 7 dias (limite yfinance é 60 dias mas é ruidoso)
        result["m15"] = self.get_bars_intraday(ticker, interval="15m", days=7)

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Internos
    # ─────────────────────────────────────────────────────────────────────────

    def _yfinance_bars(self, ticker: str, start: datetime,
                       end: datetime, interval: str) -> pd.DataFrame:
        try:
            data = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval=interval,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
            )
        except Exception as e:
            logger.error("yfinance erro " + ticker + " " + interval + ": " + str(e))
            return pd.DataFrame()

        if data is None or data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            top = data.columns.get_level_values(0)
            if ticker.upper() in top:
                data = data[ticker.upper()]
            elif ticker in top:
                data = data[ticker]
            else:
                data.columns = data.columns.get_level_values(-1)

        data.columns = [str(c).lower().strip() for c in data.columns]

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(data.columns)):
            logger.warning("Colunas inesperadas para " + ticker + " " + interval +
                           ": " + str(list(data.columns)))
            return pd.DataFrame()

        data.index = pd.to_datetime(data.index).tz_localize(None)
        data = data[["open", "high", "low", "close", "volume"]].copy()

        for col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

        data.dropna(inplace=True)
        return data

    def _resample_to_4h(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Converte DataFrame de 1h para 4h via resample."""
        try:
            df.index = pd.to_datetime(df.index)
            df_4h = df.resample("4h").agg({
                "open":   "first",
                "high":   "max",
                "low":    "min",
                "close":  "last",
                "volume": "sum",
            }).dropna()
            return df_4h if not df_4h.empty else None
        except Exception as e:
            logger.warning("Resample 4h falhou: " + str(e))
            return None
