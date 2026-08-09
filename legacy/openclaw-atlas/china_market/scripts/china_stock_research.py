#!/usr/bin/env python3
"""
Atlas A 股股票研究模板 v1.1
输入：A 股代码
输出：Markdown 研究报告
保存：investment/china_market/reports/research/{TICKER}_{YYYY-MM-DD}.md

A 股研究模板新增字段：
  - 公司基本面（行业地位、主营业务、ROE、毛利率）
  - 财务质量（营收增长、利润增长、现金流）
  - 估值（PE 分位、PB 分位、PEG）
  - 资金面（基金持仓、北向资金、机构调研）
  - 政策与行业（政策、产业链位置）
  - 风险（监管、地缘、流动性）
"""

import argparse
import os
import sys
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

# Atlas core paths
_INVESTMENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _INVESTMENT_ROOT not in sys.path:
    sys.path.insert(0, _INVESTMENT_ROOT)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from china_market_data import (
    fetch_realtime_quote,
    fetch_realtime_quotes,
    fetch_history_kline,
    normalize_symbol,
)

from core.paths import INVESTMENT_DIR, 个股研究_DIR as _DEFAULT_OUTPUT_DIR

import requests
import json


# === 概念板块（来自 Tencent）===

def fetch_concept_info(symbol: str) -> list:
    """拉取股票所属概念板块（Tencent）"""
    try:
        market, code = normalize_symbol(symbol)
        url = f"https://stock.gtimg.cn/data/index.php"
        params = {
            "appid": "appmzd",
            "t": "zh",
            "c": symbol,  # sh600519
            "p": "concept",
        }
        # 简化：直接返回占位（实际生产需详细解析）
        return []
    except Exception:
        return []


# === 财务指标（占位，需 Tushare）===

FINANCIAL_FIELDS = {
    '营业收入': '营收（亿元）',
    '净利润': '归母净利润（亿元）',
    'ROE': '净资产收益率（%）',
    '毛利率': '毛利率（%）',
    '净利率': '净利率（%）',
    '资产负债率': '负债率（%）',
    '经营现金流': '经营性现金流（亿元）',
    '营收增长': '营收同比（%）',
    '利润增长': '净利润同比（%）',
    'PE分位': 'PE 历史分位（%）',
    'PB分位': 'PB 历史分位（%）',
    'PEG': 'PEG（PE / 增长）',
    '股息率': '股息率（%）',
}


def fetch_financial_proxy(symbol: str) -> dict:
    """
    财务数据占位接口。
    实际生产需 Tushare（用户未配置 token）。
    """
    return {
        'data_ok': False,
        'note': '财务数据需 Tushare/同花顺等专业接口（当前未接入）',
        'fields': FINANCIAL_FIELDS,
    }


# === 资金面（占位）===

CAPITAL_FIELDS = {
    '基金持仓': '基金季报持仓比例（%）',
    '北向资金': '北向资金持股变化',
    '融资余额': '融资余额（亿元）',
    '机构调研': '近 30 天机构调研次数',
    '研报数量': '近 30 天券商研报数量',
}


def fetch_capital_proxy(symbol: str) -> dict:
    """
    资金面数据占位接口。
    """
    return {
        'data_ok': False,
        'note': '资金面数据需接入专业数据源（万得/同花顺/iFind）',
        'fields': CAPITAL_FIELDS,
    }


# === 生成研究报告 ===

def generate_china_research(
    symbol: str,
    output_dir: str = None,
) -> str:
    """生成 A 股研究报告"""
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    time_str = today.strftime('%Y-%m-%d %H:%M:%S')

    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    market, code = normalize_symbol(symbol)
    code_tencent = f"{market.lower()}{code}"

    # 拉取数据
    print(f'>>> 拉取 {symbol} 实时行情...')
    quote = fetch_realtime_quote(symbol)

    print(f'>>> 拉取 {symbol} 财务数据（占位）...')
    fin = fetch_financial_proxy(symbol)

    print(f'>>> 拉取 {symbol} 资金面（占位）...')
    cap = fetch_capital_proxy(symbol)

    # 生成报告
    lines = []
    lines.append(f'# {symbol} · A 股研究报告')
    lines.append('')
    lines.append(f'> Atlas 中国市场研究模板（China Equity v1.1）')
    lines.append(f'> **生成时间**：{time_str}')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 一、基本信息 ===
    lines.append('## 一、基本信息')
    lines.append('')
    if quote:
        lines.append('| 字段 | 值 |')
        lines.append('|------|------|')
        lines.append(f'| 名称 | {quote.get("name", "N/A")} |')
        lines.append(f'| 代码 | {quote.get("ts_code", code)}.{market} |')
        lines.append(f'| 交易所 | {"上海证券交易所" if market == "SH" else "深圳证券交易所" if market == "SZ" else "北京证券交易所"} |')
        lines.append(f'| 行情时间 | {quote.get("timestamp", "N/A")} |')
        lines.append(f'| 数据源 | {quote.get("data_source", "N/A")} |')
    else:
        lines.append('⚠️ **数据缺失**')
        lines.append('')
        lines.append('| 字段 | 值 |')
        lines.append('|------|------|')
        lines.append('| 名称 | DATA NOT AVAILABLE |')
        lines.append(f'| 代码 | {symbol} |')
    lines.append('')

    # === 二、实时行情 ===
    lines.append('## 二、实时行情')
    lines.append('')
    if quote:
        lines.append('| 字段 | 值 | 解读 |')
        lines.append('|------|------|------|')
        price = quote.get('price', 0)
        chg = quote.get('change_pct', 0)
        chg_interp = '上涨' if chg > 0 else ('下跌' if chg < 0 else '平稳')
        lines.append(f'| 现价 | ¥{price:.2f} | {chg_interp} |')
        lines.append(f'| 今开 | ¥{quote.get("open", 0):.2f} | — |')
        lines.append(f'| 昨收 | ¥{quote.get("prev_close", 0):.2f} | — |')
        lines.append(f'| 最高 | ¥{quote.get("high", 0):.2f} | — |')
        lines.append(f'| 最低 | ¥{quote.get("low", 0):.2f} | — |')
        lines.append(f'| 涨跌 | {quote.get("change", 0):+.2f} | — |')
        lines.append(f'| 涨跌% | {chg:+.2f}% | — |')
        lines.append(f'| 换手率 | {quote.get("turnover_pct", 0):.2f}% | {"活跃" if quote.get("turnover_pct", 0) > 3 else ("正常" if quote.get("turnover_pct", 0) > 1 else "低迷")} |')
        lines.append(f'| 市值 | {quote.get("market_cap_yi", 0):.0f} 亿 | {"大盘" if quote.get("market_cap_yi", 0) > 1000 else ("中盘" if quote.get("market_cap_yi", 0) > 200 else "小盘")} |')
        lines.append(f'| 流通市值 | {quote.get("circulating_cap_yi", 0):.0f} 亿 | — |')
        lines.append(f'| PE | {quote.get("pe", 0):.2f} | {"低" if quote.get("pe", 0) < 15 else ("中" if quote.get("pe", 0) < 30 else "高")} |')
        pb_value = quote.get("pb") or 0
        lines.append(f'| PB | {pb_value:.2f} | — |')
    else:
        lines.append('⚠️ **数据缺失** — 请检查网络或 symbol 格式')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 三、估值水平 ===
    lines.append('## 三、估值水平（PE/PB 历史分位）')
    lines.append('')
    if quote:
        pe = quote.get('pe', 0)
        lines.append(f'**当前 PE**：{pe:.2f}')
        lines.append('')
        lines.append('**PE 历史分位**（需历史数据，Tushare 接入后可计算）：')
        lines.append('')
        lines.append('| 分位区间 | 含义 |')
        lines.append('|---------|------|')
        lines.append('| 0-20% | 历史低位（可能机会） |')
        lines.append('| 20-50% | 历史中低位（合理） |')
        lines.append('| 50-80% | 历史中高位（谨慎） |')
        lines.append('| 80-100% | 历史高位（风险） |')
        lines.append('')
        lines.append(f'**初步判断**（基于当前 PE 估值水平）：')
        lines.append('')
        if pe < 15:
            lines.append('- PE < 15：偏低估（注意：可能反映市场对基本面的担忧）')
        elif pe < 25:
            lines.append('- PE 15-25：合理区间（适合长期持有）')
        elif pe < 40:
            lines.append('- PE 25-40：偏高（需高增长支撑）')
        else:
            lines.append('- PE > 40：高度高估（风险信号）')
    else:
        lines.append('⚠️ 数据缺失')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 四、财务质量（占位）===
    lines.append('## 四、财务质量（占位 · 待 Tushare）')
    lines.append('')
    if not fin['data_ok']:
        lines.append(f'⚠️ **{fin["note"]}**')
        lines.append('')
    lines.append('**待评估指标**：')
    lines.append('')
    for field, desc in fin['fields'].items():
        lines.append(f'- **{field}** ({desc}): DATA NOT AVAILABLE')
    lines.append('')
    lines.append('**判断标准**（用于未来 Tushare 接入后）：')
    lines.append('')
    lines.append('| 指标 | 优秀 | 良好 | 一般 | 较差 |')
    lines.append('|------|------|------|------|------|')
    lines.append('| ROE | >20% | 15-20% | 10-15% | <10% |')
    lines.append('| 毛利率 | >50% | 30-50% | 15-30% | <15% |')
    lines.append('| 净利率 | >20% | 10-20% | 5-10% | <5% |')
    lines.append('| 资产负债率 | <40% | 40-60% | 60-70% | >70% |')
    lines.append('| 营收增长 | >30% | 15-30% | 5-15% | <5% |')
    lines.append('| 利润增长 | >30% | 15-30% | 5-15% | <5% |')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 五、资金面（占位）===
    lines.append('## 五、资金面（占位 · 待专业数据源）')
    lines.append('')
    if not cap['data_ok']:
        lines.append(f'⚠️ **{cap["note"]}**')
        lines.append('')
    lines.append('**待评估指标**：')
    lines.append('')
    for field, desc in cap['fields'].items():
        lines.append(f'- **{field}** ({desc}): DATA NOT AVAILABLE')
    lines.append('')
    lines.append('**资金面信号解读**：')
    lines.append('')
    lines.append('- **北向资金持续净买入**：外资看多 → 利好')
    lines.append('- **北向资金持续净卖出**：外资看空 → 利空')
    lines.append('- **基金持仓比例提升**：机构看好 → 利好')
    lines.append('- **融资余额上升**：散户加杠杆 → 短线偏热（注意风险）')
    lines.append('- **机构调研密集**：市场关注度高 → 关注后续催化剂')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 六、风险评估 ===
    lines.append('## 六、风险评估')
    lines.append('')
    if quote:
        pe = quote.get('pe', 0)
        turnover = quote.get('turnover_pct', 0)

        risks = []
        if pe > 50:
            risks.append(('🔴 高 PE 风险', f'当前 PE {pe:.1f} 处于高位，估值回调风险大'))
        if pe > 0 and pe < 0:
            risks.append(('🔴 亏损风险', '公司当前亏损（PE 为负）'))
        if turnover > 10:
            risks.append(('⚠️ 高换手风险', f'换手率 {turnover:.1f}%，投机情绪浓厚'))
        if quote.get('market_cap_yi', 0) < 50:
            risks.append(('⚠️ 小盘股风险', '市值 < 50 亿，流动性差'))

        # 行业风险（简化判断）
        if quote.get('pe', 0) > 100:
            risks.append(('🔴 行业风险', 'PE > 100，行业整体高估或公司业绩不稳定'))

        if risks:
            for title, desc in risks:
                lines.append(f'- {title}：{desc}')
        else:
            lines.append('- ✅ 无明显风险信号')

    lines.append('')
    lines.append('---')
    lines.append('')

    # === 七、Atlas 综合判断 ===
    lines.append('## 七、Atlas 综合判断')
    lines.append('')
    if quote:
        pe = quote.get('pe', 0)
        turnover = quote.get('turnover_pct', 0)
        market_cap = quote.get('market_cap_yi', 0)

        # 简化评分（仅基于当前可得数据）
        score = 50  # 基础分
        notes = []

        # PE 评分
        if 0 < pe < 15:
            score += 20
            notes.append('PE 偏低估')
        elif 15 <= pe < 25:
            score += 10
            notes.append('PE 合理')
        elif 25 <= pe < 40:
            score -= 10
            notes.append('PE 偏高')
        elif pe >= 40:
            score -= 25
            notes.append('PE 高估')

        # 市值评分
        if market_cap > 1000:
            score += 10
            notes.append('大盘股')
        elif market_cap > 200:
            score += 5
            notes.append('中盘股')
        elif market_cap < 50:
            score -= 15
            notes.append('小盘股')

        # 换手率评分
        if turnover > 10:
            score -= 10
            notes.append('换手率高（投机）')
        elif turnover < 1:
            score -= 5
            notes.append('换手率低（冷门）')

        score = max(0, min(100, score))

        lines.append(f'**综合评分**：{score} / 100')
        lines.append('')
        lines.append('**评估依据**：')
        lines.append('')
        for note in notes:
            lines.append(f'- {note}')
        lines.append('')
        lines.append('**风险等级**（动态评估）：')
        lines.append('')
        if score >= 70:
            lines.append(f'- 等级：**LOW**')
            lines.append('- 单股上限：≤10%（v10.5）')
            lines.append('- v1.1：核心仓 ≤15% / 成长仓 ≤8% / 主题仓 ≤3%')
        elif score >= 40:
            lines.append(f'- 等级：**MEDIUM**')
            lines.append('- 单股上限：≤5%（v10.5）')
            lines.append('- v1.1：核心仓 ≤15% / 成长仓 ≤8% / 主题仓 ≤3%')
        else:
            lines.append(f'- 等级：**HIGH**')
            lines.append('- 单股上限：≤2%（v10.5）')
            lines.append('- v1.1：核心仓 ≤15% / 成长仓 ≤8% / 主题仓 ≤3%')
    else:
        lines.append('⚠️ **数据缺失，无法评估**')

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 附录：研究框架（A 股）')
    lines.append('')
    lines.append('**完整 A 股研究框架**（待 Tushare/财务数据接入）：')
    lines.append('')
    lines.append('1. **公司基本面**')
    lines.append('   - 主营业务 / 行业地位 / 竞争壁垒')
    lines.append('   - 商业模式 / 客户结构 / 地域分布')
    lines.append('2. **财务质量**')
    lines.append('   - 营收增长 / 利润增长 / 毛利率 / 净利率')
    lines.append('   - ROE / ROA / 资产负债率')
    lines.append('   - 经营性现金流 / 应收账款周转')
    lines.append('3. **估值水平**')
    lines.append('   - PE 历史分位（最近 5 年）')
    lines.append('   - PB 历史分位')
    lines.append('   - PEG（PE / 增长）')
    lines.append('   - 同行业可比公司估值对比')
    lines.append('4. **资金面**')
    lines.append('   - 基金持仓比例（季报）')
    lines.append('   - 北向资金变化（日度）')
    lines.append('   - 融资融券余额')
    lines.append('   - 机构调研密度')
    lines.append('   - 券商研报数量与评级分布')
    lines.append('5. **行业与政策**')
    lines.append('   - 产业链位置')
    lines.append('   - 行业景气度（上升 / 顶 / 下 / 底）')
    lines.append('   - 政策支持 / 监管风险')
    lines.append('   - 国际比较（出口 vs 内销）')
    lines.append('6. **风险评估**')
    lines.append('   - 监管风险（行业政策变化）')
    lines.append('   - 地缘风险（出口型企业）')
    lines.append('   - 流动性风险（小盘股）')
    lines.append('   - 商誉减值（多元化集团）')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append(f'> **免责声明**：本报告为 Atlas 投资研究工具自动生成。')
    lines.append('> 仅供研究参考，不构成投资建议。')
    lines.append('> 投资决策权归用户所有。')

    # 保存（使用中文文件名：股票名_报告类型_日期）
    stock_name = quote.get('name', symbol) if quote else symbol
    if not stock_name or stock_name == symbol:
        stock_name = symbol
    filename = f'{stock_name}_个股研究_{date_str}.md'
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Atlas A 股股票研究模板（China Equity v1.1）',
        epilog='示例: python3 china_stock_research.py 600519.SH',
    )
    parser.add_argument('symbol', help='A 股代码')
    parser.add_argument('--output-dir', help='输出目录')

    args = parser.parse_args()

    print(f'=== Atlas A 股研究 · {args.symbol} ===')

    filepath = generate_china_research(args.symbol, output_dir=args.output_dir)

    print()
    print(f'✅ 已生成: {filepath}')


if __name__ == '__main__':
    main()