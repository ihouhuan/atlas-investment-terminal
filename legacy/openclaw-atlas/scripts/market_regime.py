#!/usr/bin/env python3
"""
Atlas Market Regime Detector v6
输入：无（自动从市场数据获取）
输出：当前市场状态（Risk-On / Neutral / Risk-Off）

参考指标：
  - VIX（^VIX）
  - SPY vs 200 日均线
  - 10Y - 2Y 收益率利差
  - 美元指数 (DX-Y.NYB)
  - 市场宽度（SPY 成分股简化版 → 用 HYG/LYD 比值近似）

存储：
  - investment/models/market_regime_report.md
"""

import os
import sys
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

import yfinance as yf


def fetch_market_indicators() -> dict:
    """获取市场状态关键指标"""
    out = {
        'fetch_date': datetime.now().strftime('%Y-%m-%d'),
        'fetch_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'indicators': {},
        'signals': {},
        'errors': [],
    }

    # 1. VIX
    try:
        vix = yf.Ticker('^VIX')
        vix_hist = vix.history(period='5d')
        if not vix_hist.empty:
            vix_current = float(vix_hist['Close'].iloc[-1])
            out['indicators']['VIX'] = vix_current
            if vix_current < 15:
                out['signals']['VIX'] = ('Risk-On', f'VIX={vix_current:.2f} 低位')
            elif vix_current < 25:
                out['signals']['VIX'] = ('Neutral', f'VIX={vix_current:.2f} 中位')
            else:
                out['signals']['VIX'] = ('Risk-Off', f'VIX={vix_current:.2f} 高位')
        else:
            out['errors'].append('VIX 无历史数据')
    except Exception as e:
        out['errors'].append(f'VIX: {e}')

    # 2. SPY vs 200 日均线
    try:
        spy = yf.Ticker('SPY')
        spy_hist = spy.history(period='1y')
        if not spy_hist.empty and len(spy_hist) >= 200:
            spy_current = float(spy_hist['Close'].iloc[-1])
            spy_ma200 = float(spy_hist['Close'].tail(200).mean())
            spy_pct_from_ma = (spy_current - spy_ma200) / spy_ma200 * 100
            out['indicators']['SPY_vs_MA200_pct'] = spy_pct_from_ma
            out['indicators']['SPY_current'] = spy_current

            if spy_pct_from_ma > 2:
                out['signals']['SPY_vs_MA200'] = ('Risk-On', f'SPY 高于 MA200 {spy_pct_from_ma:.1f}%')
            elif spy_pct_from_ma > -5:
                out['signals']['SPY_vs_MA200'] = ('Neutral', f'SPY 偏离 MA200 {spy_pct_from_ma:.1f}%')
            else:
                out['signals']['SPY_vs_MA200'] = ('Risk-Off', f'SPY 低于 MA200 {spy_pct_from_ma:.1f}%')
        else:
            out['errors'].append('SPY 历史数据不足')
    except Exception as e:
        out['errors'].append(f'SPY: {e}')

    # 3. 10Y-2Y 收益率利差（用 ^TNX 和 ^FVX 近似）
    try:
        tnx = yf.Ticker('^TNX')  # 10 年期
        fvx = yf.Ticker('^FVX')  # 5 年期（作为 2Y 的替代）
        tnx_hist = tnx.history(period='5d')
        fvx_hist = fvx.history(period='5d')

        if not tnx_hist.empty and not fvx_hist.empty:
            tnx_yield = float(tnx_hist['Close'].iloc[-1])
            fvx_yield = float(fvx_hist['Close'].iloc[-1])
            spread = tnx_yield - fvx_yield

            out['indicators']['10Y_yield'] = tnx_yield
            out['indicators']['5Y_yield'] = fvx_yield
            out['indicators']['yield_spread_10Y_5Y'] = spread

            if spread > 0.5:
                out['signals']['yield_curve'] = ('Risk-On', f'利差 {spread:.2f}% 陡峭')
            elif spread > 0:
                out['signals']['yield_curve'] = ('Neutral', f'利差 {spread:.2f}% 正常')
            else:
                out['signals']['yield_curve'] = ('Risk-Off', f'利差 {spread:.2f}% 倒挂')
    except Exception as e:
        out['errors'].append(f'收益率曲线: {e}')

    # 4. 美元指数
    try:
        dxy = yf.Ticker('DX-Y.NYB')
        dxy_hist = dxy.history(period='3mo')
        if not dxy_hist.empty and len(dxy_hist) >= 5:
            dxy_current = float(dxy_hist['Close'].iloc[-1])
            dxy_ma20 = float(dxy_hist['Close'].tail(20).mean()) if len(dxy_hist) >= 20 else dxy_current
            dxy_pct = (dxy_current - dxy_ma20) / dxy_ma20 * 100

            out['indicators']['DXY_current'] = dxy_current
            out['indicators']['DXY_vs_MA20_pct'] = dxy_pct

            if dxy_pct < -1:
                out['signals']['DXY'] = ('Risk-On', f'DXY 走弱 {dxy_pct:.1f}%')
            elif dxy_pct > 2:
                out['signals']['DXY'] = ('Risk-Off', f'DXY 强势 {dxy_pct:.1f}%')
            else:
                out['signals']['DXY'] = ('Neutral', f'DXY 稳定 {dxy_pct:.1f}%')
    except Exception as e:
        out['errors'].append(f'DXY: {e}')

    # 5. 市场宽度（用 HYG/LQD 比值作为信用利差代理）
    try:
        hyg = yf.Ticker('HYG')  # 高收益债
        lqd = yf.Ticker('LQD')  # 投资级债
        hyg_hist = hyg.history(period='3mo')
        lqd_hist = lqd.history(period='3mo')

        if not hyg_hist.empty and not lqd_hist.empty:
            hyg_close = float(hyg_hist['Close'].iloc[-1])
            lqd_close = float(lqd_hist['Close'].iloc[-1])
            # HYG/LQD 比值下降 → 信用利差扩大 → Risk-Off
            current_ratio = hyg_close / lqd_close
            avg_ratio = float((hyg_hist['Close'] / lqd_hist['Close']).tail(60).mean())
            ratio_pct = (current_ratio - avg_ratio) / avg_ratio * 100

            out['indicators']['HYG_LQD_ratio'] = current_ratio
            out['indicators']['HYG_LQD_ratio_pct'] = ratio_pct

            if ratio_pct < -2:
                out['signals']['credit_spread'] = ('Risk-Off', f'HYG/LQD 比值下降 {ratio_pct:.1f}%')
            elif ratio_pct > 2:
                out['signals']['credit_spread'] = ('Risk-On', f'HYG/LQD 比值上升 {ratio_pct:.1f}%')
            else:
                out['signals']['credit_spread'] = ('Neutral', f'HYG/LQD 比值稳定 {ratio_pct:.1f}%')
    except Exception as e:
        out['errors'].append(f'HYG/LQD: {e}')

    return out


def determine_regime(out: dict) -> str:
    """综合判断当前市场状态"""
    if not out['signals']:
        return 'UNKNOWN (DATA INSUFFICIENT)'

    # 投票机制
    risk_on_count = sum(1 for s, _ in out['signals'].values() if s == 'Risk-On')
    neutral_count = sum(1 for s, _ in out['signals'].values() if s == 'Neutral')
    risk_off_count = sum(1 for s, _ in out['signals'].values() if s == 'Risk-Off')

    total = len(out['signals'])
    risk_on_pct = risk_on_count / total if total else 0
    risk_off_pct = risk_off_count / total if total else 0

    # 决策逻辑
    if risk_off_pct >= 0.5:
        return 'Risk-Off 🔴'
    elif risk_on_pct >= 0.5 and risk_off_pct == 0:
        return 'Risk-On 🟢'
    elif risk_off_count >= 2:
        return 'Risk-Off 🔴'
    elif risk_on_count >= 3 and risk_off_count == 0:
        return 'Risk-On 🟢'
    else:
        return 'Neutral 🟡'


def generate_report(out: dict, regime: str) -> str:
    """生成市场状态报告"""
    lines = []
    lines.append(f'# Market Regime Report · {out["fetch_date"]}')
    lines.append('')
    lines.append(f'**生成时间**：{out["fetch_time"]}')
    lines.append(f'**当前状态**：{regime}')
    lines.append(f'**生成工具**：Atlas Market Regime Detector v6')
    lines.append('')
    lines.append('---')
    lines.append('')

    # === 关键指标 ===
    lines.append('## 一、关键指标')
    lines.append('')
    lines.append('| 指标 | 值 | 区间 |')
    lines.append('|------|------|------|')

    vix = out['indicators'].get('VIX')
    if vix is not None:
        lines.append(f'| VIX | {vix:.2f} | {"< 15 低位" if vix < 15 else ("15-25 中位" if vix < 25 else "> 25 高位")} |')

    spy_pct = out['indicators'].get('SPY_vs_MA200_pct')
    if spy_pct is not None:
        spy_pos = f'{spy_pct:+.1f}%'
        lines.append(f'| SPY vs 200 日均线 | {spy_pos} | {"上方" if spy_pct > 0 else "下方"} |')

    spread = out['indicators'].get('yield_spread_10Y_5Y')
    if spread is not None:
        lines.append(f'| 10Y-5Y 收益率利差 | {spread:+.2f}% | {"陡峭" if spread > 0.5 else ("正常" if spread > 0 else "倒挂")} |')

    dxy_pct = out['indicators'].get('DXY_vs_MA20_pct')
    if dxy_pct is not None:
        lines.append(f'| 美元指数 (DXY) vs MA20 | {dxy_pct:+.1f}% | {"走弱" if dxy_pct < -1 else ("稳定" if dxy_pct < 2 else "强势")} |')

    hyg_lqd_pct = out['indicators'].get('HYG_LQD_ratio_pct')
    if hyg_lqd_pct is not None:
        lines.append(f'| HYG/LQD 比值变化 | {hyg_lqd_pct:+.1f}% | {"信用扩张" if hyg_lqd_pct > 2 else ("稳定" if hyg_lqd_pct > -2 else "信用收缩")} |')
    lines.append('')

    # === 信号汇总 ===
    lines.append('## 二、信号汇总')
    lines.append('')
    lines.append('| 维度 | 状态 | 说明 |')
    lines.append('|------|------|------|')

    for dim, (state, desc) in out['signals'].items():
        marker = '🟢' if state == 'Risk-On' else ('🟡' if state == 'Neutral' else '🔴')
        lines.append(f'| {dim} | {marker} {state} | {desc} |')
    lines.append('')

    # === 综合判断 ===
    lines.append('## 三、综合判断')
    lines.append('')

    if 'Risk-On' in regime:
        lines.append(f'### {regime}')
        lines.append('')
        lines.append('**当前市场处于风险偏好上升环境。**')
        lines.append('')
        lines.append('**对投资的影响**：')
        lines.append('- 可适度提升股票仓位')
        lines.append('- 成长股表现可能优于价值股')
        lines.append('- 风险资产配置可增加')
        lines.append('- 但仍需保留现金缓冲（市场状态可能突然切换）')
    elif 'Neutral' in regime:
        lines.append(f'### {regime}')
        lines.append('')
        lines.append('**当前市场处于中性环境。**')
        lines.append('')
        lines.append('**对投资的影响**：')
        lines.append('- 选股优于择时')
        lines.append('- 维持目标仓位')
        lines.append('- 关注个股基本面变化')
        lines.append('- 警惕状态向 Risk-Off 切换的早期信号')
    elif 'Risk-Off' in regime:
        lines.append(f'### {regime}')
        lines.append('')
        lines.append('**当前市场处于风险偏好下降环境。**')
        lines.append('')
        lines.append('**对投资的影响**：')
        lines.append('- **降低股票仓位**')
        lines.append('- 增加防御性板块配置（必需消费/医疗/公用事业）')
        lines.append('- 现金/债券配置价值上升')
        lines.append('- **提高止损纪律**')
        lines.append('- 不抄底"打折"标的，等待状态确认')
    else:
        lines.append(f'### {regime}')
        lines.append('')
        lines.append('**数据不足以判断市场状态。**')
        lines.append('')
        lines.append('需手动检查以下指标：')
        lines.append('- VIX 水平')
        lines.append('- 主要指数 vs 200 日均线')
        lines.append('- 收益率曲线')
        lines.append('- 美元走势')
    lines.append('')

    # === 错误 ===
    if out['errors']:
        lines.append('---')
        lines.append('')
        lines.append('## 四、数据获取问题')
        lines.append('')
        for err in out['errors']:
            lines.append(f'- ⚠️ {err}')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append(f'**数据源**：Yahoo Finance (yfinance)')
    lines.append(f'**生成工具**：Atlas Market Regime Detector v6')
    lines.append(f'**完整框架**：见 `models/market_regime.md`')
    lines.append('')
    lines.append('*市场状态是描述而非预测，不构成投资建议。*')

    return '\n'.join(lines)


def save_report(content: str, output_dir: str = None) -> str:
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '持仓与风控',
            '市场环境'
        )
    os.makedirs(output_dir, exist_ok=True)

    date = datetime.now().strftime('%Y-%m-%d')
    filename = f'市场环境报告_{date}.md'
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    # 也写入 "latest" 文件用于快速访问
    latest_path = os.path.join(output_dir, '最新市场环境.md')
    with open(latest_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath


def main():
    print('\n>>> 检测当前市场状态...')

    try:
        out = fetch_market_indicators()
        regime = determine_regime(out)
        content = generate_report(out, regime)
        filepath = save_report(content)
        print(f'✅ 当前市场状态: {regime}')
        print(f'   报告: {filepath}')

        # 简化输出
        print('\n信号:')
        for dim, (state, desc) in out['signals'].items():
            marker = '🟢' if state == 'Risk-On' else ('🟡' if state == 'Neutral' else '🔴')
            print(f'   {marker} {dim}: {desc}')

        if out['errors']:
            print('\n⚠️ 数据问题:')
            for err in out['errors']:
                print(f'   - {err}')

        return 0
    except Exception as e:
        print(f'\n❌ DATA ERROR: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())