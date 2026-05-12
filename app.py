import streamlit as st
import requests
from bs4 import BeautifulSoup
from collections import Counter
import re
import json
import html
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# 페이지 설정
st.set_page_config(page_title="주요 언론사 뉴스 대시보드", page_icon="📰", layout="wide")

TARGET_PRESS = "국민일보"

# 프리미엄 디자인 적용
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


# 주요 언론사 네이버 채널 URL
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


@st.cache_data(ttl=600)
def fetch_news():
    """
    언론사별 주요 뉴스 제목과 URL을 수집합니다.
    반환 형식:
    {
        "국민일보": [
            {"title": "기사 제목", "url": "https://..."},
            ...
        ]
    }
    """
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

            # 1차: 네이버 언론사 채널 주요 제목 셀렉터
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

            # 2차: 예비 셀렉터
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

            # 3차: 링크 기반 보조 수집
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


def flatten_news_titles(news_data):
    all_titles = []

    for press, articles in news_data.items():
        for article in articles:
            title = article.get("title", "")
            if title and "데이터를 불러올 수 없습니다" not in title:
                all_titles.append(title)

    return all_titles


def analyze_issues(news_data, top_n=3):
    """API 없이 파이썬 로컬 텍스트 분석으로 핵심 토픽을 자동 군집화합니다."""
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
    """
    API 없이 간단히 '다른 언론에는 있는데 국민일보에는 상대적으로 덜 보이는 키워드'를 탐지합니다.
    정확한 이슈 클러스터링은 Gemini 사용 시 더 정교하게 작동합니다.
    """
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
                # 국민일보 제목에 없는 키워드만 후보로
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
    """
    Gemini 2.5 Flash Lite에 주입할 뉴스 분석 페르소나 프롬프트입니다.
    """
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

너는 단순 요약봇이 아니다.
너는 뉴스 편집자, 트렌드 분석가, 추천 알고리즘, 경쟁지 모니터링 에디터의 역할을 동시에 수행한다.

분석 대상은 기사 제목, 언론사명, URL이다.
기사 본문은 제공되지 않는다.
따라서 기사 제목에 없는 사실을 임의로 추정하거나 단정해서는 안 된다.

핵심 이슈 분석 기준은 다음과 같다.

1. 이슈 집중도
- 여러 언론사에서 반복적으로 다루는 주제인가?
- 비슷한 사건, 인물, 기관, 키워드가 여러 기사 제목에서 반복되는가?
- 같은 이슈가 정치, 경제, 사회 등 여러 관점으로 확장되고 있는가?

2. 시의성
- 현재 시점에서 막 발생했거나 오늘의 주요 흐름을 보여주는가?
- 속보성, 긴급성, 업데이트 가능성이 있는가?

3. 사회적 파급력
- 국민 생활, 정책, 경제, 안보, 재난, 사건사고, 사법, 국제 정세 등에 영향이 큰가?
- 단순 화제성보다 실제 영향력이 큰 이슈를 우선한다.

4. 독자 관심도
- 대중이 클릭하거나 알고 싶어 할 가능성이 높은가?
- 유명 인물, 논란, 갈등, 금전, 안전, 부동산, 정치 이벤트, 범죄, 재난, 생활 정보 등 관심 요소가 있는가?

5. 뉴스 가치
- 공공성, 영향성, 갈등성, 의외성, 근접성, 유명성, 지속성을 기준으로 판단한다.
- 단순 자극적 제목이나 낚시성 제목은 과대평가하지 않는다.

6. 중복 제거
- 같은 사건을 다룬 여러 기사는 하나의 이슈로 묶는다.
- 표현만 다르고 본질이 같은 기사는 중복 이슈로 분리하지 않는다.
- 단, 같은 사건이라도 정치적 파장, 경제적 영향, 사회적 논란이 명확히 다르면 하위 관점으로 구분할 수 있다.

추천 기사 기준은 다음과 같다.

1. 제목만 봐도 이슈가 명확히 드러나는 기사
2. 지나치게 자극적이지 않으면서도 클릭 동기가 있는 기사
3. 핵심 사실, 주요 인물, 갈등 구조가 잘 드러나는 기사
4. 여러 언론사가 다룬 이슈라면 가장 대표성이 높은 제목
5. 동일 이슈 내에서 중복 기사가 많을 경우 가장 정보량이 많은 제목
6. 이용자에게 지금 보여줄 가치가 높은 기사

〈우리가 놓친 기사들〉 분석 기준은 다음과 같다.

- 기준 언론사는 반드시 "{TARGET_PRESS}"다.
- "{TARGET_PRESS}"의 기사 목록에 없는 이슈 중, 다른 언론사 여러 곳에서 반복적으로 등장하는 이슈를 우선 제안한다.
- 단순히 제목 표현이 다를 뿐 같은 이슈를 {TARGET_PRESS}가 이미 다루고 있다면 "놓친 기사"로 분류하지 않는다.
- 다른 언론 1곳만 다룬 단독성 기사보다, 여러 언론이 동시에 다룬 공통 이슈를 우선한다.
- 정치, 경제, 사회, 사건사고, 국제, 생활 영향이 큰 이슈를 우선한다.
- 연예, 스포츠, 단순 화제성 이슈는 중요도가 높지 않으면 후순위로 둔다.
- 제안 시에는 "{TARGET_PRESS}가 어떤 앵글로 다루면 좋은지"를 반드시 포함한다.
- 참고 기사는 반드시 입력 기사 목록에 있는 타 언론 기사만 사용한다.

주의사항:
- 기사 제목에 없는 세부 사실을 만들어내지 마라.
- 특정 정치 성향이나 언론사 관점을 편들지 마라.
- 제목이 모호하면 "제목 기준 추정"이라고 표시하라.
- 루머, 의혹, 단독 보도는 확정 사실처럼 표현하지 마라.
- 추천 기사는 반드시 입력된 기사 목록 안에서만 선택하라.
- 기사 본문을 읽은 것처럼 말하지 마라.
- 결과는 한국어로 작성하라.

카테고리는 반드시 아래 중 하나만 사용하라.
정치, 경제, 사회, 국제, 생활, IT·과학, 문화, 스포츠, 연예, 오피니언, 기타

점수는 1점부터 5점까지 정수로 부여하라.
- 5점: 매우 높음
- 4점: 높음
- 3점: 보통
- 2점: 낮음
- 1점: 매우 낮음

내부적으로 다음 순서로 판단하라.
1단계: 기사 제목에서 핵심 키워드, 인물, 기관, 사건명을 추출한다.
2단계: 유사한 제목을 같은 이슈로 클러스터링한다.
3단계: 각 클러스터의 기사 수, 언론사 수, 시의성, 파급력을 평가한다.
4단계: 중복 이슈를 제거한다.
5단계: 핵심 이슈 6개를 중요도 순으로 정렬한다.
6단계: 각 이슈에서 가장 대표적인 노출 추천 기사를 1개 선정한다.
7단계: {TARGET_PRESS} 기사 목록과 타 언론 기사 목록을 비교한다.
8단계: 타 언론에는 반복 등장하지만 {TARGET_PRESS}에는 없는 이슈를 〈우리가 놓친 기사들〉로 정리한다.
9단계: 대시보드에 보여줄 전체 흐름 요약과 키워드를 생성한다.

단, 위 사고 과정은 출력하지 말고 최종 결과만 출력하라.

반드시 아래 JSON 형식으로만 출력하라.
마크다운 코드블록을 사용하지 마라.
JSON 외의 설명 문장을 출력하지 마라.

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
    """
    Gemini 응답에서 JSON을 안전하게 파싱합니다.
    혹시 코드블록이 섞여도 최대한 복구합니다.
    """
    if not text:
        return None

    cleaned = text.strip()

    cleaned = re.sub(r"^```json", "", cleaned)
    cleaned = re.sub(r"^```", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
    except Exception:
        return None

    return None


def generate_ai_insight(news_data, api_key):
    """
    Gemini API를 이용한 실시간 AI 인사이트 도출.
    페르소나를 주입하고 JSON 구조로 결과를 받습니다.
    """
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            "gemini-2.5-flash-lite",
            generation_config={
                "temperature": 0.25,
                "top_p": 0.8,
                "max_output_tokens": 6500,
                "response_mime_type": "application/json"
            }
        )

        prompt = build_ai_persona_prompt(news_data)
        response = model.generate_content(prompt)

        parsed = parse_gemini_json(response.text)

        if parsed is None:
            return {
                "error": "AI 응답을 JSON으로 파싱하지 못했습니다.",
                "raw": response.text
            }

        return parsed

    except Exception as e:
        return {
            "error": f"AI 인사이트를 생성하는 중 오류가 발생했습니다. API Key와 할당량을 확인해주세요. 상세: {e}",
            "raw": None
        }


def render_ai_dashboard(ai_data):
    """
    Gemini가 생성한 JSON 결과를 Streamlit 대시보드에 렌더링합니다.
    """
    if not ai_data:
        st.warning("AI 분석 결과가 없습니다.")
        return

    if ai_data.get("error"):
        st.error(ai_data["error"])

        if ai_data.get("raw"):
            with st.expander("AI 원문 응답 보기"):
                st.text(ai_data["raw"])

        return

    summary = ai_data.get("dashboard_summary", {})
    issues = ai_data.get("issues", [])
    missed_articles = ai_data.get("missed_articles", [])

    overall_trend = summary.get("overall_trend", "")
    top_keywords = summary.get("top_keywords", [])
    editorial_note = summary.get("editorial_note", "")

    st.markdown(
        f"""
        <div class="summary-card">
            <h3>📌 오늘의 전체 뉴스 흐름</h3>
            <p>{html.escape(overall_trend)}</p>
            <p><b>핵심 키워드:</b> {", ".join([html.escape(str(k)) for k in top_keywords])}</p>
            <p><b>편집 코멘트:</b> {html.escape(editorial_note)}</p>
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
            category = issue.get("category", "기타")
            one_line_summary = issue.get("one_line_summary", "")
            why_it_matters = issue.get("why_it_matters", "")
            recommended = issue.get("recommended_article", {}) or {}
            scores = issue.get("scores", {}) or {}
            editor_comment = issue.get("editor_comment", "")

            rec_media = recommended.get("media", "")
            rec_title = recommended.get("title", "")
            rec_url = recommended.get("url")
            rec_reason = recommended.get("reason", "")

            importance = scores.get("importance", "-")
            virality = scores.get("virality", "-")
            reader_interest = scores.get("reader_interest", "-")
            freshness = scores.get("freshness", "-")

            rec_link_html = html.escape(rec_title)

            if rec_url:
                rec_link_html = f"<a href='{html.escape(str(rec_url))}' target='_blank'>{html.escape(rec_title)}</a>"

            st.markdown(
                f"""
                <div class="issue-card">
                    <div class="issue-rank">#{rank}</div>
                    <div class="issue-title">{html.escape(issue_title)}</div>
                    <div class="issue-category">{html.escape(category)}</div>
                    <p><b>요약:</b> {html.escape(one_line_summary)}</p>
                    <p><b>중요한 이유:</b> {html.escape(why_it_matters)}</p>

                    <div>
                        <span class="score-badge">중요도 {importance}</span>
                        <span class="score-badge">확산성 {virality}</span>
                        <span class="score-badge">관심도 {reader_interest}</span>
                        <span class="score-badge">신선도 {freshness}</span>
                    </div>

                    <div class="recommended-box">
                        <b>✅ 추천 노출 기사</b><br>
                        <small>{html.escape(rec_media)}</small><br>
                        {rec_link_html}<br>
                        <small>{html.escape(rec_reason)}</small>
                    </div>

                    <p style="margin-top:12px;"><b>편집 코멘트:</b> {html.escape(editor_comment)}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

            related_articles = issue.get("related_articles", [])

            with st.expander(f"관련 기사 보기 - {issue_title}"):
                if related_articles:
                    for article in related_articles:
                        media = article.get("media", "")
                        title = article.get("title", "")
                        url = article.get("url")

                        if url:
                            st.markdown(f"- [{media}] [{title}]({url})")
                        else:
                            st.markdown(f"- [{media}] {title}")
                else:
                    st.caption("관련 기사 정보가 없습니다.")

    st.markdown("---")
    st.markdown(f"### 🧭 우리가 놓친 기사들")
    st.caption(f"기준: {TARGET_PRESS} 주요 뉴스 목록에 없지만 타 언론에서 반복적으로 다루는 이슈")

    if not missed_articles:
        st.success(f"현재 기준으로 {TARGET_PRESS}가 뚜렷하게 놓친 주요 이슈는 발견되지 않았습니다.")
        return

    missed_cols = st.columns(2)

    for idx, item in enumerate(missed_articles[:5]):
        with missed_cols[idx % 2]:
            rank = item.get("rank", idx + 1)
            issue_title = item.get("issue_title", "이슈명 없음")
            category = item.get("category", "기타")
            why_missed = item.get("why_missed", "")
            coverage_signal = item.get("coverage_signal", "")
            suggested_angle = item.get("suggested_angle", "")
            urgency_score = item.get("urgency_score", "-")

            st.markdown(
                f"""
                <div class="missed-card">
                    <div class="missed-rank">#{rank} 놓친 후보</div>
                    <div class="issue-title">{html.escape(issue_title)}</div>
                    <div class="missed-badge">{html.escape(category)}</div>
                    <p><b>판단 이유:</b> {html.escape(why_missed)}</p>
                    <p><b>타 언론 보도 신호:</b> {html.escape(coverage_signal)}</p>
                    <span class="urgency-badge">긴급도 {urgency_score}</span>

                    <div class="missed-recommend-box">
                        <b>📝 국민일보 추천 앵글</b><br>
                        {html.escape(suggested_angle)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            reference_articles = item.get("reference_articles", [])

            with st.expander(f"참고 기사 보기 - {issue_title}"):
                if reference_articles:
                    for article in reference_articles:
                        media = article.get("media", "")
                        title = article.get("title", "")
                        url = article.get("url")

                        if url:
                            st.markdown(f"- [{media}] [{title}]({url})")
                        else:
                            st.markdown(f"- [{media}] {title}")
                else:
                    st.caption("참고 기사 정보가 없습니다.")


def render_local_missed_articles(news_data):
    """
    API 키가 없을 때 로컬 방식으로 우리가 놓친 기사 후보를 표시합니다.
    """
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
                    <div style="font-weight:800;color:#e07b00;">#{item['rank']} 놓친 후보</div>
                    <h3>{html.escape(item['issue_title'])}</h3>
                    <p><b>판단:</b> {html.escape(item['why_missed'])}</p>
                    <p><b>신호:</b> {html.escape(item['coverage_signal'])}</p>
                    <p><b>제안:</b> {html.escape(item['suggested_angle'])}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

            with st.expander(f"참고 기사 - {item['issue_title']}"):
                refs = item.get("reference_articles", [])
                if refs:
                    for ref in refs:
                        media = ref.get("media", "")
                        title = ref.get("title", "")
                        url = ref.get("url")

                        if url:
                            st.markdown(f"- [{media}] [{title}]({url})")
                        else:
                            st.markdown(f"- [{media}] {title}")
                else:
                    st.caption("참고 기사 정보가 없습니다.")


# --- 사이드바 설정 ---
with st.sidebar:
    st.header("⚙️ 대시보드 설정")

    api_key = st.text_input(
        "Gemini API Key 선택사항",
        type="password",
        help="API 키를 입력하면 Gemini 2.5 Flash Lite가 실시간 뉴스를 심층 분석합니다."
    )

    st_autorefresh(interval=600 * 1000, limit=None, key="news_autorefresh")

    st.markdown("---")

    if st.button("🔄 최신 뉴스 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    tz_kst = pytz.timezone("Asia/Seoul")
    st.caption(f"마지막 업데이트:\n{datetime.now(tz_kst).strftime('%Y-%m-%d %H:%M:%S')} KST")
    st.caption(f"모니터링 기준 언론사: {TARGET_PRESS}")


# --- 메인 화면 ---
st.title("📰 뉴스 트렌드 & 인사이트 대시보드")
st.markdown(
    f"주요 언론사 네이버 채널의 실시간 주요 뉴스와 핵심 인사이트를 한눈에 파악하세요. "
    f"현재 〈우리가 놓친 기사들〉 기준 언론사는 **{TARGET_PRESS}**입니다."
)

# 뉴스 데이터 로드
with st.spinner("언론사별 주요 뉴스를 수집 중입니다..."):
    news_data = fetch_news()


# --- 1. 인사이트 섹션 ---
st.markdown("<div class='insight-box'>", unsafe_allow_html=True)

if api_key:
    st.markdown(
        f"<div class='insight-title'>💡 Gemini 2.5 Flash Lite 뉴스 트렌드 에디터 분석</div>",
        unsafe_allow_html=True
    )

    with st.spinner("Gemini 2.5 Flash Lite가 핵심 이슈 6개와 우리가 놓친 기사를 분석하고 있습니다..."):
        ai_insight = generate_ai_insight(news_data, api_key)
        render_ai_dashboard(ai_insight)

else:
    st.markdown("<div class='insight-title'>💡 실시간 핵심 토픽 분석 No API</div>", unsafe_allow_html=True)
    st.markdown(
        "API 키가 입력되지 않아 **파이썬 로컬 자동 분석 모드**로 대체하여 보여줍니다. "
        "좌측 메뉴에 API 키를 입력하면 Gemini가 **핵심 이슈 6개, 추천 기사, 우리가 놓친 기사들**을 분석합니다.",
        unsafe_allow_html=True
    )
    st.write("")

    issues = analyze_issues(news_data, top_n=3)

    if not issues:
        st.markdown("현재 충분한 뉴스 데이터를 수집하지 못했습니다.")
    else:
        cols = st.columns(3)

        for idx, issue in enumerate(issues):
            with cols[idx]:
                st.markdown(
                    f"<h3 style='color: #a8e6cf;'>🔥 #{idx + 1} {html.escape(issue['keyword'])} "
                    f"<span style='font-size: 1rem; color: #e0e0e0;'>({issue['count']}건)</span></h3>",
                    unsafe_allow_html=True
                )

                for title in issue["titles"]:
                    st.markdown(f"- {title}")

    render_local_missed_articles(news_data)

st.markdown("</div>", unsafe_allow_html=True)


# --- 2. 각 언론사별 주요뉴스 박스 ---
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
            f"<div class='press-title'>{html.escape(press)}{target_label}</div>"
        )

        if not articles or "데이터를 불러올 수 없습니다" in articles[0].get("title", ""):
            html_content += "<div class='news-item'>최신 뉴스를 불러오지 못했습니다.</div>"
        else:
            for article in articles:
                title = article.get("title", "")
                url = article.get("url")

                safe_title = html.escape(title)

                if url:
                    safe_url = html.escape(str(url))
                    html_content += f"<div class='news-item'><a href='{safe_url}' target='_blank'>{safe_title}</a></div>"
                else:
                    html_content += f"<div class='news-item'>{safe_title}</div>"

        html_content += "</div>"

        st.markdown(html_content, unsafe_allow_html=True)
