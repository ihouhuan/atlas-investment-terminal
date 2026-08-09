import json
import os
import sys
from pathlib import Path
from typing import Dict, List
from urllib.request import Request, urlopen
from urllib.parse import urlencode


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.pages.portfolio_risk import render_portfolio_risk
from app.pages.decision_journal import render_decision_journal
from app.pages.morning_brief import render_morning_brief
from app.pages.screener import render_screener
from app.pages.stock_detail import render_stock_detail
from app.pages.thesis import render_thesis_overview
from app.dashboard.ui import (
    change_tone,
    humanize_datetime,
    inject_theme,
    kpi_cards,
    section_title,
)


DEFAULT_API_URL = "http://127.0.0.1:8000"


def market_index_rows(overview: Dict[str, object]) -> List[Dict[str, str]]:
    """Convert API index data into presentation rows without inventing missing values."""
    rows: List[Dict[str, str]] = []
    for index in overview.get("indices", []):
        price = index.get("price")
        change_pct = index.get("change_pct")
        rows.append(
            {
                "指数": index.get("name", "未知"),
                "最新价": "数据不可用" if price is None else format(float(price), ",.2f"),
                "涨跌幅": "数据不可用"
                if change_pct is None
                else "{:+.2f}%".format(float(change_pct)),
                "状态": (
                    "历史缓存"
                    if index.get("status") == "available" and index.get("cached_at")
                    else "可用"
                    if index.get("status") == "available"
                    else "数据不可用"
                ),
                "来源": index.get("source") or "未提供",
                "时间": index.get("observed_at") or "未提供",
            }
        )
    return rows


def fetch_json(url: str, timeout: int = 12) -> Dict[str, object]:
    """Fetch a JSON API response for the dashboard."""
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: Dict[str, object]) -> Dict[str, object]:
    """Submit user-authored form data to the local API."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def patch_json(url: str, payload: Dict[str, object]) -> Dict[str, object]:
    """Update user-authored local data through the Atlas API."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="PATCH",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def run_dashboard() -> None:
    import streamlit as st

    st.set_page_config(page_title="Atlas Investment Terminal", page_icon="📈", layout="wide")
    inject_theme(st)
    st.title("Atlas Investment Terminal")
    st.caption("A 股研究终端 · 数据不可用时不显示估算值")

    api_url = os.environ.get("ATLAS_API_URL", DEFAULT_API_URL).rstrip("/")
    page = st.sidebar.radio("导航", ["晨报", "市场概览", "选股中心", "股票详情", "投资逻辑", "决策日志", "组合与风险"])
    if page == "晨报":
        try:
            brief = fetch_json(api_url + "/api/v1/morning-brief/overview", timeout=60)
            render_morning_brief(
                st,
                brief["market"],
                lambda: post_json(api_url + "/api/v1/market/refresh", {}),
                brief["portfolio"],
                brief["screener"],
                brief["open_actions"],
                lambda due_window: fetch_json(api_url + "/api/v1/morning-brief/actions?" + urlencode({"status": "open", "due_window": due_window})),
                brief["trend_7"],
                lambda days: fetch_json(api_url + "/api/v1/morning-brief/actions/trend?days={}".format(days)),
                lambda alert_key: fetch_json(api_url + "/api/v1/alerts/{}".format(alert_key)),
                lambda alert_key: post_json(api_url + "/api/v1/alerts/{}/acknowledgements".format(alert_key), {}),
                brief["delta"],
                brief["history"],
                lambda research_conclusion: post_json(
                    api_url + "/api/v1/morning-brief/snapshots",
                    {"research_conclusion": research_conclusion},
                ),
                lambda current_id, previous_id: fetch_json(
                    api_url + "/api/v1/morning-brief/delta?" + urlencode(
                        {"current_id": current_id, "previous_id": previous_id}
                    )
                ),
                lambda snapshot_id, reviewed, reviewed_at, review_notes: patch_json(
                    api_url + "/api/v1/morning-brief/snapshots/{}/review".format(snapshot_id),
                    {"reviewed": reviewed, "reviewed_at": reviewed_at, "review_notes": review_notes},
                ),
                brief["decisions"],
                lambda snapshot_id: fetch_json(api_url + "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot_id)),
                lambda snapshot_id, action_text, decision_key, due_date, priority: post_json(
                    api_url + "/api/v1/morning-brief/snapshots/{}/actions".format(snapshot_id),
                    {"action_text": action_text, "decision_legacy_key": decision_key, "due_date": due_date, "priority": priority},
                ),
                lambda snapshot_id, action_id, completed: patch_json(
                    api_url + "/api/v1/morning-brief/snapshots/{}/actions/{}".format(snapshot_id, action_id),
                    {"completed": completed},
                ),
            )
        except Exception as error:
            st.error("无法生成晨报：{}".format(error))
        return
    if page == "组合与风险":
        try:
            portfolio = fetch_json(api_url + "/api/v1/portfolio/overview")
            open_actions = fetch_json(api_url + "/api/v1/morning-brief/actions?status=open")
            action_trend = fetch_json(api_url + "/api/v1/morning-brief/actions/trend?days=7")
        except Exception as error:
            st.error("无法获取组合风险数据：{}".format(error))
            return
        render_portfolio_risk(
            st,
            portfolio,
            open_actions,
            lambda due_window: fetch_json(api_url + "/api/v1/morning-brief/actions?" + urlencode({"status": "open", "due_window": due_window})),
            action_trend,
            lambda days: fetch_json(api_url + "/api/v1/morning-brief/actions/trend?days={}".format(days)),
        )
        return
    if page == "股票详情":
        symbol = st.text_input("股票代码", value="000021.SZ").upper().strip()
        try:
            detail = fetch_json(api_url + "/api/v1/stocks/" + symbol)
        except Exception as error:
            st.error("无法获取股票详情：{}".format(error))
            return
        render_stock_detail(
            st,
            detail,
            lambda: post_json(
                api_url + "/api/v1/stocks/{}/financials/refresh".format(symbol), {}
            ),
        )
        return
    if page == "选股中心":
        st.sidebar.subheader("筛选条件")
        filters = {}
        if st.sidebar.checkbox("限制 PE TTM", value=False):
            filters["max_pe_ttm"] = st.sidebar.number_input("PE TTM 上限", min_value=0.0, value=30.0)
        if st.sidebar.checkbox("限制 PB", value=False):
            filters["max_pb"] = st.sidebar.number_input("PB 上限", min_value=0.0, value=3.0)
        if st.sidebar.checkbox("限制净利润同比", value=False):
            filters["min_profit_growth"] = st.sidebar.number_input("净利润同比下限（%）", value=20.0)
        if st.sidebar.checkbox("限制毛利率", value=False):
            filters["min_gross_margin"] = st.sidebar.number_input("毛利率下限（%）", value=20.0)
        sector = st.sidebar.text_input("行业主题（精确匹配）", value="").strip()
        if sector:
            filters["sector"] = sector
        try:
            result = fetch_json(api_url + "/api/v1/screener?" + urlencode(filters))
        except Exception as error:
            st.error("无法获取选股数据：{}".format(error))
            return
        render_screener(st, result)
        return
    if page == "投资逻辑":
        try:
            overview = fetch_json(api_url + "/api/v1/thesis")
        except Exception as error:
            st.error("无法获取投资逻辑记录：{}".format(error))
            return
        render_thesis_overview(
            st,
            overview,
            lambda payload: post_json(api_url + "/api/v1/thesis/versions", payload),
            lambda symbol: fetch_json(api_url + "/api/v1/thesis/{}/versions".format(symbol)),
        )
        return
    if page == "决策日志":
        try:
            journal = fetch_json(api_url + "/api/v1/decisions")
        except Exception as error:
            st.error("无法获取决策日志：{}".format(error))
            return
        render_decision_journal(
            st,
            journal,
            lambda legacy_key, payload: post_json(api_url + "/api/v1/decisions/{}/updates".format(legacy_key), payload),
            lambda legacy_key: fetch_json(api_url + "/api/v1/decisions/{}/updates".format(legacy_key)),
        )
        return

    try:
        overview = fetch_json(api_url + "/api/v1/market/overview", timeout=60)
    except Exception as error:
        st.error("无法连接 Atlas API：{}".format(error))
        st.code("uvicorn backend.api.app:app --reload")
        return

    section_title(st, "A 股市场状态", "行情与广度均保留来源、时间与历史缓存标记。")
    index_items = []
    for index in overview.get("indices", []):
        price = index.get("price")
        change = index.get("change_pct")
        index_items.append(
            {
                "label": index.get("name", "未知"),
                "value": "数据不可用" if price is None else format(float(price), ",.2f"),
                "note": "{} · {}".format(
                    index.get("source") or "未提供",
                    humanize_datetime(index.get("observed_at")),
                ),
                "tone": change_tone(change),
            }
        )
    kpi_cards(st, index_items)

    breadth = overview.get("breadth", {})
    if breadth.get("status") != "available":
        st.info("市场广度暂不可用：{}".format(breadth.get("reason", "未提供")))
    else:
        turnover = breadth.get("turnover_yi")
        kpi_cards(
            st,
            [
                {
                    "label": "上涨家数",
                    "value": breadth.get("advancers") if breadth.get("advancers") is not None else "数据不可用",
                    "tone": "up",
                },
                {
                    "label": "下跌家数",
                    "value": breadth.get("decliners") if breadth.get("decliners") is not None else "数据不可用",
                    "tone": "down",
                },
                {
                    "label": "涨停",
                    "value": breadth.get("limit_up") if breadth.get("limit_up") is not None else "数据不可用",
                    "tone": "up",
                },
                {
                    "label": "跌停",
                    "value": breadth.get("limit_down") if breadth.get("limit_down") is not None else "数据不可用",
                    "tone": "down",
                },
                {
                    "label": "成交额（亿）",
                    "value": "数据不可用" if turnover is None else format(float(turnover), ",.2f"),
                    "tone": "neutral",
                },
            ],
        )
        st.caption(
            "市场广度来源：{} · 时间：{} · {}".format(
                breadth.get("source") or "未提供",
                humanize_datetime(breadth.get("as_of")),
                "历史缓存" if breadth.get("cached_at") else "实时",
            )
        )
        breadth_chart = {}
        for label, key in (
            ("上涨", "advancers"),
            ("下跌", "decliners"),
            ("平盘", "unchanged"),
            ("涨停", "limit_up"),
            ("跌停", "limit_down"),
        ):
            value = breadth.get(key)
            if value is not None:
                breadth_chart[label] = value
        if breadth_chart:
            st.caption("市场广度结构（家数）")
            st.bar_chart(breadth_chart)

    st.subheader("股票池")
    try:
        watchlist = fetch_json(api_url + "/api/v1/watchlist?limit=20")
    except Exception as error:
        st.warning("股票池暂不可用：{}".format(error))
        return

    table_rows = []
    for item in watchlist.get("items", []):
        quote = item["quote"]
        table_rows.append(
            {
                "股票": item["name"],
                "代码": item["symbol"],
                "行业": item["industry"] or "未分类",
                "价格": quote["price"] if quote["price"] is not None else "数据不可用",
                "涨跌幅": quote["change_pct"] if quote["change_pct"] is not None else "数据不可用",
                "行情来源": quote["source"],
                "状态": (
                    "历史缓存"
                    if quote.get("cached_at") and quote["status"] == "available"
                    else quote["status"]
                ),
            }
        )
    st.caption("股票池共 {} 只；当前展示前 {} 只。".format(watchlist["total"], len(table_rows)))
    st.dataframe(table_rows, width="stretch", hide_index=True)


if __name__ == "__main__":
    run_dashboard()
