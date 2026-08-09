#!/usr/bin/env python3
"""
Atlas Investment Core Reference Data
======================================

Centralized REFERENCE data (fallback when yfinance unavailable).
All scripts should import from here, never redefine.

NOTE: This is FALLBACK data. Primary data should come from yfinance.
The 3 data modules (drawdown / recovery / risk_cluster) use yfinance first,
then fall back to these references if yfinance fails.

Usage:
    from core.reference_data import KNOWN_DRAWDOWNS, KNOWN_RECOVERY_TIMES, KNOWN_CORRELATIONS
"""

# Known historical maximum drawdowns (fallback data)
KNOWN_DRAWDOWNS = {
    "NVDA": {
        "max_dd_pct": -86.0,
        "peak_date": "2018-09-13",
        "trough_date": "2018-12-24",
        "current_dd_pct": -10.0,
        "days_to_recover": 800,
        "note": "参考 2018 加密货币熊市 + 2022 利率周期。最新数据需 yfinance。",
    },
    "MSFT": {
        "max_dd_pct": -52.0,
        "peak_date": "2000-12-28",
        "trough_date": "2009-03-09",
        "current_dd_pct": -5.0,
        "days_to_recover": 2900,
        "note": "参考 dot-com + 2008 金融危机。最新数据需 yfinance。",
    },
    "AAPL": {
        "max_dd_pct": -52.0,
        "peak_date": "2007-12-28",
        "trough_date": "2009-03-09",
        "current_dd_pct": -7.0,
        "days_to_recover": 1500,
        "note": "参考 2007-2009 金融危机。最新数据需 yfinance。",
    },
    "GOOGL": {
        "max_dd_pct": -45.0,
        "peak_date": "2007-11-05",
        "trough_date": "2009-03-09",
        "current_dd_pct": -5.0,
        "days_to_recover": 1400,
        "note": "参考 2008 金融危机。最新数据需 yfinance。",
    },
    "AMZN": {
        "max_dd_pct": -95.0,
        "peak_date": "1999-12-10",
        "trough_date": "2001-09-28",
        "current_dd_pct": -8.0,
        "days_to_recover": 2300,
        "note": "参考 dot-com 泡沫。最新数据需 yfinance。",
    },
    "META": {
        "max_dd_pct": -77.0,
        "peak_date": "2021-09-07",
        "trough_date": "2022-11-04",
        "current_dd_pct": -3.0,
        "days_to_recover": 800,
        "note": "参考 2022 利率周期 + AI 转型。最新数据需 yfinance。",
    },
    "TSLA": {
        "max_dd_pct": -73.0,
        "peak_date": "2021-11-04",
        "trough_date": "2023-01-06",
        "current_dd_pct": -10.0,
        "days_to_recover": 700,
        "note": "参考 2022 利率周期 + 需求担忧。最新数据需 yfinance。",
    },
    "0700.HK": {
        "max_dd_pct": -53.0,
        "peak_date": "2018-01-23",
        "trough_date": "2019-01-03",
        "current_dd_pct": -5.0,
        "days_to_recover": 600,
        "note": "参考 2018-2019 中国科技监管。最新数据需 yfinance。",
    },
    "BABA": {
        "max_dd_pct": -78.0,
        "peak_date": "2020-10-27",
        "trough_date": "2022-10-31",
        "current_dd_pct": -10.0,
        "days_to_recover": 900,
        "note": "参考 2021-2022 中国监管 + 中概股退市风险。最新数据需 yfinance。",
    },
}


# Known recovery time statistics (fallback data)
KNOWN_RECOVERY_TIMES = {
    "NVDA": {
        "max_dd": -86.0,
        "avg_recovery_50pct": 400,
        "avg_recovery_30pct": 250,
        "avg_recovery_20pct": 120,
        "avg_recovery_10pct": 60,
        "max_recovery_days": 800,
        "note": "高波动，恢复时间较长。最新数据需 yfinance。",
    },
    "MSFT": {
        "max_dd": -52.0,
        "avg_recovery_50pct": 1500,
        "avg_recovery_30pct": 400,
        "avg_recovery_20pct": 200,
        "avg_recovery_10pct": 100,
        "max_recovery_days": 2900,
        "note": "成熟公司，恢复稳定。最新数据需 yfinance。",
    },
    "AAPL": {
        "max_dd": -52.0,
        "avg_recovery_50pct": 800,
        "avg_recovery_30pct": 300,
        "avg_recovery_20pct": 150,
        "avg_recovery_10pct": 80,
        "max_recovery_days": 1500,
        "note": "消费品属性，恢复较快。最新数据需 yfinance。",
    },
    "GOOGL": {
        "max_dd": -45.0,
        "avg_recovery_50pct": 700,
        "avg_recovery_30pct": 280,
        "avg_recovery_20pct": 130,
        "avg_recovery_10pct": 70,
        "max_recovery_days": 1400,
        "note": "防御性较好。最新数据需 yfinance。",
    },
    "AMZN": {
        "max_dd": -95.0,
        "avg_recovery_50pct": 1200,
        "avg_recovery_30pct": 350,
        "avg_recovery_20pct": 180,
        "avg_recovery_10pct": 90,
        "max_recovery_days": 2300,
        "note": "高 beta，恢复差异大。最新数据需 yfinance。",
    },
    "META": {
        "max_dd": -77.0,
        "avg_recovery_50pct": 500,
        "avg_recovery_30pct": 250,
        "avg_recovery_20pct": 130,
        "avg_recovery_10pct": 70,
        "max_recovery_days": 800,
        "note": "高波动。最新数据需 yfinance。",
    },
    "TSLA": {
        "max_dd": -73.0,
        "avg_recovery_50pct": 450,
        "avg_recovery_30pct": 230,
        "avg_recovery_20pct": 120,
        "avg_recovery_10pct": 65,
        "max_recovery_days": 700,
        "note": "高波动，恢复差异极大。最新数据需 yfinance。",
    },
}


# Known correlations between symbols (long-term historical average)
KNOWN_CORRELATIONS = {
    ("NVDA", "MSFT"): 0.72,
    ("NVDA", "AAPL"): 0.65,
    ("MSFT", "AAPL"): 0.68,
    ("NVDA", "GOOGL"): 0.70,
    ("MSFT", "GOOGL"): 0.75,
    ("AAPL", "GOOGL"): 0.65,
    ("NVDA", "AMZN"): 0.68,
    ("MSFT", "AMZN"): 0.72,
    ("NVDA", "META"): 0.65,
    ("MSFT", "META"): 0.68,
    ("BABA", "0700.HK"): 0.78,
    ("BABA", "BIDU"): 0.82,
    ("JPM", "BAC"): 0.85,
    ("JPM", "WFC"): 0.83,
    ("BAC", "WFC"): 0.87,
    ("XOM", "CVX"): 0.88,
    ("KO", "PEP"): 0.75,
    ("JNJ", "PFE"): 0.65,
    ("META", "GOOGL"): 0.72,
    ("AMZN", "GOOGL"): 0.70,
}


# Risk clusters (for risk_cluster.py classification)
RISK_CLUSTERS = {
    "US Technology Growth": ["NVDA", "TSLA", "META", "AMZN", "NFLX"],
    "US Technology Mature": ["AAPL", "MSFT", "GOOGL", "ORCL", "CRM", "ADBE"],
    "US Financials": ["JPM", "BAC", "WFC", "C", "GS", "MS"],
    "US Energy": ["XOM", "CVX", "COP", "SLB"],
    "US Consumer Staples": ["KO", "PEP", "WMT", "PG", "JNJ"],
    "US Healthcare": ["JNJ", "PFE", "MRK", "UNH", "ABBV"],
    "China Internet": ["BABA", "0700.HK", "BIDU", "JD", "PDD"],
    "China EV": ["NIO", "XPEV", "LI", "BABA"],
}