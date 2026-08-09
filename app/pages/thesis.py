from typing import Dict, List

from app.dashboard.ui import kpi_cards, section_title


def thesis_rows(overview: Dict[str, object]) -> List[Dict[str, str]]:
    """Format persisted thesis items without presenting missing definitions as green."""
    rows = []
    for item in overview.get("items", []):
        rows.append(
            {
                "股票": item.get("name", "未知"),
                "代码": item.get("symbol", "未知"),
                "状态": "待定义" if item.get("status") == "needs_definition" else "已定义，待核验",
                "投资逻辑": item.get("thesis", "未提供"),
                "验证指标": item.get("validation_metrics") or "未提供",
                "失效条件": item.get("invalid_conditions") or "未提供",
                "下次复核": item.get("review_date") or "未设置",
                "来源": item.get("entry_source") or "未提供",
                "原因": item.get("status_reason", "未提供"),
            }
        )
    return rows


def render_thesis_overview(st, overview: Dict[str, object], submit_version, fetch_versions) -> None:
    """Render the thesis tracker as an evidence inventory rather than advice."""
    section_title(st, "投资逻辑追踪", "基于已留存持仓快照的 Thesis、验证指标与失效条件清单。")
    total = overview.get("total", 0)
    missing = overview.get("needs_definition_count", 0)
    kpi_cards(
        st,
        [
            {"label": "持仓数量", "value": total, "tone": "neutral"},
            {
                "label": "待定义",
                "value": missing,
                "tone": "warn" if missing else "good",
            },
            {
                "label": "已定义",
                "value": max(0, total - missing),
                "tone": "good",
            },
        ],
    )
    st.caption("基于 {} 份持仓快照；数据来源：{}".format(overview.get("as_of_date") or "未提供", overview.get("source_path") or "未提供"))
    if missing:
        st.warning("{} / {} 个持仓缺少可验证的投资逻辑、验证指标或失效条件。状态不代表交易建议。".format(missing, total))
    else:
        st.info("所有持仓均已记录投资逻辑；验证指标与失效条件仍须人工核验。")
    st.dataframe(thesis_rows(overview), width="stretch", hide_index=True)
    render_thesis_history(st, overview, fetch_versions)
    render_thesis_entry_form(st, overview, submit_version)


def render_thesis_history(st, overview: Dict[str, object], fetch_versions) -> None:
    """Show append-only manual records without conflating them with legacy snapshots."""
    for item in overview.get("items", []):
        symbol = item.get("symbol")
        with st.expander("{} · 版本历史".format(symbol or "未提供")):
            try:
                history = fetch_versions(symbol)
            except Exception as error:
                st.error("无法读取版本历史：{}".format(error))
                continue
            if not history.get("items"):
                st.caption("尚无手动 Thesis 版本；当前仅显示旧持仓快照。")
                continue
            for version in history["items"]:
                st.caption(
                    "{} · {}{}".format(
                        version.get("created_at") or "未提供",
                        version.get("entry_source") or "未提供",
                        " · " + version["source_note"] if version.get("source_note") else "",
                    )
                )
                st.markdown("**投资逻辑**：{}".format(version.get("thesis") or "未提供"))
                st.markdown("**验证指标**：{}".format(version.get("validation_metrics") or "未提供"))
                st.markdown("**失效条件**：{}".format(version.get("invalid_conditions") or "未提供"))
                st.markdown("**下次复核**：{}".format(version.get("review_date") or "未提供"))


def render_thesis_entry_form(st, overview: Dict[str, object], submit_version) -> None:
    """Collect only user-authored research fields and append them as a new version."""
    options = {
        "{} · {}".format(item.get("symbol", "未提供"), item.get("name", "未知")): item.get("symbol")
        for item in overview.get("items", [])
    }
    if not options:
        return
    with st.expander("新增 Thesis 版本（手动录入）"):
        st.caption("保存会追加新版本，不会覆盖任何旧记录。请基于自己的研究填写，不构成或生成交易指令。")
        with st.form("thesis-version-form", clear_on_submit=True):
            selected = st.selectbox("股票", list(options))
            thesis = st.text_area("投资逻辑", placeholder="一句可验证、可证伪的核心判断")
            validation_metrics = st.text_area("验证指标", placeholder="例如：季度产量、营收、毛利率等可观察指标")
            invalid_conditions = st.text_area("失效条件", placeholder="什么事实出现时需要重新评估该判断")
            review_date = st.text_input("下次复核日期", placeholder="YYYY-MM-DD")
            source_note = st.text_input("录入说明（可选）", placeholder="例如：首次手动记录 / 季度更新")
            submitted = st.form_submit_button("保存新版本")
        if not submitted:
            return
        payload = {
            "symbol": options[selected],
            "thesis": thesis,
            "validation_metrics": validation_metrics,
            "invalid_conditions": invalid_conditions,
            "review_date": review_date,
            "source_note": source_note or None,
        }
        try:
            submit_version(payload)
        except Exception as error:
            st.error("无法保存 Thesis 版本：{}".format(error))
            return
        st.success("已追加 Thesis 新版本。")
        st.rerun()
