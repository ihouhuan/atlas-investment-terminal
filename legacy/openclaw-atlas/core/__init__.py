#!/usr/bin/env python3
"""
Atlas Investment Core
=====================

Centralized utilities for the Atlas Investment Office.
All scripts should import from here, never redefine.

Modules:
    paths            - Path constants
    market_data      - yfinance wrappers
    reference_data   - Fallback data (KNOWN_*)
    risk_rules       - Position sizing rules (v10.5+ standard)

Usage:
    from core.paths import WORKSPACE_ROOT, daily_report_path
    from core.market_data import fetch_price_series
    from core.reference_data import KNOWN_DRAWDOWNS, KNOWN_CORRELATIONS
    from core.risk_rules import MAX_POSITION_BY_RISK, validate_position
"""

# Re-export commonly used items for convenience
from .paths import (
    WORKSPACE_ROOT,
    INVESTMENT_DIR,
    SCRIPTS_DIR,
    PORTFOLIO_FILE,
    DAILY_REPORTS_DIR,
    STRESS_TEST_REPORTS_DIR,
    PORTFOLIO_REPORTS_DIR,
    daily_report_path,
    stress_test_report_path,
    today_str,
)

from .market_data import (
    fetch_price_series,
    fetch_current_price,
    fetch_returns,
    fetch_ticker_info,
)

from .reference_data import (
    KNOWN_DRAWDOWNS,
    KNOWN_RECOVERY_TIMES,
    KNOWN_CORRELATIONS,
    RISK_CLUSTERS,
)

from .risk_rules import (
    MAX_POSITION_BY_RISK,
    MAX_SECTOR_PCT,
    MAX_THEME_PCT,
    MIN_CASH_PCT,
    MAX_LEVERAGE_PCT,
    DAILY_LOSS_TRIGGER_PCT,
    validate_position,
    validate_sector,
    validate_theme,
    validate_cash,
)