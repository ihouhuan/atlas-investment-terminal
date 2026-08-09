#!/usr/bin/env python3
"""
Atlas Scenario Engine v10
组合压力测试 · 情景模拟

输入：portfolio.json + 预定义情景 / 自定义情景
输出：每个情景下的组合损失明细

设计原则：
  - 不是预测（hypothetical only）
  - 不是交易建议
  - 只评估脆弱性

参考：
  investment/stress_test/scenarios.md (8 个预设情景)
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

from core.paths import WORKSPACE_ROOT, INVESTMENT_DIR, stress_test_report_path, today_str

warnings.filterwarnings('ignore')

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
PORTFOLIO_FILE = os.path.join(ROOT, "portfolio", "portfolio.json")
SCENARIOS_FILE = os.path.join(ROOT, "stress_test", "scenarios.md")
SCENARIOS_DIR = os.path.join(ROOT, "stress_test", "scenarios")
from core.paths import 压力测试_DIR as REPORTS_DIR

os.makedirs(SCENARIOS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


# ----------------------------------------------------------------------------
# 预设情景库（与 scenarios.md 同步）
# ----------------------------------------------------------------------------

PRESET_SCENARIOS = {
    "bear_market": {
        "name": "Bear Market — 熊市（通用）",
        "category": "macro",
        "trigger": "长期持有者失去信心，估值杀 + 盈利杀",
        "shocks": {
            "US_LARGE_CAP": -25,
            "US_SMALL_CAP": -35,
            "INTERNATIONAL": -30,
            "TECH_EXTRA": -15,
            "BONDS": -5,
        },
        "tech_extra": True,  # 科技股额外 -15%
    },
    "tech_correction": {
        "name": "Technology Correction — 科技股修正",
        "category": "sector",
        "trigger": "AI 泡沫破裂 / 利率超预期 / 监管",
        "shocks": {
            "NVDA": -40, "MSFT": -25, "AAPL": -20,
            "GOOGL": -22, "AMZN": -28, "META": -30, "TSLA": -50,
        },
    },
    "ai_bubble_burst": {
        "name": "AI Bubble Burst — AI 泡沫破裂",
        "category": "sector",
        "trigger": "AI 资本开支缩减 / 商业化不及预期 / 替代芯片崛起",
        "shocks": {
            "NVDA": -55, "MSFT": -30, "GOOGL": -25,
            "AMD": -50, "AVGO": -35, "SMCI": -70,
        },
    },
    "recession": {
        "name": "Recession — 衰退",
        "category": "macro",
        "trigger": "失业率上升 / 消费衰退 / 央行宽松",
        "shocks": {
            "US_EQUITIES": -30, "TECH": -35, "FINANCIALS": -25,
            "CONSUMER_DISCRETIONARY": -28, "CONSUMER_STAPLES": -10,
            "HEALTHCARE": -15, "UTILITIES": -5,
            "GOVT_BONDS": 5, "GOLD": 10,
        },
    },
    "inflation_surge": {
        "name": "Inflation Surge — 通胀飙升",
        "category": "macro",
        "trigger": "CPI > 5% / 工资螺旋 / 央行鹰派",
        "shocks": {
            "GROWTH_STOCKS": -25, "BONDS": -15, "REITS": -20,
            "COMMODITIES": 15, "ENERGY": 10,
        },
    },
    "rate_shock": {
        "name": "Rate Shock — 利率冲击",
        "category": "macro",
        "trigger": "10Y 国债收益率 +200bp 突然上升",
        "shocks": {
            "LONG_DURATION": -30, "HIGH_GROWTH_TECH": -35,
            "REITS": -25, "BANKS": 5,
        },
    },
    "china_tech_crisis": {
        "name": "China Tech Crisis — 中国科技危机",
        "category": "geography",
        "trigger": "地缘政治 / 中美脱钩 / 监管升级",
        "shocks": {
            "BABA": -45, "0700.HK": -35, "BIDU": -40,
            "JD": -50, "PDD": -45,
        },
    },
    "geopolitical": {
        "name": "Geopolitical — 地缘政治",
        "category": "macro",
        "trigger": "重大地缘冲突 / 贸易战升级",
        "shocks": {
            "US_EQUITIES": -15, "DEFENSE": 20, "ENERGY": 10,
            "GOLD": 15, "INTERNATIONAL": -25,
        },
    },
}


# ----------------------------------------------------------------------------
# 自定义情景解析
# ----------------------------------------------------------------------------

def parse_custom_shocks(spec: str) -> dict:
    """
    解析自定义情景。
    格式："NVDA:-50,MSFT:-30,AAPL:-25"
    """
    out = {}
    for item in spec.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        sym, val = item.split(":", 1)
        sym = sym.strip().upper()
        try:
            out[sym] = float(val.strip())
        except ValueError:
            continue
    return out


# ----------------------------------------------------------------------------
# 组合加载
# ----------------------------------------------------------------------------

def load_portfolio() -> dict:
    """读取 portfolio.json"""
    if not os.path.exists(PORTFOLIO_FILE):
        raise FileNotFoundError(f"Portfolio not found: {PORTFOLIO_FILE}")
    with open(PORTFOLIO_FILE, "r") as f:
        return json.load(f)


def compute_position_values(portfolio: dict) -> dict:
    """计算每个持仓的市值（基于成本，参见 v7 约定）"""
    out = []
    total_cost = 0.0
    # 兼容 v1.1 嵌套结构：portfolio["positions"] 可能是 dict，内含 "positions" key
    positions = portfolio["positions"]
    if isinstance(positions, dict):
        positions = positions.get("positions", [])
    for pos in positions:
        sym = pos["symbol"]
        shares = pos["shares"]
        # v1.1 使用 cost_price，旧版叫 cost，兼容两者
        cost = float(pos.get("cost_price", pos.get("cost", 0)))
        value = shares * cost
        out.append({
            "symbol": sym,
            "shares": shares,
            "cost": cost,
            "value": value,
            "weight": 0.0,  # 之后填充
        })
        total_cost += value
    for p in out:
        p["weight"] = p["value"] / total_cost if total_cost > 0 else 0.0
    return {"positions": out, "total_cost": total_cost}


# ----------------------------------------------------------------------------
# 命中规则
# ----------------------------------------------------------------------------

def find_shock_for_symbol(symbol: str, scenario: dict) -> float:
    """
    找个股 shock。逻辑：
    1) shocks 直接含该 symbol（最常见）
    2) 否则按分类 fallback（适用于宏观情景）
    """
    shocks = scenario.get("shocks", {})

    # 直接命中
    if symbol in shocks:
        return shocks[symbol] / 100.0

    # Tech 股票识别
    tech_growth = {"NVDA", "AMD", "SMCI", "AVGO", "TSLA", "PLTR", "CRWD",
                   "PANW", "SNOW"}
    tech_mature = {"MSFT", "GOOGL", "GOOG", "AMZN", "META", "AAPL",
                   "ORCL", "CRM", "ADBE", "INTC"}
    is_tech_growth = symbol in tech_growth
    is_tech_mature = symbol in tech_mature
    is_tech = is_tech_growth or is_tech_mature

    # 宏观情景 fallback
    cat = scenario.get("category", "")
    if cat == "macro":
        # 1. 针对性 tech shock
        if is_tech_growth and "HIGH_GROWTH_TECH" in shocks:
            return shocks["HIGH_GROWTH_TECH"] / 100.0
        if is_tech_mature and "TECH_MATURE" in shocks:
            return shocks["TECH_MATURE"] / 100.0
        if is_tech and "TECH" in shocks:
            return shocks["TECH"] / 100.0
        if is_tech and "GROWTH_STOCKS" in shocks:
            return shocks["GROWTH_STOCKS"] / 100.0

        # 2. 通用基础 + 科技额外（bear_market 场景）
        base = 0.0
        if "US_EQUITIES" in shocks:
            base = shocks["US_EQUITIES"] / 100.0
        elif "US_LARGE_CAP" in shocks:
            base = shocks["US_LARGE_CAP"] / 100.0

        # 科技股额外（bear_market: US_LARGE_CAP + TECH_EXTRA）
        if is_tech and "TECH_EXTRA" in shocks:
            base += shocks["TECH_EXTRA"] / 100.0

        # 3. LONG_DURATION 涵盖长期资产（高估值科技也适用）
        if base == 0.0 and is_tech and "LONG_DURATION" in shocks:
            base = shocks["LONG_DURATION"] / 100.0

        if base != 0.0:
            return base

    # sector 场景 fallback (tech_correction, ai_bubble_burst)
    if cat == "sector" and is_tech:
        # AI 泡沫破裂场景：AAPL 实际受影响约 -25%（公开资料）
        name = scenario.get("name", "")
        if "AI Bubble" in name:
            if is_tech_growth:
                return -0.40  # 成长股重创
            elif is_tech_mature:
                return -0.25  # 成熟股中等
        # 科技股修正：所有 tech 都有影响
        if "Tech" in name or "Technology" in name:
            return -0.20

    return 0.0  # 该情景下未受影响


# ----------------------------------------------------------------------------
# 模拟
# ----------------------------------------------------------------------------

def simulate_scenario(portfolio_val: dict, scenario: dict) -> dict:
    """
    模拟一个情景。
    返回：每个持仓的损失 + 组合总计损失
    """
    positions = portfolio_val["positions"]
    total_cost = portfolio_val["total_cost"]

    rows = []
    total_loss = 0.0
    weighted_shock = 0.0

    for p in positions:
        shock = find_shock_for_symbol(p["symbol"], scenario)
        pos_value = p["value"]
        pos_loss = pos_value * shock  # shock 是负数 (e.g., -0.2), 所以 pos_loss 是负数
        new_value = pos_value + pos_loss  # 等同于 pos_value - |pos_loss|
        loss_pct = shock * 100.0
        weight = p["weight"]

        rows.append({
            "symbol": p["symbol"],
            "shares": p["shares"],
            "cost": p["cost"],
            "value": pos_value,
            "weight": weight,
            "shock_pct": loss_pct,
            "loss": pos_loss,
            "new_value": new_value,
        })
        total_loss += pos_loss
        weighted_shock += weight * shock

    new_total = total_cost + total_loss  # total_loss 是负数，所以是 total_cost - |total_loss|
    return {
        "scenario": scenario,
        "rows": rows,
        "total_cost": total_cost,
        "new_total": new_total,
        "total_loss": total_loss,
        "total_loss_pct": (total_loss / total_cost * 100.0) if total_cost > 0 else 0.0,
        "weighted_shock_pct": weighted_shock * 100.0,
    }


# ----------------------------------------------------------------------------
# 报告生成
# ----------------------------------------------------------------------------

def fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def fmt_pct(p: float, sign: bool = False) -> str:
    if sign and p >= 0:
        return f"+{p:.2f}%"
    return f"{p:.2f}%"


def severity_color(pct_loss: float) -> str:
    """颜色分级（pct_loss 为正数表示损失%）"""
    abs_pl = abs(pct_loss)
    if abs_pl < 10:
        return "🟢 LOW"
    elif abs_pl < 20:
        return "🟡 MEDIUM"
    elif abs_pl < 35:
        return "🟠 HIGH"
    else:
        return "🔴 EXTREME"


def render_scenario_report(result: dict, portfolio_val: dict) -> str:
    s = result["scenario"]
    lines = []
    lines.append(f"## {s['name']}")
    lines.append("")
    lines.append(f"- **分类**：`{s.get('category', 'N/A')}`")
    lines.append(f"- **触发**：`{s.get('trigger', 'N/A')}`")
    lines.append(f"- **运行时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append("")
    lines.append("### 组合影响")
    lines.append("")
    lines.append(f"- **组合总成本**：`{fmt_money(result['total_cost'])}`")
    lines.append(f"- **组合新价值**：`{fmt_money(result['new_total'])}`")
    loss = abs(result['total_loss'])
    pct = abs(result['total_loss_pct'])
    lines.append(f"- **总损失**：`{fmt_money(loss)}` ({pct:.2f}%)")
    lines.append(f"- **加权冲击**：`{abs(result['weighted_shock_pct']):.2f}%`")
    lines.append(f"- **脆弱性等级**：`{severity_color(pct)}`")
    lines.append("")
    lines.append("### 持仓明细")
    lines.append("")
    lines.append("| 标的 | 持仓 | 成本 | 市值 | 权重 | 跌幅 | 损失 | 新值 |")
    lines.append("|------|------|------|------|------|------|------|------|")
    for r in result["rows"]:
        lines.append(
            f"| {r['symbol']} | {r['shares']} | {fmt_money(r['cost'])} | "
            f"{fmt_money(r['value'])} | {r['weight']*100:.1f}% | "
            f"{r['shock_pct']:.2f}% | {fmt_money(abs(r['loss']))} | "
            f"{fmt_money(r['new_value'])} |"
        )
    lines.append("")
    lines.append("### 风险解读")
    lines.append("")
    if pct < 15:
        lines.append("- 组合在该情景下损失可控。")
        lines.append("- 整体防御能力良好。")
    elif pct < 25:
        lines.append("- 中等程度损失，需要关注。")
        lines.append("- 检视是否有结构性脆弱（例如行业集中）。")
    elif pct < 40:
        lines.append("- 🔴 严重损失。该情景触发组合严重脆弱。")
        lines.append("- 必须考虑减少脆弱性最高的头寸。")
    else:
        lines.append("- 🔴 极端损失。组合在该情景下接近毁灭性打击。")
        lines.append("- 强烈建议审视持仓结构。")
    lines.append("")
    # 找最脆弱（损失绝对值最大）
    if result["rows"]:
        worst = max(result["rows"], key=lambda x: abs(x["loss"]))
        lines.append(f"- **最脆弱标的**：`{worst['symbol']}` "
                     f"(权重 {worst['weight']*100:.1f}%, 损失 {fmt_money(abs(worst['loss']))})")
    lines.append("")
    return "\n".join(lines)


def render_full_report(results: list, portfolio_val: dict) -> str:
    """完整报告 — 多情景汇总"""
    lines = []
    lines.append("# Stress Test Report — 组合压力测试")
    lines.append("")
    lines.append(f"**生成时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"**组合成本**：`{fmt_money(portfolio_val['total_cost'])}`")
    lines.append(f"**持仓数**：`{len(portfolio_val['positions'])}`")
    lines.append("")
    lines.append("> ⚠️ **声明**：本报告是 hypothetical 风险模拟，**不是预测**，**不是交易建议**。")
    lines.append("> 所有跌幅基于历史事件或合理假设，仅用于评估组合脆弱性。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 一、情景汇总")
    lines.append("")
    lines.append("| 情景 | 分类 | 总损失 | 损失% | 加权冲击 | 脆弱性 |")
    lines.append("|------|------|--------|-------|----------|--------|")
    for r in results:
        s = r["scenario"]
        loss = abs(r["total_loss"])
        pct = abs(r["total_loss_pct"])
        ws = abs(r["weighted_shock_pct"])
        lines.append(
            f"| {s['name']} | {s.get('category', 'N/A')} | "
            f"{fmt_money(loss)} | {pct:.2f}% | {ws:.2f}% | "
            f"{severity_color(pct)} |"
        )
    lines.append("")
    # 找出最严峻情景（损失最大 = pct 最负）
    worst = min(results, key=lambda x: x["total_loss_pct"])
    worst_pct = abs(worst['total_loss_pct'])
    lines.append(f"**最严峻情景**：`{worst['scenario']['name']}` "
                 f"(损失 {worst_pct:.2f}%)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 二、详细分解")
    lines.append("")
    for r in results:
        lines.append(render_scenario_report(r, portfolio_val))
        lines.append("---")
        lines.append("")
    lines.append("")
    lines.append("## 三、纪律声明")
    lines.append("")
    lines.append("- 本报告仅用于风险评估，**不构成任何买卖建议**。")
    lines.append("- 模拟结果不预测未来，仅反映特定假设下的脆弱性。")
    lines.append("- 投资决策需结合基本面、估值、宏观状态综合判断。")
    lines.append("- 决策权在用户，Atlas 提供分析辅助。")
    lines.append("")
    lines.append(f"*Atlas Stress Test · v10 · {datetime.now().strftime('%Y-%m-%d')}*")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def run_scenarios(scenario_keys: list, custom_spec: str = None) -> str:
    """运行一组情景，返回报告"""
    portfolio = load_portfolio()
    pv = compute_position_values(portfolio)

    # 决定情景
    if custom_spec:
        cs = parse_custom_shocks(custom_spec)
        scenario = {
            "name": "Custom Scenario — 自定义",
            "category": "custom",
            "trigger": "用户自定义",
            "shocks": cs,
        }
        scenarios = [scenario]
    else:
        scenarios = []
        for k in scenario_keys:
            if k in PRESET_SCENARIOS:
                scenarios.append(PRESET_SCENARIOS[k])
            elif k == "all":
                scenarios = list(PRESET_SCENARIOS.values())
                break
            else:
                print(f"⚠️ 未知情景：{k}", file=sys.stderr)

    if not scenarios:
        print("⚠️ 没有有效情景", file=sys.stderr)
        sys.exit(1)

    # 模拟
    results = []
    for s in scenarios:
        results.append(simulate_scenario(pv, s))

    # 渲染
    report = render_full_report(results, pv)

    # 输出
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(REPORTS_DIR, f"A股压力测试_{date_str}.md")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"✅ Report saved: {out_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Atlas Scenario Engine v10 — 组合压力测试")
    parser.add_argument(
        "--scenario", nargs="+", default=["all"],
        help="情景名 (bear_market / tech_correction / ai_bubble_burst / "
             "recession / inflation_surge / rate_shock / china_tech_crisis / "
             "geopolitical / all)")
    parser.add_argument(
        "--custom", type=str, default=None,
        help="自定义情景，格式：NVDA:-50,MSFT:-30")
    parser.add_argument(
        "--list", action="store_true",
        help="列出所有可用情景")
    parser.add_argument(
        "--stdout", action="store_true",
        help="输出到 stdout 而非文件")
    args = parser.parse_args()

    if args.list:
        print("可用情景：")
        for k, v in PRESET_SCENARIOS.items():
            print(f"  - {k}: {v['name']}")
        return

    report = run_scenarios(args.scenario, args.custom)

    if args.stdout:
        print(report)


if __name__ == "__main__":
    main()
