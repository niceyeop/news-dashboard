import streamlit as st
import requests
from bs4 import BeautifulSoup
from collections import Counter
import re
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# 페이지 설정
st.set_page_config(page_title="주요 언론사 뉴스 대시보드", page_icon="📰", layout="wide")

# 프리미엄 디자인 적용 (Aesthetics)
st.markdown("""
<style>
    /* 인사이트 박스 디자인 */
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
    /* 언론사별 뉴스 박스 디자인 */
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
</style>
""", unsafe_allow_html=True)

# 주요 언론사 네이버 채널 URL
URLS = {
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

@st.cache_data(ttl=600)
def fetch_news():
    results = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, url in URLS.items():
        try:
            r = requests.get(url, headers=headers)
            r.encoding = 'utf-8'
            soup = BeautifulSoup(r.text, 'html.parser')
            # 네이버 모바일/PC 구조에 맞춘 셀렉터
            titles = [t.text.strip() for t in soup.select('.press_news_text')]
            if not titles:
                titles = [t.text.strip() for t in soup.select('.cjs_t')] # 예비 셀렉터
            results[name] = titles[:6] # 언론사별 주요 뉴스 최대 6개 추출
        except Exception as e:
            results[name] = [f"데이터를 불러올 수 없습니다."]
    return results

def analyze_issues(news_data, top_n=3):
    """API 없이 파이썬 로컬 텍스트 분석으로 핵심 토픽을 자동 군집화합니다."""
    all_titles = []
    for titles in news_data.values():
        all_titles.extend(titles)
        
    # 뉴스 기사에 흔히 쓰이는 불용어(Stopwords) 정의
    stopwords = set([
        "위해", "대한", "하는", "결국", "다시", "오늘", "내일", "어제", "부터", "까지", 
        "있는", "없는", "에서", "으로", "어떻게", "이런", "입니다", "합니다", "않다", 
        "없다", "있다", "된다", "한다", "종합", "속보", "단독", "포토", "영상", "뉴스"
    ])
    
    words = []
    for title in all_titles:
        # 특수기호 제거 (알파벳, 한글, 숫자만 남김)
        clean_title = re.sub(r'[^\w\s]', ' ', title)
        for w in clean_title.split():
            # 2글자 이상, 불용어가 아닌 단어, 숫자로만 이루어지지 않은 단어 필터링
            if len(w) > 1 and w not in stopwords and not w.isdigit():
                words.append(w)
                
    # 가장 많이 등장한 키워드 추출
    counter = Counter(words)
    top_keywords = counter.most_common(top_n)
    
    issues = []
    for keyword, count in top_keywords:
        related_titles = []
        for title in all_titles:
            # 원문에 해당 키워드가 포함되어 있으면 연관 기사로 분류
            if keyword in title and title not in related_titles:
                related_titles.append(title)
        
        issues.append({
            "keyword": keyword,
            "count": count,
            "titles": related_titles[:4] # 대표 기사 최대 4개 노출
        })
        
    return issues

def generate_ai_insight(news_data, api_key):
    """Gemini API를 이용한 실시간 AI 인사이트 도출"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # 요청하신 gemini-2.5-flash-lite 모델 사용
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        
        all_titles = "\n".join([f"[{press}] " + " / ".join(titles) for press, titles in news_data.items() if titles])
        prompt = f"다음은 현재 한국 주요 언론사들의 네이버 뉴스 채널 헤드라인입니다.\n\n{all_titles}\n\n이 제목들을 분석하여 현재 가장 많이 다뤄지고 있는 핵심 이슈 3가지를 추출하고, '어떤 뉴스가 많이 선정되고 있는지' 명확하고 심층적인 인사이트를 제시해 주세요. 가독성 좋게 마크다운과 이모지를 사용해서 작성해주세요."
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ AI 인사이트를 생성하는 중 오류가 발생했습니다. (API Key와 할당량을 확인해주세요)\n\n에러 상세: {e}"

# --- 사이드바 설정 ---
with st.sidebar:
    st.header("⚙️ 대시보드 설정")
    
    # Gemini API Key 입력창
    api_key = st.text_input("Gemini API Key (선택사항)", type="password", help="API 키를 입력하면 Gemini 2.5 Flash Lite가 실시간 뉴스를 심층 분석합니다.")
    
    # 10분(600000 밀리초) 간격으로 대시보드 자동 새로고침
    st_autorefresh(interval=600 * 1000, limit=None, key="news_autorefresh")
    st.markdown("---")
    if st.button("🔄 최신 뉴스 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    tz_kst = pytz.timezone('Asia/Seoul')
    st.caption(f"마지막 업데이트:\n{datetime.now(tz_kst).strftime('%Y-%m-%d %H:%M:%S')} KST")

# --- 메인 화면 ---
st.title("📰 뉴스 트렌드 & 인사이트 대시보드")
st.markdown("주요 언론사 네이버 채널의 실시간 주요 뉴스와 핵심 인사이트를 한눈에 파악하세요.")

# 뉴스 데이터 로드
with st.spinner("언론사별 주요 뉴스를 수집 중입니다..."):
    news_data = fetch_news()

# --- 1. 인사이트 섹션 (가장 위에 노출) ---
st.markdown("<div class='insight-box'>", unsafe_allow_html=True)

if api_key:
    st.markdown("<div class='insight-title'>💡 Gemini 2.5 Flash Lite 실시간 인사이트 분석</div>", unsafe_allow_html=True)
    with st.spinner("Gemini 2.5 Flash Lite가 실시간 뉴스를 분석하고 있습니다..."):
        ai_insight = generate_ai_insight(news_data, api_key)
        st.markdown(ai_insight)
else:
    st.markdown("<div class='insight-title'>💡 실시간 핵심 토픽 분석 (No API)</div>", unsafe_allow_html=True)
    st.markdown("API 키가 입력되지 않아 **파이썬 로컬 자동 분석 모드**로 대체하여 보여줍니다. 좌측 메뉴에 API 키를 입력하면 더욱 심층적인 AI 기반 요약을 볼 수 있습니다.", unsafe_allow_html=True)
    st.write("")

    issues = analyze_issues(news_data, top_n=3)

    if not issues:
        st.markdown("현재 충분한 뉴스 데이터를 수집하지 못했습니다.")
    else:
        cols = st.columns(3)
        for idx, issue in enumerate(issues):
            with cols[idx]:
                # CSS를 약간 가미하여 토픽 카드 생성
                st.markdown(f"<h3 style='color: #a8e6cf;'>🔥 #{idx+1} {issue['keyword']} <span style='font-size: 1rem; color: #e0e0e0;'>({issue['count']}건)</span></h3>", unsafe_allow_html=True)
                for title in issue['titles']:
                    st.markdown(f"- {title}")

st.markdown("</div>", unsafe_allow_html=True)

# --- 2. 각 언론사별 주요뉴스 박스 ---
st.subheader("📰 언론사별 주요 뉴스")
st.write("") # 간격 띄우기

# 그리드 형태로 3열 배치
cols = st.columns(3)
press_names = list(news_data.keys())

for idx, press in enumerate(press_names):
    col_idx = idx % 3
    with cols[col_idx]:
        articles = news_data[press]
        
        # HTML을 사용하여 커스텀 뉴스 박스 렌더링
        html_content = f"<div class='news-box'><div class='press-title'>{press}</div>"
        
        if not articles or "데이터를 불러올 수 없습니다" in articles[0]:
            html_content += "<div class='news-item'>최신 뉴스를 불러오지 못했습니다.</div>"
        else:
            for title in articles:
                # 텍스트 이스케이프 (따옴표 처리)
                safe_title = title.replace("'", "&#39;").replace('"', "&quot;")
                html_content += f"<div class='news-item'>{safe_title}</div>"
                
        html_content += "</div>"
        st.markdown(html_content, unsafe_allow_html=True)

