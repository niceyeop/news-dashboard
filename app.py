import streamlit as st
import requests
from bs4 import BeautifulSoup
from collections import Counter
from contextlib import closing
import re
import json
import html
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

# =========================
# 페이지 설정
# =========================
st.set_page_config(
    page_title="뉴스 트렌드 & 인사이트 대시보드",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

TARGET_PRESS = "국민일보"
AI_CACHE_VERSION = "minimal-fields-v1"
GEMINI_MODEL_NAME = "gemini-3.1-flash-lite"
REFRESH_INTERVAL_MINUTES = 10
UI_POLL_INTERVAL_MS = 15 * 1000
AI_CACHE_DIR = Path(os.getenv("NEWS_DASHBOARD_CACHE_DIR", ".news_dashboard_cache"))
AI_DB_PATH = AI_CACHE_DIR / "news_dashboard_cache.sqlite3"


# =========================
# 정치성향 매핑 (편의상 정적, 필요시 외부화)
# =========================
BIAS_MAP = {
    "국민일보": "C", "조선일보": "R", "동아일보": "R", "중앙일보": "R",
    "한국일보": "C", "경향신문": "L", "한겨레신문": "L", "세계일보": "C",
    "서울신문": "C", "문화일보": "C", "연합뉴스": "C", "뉴시스": "C",
    "매일경제": "C", "한국경제": "C",
}
BIAS_LABEL = {"L": "진보", "C": "중도", "R": "보수"}


# =========================
# 유틸 함수 (텍스트 정리·DB) — 기존 로직 유지
# =========================
def clean_model_text(text):
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r"^```json", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```html", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def is_probably_html(text):
    if not text:
        return False
    t = html.unescape(str(text)).strip().lower()
    return any(s in t for s in ["<div", "<span", "<p", "<br", "<small", "<a ", "<ul", "<li", "<section"])


def to_plain_display_text(value, prefer_after_label=None):
    if value is None:
        return ""
    text = html.unescape(clean_model_text(value))
    cut_points = [p for p in [
        text.lower().find("<div"),
        text.lower().find("&lt;div"),
        text.find("```"),
    ] if p != -1]
    if cut_points:
        text = text[:min(cut_points)]
    if is_probably_html(text) or re.search(r"</?[a-z][\s\S]*?>", text, flags=re.IGNORECASE):
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    text = re.sub(r"```(?:html|json)?", "", str(text), flags=re.IGNORECASE)
    text = text.replace("```", "")
    text = re.sub(r"</?[a-z][^>]*?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if prefer_after_label and prefer_after_label in text:
        text = text.split(prefer_after_label, 1)[1].strip()
    return text


def strip_embedded_card_text(value, fallback=""):
    text = to_plain_display_text(value)
    card_markers = ["summary", "importance", "???", "priority", "?? ?? ??",
                    "score-badge", "recommended-box"]
    original = html.unescape(str(value or ""))
    if is_probably_html(original) or any(m in text for m in card_markers):
        if "?? ???" in text:
            return text.split("?? ???", 1)[1].strip()
        if any(m in text for m in card_markers):
            return fallback
    return text


def has_embedded_markup(value):
    text = html.unescape(str(value or "")).lower()
    markers = ["<div", "</div", "<span", "</span", "<p", "</p", "<br",
               "<small", "</small", "<a ", "</a", "```", "score-badge",
               "recommended-box", "class=", "target='_blank'", 'target="_blank"']
    return any(m in text for m in markers)


def sanitize_ai_text(value, fallback=""):
    text = strip_embedded_card_text(value, fallback=fallback)
    if has_embedded_markup(text):
        return fallback
    return text


def sanitize_ai_payload(ai_data):
    if not isinstance(ai_data, dict):
        return ai_data
    summary = ai_data.get("dashboard_summary")
    if isinstance(summary, dict):
        for key in ["overall_trend", "editorial_note"]:
            summary[key] = sanitize_ai_text(summary.get(key, ""))
        clean_keywords = []
        for keyword in summary.get("top_keywords", []) or []:
            k = sanitize_ai_text(keyword)
            if k:
                clean_keywords.append(k)
        summary["top_keywords"] = clean_keywords
    for issue in ai_data.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue
        for key in ["issue_title", "category", "one_line_summary", "why_it_matters", "editor_comment"]:
            issue[key] = sanitize_ai_text(issue.get(key, ""))
        rec = issue.get("recommended_article")
        if isinstance(rec, dict):
            for key in ["media", "title", "reason"]:
                rec[key] = sanitize_ai_text(rec.get(key, ""))
        clean_rel = []
        for a in issue.get("related_articles", []) or []:
            if not isinstance(a, dict):
                continue
            a["media"] = sanitize_ai_text(a.get("media", ""))
            a["title"] = sanitize_ai_text(a.get("title", ""))
            clean_rel.append(a)
        issue["related_articles"] = clean_rel
    for item in ai_data.get("missed_articles", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ["issue_title", "category", "why_missed", "coverage_signal", "suggested_angle"]:
            item[key] = sanitize_ai_text(item.get(key, ""))
        clean_refs = []
        for a in item.get("reference_articles", []) or []:
            if not isinstance(a, dict):
                continue
            a["media"] = sanitize_ai_text(a.get("media", ""))
            a["title"] = sanitize_ai_text(a.get("title", ""))
            clean_refs.append(a)
        item["reference_articles"] = clean_refs
    return ai_data


def esc(value):
    return html.escape(to_plain_display_text(value))


def esc_safe(value, fallback=""):
    return html.escape(strip_embedded_card_text(value, fallback=fallback))


# =========================
# DB / Cache 헬퍼 — 기존 그대로
# =========================
def get_db_connection():
    AI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AI_DB_PATH), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_ai_store():
    with closing(get_db_connection()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_cache (
                cache_key TEXT PRIMARY KEY,
                refresh_slot TEXT NOT NULL,
                generated_at REAL NOT NULL,
                cache_version TEXT NOT NULL,
                model TEXT NOT NULL,
                data_json TEXT NOT NULL
            )
        """)


def get_cached_ai_result():
    init_ai_store()
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM ai_cache WHERE cache_key = 'latest'").fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row["data_json"])
    except Exception:
        data = None
    return {
        "refresh_slot": row["refresh_slot"],
        "generated_at": row["generated_at"],
        "cache_version": row["cache_version"],
        "model": row["model"],
        "data": data,
    }


def get_dashboard_stats():
    init_ai_store()
    stats = {
        "last_refresh_slot": "",
        "last_generated_at": None,
        "last_model": "",
        "today_ai_calls": 0,
    }
    with closing(get_db_connection()) as conn:
        cached_row = conn.execute(
            "SELECT refresh_slot, generated_at, model FROM ai_cache WHERE cache_key = 'latest'"
        ).fetchone()
        if cached_row:
            stats["last_refresh_slot"] = str(cached_row["refresh_slot"] or "")
            stats["last_generated_at"] = float(cached_row["generated_at"])
            stats["last_model"] = str(cached_row["model"] or "")
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'gemini_request_log'"
        ).fetchone()
        if table_exists:
            now = get_kst_now()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            day_end = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()
            stats["today_ai_calls"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM gemini_request_log WHERE ts >= ? AND ts < ?",
                    (day_start, day_end),
                ).fetchone()[0]
            )
    return stats


def format_timestamp(ts):
    if not ts:
        return "-"
    dt = datetime.fromtimestamp(float(ts), ZoneInfo("Asia/Seoul"))
    return dt.strftime("%m-%d %H:%M:%S")


def format_refresh_slot(slot_text):
    if not slot_text:
        return "-"
    return str(slot_text)[5:]


def get_kst_now():
    return datetime.now(ZoneInfo("Asia/Seoul"))


def get_current_refresh_slot():
    now = get_kst_now()
    slot_minute = (now.minute // REFRESH_INTERVAL_MINUTES) * REFRESH_INTERVAL_MINUTES
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return slot.strftime("%Y-%m-%dT%H:%M:%S%z")


# =========================
# 언론사 URL & 수집 — 기존 그대로
# =========================
URLS = {
    "국민일보": "https://media.naver.com/press/005",
    "조선일보": "https://media.naver.com/press/023",
    "동아일보": "https://media.naver.com/press/020",
    "중앙일보": "https://media.naver.com/press/025",
    "한국일보": "https://media.naver.com/press/469",
    "경향신문": "https://media.naver.com/press/032",
    "한겨레신문": "https://media.naver.com/press/028",
    "세계일보": "https://media.naver.com/press/022",
    "서울신문": "https://media.naver.com/press/081",
    "문화일보": "https://media.naver.com/press/021",
    "연합뉴스": "https://media.naver.com/press/001",
    "뉴시스": "https://media.naver.com/press/003",
    "매일경제": "https://media.naver.com/press/009",
    "한국경제": "https://media.naver.com/press/015",
}


def normalize_url(url):
    if not url:
        return None
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return "https://media.naver.com" + url
    return url


def collect_news():
    results = {}
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    for name, url in URLS.items():
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            articles = []
            for selector in [".press_news_text", ".cjs_t"]:
                if articles:
                    break
                for node in soup.select(selector):
                    title = node.get_text(strip=True)
                    if not title:
                        continue
                    a_tag = node.find_parent("a")
                    article_url = normalize_url(a_tag.get("href")) if a_tag else None
                    if title not in [a["title"] for a in articles]:
                        articles.append({"title": title, "url": article_url})
            if not articles:
                for a_tag in soup.select("a[href*='/article/']"):
                    title = a_tag.get_text(" ", strip=True)
                    article_url = normalize_url(a_tag.get("href"))
                    if len(title) >= 8 and title not in [a["title"] for a in articles]:
                        articles.append({"title": title, "url": article_url})
            results[name] = articles[:6]
        except Exception:
            results[name] = [{"title": "데이터를 불러올 수 없습니다.", "url": None}]
    return results


@st.cache_data
def fetch_news(refresh_slot):
    return collect_news()


def get_stored_ai_insight():
    cached_result = get_cached_ai_result()
    if isinstance(cached_result, dict) and cached_result.get("data"):
        return cached_result["data"]
    return {
        "error": "저장된 AI 분석 결과가 아직 없습니다. 별도 스케줄러가 DB를 갱신한 뒤 표시됩니다.",
        "raw": None,
    }


# =========================
# 분석 헬퍼 (V2 시각화용)
# =========================
def compute_issue_heat(issue):
    """AI scores(1~5) 평균을 0~100 heat로 환산."""
    scores = issue.get("scores") or {}
    vals = [scores.get(k) for k in ("importance", "virality", "reader_interest", "freshness")]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return 70
    avg = sum(vals) / len(vals)
    return max(10, min(100, int(round(avg * 20))))


def compute_issue_coverage(issue):
    """related_articles 길이를 보도 매체수 근사로 사용 (최대 14)."""
    rel = issue.get("related_articles") or []
    return min(14, len(rel))


def compute_heatmap(issues, news_data):
    """이슈 × 언론사 보도 매트릭스. 키워드 매칭 기반 (0~3 강도)."""
    matrix = []
    for issue in issues:
        title = issue.get("issue_title", "")
        kws = [w for w in re.split(r"[\s,·]+", title) if len(w) > 1]
        row = []
        for press_name in URLS.keys():
            arts = news_data.get(press_name, [])
            hits = 0
            for a in arts:
                t = a.get("title", "")
                if not t:
                    continue
                for k in kws:
                    if k in t:
                        hits += 1
            row.append(min(3, hits))
        matrix.append(row)
    return matrix


def compute_keyword_freq(news_data, keywords, limit=10):
    """선정된 키워드들이 14개사 헤드라인에서 몇 회 등장했는지."""
    freq = []
    for kw in keywords[:limit]:
        n = 0
        for arts in news_data.values():
            for a in arts:
                if kw in (a.get("title") or ""):
                    n += 1
        freq.append((kw, n))
    freq.sort(key=lambda x: -x[1])
    return freq


def total_headlines(news_data):
    return sum(len(v) for v in news_data.values())


def topic_palette_class(category):
    """카테고리 → CSS class 매핑."""
    if not category:
        return "cat-default"
    c = category.strip()
    if c in ("경제", "생활"):
        return "cat-econ"
    if c in ("정치", "국제"):
        return "cat-poli"
    if c in ("사회",):
        return "cat-soci"
    if c in ("문화", "IT·과학", "연예", "스포츠", "오피니언", "기타"):
        return "cat-cult"
    return "cat-default"


# =========================
# CSS — V2 Signal Terminal (Light)
# =========================
V2_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
  /* Streamlit chrome 최소화 */
  #MainMenu, footer, header { visibility: hidden; }
  .main .block-container { padding: 0 !important; max-width: 100% !important; }
  .stApp { background: #f5f3ee; }
  div[data-testid="stToolbar"] { display: none; }
  section[data-testid="stSidebar"] { display: none; }

  :root {
    --bg:#f5f3ee; --panel:#ffffff; --panel-2:#eceae3; --line:#dfdcd1;
    --line-2:#c9c5b8; --ink:#1a1814; --ink-2:#5d5749; --ink-3:#8d8676;
    --green:#2f7d5a; --amber:#a06913; --red:#a8493a; --blue:#2c64a0; --violet:#5d4694;
  }

  .v2 { font-family:'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
    background:var(--bg); color:var(--ink); font-size:13px; line-height:1.5;
    letter-spacing:-0.005em; }
  .v2 .mono, .v2 [class*="mono"] { font-family:'JetBrains Mono', ui-monospace, monospace; letter-spacing:0; }

  /* Top nav */
  .v2 .topnav { display:flex; justify-content:space-between; align-items:center;
    padding:10px 28px; border-bottom:1px solid var(--line-2); background:var(--panel);
    font-family:'JetBrains Mono', monospace; }
  .v2 .topnav .left { display:flex; align-items:center; gap:24px; }
  .v2 .logo { font-size:11px; letter-spacing:0.22em; color:var(--green); font-weight:600; }
  .v2 .logo::before { content:"● "; }
  .v2 .nav-tabs { display:flex; gap:1px; background:var(--line); padding:1px; border-radius:2px; }
  .v2 .nav-tab { padding:5px 12px; font-size:10px; letter-spacing:0.12em; color:var(--ink-2);
    background:var(--bg); }
  .v2 .nav-tab.active { background:var(--green); color:#fff; }
  .v2 .status-bar { display:flex; align-items:center; gap:20px; font-size:11px; color:var(--ink-2); }
  .v2 .status-bar .live { color:var(--green); }
  .v2 .status-bar .live::before { content:"◉ "; animation:v2blink 2s infinite; }
  @keyframes v2blink { 0%,49%{opacity:1} 50%,100%{opacity:0.3} }

  /* Header block */
  .v2 .header-block { padding:32px 28px 26px; border-bottom:1px solid var(--line-2);
    display:grid; grid-template-columns:1.4fr 1fr; gap:36px; background:var(--bg); }
  .v2 .pre-title { font-family:'JetBrains Mono', monospace; font-size:10px;
    letter-spacing:0.2em; color:var(--ink-3); margin-bottom:14px; }
  .v2 .header-title { font-size:34px; font-weight:700; letter-spacing:-0.025em;
    line-height:1.15; color:var(--ink); margin:0; }
  .v2 .header-title .accent { color:var(--green); }
  .v2 .header-sub { font-size:13px; color:var(--ink-2); margin-top:12px;
    line-height:1.55; max-width:680px; }
  .v2 .header-sub .base { color:var(--amber); font-weight:600; }

  .v2 .metric-strip { display:grid; grid-template-columns:repeat(4, 1fr); gap:1px;
    background:var(--line-2); border:1px solid var(--line-2); align-self:start; border-radius:3px;
    overflow:hidden; }
  .v2 .metric { background:var(--panel); padding:14px 14px; font-family:'JetBrains Mono', monospace; }
  .v2 .metric .lbl { font-size:9px; letter-spacing:0.16em; color:var(--ink-3); text-transform:uppercase; }
  .v2 .metric .val { font-size:20px; color:var(--ink); margin-top:6px; font-weight:500; }
  .v2 .metric .val.green { color:var(--green); }
  .v2 .metric .val.amber { color:var(--amber); }
  .v2 .metric .val .dim { color:var(--ink-3); font-size:13px; font-weight:400; }
  .v2 .metric .sub { font-size:10px; color:var(--ink-3); margin-top:3px; }

  /* Panels */
  .v2 .grid-2 { display:grid; grid-template-columns:1fr 380px; gap:1px;
    background:var(--line-2); }
  .v2 .panel { background:var(--bg); padding:22px 28px; }
  .v2 .panel-head { display:flex; justify-content:space-between; align-items:center;
    margin-bottom:16px; padding-bottom:10px; border-bottom:1px dashed var(--line-2); }
  .v2 .panel-head h2 { margin:0; font-size:15px; letter-spacing:-0.005em; color:var(--ink); font-weight:700; }
  .v2 .panel-head .meta { font-family:'JetBrains Mono', monospace; font-size:10px;
    color:var(--ink-3); letter-spacing:0.12em; }

  /* AI flow */
  .v2 .flow-text { font-size:15px; line-height:1.65; color:var(--ink); padding:6px 0 14px;
    font-weight:500; }
  .v2 .flow-text .hl { background:rgba(47,125,90,0.12); color:var(--green);
    padding:1px 4px; border-radius:2px; font-weight:600; }
  .v2 .ed-row { display:flex; gap:14px; padding:14px; background:var(--panel);
    border-left:2px solid var(--amber); border-radius:0 4px 4px 0;
    font-size:12px; color:var(--ink-2); line-height:1.55; }
  .v2 .ed-row .badge { font-family:'JetBrains Mono', monospace; font-size:9px;
    color:var(--amber); letter-spacing:0.16em; flex:0 0 auto; padding-top:2px; font-weight:600; }

  /* Keyword bars */
  .v2 .kw-rows { display:flex; flex-direction:column; gap:7px; }
  .v2 .kw-row { display:grid; grid-template-columns:90px 1fr 28px; gap:10px;
    align-items:center; font-size:12px; }
  .v2 .kw-row .name { color:var(--ink); }
  .v2 .kw-row.t1 .name { color:var(--green); font-weight:600; }
  .v2 .kw-row.t2 .name { color:var(--amber); font-weight:500; }
  .v2 .kw-row .bar { height:8px; background:var(--panel-2); border-radius:1px; overflow:hidden; }
  .v2 .kw-row .bar .fill { height:100%; background:var(--ink-3); }
  .v2 .kw-row.t1 .bar .fill { background:var(--green); }
  .v2 .kw-row.t2 .bar .fill { background:var(--amber); }
  .v2 .kw-row .n { font-family:'JetBrains Mono', monospace; color:var(--ink-2); text-align:right; font-size:11px; }

  /* Issue cards 3x2 */
  .v2 .iss-grid { display:grid; grid-template-columns:repeat(3, 1fr); grid-auto-rows:1fr; gap:14px; }
  .v2 .iss-card { background:var(--panel); border:1px solid var(--line); border-radius:4px;
    padding:22px 24px; display:flex; flex-direction:column; gap:12px; position:relative;
    overflow:hidden; min-height:240px; }
  .v2 .iss-card .topic-block { position:absolute; right:0; top:0; bottom:0; width:3px; }
  .v2 .iss-card.cat-econ .topic-block { background:var(--amber); }
  .v2 .iss-card.cat-poli .topic-block { background:var(--blue); }
  .v2 .iss-card.cat-soci .topic-block { background:var(--red); }
  .v2 .iss-card.cat-cult .topic-block { background:var(--violet); }
  .v2 .iss-card.cat-default .topic-block { background:var(--ink-3); }
  .v2 .iss-card .iss-head { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; }
  .v2 .iss-card .iss-meta { display:flex; flex-direction:column; gap:8px; }
  .v2 .iss-card .rank { font-family:'JetBrains Mono', monospace; font-size:10px;
    color:var(--ink-3); letter-spacing:0.16em; }
  .v2 .iss-card .topic-pill { font-family:'JetBrains Mono', monospace; font-size:9px;
    letter-spacing:0.14em; padding:3px 8px; align-self:flex-start;
    border:1px solid currentColor; border-radius:2px; text-transform:uppercase; }
  .v2 .iss-card.cat-econ .topic-pill { color:var(--amber); }
  .v2 .iss-card.cat-poli .topic-pill { color:var(--blue); }
  .v2 .iss-card.cat-soci .topic-pill { color:var(--red); }
  .v2 .iss-card.cat-cult .topic-pill { color:var(--violet); }
  .v2 .iss-card.cat-default .topic-pill { color:var(--ink-3); }
  .v2 .iss-card h3 { margin:0; font-size:17px; line-height:1.4; font-weight:700;
    letter-spacing:-0.015em; color:var(--ink); }
  .v2 .iss-card p { margin:0; font-size:12.5px; color:var(--ink-2); line-height:1.55; }
  .v2 .iss-card .why { font-size:11px; color:var(--ink-3); line-height:1.55;
    padding-top:10px; border-top:1px dashed var(--line); margin-top:auto; }
  .v2 .iss-card .why::before { content:"WHY  "; color:var(--green);
    font-family:'JetBrains Mono', monospace; font-size:9px; letter-spacing:0.16em; font-weight:600; }
  .v2 .iss-card .metrics { display:flex; gap:20px; padding-top:10px; border-top:1px dashed var(--line); }
  .v2 .iss-card .m-lbl { font-family:'JetBrains Mono', monospace; font-size:9px;
    letter-spacing:0.14em; color:var(--ink-3); text-transform:uppercase; }
  .v2 .iss-card .m-val { font-family:'JetBrains Mono', monospace; font-size:17px;
    color:var(--ink); margin-top:2px; font-weight:500; }
  .v2 .iss-card .m-val .dim { color:var(--ink-3); font-size:11px; }

  /* Heat arc */
  .v2 .heat-arc { width:56px; height:56px; flex-shrink:0; position:relative; }
  .v2 .heat-arc svg { transform:rotate(-90deg); display:block; }
  .v2 .heat-arc .num { position:absolute; inset:0; display:flex; align-items:center;
    justify-content:center; font-family:'JetBrains Mono', monospace; font-size:13px;
    font-weight:600; color:var(--ink); }

  /* Heatmap matrix */
  .v2 .hm { display:grid; grid-template-columns:220px repeat(14, 1fr); gap:2px; }
  .v2 .hm .corner { padding:0 8px 4px 0; font-family:'JetBrains Mono', monospace;
    font-size:9px; letter-spacing:0.14em; color:var(--ink-3); text-transform:uppercase; align-self:end; }
  .v2 .hm .h-press { font-size:10px; color:var(--ink-2); writing-mode:vertical-rl;
    transform:rotate(180deg); padding:6px 0; text-align:right; align-self:end;
    height:90px; }
  .v2 .hm .h-press.base { color:var(--amber); font-weight:700; }
  .v2 .hm .iss-label { font-size:11.5px; color:var(--ink); padding:6px 12px 6px 0;
    display:flex; align-items:center; gap:8px; line-height:1.3; }
  .v2 .hm .iss-label .num { color:var(--green); font-family:'JetBrains Mono', monospace; font-weight:600; }
  .v2 .hm .cell { aspect-ratio:1; background:var(--panel); display:flex; align-items:center;
    justify-content:center; font-family:'JetBrains Mono', monospace; font-size:9px;
    color:var(--ink-3); border-radius:2px; }
  .v2 .hm .cell.l1 { background:rgba(47,125,90,0.14); color:var(--green); }
  .v2 .hm .cell.l2 { background:rgba(47,125,90,0.42); color:var(--ink); }
  .v2 .hm .cell.l3 { background:var(--green); color:#fff; font-weight:600; }

  /* Missed alerts */
  .v2 .alerts { display:flex; flex-direction:column; gap:1px; background:var(--line-2);
    border:1px solid var(--line-2); border-radius:3px; overflow:hidden; }
  .v2 .alert { padding:16px 22px; background:var(--panel); border-left:3px solid var(--red);
    display:grid; grid-template-columns:120px 1fr; gap:20px; }
  .v2 .alert .alert-tag { font-family:'JetBrains Mono', monospace; font-size:10px;
    color:var(--red); letter-spacing:0.18em; font-weight:700; }
  .v2 .alert .alert-tag::before { content:"▲ "; }
  .v2 .alert .alert-title { font-size:15px; font-weight:700; color:var(--ink);
    margin-bottom:8px; letter-spacing:-0.015em; }
  .v2 .alert .alert-meta { font-size:11.5px; color:var(--ink-2); line-height:1.55; }
  .v2 .alert .alert-meta + .alert-meta { margin-top:4px; }
  .v2 .alert .alert-meta .lbl { color:var(--ink-3); margin-right:8px;
    font-family:'JetBrains Mono', monospace; font-size:9px; letter-spacing:0.14em; text-transform:uppercase; }

  /* Press table */
  .v2 .press-table { display:grid; grid-template-columns:repeat(2, 1fr); gap:1px;
    background:var(--line-2); border:1px solid var(--line-2); border-radius:3px; overflow:hidden; }
  .v2 .press-col { background:var(--panel); }
  .v2 .press-col .pr { display:grid; grid-template-columns:24px 1fr 60px 40px;
    padding:10px 16px; align-items:center; border-bottom:1px solid var(--line);
    background:var(--panel-2); }
  .v2 .press-col .pr .nm { font-size:14px; color:var(--ink); font-weight:700;
    letter-spacing:-0.01em; display:flex; align-items:center; gap:8px; }
  .v2 .press-col .pr .nm .basebadge { font-size:8px; padding:2px 6px; background:var(--amber);
    color:#fff; font-family:'JetBrains Mono', monospace; letter-spacing:0.1em; font-weight:700;
    border-radius:1px; }
  .v2 .press-col .pr .bias-mini { font-family:'JetBrains Mono', monospace; font-size:9px;
    letter-spacing:0.1em; padding:3px 6px; text-align:center; border-radius:1px; font-weight:600; }
  .v2 .press-col .pr .bias-mini.L { color:var(--blue); border:1px solid var(--blue); }
  .v2 .press-col .pr .bias-mini.R { color:var(--red); border:1px solid var(--red); }
  .v2 .press-col .pr .bias-mini.C { color:var(--ink-3); border:1px solid var(--line-2); }
  .v2 .press-col .pr .stcount { font-family:'JetBrains Mono', monospace; font-size:10px;
    color:var(--ink-2); text-align:right; }
  .v2 .press-col .lead { padding:10px 16px 16px 16px; display:flex; flex-direction:column; gap:6px; }
  .v2 .press-col .st { font-size:12px; line-height:1.45; color:var(--ink);
    display:flex; gap:8px; align-items:flex-start; }
  .v2 .press-col .st .bullet { color:var(--green); flex:0 0 auto; font-size:10px; padding-top:2px; }
  .v2 .press-col .st.bk { color:var(--red); font-weight:500; }
  .v2 .press-col .st.bk .bullet { color:var(--red); }
  .v2 .press-col .st a { color:inherit; text-decoration:none; }
  .v2 .press-col .st a:hover { text-decoration:underline; }
  .v2 .press-col .st.empty { color:var(--ink-3); font-style:italic; }

  /* Section divider */
  .v2 .sec-div { height:1px; background:var(--line-2); }

  /* Reduce default Streamlit gaps around our HTML chunks */
  div[data-testid="stMarkdownContainer"] { line-height:1.5; }
</style>
"""


# =========================
# 렌더링 — HTML 빌더
# =========================
def heat_arc_svg(value, size=56):
    """SVG 도넛 게이지 (heat 0~100)."""
    import math
    r = (size / 2) - 4
    c = 2 * math.pi * r
    if value > 85:
        color = "var(--red)"
    elif value > 70:
        color = "var(--amber)"
    else:
        color = "var(--green)"
    dash = c - (c * value / 100)
    return (
        f'<div class="heat-arc" style="width:{size}px;height:{size}px;">'
        f'<svg width="{size}" height="{size}">'
        f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="rgba(0,0,0,0.08)" stroke-width="3"/>'
        f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="3" '
        f'stroke-dasharray="{c:.2f}" stroke-dashoffset="{dash:.2f}" stroke-linecap="round"/>'
        f'</svg>'
        f'<div class="num">{value}</div>'
        f'</div>'
    )


def render_topnav(stats):
    slot = format_refresh_slot(stats.get("last_refresh_slot") or "")
    return f"""
    <div class="topnav">
      <div class="left">
        <span class="logo">NEWSDESK · TERMINAL</span>
        <span class="nav-tabs">
          <span class="nav-tab active">DASHBOARD</span>
          <span class="nav-tab">ISSUES</span>
          <span class="nav-tab">COVERAGE</span>
          <span class="nav-tab">KEYWORDS</span>
          <span class="nav-tab">ARCHIVE</span>
        </span>
      </div>
      <div class="status-bar">
        <span class="live">LIVE</span>
        <span>SLOT {html.escape(slot)}</span>
        <span>POLL {UI_POLL_INTERVAL_MS // 1000}s</span>
      </div>
    </div>
    """


def render_header(stats, ai_data, news_data):
    today = get_kst_now()
    issues = (ai_data or {}).get("issues") or []
    missed = (ai_data or {}).get("missed_articles") or []
    heats = [compute_issue_heat(i) for i in issues] or [0]
    avg_heat = sum(heats) / max(1, len(heats))

    bias_count = Counter(BIAS_MAP.get(p, "C") for p in URLS.keys())
    bias_summary = f"L {bias_count.get('L', 0)} · C {bias_count.get('C', 0)} · R {bias_count.get('R', 0)}"

    last_analysis = format_timestamp(stats.get("last_generated_at"))
    model = html.escape(stats.get("last_model") or "-")
    calls = int(stats.get("today_ai_calls", 0))

    return f"""
    <div class="header-block">
      <div>
        <div class="pre-title">DAILY BRIEF · {today.strftime('%Y.%m.%d · %a').upper()}</div>
        <h1 class="header-title">오늘의 <span class="accent">시그널</span></h1>
        <div class="header-sub">
          14개 주요 언론사의 네이버 뉴스 헤드라인을 AI가 분석해 핵심 이슈, 키워드 분포,
          우리가 놓친 기사를 추출합니다. <span class="base">기준 매체: {TARGET_PRESS}</span>
        </div>
      </div>
      <div class="metric-strip">
        <div class="metric">
          <div class="lbl">Tracked</div>
          <div class="val">14<span class="dim"> outlets</span></div>
          <div class="sub">{bias_summary}</div>
        </div>
        <div class="metric">
          <div class="lbl">Issues</div>
          <div class="val green">{len(issues):02d}</div>
          <div class="sub">avg heat {avg_heat:.1f}</div>
        </div>
        <div class="metric">
          <div class="lbl">Missed</div>
          <div class="val amber">{len(missed):02d}</div>
          <div class="sub">vs. {TARGET_PRESS}</div>
        </div>
        <div class="metric">
          <div class="lbl">AI Calls</div>
          <div class="val">{calls}<span class="dim">/400</span></div>
          <div class="sub">{html.escape(last_analysis)}</div>
        </div>
      </div>
    </div>
    """


def render_flow_and_keywords(ai_data, news_data, stats):
    summary = (ai_data or {}).get("dashboard_summary") or {}
    overall = summary.get("overall_trend") or ""
    editorial = summary.get("editorial_note") or ""
    top_keywords = summary.get("top_keywords") or []

    # 키워드 강조 (앞 3개를 본문에서 하이라이트)
    overall_html = esc(overall) if overall else "분석 결과를 불러오는 중입니다."
    for kw in top_keywords[:3]:
        if not kw:
            continue
        safe_kw = html.escape(kw)
        overall_html = overall_html.replace(safe_kw, f'<span class="hl">{safe_kw}</span>', 1)

    # 키워드 빈도
    freq = compute_keyword_freq(news_data, top_keywords or [], limit=10)
    if freq:
        max_n = max(n for _, n in freq) or 1
    else:
        max_n = 1
    kw_rows = []
    for i, (kw, n) in enumerate(freq):
        klass = "t1" if i < 2 else ("t2" if i < 4 else "")
        pct = (n / max_n) * 100
        kw_rows.append(
            f'<div class="kw-row {klass}">'
            f'  <span class="name">{html.escape(kw)}</span>'
            f'  <span class="bar"><span class="fill" style="width:{pct:.1f}%"></span></span>'
            f'  <span class="n">{n:02d}</span>'
            f'</div>'
        )
    if not kw_rows:
        kw_rows = ['<div style="color:var(--ink-3);font-size:11px;">키워드 데이터 없음</div>']

    last_analysis = format_timestamp(stats.get("last_generated_at"))
    n_headlines = total_headlines(news_data)

    return f"""
    <div class="grid-2">
      <div class="panel">
        <div class="panel-head">
          <h2>AI 에디터 · 오늘의 흐름</h2>
          <span class="meta">UPDATED {html.escape(last_analysis)}</span>
        </div>
        <div class="flow-text">{overall_html}</div>
        <div class="ed-row">
          <span class="badge">EDIT<br>NOTE</span>
          <span>{esc_safe(editorial, fallback="편집 코멘트가 아직 준비되지 않았습니다.")}</span>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">
          <h2>키워드 빈도</h2>
          <span class="meta">N={n_headlines} HEADLINES</span>
        </div>
        <div class="kw-rows">{''.join(kw_rows)}</div>
      </div>
    </div>
    """


def render_issues(ai_data):
    issues = (ai_data or {}).get("issues") or []
    if not issues:
        return """
        <div class="panel">
          <div class="panel-head"><h2>핵심 이슈</h2></div>
          <div style="color:var(--ink-3);padding:30px;text-align:center;font-size:12px;">
            아직 분석된 이슈가 없습니다.
          </div>
        </div>
        """
    cards = []
    for idx, issue in enumerate(issues[:6]):
        rank = issue.get("rank", idx + 1)
        category = issue.get("category") or ""
        klass = topic_palette_class(category)
        title = esc(issue.get("issue_title", "이슈명 없음"))
        summary = esc_safe(issue.get("one_line_summary", ""))
        why = esc_safe(issue.get("why_it_matters", ""))
        heat = compute_issue_heat(issue)
        cov = compute_issue_coverage(issue)
        cards.append(f"""
        <div class="iss-card {klass}">
          <div class="topic-block"></div>
          <div class="iss-head">
            <div class="iss-meta">
              <div class="rank">ISSUE #{int(rank):02d}</div>
              <span class="topic-pill">{html.escape(category) or '기타'}</span>
            </div>
            {heat_arc_svg(heat, 56)}
          </div>
          <h3>{title}</h3>
          <p>{summary}</p>
          <div class="metrics">
            <div>
              <div class="m-lbl">Coverage</div>
              <div class="m-val">{cov}<span class="dim">/14</span></div>
            </div>
            <div>
              <div class="m-lbl">Heat</div>
              <div class="m-val">{heat}</div>
            </div>
          </div>
          <div class="why">{why}</div>
        </div>
        """)
    return f"""
    <div class="panel">
      <div class="panel-head">
        <h2>핵심 이슈 · HEAT × COVERAGE</h2>
        <span class="meta">{len(issues)} ISSUES · UNIFORM GRID</span>
      </div>
      <div class="iss-grid">{''.join(cards)}</div>
    </div>
    """


def render_heatmap(ai_data, news_data):
    issues = (ai_data or {}).get("issues") or []
    if not issues:
        return ""
    matrix = compute_heatmap(issues, news_data)
    press_names = list(URLS.keys())
    rows = []
    rows.append('<div class="corner">ISSUE ↓ · PRESS →</div>')
    for p in press_names:
        base_cls = " base" if p == TARGET_PRESS else ""
        rows.append(f'<div class="h-press{base_cls}">{html.escape(p)}</div>')
    for ri, issue in enumerate(issues[:6]):
        title_raw = issue.get("issue_title", "")
        title_display = title_raw if len(title_raw) <= 22 else title_raw[:22] + "…"
        rows.append(
            f'<div class="iss-label">'
            f'  <span class="num">#{int(issue.get("rank", ri + 1)):02d}</span>'
            f'  <span>{html.escape(title_display)}</span>'
            f'</div>'
        )
        for v in matrix[ri]:
            cls = f"cell l{v}" if v > 0 else "cell"
            rows.append(f'<div class="{cls}">{v if v > 0 else ""}</div>')
    return f"""
    <div class="panel">
      <div class="panel-head">
        <h2>이슈 × 언론사 보도 매트릭스</h2>
        <span class="meta">DARKER = MORE COVERAGE · KEYWORD MATCH</span>
      </div>
      <div class="hm">{''.join(rows)}</div>
    </div>
    """


def render_missed(ai_data):
    missed = (ai_data or {}).get("missed_articles") or []
    if not missed:
        body = ('<div style="padding:30px;text-align:center;color:var(--ink-3);font-size:12px;">'
                f'현재 기준으로 {TARGET_PRESS}가 뚜렷하게 놓친 주요 이슈는 발견되지 않았습니다.</div>')
        return f"""
        <div class="panel">
          <div class="panel-head">
            <h2>⚠ 우리가 놓친 기사</h2>
            <span class="meta">기준 = {TARGET_PRESS}</span>
          </div>
          {body}
        </div>
        """
    items = []
    for idx, m in enumerate(missed[:5]):
        rank = m.get("rank", idx + 1)
        title = esc(m.get("issue_title", "이슈명 없음"))
        reason = esc_safe(m.get("why_missed", ""))
        signal = esc_safe(m.get("coverage_signal", ""))
        items.append(f"""
        <div class="alert">
          <div class="alert-tag">MISSED #{int(rank):02d}</div>
          <div>
            <div class="alert-title">{title}</div>
            <div class="alert-meta"><span class="lbl">REASON</span>{reason}</div>
            <div class="alert-meta"><span class="lbl">SIGNAL</span>{signal}</div>
          </div>
        </div>
        """)
    return f"""
    <div class="panel">
      <div class="panel-head">
        <h2>⚠ 우리가 놓친 기사</h2>
        <span class="meta">기준 = {TARGET_PRESS} · DETECTED IN OTHER OUTLETS</span>
      </div>
      <div class="alerts">{''.join(items)}</div>
    </div>
    """


def render_press_table(news_data):
    cols = []
    for press in URLS.keys():
        bias = BIAS_MAP.get(press, "C")
        bias_label = BIAS_LABEL.get(bias, "중도")
        articles = news_data.get(press, []) or []
        # 헤더
        base_badge = '<span class="basebadge">BASE</span>' if press == TARGET_PRESS else ""
        header = (
            f'<div class="pr">'
            f'  <span></span>'
            f'  <span class="nm">{html.escape(press)} {base_badge}</span>'
            f'  <span class="bias-mini {bias}">{bias_label}</span>'
            f'  <span class="stcount">{len(articles):02d}</span>'
            f'</div>'
        )
        # 헤드라인
        if not articles or "데이터를 불러올 수 없습니다" in (articles[0].get("title") or ""):
            lead_items = ['<div class="st empty"><span class="bullet">▸</span>최신 뉴스를 불러오지 못했습니다.</div>']
        else:
            lead_items = []
            for a in articles[:5]:
                t = a.get("title", "")
                u = a.get("url")
                is_break = t.startswith("[속보]")
                t_display = re.sub(r"^\[속보\]\s*", "", t)
                klass = "st bk" if is_break else "st"
                bullet = "◆" if is_break else "▸"
                safe_t = html.escape(t_display)
                if u:
                    body = f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{safe_t}</a>'
                else:
                    body = safe_t
                lead_items.append(f'<div class="{klass}"><span class="bullet">{bullet}</span>{body}</div>')
        cols.append(f'<div class="press-col">{header}<div class="lead">{"".join(lead_items)}</div></div>')
    return f"""
    <div class="panel">
      <div class="panel-head">
        <h2>언론사별 리드 헤드라인</h2>
        <span class="meta">14 OUTLETS · TOP 5 PER OUTLET</span>
      </div>
      <div class="press-table">{''.join(cols)}</div>
    </div>
    """


# =========================
# 메인 렌더
# =========================
refresh_slot = get_current_refresh_slot()
st_autorefresh(interval=UI_POLL_INTERVAL_MS, limit=None, key="news_autorefresh")

# CSS 주입
st.markdown(V2_CSS, unsafe_allow_html=True)

# 데이터 수집
dashboard_stats = get_dashboard_stats()
with st.spinner("언론사별 주요 뉴스를 수집 중입니다..."):
    news_data = fetch_news(refresh_slot)
with st.spinner("저장된 AI 분석 결과를 불러오고 있습니다..."):
    ai_insight = get_stored_ai_insight()
    if isinstance(ai_insight, str):
        try:
            ai_insight = json.loads(clean_model_text(ai_insight))
        except Exception:
            ai_insight = {}
    if isinstance(ai_insight, dict):
        ai_insight = sanitize_ai_payload(ai_insight)

# 에러 표시 (캐시 비어있음)
ai_error = ai_insight.get("error") if isinstance(ai_insight, dict) else None

# 렌더링 (전체를 .v2 wrapper로 묶어 한 번에 emit)
sections = [
    render_topnav(dashboard_stats),
    render_header(dashboard_stats, ai_insight if not ai_error else {}, news_data),
]

if ai_error:
    sections.append(
        f'<div class="panel"><div style="padding:20px;background:var(--panel);'
        f'border-left:3px solid var(--amber);color:var(--ink-2);font-size:13px;">'
        f'{html.escape(str(ai_error))}</div></div>'
    )
else:
    sections.append(render_flow_and_keywords(ai_insight, news_data, dashboard_stats))
    sections.append('<div class="sec-div"></div>')
    sections.append(render_issues(ai_insight))
    sections.append('<div class="sec-div"></div>')
    sections.append(render_heatmap(ai_insight, news_data))
    sections.append('<div class="sec-div"></div>')
    sections.append(render_missed(ai_insight))

sections.append('<div class="sec-div"></div>')
sections.append(render_press_table(news_data))

# Streamlit markdown은 4칸 들여쓰기를 코드블록으로 해석할 수 있으므로
# 라인 선두 공백을 모두 제거한 뒤 출력한다 (HTML 시각효과에 영향 없음).
final_html = '<div class="v2">' + ''.join(sections) + '</div>'
final_html = re.sub(r'^[ \t]+', '', final_html, flags=re.MULTILINE)
st.markdown(final_html, unsafe_allow_html=True)
