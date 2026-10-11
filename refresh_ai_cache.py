import argparse
from contextlib import closing
from datetime import datetime, timedelta
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import statistics
import time
from zoneinfo import ZoneInfo


TARGET_PRESS = "국민일보"
AI_CACHE_VERSION = "daily-coverage-v1"
ARTICLE_RETENTION_DAYS = 7
PROMPT_MAX_ARTICLES_PER_PRESS = 40
PROMPT_MAX_TARGET_ARTICLES = 80
MAX_ISSUES = 12
# 타사 몇 곳 이상이 다룬 이슈부터 국민일보 누락·소홀 후보로 보는지
MIN_OUTLETS_FOR_GAP = 3
# 국민일보 노출 합계가 타사 노출 중앙값의 이 비율보다 낮으면 '소홀'
UNDERCOVERED_RATIO = 0.5
PRIMARY_MODEL_NAME = "gemini-3.5-flash-lite"
REFRESH_INTERVAL_MINUTES = 10
SERVICE_UNAVAILABLE_THRESHOLD = 2
SERVICE_UNAVAILABLE_COOLDOWN_SECONDS = 30 * 60
AI_CACHE_DIR = Path(os.getenv("NEWS_DASHBOARD_CACHE_DIR", ".news_dashboard_cache"))
AI_DB_PATH = AI_CACHE_DIR / "news_dashboard_cache.sqlite3"
AI_REFRESH_LOCK_TTL_SECONDS = 120

MODEL_CHAIN = [
    {
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "api_keys": ["GEMINI_API_KEY"],
        "rpm": 15,
        "rpd": 500,
        "tpm": 250_000,
        "tpd": None,
        "max_attempts": 3,
    },
    {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "api_keys": ["GEMINI_API_KEY"],
        "rpm": 15,
        "rpd": 500,
        "tpm": 250_000,
        "tpd": None,
        "max_attempts": 3,
    },
]


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


def get_secret_value(secret_name):
    key = os.getenv(secret_name, "")
    if key:
        return key.strip()

    secrets_path = Path(".streamlit") / "secrets.toml"
    if not secrets_path.exists():
        return ""

    try:
        import tomllib

        secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
        return str(secrets.get(secret_name, "")).strip()
    except Exception:
        return ""


def get_api_key_for_model(model_config):
    for secret_name in model_config.get("api_keys", []):
        value = get_secret_value(secret_name)
        if value:
            return value
    return ""


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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gemini_request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                input_tokens INTEGER NOT NULL,
                model TEXT NOT NULL,
                refresh_slot TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slot_attempts (
                refresh_slot TEXT PRIMARY KEY,
                attempted_at REAL NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS refresh_locks (
                lock_name TEXT PRIMARY KEY,
                acquired_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_state (
                state_key TEXT PRIMARY KEY,
                state_value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_attempt_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                refresh_slot TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_key TEXT NOT NULL,
                press TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                seen_count INTEGER NOT NULL,
                UNIQUE(day_key, press, title)
            )
        """)


def get_kst_now():
    return datetime.now(ZoneInfo("Asia/Seoul"))


def get_current_refresh_slot():
    now = get_kst_now()
    slot_minute = (now.minute // REFRESH_INTERVAL_MINUTES) * REFRESH_INTERVAL_MINUTES
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return slot.strftime("%Y-%m-%dT%H:%M:%S%z")


def seconds_until_next_refresh_slot():
    now = get_kst_now()
    next_minute = ((now.minute // REFRESH_INTERVAL_MINUTES) + 1) * REFRESH_INTERVAL_MINUTES

    if next_minute >= 60:
        next_slot = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_slot = now.replace(minute=next_minute, second=0, microsecond=0)

    return max(1, int((next_slot - now).total_seconds()))


def kst_day_bounds():
    now = get_kst_now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.timestamp(), end.timestamp()


def get_kst_day_key():
    return get_kst_now().strftime("%Y-%m-%d")


def model_state_key(model_name, suffix):
    slug = re.sub(r"[^a-z0-9]+", "_", model_name.lower()).strip("_")
    return f"{slug}::{suffix}"


def get_scheduler_state(state_key):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        row = conn.execute(
            "SELECT state_value FROM scheduler_state WHERE state_key = ?",
            (state_key,),
        ).fetchone()
    return row["state_value"] if row else ""


def set_scheduler_state(state_key, state_value):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_state (state_key, state_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                state_value = excluded.state_value,
                updated_at = excluded.updated_at
            """,
            (state_key, state_value, time.time()),
        )


def clear_scheduler_state(state_key):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM scheduler_state WHERE state_key = ?", (state_key,))


def get_daily_quota_block_reason(model_name):
    blocked_day = get_scheduler_state(model_state_key(model_name, "quota_blocked_day"))
    if blocked_day != get_kst_day_key():
        return ""
    return get_scheduler_state(model_state_key(model_name, "quota_block_reason"))


def get_service_unavailable_cooldown_reason(model_name):
    until_key = model_state_key(model_name, "service_unavailable_until_ts")
    reason_key = model_state_key(model_name, "service_unavailable_reason")
    until_raw = get_scheduler_state(until_key)
    if not until_raw:
        return ""

    try:
        until_ts = float(until_raw)
    except Exception:
        clear_scheduler_state(until_key)
        clear_scheduler_state(reason_key)
        return ""

    if until_ts <= time.time():
        clear_scheduler_state(until_key)
        clear_scheduler_state(reason_key)
        return ""

    return get_scheduler_state(reason_key)


def cleanup_expired_store():
    init_ai_store()
    cutoff = time.time() - 24 * 60 * 60

    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM gemini_request_log WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM slot_attempts WHERE attempted_at < ?", (cutoff,))
        conn.execute("DELETE FROM scheduler_state WHERE updated_at < ?", (cutoff,))
        conn.execute("DELETE FROM refresh_locks WHERE acquired_at < ?", (cutoff,))
        conn.execute("DELETE FROM ai_cache WHERE generated_at < ?", (cutoff,))
        conn.execute("DELETE FROM model_attempt_log WHERE ts < ?", (cutoff,))
        oldest_day = (get_kst_now() - timedelta(days=ARTICLE_RETENTION_DAYS)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM daily_articles WHERE day_key < ?", (oldest_day,))


def acquire_refresh_lock():
    init_ai_store()
    now = time.time()

    with closing(get_db_connection()) as conn:
        conn.execute(
            "DELETE FROM refresh_locks WHERE lock_name = 'ai_refresh' AND acquired_at < ?",
            (now - AI_REFRESH_LOCK_TTL_SECONDS,),
        )

        try:
            conn.execute(
                "INSERT INTO refresh_locks (lock_name, acquired_at) VALUES ('ai_refresh', ?)",
                (now,),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def release_refresh_lock():
    init_ai_store()
    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM refresh_locks WHERE lock_name = 'ai_refresh'")


def get_slot_attempt(refresh_slot):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        return conn.execute(
            "SELECT status, attempted_at, error FROM slot_attempts WHERE refresh_slot = ?",
            (refresh_slot,),
        ).fetchone()


def should_skip_slot(refresh_slot):
    row = get_slot_attempt(refresh_slot)
    if not row:
        return False

    if row["status"] in {"success", "cached", "skipped"}:
        return True

    if row["status"] == "running":
        return time.time() - float(row["attempted_at"]) < AI_REFRESH_LOCK_TTL_SECONDS

    return False


def record_slot_attempt(refresh_slot, status, error=None):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            INSERT INTO slot_attempts (refresh_slot, attempted_at, status, error)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(refresh_slot) DO UPDATE SET
                attempted_at = excluded.attempted_at,
                status = excluded.status,
                error = excluded.error
            """,
            (refresh_slot, time.time(), status, error),
        )


def record_model_attempt(refresh_slot, model_config, attempt_number, status, error=None):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            INSERT INTO model_attempt_log (
                ts, refresh_slot, model, provider, attempt_number, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                refresh_slot,
                model_config["model"],
                model_config["provider"],
                attempt_number,
                status,
                error,
            ),
        )


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
        "cache_version": row["cache_version"],
        "model": row["model"],
        "data": data,
    }


def is_fresh_ai_cache(cache_payload, refresh_slot):
    return cache_payload.get("refresh_slot") == refresh_slot


def save_ai_result(refresh_slot, data, model_name):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        conn.execute(
            """
            INSERT INTO ai_cache (
                cache_key, refresh_slot, generated_at, cache_version, model, data_json
            )
            VALUES ('latest', ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                refresh_slot = excluded.refresh_slot,
                generated_at = excluded.generated_at,
                cache_version = excluded.cache_version,
                model = excluded.model,
                data_json = excluded.data_json
            """,
            (
                refresh_slot,
                time.time(),
                AI_CACHE_VERSION,
                model_name,
                json.dumps(data, ensure_ascii=False),
            ),
        )


def estimate_input_tokens(text):
    return max(1, len(str(text).encode("utf-8")) // 3)


def reserve_model_capacity(input_text, refresh_slot, model_config):
    init_ai_store()
    now = time.time()
    input_tokens = estimate_input_tokens(input_text)
    day_start, day_end = kst_day_bounds()
    model_name = model_config["model"]
    model_rpm = int(model_config["rpm"])
    model_rpd = model_config.get("rpd")
    model_tpm = int(model_config["tpm"])
    model_tpd = model_config.get("tpd")

    with closing(get_db_connection()) as conn:
        conn.execute("DELETE FROM gemini_request_log WHERE ts < ?", (day_start,))
        minute_requests = conn.execute(
            "SELECT COUNT(*) FROM gemini_request_log WHERE ts >= ? AND model = ?",
            (now - 60, model_name),
        ).fetchone()[0]
        minute_input_tokens = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) FROM gemini_request_log WHERE ts >= ? AND model = ?",
            (now - 60, model_name),
        ).fetchone()[0]
        day_requests = conn.execute(
            "SELECT COUNT(*) FROM gemini_request_log WHERE ts >= ? AND ts < ? AND model = ?",
            (day_start, day_end, model_name),
        ).fetchone()[0]
        day_input_tokens = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) FROM gemini_request_log WHERE ts >= ? AND ts < ? AND model = ?",
            (day_start, day_end, model_name),
        ).fetchone()[0]

        if minute_requests + 1 > model_rpm:
            return f"{model_name} rate limit: RPM would be exceeded; skipping this slot."

        if minute_input_tokens + input_tokens > model_tpm:
            return f"{model_name} rate limit: TPM would be exceeded; skipping this slot."

        if model_rpd is not None and day_requests + 1 > int(model_rpd):
            return f"{model_name} rate limit: KST daily requests would be exceeded; skipping this slot."

        if model_tpd and day_input_tokens + input_tokens > int(model_tpd):
            return f"{model_name} rate limit: KST daily input tokens would be exceeded; skipping this slot."

        conn.execute(
            """
            INSERT INTO gemini_request_log (ts, input_tokens, model, refresh_slot)
            VALUES (?, ?, ?, ?)
            """,
            (now, input_tokens, model_name, refresh_slot),
        )

    return None


def normalize_url(url):
    if not url:
        return None
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return "https://media.naver.com" + url
    return url


def collect_news():
    import requests
    from bs4 import BeautifulSoup

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
            results[name] = [{
                "title": "데이터를 불러올 수 없습니다.",
                "url": None,
            }]

    return results


def clean_model_text(text):
    if not text:
        return ""

    cleaned = str(text).strip()
    cleaned = re.sub(r"^```json", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```html", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def extract_first_json_object(text):
    if not text:
        return ""

    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    return ""


def parse_gemini_json(text):
    if not text:
        return None

    cleaned = clean_model_text(text)
    cleaned = cleaned.replace("\ufeff", "").strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    json_candidate = extract_first_json_object(cleaned)
    if json_candidate:
        json_candidate = re.sub(r",\s*([}\]])", r"\1", json_candidate)
        try:
            return json.loads(json_candidate)
        except Exception:
            pass

    return None


def build_json_only_retry_prompt(base_prompt):
    return (
        f"{base_prompt}\n\n"
        "CRITICAL OUTPUT RULE:\n"
        "- Return exactly one valid JSON object.\n"
        "- Do not include markdown, code fences, explanations, or extra text.\n"
        "- The first character must be '{' and the last character must be '}'.\n"
    )


def is_probably_html(text):
    if not text:
        return False
    t = html.unescape(str(text)).strip().lower()
    html_signals = ["<div", "<span", "<p", "<br", "<small", "<a ", "<ul", "<li", "<section"]
    return any(signal in t for signal in html_signals)


def sanitize_ai_text(value):
    from bs4 import BeautifulSoup

    if value is None:
        return ""
    text = html.unescape(clean_model_text(value))
    if is_probably_html(text) or re.search(r"</?[a-z][\s\S]*?>", text, flags=re.IGNORECASE):
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    text = re.sub(r"```(?:html|json)?", "", str(text), flags=re.IGNORECASE)
    text = text.replace("```", "")
    text = re.sub(r"</?[a-z][^>]*?>", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def store_daily_articles(news_data, day_key):
    init_ai_store()
    now = time.time()
    with closing(get_db_connection()) as conn:
        conn.execute("BEGIN")
        for press, articles in news_data.items():
            for article in articles:
                title = (article.get("title") or "").strip()
                if not title or "데이터를 불러올 수 없습니다" in title:
                    continue
                conn.execute(
                    """
                    INSERT INTO daily_articles (day_key, press, title, url, first_seen, last_seen, seen_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(day_key, press, title) DO UPDATE SET
                        url = COALESCE(excluded.url, daily_articles.url),
                        last_seen = excluded.last_seen,
                        seen_count = daily_articles.seen_count + 1
                    """,
                    (day_key, press, title, article.get("url"), now, now),
                )
        conn.execute("COMMIT")


def load_daily_articles(day_key):
    init_ai_store()
    with closing(get_db_connection()) as conn:
        rows = conn.execute(
            """
            SELECT id, press, title, url, first_seen, last_seen, seen_count
            FROM daily_articles WHERE day_key = ?
            ORDER BY seen_count DESC, first_seen ASC
            """,
            (day_key,),
        ).fetchall()
    return [
        {
            "id": f"a{row['id']}",
            "press": row["press"],
            "title": row["title"],
            "url": row["url"],
            "first_seen": row["first_seen"],
            "seen_count": int(row["seen_count"]),
        }
        for row in rows
    ]


def format_articles_for_prompt(articles):
    by_press = {press: [] for press in URLS}
    for article in articles:
        by_press.setdefault(article["press"], []).append(article)

    lines = []
    for press, rows in by_press.items():
        limit = PROMPT_MAX_TARGET_ARTICLES if press == TARGET_PRESS else PROMPT_MAX_ARTICLES_PER_PRESS
        rows = sorted(rows, key=lambda a: (-a["seen_count"], a["first_seen"]))[:limit]
        if not rows:
            continue
        lines.append(f"[{press}]")
        for article in rows:
            title = article["title"].replace("|", " ")
            lines.append(f"{article['id']}|{title}|노출{article['seen_count']}")
    return "\n".join(lines)


def build_ai_persona_prompt(articles, day_key):
    articles_text = format_articles_for_prompt(articles)
    outlet_count = len({a["press"] for a in articles})

    return f"""
당신은 {TARGET_PRESS} 편집국의 보도 모니터링을 돕는 AI 에디터입니다.

아래는 오늘(KST {day_key}) 0시부터 지금까지 10분 간격으로 수집해 누적한 언론사 {outlet_count}곳의 네이버 언론사 홈 주요 기사 제목입니다.
- 형식: 기사ID|제목|노출N
- 노출N은 그 기사가 언론사 홈 주요 기사 영역에 걸려 있던 수집 횟수입니다(1회 = 약 10분). 값이 클수록 그 언론사가 오래, 비중 있게 다룬 기사입니다.
- 기사 본문은 없습니다. 제목에 없는 사실을 추정하거나 단정하지 마세요.

분석 목적:
언론사들이 오늘 중요하게 다룬 이슈를 파악하고, {TARGET_PRESS}가 그 이슈를 누락했거나 소홀히 다뤘는지 판단하는 것입니다.

해야 할 일:
1. 같은 사건·주제를 다룬 기사를 하나의 이슈로 묶으세요. 표현이 달라도 같은 사안이면 같은 이슈입니다.
2. 2곳 이상의 언론사가 다룬 이슈를 최대 {MAX_ISSUES}개 고르세요. 다룬 언론사 수가 많고 노출이 큰 이슈를 우선합니다.
3. article_ids에는 그 이슈에 해당하는 기사 ID를 언론사 구분 없이 빠짐없이 넣으세요. {TARGET_PRESS} 기사가 해당되면 반드시 포함하세요.
4. target_note: 해당 이슈에 대한 {TARGET_PRESS} 보도를 타사와 비교해 1~2문장으로 쓰세요(기사 수, 노출 비중, 관점 차이). {TARGET_PRESS} 기사가 없으면 없다고 쓰세요.
5. suggested_angle: {TARGET_PRESS} 보도가 없거나 약하면 보강 방향을 1문장으로 쓰고, 충분하면 빈 문자열로 두세요.
6. daily_summary: 오늘 언론 전체가 집중한 흐름을 2~3문장으로 요약하세요.
7. target_assessment: 타사 대비 {TARGET_PRESS}의 오늘 보도 특징과 공백을 2~3문장으로 평가하세요.

출력 규칙:
- JSON 객체 하나만 출력하세요. Markdown, HTML, 코드블록, 설명 문장은 금지입니다.
- 문자열 값에 HTML 태그나 class 속성을 넣지 마세요.
- article_ids에는 아래 목록에 실제로 있는 기사ID만 넣으세요.

JSON 스키마:
{{
  "daily_summary": "오늘 흐름 요약",
  "target_assessment": "{TARGET_PRESS} 보도 평가",
  "issues": [
    {{
      "topic": "이슈명(20자 이내)",
      "category": "정치",
      "summary": "이슈 한 줄 요약",
      "article_ids": ["a1", "a2"],
      "target_note": "{TARGET_PRESS} 보도 비교",
      "suggested_angle": "보강 방향 또는 빈 문자열"
    }}
  ]
}}

카테고리는 다음 중 하나만 사용하세요:
정치, 경제, 사회, 국제, 생활, IT·과학, 문화, 스포츠·연예, 오피니언, 기타

기사 목록:
{articles_text}
"""


def build_dashboard_payload(parsed, articles, day_key):
    articles_by_id = {a["id"]: a for a in articles}
    issues = []

    for raw in parsed.get("issues", []) or []:
        if not isinstance(raw, dict):
            continue

        ids = []
        for article_id in raw.get("article_ids", []) or []:
            article_id = str(article_id).strip()
            if article_id in articles_by_id and article_id not in ids:
                ids.append(article_id)
        if not ids:
            continue

        related = sorted((articles_by_id[i] for i in ids), key=lambda a: -a["seen_count"])
        exposure_by_press = {}
        for article in related:
            exposure_by_press[article["press"]] = exposure_by_press.get(article["press"], 0) + article["seen_count"]

        other_exposures = [v for press, v in exposure_by_press.items() if press != TARGET_PRESS]
        target_exposure = exposure_by_press.get(TARGET_PRESS, 0)
        other_median = statistics.median(other_exposures) if other_exposures else 0

        if not target_exposure:
            status = "누락"
        elif target_exposure < other_median * UNDERCOVERED_RATIO:
            status = "소홀"
        else:
            status = "보도"

        issues.append({
            "topic": sanitize_ai_text(raw.get("topic")) or "이슈명 없음",
            "category": sanitize_ai_text(raw.get("category")) or "기타",
            "summary": sanitize_ai_text(raw.get("summary")),
            "target_note": sanitize_ai_text(raw.get("target_note")),
            "suggested_angle": sanitize_ai_text(raw.get("suggested_angle")),
            "outlet_count": len(exposure_by_press),
            "other_outlet_count": len(other_exposures),
            "article_count": len(related),
            "total_exposure": sum(exposure_by_press.values()),
            "target_article_count": sum(1 for a in related if a["press"] == TARGET_PRESS),
            "target_exposure": target_exposure,
            "other_median_exposure": other_median,
            "target_status": status,
            "is_gap": status != "보도" and len(other_exposures) >= MIN_OUTLETS_FOR_GAP,
            "presses": sorted(exposure_by_press, key=lambda p: -exposure_by_press[p]),
            "articles": [
                {"media": a["press"], "title": a["title"], "url": a["url"], "seen_count": a["seen_count"]}
                for a in related
            ],
        })

    issues.sort(key=lambda issue: (-issue["outlet_count"], -issue["total_exposure"]))
    for rank, issue in enumerate(issues, start=1):
        issue["rank"] = rank

    return {
        "day_key": day_key,
        "article_total": len(articles),
        "outlet_total": len({a["press"] for a in articles}),
        "gap_min_outlets": MIN_OUTLETS_FOR_GAP,
        "daily_summary": sanitize_ai_text(parsed.get("daily_summary")),
        "target_assessment": sanitize_ai_text(parsed.get("target_assessment")),
        "issues": issues,
    }


def extract_gemini_text(response):
    text = getattr(response, "text", "")
    if text:
        return text

    parts = []
    try:
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", "")
                if part_text:
                    parts.append(part_text)
    except Exception:
        pass

    return "\n".join(parts).strip()


def call_gemini_model(api_key, model_name, prompt):
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        generation_config={
            "temperature": 0.25,
            "top_p": 0.8,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        },
    )
    response = model.generate_content(prompt)
    return extract_gemini_text(response)


def call_model(model_config, api_key, prompt):
    if model_config["provider"] == "gemini":
        return call_gemini_model(api_key, model_config["model"], prompt)
    raise RuntimeError(f"Unsupported provider: {model_config['provider']}")


def is_daily_quota_exceeded_error(exc):
    message = str(exc).lower()
    return "quota exceeded" in message or ("429" in message and "quota" in message)


def build_daily_quota_block_reason(model_name, exc):
    first_line = str(exc).splitlines()[0].strip()
    return (
        f"{model_name} daily quota is blocked for KST {get_kst_day_key()}. "
        f"Remaining slots will be skipped. Reason: {first_line}"
    )


def is_service_unavailable_error(exc):
    message = str(exc).lower()
    return "503" in message or "service unavailable" in message


def is_transient_retryable_error(exc):
    message = str(exc).lower()
    return (
        is_service_unavailable_error(exc)
        or "timeout" in message
        or "timed out" in message
        or "deadline" in message
        or "temporarily unavailable" in message
    )


def record_service_unavailable_and_maybe_cooldown(model_name, exc):
    count_key = model_state_key(model_name, "service_unavailable_count")
    until_key = model_state_key(model_name, "service_unavailable_until_ts")
    reason_key = model_state_key(model_name, "service_unavailable_reason")
    current_count_raw = get_scheduler_state(count_key)
    try:
        current_count = int(current_count_raw or "0")
    except Exception:
        current_count = 0
    new_count = current_count + 1
    set_scheduler_state(count_key, str(new_count))
    first_line = str(exc).splitlines()[0].strip()
    if new_count < SERVICE_UNAVAILABLE_THRESHOLD:
        return f"{model_name} transient 503 detected: consecutive={new_count}. Reason: {first_line}"
    until_ts = time.time() + SERVICE_UNAVAILABLE_COOLDOWN_SECONDS
    until_text = datetime.fromtimestamp(until_ts, ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    reason = (
        f"{model_name} 503 cooldown active after {new_count} consecutive failures. "
        f"Skipping calls until {until_text} KST. Reason: {first_line}"
    )
    set_scheduler_state(until_key, str(until_ts))
    set_scheduler_state(reason_key, reason)
    return reason


def clear_service_unavailable_state(model_name):
    clear_scheduler_state(model_state_key(model_name, "service_unavailable_count"))
    clear_scheduler_state(model_state_key(model_name, "service_unavailable_until_ts"))
    clear_scheduler_state(model_state_key(model_name, "service_unavailable_reason"))

def refresh_ai_for_current_slot():
    cleanup_expired_store()
    refresh_slot = get_current_refresh_slot()

    if should_skip_slot(refresh_slot):
        print(f"Slot already completed or currently running: {refresh_slot}")
        return 0

    if not acquire_refresh_lock():
        print("Another scheduler is refreshing the cache.")
        return 0

    try:
        cached_result = get_cached_ai_result()
        if (
            isinstance(cached_result, dict)
            and cached_result.get("cache_version") == AI_CACHE_VERSION
            and cached_result.get("data")
            and is_fresh_ai_cache(cached_result, refresh_slot)
        ):
            record_slot_attempt(refresh_slot, "cached")
            print(f"Cache already fresh for slot: {refresh_slot}")
            return 0

        day_key = refresh_slot[:10]
        store_daily_articles(collect_news(), day_key)
        articles = load_daily_articles(day_key)
        if not articles:
            record_slot_attempt(refresh_slot, "skipped", "No articles collected for today.")
            print("No articles collected for today.")
            return 0

        prompt = build_ai_persona_prompt(articles, day_key)
        record_slot_attempt(refresh_slot, "running")
        attempt_errors = []

        for model_config in MODEL_CHAIN:
            model_name = model_config["model"]
            api_key = get_api_key_for_model(model_config)
            if not api_key:
                error = f"{model_name}: API key is not configured"
                record_model_attempt(refresh_slot, model_config, 0, "skipped", error)
                attempt_errors.append(error)
                continue

            max_attempts = int(model_config.get("max_attempts", 1))
            model_prompt = prompt

            for attempt_number in range(1, max_attempts + 1):
                limit_error = reserve_model_capacity(model_prompt, refresh_slot, model_config)
                if limit_error:
                    record_model_attempt(refresh_slot, model_config, attempt_number, "skipped", limit_error)
                    attempt_errors.append(limit_error)
                    break

                try:
                    response_text = call_model(model_config, api_key, model_prompt)
                    parsed = parse_gemini_json(response_text)
                    if not isinstance(parsed, dict):
                        error = f"{model_name}: failed to parse JSON response"
                        record_model_attempt(refresh_slot, model_config, attempt_number, "failed", error)
                        attempt_errors.append(error)
                        if attempt_number < max_attempts:
                            retry_note = f"{model_name}: retrying with JSON-only prompt after parse failure"
                            record_model_attempt(refresh_slot, model_config, attempt_number + 1, "retrying", retry_note)
                            print(retry_note)
                            model_prompt = build_json_only_retry_prompt(prompt)
                            continue
                        break

                    save_ai_result(refresh_slot, build_dashboard_payload(parsed, articles, day_key), model_name)
                    record_model_attempt(refresh_slot, model_config, attempt_number, "success")
                    record_slot_attempt(refresh_slot, "success", model_name)
                    print(f"AI cache refreshed for slot: {refresh_slot} via {model_name}")
                    return 0
                except Exception as exc:
                    error = str(exc).splitlines()[0].strip()
                    record_model_attempt(refresh_slot, model_config, attempt_number, "failed", error)

                    if is_daily_quota_exceeded_error(exc):
                        quota_reason = build_daily_quota_block_reason(model_name, exc)
                        attempt_errors.append(quota_reason)
                        break

                    if attempt_number < max_attempts:
                        time.sleep(5)
                        continue

                    attempt_errors.append(f"{model_name}: {error}")
                    break

        final_error = " | ".join(attempt_errors) if attempt_errors else "No available model succeeded."
        record_slot_attempt(refresh_slot, "skipped", final_error)
        print(final_error)
        return 0
    finally:
        release_refresh_lock()


def run_daemon():
    while True:
        sleep_seconds = seconds_until_next_refresh_slot() + 1
        print(f"Sleeping {sleep_seconds}s until next KST 10-minute slot.")
        time.sleep(sleep_seconds)
        refresh_ai_for_current_slot()


def main():
    parser = argparse.ArgumentParser(description="Refresh the news dashboard AI cache.")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously and refresh at every KST 10-minute slot.",
    )
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
        return 0

    return refresh_ai_for_current_slot()


if __name__ == "__main__":
    raise SystemExit(main())
