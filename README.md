# V2 Signal Terminal — Streamlit 통합 가이드

## 이 폴더 안의 파일
- `app.py` — 기존 `app.py`를 V2 라이트 테마로 다시 쓴 버전. 그대로 레포 루트의 `app.py`를 덮어쓰면 됨.

## 적용 방법
```bash
# 레포 루트에서
cp /path/to/integration/app.py ./app.py
streamlit run app.py
```

## 무엇이 바뀌었나

### 유지된 것 (기존 그대로)
- `st.set_page_config`, 페이지 메타
- SQLite 캐시 / Gemini 결과 로드 (`get_cached_ai_result`, `get_stored_ai_insight`, …)
- 네이버 채널 크롤링 (`collect_news`, `fetch_news`)
- AI 응답 텍스트 살균 (`sanitize_ai_payload`, `clean_model_text`, …)
- `st_autorefresh`, refresh slot 계산
- `URLS` 14개 매체 매핑
- `prompt`와 `analyze_*` 로컬 분석 (이번 V2에서는 사용 안 함 — 추후 fallback 필요시 재사용 가능)

### 새로 추가/변경된 것
1. **CSS 한 블록** (`V2_CSS`) — 라이트 테마 팔레트, Pretendard + JetBrains Mono CDN 로드. Streamlit chrome (메뉴/푸터/사이드바) 숨김.
2. **`BIAS_MAP`** — 14개사 진보/중도/보수 정적 매핑. 정확도 필요하면 외부 JSON으로 분리 권장.
3. **분석 헬퍼**
   - `compute_issue_heat(issue)` — AI scores(1~5) 4개를 평균 × 20으로 0~100 heat 환산
   - `compute_issue_coverage(issue)` — `related_articles` 길이 (최대 14)
   - `compute_heatmap(issues, news_data)` — 이슈 키워드를 14개사 헤드라인과 매칭해 0~3 강도 행렬
   - `compute_keyword_freq(news_data, keywords)` — top_keywords의 출현 빈도
4. **렌더링 함수** — 모두 HTML 문자열 빌더. `st.columns` 대신 CSS Grid로 정확한 레이아웃.
   - `render_topnav` — 상단 터미널 네비
   - `render_header` — 타이틀 + 4-메트릭 스트립
   - `render_flow_and_keywords` — AI 흐름 (키워드 하이라이트) + 키워드 빈도 막대
   - `render_issues` — 6칸 균등 그리드 + heat 도넛 게이지 + 카테고리 컬러블록
   - `render_heatmap` — 이슈 × 언론사 14열 매트릭스
   - `render_missed` — ⚠ 알림 톤 카드
   - `render_press_table` — 14개사 2열 그리드 + bias 점

### 제거된 것 / 호출되지 않음
- 기존 `<style>` 블록 (insight-box, summary-card 등) — V2 CSS가 대체
- `st.title`, `st.subheader`, `st.metric`, `st.columns` 같은 Streamlit 위젯 위주 출력 — 모두 HTML로 단일 emit
- `render_local_missed_articles`, `analyze_missed_articles_local` — V2는 AI missed_articles만 사용 (필요하면 fallback으로 다시 끼울 수 있음)
- `render_ai_dashboard` — `render_*` 함수들로 분해

## AI JSON 호환성
기존 Gemini 프롬프트(`refresh_ai_cache.py`)가 만드는 JSON 구조 그대로 사용합니다:
- `dashboard_summary.overall_trend / top_keywords / editorial_note`
- `issues[].rank / issue_title / category / one_line_summary / why_it_matters / scores / related_articles`
- `missed_articles[].rank / issue_title / why_missed / coverage_signal`

→ **백엔드 스케줄러 수정 불필요**

## 검증 체크리스트
- [ ] `streamlit run app.py` 정상 기동
- [ ] 캐시 비어있을 때 (DB 초기 상태) 경고 카드만 보이는지
- [ ] AI 데이터 있을 때 6개 이슈 카드가 모두 같은 높이로 정렬되는지
- [ ] 히트맵 셀이 0~3 단계로 명도 변화하는지
- [ ] `[속보]` 헤드라인이 빨간색으로 강조되는지
- [ ] 국민일보 카드에 `BASE` 뱃지가 붙는지
- [ ] 모바일 폭에서 그리드 깨지는지 (현재는 1440 데스크탑 기준 — 반응형 필요시 추가 작업)

## 알려진 제약
- **반응형 미적용**: V2는 데스크탑 폭(1280px+) 기준. 좁은 화면에서는 metric strip / 히트맵 / 이슈 그리드가 가로 스크롤됩니다. 필요시 `@media (max-width: 1024px)` 룰을 `V2_CSS`에 추가.
- **카테고리 매핑 4종**: 경제·생활 / 정치·국제 / 사회 / 문화·IT·연예·스포츠·오피니언·기타 — Gemini가 카테고리를 더 세분화하면 `topic_palette_class()`에 케이스 추가.
- **bias 정적 매핑**: 14개사 한정. 신규 매체 추가시 `BIAS_MAP`도 같이 갱신.
