from datetime import date
from typing import Dict, List

from app.dashboard.ui import humanize_datetime, kpi_cards, section_title
from backend.services.brief_report import brief_delta_rows, morning_brief_markdown


def morning_brief_comparison_markdown(delta: Dict[str, object]) -> str:
    """Export a selected local morning-brief comparison for later review."""
    lines = ["# Atlas 晨报差异复盘", ""]
    if delta.get("status") != "available":
        lines.extend(["## 状态", "", "- {}".format(delta.get("reason", "尚无可比较的本地晨报。"))])
        return "\n".join(lines) + "\n"

    current = delta["current"]
    previous = delta["previous"]
    lines.extend(
        [
            "## 比较基准",
            "",
            "- 当前晨报：#{} · {}".format(current["id"], current["created_at"]),
            "- 对比晨报：#{} · {}".format(previous["id"], previous["created_at"]),
            "",
            "## 风险与研究待办变化",
            "",
        ]
    )
    for row in brief_delta_rows(delta):
        lines.append("- {}：{}".format(row["项目"], row["变化"]))
    lines.extend(
        [
            "",
            "## 当日研究结论",
            "",
            "- 当前结论：{}".format(current.get("research_conclusion") or "未填写"),
            "- 对比结论：{}".format(previous.get("research_conclusion") or "未填写"),
        ]
    )
    lines.extend(["", "## 使用说明", "", "- 计数减少仅表示需要进一步核对，不代表风险已自动解除。"])
    return "\n".join(lines) + "\n"


def brief_history_rows(history: Dict[str, object]) -> List[Dict[str, object]]:
    """Format snapshot history for inspection without modifying local records."""
    return [
        {
            "快照": "#{}".format(item["id"]),
            "保存时间": item["created_at"],
            "风险预算违规": item["risk_violation_count"],
            "缺少 Thesis": item["missing_thesis_count"],
            "未确认计划": item["unconfirmed_plan_count"],
            "当日研究结论": item.get("research_conclusion") or "未填写",
            "复盘状态": "已复盘" if item.get("review_status") == "reviewed" else "未复盘",
            "复盘日期": item.get("reviewed_at") or "未填写",
        }
        for item in history.get("items", [])
    ]


def open_action_rows(actions: Dict[str, object]) -> List[Dict[str, object]]:
    """Format aggregated review follow-ups for read-only reminders."""
    return [
        {
            "行动项": item["action_text"],
            "晨报快照": "#{} · {}".format(item["snapshot_id"], item["snapshot_created_at"]),
            "关联决策": item["decision_legacy_key"] or "未关联",
            "优先级": {"high": "高", "normal": "普通", "low": "低"}.get(item.get("priority"), "普通"),
            "截止日期": item.get("due_date") or "未设置",
            "提醒": "逾期" if item.get("is_overdue") else "",
        }
        for item in actions.get("items", [])
    ]


def priority_action_rows(actions: Dict[str, object]) -> List[Dict[str, object]]:
    """Select the highest urgency local follow-ups for the daily brief."""
    priority_items = [
        item for item in actions.get("items", [])
        if item.get("is_overdue") or item.get("priority") == "high"
    ][:5]
    return [
        {
            "行动项": item["action_text"],
            "提醒": "逾期" if item.get("is_overdue") else "高优先级",
            "截止日期": item.get("due_date") or "未设置",
            "关联决策": item.get("decision_legacy_key") or "未关联",
        }
        for item in priority_items
    ]


def execution_alert(short_trend: Dict[str, object], long_trend: Dict[str, object]) -> Dict[str, str]:
    """Flag persistently low review execution without making investment recommendations."""
    short_summary = short_trend.get("summary", {})
    long_summary = long_trend.get("summary", {})
    is_low = (
        short_summary.get("created", 0) >= 3
        and long_summary.get("created", 0) >= 3
        and short_summary.get("completion_rate", 0.0) < 50.0
        and long_summary.get("completion_rate", 0.0) < 50.0
    )
    if is_low:
        return {
            "status": "warning",
            "message": "执行力提醒：近 7 天与近 30 天行动项完成率持续偏低，请优先复核未完成事项。此提醒不构成投资或交易建议。",
        }
    return {"status": "ok", "message": "执行节奏暂无持续偏低提醒。"}


def render_morning_brief(
    st,
    market: Dict[str, object],
    refresh_market,
    portfolio: Dict[str, object],
    screener: Dict[str, object],
    open_actions: Dict[str, object],
    load_open_actions,
    action_trend,
    load_action_trend,
    get_alert_acknowledgement,
    acknowledge_alert,
    delta: Dict[str, object],
    history: Dict[str, object],
    save_snapshot,
    load_delta,
    update_review,
    decision_journal,
    load_actions,
    create_action,
    update_action,
) -> None:
    """Render a read-only daily research checklist from existing verified endpoints."""
    section_title(st, "晨报", "研究清单，不构成投资建议；所有指标沿用各自数据来源与口径。")
    cache = market.get("cache") or {}
    if st.button("手动刷新行情"):
        try:
            market = refresh_market()
        except Exception as error:
            st.error("无法刷新行情：{}".format(error))
        else:
            st.success("行情已刷新。")
            st.rerun()
    st.caption(
        "行情缓存：{}；最后成功数据时间：{}".format(
            "已命中" if cache.get("cached") else "已刷新",
            humanize_datetime(
                next(
                    (item.get("fetched_at") for item in market.get("indices", []) if item.get("fetched_at")),
                    None,
                )
            ),
        )
    )
    st.subheader("待完成行动项")
    due_window = st.selectbox("行动项截止日筛选", ["all", "today", "week"], format_func=lambda value: {"all": "全部待办", "today": "今日到期", "week": "本周到期"}[value])
    if due_window != "all":
        open_actions = load_open_actions(due_window)
    summary = open_actions.get("summary", {})
    st.caption("完成率：{}%（已完成 {} / 总计 {}）".format(summary.get("completion_rate", 0.0), summary.get("completed", 0), summary.get("total", 0)))
    integrity = portfolio["research_integrity"]
    kpi_cards(
        st,
        [
            {
                "label": "待完成行动",
                "value": open_actions.get("total", 0),
                "note": "完成率 {}%".format(summary.get("completion_rate", 0.0)),
                "tone": "danger" if open_actions.get("total", 0) else "good",
            },
            {
                "label": "风险违规",
                "value": portfolio["risk"]["violation_count"],
                "note": "按当前生效风险预算",
                "tone": "danger" if portfolio["risk"]["violation_count"] else "good",
            },
            {
                "label": "缺少 Thesis",
                "value": integrity["missing_thesis_count"],
                "note": "待补研究逻辑",
                "tone": "warn" if integrity["missing_thesis_count"] else "good",
            },
            {
                "label": "候选股票",
                "value": screener.get("total", 0),
                "note": "来自历史快照",
                "tone": "neutral",
            },
        ],
    )
    summary_parts = []
    open_total = open_actions.get("total", 0)
    risk_count = portfolio["risk"]["violation_count"]
    thesis_missing = integrity["missing_thesis_count"]
    summary_parts.append(
        "{} 项复盘待办".format(open_total) if open_total else "暂无待办"
    )
    summary_parts.append("{} 项风险违规".format(risk_count))
    summary_parts.append("{} 个持仓缺 Thesis".format(thesis_missing))
    st.info("今日状态：" + "；".join(summary_parts) + "。")
    if open_actions.get("items"):
        st.warning("有 {} 项复盘行动待处理。".format(open_actions["total"]))
        st.dataframe(open_action_rows(open_actions), width="stretch", hide_index=True)
    else:
        st.success("暂无待完成复盘行动项。")
    st.subheader("今日优先事项")
    priority_rows = priority_action_rows(open_actions)
    if priority_rows:
        st.warning("优先处理逾期或高优先级复盘事项。")
        st.dataframe(priority_rows, width="stretch", hide_index=True)
    else:
        st.info("当前没有逾期或高优先级行动项。")
    st.subheader("行动项完成趋势")
    trend_days = st.selectbox("趋势周期", [7, 30], format_func=lambda days: "近 {} 天".format(days))
    if trend_days != action_trend.get("days"):
        action_trend = load_action_trend(trend_days)
    trend_summary = action_trend["summary"]
    st.caption("新增 {} 项 · 完成 {} 项 · 完成率 {}%".format(trend_summary["created"], trend_summary["completed"], trend_summary["completion_rate"]))
    alert = execution_alert(action_trend, load_action_trend(30))
    if alert["status"] == "warning":
        alert_key = "execution-low-{}-{}".format(action_trend["summary"]["completion_rate"], load_action_trend(30)["summary"]["completion_rate"])
        acknowledgement = get_alert_acknowledgement(alert_key)
        if acknowledgement["acknowledged"]:
            st.info("执行力提醒：已查看（{}）。".format(acknowledgement["acknowledged_at"]))
        else:
            st.warning(alert["message"])
            if st.button("标记提醒为已查看"):
                acknowledge_alert(alert_key)
                st.rerun()
    if action_trend["items"]:
        st.dataframe(
            [{"日期": item["action_date"], "完成行动项": item["completed"] or 0} for item in action_trend["items"]],
            width="stretch",
            hide_index=True,
        )
    research_conclusion = st.text_area(
        "当日研究结论（可选）",
        placeholder="记录今天最重要的研究判断、待验证事项或风险提醒。",
    )
    if st.button("保存本地晨报快照"):
        try:
            save_snapshot(research_conclusion)
        except Exception as error:
            st.error("无法保存晨报快照：{}".format(error))
        else:
            st.success("已保存；页面刷新后显示与上一份晨报的变化。")
            st.rerun()
    indices = market.get("indices", [])
    columns = st.columns(len(indices))
    for column, item in zip(columns, indices):
        price = item.get("price")
        change = item.get("change_pct")
        column.metric(item.get("name"), "数据不可用" if price is None else "{:.2f}".format(float(price)), "数据不可用" if change is None else "{:+.2f}%".format(float(change)))
        column.caption("{} · {}".format(item.get("source") or "未提供", humanize_datetime(item.get("observed_at"))))
    st.subheader("今日研究待办")
    st.caption("组合快照：{} · 来源：{}".format(portfolio.get("as_of_date") or "未提供", portfolio["summary"].get("source_path") or "未提供"))
    st.info("缺少 Thesis：{}；未确认计划：{}；风险预算违规：{}。".format(integrity["missing_thesis_count"], integrity["unconfirmed_plan_count"], portfolio["risk"]["violation_count"]))
    st.dataframe(integrity["items"], width="stretch", hide_index=True)
    st.subheader("风险变化摘要")
    if delta.get("status") == "available":
        st.caption("对比上一份已保存的本地晨报；计数减少仅表示待进一步核对。")
        st.dataframe(brief_delta_rows(delta), width="stretch", hide_index=True)
    else:
        st.info(delta.get("reason", "保存至少两份本地晨报后可比较风险变化。"))
    history_tab = st.tabs(["晨报历史与复盘"])[0]
    with history_tab:
        delta = render_morning_brief_history(
            st,
            history,
            decision_journal,
            update_review,
            load_delta,
            load_actions,
            create_action,
            update_action,
            delta,
        )
    st.download_button(
        "下载 Markdown 晨报",
        morning_brief_markdown(market, portfolio, screener, delta),
        file_name="atlas-morning-brief-{}.md".format(market.get("as_of", "local")[:10]),
        mime="text/markdown",
    )
    st.subheader("筛选候选（历史快照）")
    st.caption("候选 {} 只；ROE、营收增长仍无完整覆盖。".format(screener["total"]))
    st.dataframe([{"股票": item["name"], "代码": item["symbol"], "行业主题": item["sector"]} for item in screener["items"][:10]], width="stretch", hide_index=True)


def render_morning_brief_history(
    st,
    history: Dict[str, object],
    decision_journal: Dict[str, object],
    update_review,
    load_delta,
    load_actions,
    create_action,
    update_action,
    delta: Dict[str, object],
) -> Dict[str, object]:
    """Render local morning-brief history and review workflows inside the history tab."""
    st.subheader("本地晨报历史")
    history_items = history.get("items", [])
    if not history_items:
        st.info("尚无本地晨报快照。保存晨报后可在此选择任意两份进行复盘。")
        return delta
    st.caption("共 {} 份本地晨报；历史快照只读。".format(history.get("total", len(history_items))))
    st.dataframe(brief_history_rows(history), width="stretch", hide_index=True)
    review_options = [item["id"] for item in history_items]
    review_target_id = st.selectbox(
        "选择需复盘的晨报",
        review_options,
        format_func=lambda snapshot_id: "#{} · {}".format(snapshot_id, next(item["created_at"] for item in history_items if item["id"] == snapshot_id)),
    )
    review_target = next(item for item in history_items if item["id"] == review_target_id)
    if review_target.get("review_status") == "reviewed":
        st.caption("该晨报已于 {} 复盘。".format(review_target.get("reviewed_at") or "未记录日期"))
        review_notes = st.text_area(
            "复盘备注",
            value=review_target.get("review_notes") or "",
            key="review_notes_{}".format(review_target_id),
        )
        if st.button("保存复盘备注"):
            try:
                update_review(review_target_id, True, review_target.get("reviewed_at"), review_notes)
            except Exception as error:
                st.error("无法保存复盘备注：{}".format(error))
            else:
                st.rerun()
        action_text = st.text_input("后续行动项", key="action_text_{}".format(review_target_id))
        decision_items = decision_journal.get("items", [])
        decision_options = [""] + [item["legacy_key"] for item in decision_items]
        decision_key = st.selectbox(
            "关联决策日志（可选）",
            decision_options,
            format_func=lambda key: "不关联" if not key else next(
                "{} · {}".format(item["legacy_key"], item["symbol"] or "未提供")
                for item in decision_items if item["legacy_key"] == key
            ),
            key="action_decision_{}".format(review_target_id),
        )
        priority = st.selectbox("优先级", ["high", "normal", "low"], format_func=lambda value: {"high": "高", "normal": "普通", "low": "低"}[value], key="action_priority_{}".format(review_target_id))
        set_due_date = st.checkbox("设置截止日期", key="action_due_enabled_{}".format(review_target_id))
        due_date = st.date_input("截止日期", value=date.today(), key="action_due_{}".format(review_target_id)).isoformat() if set_due_date else None
        if st.button("添加后续行动项"):
            try:
                create_action(review_target_id, action_text, decision_key or None, due_date, priority)
            except Exception as error:
                st.error("无法添加行动项：{}".format(error))
            else:
                st.rerun()
        actions = load_actions(review_target_id).get("items", [])
        if actions:
            st.caption("复盘行动清单")
            st.dataframe(
                [
                    {
                        "行动项": item["action_text"],
                        "关联决策": item["decision_legacy_key"] or "未关联",
                        "优先级": {"high": "高", "normal": "普通", "low": "低"}.get(item.get("priority"), "普通"),
                        "截止日期": item.get("due_date") or "未设置",
                        "状态": "已完成" if item["status"] == "completed" else "待完成",
                        "完成时间": item["completed_at"] or "未完成",
                    }
                    for item in actions
                ],
                width="stretch",
                hide_index=True,
            )
            for item in actions:
                target_completed = item["status"] != "completed"
                label = "标记完成" if target_completed else "重新打开"
                if st.button(label + "：" + item["action_text"], key="action_status_{}".format(item["id"])):
                    try:
                        update_action(review_target_id, item["id"], target_completed)
                    except Exception as error:
                        st.error("无法更新行动项：{}".format(error))
                    else:
                        st.rerun()
        if st.button("标记为未复盘"):
            try:
                update_review(review_target_id, False, None, None)
            except Exception as error:
                st.error("无法更新复盘状态：{}".format(error))
            else:
                st.rerun()
    else:
        reviewed_at = st.date_input("复盘日期", value=date.today())
        review_notes = st.text_area("复盘备注（可选）", key="review_notes_{}".format(review_target_id))
        if st.button("标记为已复盘"):
            try:
                update_review(review_target_id, True, reviewed_at.isoformat(), review_notes)
            except Exception as error:
                st.error("无法更新复盘状态：{}".format(error))
            else:
                st.rerun()
    if len(history_items) >= 2:
        options = [item["id"] for item in history_items]
        current_column, previous_column = st.columns(2)
        current_id = current_column.selectbox(
            "当前晨报",
            options,
            format_func=lambda snapshot_id: "#{} · {}".format(snapshot_id, next(item["created_at"] for item in history_items if item["id"] == snapshot_id)),
        )
        previous_id = previous_column.selectbox(
            "对比晨报",
            options,
            index=1,
            format_func=lambda snapshot_id: "#{} · {}".format(snapshot_id, next(item["created_at"] for item in history_items if item["id"] == snapshot_id)),
        )
        if current_id == previous_id:
            st.warning("请选择两份不同的晨报快照进行比较。")
        else:
            selected_delta = load_delta(current_id, previous_id)
            st.caption("已按选定的两份晨报更新风险变化摘要。")
            st.dataframe(brief_delta_rows(selected_delta), width="stretch", hide_index=True)
            st.download_button(
                "下载差异复盘 Markdown",
                morning_brief_comparison_markdown(selected_delta),
                file_name="atlas-morning-comparison-{}-{}.md".format(current_id, previous_id),
                mime="text/markdown",
            )
            delta = selected_delta
    return delta
