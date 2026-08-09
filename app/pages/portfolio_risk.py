from typing import Dict, List


def portfolio_position_rows(overview: Dict[str, object]) -> List[Dict[str, str]]:
    """Format persisted portfolio positions for presentation."""
    return [
        {
            "股票": position["name"],
            "代码": position["symbol"],
            "市值": "{:.2f}".format(float(position["market_value"])),
            "仓位": "{:.2%}".format(float(position["weight"])),
            "浮动盈亏": "{:.2f}".format(float(position["pnl"])),
            "仓位层级": position["tier"],
        }
        for position in overview.get("positions", [])
    ]


def open_action_rows(actions: Dict[str, object]) -> List[Dict[str, str]]:
    """Format outstanding review follow-ups for the portfolio-risk view."""
    return [
        {
            "行动项": item["action_text"],
            "晨报快照": "#{}".format(item["snapshot_id"]),
            "关联决策": item["decision_legacy_key"] or "未关联",
            "优先级": {"high": "高", "normal": "普通", "low": "低"}.get(item.get("priority"), "普通"),
            "截止日期": item.get("due_date") or "未设置",
            "提醒": "逾期" if item.get("is_overdue") else "",
        }
        for item in actions.get("items", [])
    ]


def render_portfolio_risk(st, overview: Dict[str, object], open_actions: Dict[str, object], load_open_actions, action_trend, load_action_trend) -> None:
    """Render portfolio facts, risk-budget results, and stress assumptions."""
    summary = overview["summary"]
    st.subheader("组合概览")
    columns = st.columns(4)
    columns[0].metric("组合市值", "{:.2f}".format(float(summary["market_value"])))
    columns[1].metric("现金比例", "{:.2%}".format(float(summary["cash_ratio"])))
    columns[2].metric("浮动盈亏", "{:.2f}".format(float(summary["unrealized_pnl"])))
    columns[3].metric("风险违规", str(overview["risk"]["violation_count"]))
    st.caption("持仓来源：{} · 截止日期：{}".format(summary["source_path"], overview["as_of_date"]))

    st.subheader("待完成复盘行动")
    due_window = st.selectbox("行动项截止日筛选", ["all", "today", "week"], format_func=lambda value: {"all": "全部待办", "today": "今日到期", "week": "本周到期"}[value])
    if due_window != "all":
        open_actions = load_open_actions(due_window)
    summary = open_actions.get("summary", {})
    st.caption("完成率：{}%（已完成 {} / 总计 {}）".format(summary.get("completion_rate", 0.0), summary.get("completed", 0), summary.get("total", 0)))
    if open_actions.get("items"):
        st.warning("{} 项待办可能影响后续研究与风险跟踪。".format(open_actions["total"]))
        st.dataframe(open_action_rows(open_actions), width="stretch", hide_index=True)
    else:
        st.success("暂无待完成复盘行动项。")
    st.subheader("行动项完成趋势")
    trend_days = st.selectbox("趋势周期", [7, 30], format_func=lambda days: "近 {} 天".format(days))
    if trend_days != action_trend.get("days"):
        action_trend = load_action_trend(trend_days)
    trend_summary = action_trend["summary"]
    st.caption("新增 {} 项 · 完成 {} 项 · 完成率 {}%".format(trend_summary["created"], trend_summary["completed"], trend_summary["completion_rate"]))
    if action_trend["items"]:
        st.bar_chart({"完成": {item["action_date"]: item["completed"] or 0 for item in action_trend["items"]}})

    st.subheader("持仓")
    st.dataframe(portfolio_position_rows(overview), width="stretch", hide_index=True)

    st.subheader("风险预算检查")
    violations = overview["risk"]["violations"]
    if violations:
        st.warning("发现 {} 项规则违规；该结果为风险预算检查，不构成交易指令。".format(len(violations)))
        st.dataframe(violations, width="stretch", hide_index=True)
    else:
        st.success("未发现风险预算违规。")

    st.subheader("研究完整性")
    integrity = overview["research_integrity"]
    if integrity["items"]:
        st.info(
            "{} 个持仓缺少 Thesis；{} 条计划记录尚无执行或复盘补录。仅为研究待办，不构成交易指令。".format(
                integrity["missing_thesis_count"], integrity["unconfirmed_plan_count"]
            )
        )
        st.dataframe(integrity["items"], width="stretch", hide_index=True)
    else:
        st.success("当前持仓的 Thesis 和计划记录均已补全。")

    st.subheader("行业集中度")
    concentration_rows = [
        {
            "行业/板块": item["sector"],
            "市值": "{:.2f}".format(float(item["market_value"])),
            "权重": "{:.2%}".format(float(item["weight"])),
        }
        for item in overview["industry_concentration"]
    ]
    st.dataframe(concentration_rows, width="stretch", hide_index=True)

    st.subheader("压力测试")
    st.caption("以下为旧 Atlas 场景库的假设结果，不预测未来市场表现。")
    stress_rows = [
        {
            "情景": item["name"],
            "估算损失": "{:.2f}".format(float(item["estimated_loss"])),
            "组合损失": "{:.2%}".format(float(item["estimated_loss_pct"])),
            "覆盖率": "{:.2%}".format(float(item["coverage_pct"])),
            "来源": item["source_path"],
            "限制": item["limitations"],
        }
        for item in overview["stress_tests"]
    ]
    st.dataframe(stress_rows, width="stretch", hide_index=True)
