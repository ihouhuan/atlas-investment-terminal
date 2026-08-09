#!/usr/bin/env python3
"""
Atlas Investment Core Paths
============================

Centralized path constants for the Atlas Investment Office.
All scripts should import paths from here, never redefine.

设计原则：
- 所有报告目录使用中文名称（中国投资者习惯）
- 报告文件名使用中文名称（股票中文名 + 报告类型 + 日期）

Usage:
    from core.paths import WORKSPACE_ROOT, 投委会报告_DIR, ...
"""

import os

# Workspace root: /Users/huan/.openclaw/workspace
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
INVESTMENT_DIR = os.path.dirname(_CORE_DIR)

# Workspace root: parent of investment/
WORKSPACE_ROOT = os.path.dirname(INVESTMENT_DIR)

# Scripts directory: {INVESTMENT_ROOT}/scripts
SCRIPTS_DIR = os.path.join(INVESTMENT_DIR, "scripts")

# Portfolio file
PORTFOLIO_FILE = os.path.join(INVESTMENT_DIR, "portfolio", "portfolio.json")

# ==================== A 股报告目录（中文）====================
# 统一使用中文目录名，遵循中国投资者习惯

# A 股分析总目录
A股分析_DIR = os.path.join(INVESTMENT_DIR, 'A股分析')
os.makedirs(A股分析_DIR, exist_ok=True)

# 投委会报告（5 角色投票）
投委会报告_DIR = os.path.join(A股分析_DIR, '投委会报告')
os.makedirs(投委会报告_DIR, exist_ok=True)

# 个股研究
个股研究_DIR = os.path.join(A股分析_DIR, '个股研究')
os.makedirs(个股研究_DIR, exist_ok=True)

# 估值报告
估值报告_DIR = os.path.join(A股分析_DIR, '估值报告')
os.makedirs(估值报告_DIR, exist_ok=True)

# 压力测试
压力测试_DIR = os.path.join(A股分析_DIR, '压力测试')
os.makedirs(压力测试_DIR, exist_ok=True)

# A 股早盘简报
早盘简报_DIR = os.path.join(A股分析_DIR, '早盘简报')
os.makedirs(早盘简报_DIR, exist_ok=True)

# ==================== 其他中文目录 ====================
# 跨市场观察
跨市场观察_DIR = os.path.join(INVESTMENT_DIR, '跨市场观察')
os.makedirs(跨市场观察_DIR, exist_ok=True)

# 持仓与风控
持仓与风控_DIR = os.path.join(INVESTMENT_DIR, '持仓与风控')
os.makedirs(持仓与风控_DIR, exist_ok=True)

# 持仓报告
持仓报告_DIR = os.path.join(持仓与风控_DIR, '持仓报告')
os.makedirs(持仓报告_DIR, exist_ok=True)

# 情景分析
情景分析_DIR = os.path.join(持仓与风控_DIR, '情景分析')
os.makedirs(情景分析_DIR, exist_ok=True)

# 市场环境
市场环境_DIR = os.path.join(持仓与风控_DIR, '市场环境')
os.makedirs(市场环境_DIR, exist_ok=True)

# ==================== 兼容旧名（内部使用）====================
# 为不破坏现有代码逻辑，保留英文别名
DAILY_REPORTS_DIR = os.path.join(INVESTMENT_DIR, "reports", "daily")
os.makedirs(DAILY_REPORTS_DIR, exist_ok=True)

STRESS_TEST_REPORTS_DIR = 压力测试_DIR
PORTFOLIO_REPORTS_DIR = 持仓报告_DIR


def daily_report_path(filename: str) -> str:
    """Get full path for a daily report file."""
    return os.path.join(DAILY_REPORTS_DIR, filename)


def stress_test_report_path(filename: str) -> str:
    """Get full path for a stress test report file."""
    return os.path.join(STRESS_TEST_REPORTS_DIR, filename)


def today_str() -> str:
    """Get today's date string in YYYY-MM-DD format."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")