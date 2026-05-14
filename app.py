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

# 페이지 설정
st.set_page_config(page_title="주요 언론사 뉴스 대시보드", page_icon="📰", layout="wide")

TARGET_PRESS = "국민일보"
AI_CACHE_VERSION = "minimal-fields-v1"
GEMINI_MODEL_NAME = "gemini-3.1-flash-lite"
REFRESH_INTERVAL_MINUTES = 10
UI_POLL_INTERVAL_MS = 15 * 1000
AI_CACHE_DIR = Path(os.getenv("NEWS_DASHBOARD_CACHE_DIR", ".news_dashboard_cache"))
AI_DB_PATH = AI_CACHE_DIR / "news_dashboard_cache.sqlite3"


# =========================
# 유틸 함수
# =========================
def clean_model_text(text):
    """
    Gemini 응답에 코드블록이나 불필요한 마크다운이 섞였을 때 정리합니다.
    """
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
    html_signals = ["<div", "<span", "<p", "<br", "<small", "<a ", "<ul", "<li", "<section"]
    return any(signal in t for signal in html_signals)


def to_plain_display_text(value, prefer_after_label=None):
    """
    AI가 JSON 필드 안에 HTML 카드 조각을 넣어도 화면에는 일반 텍스트만 보이게 합니다.
    """
    if value is None:
        return ""

    text = html.unescape(clean_model_text(value))
    cut_points = [
        pos for pos in [
            text.lower().find("<div"),
            text.lower().find("&lt;div"),
            text.find("```"),
        ]
        if pos != -1
    ]
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
    """
    Remove dashboard card markup or boilerplate text accidentally embedded in
    AI text fields and fall back to plain text when needed.
    """
    text = to_plain_display_text(value)
    card_markers = [
        "summary",
        "importance",
        "???",
        "priority",
        "?? ?? ??",
        "score-badge",
        "recommended-box",
    ]

    original = html.unescape(str(value or ""))

    if is_probably_html(original) or any(marker in text for marker in card_markers):
        if "?? ???" in text:
            return text.split("?? ???", 1)[1].strip()
        if any(marker in text for marker in card_markers):
            return fallback

    return text


def has_embedded_markup(value):
    text = html.unescape(str(value or "")).lower()
    markup_markers = [
        "<div",
        "</div",
        "<span",
        "</span",
        "<p",
        "</p",
        "<br",
        "<small",
        "</small",
        "<a ",
        "</a",
        "```",
        "score-badge",
        "recommended-box",
        "class=",
        "target='_blank'",
        'target="_blank"',
    ]
    return any(marker in text for marker in markup_markers)


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
            clean_keyword = sanitize_ai_text(keyword)
            if clean_keyword:
                clean_keywords.append(clean_keyword)
        summary["top_keywords"] = clean_keywords

    for issue in ai_data.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue

        for key in ["issue_title", "category", "one_line_summary", "why_it_matters", "editor_comment"]:
            issue[key] = sanitize_ai_text(issue.get(key, ""))

        recommended = issue.get("recommended_article")
        if isinstance(recommended, dict):
            for key in ["media", "title", "reason"]:
                recommended[key] = sanitize_ai_text(recommended.get(key, ""))

        clean_related = []
        for article in issue.get("related_articles", []) or []:
            if not isinstance(article, dict):
                continue
            article["media"] = sanitize_ai_text(article.get("media", ""))
            article["title"] = sanitize_ai_text(article.get("title", ""))
            clean_related.append(article)
        issue["related_articles"] = clean_related

    for item in ai_data.get("missed_articles", []) or []:
        if not isinstance(item, dict):
            continue

        for key in ["issue_title", "category", "why_missed", "coverage_signal", "suggested_angle"]:
            item[key] = sanitize_ai_text(item.get(key, ""))

        clean_refs = []
        for article in item.get("reference_articles", []) or []:
            if not isinstance(article, dict):
                continue
            article["media"] = sanitize_ai_text(article.get("media", ""))
            article["title"] = sanitize_ai_text(article.get("title", ""))
            clean_refs.append(article)
        item["reference_articles"] = clean_refs

    return ai_data


def escape_display_text(value, prefer_after_label=None):
    return html.escape(to_plain_display_text(value, prefer_after_label=prefer_after_label))


def escape_card_safe_text(value, fallback=""):
    return html.escape(strip_embedded_card_text(value, fallback=fallback))


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
        row = conn.execute(
            "SELECT * FROM ai_cache WHERE cache_key = 'latest'"
        ).fetchone()

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


def milliseconds_until_next_refresh_slot():
    now = get_kst_now()
    next_minute = ((now.minute // REFRESH_INTERVAL_MINUTES) + 1) * REFRESH_INTERVAL_MINUTES

    if next_minute >= 60:
        next_slot = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    else:
        next_slot = now.replace(minute=next_minute, second=0, microsecond=0)

    milliseconds = int((next_slot - now).total_seconds() * 1000)
    return max(milliseconds, 1000)


def get_autorefresh_interval_ms(current_refresh_slot):
    cached_result = get_cached_ai_result()
    cached_slot = ""

    if isinstance(cached_result, dict):
        cached_slot = str(cached_result.get("refresh_slot", "") or "")

    if cached_slot == current_refresh_slot:
        return milliseconds_until_next_refresh_slot()

    # The scheduler usually finishes after the slot boundary, so keep polling
    # briefly until the latest cached result catches up with the current slot.
    return 15 * 1000


# =========================
# CSS
# =========================
st.markdown("""
<style>
    .insight-box {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        color: white;
        padding: 30px;
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        margin-bottom: 40px;
    }
    .insight-title {
        font-size: 1.8rem;
        font-weight: 800;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .summary-card {
        background: rgba(255,255,255,0.12);
        padding: 20px;
        border-radius: 14px;
        margin-bottom: 20px;
        border: 1px solid rgba(255,255,255,0.18);
    }
    .issue-card {
        background: #ffffff;
        color: #1a1a1a;
        padding: 20px;
        border-radius: 14px;
        margin-bottom: 18px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.10);
        border-left: 6px solid #2c5364;
    }
    .missed-card {
        background: #fff8ef;
        color: #1a1a1a;
        padding: 20px;
        border-radius: 14px;
        margin-bottom: 18px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.10);
        border-left: 6px solid #ff9800;
    }
    .issue-rank {
        font-size: 0.9rem;
        font-weight: 800;
        color: #2c5364;
        margin-bottom: 6px;
    }
    .missed-rank {
        font-size: 0.9rem;
        font-weight: 800;
        color: #e07b00;
        margin-bottom: 6px;
    }
    .issue-title {
        font-size: 1.25rem;
        font-weight: 800;
        margin-bottom: 8px;
    }
    .issue-category {
        display: inline-block;
        background: #eef5f7;
        color: #2c5364;
        font-size: 0.8rem;
        font-weight: 700;
        padding: 4px 9px;
        border-radius: 999px;
        margin-bottom: 10px;
    }
    .missed-badge {
        display: inline-block;
        background: #fff0d9;
        color: #d86f00;
        font-size: 0.8rem;
        font-weight: 800;
        padding: 4px 9px;
        border-radius: 999px;
        margin-bottom: 10px;
    }
    .score-badge {
        display: inline-block;
        background: #f3f6f8;
        color: #203a43;
        padding: 5px 8px;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 700;
        margin-right: 5px;
        margin-top: 6px;
    }
    .urgency-badge {
        display: inline-block;
        background: #ffedd6;
        color: #d86f00;
        padding: 5px 8px;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 800;
        margin-right: 5px;
        margin-top: 6px;
    }
    .recommended-box {
        background: #f7fbfc;
        border-radius: 10px;
        padding: 12px;
        margin-top: 12px;
        border: 1px solid #e1edf0;
    }
    .missed-recommend-box {
        background: #fff4e6;
        border-radius: 10px;
        padding: 12px;
        margin-top: 12px;
        border: 1px solid #ffd8a8;
    }
    .news-box {
        background-color: #ffffff;
        padding: 25px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
        margin-bottom: 25px;
        border-top: 5px solid #203a43;
        height: 100%;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .news-box.target-press {
        border-top: 5px solid #ff9800;
        box-shadow: 0 5px 24px rgba(255,152,0,0.18);
    }
    .news-box:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }
    .press-title {
        font-size: 1.3rem;
        font-weight: 800;
        color: #1a1a1a;
        margin-bottom: 15px;
        border-bottom: 1px solid #e0e0e0;
        padding-bottom: 10px;
    }
    .target-label {
        display: inline-block;
        margin-left: 8px;
        font-size: 0.75rem;
        background: #fff0d9;
        color: #d86f00;
        padding: 3px 7px;
        border-radius: 999px;
        vertical-align: middle;
    }
    .news-item {
        font-size: 1.0rem;
        color: #4a4a4a;
        margin-bottom: 12px;
        line-height: 1.6;
        display: flex;
        align-items: flex-start;
        gap: 8px;
    }
    .news-item::before {
        content: "•";
        color: #2c5364;
        font-weight: bold;
    }
    .news-item a {
        color: #4a4a4a;
        text-decoration: none;
    }
    .news-item a:hover {
        color: #203a43;
        text-decoration: underline;
    }
</style>
""", unsafe_allow_html=True)


# =========================
# 주요 언론사 네이버 채널 URL
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
    "한국경제": "https://media.naver.com/press/015"
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
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for name, url in URLS.items():
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")

            articles = []

            title_nodes = soup.select(".press_news_text")

            for node in title_nodes:
                title = node.get_text(strip=True)
                if not title:
                    continue

                a_tag = node.find_parent("a")
                article_url = normalize_url(a_tag.get("href")) if a_tag else None

                if title not in [a["title"] for a in articles]:
                    articles.append({
                        "title": title,
                        "url": article_url
                    })

            if not articles:
                title_nodes = soup.select(".cjs_t")

                for node in title_nodes:
                    title = node.get_text(strip=True)
                    if not title:
                        continue

                    a_tag = node.find_parent("a")
                    article_url = normalize_url(a_tag.get("href")) if a_tag else None

                    if title not in [a["title"] for a in articles]:
                        articles.append({
                            "title": title,
                            "url": article_url
                        })

            if not articles:
                link_nodes = soup.select("a[href*='/article/']")

                for a_tag in link_nodes:
                    title = a_tag.get_text(" ", strip=True)
                    article_url = normalize_url(a_tag.get("href"))

                    if len(title) >= 8 and title not in [a["title"] for a in articles]:
                        articles.append({
                            "title": title,
                            "url": article_url
                        })

            results[name] = articles[:6]

        except Exception:
            results[name] = [{
                "title": "데이터를 불러올 수 없습니다.",
                "url": None
            }]

    return results


@st.cache_data
def fetch_news(refresh_slot):
    return collect_news()


def flatten_news_titles(news_data):
    all_titles = []

    for press, articles in news_data.items():
        for article in articles:
            title = article.get("title", "")
            if title and "데이터를 불러올 수 없습니다" not in title:
                all_titles.append(title)

    return all_titles


def analyze_issues(news_data, top_n=3):
    all_titles = flatten_news_titles(news_data)

    stopwords = set([
        "위해", "대한", "하는", "결국", "다시", "오늘", "내일", "어제", "부터", "까지",
        "있는", "없는", "에서", "으로", "어떻게", "이런", "입니다", "합니다", "않다",
        "없다", "있다", "된다", "한다", "종합", "속보", "단독", "포토", "영상", "뉴스",
        "이번", "관련", "기자", "지난", "올해", "내년", "사실", "논란"
    ])

    words = []

    for title in all_titles:
        clean_title = re.sub(r"[^\w\s]", " ", title)

        for w in clean_title.split():
            if len(w) > 1 and w not in stopwords and not w.isdigit():
                words.append(w)

    counter = Counter(words)
    top_keywords = counter.most_common(top_n)

    issues = []

    for keyword, count in top_keywords:
        related_titles = []

        for title in all_titles:
            if keyword in title and title not in related_titles:
                related_titles.append(title)

        issues.append({
            "keyword": keyword,
            "count": count,
            "titles": related_titles[:4]
        })

    return issues


def analyze_missed_articles_local(news_data, target_press=TARGET_PRESS, top_n=3):
    target_articles = news_data.get(target_press, [])
    target_titles = [
        a.get("title", "")
        for a in target_articles
        if "데이터를 불러올 수 없습니다" not in a.get("title", "")
    ]
    target_text = " ".join(target_titles)

    other_titles = []
    other_article_map = []

    for press, articles in news_data.items():
        if press == target_press:
            continue

        for article in articles:
            title = article.get("title", "")
            if title and "데이터를 불러올 수 없습니다" not in title:
                other_titles.append(title)
                other_article_map.append({
                    "media": press,
                    "title": title,
                    "url": article.get("url")
                })

    stopwords = set([
        "위해", "대한", "하는", "결국", "다시", "오늘", "내일", "어제", "부터", "까지",
        "있는", "없는", "에서", "으로", "어떻게", "이런", "입니다", "합니다", "않다",
        "없다", "있다", "된다", "한다", "종합", "속보", "단독", "포토", "영상", "뉴스",
        "이번", "관련", "기자", "지난", "올해", "내년", "사실", "논란"
    ])

    words = []

    for title in other_titles:
        clean_title = re.sub(r"[^\w\s]", " ", title)

        for w in clean_title.split():
            if len(w) > 1 and w not in stopwords and not w.isdigit():
                if w not in target_text:
                    words.append(w)

    counter = Counter(words)
    keywords = counter.most_common(top_n)

    missed = []

    for idx, (keyword, count) in enumerate(keywords, start=1):
        refs = [
            a for a in other_article_map
            if keyword in a["title"]
        ][:4]

        missed.append({
            "rank": idx,
            "issue_title": keyword,
            "why_missed": f"다른 언론 주요 뉴스에서 '{keyword}' 키워드가 반복되지만 국민일보 주요 목록에서는 뚜렷하게 보이지 않습니다.",
            "coverage_signal": f"타 언론 기사 기준 {count}회 이상 반복",
            "suggested_angle": "국민일보 독자 관점에서 공공성, 생활 영향, 정치·사회적 파장을 중심으로 후속 기사화할 수 있습니다.",
            "urgency_score": min(5, max(1, count)),
            "reference_articles": refs
        })

    return missed


def build_ai_persona_prompt(news_data):
    input_articles = []

    for press, articles in news_data.items():
        for article in articles:
            title = article.get("title", "")
            url = article.get("url")

            if title and "데이터를 불러올 수 없습니다" not in title:
                input_articles.append({
                    "media": press,
                    "title": title,
                    "url": url
                })

    articles_json = json.dumps(input_articles, ensure_ascii=False, indent=2)

    prompt = f"""
너는 “뉴스 트렌드 에디터 AI”다.

너의 역할은 주요 언론사의 네이버채널 뉴스 제목 목록을 분석해 현재 핵심 뉴스 이슈를 6개로 정리하고,
각 이슈별로 사용자에게 노출할 만한 대표 기사를 추천하는 것이다.

또한 너는 {TARGET_PRESS} 편집팀을 돕는 모니터링 에디터 역할도 수행한다.
다른 주요 언론사들은 다루고 있는데 {TARGET_PRESS}의 현재 주요 뉴스 목록에는 보이지 않는 이슈를 찾아
〈우리가 놓친 기사들〉 항목으로 제안해야 한다.

중요:
- 기사 본문은 제공되지 않는다.
- 기사 제목에 없는 사실을 임의로 추정하거나 단정하지 마라.
- 결과는 반드시 JSON만 출력하라.
- HTML, Markdown, 코드블록을 절대 출력하지 마라.
- JSON 앞뒤에 설명 문장을 붙이지 마라.
- 어떤 문자열 값에도 <div>, <span>, <p>, <br>, <a>, class=, ``` 같은 HTML/Markdown 조각을 넣지 마라.
- 중요도, 확산성, 관심도, 신선도는 반드시 scores 객체 안의 숫자로만 넣고 본문 문자열에는 반복하지 마라.
- 추천 기사 제목, 언론사, URL, 추천 이유는 반드시 recommended_article 객체 필드에만 나누어 넣어라.

카테고리는 반드시 아래 중 하나만 사용하라.
정치, 경제, 사회, 국제, 생활, IT·과학, 문화, 스포츠, 연예, 오피니언, 기타

점수는 1점부터 5점까지 정수로 부여하라.

반드시 아래 JSON 형식으로만 출력하라.

{{
  "dashboard_summary": {{
    "overall_trend": "오늘 뉴스 흐름에 대한 2~3문장 요약",
    "top_keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
    "editorial_note": "편집자가 참고할 전체 코멘트"
  }},
  "issues": [
    {{
      "rank": 1,
      "issue_title": "핵심 이슈명",
      "category": "정치",
      "one_line_summary": "이슈 한 줄 요약",
      "why_it_matters": "이 이슈가 중요한 이유",
      "related_articles": [
        {{
          "media": "언론사명",
          "title": "기사 제목",
          "url": "기사 URL 또는 null"
        }}
      ],
      "recommended_article": {{
        "media": "언론사명",
        "title": "노출 추천 기사 제목",
        "url": "기사 URL 또는 null",
        "reason": "이 기사를 추천하는 이유"
      }},
      "scores": {{
        "importance": 1,
        "virality": 1,
        "reader_interest": 1,
        "freshness": 1
      }},
      "editor_comment": "편집 관점의 짧은 코멘트"
    }}
  ],
  "missed_articles": [
    {{
      "rank": 1,
      "issue_title": "{TARGET_PRESS}가 놓친 것으로 보이는 이슈명",
      "category": "정치",
      "why_missed": "왜 {TARGET_PRESS}가 놓친 기사로 판단했는지",
      "coverage_signal": "다른 언론 몇 곳 또는 어떤 언론들이 다루고 있는지",
      "suggested_angle": "{TARGET_PRESS}가 이 이슈를 어떤 관점으로 다루면 좋을지",
      "urgency_score": 1,
      "reference_articles": [
        {{
          "media": "타 언론사명",
          "title": "참고 기사 제목",
          "url": "기사 URL 또는 null"
        }}
      ]
    }}
  ]
}}

추가 규칙:
- issues 배열은 반드시 6개여야 한다.
- missed_articles 배열은 최대 5개까지 출력하라.
- 놓친 이슈가 없다면 missed_articles는 빈 배열 []로 출력하라.
- related_articles에는 입력 기사 목록에 실제 존재하는 기사만 넣어라.
- recommended_article은 반드시 related_articles 안에 있는 기사 중에서 선택하라.
- missed_articles.reference_articles에는 {TARGET_PRESS}가 아닌 타 언론 기사만 넣어라.
- URL이 없는 경우 null로 표시하라.

이제 아래 기사 목록을 분석하라.

[기사 목록]
{articles_json}
"""
    return prompt


def parse_gemini_json(text):
    if not text:
        return None

    cleaned = clean_model_text(text)

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end > start:
        json_candidate = cleaned[start:end + 1]
        json_candidate = re.sub(r",\s*([}\]])", r"\1", json_candidate)

        try:
            return json.loads(json_candidate)
        except Exception:
            pass

    return None


def get_stored_ai_insight():
    cached_result = get_cached_ai_result()
    if isinstance(cached_result, dict) and cached_result.get("data"):
        return cached_result["data"]

    return {
        "error": "저장된 AI 분석 결과가 아직 없습니다. 별도 스케줄러가 DB를 갱신한 뒤 표시됩니다.",
        "raw": None
    }


def render_ai_dashboard(ai_data):
    """
    Gemini가 생성한 JSON 결과를 Streamlit 대시보드에 렌더링합니다.
    혹시 문자열 HTML이 들어오더라도 코드로 보이지 않게 보정합니다.
    """
    if not ai_data:
        st.warning("AI 분석 결과가 없습니다.")
        return

    if isinstance(ai_data, str):
        cleaned = clean_model_text(ai_data)

        parsed = parse_gemini_json(cleaned)
        if parsed:
            render_ai_dashboard(parsed)
        else:
            st.warning("AI 응답 형식이 올바르지 않아 표시하지 않았습니다. 새로고침을 눌러 다시 분석해주세요.")
        return

    if not isinstance(ai_data, dict):
        st.warning("AI 분석 결과 형식이 올바르지 않습니다.")
        return

    ai_data = sanitize_ai_payload(ai_data)

    if ai_data.get("error"):
        st.error(ai_data["error"])

        raw = ai_data.get("raw")
        if raw:
            raw_cleaned = clean_model_text(raw)

            with st.expander("AI 원문 응답 보기"):
                if is_probably_html(raw_cleaned):
                    st.write(strip_embedded_card_text(raw_cleaned, fallback="AI가 HTML 형식으로 응답했습니다. 새로고침을 눌러 다시 분석해주세요."))
                else:
                    st.code(raw_cleaned, language="json")

        return

    summary = ai_data.get("dashboard_summary", {}) or {}
    issues = ai_data.get("issues", []) or []
    missed_articles = ai_data.get("missed_articles", []) or []

    overall_trend = summary.get("overall_trend", "")
    top_keywords = summary.get("top_keywords", [])
    editorial_note = summary.get("editorial_note", "")
    top_keywords_text = ", ".join([escape_display_text(k) for k in top_keywords])

    st.markdown(
        f"""
        <div class="summary-card">
            <h3>📌 오늘의 전체 뉴스 흐름</h3>
            <p>{escape_display_text(overall_trend)}</p>
            <p><b>핵심 키워드:</b> {top_keywords_text}</p>
            <p><b>편집 코멘트:</b> {escape_card_safe_text(editorial_note)}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("### 🔥 핵심 이슈 6")

    cols = st.columns(2)

    for idx, issue in enumerate(issues[:6]):
        with cols[idx % 2]:
            rank = issue.get("rank", idx + 1)
            issue_title = issue.get("issue_title", "이슈명 없음")
            one_line_summary = issue.get("one_line_summary", "")
            why_it_matters = issue.get("why_it_matters", "")

            st.markdown(
                f"""
                <div class="issue-card">
                    <div class="issue-rank">#{escape_display_text(rank)}</div>
                    <div class="issue-title">{escape_display_text(issue_title)}</div>
                    <p><b>요약:</b> {escape_card_safe_text(one_line_summary)}</p>
                    <p><b>중요한 이유:</b> {escape_card_safe_text(why_it_matters)}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("---")
    st.markdown("### 🧭 우리가 놓친 기사들")
    st.caption(f"기준: {TARGET_PRESS} 주요 뉴스 목록에 없지만 타 언론에서 반복적으로 다루는 이슈")

    if not missed_articles:
        st.success(f"현재 기준으로 {TARGET_PRESS}가 뚜렷하게 놓친 주요 이슈는 발견되지 않았습니다.")
        return

    missed_cols = st.columns(2)

    for idx, item in enumerate(missed_articles[:5]):
        with missed_cols[idx % 2]:
            rank = item.get("rank", idx + 1)
            issue_title = item.get("issue_title", "이슈명 없음")
            why_missed = item.get("why_missed", "")
            coverage_signal = item.get("coverage_signal", "")

            st.markdown(
                f"""
                <div class="missed-card">
                    <div class="missed-rank">#{escape_display_text(rank)} 놓친 후보</div>
                    <div class="issue-title">{escape_display_text(issue_title)}</div>
                    <p><b>판단 이유:</b> {escape_card_safe_text(why_missed)}</p>
                    <p><b>타 언론 보도 신호:</b> {escape_card_safe_text(coverage_signal)}</p>
                </div>
                """,
                unsafe_allow_html=True
            )


def render_local_missed_articles(news_data):
    missed = analyze_missed_articles_local(news_data, TARGET_PRESS, top_n=3)

    st.markdown("---")
    st.markdown("### 🧭 우리가 놓친 기사들")
    st.caption(f"기준: {TARGET_PRESS} 주요 뉴스 목록에 없지만 타 언론에서 반복적으로 등장하는 키워드")

    if not missed:
        st.success(f"현재 기준으로 {TARGET_PRESS}가 뚜렷하게 놓친 주요 키워드는 발견되지 않았습니다.")
        return

    cols = st.columns(3)

    for idx, item in enumerate(missed):
        with cols[idx]:
            st.markdown(
                f"""
                <div style="
                    background:#fff8ef;
                    color:#1a1a1a;
                    padding:18px;
                    border-radius:14px;
                    border-left:6px solid #ff9800;
                    min-height:230px;
                ">
                    <div style="font-weight:800;color:#e07b00;">#{escape_display_text(item['rank'])} 놓친 후보</div>
                    <h3>{escape_display_text(item['issue_title'])}</h3>
                    <p><b>판단 이유:</b> {escape_card_safe_text(item['why_missed'])}</p>
                    <p><b>타 언론 보도 신호:</b> {escape_card_safe_text(item['coverage_signal'])}</p>
                </div>
                """,
                unsafe_allow_html=True
            )


refresh_slot = get_current_refresh_slot()
st_autorefresh(interval=UI_POLL_INTERVAL_MS, limit=None, key="news_autorefresh")


# =========================
# 메인 화면
# =========================
st.title("📰 뉴스 트렌드 & 인사이트 대시보드")
st.markdown(
    f"주요 언론사의 네이버 뉴스 제목을 바탕으로 현재 뉴스 흐름과 AI 분석 결과를 한 화면에서 확인합니다. "
    f"기준 매체는 **{TARGET_PRESS}**입니다."
)

dashboard_stats = get_dashboard_stats()
metric_cols = st.columns(4)
metric_cols[0].metric("마지막 분석 시간", format_timestamp(dashboard_stats["last_generated_at"]))
metric_cols[1].metric("마지막 사용 AI", dashboard_stats["last_model"] or "-")
metric_cols[2].metric("오늘 AI 호출 횟수", f"{dashboard_stats['today_ai_calls']} / 400")
metric_cols[3].metric("마지막 분석 슬롯", format_refresh_slot(dashboard_stats["last_refresh_slot"]))

with st.spinner("언론사별 주요 뉴스를 수집 중입니다..."):
    news_data = fetch_news(refresh_slot)


# =========================
# 인사이트 섹션
# =========================
st.markdown("<div class='insight-box'>", unsafe_allow_html=True)

st.markdown(
    "<div class='insight-title'>🧠 AI 에디터의 뉴스 트렌드 분석</div>",
    unsafe_allow_html=True
)

with st.spinner("저장된 AI 분석 결과를 불러오고 있습니다..."):
    ai_insight = get_stored_ai_insight()
    render_ai_dashboard(ai_insight)

st.markdown("</div>", unsafe_allow_html=True)


# =========================
# 언론사별 주요 뉴스
# =========================
st.subheader("📰 언론사별 주요 뉴스")
st.write("")

cols = st.columns(3)
press_names = list(news_data.keys())

for idx, press in enumerate(press_names):
    col_idx = idx % 3

    with cols[col_idx]:
        articles = news_data[press]

        target_class = " target-press" if press == TARGET_PRESS else ""
        target_label = "<span class='target-label'>기준 언론사</span>" if press == TARGET_PRESS else ""

        html_content = (
            f"<div class='news-box{target_class}'>"
            f"<div class='press-title'>{html.escape(str(press))}{target_label}</div>"
        )

        if not articles or "데이터를 불러올 수 없습니다" in articles[0].get("title", ""):
            html_content += "<div class='news-item'>최신 뉴스를 불러오지 못했습니다.</div>"
        else:
            for article in articles:
                title = article.get("title", "")
                url = article.get("url")

                safe_title = html.escape(str(title))

                if url:
                    safe_url = html.escape(str(url))
                    html_content += f"<div class='news-item'><a href='{safe_url}' target='_blank'>{safe_title}</a></div>"
                else:
                    html_content += f"<div class='news-item'>{safe_title}</div>"

        html_content += "</div>"

        st.markdown(html_content, unsafe_allow_html=True)
