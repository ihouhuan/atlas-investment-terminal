#!/usr/bin/env python3
"""
Atlas Investment Core Market Data
==================================

Centralized market data fetching utilities.
All scripts should import these functions, never redefine.

Usage:
    from core.market_data import fetch_price_series, fetch_current_price
"""

import warnings
from datetime import datetime
from typing import List, Tuple, Optional

# Suppress yfinance warnings
warnings.filterwarnings("ignore")

import yfinance as yf


def fetch_price_series(symbol: str, period: str = "5y") -> Tuple[List, List, List]:
    """
    Fetch historical price series for a symbol.

    Args:
        symbol: Ticker symbol (e.g., "NVDA", "AAPL")
        period: Yahoo Finance period (e.g., "1y", "5y", "10y", "max")

    Returns:
        Tuple of (dates, close_prices, errors)
        - dates: List of datetime objects
        - close_prices: List of float
        - errors: List of error messages (empty if successful)
    """
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, auto_adjust=True)
        if hist.empty:
            return [], [], [f"{symbol} 无历史数据"]
        dates = hist.index.to_pydatetime().tolist()
        prices = hist["Close"].tolist()
        return dates, prices, []
    except Exception as e:
        return [], [], [f"{symbol}: {e}"]


def fetch_current_price(symbol: str) -> Optional[float]:
    """
    Fetch latest closing price for a symbol.

    Args:
        symbol: Ticker symbol

    Returns:
        Latest close price as float, or None if failed
    """
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="5d", auto_adjust=True)
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        return None


def fetch_returns(symbol: str, period: str = "1y") -> Tuple[List, List, List]:
    """
    Fetch daily returns for a symbol.

    Args:
        symbol: Ticker symbol
        period: Yahoo Finance period

    Returns:
        Tuple of (dates, returns_pct, errors)
        - returns_pct: Daily percentage returns
    """
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, auto_adjust=True)
        if hist.empty:
            return [], [], [f"{symbol} 无历史数据"]
        dates = hist.index.to_pydatetime().tolist()
        closes = hist["Close"].tolist()
        returns = [0.0]
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                ret = (closes[i] - closes[i-1]) / closes[i-1] * 100.0
                returns.append(ret)
            else:
                returns.append(0.0)
        return dates, returns, []
    except Exception as e:
        return [], [], [f"{symbol}: {e}"]


def fetch_ticker_info(symbol: str) -> dict:
    """
    Fetch ticker info (company metadata, financials).

    Args:
        symbol: Ticker symbol

    Returns:
        Dict with ticker info, or empty dict if failed
    """
    try:
        t = yf.Ticker(symbol)
        return t.info or {}
    except Exception:
        return {}