from typing import Dict, List


def build_morning_intelligence(
    market: Dict[str, object],
    portfolio: Dict[str, object],
    open_actions: Dict[str, object],
) -> Dict[str, object]:
    """Build a rule-based morning cockpit using only verified local data."""
    market_state = _market_state(market)
    portfolio_state = _portfolio_state(portfolio)
    focus_items = _focus_items(portfolio, open_actions)
    return {
        "market": market_state,
        "portfolio": portfolio_state,
        "focus": focus_items,
        "focus_count": len(focus_items),
        "source": "rule-based-intelligence-v1",
    }


def _market_state(market: Dict[str, object]) -> Dict[str, object]:
    indices = market.get("indices", [])
    changes = [
        float(item["change_pct"])
        for item in indices
        if item.get("change_pct") is not None
    ]
    breadth = market.get("breadth", {})
    advancers = breadth.get("advancers")
    decliners = breadth.get("decliners")
    limit_up = breadth.get("limit_up")
    limit_down = breadth.get("limit_down")

    reasons: List[str] = []
    if changes:
        average_change = sum(changes) / len(changes)
        reasons.append("指数均值 {:+.2f}%".format(average_change))
        for item in indices[:3]:
            if item.get("change_pct") is not None:
                reasons.append(
                    "{} {:+.2f}%".format(
                        item.get("name", "未知"),
                        float(item["change_pct"]),
                    )
                )
    if advancers is not None and decliners is not None:
        reasons.append("上涨 {} / 下跌 {}".format(advancers, decliners))
    if limit_up is not None and limit_down is not None:
        reasons.append("涨停 {} / 跌停 {}".format(limit_up, limit_down))

    if not reasons:
        return {
            "label": "数据不足",
            "tone": "neutral",
            "reasons": ["市场数据暂不可用，无法形成状态判断。"],
        }

    if advancers is not None and decliners is not None and changes:
        average_change = sum(changes) / len(changes)
        if advancers > decliners and average_change >= 0:
            label = "偏积极"
            tone = "good"
        elif decliners > advancers and average_change <= 0:
            label = "偏谨慎"
            tone = "danger"
        else:
            label = "中性"
            tone = "neutral"
    elif changes and sum(changes) / len(changes) >= 1.0:
        label = "偏积极"
        tone = "good"
    elif changes and sum(changes) / len(changes) <= -1.0:
        label = "偏谨慎"
        tone = "danger"
    else:
        label = "中性"
        tone = "neutral"

    return {"label": label, "tone": tone, "reasons": reasons[:5]}


def _portfolio_state(portfolio: Dict[str, object]) -> Dict[str, object]:
    risk = portfolio.get("risk", {})
    integrity = portfolio.get("research_integrity", {})
    summary = portfolio.get("summary", {})
    violation_count = risk.get("violation_count", 0)
    missing_thesis = integrity.get("missing_thesis_count", 0)
    cash_ratio = summary.get("cash_ratio", 0.0)

    reasons: List[str] = []
    if violation_count:
        reasons.append("{} 项风险预算违规".format(violation_count))
    if cash_ratio < 0.2:
        reasons.append("现金比例 {:.1%}，低于 20%".format(cash_ratio))
    if missing_thesis:
        reasons.append("{} 个持仓缺少 Thesis".format(missing_thesis))

    if violation_count and cash_ratio < 0.2:
        label = "高风险"
        tone = "danger"
    elif violation_count or missing_thesis:
        label = "需要关注"
        tone = "warn"
    else:
        label = "健康"
        tone = "good"

    return {"label": label, "tone": tone, "reasons": reasons[:5]}


def _focus_items(
    portfolio: Dict[str, object],
    open_actions: Dict[str, object],
) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    for violation in portfolio.get("risk", {}).get("violations", [])[:3]:
        items.append(
            {
                "symbol": violation.get("symbol"),
                "name": violation.get("name") or "组合风险",
                "kind": "风险违规",
                "message": violation.get("message") or "风险预算规则被触发。",
                "next_step": "复核仓位与风险预算",
                "tone": "danger",
            }
        )
    for integrity_item in portfolio.get("research_integrity", {}).get("items", [])[:3]:
        if integrity_item.get("type") != "missing_thesis":
            continue
        items.append(
            {
                "symbol": integrity_item.get("symbol"),
                "name": integrity_item.get("name") or "研究待办",
                "kind": "缺 Thesis",
                "message": integrity_item.get("message") or "缺少可验证研究逻辑。",
                "next_step": "补充 Thesis、验证指标与失效条件",
                "tone": "warning",
            }
        )
    for action in open_actions.get("items", [])[:3]:
        items.append(
            {
                "symbol": action.get("decision_legacy_key"),
                "name": "复盘待办",
                "kind": "行动项",
                "message": action.get("action_text") or "未填写行动项。",
                "next_step": "完成或复核该行动项",
                "tone": "warn",
            }
        )
    return items
