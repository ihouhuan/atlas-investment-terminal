#!/usr/bin/env python3
"""
Atlas Risk Cluster v10
组合相关性 + 风险集群识别

输入：股票代码列表
输出：相关性矩阵 + 风险集群 (硬编码 + 数据驱动 mixed)

风险因子分类（预定义）：
  Cluster 1: US Technology Growth
  Cluster 2: US Technology Mature
  Cluster 3: US Consumer
  Cluster 4: US Financials
  Cluster 5: US Healthcare
  Cluster 6: China Internet
  Cluster 7: Emerging Markets
  Cluster 8: Commodities
  Cluster 9: Defensives

降级策略：
  - 尝试 yfinance 拉取真实相关性
  - 失败时使用【已知相关性参考值】（不同股票各自历史会变）
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

from core.paths import stress_test_report_path, today_str, WORKSPACE_ROOT, INVESTMENT_DIR
from core.market_data import fetch_returns
from core.reference_data import KNOWN_CORRELATIONS, RISK_CLUSTERS

warnings.filterwarnings('ignore')

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# ----------------------------------------------------------------------------
# 已知相关性参考值（仅在 yfinance 不可用时使用）
# 来源：公开资产相关性资料
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
from core.paths import 压力测试_DIR as REPORTS_DIR
os.makedirs(REPORTS_DIR, exist_ok=True)


# ----------------------------------------------------------------------------
# 预定义风险因子
# ----------------------------------------------------------------------------

CLUSTER_MAP = {
    # US Technology Growth
    "NVDA": "US Technology Growth",
    "AMD": "US Technology Growth",
    "SMCI": "US Technology Growth",
    "AVGO": "US Technology Growth",
    "TSLA": "US Technology Growth",
    "PLTR": "US Technology Growth",
    "CRWD": "US Technology Growth",
    "PANW": "US Technology Growth",
    "SNOW": "US Technology Growth",

    # US Technology Mature
    "MSFT": "US Technology Mature",
    "GOOGL": "US Technology Mature",
    "GOOG": "US Technology Mature",
    "AMZN": "US Technology Mature",
    "META": "US Technology Mature",
    "AAPL": "US Technology Mature",
    "ORCL": "US Technology Mature",
    "CRM": "US Technology Mature",
    "ADBE": "US Technology Mature",
    "INTC": "US Technology Mature",

    # US Consumer
    "WMT": "US Consumer Staples",
    "COST": "US Consumer Staples",
    "PG": "US Consumer Staples",
    "KO": "US Consumer Staples",
    "PEP": "US Consumer Staples",
    "MCD": "US Consumer Discretionary",
    "NKE": "US Consumer Discretionary",
    "SBUX": "US Consumer Discretionary",
    "HD": "US Consumer Discretionary",
    "LOW": "US Consumer Discretionary",

    # US Financials
    "JPM": "US Financials",
    "BAC": "US Financials",
    "WFC": "US Financials",
    "GS": "US Financials",
    "MS": "US Financials",
    "BLK": "US Financials",
    "V": "US Financials",
    "MA": "US Financials",
    "BRK-B": "US Financials",

    # US Healthcare
    "JNJ": "US Healthcare",
    "UNH": "US Healthcare",
    "PFE": "US Healthcare",
    "ABBV": "US Healthcare",
    "LLY": "US Healthcare",
    "MRK": "US Healthcare",
    "TMO": "US Healthcare",

    # US Energy
    "XOM": "US Energy",
    "CVX": "US Energy",
    "COP": "US Energy",

    # US Industrials
    "BA": "US Industrials",
    "CAT": "US Industrials",
    "GE": "US Industrials",
    "HON": "US Industrials",

    # China Internet
    "BABA": "China Internet",
    "0700.HK": "China Internet",
    "BIDU": "China Internet",
    "JD": "China Internet",
    "PDD": "China Internet",
    "TCEHY": "China Internet",
    "NTES": "China Internet",
    "BILI": "China Internet",

    # Emerging Markets
    "TSM": "Emerging Markets",
    "VALE": "Emerging Markets",
    "BBD": "Emerging Markets",

    # Defensives
    "TM": "Defensives",
    "NEE": "Defensives",
    "DUK": "Defensives",
    "SO": "Defensives",
}


# ----------------------------------------------------------------------------
# 相关性计算
# ----------------------------------------------------------------------------

def fetch_returns(symbol: str, period: str = "1y") -> tuple:
    """拉取日收益率"""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, auto_adjust=True)
        if hist.empty:
            return None, [f"{symbol} 无历史数据"]
        prices = hist["Close"].tolist()
        dates = hist.index.to_pydatetime().tolist()
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                returns.append((prices[i] - prices[i-1]) / prices[i-1])
            else:
                returns.append(0.0)
        return {"dates": dates[1:], "returns": returns}, []
    except Exception as e:
        return None, [f"{symbol}: {e}"]


def compute_correlation(symbols: list, period: str = "1y") -> dict:
    """
    计算相关性矩阵。
    返回 {sym_a: {sym_b: corr}}
    """
    series = {}
    errors = []
    for s in symbols:
        data, errs = fetch_returns(s, period)
        if errs:
            errors.extend(errs)
            continue
        series[s] = data["returns"]

    # 对齐：用最短长度
    if not series:
        # Fallback 到已知相关性
        matrix = {}
        syms = symbols
        for a in syms:
            matrix[a] = {}
            for b in syms:
                if a == b:
                    matrix[a][b] = 1.0
                else:
                    matrix[a][b] = KNOWN_CORRELATIONS.get(
                        (a, b), KNOWN_CORRELATIONS.get((b, a), 0.5))
        return {"matrix": matrix, "errors": errors, "period": period,
                "data_points": 0, "data_source": "REFERENCE"}

    min_len = min(len(r) for r in series.values())
    aligned = {s: r[-min_len:] for s, r in series.items()}

    # 计算 Pearson 相关
    matrix = {}
    syms = list(aligned.keys())
    for i, a in enumerate(syms):
        matrix[a] = {}
        for j, b in enumerate(syms):
            if i == j:
                matrix[a][b] = 1.0
            elif b in matrix and a in matrix[b]:
                matrix[a][b] = matrix[b][a]
            else:
                ra = aligned[a]
                rb = aligned[b]
                n = len(ra)
                mean_a = sum(ra) / n
                mean_b = sum(rb) / n
                cov = sum((ra[k] - mean_a) * (rb[k] - mean_b) for k in range(n)) / n
                std_a = (sum((ra[k] - mean_a) ** 2 for k in range(n)) / n) ** 0.5
                std_b = (sum((rb[k] - mean_b) ** 2 for k in range(n)) / n) ** 0.5
                if std_a > 0 and std_b > 0:
                    matrix[a][b] = cov / (std_a * std_b)
                else:
                    matrix[a][b] = 0.0

    return {"matrix": matrix, "errors": errors, "period": period,
            "data_points": min_len, "data_source": "YF"}


# ----------------------------------------------------------------------------
# 集群识别
# ----------------------------------------------------------------------------

def group_by_cluster(symbols: list) -> dict:
    """按预定义分为簇"""
    clusters = {}
    for s in symbols:
        cluster = CLUSTER_MAP.get(s, "Unclassified")
        clusters.setdefault(cluster, []).append(s)
    return clusters


def find_pair_correlations(matrix: dict) -> list:
    """提取高相关性对"""
    pairs = []
    syms = list(matrix.keys())
    for i, a in enumerate(syms):
        for j, b in enumerate(syms):
            if j <= i:
                continue
            corr = matrix[a].get(b, 0.0)
            pairs.append({"a": a, "b": b, "corr": corr})
    pairs.sort(key=lambda x: abs(x["corr"]), reverse=True)
    return pairs


# ----------------------------------------------------------------------------
# 报告
# ----------------------------------------------------------------------------

def render_report(symbols: list, corr_data: dict, portfolio_concentration: dict = None) -> str:
    lines = []
    lines.append("# Risk Cluster Report — 风险集群分析")
    lines.append("")
    lines.append(f"**生成时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"**分析标的**：`{', '.join(symbols)}`")
    lines.append(f"**回溯周期**：`{corr_data.get('period', 'N/A')}`")
    lines.append(f"**数据点**：`{corr_data.get('data_points', 0)}`")
    lines.append("")
    lines.append("> ⚠️ **声明**：相关性基于历史数据，**不预测**未来。")
    lines.append("> 集群分类为**风险因子识别**而非行业严格定义。")
    lines.append("")
    if corr_data.get("data_source") == "REFERENCE":
        lines.append("> ⚠️ **yfinance 不可用** — 使用【已知相关性参考值】（来源：公开资产相关性资料）。")
        lines.append("> 以下数据为参考量级，**不是实时数据**。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、风险集群识别")
    lines.append("")
    clusters = group_by_cluster(symbols)
    lines.append("| 集群 | 包含标的 | 数量 |")
    lines.append("|------|----------|------|")
    for cname, syms in clusters.items():
        lines.append(f"| {cname} | {', '.join(syms)} | {len(syms)} |")
    lines.append("")

    # 集群权重
    if portfolio_concentration:
        lines.append("### 集群权重（基于成本）")
        lines.append("")
        lines.append("| 集群 | 权重 | 累计 |")
        lines.append("|------|------|------|")
        cumulative = 0.0
        for cname, syms in clusters.items():
            w = sum(portfolio_concentration.get(s, 0.0) for s in syms)
            cumulative += w
            lines.append(f"| {cname} | {w*100:.1f}% | {cumulative*100:.1f}% |")
        lines.append("")
        # 警告
        if cumulative > 0.70:
            lines.append(f"⚠️ **最大集群占比 {cumulative*100:.1f}%** — 高度集中风险。")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 二、相关性矩阵")
    lines.append("")
    matrix = corr_data.get("matrix", {})
    if matrix:
        syms = list(matrix.keys())
        # 表格
        header = "| | " + " | ".join(syms) + " |"
        sep = "|---" * (len(syms) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for a in syms:
            row = [a]
            for b in syms:
                c = matrix[a].get(b, 0.0)
                # 颜色 emoji
                if c >= 0.7:
                    marker = "🔴"
                elif c >= 0.4:
                    marker = "🟡"
                elif c >= 0:
                    marker = "🟢"
                else:
                    marker = "🔵"  # 负相关
                row.append(f"{marker} {c:.2f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        lines.append("图例：🔴 高相关 (≥0.7) · 🟡 中相关 (0.4-0.7) · 🟢 低相关 (0-0.4) · 🔵 负相关")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 三、高相关性对（潜在冗余）")
    lines.append("")
    pairs = find_pair_correlations(matrix)
    high_pairs = [p for p in pairs if abs(p["corr"]) >= 0.5]
    if not high_pairs:
        lines.append("无高度相关的标的。✅")
    else:
        lines.append("| 标的 A | 标的 B | 相关系数 | 解读 |")
        lines.append("|--------|--------|----------|------|")
        for p in high_pairs:
            interp = "几乎同质" if p["corr"] >= 0.8 else "高相关" if p["corr"] >= 0.6 else "中相关"
            lines.append(f"| {p['a']} | {p['b']} | {p['corr']:.2f} | {interp} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 四、共同风险因子")
    lines.append("")
    lines.append("### 共享因子")
    lines.append("")
    shared = []
    for cname, syms in clusters.items():
        if len(syms) >= 2:
            shared.append((cname, syms))
    if not shared:
        lines.append("无共享风险因子的标的组。")
    else:
        for cname, syms in shared:
            lines.append(f"**`{cname}`**")
            lines.append("")
            lines.append(f"包含标的：{', '.join(syms)}")
            lines.append("")
            # 描述风险因子
            factor_desc = {
                "US Technology Growth": "高估值 + 利率敏感 + AI 周期 + 增速预期",
                "US Technology Mature": "AI 商业化 + 估值 + 监管 + 平台竞争",
                "US Consumer Staples": "通胀敏感 + 必需品需求 + 现金流稳定",
                "US Consumer Discretionary": "消费力 + 利率敏感 + 周期",
                "US Financials": "利率周期 + 信贷质量 + 监管",
                "US Healthcare": "政策 + 药品周期 + 人口结构",
                "US Energy": "油价 + 周期 + ESG",
                "US Industrials": "经济周期 + 供应链 + 资本开支",
                "China Internet": "地缘 + 监管 + 中美脱钩 + 国内宏观",
                "Emerging Markets": "汇率 + 地缘 + 美元周期",
                "Defensives": "低波动 + 派息 + 防御性",
            }.get(cname, "未定义")
            lines.append(f"共同风险因子：{factor_desc}")
            lines.append("")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 五、风险发现")
    lines.append("")
    if matrix:
        # 计算平均相关性
        syms = list(matrix.keys())
        if len(syms) >= 2:
            total = 0.0
            count = 0
            for i, a in enumerate(syms):
                for j, b in enumerate(syms):
                    if i < j:
                        total += matrix[a].get(b, 0.0)
                        count += 1
            avg_corr = total / count if count > 0 else 0.0
            lines.append(f"- **平均相关性**：`{avg_corr:.2f}`")
            if avg_corr >= 0.7:
                lines.append("- ⚠️ 组合高度同质化，分散化效果有限。")
            elif avg_corr >= 0.4:
                lines.append("- 中等相关性，存在一定分散化但仍有改进空间。")
            else:
                lines.append("- ✅ 平均相关性较低，分散化效果良好。")
            lines.append("")
    if portfolio_concentration:
        max_cluster = max(clusters.items(), key=lambda x: sum(
            portfolio_concentration.get(s, 0.0) for s in x[1]))
        max_weight = sum(portfolio_concentration.get(s, 0.0) for s in max_cluster[1])
        lines.append(f"- **最大集群**：`{max_cluster[0]}`（权重 {max_weight*100:.1f}%）")
        if max_weight >= 0.5:
            lines.append("- ⚠️ 单一集群占比 > 50%，脆弱性高。")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 六、纪律声明")
    lines.append("")
    lines.append("- 相关性基于历史，不能预测未来。")
    lines.append("- 集群分类为风险因子识别，非严格行业分类。")
    lines.append("- 决策权在用户，Atlas 仅提供分析。")
    lines.append("")
    lines.append(f"*Atlas Risk Cluster · v10 · {datetime.now().strftime('%Y-%m-%d')}*")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Atlas Risk Cluster v10 — 相关性 + 风险集群")
    parser.add_argument(
        "symbols", nargs="+",
        help="股票代码")
    parser.add_argument(
        "--period", type=str, default="1y",
        help="回溯周期 (6mo / 1y / 2y)")
    parser.add_argument(
        "--portfolio", type=str, default=None,
        help="portfolio.json 路径（用于集群权重）")
    parser.add_argument(
        "--stdout", action="store_true",
        help="输出到 stdout")
    args = parser.parse_args()

    correlation = compute_correlation(args.symbols, args.period)

    portfolio_concentration = None
    if args.portfolio and os.path.exists(args.portfolio):
        with open(args.portfolio, "r") as f:
            po = json.load(f)
        # 兼容 v1.1 嵌套结构
        positions = po.get("positions", [])
        if isinstance(positions, dict):
            positions = positions.get("positions", [])
        portfolio_concentration = {}
        total = 0.0
        for pos in positions:
            v = pos["shares"] * pos["cost"]
            portfolio_concentration[pos["symbol"]] = v
            total += v
        if total > 0:
            for s in portfolio_concentration:
                portfolio_concentration[s] /= total

    report = render_report(args.symbols, correlation, portfolio_concentration)

    if not args.stdout:
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_path = os.path.join(REPORTS_DIR, f"风险集中度_{date_str}.md")
        with open(out_path, "w") as f:
            f.write(report)
        print(f"✅ Report saved: {out_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
