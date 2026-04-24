"""
Integral Trading — Data Feed
Camada única de dados. Polygon + yfinance fallback.
Compatível com yfinance >= 0.2.50 (MultiIndex columns).
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DataFeed:
    def __init__(self, polygon_key: str = ""):
        self.polygon_key  = polygon_key
        self._use_polygon = bool(polygon_key)

    def get_bars(self, ticker: str, days: int = 365, interval: str = "1d",
                 end_date: Optional[datetime] = None) -> pd.DataFrame:
        end   = end_date or datetime.utcnow()
        start = end - timedelta(days=days)
        return self._yfinance_bars(ticker, start, end, interval)

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

    def _yfinance_bars(self, ticker: str, start: datetime,
                       end: datetime, interval: str) -> pd.DataFrame:
        try:
            data = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=interval,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
            )
        except Exception as e:
            logger.error("yfinance erro " + ticker + ": " + str(e))
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
            logger.warning("Colunas inesperadas para " + ticker + ": " + str(list(data.columns)))
            return pd.DataFrame()

        data.index = pd.to_datetime(data.index).tz_localize(None)
        data = data[["open", "high", "low", "close", "volume"]].copy()

        for col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

        data.dropna(inplace=True)
        return data
