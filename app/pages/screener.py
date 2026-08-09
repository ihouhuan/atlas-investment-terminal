from typing import Dict, List

from app.dashboard.ui import kpi_cards, section_title


def screener_rows(result: Dict[str, object]) -> List[Dict[str, str]]:
    """Format preserved screener metrics without filling missing values."""
    rows = []
    for item in result.get("items", []):
        metrics = item.get("metrics", {})
        sources = item.get("sources", {})
        rows.append(
            {
                "股票": item.get("name", "未知"),
                "代码": item.get("symbol", "未知"),
                "行业主题": item.get("sector") or "未分类",
                "PE TTM": _format_number(metrics.get("pe_ttm")),
                "PB": _format_number(metrics.get("pb")),
                "净利润同比": _format_percent(metrics.get("profit_growth")),
                "营收同比": _format_percent(metrics.get("revenue_growth")),
                "毛利率": _format_percent(metrics.get("gross_margin")),
                "ROE": _format_percent(metrics.get("roe")),
                "市值（亿元）": _format_number(metrics.get("market_value_yi")),
                "指标来源": " / ".join(dict.fromkeys(sources.values())) or "未提供",
            }
        )
    return rows


def render_screener(st, result: Dict[str, object]) -> None:
    """Render screening results with per-metric provenance and no estimation."""
    section_title(st, "选股中心", "已刷新股票优先使用 AkShare 规范化缓存，其余使用已留存历史快照；缺失字段不估算。")
    items = result.get("items", [])
    covered_pe = sum(
        1 for item in items if item.get("metrics", {}).get("pe_ttm") is not None
    )
    covered_roe = sum(
        1 for item in items if item.get("metrics", {}).get("roe") is not None
    )
    kpi_cards(
        st,
        [
            {"label": "候选股票", "value": result.get("total", len(items)), "tone": "neutral"},
            {"label": "有 PE TTM", "value": covered_pe, "tone": "good" if covered_pe else "warn"},
            {"label": "有 ROE", "value": covered_roe, "tone": "good" if covered_roe else "warn"},
        ],
    )
    st.caption("候选股票 {} 只。每项指标来源均显示在结果表中。".format(result.get("total", 0)))
    st.dataframe(screener_rows(result), width="stretch", hide_index=True)


def _format_number(value: object) -> str:
    return "数据不可用" if value is None else "{:.2f}".format(float(value))


def _format_percent(value: object) -> str:
    return "数据不可用" if value is None else "{:.2f}%".format(float(value))
