#!/usr/bin/env python3
"""
Atlas 跨市场观察工具 v1.0
=======================
用户工作流：
1. 21:30-04:00 美股交易时段：观察 SOX + 半导体个股
2. 次日 09:15-09:25 A 股集合竞价：观察映射标的
3. 09:30 开盘 30 分钟：确认板块持续性

⚠️ 这是辅助决策工具，不是交易建议。

数据源：
- 美股: yfinance (NVDA, MU, TSM, AMD, AVGO, SOX)
- A 股: Tencent web.ifzq.gtimg.cn

作者: Atlas Investment Office
"""

import os
import sys
import json
import math
from datetime import datetime, timedelta

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/Users/huan/.openclaw/workspace/investment/china_market/scripts')
from china_market_data import fetch_realtime_quote, normalize_symbol

# 美股映射表（用户自选股中提取的 A 股标的）
US_TO_A_MAPPING = {
    # 美股核心标的
    'NVDA': {
        'name': 'NVIDIA',
        'a_targets': ['300308.SZ', '002371.SZ', '688981.SH'],  # 中际旭创, 北方华创, 中芯国际
        'sector': 'AI 算力',
    },
    'MU': {
        'name': 'Micron (存储)',
        'a_targets': ['688981.SH', '688126.SH', '600460.SH'],  # 中芯国际, 沪硅产业, 士兰微
        'sector': '存储',
    },
    'TSM': {
        'name': '台积电',
        'a_targets': ['688981.SH', '002371.SZ', '688256.SH'],  # 中芯国际, 北方华创, 寒武纪
        'sector': '代工',
    },
    'AMD': {
        'name': 'AMD',
        'a_targets': ['688256.SH', '688041.SH', '002371.SZ'],  # 寒武纪, 海光信息, 北方华创
        'sector': 'CPU/GPU',
    },
    'AVGO': {
        'name': 'Broadcom',
        'a_targets': ['300308.SZ', '002463.SZ', '600487.SH'],  # 中际旭创, 沪电股份, 亨通光电
        'sector': '通信芯片',
    },
    '^SOX': {
        'name': '费城半导体指数',
        'a_targets': ['512480.SH', '515000.SH', '588080.SH'],  # 半导体ETF, 科技ETF, 科创50
        'sector': '整体板块',
    },
}

# A 股 ETF 池（用户自选股中 2 只 ETF）
A_SHARE_ETFS = {
    '588080.SH': '科创50ETF易方达',
    '516080.SH': '创新药ETF易方达',
}

def fetch_us_realtime(ticker: str) -> dict:
    """拉美股实时数据"""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        info = tk.info
        hist = tk.history(period='5d', interval='1d')
        
        if len(hist) == 0:
            return {'error': 'no data'}
        
        current = float(hist['Close'].iloc[-1])
        prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
        change_pct = (current / prev - 1) * 100
        
        # 5 日走势
        ret_5d = (current / float(hist['Close'].iloc[0]) - 1) * 100
        
        return {
            'ticker': ticker,
            'price': current,
            'prev_close': prev,
            'change_pct': change_pct,
            'ret_5d': ret_5d,
            'currency': 'USD',
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        return {'error': str(e)}

def analyze_us_signal(us_data: dict) -> str:
    """根据美股数据给出信号"""
    if 'error' in us_data:
        return '⚠️ 数据缺失'
    
    change = us_data['change_pct']
    ret_5d = us_data['ret_5d']
    
    if change > 3 and ret_5d > 5:
        return '🟢 强势（隔夜大幅上涨 + 趋势延续）'
    elif change > 1:
        return '🟢 偏强'
    elif change > -1:
        return '🟡 中性'
    elif change > -3:
        return '🔴 偏弱'
    else:
        return '🔴 弱势（隔夜大跌）'

def generate_cross_market_brief() -> str:
    """生成跨市场观察简报"""
    
    lines = []
    lines.append('# Atlas 跨市场观察简报')
    lines.append('')
    lines.append(f'> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M GMT+8")}')
    lines.append(f'> 用途: 辅助隔夜套利决策（美股半导体 → A 股映射）')
    lines.append('')
    lines.append('---')
    lines.append('')
    
    # 1. 美股半导体板块整体
    lines.append('## 一、美股半导体板块（费城半导体 SOX）')
    lines.append('')
    lines.append('| 美股标的 | 价格 | 日涨跌 | 5日累计 | 信号 |')
    lines.append('|---------|------|--------|---------|------|')
    
    for us_ticker in ['^SOX', 'NVDA', 'MU', 'TSM', 'AMD', 'AVGO']:
        data = fetch_us_realtime(us_ticker)
        if 'error' not in data:
            sig = analyze_us_signal(data)
            display_ticker = us_ticker.replace('^', '')
            lines.append(f"| {display_ticker:8} | ${data['price']:.2f} | {data['change_pct']:+.2f}% | {data['ret_5d']:+.2f}% | {sig} |")
    
    lines.append('')
    lines.append('---')
    lines.append('')
    
    # 2. A 股映射标的
    lines.append('## 二、A 股映射标的（实时行情）')
    lines.append('')
    lines.append('| A 股标的 | 代码 | 现价 | 涨跌 | 行业 |')
    lines.append('|---------|------|------|------|------|')
    
    all_a_targets = set()
    for us_ticker, info in US_TO_A_MAPPING.items():
        for target in info['a_targets']:
            all_a_targets.add(target)
    
    for sym in sorted(all_a_targets):
        quote = fetch_realtime_quote(sym)
        if quote and quote.get('price'):
            name = quote.get('name', sym)
            price = quote.get('price', 0)
            change = quote.get('change_pct', 0)
            # 行业
            industry = ''
            for us_t, info in US_TO_A_MAPPING.items():
                if sym in info['a_targets']:
                    industry = info['sector']
                    break
            lines.append(f"| {name:10} | {sym:10} | ¥{price:.2f} | {change:+.2f}% | {industry} |")
    
    lines.append('')
    lines.append('---')
    lines.append('')
    
    # 3. 操作建议（基于用户工作流）
    lines.append('## 三、决策框架（用户工作流对应）')
    lines.append('')
    lines.append('### 阶段 1: 21:30 - 04:00（美股交易时段）')
    lines.append('')
    lines.append('- 🟢 **强势信号**（SOX 大涨 +3%）：次日 A 股半导体板块可能高开，**竞价最强**个股值得关注')
    lines.append('- 🟡 **中性信号**：板块无明确方向，**观望为主**')
    lines.append('- 🔴 **弱势信号**（SOX 大跌 -3%）：**次日避免追高**，可考虑反向（但需谨慎）')
    lines.append('')
    lines.append('### 阶段 2: 09:15 - 09:25（A 股集合竞价）')
    lines.append('')
    lines.append('| 竞价强度 | 操作 |')
    lines.append('|---------|------|')
    lines.append('| 映射标的 +5% 以上，板块多股高开 | 🟢 候选：竞价最强 + 换手充分的龙头 |')
    lines.append('| 映射标的 +2% ~ +5%，板块跟涨 | 🟡 观察：等 09:30 后确认持续性 |')
    lines.append('| 映射标的 +0% ~ +2%，分化明显 | ⚪ 放弃：信号不足 |')
    lines.append('| 映射标的低开或冲高回落 | 🔴 放弃：坚决不追 |')
    lines.append('')
    lines.append('### 阶段 3: 09:30 - 10:00（开盘 30 分钟）')
    lines.append('')
    lines.append('- 🟢 **小仓位介入条件**：')
    lines.append('  - 板块多股跟涨（至少 3 只 +2% 以上）')
    lines.append('  - 龙头封板质量好（买一挂单大）')
    lines.append('  - 换手率 >5%（流动性充分）')
    lines.append('')
    lines.append('- 🔴 **放弃条件**：')
    lines.append('  - 板块冲高回落')
    lines.append('  - 龙头炸板（封不住）')
    lines.append('  - 成交量不足预期')
    lines.append('')
    lines.append('---')
    lines.append('')
    
    # 4. 止损止盈规则
    lines.append('## 四、持仓期间 · 纪律')
    lines.append('')
    lines.append('| 规则 | 数值 | 备注 |')
    lines.append('|------|------|------|')
    lines.append('| 止损 | -5% | 从买入价起 |')
    lines.append('| 止盈 | +5% 或 收盘前 14:30 | 次日卖出策略 |')
    lines.append('| 持仓时长 | T+1（次日卖）| 短线原则 |')
    lines.append('| 仓位上限 | 单股 ≤10% | 隔夜套利风险大 |')
    lines.append('| 累计止损 | 单日 -3% 总资金 | 全天停止交易 |')
    lines.append('')
    lines.append('---')
    lines.append('')
    
    # 5. 风险提示
    lines.append('## 五、关键风险')
    lines.append('')
    lines.append('1. **隔夜跳空风险**：美股尾盘跳水 → A 股次日开盘可能 -5% 直接触发止损')
    lines.append('2. **流动性风险**：A 股小盘股 09:25-09:30 集合竞价可能没有足够对手盘')
    lines.append('3. **板块轮动风险**：美股半导体上涨 ≠ A 股半导体跟随（30 天相关性仅 0.4 左右）')
    lines.append('4. **监管风险**：A 股 T+1 制度下，次日不能及时卖出会放大亏损')
    lines.append('5. **汇率风险**：美股收益还需换算回 CNY')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('*Atlas Investment Office · Cross-Market Observer v1.0 · 2026-08-08*')
    lines.append('')
    
    return '\n'.join(lines)


if __name__ == '__main__':
    print("=== Atlas 跨市场观察工具 ===")
    print()
    
    # 拉美股数据
    print(">>> 拉取美股半导体板块...")
    us_signals = {}
    for us_ticker in ['^SOX', 'NVDA', 'MU', 'TSM', 'AMD', 'AVGO']:
        data = fetch_us_realtime(us_ticker)
        us_signals[us_ticker] = data
    
    # 拉 A 股映射
    print(">>> 拉取 A 股映射标的...")
    a_targets = set()
    for us_ticker, info in US_TO_A_MAPPING.items():
        for target in info['a_targets']:
            a_targets.add(target)
    
    for sym in sorted(a_targets):
        quote = fetch_realtime_quote(sym)
    
    # 生成报告
    print(">>> 生成跨市场观察简报...")
    report = generate_cross_market_brief()
    
    out_path = f"/Users/huan/.openclaw/workspace/investment/跨市场观察/跨市场观察_{datetime.now().strftime('%Y-%m-%d')}.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 已生成: {out_path}")
