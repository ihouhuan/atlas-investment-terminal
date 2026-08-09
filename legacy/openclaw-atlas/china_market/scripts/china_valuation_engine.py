#!/usr/bin/env python3
"""
Atlas A 股估值引擎 v1.1
输入：A 股代码
输出：Markdown 估值报告
保存：investment/china_market/reports/valuation/{TICKER}_valuation_{YYYY-MM-DD}.md

A 股估值方法：
  1. PE / 静态 PE（当前数据）
  2. PE 历史分位（需 5 年历史数据，当前占位）
  3. PB / PB 历史分位
  4. PEG（PE / 营收增长，待财务数据）
  5. PS（市销率）
  6. 股息率（占位）
  7. 行业对比（简化）
  8. DCF（简化版）
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
    fetch_history_kline,
    normalize_symbol,
)

from core.paths import INVESTMENT_DIR, 估值报告_DIR as _DEFAULT_OUTPUT_DIR

import requests


# === A 股行业平均 PE 参考（基于公开数据，2026-08-08 估算）===
INDUSTRY_PE_REFERENCE = {
    '白酒': 22,
    '银行': 5,
    '保险': 8,
    '证券': 14,
    '地产': 9,
    '家电': 12,
    '汽车': 18,
    '医药': 25,
    '电子': 35,
    '计算机': 45,
    '通信': 28,
    '传媒': 32,
    '军工': 45,
    '新能源': 22,
    '光伏': 16,
    '锂电池': 24,
    '有色金属': 18,
    '煤炭': 8,
    '石油石化': 10,
    '钢铁': 9,
    '化工': 14,
    '建材': 11,
    '零售': 28,
    '纺织服装': 18,
    '食品饮料': 26,
    '农林牧渔': 22,
    '旅游': 30,
    '交通运输': 12,
    '公用事业': 14,
}


def estimate_industry_from_pe(pe: float, market_cap: float, name: str = '') -> str:
    """根据股票名称优先匹配，其次用 PE 和市值估算行业"""
    # 优先从名称匹配（简单关键词）
    name_keywords = {
        '新能源': '新能源',
        '光伏': '光伏',
        '锂电': '锂电池',
        '电池': '锂电池',
        '汽车': '汽车',
        '银行': '银行',
        '证券': '证券',
        '保险': '保险',
        '白酒': '白酒',
        '酒': '白酒',
        '地产': '地产',
        '房产': '地产',
        '家电': '家电',
        '医药': '医药',
        '医院': '医药',
        '生物': '医药',
        '电子': '电子',
        '半导体': '电子',
        '芯片': '电子',
        '集成电路': '电子',
        '计算机': '计算机',
        '软件': '计算机',
        '网络': '计算机',
        '通信': '通信',
        '传媒': '传媒',
        '军': '军工',
        '光伏': '光伏',
        '传媒': '传媒',
        '有色': '有色金属',
        '黄金': '有色金属',
        '矿业': '有色金属',
        '煤炭': '煤炭',
        '石油': '石油石化',
        '石化': '石油石化',
        '钢铁': '钢铁',
        '化工': '化工',
        '零售': '零售',
        '百货': '零售',
        '商业': '零售',
        '集团': '零售',  # 很多集团是零售
        '旅游': '旅游',
        '酒店': '旅游',
        '公运': '公用事业',
        '电力': '公用事业',
        '能源': '公用事业',
    }
    for kw, ind in name_keywords.items():
        if kw in name:
            return ind

    # 没有匹配 → 按 PE 和市值估算（fallback）
    if pe < 8 and market_cap > 500:
        return '银行'
    elif pe < 12 and market_cap > 200:
        return '证券' if market_cap > 1000 else '保险'
    elif pe < 15 and market_cap > 1000:
        return '白酒' if market_cap > 5000 else '家电'
    elif pe > 50:
        return '新能源' if market_cap > 200 else '计算机'
    elif pe > 30 and market_cap < 500:
        return '零售'
    else:
        return '综合'


def fetch_valuation_data(symbol: str) -> dict:
    """获取 A 股估值所需数据"""
    out = {
        'symbol': symbol,
        'fetch_date': datetime.now().strftime('%Y-%m-%d'),
        'fetch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_ok': False,
        'errors': [],
    }

    try:
        quote = fetch_realtime_quote(symbol)
        if quote is None:
            out['errors'].append(f'{symbol}: 实时行情拉取失败')
            return out

        # K 线历史（用于波动率计算）
        dates, closes, errs = fetch_history_kline(symbol, days=60)
        if errs:
            out['errors'].extend(errs)

        out.update({
            'data_ok': True,
            'name': quote.get('name'),
            'market': quote.get('market'),
            'price': quote.get('price'),
            'prev_close': quote.get('prev_close'),
            'change_pct': quote.get('change_pct'),
            'pe': quote.get('pe') or 0,
            'pb': quote.get('pb') or 0,
            'market_cap_yi': quote.get('market_cap_yi') or 0,
            'circulating_cap_yi': quote.get('circulating_cap_yi') or 0,
            'volume_shares': quote.get('volume_shares') or 0,
            'turnover_pct': quote.get('turnover_pct') or 0,
            'high_60d': max(closes) if closes else quote.get('high', 0),
            'low_60d': min(closes) if closes else quote.get('low', 0),
            'closes': closes,
            'dates': dates,
        })

        # 估算波动率（基于 60 天日收益率）
        if closes and len(closes) > 5:
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            if returns:
                avg_return = sum(returns) / len(returns)
                variance = sum((r - avg_return)**2 for r in returns) / len(returns)
                std_dev = variance ** 0.5
                # 年化波动率（240 交易日）
                out['volatility_annual'] = std_dev * (240 ** 0.5) * 100

        return out
    except Exception as e:
        out['errors'].append(str(e))
        return out


def calculate_pe_percentile(current_pe: float, sector: str) -> dict:
    """
    估算 PE 历史分位（简化版）。
    实际生产需 5 年 PE 历史数据。
    """
    industry_avg = INDUSTRY_PE_REFERENCE.get(sector, 20)

    # 简化假设：A 股大多数行业 PE 在 [industry_avg*0.5, industry_avg*1.8] 区间
    pe_low = industry_avg * 0.5
    pe_high = industry_avg * 1.8

    if current_pe <= pe_low:
        percentile = 0
        zone = '低位（机会）'
    elif current_pe >= pe_high:
        percentile = 100
        zone = '高位（风险）'
    else:
        percentile = ((current_pe - pe_low) / (pe_high - pe_low)) * 100
        if percentile < 25:
            zone = '低位'
        elif percentile < 50:
            zone = '中低位'
        elif percentile < 75:
            zone = '中高位'
        else:
            zone = '高位'

    return {
        'current_pe': current_pe,
        'industry_avg': industry_avg,
        'pe_low': pe_low,
        'pe_high': pe_high,
        'percentile_estimate': percentile,
        'zone': zone,
        'note': '基于行业平均的简化估算（非真实历史分位）',
    }


def calculate_dynamic_rating(data: dict) -> dict:
    """
    动态评级（v1.1 原则）。
    5 维度：PE/PB（25%）+ 波动率（20%）+ 盈利稳定性（20%）+ 增长（20%）+ 行业周期（15%）
    """
    score = 50  # 基础分
    notes = []

    pe = data.get('pe', 0)
    pb = data.get('pb', 0)
    volatility = data.get('volatility_annual', 0)
    market_cap = data.get('market_cap_yi', 0)

    # 1. PE 评分（25%）
    pe_score = 50
    if pe <= 0:
        pe_score = 0
        notes.append('PE 为负（亏损），评级最高风险')
    elif pe < 12:
        pe_score = 90
        notes.append('PE 偏低估（<12）')
    elif pe < 20:
        pe_score = 70
        notes.append('PE 合理（12-20）')
    elif pe < 35:
        pe_score = 45
        notes.append('PE 偏高（20-35）')
    elif pe < 60:
        pe_score = 25
        notes.append('PE 高估（35-60）')
    else:
        pe_score = 10
        notes.append('PE 极高估（>60）')

    # 2. 波动率评分（20%）
    vol_score = 50
    if volatility > 60:
        vol_score = 10
        notes.append(f'年化波动率极高（{volatility:.0f}%）')
    elif volatility > 40:
        vol_score = 30
        notes.append(f'年化波动率高（{volatility:.0f}%）')
    elif volatility > 20:
        vol_score = 60
        notes.append(f'年化波动率中等（{volatility:.0f}%）')
    elif volatility > 0:
        vol_score = 80
        notes.append(f'年化波动率低（{volatility:.0f}%）')

    # 3. 盈利稳定性（20%）（占位，无 ROE 数据用 PE 间接评估）
    stab_score = 50
    if 0 < pe < 20 and pb > 0:
        stab_score = 70
        notes.append('盈利稳定性较好（基于 PE 间接推断）')
    elif pe > 50 or pe <= 0:
        stab_score = 20
        notes.append('盈利稳定性差')

    # 4. 增长（20%）（占位，无增长数据用市值间接评估）
    growth_score = 50
    if market_cap > 1000:
        growth_score = 65
        notes.append('大盘股（增长较稳定但天花板低）')
    elif market_cap < 200:
        growth_score = 40
        notes.append('小盘股（增长空间大但风险高）')

    # 5. 行业周期（15%）（占位）
    cycle_score = 50

    # 加权计算
    final_score = (
        pe_score * 0.25 +
        vol_score * 0.20 +
        stab_score * 0.20 +
        growth_score * 0.20 +
        cycle_score * 0.15
    )

    # 评级
    if final_score >= 70:
        rating = 'LOW'
    elif final_score >= 40:
        rating = 'MEDIUM'
    else:
        rating = 'HIGH'

    return {
        'score': round(final_score, 1),
        'rating': rating,
        'breakdown': {
            'PE (25%)': pe_score,
            '波动率 (20%)': vol_score,
            '盈利稳定性 (20%)': stab_score,
            '增长 (20%)': growth_score,
            '行业周期 (15%)': cycle_score,
        },
        'notes': notes,
    }


def generate_china_valuation(symbol: str, output_dir: str = None) -> str:
    """生成 A 股估值报告"""
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    time_str = today.strftime('%Y-%m-%d %H:%M:%S')

    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    # 拉取数据
    print(f'>>> 拉取 {symbol} 估值数据...')
    data = fetch_valuation_data(symbol)

    if not data.get('data_ok'):
        # 失败时也生成一个 minimal 报告
        market, code = normalize_symbol(symbol)
        lines = []
        lines.append(f'# {symbol} · A 股估值报告（数据缺失）')
        lines.append('')
        lines.append(f'> Atlas A 股估值引擎（China Equity v1.1）')
        lines.append(f'> **生成时间**：{time_str}')
        lines.append('')
        lines.append('## ⚠️ 数据缺失')
        lines.append('')
        lines.append('**错误信息**：')
        lines.append('')
        for err in data.get('errors', []):
            lines.append(f'- {err}')
        lines.append('')
        lines.append('**建议**：')
        lines.append('')
        lines.append('1. 检查网络（数据源：腾讯 qt.gtimg.cn）')
        lines.append('2. 检查 symbol 格式（600519.SH / sh600519 / 600519）')
        lines.append('3. 检查市场是否开市（A 股 9:30-15:00 GMT+8）')

        stock_name = data.get('name', symbol)
        filename = f'{stock_name}_估值报告_{date_str}.md'
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return filepath

    # 动态评级
    rating = calculate_dynamic_rating(data)

    # PE 历史分位
    pe_pct = calculate_pe_percentile(data.get('pe', 0), data.get('industry_estimate', '综合'))

    # 报告生成
    lines = []
    lines.append(f'# {symbol} · A 股估值报告')
    lines.append('')
    lines.append(f'> Atlas A 股估值引擎（China Equity v1.1）')
    lines.append(f'> **生成时间**：{time_str}')
    lines.append(f'> **数据源**：腾讯 qt.gtimg.cn（实时）+ web.ifzq.gtimg.cn（K线）')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 一、基础数据 ===
    lines.append('## 一、基础数据')
    lines.append('')
    lines.append('| 字段 | 值 |')
    lines.append('|------|------|')
    lines.append(f'| 名称 | {data.get("name", "N/A")} |')
    lines.append(f'| 代码 | {symbol} |')
    lines.append(f'| 交易所 | {"上海证券交易所" if data.get("market") == "SH" else "深圳证券交易所"} |')
    lines.append(f'| 现价 | ¥{data.get("price", 0):.2f} |')
    lines.append(f'| 市值 | {data.get("market_cap_yi", 0):.0f} 亿 |')
    lines.append(f'| 60 天最高 | ¥{data.get("high_60d", 0):.2f} |')
    lines.append(f'| 60 天最低 | ¥{data.get("low_60d", 0):.2f} |')
    lines.append(f'| 60 天位置 | {(data["price"] - data["low_60d"]) / (data["high_60d"] - data["low_60d"]) * 100 if data.get("high_60d") and data.get("low_60d") else 0:.1f}% |')
    if data.get('volatility_annual'):
        lines.append(f'| 年化波动率 | {data["volatility_annual"]:.1f}% |')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 二、估值指标 ===
    lines.append('## 二、估值指标')
    lines.append('')
    pe = data.get('pe', 0)
    pb = data.get('pb', 0)
    lines.append('| 指标 | 值 | 解读 |')
    lines.append('|------|------|------|')
    if pe > 0:
        pe_interp = '低估' if pe < 15 else ('合理' if pe < 30 else ('偏高' if pe < 50 else '高估'))
        lines.append(f'| 静态 PE | {pe:.2f} | {pe_interp} |')
    else:
        lines.append('| 静态 PE | N/A（亏损或数据缺失） | — |')

    if pb and pb > 0:
        pb_interp = '低估' if pb < 1.5 else ('合理' if pb < 4 else ('偏高' if pb < 8 else '高估'))
        lines.append(f'| PB | {pb:.2f} | {pb_interp} |')
    else:
        lines.append('| PB | N/A（数据未提供） | — |')

    # PS（市销率，占位）
    lines.append('| PS | N/A（需营收数据） | — |')
    # PEG
    lines.append('| PEG | N/A（需增长数据） | — |')
    # 股息率
    lines.append('| 股息率 | N/A（需分红数据） | — |')

    lines.append('')
    lines.append('**说明**：')
    lines.append('')
    lines.append('- PE/PB 来自实时行情')
    lines.append('- PS/PEG/股息率 需 Tushare 财务数据接入')
    lines.append('- 历史分位（5 年）需长期 K 线 + 历史 PE 数据')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 三、PE 历史分位（估算） ===
    lines.append('## 三、PE 历史分位（估算）')
    lines.append('')
    lines.append('| 指标 | 值 |')
    lines.append('|------|------|')
    lines.append(f'| 当前 PE | {pe_pct["current_pe"]:.2f} |')
    lines.append(f'| 行业平均 PE（参考） | {pe_pct["industry_avg"]:.1f} |')
    lines.append(f'| 估算分位 | {pe_pct["percentile_estimate"]:.1f}% |')
    lines.append(f'| 区间判断 | {pe_pct["zone"]} |')
    lines.append('')
    lines.append(f'**说明**：{pe_pct["note"]}')
    lines.append('')
    lines.append('**完整历史分位计算**需接入 Tushare 财务数据 + 5 年历史 PE。')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 四、动态评级 ===
    lines.append('## 四、动态风险评级（v1.1 原则）')
    lines.append('')
    lines.append('**评级方法**：5 维度动态评估')
    lines.append('')
    lines.append('| 维度 | 权重 | 评分 |')
    lines.append('|------|------|------|')
    for dim, score in rating['breakdown'].items():
        lines.append(f'| {dim} | — | {score} |')
    lines.append(f'| **综合评分** | — | **{rating["score"]}** |')
    lines.append('')
    lines.append(f'**最终评级**：**{rating["rating"]}**')
    lines.append('')
    lines.append('**评估依据**：')
    lines.append('')
    for note in rating['notes']:
        lines.append(f'- {note}')
    lines.append('')
    lines.append('**仓位上限**（基于评级）：')
    lines.append('')
    if rating['rating'] == 'LOW':
        lines.append('- 单股上限：≤10%（v10.5）')
    elif rating['rating'] == 'MEDIUM':
        lines.append('- 单股上限：≤5%（v10.5）')
    else:
        lines.append('- 单股上限：≤2%（v10.5）')
    lines.append('- **v1.1 三层仓位模型**：核心 ≤15% / 成长 ≤8% / 主题 ≤3%')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 五、估值结论 ===
    lines.append('## 五、估值结论')
    lines.append('')
    pe = data.get('pe', 0)
    rating_text = rating['rating']
    zone_text = pe_pct['zone']

    # 综合判断
    if rating_text == 'LOW' and '低位' in zone_text:
        conclusion = '🟢 **估值偏低，评级较低** — 可能是机会，但需结合基本面综合判断'
    elif rating_text == 'LOW' and '高' in zone_text:
        conclusion = '🟡 **估值偏高，评级较低** — 公司质量好但当前价格贵，等待回调'
    elif rating_text == 'HIGH':
        conclusion = '🔴 **风险较高** — 估值高或波动大，建议谨慎'
    else:
        conclusion = '⚪ **估值合理** — 中性判断，需结合行业趋势和资金面'

    lines.append(conclusion)
    lines.append('')
    lines.append('**Atlas 立场**：')
    lines.append('')
    lines.append('- 不预测短期价格')
    lines.append('- 不给买卖建议')
    lines.append('- 仅基于数据 + 原则 + 逻辑评估')
    lines.append('- 决策权归用户')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 六、附录：方法论 ===
    lines.append('## 附录：估值方法论')
    lines.append('')
    lines.append('**v1.1 估值框架**：')
    lines.append('')
    lines.append('1. **基础估值**：PE / PB（实时数据）')
    lines.append('2. **历史分位**：PE/PB 历史分位（需 5 年数据）')
    lines.append('3. **跨维度评分**：PE + 波动率 + 稳定性 + 增长 + 行业周期')
    lines.append('4. **动态评级**：自动输出 LOW/MEDIUM/HIGH')
    lines.append('5. **行业对比**：与行业平均 PE 对比')
    lines.append('6. **DCF（未来）**：需现金流数据')
    lines.append('')
    lines.append('**待接入数据源**：')
    lines.append('')
    lines.append('- **Tushare**（推荐）：财务数据 + 历史 PE/PB')
    lines.append('- **Wind/iFind**：专业数据（需订阅）')
    lines.append('- **同花顺**：财务数据')
    lines.append('')
    lines.append(f'> **免责声明**：本报告为 Atlas 投资研究工具自动生成。')
    lines.append('> 仅供研究参考，不构成投资建议。')
    lines.append('> 投资决策权归用户所有。')

    # 保存（使用中文文件名：股票名_报告类型_日期）
    stock_name = data.get('name', symbol)
    filename = f'{stock_name}_估值报告_{date_str}.md'
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Atlas A 股估值引擎（China Equity v1.1）',
        epilog='示例: python3 china_valuation_engine.py 600519.SH',
    )
    parser.add_argument('symbol', help='A 股代码')
    parser.add_argument('--output-dir', help='输出目录')

    args = parser.parse_args()

    print(f'=== Atlas A 股估值 · {args.symbol} ===')

    filepath = generate_china_valuation(args.symbol, output_dir=args.output_dir)

    print()
    print(f'✅ 已生成: {filepath}')


if __name__ == '__main__':
    main()