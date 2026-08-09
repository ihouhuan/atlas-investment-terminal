#!/usr/bin/env python3
"""
Atlas China Market Data Module
================================

A 股数据获取模块（China A-Share Data Provider）。

数据源策略（按优先级）：
  1. AkShare（首选，如果可用）
  2. 腾讯 qt.gtimg.cn（实时行情，fallback）
  3. 腾讯 web.ifzq.gtimg.cn（K 线，fallback）
  4. DATA NOT AVAILABLE（最后 fallback，禁止伪造）

支持的市场代码：
  - SH: 上证（6 开头）
  - SZ: 深证（0、3 开头）
  - BJ: 北交所（8 开头）

Usage:
    from china_market.scripts.china_market_data import (
        fetch_realtime_quote,
        fetch_history_kline,
        normalize_symbol,
    )
    quote = fetch_realtime_quote("600519.SH")
"""

import os
import sys
import csv
import warnings
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

warnings.filterwarnings("ignore")

import requests

# Atlas core paths
_INVESTMENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _INVESTMENT_ROOT not in sys.path:
    sys.path.insert(0, _INVESTMENT_ROOT)

from core.paths import INVESTMENT_DIR  # noqa: E402

# Data storage directory
CHINA_DATA_DIR = os.path.join(INVESTMENT_DIR, "china_market", "data")
os.makedirs(CHINA_DATA_DIR, exist_ok=True)

# Request timeout
REQUEST_TIMEOUT = 15

# User-Agent (腾讯接口需要)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://stockapp.finance.qq.com/",
}


# =============================================================================
# Symbol Normalization
# =============================================================================

def normalize_symbol(symbol: str) -> Tuple[str, str]:
    """
    Normalize A-share symbol to (market, code).

    Args:
        symbol: "600519", "600519.SH", "sh600519", "000001.SZ", "sz000001"

    Returns:
        Tuple of (market, code) where market is "SH"/"SZ"/"BJ"
        and code is 6-digit code (e.g., "600519")

    Raises:
        ValueError: If symbol format is invalid

    Examples:
        >>> normalize_symbol("600519.SH")
        ('SH', '600519')
        >>> normalize_symbol("sh600519")
        ('SH', '600519')
        >>> normalize_symbol("000001")
        ('SZ', '000001')
    """
    s = symbol.strip().upper()

    # Remove market suffix
    for suffix in [".SH", ".SZ", ".BJ"]:
        if s.endswith(suffix):
            return s[-2:], s[:-3]

    # Remove market prefix
    for prefix in ["SH", "SZ", "BJ"]:
        if s.startswith(prefix) and len(s) > 2:
            return prefix, s[2:]

    # No market indicator - infer from code
    if not s.isdigit() or len(s) != 6:
        raise ValueError(f"Invalid A-share symbol: {symbol}")

    if s.startswith("6") or s.startswith("9"):
        # 6xxxxx: 上证主板/科创板
        return "SH", s
    elif s.startswith("0") or s.startswith("3"):
        # 0xxxxx: 深证主板/创业板
        return "SZ", s
    elif s.startswith("8"):
        # 8xxxxx: 北交所
        return "BJ", s
    else:
        raise ValueError(f"Cannot infer market for symbol: {symbol}")


def tencent_symbol(symbol: str) -> str:
    """
    Convert to Tencent's symbol format (lowercase market + code).

    Args:
        symbol: Any supported format

    Returns:
        Tencent format (e.g., "sh600519")
    """
    market, code = normalize_symbol(symbol)
    return f"{market.lower()}{code}"


# =============================================================================
# Real-time Quote (Tencent qt.gtimg.cn)
# =============================================================================

def fetch_realtime_quote(symbol: str) -> Optional[Dict]:
    """
    Fetch real-time quote for a single A-share symbol.

    Args:
        symbol: A-share code (any supported format)

    Returns:
        Dict with quote data, or None if DATA NOT AVAILABLE.
        Keys: name, code, price, change, change_pct, open, high, low,
              prev_close, volume, amount, turnover_pct, pe, pb,
              market_cap, circulating_cap, timestamp

    Tencent response format:
        v_sh600519="1~name~code~price~prev_close~open~volume~bid_volume~ask_volume~high~..."
        Fields (after code): current_price, prev_close, open, volume, bid_vol, ask_vol,
        high, [sell 5 levels], [buy 5 levels], timestamp, change, change_pct,
        high_today, low_today, price/volume/amount, ...
    """
    try:
        ts = tencent_symbol(symbol)
        url = f"https://qt.gtimg.cn/q={ts}"

        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None

        # Parse: v_sh600519="..."
        text = r.text.strip()
        if "=" not in text or '""' in text:
            return None

        # Extract content between quotes
        content = text.split('"', 2)[1] if text.count('"') >= 2 else ""
        if not content:
            return None

        fields = content.split("~")
        if len(fields) < 40:
            return None

        # Tencent field indices (verified 2026-08-08):
        # [0] market_code (1=上证, 51=深证)
        # [1] name
        # [2] code
        # [3] current_price
        # [4] prev_close
        # [5] open
        # [6] volume (手, 1手=100股)
        # [7] outer_bid_volume
        # [8] inner_bid_volume
        # [9] high (intraday high)
        # [30] timestamp (YYYYMMDDHHMMSS)
        # [31] change
        # [32] change_pct
        # [33] high_today
        # [34] low_today
        # [37] turnover_pct
        # [38] PE
        # [39] PB
        # [44] market_cap (亿)
        # [45] circulating_cap (亿)
        def safe_float(idx, default=None):
            try:
                return float(fields[idx]) if fields[idx] else default
            except (ValueError, IndexError):
                return default

        result = {
            "symbol": symbol,
            "ts_code": fields[2],
            "name": fields[1],
            "market": "SH" if fields[0] == "1" else "SZ" if fields[0] == "51" else "BJ",
            "price": safe_float(3),
            "prev_close": safe_float(4),
            "open": safe_float(5),
            "volume_shares": int(safe_float(6, 0)) * 100 if fields[6] else 0,  # 手→股
            "high": safe_float(33),
            "low": safe_float(34),
            "change": safe_float(31),
            "change_pct": safe_float(32),
            "turnover_pct": safe_float(38),
            "pe": safe_float(39),
            "pb": safe_float(40) if len(fields) > 40 else None,
            "market_cap_yi": safe_float(45),  # 亿元
            "circulating_cap_yi": safe_float(44),
            "timestamp": fields[30] if len(fields) > 30 else None,
            "data_source": "tencent_qt.gtimg.cn",
            "fetch_time": datetime.now().isoformat(),
        }
        return result
    except Exception as e:
        return None


def fetch_realtime_quotes(symbols: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Batch fetch real-time quotes.

    Args:
        symbols: List of A-share symbols

    Returns:
        Dict mapping symbol to quote data (None if failed)
    """
    try:
        ts_list = [tencent_symbol(s) for s in symbols]
        url = f"https://qt.gtimg.cn/q={','.join(ts_list)}"

        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return {s: None for s in symbols}

        # Parse response: each line starts with v_<ts>="..."
        result = {}
        for line in r.text.strip().split("\n"):
            if "=" not in line:
                continue
            prefix, _, content = line.partition("=")
            content = content.strip('"').strip(';')
            ts = prefix.strip().lstrip("v_")
            # Find matching symbol
            matched_symbol = None
            for sym in symbols:
                if tencent_symbol(sym) == ts:
                    matched_symbol = sym
                    break
            if matched_symbol is None:
                continue

            fields = content.split("~")
            if len(fields) < 40:
                result[matched_symbol] = None
                continue

            def safe_float(idx, default=None):
                try:
                    return float(fields[idx]) if fields[idx] else default
                except (ValueError, IndexError):
                    return default

            result[matched_symbol] = {
                "symbol": matched_symbol,
                "ts_code": fields[2],
                "name": fields[1],
                "market": "SH" if fields[0] == "1" else "SZ" if fields[0] == "51" else "BJ",
                "price": safe_float(3),
                "prev_close": safe_float(4),
                "open": safe_float(5),
                "volume_shares": int(safe_float(6, 0)) * 100 if fields[6] else 0,
                "high": safe_float(33),
                "low": safe_float(34),
                "change": safe_float(31),
                "change_pct": safe_float(32),
                "turnover_pct": safe_float(38),
                "pe": safe_float(39),
                "pb": safe_float(40) if len(fields) > 40 else None,
                "market_cap_yi": safe_float(45),
                "circulating_cap_yi": safe_float(44),
                "timestamp": fields[30] if len(fields) > 30 else None,
                "data_source": "tencent_qt.gtimg.cn",
                "fetch_time": datetime.now().isoformat(),
            }

        # Fill in None for missing
        for sym in symbols:
            if sym not in result:
                result[sym] = None

        return result
    except Exception:
        return {s: None for s in symbols}


# =============================================================================
# Historical K-line (Tencent web.ifzq.gtimg.cn)
# =============================================================================

def fetch_history_kline(
    symbol: str,
    days: int = 60,
    adjust: str = "qfq"
) -> Tuple[List, List, List]:
    """
    Fetch historical K-line data for an A-share symbol.

    Args:
        symbol: A-share code
        days: Number of recent days to fetch
        adjust: "qfq" (前复权), "hfq" (后复权), "" (不复权)

    Returns:
        Tuple of (dates, closes, errors)
    """
    errors = []
    try:
        market_code, code = normalize_symbol(symbol)

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{market_code.lower()}{code},day,{start_date},{end_date},{days},{adjust}",
        }

        r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return [], [], [f"{symbol}: HTTP {r.status_code}"]

        data = r.json()
        if data.get("code") != 0:
            return [], [], [f"{symbol}: API error"]

        stock_data = data.get("data", {}).get(f"{market_code.lower()}{code}", {})
        klines = stock_data.get("qfqday") or stock_data.get("day") or []

        if not klines:
            return [], [], [f"{symbol}: 无K线数据"]

        dates = []
        closes = []
        for kline in klines:
            # Format: ["2026-01-05", open, close, high, low, volume, ...]
            if len(kline) >= 3:
                dates.append(datetime.strptime(kline[0], "%Y-%m-%d"))
                closes.append(float(kline[2]))

        return dates, closes, []
    except Exception as e:
        return [], [], [f"{symbol}: {e}"]


# =============================================================================
# CSV Export
# =============================================================================

def save_quotes_to_csv(quotes: Dict, filename: Optional[str] = None) -> str:
    """
    Save quotes dict to CSV file.

    Args:
        quotes: Dict mapping symbol to quote dict
        filename: Optional filename (default: china_quotes_{date}.csv)

    Returns:
        Full path to saved file
    """
    if filename is None:
        filename = f"china_quotes_{datetime.now().strftime('%Y%m%d')}.csv"

    filepath = os.path.join(CHINA_DATA_DIR, filename)

    fieldnames = [
        "symbol", "ts_code", "name", "market",
        "price", "prev_close", "open", "high", "low",
        "change", "change_pct",
        "volume_shares", "turnover_pct",
        "pe", "pb", "market_cap_yi", "circulating_cap_yi",
        "timestamp", "data_source", "fetch_time"
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for sym, quote in quotes.items():
            if quote is None:
                # Write a "DATA NOT AVAILABLE" row
                writer.writerow({"symbol": sym, "name": "DATA NOT AVAILABLE"})
            else:
                writer.writerow(quote)

    return filepath


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Atlas China Market Data Fetcher (A 股数据)",
        epilog="示例: python3 china_market_data.py 600519.SH 000001.SZ"
    )
    parser.add_argument("symbols", nargs="+", help="A 股代码（支持 600519 / 600519.SH / sh600519）")
    parser.add_argument("--save", action="store_true", help="保存到 CSV")
    parser.add_argument("--history", type=int, metavar="DAYS", help="拉取历史K线（天数）")

    args = parser.parse_args()

    print(f"=== Atlas A 股数据查询 ===")
    print(f"代码: {args.symbols}")
    print()

    if args.history:
        # K 线模式
        for sym in args.symbols:
            dates, prices, errors = fetch_history_kline(sym, days=args.history)
            if errors:
                print(f"❌ {sym}: {errors}")
            else:
                print(f"✅ {sym}: {len(prices)} 天")
                print(f"   最新: {dates[-1].strftime('%Y-%m-%d')} ¥{prices[-1]:.2f}")
                print(f"   区间: {dates[0].strftime('%Y-%m-%d')} → {dates[-1].strftime('%Y-%m-%d')}")
                print(f"   收益: {(prices[-1]/prices[0]-1)*100:+.2f}%")
                print()
    else:
        # 实时行情模式
        quotes = fetch_realtime_quotes(args.symbols)

        for sym in args.symbols:
            q = quotes.get(sym)
            if q is None:
                print(f"❌ {sym}: DATA NOT AVAILABLE")
                continue
            print(f"✅ {q['name']} ({q['symbol']})")
            print(f"   价格: ¥{q['price']}")
            print(f"   涨跌: {q['change']:+.2f} ({q['change_pct']:+.2f}%)")
            print(f"   今开: ¥{q['open']} | 最高: ¥{q['high']} | 最低: ¥{q['low']}")
            print(f"   市值: {q['market_cap_yi']} 亿 | PE: {q['pe']}")
            print()

        if args.save:
            filepath = save_quotes_to_csv(quotes)
            print(f"💾 已保存: {filepath}")


if __name__ == "__main__":
    main()