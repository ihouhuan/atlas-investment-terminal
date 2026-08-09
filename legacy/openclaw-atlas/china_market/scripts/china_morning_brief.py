#!/usr/bin/env python3
"""
Atlas China Morning Brief v1.1
A 股每日晨报生成器（China Equity 改造版）

输入：watchlist（A 股代码）
输出：每日晨报（Markdown）

A 股 Morning Brief 结构：
  1. 隔夜全球（美股情绪参考）
  2. A 股市场状态
  3. 热点板块（资金流向）
  4. 资金面（北向资金 / 融资融券 / 成交量）
  5. 自选股（Watchlist）
  6. 风险概览
  7. 今日观察

存储：investment/china_market/reports/china_morning_brief_{DATE}.md
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

# 复用 china_market_data
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from china_market_data import (
    fetch_realtime_quote,
    fetch_realtime_quotes,
    normalize_symbol,
    HEADERS,
    REQUEST_TIMEOUT,
)

# 复用 core market_data (美股情绪)
from core.paths import INVESTMENT_DIR, 早盘简报_DIR as _DEFAULT_OUTPUT_DIR

import requests


# 默认 A 股 watchlist（用户 2026-08-08 导入）
# 仅包含用户实际持仓 + 部分高关注度自选股
DEFAULT_CHINA_WATCHLIST = [
    '601899.SH',  # 紫金矿业（实际持仓 - 贵金属）
    '001258.SZ',  # 立新能源（实际持仓 - 电力/新能源）
    '600693.SH',  # 东百集团（实际持仓 - 零售）
    # 以下为部分高关注度自选股（用户可调整）
    '600403.SH',  # 大有能源（煤炭）
    '000657.SZ',  # 中钨高新（小金属）
    '600487.SH',  # 亨通光电（通信设备）
    '002463.SZ',  # 沪电股份（元件）
    '601138.SH',  # 工业富联（消费电子）
]


# === A 股指数 ===

CHINA_INDICES = {
    '000001.SH': '上证指数',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '000688.SH': '科创50',
}


def fetch_index_quote(symbol: str) -> dict:
    """拉取 A 股指数实时行情"""
    out = {'symbol': symbol, 'data_ok': False}
    try:
        market_code, code = normalize_symbol(symbol)
        url = f"https://qt.gtimg.cn/q={market_code.lower()}{code}"
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return out
        text = r.text.strip()
        if '="v_' in text or '="pv_' in text:
            # 指数使用 pv_ 开头
            text = text.replace('="pv_', '="v_')

        if "=" not in text:
            return out
        content = text.split('"', 2)[1] if text.count('"') >= 2 else ""
        if not content:
            return out

        fields = content.split("~")
        if len(fields) < 35:
            return out

        def safe_float(idx, default=None):
            try:
                return float(fields[idx]) if fields[idx] else default
            except (ValueError, IndexError):
                return default

        out.update({
            'name': fields[1],
            'current': safe_float(3),
            'prev_close': safe_float(4),
            'open': safe_float(5),
            'high': safe_float(33),
            'low': safe_float(34),
            'change': safe_float(31),
            'change_pct': safe_float(32),
            'volume': safe_float(6),
            'amount': safe_float(37),
            'data_ok': True,
        })
        return out
    except Exception as e:
        out['error'] = str(e)
        return out


# === 隔夜美股（情绪参考）===

US_PROXIES = {
    'SPY': 'SPDR S&P 500 ETF',
    'QQQ': 'Invesco QQQ Trust',
    '^VIX': 'CBOE Volatility Index',
    '^TNX': '10-Year Treasury Yield',
    'DX-Y.NYB': 'US Dollar Index',
}


def fetch_us_proxy_quote(symbol: str) -> dict:
    """通过 yfinance 拉取美股情绪指标"""
    out = {'symbol': symbol, 'data_ok': False}
    try:
        # 强制直接导入（绕过可能被代理影响的环境）
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='5d')
        if hist is None or hist.empty or len(hist) < 2:
            return out
        cur = float(hist['Close'].iloc[-1])
        prev = float(hist['Close'].iloc[-2])
        change_pct = (cur - prev) / prev * 100
        out['current'] = cur
        out['change_pct'] = change_pct
        out['data_ok'] = True
    except Exception as e:
        out['error'] = str(e)
    return out


# === 北向资金（最新可用） ===

def fetch_northbound_proxy() -> dict:
    """
    北向资金代理数据。
    通过沪深港通成分股成交活跃度间接观察（简化版）。
    实际生产建议接入专业数据源（需 token）。
    """
    return {
        'data_ok': False,
        'note': '北向资金数据需专业接口（万得/聚宽/Tushare）',
        'placeholder': '上海北向净买/深圳北向净买',
    }


# === 资金面：成交量 ===

def fetch_volume_data() -> dict:
    """成交量相关数据（沪深两市）"""
    return {
        'sh_total': None,
        'sz_total': None,
        'data_ok': False,
        'note': '成交额数据通过东方财富接口获取，当前未启用',
    }


# === 生成晨报 ===

def generate_china_brief(
    watchlist: list,
    output_dir: str = None,
    include_us: bool = True,
) -> str:
    """生成 A 股 Morning Brief"""
    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')
    time_str = today.strftime('%Y-%m-%d %H:%M:%S')

    if output_dir is None:
        output_dir = _DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    lines = []
    lines.append(f'# A 股 Morning Brief · {date_str}')
    lines.append('')
    lines.append(f'> Atlas 中国市场每日情报简报（China Equity v1.1）')
    lines.append(f'> **生成时间**：{time_str}')
    lines.append(f'> **生成工具**：Atlas China Morning Brief')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 一、隔夜全球 ===
    if include_us:
        lines.append('## 一、隔夜全球（美股情绪参考）')
        lines.append('')
        lines.append('| 标的 | 价格 | 涨跌 | 解读 |')
        lines.append('|------|------|------|------|')
        print('>>> 拉取美股情绪指标...')
        for symbol, name in US_PROXIES.items():
            q = fetch_us_proxy_quote(symbol)
            if q['data_ok']:
                chg = q['change_pct']
                # A 股颜色规则：红涨绿跌（注意美股仍用绿涨红跌，仅作为对比）
                marker = '🔴' if chg > 0.5 else ('🟢' if chg < -0.5 else '⚪')
                if symbol == '^VIX':
                    interp = '低位（风险偏好高）' if q['current'] < 15 else ('中位' if q['current'] < 25 else '高位（避险）')
                elif symbol == '^TNX':
                    interp = f'{q["current"]:.2f}%'
                else:
                    interp = '走强' if chg > 0.5 else ('走弱' if chg < -0.5 else '平稳')
                lines.append(f'| {name} ({symbol}) | {q["current"]:.2f} | {marker} {chg:+.2f}% | {interp} |')
            else:
                lines.append(f'| {name} ({symbol}) | ❌ | — | 数据缺失 |')
        lines.append('')
        lines.append('**对 A 股影响**：')
        lines.append('')
        lines.append('- 美股走强 → A 股开盘情绪偏暖（尤其科技/出口股）')
        lines.append('- VIX 走高 → A 股可能低开（避险情绪）')
        lines.append('- 美元走强 → 北向资金可能流出')
        lines.append('')
        lines.append('---')
        lines.append('')

    # === 二、A 股市场状态 ===
    lines.append('## 二、A 股市场状态')
    lines.append('')
    print('>>> 拉取 A 股主要指数...')
    lines.append('**主要指数**：')
    lines.append('')
    lines.append('| 指数 | 代码 | 收盘 | 涨跌 |')
    lines.append('|------|------|------|------|')
    for symbol, name in CHINA_INDICES.items():
        q = fetch_index_quote(symbol)
        if q['data_ok']:
            chg = q.get('change_pct', 0)
            # A 股颜色规则：红涨绿跌
            marker = '🔴' if chg > 0.5 else ('🟢' if chg < -0.5 else '⚪')
            lines.append(f'| {name} | {symbol} | {q["current"]:.2f} | {marker} {chg:+.2f}% |')
        else:
            lines.append(f'| {name} | {symbol} | ❌ | — |')
    lines.append('')

    # 市场状态判定（简化版）
    # 取沪深 300 涨跌幅作为整体市场表现
    # A 股颜色规则：红涨绿跌
    lines.append('**市场状态判定**：')
    lines.append('')
    lines.append('- 🔴 **强势**：沪深 300 涨 > 1%（红涨）')
    lines.append('- ⚪ **震荡**：-1% < 沪深 300 ≤ 1%')
    lines.append('- 🟢 **弱势**：沪深 300 跌 > 1%（绿跌）')
    lines.append('')
    lines.append('**对仓位的影响**：')
    lines.append('')
    lines.append('- 强势 → 可适度加仓（仍保持 20% 现金）')
    lines.append('- 震荡 → 选股优于择时')
    lines.append('- 弱势 → 降低仓位，等待止跌信号')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 三、热点板块（资金流向）===
    lines.append('## 三、热点板块（资金流向）')
    lines.append('')
    lines.append('> **数据说明**：板块资金流向需接入专业接口（东方财富/同花顺）。')
    lines.append('> 当前为 manual 模式（用户提供）。')
    lines.append('')
    lines.append('**如何观察**：')
    lines.append('')
    lines.append('1. **领涨板块**：今日涨幅 Top 3 板块')
    lines.append('2. **领跌板块**：今日跌幅 Top 3 板块')
    lines.append('3. **资金净流入**：北向资金 / 主力资金 / 散户资金')
    lines.append('4. **板块轮动**：强势板块是否切换')
    lines.append('')
    lines.append('**当前关注板块**（来自 watchlist）：')
    lines.append('')
    lines.append('- 白酒（贵州茅台 / 五粮液 / 泸州老窖）')
    lines.append('- 新能源（宁德时代 / 隆基绿能 / 立新能源）')
    lines.append('- 有色金属（紫金矿业 / 江西铜业）')
    lines.append('- 半导体（中科曙光 / 北方华创 / 韦尔股份）')
    lines.append('- 金融（中国平安 / 招商银行 / 中信证券）')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 四、资金面 ===
    lines.append('## 四、资金面')
    lines.append('')
    nb = fetch_northbound_proxy()
    lines.append('**北向资金**：')
    lines.append('')
    if not nb['data_ok']:
        lines.append(f'- ⚠️ {nb["note"]}')
        lines.append('- 占位字段：上海北向净买 / 深圳北向净买（待接入专业数据源）')
    lines.append('')
    lines.append('**融资融券**（待接入）：')
    lines.append('')
    lines.append('- 融资余额变化（增加 = 看多 / 减少 = 看空）')
    lines.append('- 融券余额变化')
    lines.append('')
    lines.append('**两市成交额**（待接入）：')
    lines.append('')
    lines.append('- 沪市成交额 / 深市成交额')
    lines.append('- 成交额萎缩 = 观望情绪')
    lines.append('- 成交额放量 = 趋势强化')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 五、自选股（核心 + 成长）===
    lines.append('## 五、自选股（Watchlist）')
    lines.append('')
    lines.append('> A 股 watchlist 默认包含核心仓 + 成长仓。')
    lines.append('')
    print('>>> 拉取自选股实时行情...')
    quotes = fetch_realtime_quotes(watchlist)
    lines.append('| 股票 | 代码 | 现价 | 日涨跌 | 52周位置 | 市值(亿) | PE | 信号 |')
    lines.append('|------|------|------|--------|-----------|----------|----|------|')

    for sym in watchlist:
        q = quotes.get(sym)
        if q is None:
            lines.append(f'| ❌ | {sym} | — | — | — | — | — | 数据缺失 |')
            continue

        # 计算信号（简化）
        chg = q.get('change_pct', 0)
        if abs(chg) >= 5:
            signal = '⚠️ 大幅波动'
        elif abs(chg) >= 3:
            signal = '⚡ 中幅波动'
        elif abs(chg) < 1:
            signal = '— 平稳'
        else:
            signal = '—'

        chg_str = f'{chg:+.2f}%' if chg is not None else 'N/A'
        # A 股颜色规则：红涨绿跌
        marker = '🔴' if chg > 0 else ('🟢' if chg < 0 else '⚪')

        mcap = q.get('market_cap_yi') or 0
        pe = q.get('pe') or 0
        lines.append(
            f'| {q.get("name", "—")} | {sym} | ¥{q.get("price", 0):.2f} | {marker} {chg_str} | N/A | {mcap:.0f} | {pe:.1f} | {signal} |'
        )

    lines.append('')
    lines.append('---')
    lines.append('')

    # === 六、风险概览 ===
    lines.append('## 六、风险概览')
    lines.append('')
    lines.append('**仓位规则**（v1.1 三层模型）：')
    lines.append('')
    lines.append('| 层级 | 单股上限 | 行业上限 |')
    lines.append('|------|---------|---------|')
    lines.append('| 核心仓 | ≤15% | ≤40% |')
    lines.append('| 成长仓 | ≤8% | ≤30% |')
    lines.append('| 主题仓 | ≤3% | 总仓≤10% |')
    lines.append('| 现金 | ≥20% | — |')
    lines.append('')
    lines.append('**当前风险**：')
    lines.append('')
    lines.append('- 🔴 当前持仓违反 v1.1 仓位规则（详见 `risk_budget.md`）')
    lines.append('- ⚠️ 用户待决策：3 只持仓风险等级与仓位调整')
    lines.append('')
    lines.append('**风险事件触发**：')
    lines.append('')
    lines.append('- 单日亏损 -3% → 暂停 review')
    lines.append('- 单股 > 上限 → 立即 rebalance')
    lines.append('- 行业 > 40% → 立即 rebalance')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 七、今日观察 ===
    lines.append('## 七、今日观察')
    lines.append('')
    lines.append('**重点关注**：')
    lines.append('')
    lines.append('1. **隔夜美股情绪**：关注 NVDA/TSLA/AAPL 走势对今日 A 股科技股影响')
    lines.append('2. **A 股开盘表现**：关注主要指数开盘 30 分钟表现')
    lines.append('3. **板块轮动**：关注是否有新热点取代旧热点')
    lines.append('4. **资金动向**：关注北向资金流向（待接入专业数据源）')
    lines.append('5. **自选股表现**：监控 watchlist 中股票的异常波动')
    lines.append('')
    lines.append('**操作纪律**：')
    lines.append('')
    lines.append('- 不追涨（建仓前已涨 >5% 不再追）')
    lines.append('- 不杀跌（基本面不变不轻易清仓）')
    lines.append('- 不因新闻冲动交易')
    lines.append('- 价格不是价值')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 附录 ===
    lines.append('## 附录：数据源说明')
    lines.append('')
    lines.append('| 数据 | 来源 | URL |')
    lines.append('|------|------|-----|')
    lines.append('| A 股实时行情 | 腾讯 qt.gtimg.cn | https://qt.gtimg.cn/q={sh|sz}{code} |')
    lines.append('| A 股 K 线 | 腾讯 web.ifzq.gtimg.cn | http://web.ifzq.gtimg.cn/... |')
    lines.append('| A 股全量数据 | AkShare | pip install akshare（备用） |')
    lines.append('| 美股情绪 | yfinance | pip install yfinance |')
    lines.append('')
    lines.append('**限制**：')
    lines.append('')
    lines.append('- 北向资金 / 融资融券 / 板块资金流向需接入专业接口（暂未启用）')
    lines.append('- Tushare 数据源待用户配置（当前仅用免费接口）')
    lines.append('- AkShare 在 fake-IP 网络下不稳定，使用腾讯接口 fallback')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append(f'> **免责声明**：本报告为 Atlas 投资研究工具自动生成。')
    lines.append('> 仅供研究参考，不构成投资建议。')
    lines.append('> 投资决策权归用户所有。')

    # 保存（使用中文文件名：A股早盘简报_日期）
    filename = f'A股早盘简报_{date_str}.md'
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Atlas A 股 Morning Brief 生成器（China Equity v1.1）',
        epilog='示例: python3 china_morning_brief.py 600519.SH 300750.SZ',
    )
    parser.add_argument(
        'symbols',
        nargs='*',
        help='A 股代码（默认 watchlist）',
    )
    parser.add_argument(
        '--no-us',
        action='store_true',
        help='不拉取美股情绪（节省时间）',
    )
    parser.add_argument(
        '--output-dir',
        help='输出目录',
    )

    args = parser.parse_args()
    watchlist = args.symbols if args.symbols else DEFAULT_CHINA_WATCHLIST

    print(f'=== Atlas A 股 Morning Brief ===')
    print(f'Watchlist: {watchlist}')
    print()

    filepath = generate_china_brief(
        watchlist,
        output_dir=args.output_dir,
        include_us=not args.no_us,
    )

    print()
    print(f'✅ 已生成: {filepath}')


if __name__ == '__main__':
    main()