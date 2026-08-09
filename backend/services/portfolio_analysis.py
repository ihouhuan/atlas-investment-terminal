import json
import sqlite3
from typing import Dict, List

from backend.services.risk_budget import get_active_risk_budget


STRESS_SOURCE_PATH = "legacy/openclaw-atlas/stress_test/A股压力测试场景.md"


def build_portfolio_overview(connection: sqlite3.Connection) -> Dict[str, object]:
    """Summarize the latest persisted portfolio without creating trading actions."""
    snapshot = connection.execute(
        """
        SELECT id, as_of_date, currency, market_value, cash_value, source_path
        FROM portfolio_snapshots
        ORDER BY as_of_date DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    if snapshot is None:
        raise LookupError("No portfolio snapshot is available.")

    raw_positions = connection.execute(
        """
        SELECT stocks.symbol, stocks.name, stocks.sector, stocks.industry,
               portfolio_positions.shares, portfolio_positions.cost_price,
               portfolio_positions.current_price, portfolio_positions.market_value,
               portfolio_positions.pnl, portfolio_positions.pnl_pct,
               portfolio_positions.risk_level, portfolio_positions.dynamic_rating_json
        FROM portfolio_positions
        JOIN stocks ON stocks.id = portfolio_positions.stock_id
        WHERE portfolio_positions.snapshot_id = ?
        ORDER BY portfolio_positions.market_value DESC
        """,
        (snapshot["id"],),
    ).fetchall()
    market_value = float(snapshot["market_value"] or 0.0)
    cash_value = float(snapshot["cash_value"] or 0.0)
    total_value = market_value + cash_value
    positions = [_position_record(row, total_value) for row in raw_positions]
    budget = get_active_risk_budget(connection)
    violations = _risk_violations(positions, cash_value, total_value, budget)

    return {
        "as_of_date": snapshot["as_of_date"],
        "currency": snapshot["currency"],
        "summary": {
            "market_value": market_value,
            "cash_value": cash_value,
            "total_value": total_value,
            "cash_ratio": _ratio(cash_value, total_value),
            "unrealized_pnl": round(sum(position["pnl"] for position in positions), 2),
            "source_path": snapshot["source_path"],
        },
        "positions": positions,
        "industry_concentration": _industry_concentration(positions, total_value),
        "risk": {
            "budget": budget,
            "violation_count": len(violations),
            "violations": violations,
            "result_type": "rule_check",
        },
        "stress_tests": _stress_tests(positions, total_value),
        "research_integrity": _research_integrity(connection, positions),
    }


def _position_record(row: sqlite3.Row, total_value: float) -> Dict[str, object]:
    rating = json.loads(row["dynamic_rating_json"] or "{}")
    tier = _tier_for_rating(rating.get("rating"))
    market_value = float(row["market_value"] or 0.0)
    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "sector": row["sector"] or row["industry"] or "未分类",
        "industry": row["industry"],
        "shares": float(row["shares"] or 0.0),
        "cost_price": row["cost_price"],
        "current_price": row["current_price"],
        "market_value": market_value,
        "weight": _ratio(market_value, total_value),
        "pnl": float(row["pnl"] or 0.0),
        "pnl_pct": row["pnl_pct"],
        "risk_level": row["risk_level"],
        "dynamic_rating": rating,
        "tier": tier,
    }


def _tier_for_rating(rating: object) -> str:
    return {"LOW": "core", "MEDIUM": "growth", "HIGH": "thematic"}.get(
        str(rating), "thematic"
    )


def _risk_violations(
    positions: List[Dict[str, object]],
    cash_value: float,
    total_value: float,
    budget: Dict[str, object],
) -> List[Dict[str, object]]:
    violations: List[Dict[str, object]] = []
    tiers = budget["tiers"]
    for position in positions:
        maximum = tiers[position["tier"]]["single_stock_max"]
        if position["weight"] > maximum:
            violations.append(
                {
                    "type": "position_limit",
                    "symbol": position["symbol"],
                    "name": position["name"],
                    "actual": position["weight"],
                    "limit": maximum,
                    "message": "持仓权重超过 {} 仓位上限。".format(position["tier"]),
                }
            )
    minimum_cash = budget["portfolio"]["minimum_cash"]
    cash_ratio = _ratio(cash_value, total_value)
    if cash_ratio < minimum_cash:
        violations.append(
            {
                "type": "minimum_cash",
                "actual": cash_ratio,
                "limit": minimum_cash,
                "message": "现金比例低于风险预算最低要求。",
            }
        )
    return violations


def _industry_concentration(
    positions: List[Dict[str, object]], total_value: float
) -> List[Dict[str, object]]:
    values: Dict[str, float] = {}
    for position in positions:
        sector = str(position["sector"])
        values[sector] = values.get(sector, 0.0) + float(position["market_value"])
    return [
        {"sector": sector, "market_value": value, "weight": _ratio(value, total_value)}
        for sector, value in sorted(values.items(), key=lambda item: item[1], reverse=True)
    ]


def _stress_tests(
    positions: List[Dict[str, object]], total_value: float
) -> List[Dict[str, object]]:
    return [
        _stress_result(
            "沪深300 -20%",
            positions,
            total_value,
            lambda position: -0.20,
            "全组合按 -20% 冲击；对应旧场景的沪深300整体下跌假设。",
        ),
        _stress_result(
            "成长股估值压缩",
            positions,
            total_value,
            lambda position: -0.45 if position["tier"] == "thematic" else -0.05,
            "主题仓按 -45%、其余仓位按 -5% 冲击；为旧高估值成长股情景的透明映射。",
        ),
        _stress_result(
            "行业系统性回撤",
            positions,
            total_value,
            _sector_shock,
            "新能源按 -40%、资源/有色按 -25%；其他行业未覆盖时按 0% 冲击。",
        ),
    ]


def _stress_result(
    name: str,
    positions: List[Dict[str, object]],
    total_value: float,
    shock_for_position,
    assumption: str,
) -> Dict[str, object]:
    affected_value = 0.0
    estimated_loss = 0.0
    for position in positions:
        shock = shock_for_position(position)
        market_value = float(position["market_value"])
        if shock != 0:
            affected_value += market_value
        estimated_loss += market_value * shock
    return {
        "name": name,
        "result_type": "assumption",
        "estimated_loss": round(estimated_loss, 2),
        "estimated_loss_pct": _ratio(estimated_loss, total_value),
        "coverage_pct": _ratio(affected_value, total_value),
        "assumption": assumption,
        "source_path": STRESS_SOURCE_PATH,
        "limitations": "限制：结果基于历史情景假设，不预测市场，不包含相关性、流动性或交易成本。",
    }


def _sector_shock(position: Dict[str, object]) -> float:
    sector = str(position["sector"])
    if "新能源" in sector:
        return -0.40
    if "贵金属" in sector or "有色" in sector or "资源" in sector:
        return -0.25
    return 0.0


def _ratio(value: float, total: float) -> float:
    return round(value / total, 6) if total else 0.0


def _research_integrity(connection: sqlite3.Connection, positions: List[Dict[str, object]]) -> Dict[str, object]:
    symbols = [position["symbol"] for position in positions]
    placeholders = ", ".join("?" for _ in symbols)
    manual_theses = connection.execute(
        """
        SELECT stocks.symbol FROM stocks
        JOIN thesis_versions ON thesis_versions.id = (
            SELECT id FROM thesis_versions
            WHERE thesis_versions.stock_id = stocks.id
            ORDER BY thesis_versions.created_at DESC, thesis_versions.id DESC
            LIMIT 1
        )
        WHERE stocks.symbol IN ({})
        """.format(placeholders),
        symbols,
    ).fetchall()
    defined_symbols = {row["symbol"] for row in manual_theses}
    missing_thesis = [position for position in positions if position["symbol"] not in defined_symbols]
    planned_rows = connection.execute(
        """
        SELECT decisions.legacy_key, decisions.symbol, decisions.action
        FROM decisions
        LEFT JOIN decision_updates ON decision_updates.id = (
            SELECT id FROM decision_updates
            WHERE decision_updates.decision_id = decisions.id
            ORDER BY decision_updates.created_at DESC, decision_updates.id DESC
            LIMIT 1
        )
        WHERE decisions.symbol IN ({})
          AND decisions.action LIKE '计划%'
          AND decision_updates.id IS NULL
        """.format(placeholders),
        symbols,
    ).fetchall()
    items = [
        {"type": "missing_thesis", "symbol": position["symbol"], "name": position["name"], "message": "缺少手动定义的 Thesis、验证指标和失效条件。"}
        for position in missing_thesis
    ] + [
        {"type": "unconfirmed_plan", "symbol": row["symbol"], "legacy_key": row["legacy_key"], "message": "历史计划记录尚无执行或复盘补录。"}
        for row in planned_rows
    ]
    return {"missing_thesis_count": len(missing_thesis), "unconfirmed_plan_count": len(planned_rows), "items": items}
