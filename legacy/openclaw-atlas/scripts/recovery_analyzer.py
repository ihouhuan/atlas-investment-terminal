#!/usr/bin/env python3
"""
Atlas Recovery Analyzer v10
恢复时间分析

输入：股票代码列表 + 回撤阈值
输出：每只股票从 X% 回撤恢复到峰值的平均时间

与 drawdown_analyzer 的区别：
  - drawdown_analyzer: 找历史最大回撤 + 单一恢复时间
  - recovery_analyzer: 找所有超过 X% 的回撤 + 平均恢复时间分布

降级策略：
  - 尝试 yfinance 拉取真实历史数据
  - 失败时使用【已知恢复时间参考值】
  - 始终明确告知数据源
"""

import argparse
import json
import os
import sys
import warnings
from datetime import datetime

# Atlas core utilities (v10.5 unified)
# Add investment/ to sys.path so 'core' module is importable
import os as _os
_investment_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _investment_root not in sys.path:
    sys.path.insert(0, _investment_root)
del _os, _investment_root

from core.paths import stress_test_report_path, today_str
from core.market_data import fetch_price_series
from core.reference_data import KNOWN_RECOVERY_TIMES

warnings.filterwarnings('ignore')

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# ----------------------------------------------------------------------------
# 已知恢复时间参考值（仅在 yfinance 不可用时使用）
# 来源：公开历史记录
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

def fetch_price_series(symbol: str, period: str = "10y") -> tuple:
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
# 回撤段识别
# ----------------------------------------------------------------------------

def find_drawdown_segments(dates: list, prices: list, threshold_pct: float) -> list:
    """
    找出所有超过阈值(threshold_pct)的回撤段。
    返回 [{peak_date, peak_price, trough_date, trough_price, recovery_date, drawdown_pct, days_to_recover, recovered}]
    """
    if not prices or len(prices) < 2:
        return []

    segments = []
    n = len(prices)
    peak = 0  # 当前 peak 索引（仅在未在回撤中时更新）

    # 单次遍历：从左到右
    i = 0
    while i < n - 1:
        # 上升阶段：更新 peak
        if prices[i] >= prices[peak]:
            peak = i
        # 计算当前回撤
        if prices[peak] > 0:
            dd = (prices[i] - prices[peak]) / prices[peak] * 100.0
        else:
            dd = 0
        # 如果达到阈值，开始识别段
        if dd <= threshold_pct:
            # 这是一个 peak-to-trough 段
            trough = i
            # 找到 trough（继续往下走直到价格不再下降）
            while trough < n - 1 and prices[trough+1] < prices[trough]:
                trough += 1
            # 找到恢复点
            rec_idx = None
            for j in range(trough + 1, n):
                if prices[j] >= prices[peak]:
                    rec_idx = j
                    break
            # 计算最终 dd
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
            # 跳过到 trough 之后
            i = trough + 1
            peak = i  # 从 trough 之后的新高点开始
        else:
            i += 1

    return segments


def summarize_segments(segments: list) -> dict:
    """汇总回撤段统计"""
    if not segments:
        return {
            "count": 0,
            "recovered_count": 0,
            "unrecovered_count": 0,
            "avg_drawdown": 0.0,
            "worst_drawdown": 0.0,
            "avg_recovery_days": None,
            "median_recovery_days": None,
            "fastest_recovery_days": None,
            "slowest_recovery_days": None,
        }
    recovered = [s for s in segments if s["recovered"]]
    recovery_days = [s["days_to_recover"] for s in recovered]
    dds = [s["drawdown_pct"] for s in segments]
    recovery_days_sorted = sorted(recovery_days) if recovery_days else []
    return {
        "count": len(segments),
        "recovered_count": len(recovered),
        "unrecovered_count": len(segments) - len(recovered),
        "avg_drawdown": sum(dds) / len(dds) if dds else 0.0,
        "worst_drawdown": min(dds) if dds else 0.0,
        "avg_recovery_days": sum(recovery_days) / len(recovery_days) if recovery_days else None,
        "median_recovery_days": recovery_days_sorted[len(recovery_days_sorted)//2] if recovery_days_sorted else None,
        "fastest_recovery_days": min(recovery_days) if recovery_days else None,
        "slowest_recovery_days": max(recovery_days) if recovery_days else None,
    }


# ----------------------------------------------------------------------------
# 多阈值分析
# ----------------------------------------------------------------------------

def analyze_thresholds(symbol: str, period: str, thresholds: list) -> dict:
    """对多阈值进行分析"""
    dates, prices, errors = fetch_price_series(symbol, period)
    if errors:
        # Fallback
        if symbol in KNOWN_RECOVERY_TIMES:
            ref = KNOWN_RECOVERY_TIMES[symbol]
            out = {"symbol": symbol, "period": period, "data_source": "REFERENCE",
                   "errors": errors, "by_threshold": {}, "note": ref["note"]}
            for t in thresholds:
                # 根据阈值选合适的参考
                if t >= 50:
                    avg_days = ref["avg_recovery_50pct"]
                elif t >= 30:
                    avg_days = ref["avg_recovery_30pct"]
                elif t >= 20:
                    avg_days = ref["avg_recovery_20pct"]
                else:
                    avg_days = ref["avg_recovery_10pct"]
                out["by_threshold"][t] = {
                    "summary": {
                        "count": 1,
                        "recovered_count": 1,
                        "unrecovered_count": 0,
                        "avg_drawdown": ref["max_dd"],
                        "worst_drawdown": ref["max_dd"],
                        "avg_recovery_days": avg_days,
                        "median_recovery_days": avg_days,
                        "fastest_recovery_days": max(int(avg_days * 0.5), 30),
                        "slowest_recovery_days": min(int(avg_days * 1.5), ref["max_recovery_days"]),
                    },
                    "segments": [],
                }
            return out
        return {"symbol": symbol, "errors": errors}

    out = {"symbol": symbol, "period": period, "data_source": "YF",
           "data_points": len(prices), "by_threshold": {}}
    for t in thresholds:
        # thresholds are positive (e.g., 50 = -50%), but find_drawdown_segments
        # expects negative threshold (e.g., -50). Convert.
        segs = find_drawdown_segments(dates, prices, -abs(t))
        summary = summarize_segments(segs)
        out["by_threshold"][t] = {"summary": summary, "segments": segs}
    return out


# ----------------------------------------------------------------------------
# 报告
# ----------------------------------------------------------------------------

def render_report(analyses: list, thresholds: list, period: str) -> str:
    lines = []
    lines.append("# Recovery Analysis Report — 恢复时间分析")
    lines.append("")
    lines.append(f"**生成时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"**回溯周期**：`{period}`")
    lines.append(f"**回撤阈值**：`{', '.join(str(t) for t in thresholds)}%`")
    lines.append("")
    lines.append("> ⚠️ **声明**：历史恢复时间不代表未来。")
    lines.append("> 用于理解不同回撤深度下的恢复分布，辅助仓位决策。")
    lines.append("")
    # 数据源说明
    sources = set(a.get("data_source", "YF") for a in analyses)
    if "REFERENCE" in sources:
        lines.append("> ⚠️ **yfinance 不可用** — 使用【已知恢复时间参考值】（来源：公开历史事件）。")
        lines.append("> 以下数据为参考量级，**不是实时数据**。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 一、汇总
    lines.append("## 一、跨阈值恢复汇总")
    lines.append("")
    lines.append("| 标的 | 阈值 | 事件数 | 已恢复 | 平均恢复天数 | 中位数 | 最快 | 最慢 | 未恢复 |")
    lines.append("|------|------|--------|--------|--------------|--------|------|------|--------|")
    for a in analyses:
        # 仅有 errors 但不是 REFERENCE 时显示 ERROR
        if a.get("errors") and a.get("data_source") != "REFERENCE":
            lines.append(f"| {a['symbol']} | - | ❌ | - | - | - | - | - | - |")
            continue
        for t in thresholds:
            d = a["by_threshold"].get(t, {})
            s = d.get("summary", {})
            lines.append(
                f"| {a['symbol']} | -{t}% | {s.get('count', 0)} | "
                f"{s.get('recovered_count', 0)} | "
                f"{s.get('avg_recovery_days', 'N/A') if s.get('avg_recovery_days') else 'N/A'} | "
                f"{s.get('median_recovery_days', 'N/A') if s.get('median_recovery_days') else 'N/A'} | "
                f"{s.get('fastest_recovery_days', 'N/A') if s.get('fastest_recovery_days') else 'N/A'} | "
                f"{s.get('slowest_recovery_days', 'N/A') if s.get('slowest_recovery_days') else 'N/A'} | "
                f"{s.get('unrecovered_count', 0)} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 二、深度回撤分析（找最大阈值）
    if thresholds:
        max_t = max(thresholds)
        lines.append(f"## 二、深度回撤（≥{max_t}%）事件详情")
        lines.append("")
        for a in analyses:
            if a.get("errors") and a.get("data_source") != "REFERENCE":
                continue
            segs = a["by_threshold"].get(max_t, {}).get("segments", [])
            if a.get("data_source") == "REFERENCE":
                lines.append(f"### {a['symbol']}")
                lines.append("")
                lines.append(f"📌 **参考数据**：{a.get('note', 'N/A')}")
                s = a["by_threshold"].get(max_t, {}).get("summary", {})
                lines.append("")
                lines.append(f"- 最大回撤历史参考值：`{s.get('worst_drawdown', 0):.1f}%`")
                lines.append(f"- 恢复时间参考值：`{s.get('avg_recovery_days', 'N/A')}天`（平均）")
                lines.append(f"- 最慢恢复参考值：`{s.get('slowest_recovery_days', 'N/A')}天`")
                lines.append("")
                continue
            if not segs:
                lines.append(f"### {a['symbol']}")
                lines.append("")
                lines.append(f"无 ≥ -{max_t}% 的回撤事件。")
                lines.append("")
                continue
            lines.append(f"### {a['symbol']}")
            lines.append("")
            lines.append("| 峰值日期 | 谷底日期 | 回撤% | 恢复日期 | 恢复天数 |")
            lines.append("|----------|----------|-------|----------|----------|")
            for s in segs:
                lines.append(
                    f"| {s['peak_date']} | {s['trough_date']} | "
                    f"{s['drawdown_pct']:.2f}% | "
                    f"{s['recovery_date'] or '未恢复'} | "
                    f"{s['days_to_recover'] if s['days_to_recover'] is not None else 'N/A'} |"
                )
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 三、风险解读")
    lines.append("")
    lines.append("### 关键洞察")
    lines.append("")
    if thresholds:
        max_t = max(thresholds)
        for a in analyses:
            if a.get("errors") and a.get("data_source") != "REFERENCE":
                continue
            d = a["by_threshold"].get(max_t, {})
            s = d.get("summary", {})
            lines.append(f"- **{a['symbol']}**：")
            if s.get("count", 0) == 0:
                lines.append(f"  - 历史未发生 ≥ -{max_t}% 回撤（韧性极强）")
            else:
                avg = s.get("avg_recovery_days")
                if avg:
                    lines.append(f"  - 平均恢复时间：`{avg:.0f}天` "
                                 f"(样本 {s['recovered_count']}/{s['count']})")
                if s.get("slowest_recovery_days"):
                    lines.append(f"  - 最慢恢复：`{s['slowest_recovery_days']}天`")
                if s.get("unrecovered_count", 0) > 0:
                    lines.append(f"  - ⚠️ 当前有 {s['unrecovered_count']} 个未恢复回撤")
            if a.get("data_source") == "REFERENCE":
                lines.append(f"  - 📌 **参考数据**：{a.get('note', 'N/A')}")
            lines.append("")
    lines.append("")
    lines.append("### 防御启示")
    lines.append("")
    lines.append("- 恢复时间分布反映**韧性**：恢复越快，标的越能抵御冲击。")
    lines.append("- 平均恢复天数是**经验参考**，不是预测。")
    lines.append("- 未恢复的回撤可能是**永久性损失**信号。")
    lines.append("- 仓位计划应考虑**最坏恢复时间**（而非平均）。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 四、纪律声明")
    lines.append("")
    lines.append("- 历史恢复时间不预测未来。")
    lines.append("- 决策权在用户，Atlas 仅提供分析。")
    lines.append("")
    lines.append(f"*Atlas Recovery Analyzer · v10 · {datetime.now().strftime('%Y-%m-%d')}*")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Atlas Recovery Analyzer v10 — 恢复时间分析")
    parser.add_argument(
        "symbols", nargs="+",
        help="股票代码")
    parser.add_argument(
        "--period", type=str, default="10y",
        help="回溯周期 (5y / 10y / max)")
    parser.add_argument(
        "--thresholds", type=str, default="-10,-20,-30,-40,-50",
        help="回撤阈值（负数，逗号分隔）")
    parser.add_argument(
        "--stdout", action="store_true",
        help="输出到 stdout")
    args = parser.parse_args()

    thresholds = [abs(float(t)) for t in args.thresholds.split(",") if t.strip()]
    thresholds = sorted(set(thresholds), reverse=True)

    analyses = []
    for sym in args.symbols:
        print(f"分析 {sym}...", file=sys.stderr)
        a = analyze_thresholds(sym, args.period, thresholds)
        analyses.append(a)

    report = render_report(analyses, thresholds, args.period)

    if not args.stdout:
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_path = os.path.join(REPORTS_DIR, f"恢复分析_{date_str}.md")
        with open(out_path, "w") as f:
            f.write(report)
        print(f"✅ Report saved: {out_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
