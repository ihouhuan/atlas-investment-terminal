#!/usr/bin/env python3
"""
Atlas Drawdown Analyzer v10
历史回撤分析

输入：股票代码列表
输出：每只股票的最大回撤 / 当前回撤 / 恢复时间

降级策略：
  - 尝试 yfinance 拉取真实历史数据
  - 失败时使用【已知历史回撤参考值】（来源：公开历史事件，标记为参考）
  - 始终明确告知数据源
"""

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timedelta

# Atlas core utilities (v10.5 unified)
# Add investment/ to sys.path so 'core' module is importable
import os as _os
_investment_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _investment_root not in sys.path:
    sys.path.insert(0, _investment_root)
del _os, _investment_root

from core.paths import stress_test_report_path, today_str
from core.market_data import fetch_price_series
from core.reference_data import KNOWN_DRAWDOWNS

warnings.filterwarnings('ignore')

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# ----------------------------------------------------------------------------
# 已知历史回撤参考值（仅在 yfinance 不可用时使用）
# 来源：公开历史记录（Wikipedia、公开财经资料）
# 标记为【参考】，不是实时数据
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
from core.paths import 压力测试_DIR as REPORTS_DIR
os.makedirs(REPORTS_DIR, exist_ok=True)


# ----------------------------------------------------------------------------
# 数据获取
# ----------------------------------------------------------------------------

def fetch_price_series(symbol: str, period: str = "5y") -> tuple:
    """
    拉取历史价格序列。
    返回 (dates, close_prices, errors)
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


# ----------------------------------------------------------------------------
# 回撤计算
# ----------------------------------------------------------------------------

def compute_drawdowns(dates: list, prices: list) -> list:
    """
    计算每个时间点的回撤。
    return drawdown_pct series (negative or 0)
    """
    if not prices:
        return []
    running_max = prices[0]
    dds = []
    for p in prices:
        running_max = max(running_max, p)
        dd = (p - running_max) / running_max * 100.0 if running_max > 0 else 0.0
        dds.append(dd)
    return dds


def find_max_drawdown(dates: list, prices: list) -> dict:
    """
    找到历史最大回撤 + 峰值日期 + 谷底日期。
    """
    if not prices:
        return None
    running_max = prices[0]
    max_dd = 0.0
    peak_idx = 0
    trough_idx = 0
    cur_peak_idx = 0
    for i, p in enumerate(prices):
        if p > running_max:
            running_max = p
            cur_peak_idx = i
        dd = (p - running_max) / running_max * 100.0 if running_max > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            peak_idx = cur_peak_idx
            trough_idx = i
    return {
        "max_dd_pct": max_dd,
        "peak_date": dates[peak_idx].strftime("%Y-%m-%d"),
        "peak_price": prices[peak_idx],
        "trough_date": dates[trough_idx].strftime("%Y-%m-%d"),
        "trough_price": prices[trough_idx],
        "peak_idx": peak_idx,
        "trough_idx": trough_idx,
    }


def find_current_drawdown(dates: list, prices: list, dds: list) -> dict:
    """
    找到当前距离最近峰值的回撤。
    """
    if not prices:
        return None
    # 找到当前最高点(峰值)
    peak_idx = max(range(len(prices)), key=lambda i: prices[i])
    current_idx = len(prices) - 1
    current_dd = dds[current_idx]
    return {
        "current_dd_pct": current_dd,
        "peak_date": dates[peak_idx].strftime("%Y-%m-%d"),
        "peak_price": prices[peak_idx],
        "current_price": prices[current_idx],
        "current_date": dates[current_idx].strftime("%Y-%m-%d"),
        "days_since_peak": (dates[current_idx] - dates[peak_idx]).days,
    }


def find_recovery_time(dates: list, prices: list, peak_idx: int, trough_idx: int) -> dict:
    """
    找到从谷底到恢复峰值的日历天数。
    如果未恢复，标记 None。
    """
    if trough_idx >= len(prices) - 1:
        return {"recovered": False, "days_to_recover": None}
    peak_price = prices[peak_idx]
    trough_price = prices[trough_idx]
    recovery_idx = None
    for i in range(trough_idx + 1, len(prices)):
        if prices[i] >= peak_price:
            recovery_idx = i
            break
    if recovery_idx is None:
        return {
            "recovered": False,
            "days_to_recover": None,
            "still_below_pct": (prices[-1] - peak_price) / peak_price * 100.0,
        }
    return {
        "recovered": True,
        "days_to_recover": (dates[recovery_idx] - dates[trough_idx]).days,
        "trough_date": dates[trough_idx].strftime("%Y-%m-%d"),
        "recovery_date": dates[recovery_idx].strftime("%Y-%m-%d"),
        "recovery_price": prices[recovery_idx],
    }


def find_top_drawdowns(dates: list, prices: list, dds: list, top_n: int = 5) -> list:
    """
    找出 top N 最大回撤事件（每个独立的峰→谷事件）。
    使用 fixed find_drawdown_segments 逻辑（threshold=-10%）。
    """
    if not prices or len(prices) < 2:
        return []

    # 复用 recovery_analyzer 的算法
    segments = []
    n = len(prices)
    peak = 0

    i = 0
    while i < n - 1:
        if prices[i] >= prices[peak]:
            peak = i
        if prices[peak] > 0:
            dd = (prices[i] - prices[peak]) / prices[peak] * 100.0
        else:
            dd = 0
        if dd < -10:  # 至少 -10% 才算事件
            trough = i
            while trough < n - 1 and prices[trough+1] < prices[trough]:
                trough += 1
            rec_idx = None
            for j in range(trough + 1, n):
                if prices[j] >= prices[peak]:
                    rec_idx = j
                    break
            final_dd = (prices[trough] - prices[peak]) / prices[peak] * 100.0
            segments.append({
                "peak_date": dates[peak].strftime("%Y-%m-%d"),
                "peak_price": prices[peak],
                "trough_date": dates[trough].strftime("%Y-%m-%d"),
                "trough_price": prices[trough],
                "drawdown_pct": final_dd,
                "recovery_date": dates[rec_idx].strftime("%Y-%m-%d") if rec_idx else None,
                "days_to_recover": (dates[rec_idx] - dates[trough]).days if rec_idx else None,
                "recovered": rec_idx is not None,
            })
            i = trough + 1
            peak = i
        else:
            i += 1

    segments.sort(key=lambda x: x["drawdown_pct"])
    return segments[:top_n]


# ----------------------------------------------------------------------------
# 报告
# ----------------------------------------------------------------------------

def analyze_symbol(symbol: str, period: str = "5y") -> dict:
    """单个标的完整分析"""
    dates, prices, errors = fetch_price_series(symbol, period)
    if errors:
        # Fallback：使用已知历史回撤参考
        if symbol in KNOWN_DRAWDOWNS:
            ref = KNOWN_DRAWDOWNS[symbol]
            return {
                "symbol": symbol,
                "data_source": "REFERENCE",
                "errors": errors,
                "max_dd": {
                    "max_dd_pct": ref["max_dd_pct"],
                    "peak_date": ref["peak_date"],
                    "peak_price": None,
                    "trough_date": ref["trough_date"],
                    "trough_price": None,
                },
                "current_dd": {
                    "current_dd_pct": ref["current_dd_pct"],
                    "peak_date": ref["peak_date"],
                    "peak_price": None,
                    "current_price": None,
                    "current_date": "未知",
                    "days_since_peak": None,
                },
                "recovery": {
                    "recovered": True,
                    "days_to_recover": ref["days_to_recover"],
                    "trough_date": ref["trough_date"],
                    "recovery_date": "未知",
                    "recovery_price": None,
                },
                "top_drawdowns": [],
                "period": period,
                "data_points": 0,
                "note": ref["note"],
            }
        return {"symbol": symbol, "errors": errors}
    dds = compute_drawdowns(dates, prices)
    max_dd = find_max_drawdown(dates, prices)
    cur_dd = find_current_drawdown(dates, prices, dds)
    rec = find_recovery_time(dates, prices, max_dd["peak_idx"], max_dd["trough_idx"])
    top5 = find_top_drawdowns(dates, prices, dds, top_n=5)
    return {
        "symbol": symbol,
        "data_source": "YF",
        "max_dd": max_dd,
        "current_dd": cur_dd,
        "recovery": rec,
        "top_drawdowns": top5,
        "period": period,
        "data_points": len(prices),
    }


def render_report(analyses: list, period: str = "5y") -> str:
    lines = []
    lines.append("# Drawdown Analyzer Report — 历史回撤分析")
    lines.append("")
    lines.append(f"**生成时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"**回溯周期**：`{period}`")
    lines.append("")
    lines.append("> ⚠️ **声明**：历史回撤不代表未来表现。")
    lines.append("> 用于理解标的在不同周期下的脆弱性，辅助仓位决策。")
    lines.append("")
    # 数据源说明
    sources = set(a.get("data_source", "YF") for a in analyses)
    if "REFERENCE" in sources:
        lines.append("> ⚠️ **yfinance 数据不可用** — 使用【已知历史回撤参考值】（来源：公开历史事件）。")
        lines.append("> 以下数据为参考量级，**不是实时数据**。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、最大回撤汇总")
    lines.append("")
    lines.append("| 标的 | 最大回撤 | 峰值日期 | 谷底日期 | 当前回撤 | 当前距离峰值 | 状态 | 数据源 |")
    lines.append("|------|----------|----------|----------|----------|--------------|------|--------|")
    for a in analyses:
        if a.get("errors") and a.get("data_source") != "REFERENCE":
            lines.append(f"| {a['symbol']} | ❌ ERROR | - | - | - | - | 数据缺失 | 无 |")
            continue
        m = a["max_dd"]
        c = a["current_dd"]
        r = a["recovery"]
        status = "已恢复" if r["recovered"] else "未恢复"
        src = a.get("data_source", "YF")
        lines.append(
            f"| {a['symbol']} | {m['max_dd_pct']:.2f}% | {m.get('peak_date', 'N/A')} | "
            f"{m.get('trough_date', 'N/A')} | {c['current_dd_pct']:.2f}% | "
            f"{c.get('days_since_peak', 'N/A')} | {status} | {src} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 二、恢复时间分析")
    lines.append("")
    lines.append("| 标的 | 最大回撤 | 谷底 → 恢复天数 | 恢复日期 | 备注 |")
    lines.append("|------|----------|------------------|----------|------|")
    for a in analyses:
        if a.get("errors") and a.get("data_source") != "REFERENCE":
            continue
        m = a["max_dd"]
        r = a["recovery"]
        if r["recovered"]:
            note = f"{r['days_to_recover']}天恢复"
        else:
            note = f"未恢复（仍距峰值 {r.get('still_below_pct', 0):.2f}%）"
        lines.append(
            f"| {a['symbol']} | {m['max_dd_pct']:.2f}% | "
            f"{r['days_to_recover'] if r['recovered'] else 'N/A'} | "
            f"{r.get('recovery_date', 'N/A')} | {note} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 三、Top 5 历史回撤事件")
    lines.append("")
    for a in analyses:
        if a.get("data_source") == "REFERENCE" or not a.get("top_drawdowns"):
            continue
        lines.append(f"### {a['symbol']}")
        lines.append("")
        lines.append("| 峰值日期 | 谷底日期 | 回撤% | 恢复日期 | 恢复天数 |")
        lines.append("|----------|----------|-------|----------|----------|")
        for e in a["top_drawdowns"]:
            lines.append(
                f"| {e['peak_date']} | {e['trough_date']} | "
                f"{e['drawdown_pct']:.2f}% | "
                f"{e['recovery_date'] or '未恢复'} | "
                f"{e['days_to_recover'] if e['days_to_recover'] is not None else 'N/A'} |"
            )
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 四、风险解读")
    lines.append("")
    lines.append("### 关键洞察")
    lines.append("")
    for a in analyses:
        if a.get("errors") and a.get("data_source") != "REFERENCE":
            continue
        m = a["max_dd"]
        c = a["current_dd"]
        r = a["recovery"]
        lines.append(f"- **{a['symbol']}**：历史最大回撤 `{m['max_dd_pct']:.2f}%`，"
                     f"当前回撤 `{c['current_dd_pct']:.2f}%`。")
        if r["recovered"] and r["days_to_recover"]:
            lines.append(f"  - 最大回撤的恢复时间：`{r['days_to_recover']}天`")
        if a.get("data_source") == "REFERENCE":
            lines.append(f"  - 📌 **参考数据**：{a.get('note', 'N/A')}")
    lines.append("")
    lines.append("### 防御启示")
    lines.append("")
    lines.append("- 历史最大回撤是**极端情景**的参考，不是预测。")
    lines.append("- 仓位需考虑这些历史回撤的潜在冲击。")
    lines.append("- 单一标的回撤 > 50% 通常意味着**结构性风险**。")
    lines.append("- 未恢复的标的可能反映**永久性价值损失**。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 五、纪律声明")
    lines.append("")
    lines.append("- 历史回撤不预测未来。")
    lines.append("- 恢复时间因市场周期不同而不同。")
    lines.append("- 决策权在用户，Atlas 仅提供分析。")
    lines.append("")
    lines.append(f"*Atlas Drawdown Analyzer · v10 · {datetime.now().strftime('%Y-%m-%d')}*")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Atlas Drawdown Analyzer v10 — 历史回撤分析")
    parser.add_argument(
        "symbols", nargs="+",
        help="股票代码 (e.g., NVDA MSFT AAPL)")
    parser.add_argument(
        "--period", type=str, default="5y",
        help="回溯周期 (1y / 2y / 5y / 10y / max)")
    parser.add_argument(
        "--stdout", action="store_true",
        help="输出到 stdout")
    args = parser.parse_args()

    analyses = []
    for sym in args.symbols:
        print(f"分析 {sym}...", file=sys.stderr)
        a = analyze_symbol(sym, args.period)
        analyses.append(a)

    report = render_report(analyses, args.period)

    if not args.stdout:
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_path = os.path.join(REPORTS_DIR, f"回撤分析_{date_str}.md")
        with open(out_path, "w") as f:
            f.write(report)
        print(f"✅ Report saved: {out_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
