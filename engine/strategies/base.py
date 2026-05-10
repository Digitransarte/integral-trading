"""Integral Trading — Estratégia Base"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    ticker: str
    strategy_name: str
    signal_date: datetime
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    score: float
    catalyst: str = ""
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def risk_pct(self):
        return abs(self.entry_price - self.stop_loss) / self.entry_price

    @property
    def reward_1_pct(self):
        return abs(self.target_1 - self.entry_price) / self.entry_price

    @property
    def risk_reward_1(self):
        return self.reward_1_pct / self.risk_pct if self.risk_pct else 0


@dataclass
class BacktestResult:
    ticker: str
    strategy_name: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime]
    exit_price: Optional[float]
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0


class BaseStrategy(ABC):
    name: str = "Base Strategy"
    description: str = ""
    version: str = "1.0"
    default_stop_loss_pct: float = 0.08
    default_hold_days: int = 20
    min_score: float = 60.0

    @abstractmethod
    def scan(self, ticker: str, df: pd.DataFrame) -> bool: ...

    @abstractmethod
    def generate_signal(self, ticker: str, df: pd.DataFrame) -> Optional[Signal]: ...

    def manage_position(self, signal: Signal, current_price: float,
                        days_held: int, df: pd.DataFrame) -> str:
        if current_price <= signal.stop_loss:
            return "stop"
        if current_price >= signal.target_1:
            return "exit"
        if days_held >= self.default_hold_days:
            return "exit"
        return "hold"

    def get_position_size(self, portfolio_value: float, price: float,
                          risk_pct: float = None) -> int:
        from config import MAX_POSITION_SIZE_PCT
        return max(1, int(portfolio_value * MAX_POSITION_SIZE_PCT / price))

    def __repr__(self):
        return f"<Strategy: {self.name} v{self.version}>"
