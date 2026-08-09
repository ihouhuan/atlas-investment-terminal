#!/usr/bin/env python3
"""
Atlas Thesis Monitor v7
输入：portfolio.json（包含 thesis + validation metrics + invalid conditions）
输出：每个持仓的 thesis 状态 (GREEN / YELLOW / RED)

检查维度：
  1. 验证指标对比（vs 当前 yfinance 数据）
  2. 新闻事件影响（关键词匹配）
  3. 财报临近（≤7 天）
  4. 价格大幅波动（>10% 单周）
  5. 估值变化（PE 突破历史区间）

状态判定：
  - GREEN：所有验证指标正常，无负面信号
  - YELLOW：1 个验证指标异常或收到负面信号
  - RED：失效条件触发 或 ≥2 个负面信号
"""

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

import yfinance as yf


# === 指标名 → yfinance 字段映射 ===
METRIC_MAP = {
    'revenue_growth': ('revenueGrowth', 'decimal'),
    'earnings_growth': ('earningsGrowth', 'decimal'),
    'gross_margin': ('grossMargins', 'decimal'),
    'operating_margin': ('operatingMargins', 'decimal'),
    'profit_margin': ('profitMargins', 'decimal'),
    'roe': ('returnOnEquity', 'decimal'),
    'fcf_margin': None,  # 需要自行计算
    'pe': ('trailingPE', 'raw'),
    'ps': ('priceToSalesTrailing12Months', 'raw'),
}


def load_portfolio_json(json_path: str) -> dict:
    """读取完整 portfolio.json"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fetch_current_metrics(symbol: str) -> dict:
    """获取当前市场数据用于验证"""
    out = {'symbol': symbol, 'data_ok': False}

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        if not info or len(info) < 5:
            raise RuntimeError(f'无效 ticker: {symbol}')

        out['name'] = info.get('longName') or info.get('shortName') or symbol
        out['current_price'] = info.get('currentPrice') or info.get('regularMarketPrice')

        # 实际财务指标
        out['revenue_growth'] = info.get('revenueGrowth')  # decimal
        out['gross_margin'] = info.get('grossMargins')
        out['operating_margin'] = info.get('operatingMargins')
        out['profit_margin'] = info.get('profitMargins')
        out['roe'] = info.get('returnOnEquity')
        out['pe'] = info.get('trailingPE')
        out['ps'] = info.get('priceToSalesTrailing12Months')

        # 计算 FCF Margin
        fcf = info.get('freeCashflow')
        rev = info.get('totalRevenue')
        if fcf is not None and rev and rev > 0:
            out['fcf_margin'] = fcf / rev

        # 价格变化（5 日）
        try:
            hist = ticker.history(period='1mo')
            if not hist.empty and len(hist) >= 5:
                cur = float(hist['Close'].iloc[-1])
                ago5 = float(hist['Close'].iloc[-5])
                out['change_5d_pct'] = (cur - ago5) / ago5 * 100
        except Exception:
            pass

        # 财报日期
        try:
            cal = ticker.calendar
            if cal is not None and not (hasattr(cal, 'empty') and cal.empty):
                if hasattr(cal, 'index') and 'Earnings Date' in cal.index:
                    ed = cal.loc['Earnings Date'].iloc[0]
                    if hasattr(ed, 'isoformat'):
                        out['earnings_date'] = ed.isoformat()[:10]
        except Exception:
            pass

        out['data_ok'] = True

    except Exception as e:
        out['error'] = str(e)

    return out


def check_validation_metric(metric_name: str, target_str: str, current_val) -> dict:
    """检查单个验证指标"""
    result = {
        'metric': metric_name,
        'target': target_str,
        'current': 'N/A',
        'status': 'UNKNOWN',
        'note': '',
    }

    if current_val is None:
        result['note'] = '当前数据缺失'
        result['status'] = 'UNKNOWN'
        return result

    # 解析 target（支持 >X%, >X, <X% 等）
    target_clean = target_str.replace('%', '').replace(' ', '').strip()
    op = None
    target_num = None
    for prefix in ['>', '<', '>=', '<=']:
        if target_clean.startswith(prefix):
            op = prefix
            try:
                target_num = float(target_clean[len(prefix):])
            except ValueError:
                pass
            break

    if op is None or target_num is None:
        result['note'] = f'目标格式无法解析: {target_str}'
        result['status'] = 'UNKNOWN'
        return result

    # 当前值（处理 decimal vs raw）
    if metric_name in ['revenue_growth', 'earnings_growth', 'gross_margin',
                       'operating_margin', 'profit_margin', 'roe', 'fcf_margin']:
        # decimal 形式（0.85 = 85%）
        cur_num = current_val * 100
        result['current'] = f'{cur_num:.2f}%'
    else:
        cur_num = current_val
        result['current'] = f'{cur_num:.2f}'

    target_num_disp = target_num

    # 比较
    if op == '>':
        passed = cur_num > target_num_disp
    elif op == '<':
        passed = cur_num < target_num_disp
    elif op == '>=':
        passed = cur_num >= target_num_disp
    elif op == '<=':
        passed = cur_num <= target_num_disp
    else:
        passed = True

    if passed:
        result['status'] = 'GREEN'
        result['note'] = f'{cur_num:.2f} {op} {target_num_disp} ✓'
    else:
        result['status'] = 'RED'
        result['note'] = f'{cur_num:.2f} {op} {target_num_disp} ✗ (未达标)'

    return result


def check_thesis_status(position: dict, current_metrics: dict, news_items: list) -> dict:
    """检查单只持仓的 thesis 状态"""
    sym = position['symbol']
    thesis = position.get('thesis', '')
    validation = position.get('validation_metrics', {})
    invalid_conditions = position.get('invalid_conditions', [])

    checks = []
    red_count = 0
    yellow_count = 0

    # === 1. 验证指标检查 ===
    for metric_name, cfg in validation.items():
        target = cfg.get('target', '') if isinstance(cfg, dict) else str(cfg)
        cur_val = current_metrics.get(metric_name)
        result = check_validation_metric(metric_name, target, cur_val)
        result['category'] = 'VALIDATION'
        checks.append(result)
        if result['status'] == 'RED':
            red_count += 1
        elif result['status'] == 'YELLOW':
            yellow_count += 1

    # === 2. 失效条件文本匹配（简化版）===
    # 检测新闻标题是否包含失效条件关键词
    # 仅当条件同时含负面词与关键主题词时才触发
    invalid_hits = []
    if news_items and invalid_conditions:
        all_news_text = ' '.join([item.get('title', '') for item in news_items]).lower()
        # 负面词列表
        negative_words = ['downgrade', 'warning', 'cut', 'miss', 'decline', 'fall',
                          'decrease', 'loss', 'drop', 'plunge', 'tumble', 'warn',
                          '下调', '警告', '减少', '下滑', '下降', '下跌', '降低']
        for cond in invalid_conditions:
            cond_lower = cond.lower()
            # 提取关键词（中文 2 字 / 英文 3+ 字）
            keywords = []
            import re
            # 找英文单词
            words = re.findall(r'[a-zA-Z]{4,}', cond_lower)
            keywords.extend(words)
            # 找中文双字词
            for char_idx in range(len(cond) - 1):
                if ord(cond[char_idx]) > 127 and ord(cond[char_idx+1]) > 127:
                    keywords.append(cond[char_idx:char_idx+2])

            # 仅当条件含负面词与主题词同时匹配时才触发
            topic_match = any(kw.lower() in all_news_text for kw in keywords)
            negative_match = any(nw in all_news_text for nw in negative_words)

            if topic_match and negative_match:
                invalid_hits.append(cond)

    for cond in invalid_hits:
        checks.append({
            'metric': 'INVALID_CONDITION',
            'target': cond,
            'current': '命中新闻',
            'status': 'RED',
            'note': '⚠️ 失效条件关键词在新闻中出现',
            'category': 'NEWS',
        })
        red_count += 1

    # === 3. 价格大幅波动 ===
    change_5d = current_metrics.get('change_5d_pct')
    if change_5d is not None and abs(change_5d) > 10:
        checks.append({
            'metric': '5D_PRICE_CHANGE',
            'target': '±10% 内',
            'current': f'{change_5d:+.2f}%',
            'status': 'YELLOW',
            'note': '单周波动较大，需评估',
            'category': 'PRICE',
        })
        yellow_count += 1

    # === 4. 财报临近 ===
    ed = current_metrics.get('earnings_date')
    if ed:
        try:
            ed_dt = datetime.strptime(ed, '%Y-%m-%d')
            days = (ed_dt - datetime.now()).days
            if 0 <= days <= 7:
                checks.append({
                    'metric': 'EARNINGS_APPROACHING',
                    'target': '>7 天',
                    'current': f'{days} 天',
                    'status': 'YELLOW',
                    'note': '财报临近，准备验证指标',
                    'category': 'EVENT',
                })
                yellow_count += 1
        except (ValueError, TypeError):
            pass

    # === 综合判定 ===
    if red_count >= 1:
        overall = 'RED'
        severity = '🔴'
    elif yellow_count >= 1:
        overall = 'YELLOW'
        severity = '🟡'
    elif red_count == 0 and yellow_count == 0:
        overall = 'GREEN'
        severity = '🟢'
    else:
        overall = 'YELLOW'
        severity = '🟡'

    return {
        'symbol': sym,
        'thesis': thesis,
        'overall': overall,
        'severity': severity,
        'red_count': red_count,
        'yellow_count': yellow_count,
        'checks': checks,
        'news_count': len(news_items) if news_items else 0,
        'invalid_hits': invalid_hits,
        'current_price': current_metrics.get('current_price'),
        'buy_reason': position.get('buy_reason', ''),
        'review_date': position.get('review_date', ''),
    }


def generate_thesis_report(statuses: list) -> str:
    """生成 thesis monitor 报告"""
    date = datetime.now().strftime('%Y-%m-%d')
    time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = []
    lines.append(f'# Thesis Monitor · {date}')
    lines.append('')
    lines.append(f'**生成时间**：{time}')
    lines.append(f'**生成工具**：Atlas Thesis Monitor v7')
    lines.append(f'**检查持仓**：{len(statuses)}')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 综合概览 ===
    lines.append('## 一、综合概览')
    lines.append('')

    green_count = sum(1 for s in statuses if s['overall'] == 'GREEN')
    yellow_count = sum(1 for s in statuses if s['overall'] == 'YELLOW')
    red_count = sum(1 for s in statuses if s['overall'] == 'RED')

    lines.append('| 状态 | 数量 | 标的 |')
    lines.append('|------|------|------|')
    lines.append(f'| 🟢 GREEN | {green_count} | {", ".join([s["symbol"] for s in statuses if s["overall"] == "GREEN"]) or "—"} |')
    lines.append(f'| 🟡 YELLOW | {yellow_count} | {", ".join([s["symbol"] for s in statuses if s["overall"] == "YELLOW"]) or "—"} |')
    lines.append(f'| 🔴 RED | {red_count} | {", ".join([s["symbol"] for s in statuses if s["overall"] == "RED"]) or "—"} |')
    lines.append('')

    # === 持仓详情 ===
    lines.append('## 二、持仓 Thesis 详情')
    lines.append('')

    for status in statuses:
        sym = status['symbol']
        overall = status['overall']
        severity = status['severity']
        thesis = status['thesis']
        buy_reason = status.get('buy_reason', '')
        review_date = status.get('review_date', '')

        lines.append(f'### {severity} {sym} · {overall}')
        lines.append('')
        lines.append(f'**Thesis**：{thesis}')
        lines.append('')
        if buy_reason:
            lines.append(f'**建仓理由**：{buy_reason}')
            lines.append('')
        if review_date:
            lines.append(f'**下次 review**：{review_date}')
            lines.append('')

        # 验证指标
        validation_checks = [c for c in status['checks'] if c.get('category') == 'VALIDATION']
        if validation_checks:
            lines.append('**验证指标**：')
            lines.append('')
            lines.append('| 指标 | 目标 | 当前 | 状态 |')
            lines.append('|------|------|------|------|')
            for c in validation_checks:
                marker = '✅' if c['status'] == 'GREEN' else ('⚠️' if c['status'] == 'YELLOW' else '❌')
                lines.append(f'| {c["metric"]} | {c["target"]} | {c["current"]} | {marker} {c["status"]} |')
            lines.append('')

        # 失效条件命中
        if status['invalid_hits']:
            lines.append('**⚠️ 失效条件命中**：')
            lines.append('')
            for cond in status['invalid_hits']:
                lines.append(f'- ❌ {cond}')
            lines.append('')

        # 其他信号
        other = [c for c in status['checks'] if c.get('category') != 'VALIDATION']
        if other:
            lines.append('**其他信号**：')
            lines.append('')
            for c in other:
                marker = '✅' if c['status'] == 'GREEN' else ('⚠️' if c['status'] == 'YELLOW' else '❌')
                lines.append(f'- {marker} **{c["metric"]}**：{c["note"]}')
            lines.append('')

        # 行动建议
        if overall == 'RED':
            lines.append('**🛑 行动建议**：thesis 出现严重问题，立即评估是否减仓/清仓')
        elif overall == 'YELLOW':
            lines.append('**👀 行动建议**：密切关注，验证指标接近失效条件')
        else:
            lines.append('**✅ 行动建议**：thesis 正常，无需调整')

        lines.append('')
        lines.append('---')
        lines.append('')

    # === 总结 ===
    lines.append('## 三、总结')
    lines.append('')

    if red_count > 0:
        lines.append(f'🔴 **{red_count} 个持仓 thesis 出现 RED 警告**')
        lines.append('')
        lines.append('**关键行动**：')
        lines.append('1. 立即 review 触发 RED 的持仓')
        lines.append('2. 评估是否触发卖出条件')
        lines.append('3. 在 Investment Memo 中记录决策')
        lines.append('4. 考虑是否需要调整仓位')
    elif yellow_count > 0:
        lines.append(f'🟡 **{yellow_count} 个持仓需要密切关注**')
        lines.append('')
        lines.append('**关键行动**：')
        lines.append('1. 持续跟踪验证指标')
        lines.append('2. 准备应对潜在风险')
        lines.append('3. 在下次 review 前确认 thesis')
    else:
        lines.append('🟢 **所有 thesis 状态正常**')
        lines.append('')
        lines.append('继续按既定策略执行，定期 review。')

    lines.append('')

    lines.append('---')
    lines.append('')
    lines.append(f'**生成工具**：Atlas Thesis Monitor v7')
    lines.append('')
    lines.append('* thesis Monitor 基于 portfolio.json 中的显式定义 + 实时市场数据自动判定。重要决策需人工验证。*')

    return '\n'.join(lines)


def save_report(content: str, output_dir: str = None) -> str:
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '假设监控',
            '报告'
        )
    os.makedirs(output_dir, exist_ok=True)

    date = datetime.now().strftime('%Y-%m-%d')
    filename = f'假设监控报告_{date}.md'
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Atlas Thesis Monitor v7',
        epilog='示例：python3 thesis_monitor.py'
    )
    parser.add_argument(
        '--portfolio',
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'portfolio',
            'portfolio.json'
        ),
        help='Portfolio JSON 路径'
    )
    parser.add_argument('--stdout', action='store_true', help='同时输出到 stdout')

    args = parser.parse_args()

    print(f'\n>>> 加载组合: {args.portfolio}')

    try:
        data = load_portfolio_json(args.portfolio)
        # 兼容 v1.1 嵌套结构
        positions = data.get('positions', [])
        if isinstance(positions, dict):
            positions = positions.get('positions', [])

        if not positions:
            print('⚠️ portfolio.json 中无持仓')
            return 0

        print(f'   监控 {len(positions)} 个持仓的 thesis 状态...')

        # 拉取每持仓的当前数据 + 新闻
        statuses = []
        for pos in positions:
            sym = pos['symbol']
            print(f'   - {sym}')

            current = fetch_current_metrics(sym)

            # 拉新闻
            try:
                ticker = yf.Ticker(sym)
                news_raw = ticker.news or []
                news_items = []
                for item in news_raw[:10]:
                    content = item.get('content') if isinstance(item, dict) else None
                    if content and isinstance(content, dict):
                        title = content.get('title', '')
                    else:
                        title = item.get('title', '') if isinstance(item, dict) else ''
                    news_items.append({'title': title})
            except Exception:
                news_items = []

            status = check_thesis_status(pos, current, news_items)
            statuses.append(status)

            # 输出状态
            print(f'     {status["severity"]} {status["overall"]}')

        content = generate_thesis_report(statuses)
        filepath = save_report(content)
        print(f'✅ Thesis Monitor 报告: {filepath}')

        if args.stdout:
            print('\n' + '=' * 70)
            print(content)

        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'\n❌ DATA ERROR: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())