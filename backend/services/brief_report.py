from typing import Dict


def morning_brief_markdown(
    market: Dict[str, object],
    portfolio: Dict[str, object],
    screener: Dict[str, object],
    delta: Dict[str, object],
) -> str:
    """Generate a local archival snapshot from the same data shown in the brief."""
    lines = ["# Atlas 晨报", "", "## 市场", ""]
    for item in market.get("indices", []):
        price = "数据不可用" if item.get("price") is None else "{:.2f}".format(float(item["price"]))
        change = "数据不可用" if item.get("change_pct") is None else "{:+.2f}%".format(float(item["change_pct"]))
        lines.append("- {}：{}（{}；{}；{}）".format(item.get("name"), price, change, item.get("source") or "未提供", item.get("observed_at") or "未提供"))
    integrity = portfolio["research_integrity"]
    lines.extend(["", "## 研究待办", "", "- 缺少 Thesis：{}".format(integrity["missing_thesis_count"]), "- 未确认计划：{}".format(integrity["unconfirmed_plan_count"]), "- 风险预算违规：{}".format(portfolio["risk"]["violation_count"]), "", "## 风险变化摘要", ""])
    if delta.get("status") == "available":
        for row in brief_delta_rows(delta):
            lines.append("- {}：{}".format(row["项目"], row["变化"]))
    else:
        lines.append("- {}".format(delta.get("reason", "尚无可比较的本地晨报。")))
    lines.extend(["", "## 筛选候选（历史快照）", ""])
    for item in screener["items"][:10]:
        lines.append("- {}（{}）· {}".format(item["name"], item["symbol"], item["sector"] or "未分类"))
    return "\n".join(lines) + "\n"


def brief_delta_rows(delta: Dict[str, object]):
    """Format saved-brief deltas without treating reduced counts as resolved facts."""
    labels = (
        ("risk_violation_count", "风险预算违规"),
        ("missing_thesis_count", "缺少 Thesis"),
        ("unconfirmed_plan_count", "未确认计划"),
    )
    changes = delta.get("changes", {})
    rows = []
    for key, label in labels:
        change = int(changes.get(key, 0))
        if change > 0:
            description = "新增 {} 项".format(change)
        elif change < 0:
            description = "减少 {} 项".format(abs(change))
        else:
            description = "无变化"
        rows.append({"项目": label, "变化": description})
    return rows
