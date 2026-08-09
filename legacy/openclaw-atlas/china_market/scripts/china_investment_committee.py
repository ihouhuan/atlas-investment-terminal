#!/usr/bin/env python3
"""
Atlas A 股投资委员会 v1.1（五角色版本）
输入：A 股代码
输出：A 股 Committee Report

A 股 Investment Committee 五角色：
  1. 多头分析师 (Bull Analyst) — 基本面 / 估值 / 增长
  2. 资金流分析师 (Capital Flow Analyst) — 北向 / 主力 / 散户
  3. 政策分析师 (Policy Analyst) — 行业政策 / 监管 / 战略方向
  4. 空头分析师 (Bear Analyst) — 风险 / 竞争 / 行业逆风
  5. 风险分析师 (Risk Analyst) — 仓位规则 / 流动性 / 波动率

保存：investment/china_market/reports/committee/{TICKER}_committee_{YYYY-MM-DD}.md
"""

import argparse
import os
import sys
import warnings
from datetime import datetime

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
from china_valuation_engine import (
    fetch_valuation_data,
    calculate_dynamic_rating,
    calculate_pe_percentile,
    estimate_industry_from_pe,
    INDUSTRY_PE_REFERENCE,
)

from core.paths import INVESTMENT_DIR, 投委会报告_DIR as _DEFAULT_OUTPUT_DIR


# === 角色观点生成 ===

def generate_bull_view(data: dict) -> str:
    """
    多头分析师（Bull Analyst）。
    关注：基本面 / 估值 / 增长 / 行业前景。
    """
    pe = data.get('pe', 0)
    pb = data.get('pb', 0)
    market_cap = data.get('market_cap_yi', 0)
    name = data.get('name', symbol_placeholder(data.get('symbol', 'N/A')))

    points = []

    # 估值论点
    if 0 < pe < 20:
        points.append(f'✅ **估值优势**：当前 PE {pe:.1f} 处于合理偏低区间（行业平均约 {INDUSTRY_PE_REFERENCE.get("综合", 20):.0f}），具备安全边际')
    elif 20 <= pe < 35:
        points.append(f'⚪ **估值中性**：当前 PE {pe:.1f} 处于行业中位水平，估值并非买入的核心驱动')
    elif pe >= 35:
        points.append(f'⚠️ **估值偏高**：PE {pe:.1f} 偏高，需要强增长支撑')

    # 市值论点
    if market_cap > 1000:
        points.append(f'✅ **大盘股优势**：市值 {market_cap:.0f} 亿，行业地位稳固，抗风险能力强')
    elif 200 < market_cap <= 1000:
        points.append(f'⚪ **中盘成长**：市值 {market_cap:.0f} 亿，兼具规模和成长空间')
    elif market_cap <= 200:
        points.append(f'⚠️ **小盘风险**：市值 {market_cap:.0f} 亿，波动大，机构关注度可能不足')

    # 60 天位置
    if data.get('high_60d') and data.get('low_60d'):
        pos = (data['price'] - data['low_60d']) / (data['high_60d'] - data['low_60d']) * 100
        if pos < 30:
            points.append(f'✅ **价格低位**：60 天位置 {pos:.0f}%，处于近期低位，可能是加仓窗口')
        elif pos > 70:
            points.append(f'⚠️ **价格高位**：60 天位置 {pos:.0f}%，接近近期高点，需谨慎追涨')

    # 行业增长性（简化）
    points.append('💡 **行业逻辑**：A 股多数行业受政策驱动，建议关注产业政策方向')

    # 总结
    if len(points) >= 3:
        conclusion = '🟢 **Bull 立场**：基本面有支撑，建议关注'
    elif len(points) >= 1:
        conclusion = '🟡 **Bull 立场**：中性偏多，需要更好的入场时机'
    else:
        conclusion = '🔴 **Bull 立场**：当前没有明显多头逻辑'

    view = '**多头分析师观点**：\n\n' + '\n'.join(f'- {p}' for p in points) + f'\n\n{conclusion}'
    return view


def generate_capital_flow_view(data: dict) -> str:
    """
    资金流分析师（Capital Flow Analyst）。
    关注：北向资金 / 主力资金 / 散户 / 融资融券 / 机构调研。
    """
    turnover = data.get('turnover_pct', 0)
    market_cap = data.get('market_cap_yi', 0)
    name = data.get('name', symbol_placeholder(data.get('symbol', 'N/A')))

    points = []

    # 换手率信号
    if turnover > 5:
        points.append(f'⚠️ **高换手**：换手率 {turnover:.1f}%，资金博弈激烈（可能是主力出货或游资炒作）')
    elif turnover > 2:
        points.append(f'⚪ **活跃换手**：换手率 {turnover:.1f}%，正常交易活跃度')
    elif turnover > 0.5:
        points.append(f'✅ **正常换手**：换手率 {turnover:.1f}%，流动性适中')
    else:
        points.append(f'⚠️ **低换手**：换手率 {turnover:.1f}%，关注度低，流动性差')

    # 市值/资金关注度
    if market_cap > 1000:
        points.append('✅ **机构覆盖**：大盘股通常有较多基金和北向资金覆盖')
    elif market_cap < 200:
        points.append('⚠️ **资金关注度低**：小盘股机构关注少，主要靠散户和游资')

    # 待接入字段
    points.append('💡 **待接入数据**：')
    points.append('- 北向资金日度变化（需专业接口）')
    points.append('- 融资融券余额变化（需专业接口）')
    points.append('- 基金季报持仓比例（需 Tushare）')
    points.append('- 机构调研密度（需专业接口）')

    # 总结
    if '高换手' in '\n'.join(points):
        conclusion = '🟡 **资金面立场**：活跃但需警惕主力动向'
    elif '正常换手' in '\n'.join(points):
        conclusion = '⚪ **资金面立场**：平稳，无明显信号'
    else:
        conclusion = '🟡 **资金面立场**：关注度不足，流动性风险存在'

    view = '**资金流分析师观点**：\n\n' + '\n'.join(f'- {p}' for p in points) + f'\n\n{conclusion}'
    return view


def generate_policy_view(data: dict) -> str:
    """
    政策分析师（Policy Analyst）。
    关注：行业政策 / 监管 / 战略方向 / 产业链位置。
    """
    pe = data.get('pe', 0)
    pb = data.get('pb', 0)
    name = data.get('name', symbol_placeholder(data.get('symbol', 'N/A')))

    points = []

    # 根据 PE 推断行业 + 政策方向
    industry = estimate_industry_from_pe(pe, data.get('market_cap_yi', 0), data.get('name', ''))

    # 政策方向（基于行业）
    policy_signals = {
        '白酒': '🟡 政策风险中等（消费税改革关注）',
        '银行': '🟢 政策友好（金融让利实体 + 估值修复）',
        '保险': '🟢 政策友好（养老第三支柱 + 长端利率上行）',
        '证券': '🟢 政策友好（注册制 + 财富管理转型）',
        '地产': '🔴 政策风险高（房住不炒长期定调）',
        '家电': '🟡 政策中性（消费刺激 + 以旧换新）',
        '汽车': '🟡 政策中性（新能源补贴退坡 + 出口政策）',
        '医药': '🟡 政策中性（集采压力 + 创新药支持）',
        '电子': '🟢 政策友好（国产替代 + 大基金三期）',
        '计算机': '🟢 政策友好（数字中国 + AI 算力）',
        '通信': '🟢 政策友好（5G + 卫星互联网）',
        '传媒': '🟡 政策中性偏紧（监管常态化）',
        '军工': '🟢 政策友好（十四五 + 地缘紧张）',
        '新能源': '🟢 政策友好（双碳战略 + 出海）',
        '光伏': '🟡 政策中性（产能过剩担忧）',
        '锂电池': '🟡 政策中性（产能过剩担忧）',
        '有色金属': '🟢 政策中性（战略资源 + 美元周期）',
        '煤炭': '🟡 政策中性（双碳目标 vs 能源安全）',
        '石油石化': '🟡 政策中性（能源安全 + 转型）',
        '钢铁': '🟡 政策中性（产能控制 + 绿色化）',
        '化工': '🟡 政策中性（安全环保 + 高端化）',
        '零售': '🟢 政策中性偏友好（消费刺激 + 数字零售）',
        '旅游': '🟢 政策友好（消费复苏 + 入境游开放）',
        '公用事业': '🟢 政策中性（电改 + 估值修复）',
    }

    signal = policy_signals.get(industry, '⚪ 政策中性（行业分类待明确）')
    points.append(f'**行业估算**：{industry}')
    points.append(f'**政策信号**：{signal}')

    # 通用政策观察
    points.append('**当前 A 股政策环境**（2026）：')
    points.append('- 🟢 新质生产力（科技 + 制造 + 数字）')
    points.append('- 🟢 设备更新 + 以旧换新（消费）')
    points.append('- 🟡 房地产（持续出清 vs 风险化解）')
    points.append('- 🟢 出海战略（一带一路 + 制造业升级）')

    # 结论
    if '🟢' in signal:
        conclusion = '🟢 **政策立场**：政策友好，可适度超配'
    elif '🔴' in signal:
        conclusion = '🔴 **政策立场**：政策风险高，建议谨慎'
    else:
        conclusion = '⚪ **政策立场**：政策中性，按基本面评估'

    view = '**政策分析师观点**：\n\n' + '\n'.join(f'- {p}' for p in points) + f'\n\n{conclusion}'
    return view


def generate_bear_view(data: dict) -> str:
    """
    空头分析师（Bear Analyst）。
    关注：估值风险 / 增长放缓 / 行业逆风 / 公司治理。
    """
    pe = data.get('pe', 0)
    pb = data.get('pb', 0)
    market_cap = data.get('market_cap_yi', 0)
    name = data.get('name', symbol_placeholder(data.get('symbol', 'N/A')))

    points = []

    # 估值风险
    if pe > 50:
        points.append(f'🔴 **估值杀风险**：PE {pe:.1f} 远高于行业平均，一旦增长不及预期或市场风险偏好下降，可能出现 30-50% 估值压缩')
    elif pe > 30:
        points.append(f'⚠️ **估值偏高**：PE {pe:.1f} 偏高，需要持续高增长支撑')

    # 市值风险
    if market_cap > 5000:
        points.append(f'⚠️ **市值天花板**：市值 {market_cap:.0f} 亿，已经接近行业天花板，成长空间有限')

    # 60 天位置风险
    if data.get('high_60d') and data.get('low_60d'):
        pos = (data['price'] - data['low_60d']) / (data['high_60d'] - data['low_60d']) * 100
        if pos > 80:
            points.append(f'⚠️ **短期超买**：60 天位置 {pos:.0f}%，技术面超买，回调风险加大')

    # 波动率
    vol = data.get('volatility_annual', 0)
    if vol > 50:
        points.append(f'🔴 **高波动**：年化波动率 {vol:.0f}%，下行风险放大')

    # 通用风险
    points.append('**A 股通用风险**：')
    points.append('- 政策风险（行业政策变化）')
    points.append('- 流动性风险（小盘股 / 极端行情）')
    points.append('- 监管风险（信息披露 / 财务造假）')
    points.append('- 地缘风险（中美关系 / 出口管制）')

    # 总结
    risk_count = sum(1 for p in points if '🔴' in p)
    warn_count = sum(1 for p in points if '⚠️' in p)
    if risk_count >= 2:
        conclusion = '🔴 **Bear 立场**：多重下行风险，建议减仓或观望'
    elif warn_count >= 2:
        conclusion = '🟡 **Bear 立场**：风险信号较多，需谨慎'
    else:
        conclusion = '⚪ **Bear 立场**：风险可控'

    view = '**空头分析师观点**：\n\n' + '\n'.join(f'- {p}' for p in points) + f'\n\n{conclusion}'
    return view


def generate_risk_view(data: dict, rating: dict) -> str:
    """
    风险分析师（Risk Analyst）。
    关注：仓位规则 / 流动性 / 波动率 / 综合风险评级。
    """
    name = data.get('name', symbol_placeholder(data.get('symbol', 'N/A')))
    rating_text = rating['rating']

    points = []

    # 仓位建议
    if rating_text == 'LOW':
        points.append(f'✅ **仓位规则**：评级 LOW，建议核心仓单股 ≤15%（v1.1）')
    elif rating_text == 'MEDIUM':
        points.append(f'⚠️ **仓位规则**：评级 MEDIUM，建议核心仓 ≤15% / 成长仓 ≤8%（v1.1）')
    else:
        points.append(f'🔴 **仓位规则**：评级 HIGH，建议主题仓 ≤3% / 成长仓 ≤8%（v1.1）')

    # 现金规则
    points.append('💰 **现金规则**：组合现金 ≥20%（v1.1 强制）')

    # 流动性
    turnover = data.get('turnover_pct', 0)
    if turnover > 5:
        points.append(f'⚠️ **流动性**：换手率 {turnover:.1f}%，盘中流动性充足（但需注意主力动向）')
    elif turnover < 0.5:
        points.append(f'🔴 **流动性风险**：换手率 {turnover:.1f}%，小盘股流动性差，大单冲击大')

    # 触发器
    points.append('**风险触发器**：')
    points.append('- 单日组合亏损 -3% → 暂停 review')
    points.append('- 单股仓位 > 上限 → 立即 rebalance')
    points.append('- 行业 > 40% → 立即 rebalance')

    # 总结
    if rating_text == 'HIGH':
        conclusion = '🔴 **Risk 立场**：高风险，建议小仓位试探或观望'
    elif rating_text == 'MEDIUM':
        conclusion = '🟡 **Risk 立场**：中等风险，需控制仓位'
    else:
        conclusion = '🟢 **Risk 立场**：低风险，可作为核心配置'

    view = '**风险分析师观点**：\n\n' + '\n'.join(f'- {p}' for p in points) + f'\n\n{conclusion}'
    return view


def symbol_placeholder(symbol: str) -> str:
    return symbol


# === 综合总结 ===

def synthesize_committee(views: dict, data: dict) -> str:
    """Atlas 综合总结"""
    rating = views.get('rating', 'MEDIUM')
    bull = views.get('bull', '')
    capital = views.get('capital', '')
    policy = views.get('policy', '')
    bear = views.get('bear', '')
    risk = views.get('risk', '')

    # 投票统计
    bull_score = sum(2 if '🟢' in view else 1 if '🟡' in view else 0 for view in [bull, capital, policy])
    bear_score = sum(2 if '🔴' in view else 1 if '🟡' in view else 0 for view in [bear])

    lines = []
    lines.append('**投票统计**：')
    lines.append('')
    lines.append(f'- 多头阵营（Bull + Capital + Policy）：{bull_score}/6')
    lines.append(f'- 空头阵营（Bear）：{bear_score}/2')
    lines.append(f'- 风险等级：{rating}')
    lines.append('')

    if bull_score > bear_score + 2 and rating == 'LOW':
        conclusion = '🟢 **综合结论**：多方共识 + 低风险 → **可适度建仓（核心仓 ≤15%）**'
    elif bull_score > bear_score:
        conclusion = '🟡 **综合结论**：多方略占优 → **可小仓位试探（核心仓 ≤10%）**'
    elif bear_score > bull_score:
        conclusion = '🔴 **综合结论**：空方占优 → **观望或减仓**'
    else:
        conclusion = '⚪ **综合结论**：多方空方平衡 → **持有不动，等待信号**'

    lines.append(conclusion)
    lines.append('')
    lines.append('**Atlas 立场**：')
    lines.append('')
    lines.append('- 不做短期价格预测')
    lines.append('- 不给明确买卖建议')
    lines.append('- 决策权归用户')
    lines.append('- 价格不是价值，市场先生情绪会波动')
    return '\n'.join(lines)


# === 报告生成 ===

def generate_china_committee(symbol: str, output_dir: str = None) -> str:
    """生成 A 股 Committee Report"""
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    time_str = today.strftime('%Y-%m-%d %H:%M:%S')

    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    # 拉取数据
    print(f'>>> 拉取 {symbol} 估值数据...')
    data = fetch_valuation_data(symbol)
    rating = calculate_dynamic_rating(data)

    # 生成五角色观点
    print(f'>>> 生成五角色观点...')
    bull = generate_bull_view(data)
    capital = generate_capital_flow_view(data)
    policy = generate_policy_view(data)
    bear = generate_bear_view(data)
    risk = generate_risk_view(data, rating)

    # 综合
    summary = synthesize_committee(
        {'bull': bull, 'capital': capital, 'policy': policy, 'bear': bear, 'risk': risk, 'rating': rating['rating']},
        data
    )

    # 报告
    lines = []
    lines.append(f'# {data.get("name", symbol)}（{symbol}） · 投委会投票报告')
    lines.append('')
    lines.append(f'> **生成时间**：{time_str}  |  **现价**：¥{data.get("price", 0):.2f}  |  **评级**：**{rating["rating"]}**（{rating["score"]:.0f} 分）')
    lines.append('')

    # 投票总览（最前面）
    lines.append('## 🎯 一句话结论')
    lines.append('')
    rating_emoji = {'LOW': '🟢', 'MEDIUM': '🟡', 'HIGH': '🔴'}.get(rating['rating'], '⚪')
    lines.append(f'{rating_emoji} **{data.get("name", symbol)}**：评级 {rating["rating"]}（{rating["score"]:.0f} 分），五角色投票结果如下 ↓')
    lines.append('')

    # 提取角色立场（从之前生成的字符串）
    def extract_stance(view_text, marker):
        for line in view_text.split('\n'):
            if marker in line:
                return line.strip()
        return '⚪ 无明确表态'

    bull_stance = extract_stance(bull, 'Bull 立场')
    capital_stance = extract_stance(capital, '资金面立场')
    policy_stance = extract_stance(policy, '政策立场')
    bear_stance = extract_stance(bear, 'Bear 立场')
    risk_stance = extract_stance(risk, 'Risk 立场')

    lines.append('## 📊 五角色投票一览')
    lines.append('')
    lines.append('| 角色 | 怎么看 | 一句话 |')
    lines.append('|------|--------|--------|')
    lines.append(f'| 🐂 多头 | 基本面 / 估值 | {bull_stance} |')
    lines.append(f'| 💰 资金面 | 主力 / 散户 | {capital_stance} |')
    lines.append(f'| 📜 政策面 | 行业政策 | {policy_stance} |')
    lines.append(f'| 🐻 空头 | 风险 / 逆风 | {bear_stance} |')
    lines.append(f'| ⚠️ 风控 | 仓位 / 波动 | {risk_stance} |')
    lines.append('')
    lines.append('---')
    lines.append('')

    # 一、五角色观点
    lines.append('## 🐂 二、多头分析师怎么看（基本面 / 估值 / 增长）')
    lines.append('')
    lines.append(bull)
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 💰 三、资金面分析师怎么看（主力 / 散户 / 资金博弈）')
    lines.append('')
    lines.append(capital)
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 📜 四、政策面分析师怎么看（行业政策 / 监管 / 战略方向）')
    lines.append('')
    lines.append(policy)
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## 🐻 五、空头分析师怎么看（风险 / 逆风 / 估值杀）')
    lines.append('')
    lines.append(bear)
    lines.append('')
    lines.append('---')
    lines.append('')

    lines.append('## ⚠️ 六、风控分析师怎么看（仓位 / 流动性 / 波动率）')
    lines.append('')
    lines.append(risk)
    lines.append('')
    lines.append('---')
    lines.append('')

    # 二、综合总结
    lines.append('## 📋 七、总结：五个角色加在一起怎么看')
    lines.append('')
    lines.append(summary)
    lines.append('')
    lines.append('---')
    lines.append('')

    # 三、关键指标
    lines.append('## 📈 八、关键指标一览')
    lines.append('')
    lines.append('| 指标 | 值 |')
    lines.append('|------|------|')
    lines.append(f'| 名称 | {data.get("name", symbol)} |')
    lines.append(f'| 现价 | ¥{data.get("price", 0):.2f} |')
    lines.append(f'| PE | {data.get("pe", 0):.2f} |')
    lines.append(f'| PB | {data.get("pb") if data.get("pb") else "N/A"} |')
    lines.append(f'| 市值 | {data.get("market_cap_yi", 0):.0f} 亿 |')
    lines.append(f'| 换手率 | {data.get("turnover_pct", 0):.2f}% |')
    if data.get('volatility_annual'):
        lines.append(f'| 年化波动率 | {data["volatility_annual"]:.1f}% |')
    lines.append(f'| **动态评级** | **{rating["rating"]}** ({rating["score"]:.1f} 分) |')
    lines.append('')
    lines.append('---')
    lines.append('')

    # 四、纪律提醒
    lines.append('## 🛡 九、Atlas 投资纪律提醒')
    lines.append('')
    lines.append('> **Atlas 投资纪律**：')
    lines.append('>')
    lines.append('> 1. 价格不是价值')
    lines.append('> 2. 不追涨杀跌')
    lines.append('> 3. 不因新闻冲动交易')
    lines.append('> 4. 保护资本 > 一切')
    lines.append('> 5. 决策权在用户')
    lines.append('')
    lines.append(f'> **免责声明**：本报告为 Atlas 投资研究工具自动生成。')
    lines.append('> 仅供研究参考，不构成投资建议。')
    lines.append('> 投资决策权归用户所有。')

    # 保存（使用中文文件名：股票名_报告类型_日期）
    stock_name = data.get('name', symbol)
    filename = f'{stock_name}_投委会报告_{date_str}.md'
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Atlas A 股投资委员会（五角色版本）',
        epilog='示例: python3 china_investment_committee.py 600519.SH',
    )
    parser.add_argument('symbol', help='A 股代码')
    parser.add_argument('--output-dir', help='输出目录')

    args = parser.parse_args()

    print(f'=== Atlas A 股 Committee · {args.symbol} ===')

    filepath = generate_china_committee(args.symbol, output_dir=args.output_dir)

    print()
    print(f'✅ 已生成: {filepath}')


if __name__ == '__main__':
    main()