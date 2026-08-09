#!/usr/bin/env python3
"""
Atlas Investment Core Risk Rules
=================================

CENTRALIZED risk budget rules (v10.5+ standard).

All risk-related scripts should import from here.
This is the SINGLE SOURCE OF TRUTH for position sizing rules.

Reference: investment/portfolio/risk_budget.md

Risk Levels:
    LOW    - Stable companies, defensive sectors, low beta
    MEDIUM - Standard growth, mainstream
    HIGH   - Speculative, high beta, unproven

Rules (2026-08-08 v10.5 unified):
    Single Stock Limits (by Risk):
        LOW Risk:    max 10% of portfolio
        MEDIUM Risk: max 5% of portfolio
        HIGH Risk:   max 2% of portfolio

    Sector Limits (universal):
        Any single sector: max 30%

    Theme Limits (universal):
        Any single theme (e.g., "AI"): max 40%

    Cash Floor:
        Minimum cash: 20%

    Leverage:
        BANNED: 0%

    Daily Loss Trigger:
        -3% triggers portfolio review/pause

Usage:
    from core.risk_rules import (
        MAX_POSITION_BY_RISK,
        MAX_SECTOR_PCT,
        MAX_THEME_PCT,
        MIN_CASH_PCT,
        MAX_LEVERAGE_PCT,
        DAILY_LOSS_TRIGGER_PCT,
    )
"""

# Position limits by risk level
MAX_POSITION_BY_RISK = {
    "LOW": 0.10,      # 10%
    "MEDIUM": 0.05,   # 5%
    "HIGH": 0.02,     # 2%
}

# Universal sector limit
MAX_SECTOR_PCT = 0.30  # 30%

# Universal theme limit
MAX_THEME_PCT = 0.40  # 40%

# Cash floor
MIN_CASH_PCT = 0.20  # 20%

# Leverage (always 0)
MAX_LEVERAGE_PCT = 0.0  # Banned

# Daily loss trigger (review/pause)
DAILY_LOSS_TRIGGER_PCT = -0.03  # -3%


def validate_position(position_pct: float, risk_level: str) -> tuple[bool, str]:
    """
    Validate a single position against risk rules.

    Args:
        position_pct: Current position size as decimal (e.g., 0.10 = 10%)
        risk_level: One of "LOW", "MEDIUM", "HIGH"

    Returns:
        Tuple of (is_valid, message)
    """
    if risk_level not in MAX_POSITION_BY_RISK:
        return False, f"Unknown risk level: {risk_level}"

    max_pct = MAX_POSITION_BY_RISK[risk_level]
    pct_100 = position_pct * 100

    if position_pct > max_pct:
        return False, (
            f"🔴 仓位违规: {pct_100:.2f}% > 上限 {max_pct*100:.0f}% "
            f"({risk_level} Risk)"
        )

    return True, f"✅ 合规: {pct_100:.2f}% ≤ {max_pct*100:.0f}% ({risk_level} Risk)"


def validate_sector(sector_pct: float) -> tuple[bool, str]:
    """Validate sector concentration."""
    if sector_pct > MAX_SECTOR_PCT:
        return False, f"🔴 行业集中违规: {sector_pct*100:.2f}% > {MAX_SECTOR_PCT*100:.0f}%"
    return True, f"✅ 合规: {sector_pct*100:.2f}% ≤ {MAX_SECTOR_PCT*100:.0f}%"


def validate_theme(theme_pct: float) -> tuple[bool, str]:
    """Validate theme concentration."""
    if theme_pct > MAX_THEME_PCT:
        return False, f"🔴 主题集中违规: {theme_pct*100:.2f}% > {MAX_THEME_PCT*100:.0f}%"
    return True, f"✅ 合规: {theme_pct*100:.2f}% ≤ {MAX_THEME_PCT*100:.0f}%"


def validate_cash(cash_pct: float) -> tuple[bool, str]:
    """Validate cash floor."""
    if cash_pct < MIN_CASH_PCT:
        return False, f"🔴 现金不足: {cash_pct*100:.2f}% < {MIN_CASH_PCT*100:.0f}%"
    return True, f"✅ 合规: {cash_pct*100:.2f}% ≥ {MIN_CASH_PCT*100:.0f}%"