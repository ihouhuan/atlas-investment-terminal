import html
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional


THEME_CSS = """
<style>
:root {
  --atlas-card: #ffffff;
  --atlas-border: #e3e8ee;
  --atlas-muted: #6b7280;
  --atlas-text: #1f2937;
  --atlas-up: #c62f4a;
  --atlas-down: #00966b;
}

[data-testid="stSidebar"] {
  background: #f1f4f8;
  border-right: 1px solid var(--atlas-border);
}

.block-container {
  max-width: 1440px;
  padding-top: 1.4rem;
  padding-bottom: 4rem;
}

h1 {
  font-size: 1.65rem !important;
  letter-spacing: 0 !important;
}

h3 {
  font-size: 1.05rem !important;
  letter-spacing: 0 !important;
}

[data-testid="stMetric"] {
  background: var(--atlas-card);
  border: 1px solid var(--atlas-border);
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
}

[data-testid="stMetricLabel"] p {
  color: var(--atlas-muted);
  font-size: 0.78rem;
}

[data-testid="stMetricValue"] {
  font-size: 1.25rem;
}

[data-testid="stDataFrame"] {
  font-size: 0.85rem;
}

.atlas-kpi {
  background: var(--atlas-card);
  border: 1px solid var(--atlas-border);
  border-radius: 8px;
  padding: 0.8rem 1rem;
  margin-bottom: 0.6rem;
}

.atlas-kpi-label {
  color: var(--atlas-muted);
  font-size: 0.78rem;
}

.atlas-kpi-value {
  font-size: 1.45rem;
  font-weight: 700;
  margin-top: 0.15rem;
}

.atlas-kpi-note {
  color: var(--atlas-muted);
  font-size: 0.75rem;
  margin-top: 0.25rem;
}

.atlas-pill {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.atlas-pill-good {
  background: #e6f6ef;
  color: #00966b;
}

.atlas-pill-warn {
  background: #fff3e0;
  color: #b76e00;
}

.atlas-pill-danger {
  background: #fdeaea;
  color: #c62f4a;
}

.atlas-pill-neutral {
  background: #eef1f4;
  color: #5f6b7a;
}

.up {
  color: var(--atlas-up);
}

.down {
  color: var(--atlas-down);
}

.neutral {
  color: var(--atlas-muted);
}

[data-testid="stAppDeployButton"] {
  display: none;
}

#MainMenu {
  display: none;
}

footer {
  display: none;
}
</style>
"""


def inject_theme(st) -> None:
    """Apply the Atlas visual shell once per Streamlit run."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def section_title(st, title: str, caption: Optional[str] = None) -> None:
    st.subheader(title)
    if caption:
        st.caption(caption)


def kpi_cards(st, items: List[Dict[str, object]]) -> None:
    """Render a compact row of KPI cards with an explicit tone."""
    if not items:
        return
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        label = html.escape(str(item.get("label") or ""))
        value = html.escape(str(item.get("value") or "数据不可用"))
        note = html.escape(str(item.get("note") or ""))
        tone = item.get("tone") or "neutral"
        column.markdown(
            '<div class="atlas-kpi">'
            '<div class="atlas-kpi-label">{}</div>'
            '<div class="atlas-kpi-value {}">{}</div>'
            '<div class="atlas-kpi-note">{}</div>'
            "</div>".format(label, tone, value, note),
            unsafe_allow_html=True,
        )


def status_pill(st, text: str, tone: str = "neutral") -> None:
    st.markdown(
        '<span class="atlas-pill atlas-pill-{}">{}</span>'.format(
            tone, html.escape(str(text))
        ),
        unsafe_allow_html=True,
    )


def humanize_amount(value: object, suffix: str = "元") -> str:
    if value is None:
        return "数据不可用"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(amount) >= 1e8:
        return "{:.2f} 亿".format(amount / 1e8)
    if abs(amount) >= 1e4:
        return "{:.2f} 万".format(amount / 1e4)
    return "{:,.2f} {}".format(amount, suffix)


def humanize_datetime(value: object) -> str:
    if value is None:
        return "未提供"
    text = str(value).strip()
    if not text:
        return "未提供"
    try:
        if re.fullmatch(r"\d{8}\d{6}", text):
            parsed = datetime.strptime(text, "%Y%m%d%H%M%S")
            if parsed.year == datetime.now().year:
                return parsed.strftime("%m-%d %H:%M")
            return parsed.strftime("%Y-%m-%d %H:%M")
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone()
        if local.year == datetime.now(timezone.utc).astimezone().year:
            return local.strftime("%m-%d %H:%M")
        return local.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return text


def status_label(status: object) -> str:
    labels = {
        "available": "可用",
        "unavailable": "不可用",
        "historical": "历史缓存",
        "cached": "历史缓存",
    }
    return labels.get(str(status), str(status))


def change_tone(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if number > 0:
        return "up"
    if number < 0:
        return "down"
    return "neutral"
