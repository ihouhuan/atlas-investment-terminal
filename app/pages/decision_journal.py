from typing import Dict, List


def decision_rows(journal: Dict[str, object]) -> List[Dict[str, str]]:
    """Format decision timeline rows while leaving missing migrated fields explicit."""
    rows = []
    for item in journal.get("items", []):
        rows.append(
            {
                "编号": "#" + str(item.get("legacy_key", "未提供")),
                "日期": item.get("decision_date") or "未提供",
                "股票": item.get("symbol") or "未提供",
                "动作": item.get("action") or "未提供",
                "核心假设": item.get("thesis") or "未提供",
                "结果": item.get("outcome_text") or "未提供",
                "导入状态": _record_status_label(item.get("record_status")),
            }
        )
    return rows


def render_decision_journal(st, journal: Dict[str, object], submit_update, fetch_updates) -> None:
    """Render migrated decision evidence without generating investment advice."""
    st.subheader("决策日志")
    incomplete = journal.get("incomplete_import_count", 0)
    planned = journal.get("planned_record_count", 0)
    st.caption("已迁移 {} 条历史决策记录。页面仅用于研究复盘，不构成投资建议。".format(journal.get("total", 0)))
    if incomplete:
        st.warning("{} 条记录的原始格式无法完整自动迁移；请结合来源文件人工复核。".format(incomplete))
    if planned:
        st.info("{} 条为历史计划记录，未确认成交或执行。".format(planned))
    st.dataframe(decision_rows(journal), width="stretch", hide_index=True)
    for item in journal.get("items", []):
        label = "#{} · {} · {}".format(
            item.get("legacy_key", "未提供"), item.get("symbol") or "未提供", item.get("action") or "未提供"
        )
        with st.expander(label):
            st.caption(item.get("record_status_reason", "未提供"))
            st.caption("来源：{}".format(item.get("source_path") or "未提供"))
            _detail(st, "投资理由", item.get("investment_reason"))
            _detail(st, "核心假设", item.get("thesis"))
            _detail(st, "验证指标", item.get("validation_metrics"))
            _detail(st, "最大风险", item.get("maximum_risk"))
            _detail(st, "失效条件", item.get("invalid_conditions"))
            _detail(st, "预期时间", item.get("expected_horizon"))
            _detail(st, "实际结果", item.get("outcome_text"))
            render_update_history(st, item, fetch_updates)
            render_update_form(st, item, submit_update)


def render_update_history(st, item: Dict[str, object], fetch_updates) -> None:
    """Show user-authored follow-up events without altering the original decision."""
    try:
        history = fetch_updates(item["legacy_key"])
    except Exception as error:
        st.error("无法读取补录历史：{}".format(error))
        return
    if not history.get("items"):
        st.caption("尚无手动补录或复盘事件。")
        return
    st.markdown("**补录历史**")
    for update in history["items"]:
        st.caption("{} · {}{}".format(update.get("created_at"), update.get("event_type"), " · " + update["source_note"] if update.get("source_note") else ""))
        _detail(st, "实际结果", update.get("actual_result"))
        _detail(st, "复盘说明", update.get("review_notes"))


def render_update_form(st, item: Dict[str, object], submit_update) -> None:
    """Append a manually authored execution or review event."""
    with st.form("decision-update-{}".format(item["legacy_key"]), clear_on_submit=True):
        event_type = st.selectbox("事件类型", ["not_executed", "executed", "reviewed"], format_func=_event_type_label)
        execution_date = st.text_input("执行日期（可选）", placeholder="YYYY-MM-DD")
        execution_price = st.text_input("执行价格（可选）")
        actual_result = st.text_area("实际结果（可选）")
        review_notes = st.text_area("复盘说明（可选）")
        source_note = st.text_input("录入说明（可选）")
        submitted = st.form_submit_button("追加补录事件")
    if not submitted:
        return
    try:
        submit_update(item["legacy_key"], {
            "event_type": event_type, "execution_date": execution_date or None,
            "execution_price": execution_price or None, "actual_result": actual_result or None,
            "review_notes": review_notes or None, "source_note": source_note or None,
        })
    except Exception as error:
        st.error("无法保存补录事件：{}".format(error))
        return
    st.success("已追加补录事件。")
    st.rerun()


def _detail(st, label: str, value: object) -> None:
    st.markdown("**{}**：{}".format(label, value or "未提供"))


def _record_status_label(status: object) -> str:
    if status == "incomplete_import":
        return "导入不完整"
    if status == "planned_record":
        return "计划记录（未确认执行）"
    return "完整"


def _event_type_label(event_type: str) -> str:
    return {"not_executed": "未执行/未成交", "executed": "已执行", "reviewed": "复盘"}[event_type]
