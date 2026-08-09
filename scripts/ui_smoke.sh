#!/bin/bash
set -euo pipefail

STREAMLIT_URL="${STREAMLIT_URL:-http://localhost:8501}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PWCLI="${PWCLI:-$PROJECT_ROOT/scripts/playwright_cli.sh}"

wait_for_page() {
  local name="$1"
  local pattern="$2"
  local timeout="${3:-30}"
  local waited=0
  while (( waited < timeout )); do
    if "$PWCLI" snapshot --raw | grep -q "$pattern"; then
      echo "OK $name"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  echo "FAIL $name (missing: $pattern)"
  "$PWCLI" snapshot --raw | tail -40
  return 1
}

"$PWCLI" open "$STREAMLIT_URL" >/dev/null
wait_for_page "晨报" "待完成行动项"

"$PWCLI" click e24 >/dev/null
wait_for_page "市场概览" "A 股市场状态"

"$PWCLI" click e30 >/dev/null
wait_for_page "选股中心" "候选股票"

"$PWCLI" click e36 >/dev/null
wait_for_page "股票详情" "财务指标（只读缓存）"

"$PWCLI" click e42 >/dev/null
wait_for_page "投资逻辑" "投资逻辑追踪"

"$PWCLI" click e48 >/dev/null
wait_for_page "决策日志" "已迁移"

"$PWCLI" click e54 >/dev/null
wait_for_page "组合与风险" "组合概览"

"$PWCLI" close >/dev/null
echo "All Streamlit pages rendered."
