from typing import Dict

from app.dashboard.ui import kpi_cards, section_title, status_pill


def render_morning_intelligence(
    st,
    intelligence: Dict[str, object],
) -> None:
    """Render the investment cockpit built from rule-based local intelligence."""
    section_title(
        st,
        "ATLAS MORNING INTELLIGENCE",
        "由本地规则引擎基于已验证数据生成，不构成投资建议。",
    )
    market = intelligence["market"]
    portfolio = intelligence["portfolio"]
    focus_count = intelligence["focus_count"]
    kpi_cards(
        st,
        [
            {
                "label": "市场状态",
                "value": market["label"],
                "note": market["reasons"][0] if market["reasons"] else "数据不足",
                "tone": market["tone"],
            },
            {
                "label": "组合状态",
                "value": portfolio["label"],
                "note": portfolio["reasons"][0] if portfolio["reasons"] else "未发现异常",
                "tone": portfolio["tone"],
            },
            {
                "label": "今日关注",
                "value": focus_count,
                "note": "风险、研究与复盘事项",
                "tone": "danger" if focus_count else "good",
            },
        ],
    )

    market_column, portfolio_column = st.columns(2)
    with market_column:
        st.markdown("**市场判断**")
        status_pill(st, market["label"], market["tone"])
        for reason in market["reasons"]:
            st.markdown("- " + reason)
    with portfolio_column:
        st.markdown("**组合判断**")
        status_pill(st, portfolio["label"], portfolio["tone"])
        for reason in portfolio["reasons"]:
            st.markdown("- " + reason)

    st.markdown("**今日关注**")
    focus_items = intelligence["focus"]
    if not focus_items:
        st.success("今日暂无必须立即处理的事项。")
        return
    for item in focus_items:
        name = item.get("name") or item.get("symbol") or "未命名"
        st.markdown(
            "- **{}**（{}）：{}；下一步：{}".format(
                name,
                item.get("kind", "事项"),
                item.get("message", "未提供"),
                item.get("next_step", "复核"),
            )
        )
