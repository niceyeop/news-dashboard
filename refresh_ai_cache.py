import argparse
from contextlib import closing
from datetime import datetime, timedelta
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from zoneinfo import ZoneInfo


TARGET_PRESS = "국민일보"
AI_CACHE_VERSION = "minimal-fields-v1"
PRIMARY_MODEL_NAME = "gemini-3.1-flash-lite"
REFRESH_INTERVAL_MINUTES = 10
SERVICE_UNAVAILABLE_THRESHOLD = 2
SERVICE_UNAVAILABLE_COOLDOWN_SECONDS = 30 * 60
AI_CACHE_DIR = Path(os.getenv("NEWS_DASHBOARD_CACHE_DIR", ".news_dashboard_cache"))
AI_DB_PATH = AI_CACHE_DIR / "news_dashboard_cache.sqlite3"
AI_REFRESH_LOCK_TTL_SECONDS = 120

MODEL_CHAIN = [
    {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "api_keys": ["GEMINI_API_KEY"],
        "rpm": 14,
        "rpd": 144,
        "tpm": 240_000,
        "tpd": None,
    },
    {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_keys": ["GROQ_API_KEY", "LLAMA_API_KEY"],
        "rpm": 30,
        "rpd": 1_000,
        "tpm": 12_000,
        "tpd": 100_000,
    },
    {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "api_keys": ["GROQ_API_KEY", "GPT_OSS_API_KEY"],
        "rpm": 30,
        "rpd": 1_000,
        "tpm": 8_000,
        "tpd": 200_000,
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
    model_rpd = int(model_config["rpd"])
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
            return f"{model_name} ?? ??: ?? ?? ?? ???? ??? ?? ??? ?????."

        if minute_input_tokens + input_tokens > model_tpm:
            return f"{model_name} ?? ??: ?? ?? ?? ?? ???? ??? ?? ??? ?????."

        if day_requests + 1 > model_rpd:
            return f"{model_name} ?? ??: KST ?? ?? ?? ???? ??? ?? ??? ?????."

        if model_tpd and day_input_tokens + input_tokens > int(model_tpd):
            return f"{model_name} ?? ??: KST ?? ?? ?? ?? ???? ??? ?? ??? ?????."

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


def sanitize_ai_payload(ai_data):
    if not isinstance(ai_data, dict):
        return ai_data

    summary = ai_data.get("dashboard_summary")
    if isinstance(summary, dict):
        for key in ["overall_trend", "editorial_note"]:
            summary[key] = sanitize_ai_text(summary.get(key, ""))
        summary["top_keywords"] = [
            clean_keyword
            for keyword in summary.get("top_keywords", []) or []
            for clean_keyword in [sanitize_ai_text(keyword)]
            if clean_keyword
        ]

    for issue in ai_data.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue
        for key in ["issue_title", "category", "one_line_summary", "why_it_matters", "editor_comment"]:
            issue[key] = sanitize_ai_text(issue.get(key, ""))

    for item in ai_data.get("missed_articles", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ["issue_title", "category", "why_missed", "coverage_signal", "suggested_angle"]:
            item[key] = sanitize_ai_text(item.get(key, ""))

    return ai_data


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
                    "url": url,
                })

    articles_json = json.dumps(input_articles, ensure_ascii=False, indent=2)

    return f"""
너는 “뉴스 트렌드 에디터 AI”다.

주요 언론사의 네이버채널 뉴스 제목 목록을 분석해 현재 핵심 뉴스 이슈 6개를 정리하고,
{TARGET_PRESS} 주요 뉴스 목록에는 보이지 않지만 타 언론에서 반복되는 이슈를 찾아라.

중요:
- 기사 본문은 제공되지 않는다.
- 기사 제목에 없는 사실을 임의로 추정하거나 단정하지 마라.
- 결과는 반드시 JSON만 출력하라.
- HTML, Markdown, 코드블록을 절대 출력하지 마라.
- 어떤 문자열 값에도 <div>, <span>, <p>, <br>, <a>, class=, ``` 같은 조각을 넣지 마라.

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
- URL이 없는 경우 null로 표시하라.

[기사 목록]
{articles_json}
"""


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
            "max_output_tokens": 12000,
            "response_mime_type": "application/json",
        },
    )
    response = model.generate_content(prompt)
    return extract_gemini_text(response)


def call_groq_model(api_key, model_name, prompt):
    import requests

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.25,
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code} {response.text}")
    payload = response.json()
    return (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def call_model(model_config, api_key, prompt):
    if model_config["provider"] == "gemini":
        return call_gemini_model(api_key, model_config["model"], prompt)
    if model_config["provider"] == "groq":
        return call_groq_model(api_key, model_config["model"], prompt)
    raise RuntimeError(f"Unsupported provider: {model_config['provider']}")


def is_daily_quota_exceeded_error(exc):
    message = str(exc).lower()
    return "quota exceeded" in message or ("429" in message and "quota" in message)


def build_daily_quota_block_reason(model_name, exc):
    first_line = str(exc).splitlines()[0].strip()
    return f"{model_name} ?? ??? ?? ???? KST {get_kst_day_key()} ?? ??? ?????. ??: {first_line}"


def is_service_unavailable_error(exc):
    message = str(exc).lower()
    return "503" in message or "service unavailable" in message


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
        return f"{model_name} 503 ?? ??: ?? {new_count}? ??. ??: {first_line}"
    until_ts = time.time() + SERVICE_UNAVAILABLE_COOLDOWN_SECONDS
    until_text = datetime.fromtimestamp(until_ts, ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")
    reason = f"{model_name} 503 ??? ?? {new_count}? ??? {until_text} KST?? ?? ??? ?????. ??: {first_line}"
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

        news_data = collect_news()
        prompt = build_ai_persona_prompt(news_data)
        record_slot_attempt(refresh_slot, "running")
        attempt_errors = []

        for model_config in MODEL_CHAIN:
            model_name = model_config["model"]
            api_key = get_api_key_for_model(model_config)
            if not api_key:
                attempt_errors.append(f"{model_name}: API key is not configured")
                continue

            daily_quota_block_reason = get_daily_quota_block_reason(model_name)
            if daily_quota_block_reason:
                attempt_errors.append(daily_quota_block_reason)
                continue

            service_unavailable_cooldown_reason = get_service_unavailable_cooldown_reason(model_name)
            if service_unavailable_cooldown_reason:
                attempt_errors.append(service_unavailable_cooldown_reason)
                continue

            limit_error = reserve_model_capacity(prompt, refresh_slot, model_config)
            if limit_error:
                attempt_errors.append(limit_error)
                continue

            try:
                response_text = call_model(model_config, api_key, prompt)
                parsed = parse_gemini_json(response_text)
                if parsed is None:
                    attempt_errors.append(f"{model_name}: failed to parse JSON response")
                    continue

                save_ai_result(refresh_slot, sanitize_ai_payload(parsed), model_name)
                clear_service_unavailable_state(model_name)
                record_slot_attempt(refresh_slot, "success", model_name)
                print(f"AI cache refreshed for slot: {refresh_slot} via {model_name}")
                return 0
            except Exception as exc:
                if is_daily_quota_exceeded_error(exc):
                    quota_reason = build_daily_quota_block_reason(model_name, exc)
                    set_scheduler_state(model_state_key(model_name, "quota_blocked_day"), get_kst_day_key())
                    set_scheduler_state(model_state_key(model_name, "quota_block_reason"), quota_reason)
                    attempt_errors.append(quota_reason)
                    continue
                if is_service_unavailable_error(exc):
                    cooldown_reason = record_service_unavailable_and_maybe_cooldown(model_name, exc)
                    attempt_errors.append(cooldown_reason)
                    continue
                attempt_errors.append(f"{model_name}: {str(exc).splitlines()[0].strip()}")

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
