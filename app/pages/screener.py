from typing import Dict, List


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
                "毛利率": _format_percent(metrics.get("gross_margin")),
                "市值（亿元）": _format_number(metrics.get("market_value_yi")),
                "指标来源": " / ".join(dict.fromkeys(sources.values())) or "未提供",
            }
        )
    return rows


def render_screener(st, result: Dict[str, object]) -> None:
    """Render historical-only screening results and coverage limits."""
    st.subheader("选股中心")
    st.caption("仅使用已留存的历史快照，不将缺失字段估算为财务事实。")
    st.info("当前数据口径：历史快照。ROE、营收增长尚未具备完整覆盖，暂不作为筛选条件。")
    st.caption("候选股票 {} 只。每项指标来源均显示在结果表中。".format(result.get("total", 0)))
    st.dataframe(screener_rows(result), use_container_width=True, hide_index=True)


def _format_number(value: object) -> str:
    return "数据不可用" if value is None else "{:.2f}".format(float(value))


def _format_percent(value: object) -> str:
    return "数据不可用" if value is None else "{:.2f}%".format(float(value))
