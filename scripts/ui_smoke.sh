#!/bin/bash
set -euo pipefail

STREAMLIT_URL="${STREAMLIT_URL:-http://localhost:8501}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PWCLI="${PWCLI:-$PROJECT_ROOT/scripts/playwright_cli.sh}"

check_page() {
  local name="$1"
  local pattern="$2"
  if "$PWCLI" snapshot --raw | grep -q "$pattern"; then
    echo "OK $name"
  else
    echo "FAIL $name"
    exit 1
  fi
}

"$PWCLI" open "$STREAMLIT_URL" >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "晨报" "晨报"

"$PWCLI" click e24 >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "市场概览" "A 股市场状态"

"$PWCLI" click e30 >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "选股中心" "选股中心"

"$PWCLI" click e36 >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "股票详情" "财务指标（只读缓存）"

"$PWCLI" click e42 >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "投资逻辑" "投资逻辑追踪"

"$PWCLI" click e48 >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "决策日志" "决策日志"

"$PWCLI" click e54 >/dev/null
sleep 2
"$PWCLI" snapshot >/dev/null
check_page "组合与风险" "组合与风险"

"$PWCLI" close >/dev/null
echo "All Streamlit pages rendered."
