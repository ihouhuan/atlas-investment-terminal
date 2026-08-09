from datetime import datetime, timezone
from typing import Dict

from app.dashboard.ui import (
    change_tone,
    humanize_amount,
    humanize_datetime,
    kpi_cards,
    section_title,
    status_label,
)

METRIC_DISPLAY_ORDER = [
    "total_revenue",
    "total_revenue_growth",
    "net_profit",
    "net_profit_growth",
    "deducted_net_profit",
    "deducted_net_profit_growth",
    "gross_margin",
    "net_margin",
    "roe",
    "roe_diluted",
    "debt_to_assets",
    "current_ratio",
    "quick_ratio",
    "eps",
    "bps",
    "operating_cash_flow_per_share",
]

HISTORY_COLUMNS = [
    ("total_revenue", "营业总收入"),
    ("net_profit", "净利润"),
    ("gross_margin", "销售毛利率"),
    ("roe", "净资产收益率"),
    ("debt_to_assets", "资产负债率"),
]


def financial_metric_rows(financials: Dict[str, object]) -> list:
    """Format the read-only normalized financial cache for display."""
    rows = []
    metrics = financials.get("metrics", {})
    ordered_keys = sorted(
        metrics,
        key=lambda key: (
            METRIC_DISPLAY_ORDER.index(key)
            if key in METRIC_DISPLAY_ORDER
            else len(METRIC_DISPLAY_ORDER)
        ),
    )
    for key in ordered_keys:
        metric = metrics[key]
        rows.append(
            {
                "指标": metric.get("label") or key,
                "报告期": metric.get("report_date") or "未提供",
                "数值": _format_metric(metric),
                "来源": metric.get("source") or "未提供",
                "刷新时间": metric.get("fetched_at") or "未提供",
            }
        )
    return rows


def financial_history_rows(financials: Dict[str, object]) -> list:
    """Format recent report periods without making historical data look current."""
    rows = []
    for report in financials.get("history", []):
        metrics = report.get("metrics", {})
        row = {"报告期": report.get("report_date") or "未提供"}
        for key, label in HISTORY_COLUMNS:
            row[label] = _format_metric(metrics.get(key))
        rows.append(row)
    return rows


def cache_age_text(fetched_at, now=None) -> str:
    """Render a short human-readable cache age without fabricating freshness."""
    if not fetched_at:
        return "未提供"
    try:
        parsed = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        days = (current - parsed).days
    except (TypeError, ValueError):
        return str(fetched_at)
    if days < 0:
        return "刚刚刷新"
    if days == 0:
        return "今日刷新"
    if days == 1:
        return "1 天前刷新"
    return "{} 天前刷新".format(days)


def valuation_rows(valuation: Dict[str, object]) -> list:
    """Format preserved legacy valuation snapshots without treating them as live."""
    labels = {
        "pe_ttm": "PE TTM",
        "pb": "PB",
        "market_value_yi": "市值（亿元）",
    }
    rows = []
    for key in ("pe_ttm", "pb", "market_value_yi"):
        metric = valuation.get("metrics", {}).get(key)
        rows.append(
            {
                "指标": labels.get(key, key),
                "数值": (
                    "数据不可用"
                    if not metric or metric.get("value") is None
                    else "{:.2f}".format(float(metric["value"]))
                ),
                "来源": metric.get("source") if metric else "未提供",
                "时间": metric.get("observed_at") if metric else "未提供",
            }
        )
    return rows


def render_stock_detail(
    st, detail: Dict[str, object], refresh_financials=None
) -> None:
    """Render a stock detail response while distinguishing real-time and historical data."""
    company = detail["company"]
    quote = detail["quote"]
    history = detail["financial_history"]
    fund_flow = detail["fund_flow"]
    section_title(
        st,
        "{} · {}".format(company["name"], company["symbol"]),
        "{} · {} · {}".format(
            company["exchange"],
            company["sector"] or "未分类",
            company["industry"] or "未分类",
        ),
    )
    kpi_cards(
        st,
        [
            {
                "label": "最新价",
                "value": "数据不可用" if quote["price"] is None else "{:.2f}".format(float(quote["price"])),
                "note": quote["source"] or "未提供",
                "tone": change_tone(quote.get("change_pct")),
            },
            {
                "label": "涨跌幅",
                "value": "{:+.2f}%".format(float(quote["change_pct"])) if quote["change_pct"] is not None else "数据不可用",
                "note": humanize_datetime(quote.get("observed_at")),
                "tone": change_tone(quote.get("change_pct")),
            },
            {
                "label": "行情状态",
                "value": status_label(quote.get("status")),
                "note": "实时或历史缓存",
                "tone": "good" if quote.get("status") == "available" else "warn",
            },
        ],
    )
    st.subheader("资金流（历史快照）")
    if fund_flow["status"] == "unavailable":
        st.info("该股票暂无已导入资金流快照。")
    else:
        kpi_cards(
            st,
            [
                {
                    "label": "主力净流入",
                    "value": humanize_amount(fund_flow["main_inflow"]),
                    "tone": change_tone(fund_flow.get("main_inflow")),
                },
                {
                    "label": "流入金额",
                    "value": humanize_amount(fund_flow["fund_in"]),
                    "tone": "up",
                },
                {
                    "label": "流出金额",
                    "value": humanize_amount(fund_flow["fund_out"]),
                    "tone": "down",
                },
            ],
        )
        st.caption(
            "来源：{} · 时间：{}；仅为历史快照。".format(
                fund_flow["source"], humanize_datetime(fund_flow["observed_at"])
            )
        )
    st.subheader("财务指标（只读缓存）")
    financials = detail["financials"]
    if refresh_financials is not None:
        if st.button("刷新财务数据", key="refresh-financials"):
            try:
                refresh_financials()
            except Exception as error:
                st.error("刷新财务数据失败：{}".format(error))
            else:
                st.success("财务缓存已刷新。")
                st.rerun()
    if financials["status"] == "unavailable":
        st.info(financials.get("reason") or "本地尚无财务缓存。")
    else:
        st.caption(
            "最新报告期：{} · 来源：{} · 刷新时间：{}（{}）".format(
                financials.get("latest_report_date") or "未提供",
                financials.get("source") or "未提供",
                humanize_datetime(financials.get("fetched_at")),
                cache_age_text(financials.get("fetched_at")),
            )
        )
        st.dataframe(
            financial_metric_rows(financials), width="stretch", hide_index=True
        )
        history_rows = financial_history_rows(financials)
        if history_rows:
            with st.expander("最近报告期历史（只读）"):
                st.dataframe(
                    history_rows, width="stretch", hide_index=True
                )
        st.caption("仅展示已缓存数据，不提供手动编辑；刷新会替换同一报告期的缓存值。")
    st.subheader("估值（历史快照）")
    valuation = detail["valuation"]
    if valuation["status"] == "available":
        st.dataframe(
            valuation_rows(valuation), width="stretch", hide_index=True
        )
        latest_observed_at = max(
            (
                metric.get("observed_at")
                for metric in valuation.get("metrics", {}).values()
                if metric.get("observed_at")
            ),
            default=None,
        )
        st.caption(
            "估值指标来自已留存快照，不视为实时数据；快照时间：{}（{}）。".format(
                humanize_datetime(latest_observed_at),
                cache_age_text(latest_observed_at),
            )
        )
    else:
        st.info(valuation.get("reason") or "本地暂无可验证的 PE、PB 或市值估值快照。")


def _format_metric(metric) -> str:
    if not isinstance(metric, dict) or metric.get("value") is None:
        return "数据不可用"
    value = float(metric["value"])
    unit = metric.get("unit")
    if unit == "percent":
        return "{:.2f}%".format(value)
    if unit == "cny":
        if abs(value) >= 1e8:
            return "{:.2f} 亿".format(value / 1e8)
        if abs(value) >= 1e4:
            return "{:.2f} 万".format(value / 1e4)
        return "{:,.2f}".format(value)
    if unit == "times":
        return "{:.2f} 倍".format(value)
    if unit == "days":
        return "{:.2f} 天".format(value)
    return "{:,.2f}".format(value)
