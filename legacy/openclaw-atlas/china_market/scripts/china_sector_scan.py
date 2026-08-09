#!/usr/bin/env python3
"""
Atlas · 全市场科技板块扫描

功能：
  1. 拉今日 A 股科技板块行情（5日涨幅排序）
  2. 选出 Top N 强势赛道
  3. 每个赛道从全市场拉 Top 5 候选（市值≥50亿）
  4. 拉基本面（毛利率/ROE）+ 腾讯行情
  5. 评分排序 → 每赛道 Top 3
  6. 写入本地 DB（追加）+ 生成复盘报告
  7. 用 watchlist 标注但不剔除

数据源：
  - 问财（hithink-market-query skill）：板块涨幅/财务
  - 腾讯接口（atlas_py market）：市值/PE/价格

输出：
  - DB：investment/china_market/data/stock_fundamentals.jsonl
  - 报告：investment/china_market/reports/全市场Top3_{DATE}.md
  - 控制台：Top 9 总榜

用法：
  atlas_py sector_scan                     # 默认 Top 3 赛道 × Top 3/赛道
  atlas_py sector_scan --top-sectors 5     # 选 5 个赛道
  atlas_py sector_scan --top-per-sector 5  # 每赛道 5 只
  atlas_py sector_scan --min-mv 100        # 市值 ≥100亿 阈值

v2.0 · 2026-08-08
"""

import sys
import os
import re
import json
import argparse
import subprocess
from datetime import datetime
from collections import defaultdict

WORKSPACE = '/Users/huan/.openclaw/workspace'
DB_PATH = f'{WORKSPACE}/investment/china_market/data/stock_fundamentals.jsonl'
WATCHLIST_PATH = f'{WORKSPACE}/investment/china_market/data/user_watchlist.json'
REPORT_DIR = f'{WORKSPACE}/investment/china_market/reports'

# 强势赛道候选（可扩展）
TECH_SECTORS = ['电子', '通信设备', '军工电子', '计算机', '电池']


def call_iwencai(query, limit=80):
    """问财 CLI 调用（封装）+ 解析"""
    cli = '/Users/huan/.openclaw/workspace/skills/hithink-market-query/scripts/cli.py'
    try:
        r = subprocess.run(
            ['python3', cli, '--query', query, '--limit', str(limit)],
            capture_output=True, text=True, timeout=60
        )
        return json.loads(r.stdout)
    except Exception as e:
        print(f'⚠️ 问财调用失败：{e}', file=sys.stderr)
        return {'datas': []}


def call_tencent(codes):
    """腾讯接口批量拉行情（atlas_py market）"""
    if not codes:
        return {}
    atlas_py = '/Users/huan/.openclaw/workspace/investment/scripts/atlas_py'
    try:
        r = subprocess.run(
            [atlas_py, 'market'] + codes,
            capture_output=True, text=True, timeout=120
        )
        out = r.stdout + r.stderr
        return parse_tencent(out)
    except Exception as e:
        print(f'⚠️ 腾讯调用失败：{e}', file=sys.stderr)
        return {}


def parse_tencent(text):
    """解析 atlas_py market 输出 → dict[code] -> {name, mv_yi, pe, ...}"""
    data = {}
    for chunk in re.split(r'(?=✅ )', text):
        m = re.search(r'✅ (.+?) \((.+?)\)', chunk)
        if not m:
            continue
        name, code = m.group(1), m.group(2).strip()
        pm = re.search(r'市值: ([\d.]+) 亿', chunk)
        pem = re.search(r'PE: ([-\d.]+)', chunk)
        chm = re.search(r'涨跌: ([+\-\d.]+)', chunk)
        prm = re.search(r'价格: ¥([\d.]+)', chunk)
        data[code] = {
            'name': name,
            'mv_yi': float(pm.group(1)) if pm else 0,
            'pe': pem.group(1) if pem else '-',
            'change_today': float(chm.group(1)) if chm else 0,
            'price': float(prm.group(1)) if prm else 0,
        }
    return data


def step0_rank_sectors(top_n=3):
    """Step 0: 拉5日板块涨幅，排序选 Top N"""
    print(f'\n=== Step 0: 拉 5 日板块行情（{len(TECH_SECTORS)} 个赛道）===')
    sector_5d = defaultdict(lambda: {'count': 0, 'total_change_5d': 0, 'stocks': []})

    for sec in TECH_SECTORS:
        d = call_iwencai(f'所属同花顺行业:{sec} 涨跌幅 主力资金净流入 最新价 总市值', limit=80)
        for x in d.get('datas', []):
            c5 = float(x.get('涨跌幅[20260803-20260807]', 0) or 0)
            sector_5d[sec]['count'] += 1
            sector_5d[sec]['total_change_5d'] += c5
            sector_5d[sec]['stocks'].append({
                'code': x.get('股票代码', ''),
                'name': x.get('股票简称', ''),
                'price': x.get('最新价', ''),
                'change_5d': c5,
            })
        print(f'  {sec:8s} : {sector_5d[sec]["count"]:>3} 只, 5日累涨幅 {sector_5d[sec]["total_change_5d"]:>6.1f}%')

    ranked = sorted(sector_5d.items(), key=lambda x: x[1]['total_change_5d'], reverse=True)
    return ranked[:top_n], sector_5d


def step1_pick_top(top_sectors, top_per=5, min_mv=50):
    """Step 1: 每赛道 Top 5 → 腾讯补市值 → Top 3"""
    # 收集所有候选
    candidates = []
    for sec, v in top_sectors:
        for s in v['stocks']:
            candidates.append((s['code'], s['name'], sec, s['change_5d'], s['price']))

    # 排序 + 拿前 (top_per × 赛道数)
    candidates.sort(key=lambda x: -x[3])
    shortlist = candidates[:top_per * len(top_sectors)]

    # 腾讯补市值
    codes = [c[0] for c in shortlist]
    print(f'\n=== Step 1: 拉 {len(codes)} 只的腾讯行情 ===')
    tx = call_tencent(codes)

    # 合并 + 标注
    with open(WATCHLIST_PATH) as f:
        wl = {x['code']: x['name'] for x in json.load(f)}

    enriched = []
    for code, name, sec, c5, price in shortlist:
        t = tx.get(code, {})
        enriched.append({
            'code': code, 'name': name, 'sector': sec,
            'change_5d': c5, 'change_today': t.get('change_today', 0),
            'mv_yi': t.get('mv_yi', 0), 'pe': t.get('pe', '-'),
            'price': t.get('price', price),
            'wl_mark': '⭐' if code in wl else '',
        })

    # 按赛道分组 + 过滤市值 + Top 3
    by_sec = defaultdict(list)
    for e in enriched:
        by_sec[e['sector']].append(e)
    final = {}
    for sec, lst in by_sec.items():
        big = [x for x in lst if x['mv_yi'] >= min_mv]
        final[sec] = big[:3] if len(big) >= 3 else lst[:3]
    return final


def step3_pull_fundamentals(picks):
    """Step 3: 拉基本面，写 DB"""
    # 读 watchlist
    with open(WATCHLIST_PATH) as f:
        wl = {x['code'] for x in json.load(f)}

    all_codes = [s['code'] for lst in picks.values() for s in lst]
    if not all_codes:
        return {}

    names = ' '.join([s['name'] for lst in picks.values() for s in lst])
    print(f'\n=== Step 3: 拉 {len(all_codes)} 只的基本面 ===')

    code_map = {s['code']: s['name'] for lst in picks.values() for s in lst}
    sec_map = {s['code']: s['sector'] for lst in picks.values() for s in lst}

    d = call_iwencai(f'{names} 营业收入 净利润 同比 ROE 毛利率 资产负债率', limit=15)
    ts = datetime.now().isoformat()
    results = {}
    for x in d.get('datas', []):
        code = x.get('股票代码', '')
        rec = {
            'timestamp': ts, 'source': 'iwencai',
            'code': code, 'name': code_map.get(code, x.get('股票简称', '')),
            'sector': sec_map.get(code, ''),
            'fundamentals': {
                'net_profit_yoy': x.get('归属母公司股东的净利润(同比增长率)[20260331]', ''),
                'revenue_yoy': x.get('营业收入(同比增长率)[20260331]', '') or x.get('营业总收入(同比增长率)[20260331]', ''),
                'gross_margin': x.get('销售毛利率[20260331]', ''),
                'roe': x.get('净资产收益率[20260331]', '') or x.get('ROE[20260331]', ''),
                'debt_ratio': x.get('资产负债率[20260331]', ''),
            },
        }
        results[rec['name']] = rec
        # 追加到 DB
        with open(DB_PATH, 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    print(f'  ✅ 入库 {len(results)} 只基本面记录')
    return results


def score_stock(s, funda):
    """单只评分（财务+趋势+估值+市值 = 100）"""
    sc = 0
    reasons = []

    # 5日涨幅 (25 分)
    try:
        c5 = float(s['change_5d'])
        if c5 > 40: sc += 25; reasons.append(f'5日+{c5:.1f}%🔥')
        elif c5 > 25: sc += 18; reasons.append(f'5日+{c5:.1f}%')
        elif c5 > 10: sc += 10; reasons.append(f'5日+{c5:.1f}%')
        else: sc += 3
    except:
        sc += 3

    # 毛利率 (25 分)
    try:
        gm = float(funda.get('gross_margin') or 0)
        if gm > 50: sc += 25; reasons.append(f'毛利率{gm:.1f}%🔥')
        elif gm > 30: sc += 18; reasons.append(f'毛利率{gm:.1f}%')
        elif gm > 20: sc += 10; reasons.append(f'毛利率{gm:.1f}%')
        else: sc += 5
    except:
        sc += 5

    # ROE (20 分)
    try:
        roe = float(funda.get('roe') or 0)
        if roe > 10: sc += 20; reasons.append(f'ROE{roe:.1f}%🔥')
        elif roe > 5: sc += 14; reasons.append(f'ROE{roe:.1f}%')
        elif roe > 0: sc += 8; reasons.append(f'ROE{roe:.1f}%')
        else: sc += 2
    except:
        sc += 2

    # PE (20 分)
    try:
        pe_v = float(s['pe'])
        if 0 < pe_v < 50: sc += 20; reasons.append(f'PE{pe_v:.0f}🟢')
        elif 0 < pe_v < 100: sc += 12; reasons.append(f'PE{pe_v:.0f}')
        elif 0 < pe_v < 200: sc += 6; reasons.append(f'PE{pe_v:.0f}贵')
        else: sc += 0; reasons.append(f'PE{pe_v:.0f}极贵🔴')
    except:
        sc += 5; reasons.append('PE异常')

    # 市值 (10 分)
    try:
        mv = float(s['mv_yi'])
        if 100 <= mv <= 1000: sc += 10; reasons.append(f'市值{mv:.0f}亿🟢')
        elif mv >= 1000: sc += 6; reasons.append(f'市值{mv:.0f}亿')
        else: sc += 4
    except:
        sc += 4

    return sc, reasons


def step4_report(picks, fundas, top_n):
    """Step 4: 生成复盘报告 + 控制台输出"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 计算评分
    all_scored = []
    sec_scored_map = {}
    for sec, lst in picks.items():
        sec_scored = []
        for s in lst:
            f = fundas.get(s['name'], {}).get('fundamentals', {})
            sc, reasons = score_stock(s, f)
            item = {**s, 'score': sc, 'reasons': reasons, 'fundamentals': f}
            sec_scored.append(item)
            all_scored.append(item)
        sec_scored_map[sec] = sec_scored

    # 控制台 Top 9
    all_scored.sort(key=lambda x: -x['score'])
    print(f'\n=== Step 4: Top {len(all_scored)} 总榜 ===')
    for i, s in enumerate(all_scored, 1):
        print(f'  {i}. {s["name"]:8s} ({s["sector"]:6s}) 评分{s["score"]:>3} | 5日+{s["change_5d"]:>4.1f}% | {s["reasons"][0]}')

    # Markdown 报告
    md = [f'# 全市场科技板块复盘 · {ts}\n']
    md.append('> 来源：**全市场筛选**（非自选股）')
    md.append(f'> Top {top_n} 强势赛道 × 每赛道 Top 3 = {len(all_scored)} 只\n')
    md.append('---\n')

    md.append('## 一、Top 9 总榜\n')
    md.append('| # | 名称 | 板块 | 评分 | 5日 | PE | 备注 |')
    md.append('|---|---|---|---:|---:|---:|---|')
    for i, s in enumerate(all_scored, 1):
        md.append(f'| {i} | {s["name"]} | {s["sector"]} | **{s["score"]}** | +{s["change_5d"]:.1f}% | {s["pe"]} | {s["reasons"][0]} |')

    md.append('\n---\n## 二、每赛道详情\n')
    for sec in picks.keys():
        md.append(f'### 📌 {sec}\n')
        for rank, x in enumerate(sorted(sec_scored_map[sec], key=lambda x: -x['score']), 1):
            medal = '🥇🥈🥉'[rank-1]
            md.append(f'#### {medal} #{rank} {x["name"]} ({x["code"]}) · 评分 {x["score"]}{x.get("wl_mark","")}')
            md.append(f'- 现价 ¥{x["price"]}（今日 {x["change_today"]:+.1f}%）')
            md.append(f'- 5日 +{x["change_5d"]:.1f}% / 市值 {x["mv_yi"]:.0f}亿 / PE {x["pe"]}')
            f = x['fundamentals']
            md.append(f'- 毛利率 {f.get("gross_margin","-")}% / ROE {f.get("roe","-")}%')
            md.append(f'- 评分理由：{", ".join(x["reasons"])}\n')

    # 写报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = f'{REPORT_DIR}/全市场Top3_{datetime.now().strftime("%Y-%m-%d")}.md'
    with open(out_path, 'w') as f:
        f.write('\n'.join(md))
    print(f'\n✅ 报告：{out_path}')
    return all_scored


def main():
    ap = argparse.ArgumentParser(description='全市场科技板块扫描')
    ap.add_argument('--top-sectors', type=int, default=3, help='选几个强势赛道')
    ap.add_argument('--top-per-sector', type=int, default=5, help='每赛道候选池')
    ap.add_argument('--min-mv', type=float, default=50, help='市值阈值（亿）')
    ap.add_argument('--final-top', type=int, default=3, help='每赛道最终 Top N')
    args = ap.parse_args()

    print('=' * 60)
    print(f'Atlas 全市场科技板块扫描 v2.0 · {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'  赛道数: {args.top_sectors} | 候选池: {args.top_per_sector}/赛道 | 市值 ≥{args.min_mv}亿')
    print('=' * 60)

    # Step 0: 选强势赛道
    top_sectors, _ = step0_rank_sectors(args.top_sectors)

    # Step 1+2: 候选池 + 腾讯补市值 + Top 3
    picks = step1_pick_top(top_sectors, args.top_per_sector, args.min_mv)
    if args.final_top != 3:
        for sec in picks:
            picks[sec] = picks[sec][:args.final_top]

    # Step 3: 拉基本面
    fundas = step3_pull_fundamentals(picks)

    # Step 4: 评分 + 报告
    step4_report(picks, fundas, args.top_sectors)

    print('\n' + '=' * 60)
    print('✅ 全部完成')


if __name__ == '__main__':
    main()