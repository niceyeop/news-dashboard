import React from "react";
import "./NewsDashboardDesign.css";

// Sample news data extracted from the source HTML.
// Replace this prop with live dashboard data when wiring into an app.
const sampleNewsDashboardData = {
  meta: {
    title: '뉴스 트렌드 & 인사이트 대시보드',
    subtitle: '주요 언론사의 네이버 뉴스 제목을 바탕으로 현재 뉴스 흐름과 AI 분석 결과를 한 화면에서 확인합니다.',
    baseline: '국민일보',
    lastAnalysis: '05-18 13:50:29',
    model: 'gemini-3.1-flash-lite',
    aiCalls: 93,
    aiQuota: 400,
    lastSlot: '05-18T13:50:00+0900',
  },
  flow: {
    summary:
      '삼성전자 노조의 파업 강행과 법원의 쟁의 제한 결정이 경제 및 사회면의 핵심 이슈로 부상했습니다. 이와 함께 5·18 민주화운동 기념일 관련 메시지와 역사 왜곡 논란, 칸 영화제 등 문화계 소식이 주요하게 다뤄지고 있습니다.',
    keywords: ['삼성전자', '노조', '파업', '법원', '역사왜곡', '5·18', '칸영화제', '에어부산'],
    editorial:
      '삼성전자 노사 갈등이 산업계 전반에 미칠 영향과 법적 판단의 의미를 심층 분석하고, 노조의 강경 발언에 대한 사회적 비판 여론을 균형 있게 다룰 필요가 있습니다.',
  },
  issues: [
    {
      n: 1,
      title: '삼성전자 노조 파업 및 법원 가처분 결정',
      summary: '법원이 삼성전자 노조의 파업 방식에 제약을 두는 가처분 결정을 내렸으나 노조가 쟁의 강행 의지를 밝힘.',
      why: '국가 핵심 산업인 삼성전자의 생산 차질 우려와 노동권·경영권 충돌의 상징적 사례이기 때문.',
      heat: 98,
      coverage: 14,
      topic: '경제',
    },
    {
      n: 2,
      title: '5·18 민주화운동 기념일 메시지',
      summary: '대통령의 5·18 정신 헌법 전문 수록 의지 표명과 기념식 관련 정치권의 행보.',
      why: '국가 통합과 과거사 청산이라는 정치적 상징성이 매우 크기 때문.',
      heat: 91,
      coverage: 13,
      topic: '정치',
    },
    {
      n: 3,
      title: "드라마 '대군부인' 역사 왜곡 논란",
      summary: '드라마의 역사 왜곡 논란에 대해 역사 강사 최태성 등이 비판하며 사회적 공분이 확산됨.',
      why: '대중 매체의 역사 인식에 대한 사회적 책임과 비판적 수용이 중요해졌기 때문.',
      heat: 76,
      coverage: 9,
      topic: '문화',
    },
    {
      n: 4,
      title: "나홍진 감독 영화 '호프' 칸 영화제 호평",
      summary: "나홍진 감독의 신작 '호프'가 칸 영화제에서 7분간 기립박수를 받으며 화제.",
      why: '한국 영화의 글로벌 위상과 예술적 성취를 보여주는 지표이기 때문.',
      heat: 72,
      coverage: 10,
      topic: '문화',
    },
    {
      n: 5,
      title: '에어부산 여객기 대만 착륙 실패',
      summary: '에어부산 여객기가 대만에서 강풍으로 인해 두 차례 착륙에 실패하고 회항함.',
      why: '항공 안전과 직결된 사안으로 승객들의 안전 우려가 크기 때문.',
      heat: 68,
      coverage: 7,
      topic: '사회',
    },
    {
      n: 6,
      title: '택배사 갑질 과징금 부과',
      summary: '쿠팡 등 5개 택배사가 안전사고 책임을 영업점에 전가하는 특약을 강요해 과징금 30억 원 부과됨.',
      why: '대기업의 불공정 거래 관행을 바로잡는 공정위의 조치이기 때문.',
      heat: 64,
      coverage: 8,
      topic: '경제',
    },
  ],
  missed: [
    {
      n: 1,
      title: '정신병원 환자 폭행 사건',
      reason: '국민일보 주요 뉴스 목록에서 제외되었으나 타 언론사에서 비중 있게 다룸.',
      where: '문화일보, 서울신문 등 다수 언론이 보도함.',
    },
    {
      n: 2,
      title: '2차 고유가 지원금 신청',
      reason: '국민일보 주요 뉴스 목록에서 제외됨.',
      where: '연합뉴스, 뉴시스 등 통신사에서 주요하게 보도함.',
    },
  ],
  press: [
    {
      name: '국민일보',
      tag: '기준 언론사',
      bias: 'C',
      stories: [
        "[속보] 에어부산 여객기, 대만서 2번 착륙 실패 후 회항",
        "[속보] 삼성전자 노조 변호인 \"법원 결정 존중…21일 쟁의할 것\"",
        "\"회사 없애버려야\"…삼성전자 노조 부위원장 극단 시점",
        "\"등에 뭔가 콱, 난 부끄럽지 않겠구나\"…광주 시민들 '그날의 일기'",
        "'정원 안 뒤 문산남'이 조폭?…'표면만 보고 인신공격'",
        "'꼬마탐험대가 발견했던' 만장굴, 2년 5개월 만에 다시 열린다",
      ],
    },
    {
      name: '조선일보',
      bias: 'R',
      stories: [
        "삼성 파업 방식에 제약 둔 법원… \"평시 수준 유지하라\"",
        "서울시장 대리전? 한동훈=\"달앵땅 홍준표, 민주당으로 월북하나\"",
        "제자 논문 표절해 해임된 前 서울대 국문과 교수… 법원 \"해임 정당\"",
        "방산업체 '총기 조준점' 기술 도면 등 1000개 파일 빼돌린 연구원 '집행유예 3년'",
        "세계 1위 신네르, 조코비치 이어 역대 두번째로 '커리어 골든 마스터스' 달성",
        "가수 노지훈, 용인 식중독 피해 \"열 40도, 6kg 빠져\"",
      ],
    },
    {
      name: '동아일보',
      bias: 'R',
      stories: [
        "볼펜에 찍히고 급소 차이는 교도관…\"분노 넘어 자괴감 든다\"[더 미듭]",
        "\"삼성전자 우리가 그냥 없애버리자\" 노조 부위원장 파업 촉구",
        "한반도 아닌 '북한 비핵화' 美中 팩트시트에 못박았다",
        "인도 또 '버스 집단 성폭행' 충격…피해여성 태운채 달렸다",
        "23년前 시트콤에 '하이닉스 460원'…\"그때 100주 샀으면 2억원\"",
        "최준희 \"키워준 이모할머니에게 '시타'라니…다 잡겠다\" 분노",
      ],
    },
    {
      name: '중앙일보',
      bias: 'R',
      stories: [
        "\"삼전 노조 위원장 월 1000만원 수당\"…파업 투표때 '문어가기 가결' 논란",
        "일하면 깎이던 국민연금 손본다…월 519만원 벌어도 전액 수령",
        "에어부산 여객기, 대만서 착륙 실패…강풍에 '테일 스트라이크' 까지",
        "\"지금 사서 5월 말 던져라\"…스페이스X 상장 전 단타 2종목",
        "순식간에 15m 바늘로 볼 떴다 추락…폭풍 휩쓸린 男 극적 생존",
        "2300석 관객 7분 기립박수…칸 폭소 터드린 나홍진표 노두릭 SF",
      ],
    },
    {
      name: '한겨레신문',
      bias: 'L',
      stories: [
        "삼전 노사 사후조정 내일까지…중노위원장 \"오늘은 노사 자율협상\"",
        "'아무 말' 장동혁 \"이재명, 다카이치와 마주앉는 것은 국단적 친일\"",
        "법원, 삼전 사찍 '평시 금지 가처분' 대폭 수용에 일부 인용 결정",
        "\"우주 쓰레기\" 청소부, 누군가 봤다니… 태양의 '흑점'",
        "한동훈 \"배지 달고 민주당 막살\" 공언에…막지원 \"낙선 편한데\"",
        "나홍진 감독 '호프' 칸서 첫 상영…관객들, 끝나고도 7분간 박수",
      ],
    },
    {
      name: '경향신문',
      bias: 'L',
      stories: [
        "경제단체 \"삼성전자 노조 파업 철회해야…국가 핵심산업 붕괴 우려\"",
        "5·18 기념식 불참 안창호 \"왼전한 진상규명·명예회복 적극 나서달라\" 성명",
        "[속보] 법원 '삼성노조 위법쟁의 가처분' 일부 인용…\"평시 수준 유지해야\"",
        "[단독] 판저 이전비 다 내라\"는 윤석열 대통령실에 반기 든 행안부 공무원…종합특감, '보복성 인사'도 살펴본다",
        "제주도 가면 이것도 조심!…편의점서 모객하고 미등록 렌터카 운송 '불법 관광영업' 기승",
        "인천공항에 세계 최초 자율주행 셀프체크인 로봇 운영",
      ],
    },
    {
      name: '한국일보',
      bias: 'C',
      stories: [
        "삼전 노조 \"법원 결정, 쟁의행위에 방해 안 돼… 21일 파업 예정대로\"",
        "\"삼성전자 우리가 없애버려야\"… 노조 부위원장 극단 발언 이어 '파업 강행' 의지",
        "\"안전사고 떠넘김점 책임\"…쿠팡 등 5개 택배사 갑질에 과징금 30억",
        "한국사 강사 최태성, '대군부인' 향해 일침… \"또 역사 왜곡, 우리는 붕어인가\"",
        "2000년 전 이집트 미라서… 그리스 서사시 '일리아드' 나왔다",
        "칸서 드디어 공개된 '호프'…'못기고 스밀 넘치는 신나는 액션 영화'",
      ],
    },
    {
      name: '세계일보',
      bias: 'C',
      stories: [
        "[속보] 삼성전자 노조 \"법원 결정 존중…21일 총파업 예정대로\"",
        "상남자 대신 '집들이 남주'…로맨스를 대체는 '대문자 I'",
        "\"아짐 둘 한잔이 위 망친다?\"…전문가들이 먼저 지적한 건 '온도' 였다",
        "서울경찰, 시민제안 80% 개선…'기본설서 ReC디자인' 중간성과 발표",
        "냉장고 속 축 늘어진 상추 살리는 10분 '심폐소생술'…'마늘 상추 묶음' 도 매력적 [FOOD+]",
        "베트남 여성 따나자 광주 여고생 맞은 장윤기…초호화 생활 즐긴 최영민 [금주의 사건사고]",
      ],
    },
    {
      name: '서울신문',
      bias: 'C',
      stories: [
        "\"총재산 1049억원\" 지방선거 역대급 후보 정체…거액 자산 내역들",
        "\"아내가 15살 어린 남학생과 불륜\" 충격…집 CCTV에 다 찍혔다",
        "\"육하길래 화나서\"…보은 정신병원서 60대 직원이 강박 저항하는 10대 환자 폭행",
        "\"2027년 역대 최고기온 오나\"…'슈퍼 엘니뇨' 기후 재앙 우려",
        "\"대군부인\" 역사왜곡 논란 속…아이유 \"다 내 잘못\" 교체 속였다",
        "\"주식으로 월 8000만원\"…슈퍼카 3대값 날리고 채끈한 토니인, 비결은?",
      ],
    },
    {
      name: '문화일보',
      bias: 'C',
      stories: [
        "[속보] '퍽퍽' 발로 차고 강박…정신병원 60대 직원, 10대 女환자 폭행",
        "\"엔비디아, 파업물 거부\" 소문… 전세계 \"제때 못받니\" 문의 쇄도",
        "코스피 급락 급등 '널뛰기'… 세계 국채금리 급등·삼성 약재 영향",
        "[속보] \"사실상 파업하겠다\" 법원 '삼성 노조 위법쟁의 가처분' 일부 인용",
        "\"아카씨 무소속이면 안 X뽑겠어요?\"…돌발 물음에 한동훈 답은",
        "5·18에 '책상에 탁' '뱅크데이' 스타벅스 이벤트에 비판 못물",
      ],
    },
    {
      name: '매일경제',
      bias: 'C',
      stories: [
        "\"주식 산다고 다 버는 거 아니야, 좀 더 즐게 돌아와\"…은행 예금금리 줄인상",
        "\"믹스프레스 매각대금으로 갚는다\"…흠플러스, 메리츠 대출 조건 공개",
        "\"코스피 시원하게 5000 만들겠다\"는 삼성 노조원…선 넘어도 한참 넘네",
        "\"삼전노조, 니들 너무 선 넘었어\"…진보 스피커도 작심 쓴소리",
        "\"박 다 푸로하겠다\" MC몽, 의혹 관련 긴급 방송 예고",
        "두 차례 반러된 방시혁 영장…'검 경 입장 다를 수 있어…경찰 최선 다해\"",
      ],
    },
    {
      name: '연합뉴스',
      bias: 'C',
      stories: [
        "법원, 삼성노조 파업에 일부 제동…\"평시 수준 유지해야\" [종합]",
        "\"마트에서 되나요?\" 2차 고유가 지원금 첫날 전국 접수처 북새통",
        "논란의 강남경찰…\"지구대 유흥업소 의혹은 살제없어…강력해신\"",
        "\"대군부인\" 역사왜곡 논란에…최태성 \"고증 연구소 만들어야\"",
        "李대통령 \"대통세상, 빛의혁명으로 부활…5·18 헌법수록 최선\"",
        "\"내가 지금 뭘 보고 있는 거야?\"…칸 술렁이게 한 나홍진 '호프'",
      ],
    },
    {
      name: '뉴시스',
      bias: 'C',
      stories: [
        "[속보] 삼성전자 노조 변호인 \"법원 결정 존중해 21일 쟁의활동 할 것\"",
        "이 대통령 \"5·18 정신 헌법 전문 수록 최선…국가가 희생자 끝까지 책임\"[종합]",
        "\"고기라도 새 먹으려고요\"…2차 고유가지원금 신청 첫날 '북새통'",
        "\"격오지 군무원도 관사 지원해야\"…인권위, 국방부 권고",
        "\"美국채금리 발작에\"…외국인 투자자 이탈 우려 고조",
        "일본서 20명 사망 '혈관영약'…\"국내선 판매 안돼\"",
      ],
    },
    {
      name: '한국경제',
      bias: 'C',
      stories: [
        "삼성전자 노조, 위반 시 최대 18억…법원 결정 '후폭풍' [종합]",
        "\"5000원 넘으면 안 살래\"…다이소 매출 4조 짜낸 터지자 '발칵' [권용훈의 트렌드워치]",
        "10만원 쓰러 왔다가 2000만원 긁고 간다…'패럴왈' 몰리는 곳 [류은혁의 유동기현]",
        "야구장서 '가곡 가득' 애국가 제장…결국 \"생각 잘맞다\" 사과",
        "\"대군부인\" 역사왜곡 논란에…\"큰별쌤\" 최태성 \"정신 차리시오소서\"",
        "\"퍽퍽\" 가러워서 굵었는데…60대 여성 괴롭힌 뜻밖의 이유 [건강1독]",
      ],
    },
  ],
};

function V2Terminal({ data = sampleNewsDashboardData } = {}) {
  const D = data;

  // Coverage heatmap data (issue × press). Simulated coverage strength 0..3.
  // Based on stories in each press list mentioning issue keywords.
  const heatMap = D.issues.map(iss => {
    const kws = iss.title.split(/[\s,·]+/).filter(w => w.length > 1);
    return D.press.map(p => {
      const hits = p.stories.reduce((acc, s) => acc + kws.filter(k => s.includes(k)).length, 0);
      return Math.min(3, hits);
    });
  });

  // Keyword frequency across all press stories
  const keywords = ['삼성', '노조', '파업', '법원', '5·18', '대군부인', '나홍진', '에어부산', '택배', '쿠팡'];
  const kwFreq = keywords.map(kw => {
    const n = D.press.reduce((acc, p) => acc + p.stories.filter(s => s.includes(kw)).length, 0);
    return { kw, n };
  }).sort((a, b) => b.n - a.n);
  const maxFreq = Math.max(...kwFreq.map(k => k.n));

  // Bias distribution
  const biasCount = D.press.reduce((acc, p) => { acc[p.bias] = (acc[p.bias] || 0) + 1; return acc; }, {});

  const css = `
    .v2 { --bg:#f5f3ee; --panel:#ffffff; --panel-2:#eceae3; --line:#dfdcd1;
      --line-2:#c9c5b8; --ink:#1a1814; --ink-2:#5d5749; --ink-3:#8d8676;
      --green:#2f7d5a; --amber:#a06913; --red:#a8493a; --blue:#2c64a0; --violet:#5d4694;
      font-family:'JetBrains Mono', ui-monospace, monospace;
      background:var(--bg); color:var(--ink); width:1440px; min-height:2050px;
      padding:0; box-sizing:border-box; font-size:12px; line-height:1.5;
    }
    .v2 .sans { font-family:'Pretendard', sans-serif; }
    .v2 .topnav { display:flex; justify-content:space-between; align-items:center;
      padding:10px 24px; border-bottom:1px solid var(--line-2); background:var(--panel); }
    .v2 .topnav .left { display:flex; align-items:center; gap:24px; }
    .v2 .logo { font-size:11px; letter-spacing:0.22em; color:var(--green); }
    .v2 .logo::before{ content:"● "; }
    .v2 .nav-tabs { display:flex; gap:1px; background:var(--line); padding:1px; border-radius:2px; }
    .v2 .nav-tab { padding:5px 12px; font-size:10px; letter-spacing:0.12em; color:var(--ink-2);
      background:var(--bg); cursor:pointer; }
    .v2 .nav-tab.active { background:var(--green); color:#fff; }
    .v2 .status-bar { display:flex; align-items:center; gap:20px; font-size:11px; color:var(--ink-2); }
    .v2 .status-bar .live { color:var(--green); }
    .v2 .status-bar .live::before { content:"◉ "; animation:blink 2s infinite; }
    @keyframes blink { 0%,49%{opacity:1} 50%,100%{opacity:0.3} }

    .v2 .header-block { padding:28px 24px 22px; border-bottom:1px solid var(--line-2);
      display:grid; grid-template-columns: 1.4fr 1fr; gap:32px; }
    .v2 .header-title { font-family:'Pretendard',sans-serif; font-size:30px;
      font-weight:700; letter-spacing:-0.02em; line-height:1.15; color:var(--ink); }
    .v2 .header-title .accent { color:var(--green); }
    .v2 .header-sub { font-family:'Pretendard',sans-serif; font-size:13px; color:var(--ink-2);
      margin-top:10px; line-height:1.5; max-width:640px; }
    .v2 .metric-strip { display:grid; grid-template-columns: repeat(4, 1fr); gap:1px;
      background:var(--line); border:1px solid var(--line-2); align-self:start; }
    .v2 .metric { background:var(--panel); padding:14px 12px; }
    .v2 .metric .lbl { font-size:9px; letter-spacing:0.16em; color:var(--ink-3); text-transform:uppercase; }
    .v2 .metric .val { font-size:18px; color:var(--ink); margin-top:6px; font-weight:500; }
    .v2 .metric .val.green { color:var(--green); }
    .v2 .metric .val.amber { color:var(--amber); }
    .v2 .metric .sub { font-size:10px; color:var(--ink-3); margin-top:2px; }

    .v2 .grid-main { display:grid; grid-template-columns: 1fr 380px;
      gap:1px; background:var(--line-2); }
    .v2 .panel { background:var(--bg); padding:18px 22px; }
    .v2 .panel-head { display:flex; justify-content:space-between; align-items:center;
      margin-bottom:14px; padding-bottom:10px; border-bottom:1px dashed var(--line-2); }
    .v2 .panel-head h2 { margin:0; font-family:'Pretendard',sans-serif; font-size:14px;
      letter-spacing:0.02em; color:var(--ink); font-weight:600; }
    .v2 .panel-head .meta { font-size:10px; color:var(--ink-3); letter-spacing:0.1em; }

    /* AI Flow */
    .v2 .flow-text { font-family:'Pretendard',sans-serif; font-size:14px; line-height:1.6;
      color:var(--ink); padding:6px 0 14px; }
    .v2 .flow-text .hl { background:rgba(47,125,90,0.12); color:var(--green); padding:1px 4px;
      border-radius:2px; }
    .v2 .ed-row { display:flex; gap:14px; padding:12px; background:var(--panel);
      border-left:2px solid var(--amber); font-family:'Pretendard',sans-serif; font-size:12px;
      color:var(--ink-2); line-height:1.5; }
    .v2 .ed-row .badge { font-family:'JetBrains Mono',monospace; font-size:9px; color:var(--amber);
      letter-spacing:0.16em; flex:0 0 auto; padding-top:2px; }

    /* Keyword bars */
    .v2 .kw-rows { display:flex; flex-direction:column; gap:6px; }
    .v2 .kw-row { display:grid; grid-template-columns: 64px 1fr 28px; gap:10px;
      align-items:center; font-size:11px; }
    .v2 .kw-row .name { color:var(--ink); font-family:'Pretendard',sans-serif; }
    .v2 .kw-row .name.top { color:var(--green); }
    .v2 .kw-row .bar { height:8px; background:var(--panel); position:relative; }
    .v2 .kw-row .bar .fill { height:100%; background:var(--ink-2); }
    .v2 .kw-row.top .bar .fill { background:var(--green); }
    .v2 .kw-row.t2 .bar .fill { background:var(--amber); }
    .v2 .kw-row .n { color:var(--ink-2); text-align:right; }

    /* Issues table */
    .v2 .issues-table { display:flex; flex-direction:column; background:var(--line-2); gap:1px; }
    .v2 .issue-row { display:grid; grid-template-columns: 36px 70px 1fr 88px 110px;
      background:var(--bg); padding:14px 14px; gap:14px; align-items:center; }
    .v2 .issue-row.head { background:var(--panel); font-size:9px; letter-spacing:0.14em;
      color:var(--ink-3); padding:10px 14px; text-transform:uppercase; }
    .v2 .issue-row .rk { color:var(--green); font-size:14px; }
    .v2 .issue-row .topic-pill { font-size:9px; padding:3px 6px; letter-spacing:0.08em;
      text-align:center; border:1px solid currentColor; }
    .v2 .issue-row .topic-pill.경제{color:var(--amber)} .v2 .issue-row .topic-pill.정치{color:var(--blue)}
    .v2 .issue-row .topic-pill.사회{color:var(--red)} .v2 .issue-row .topic-pill.문화{color:var(--violet)}
    .v2 .issue-row .ttl { font-family:'Pretendard',sans-serif; font-weight:600; font-size:14px;
      color:var(--ink); letter-spacing:-0.01em; line-height:1.4; }
    .v2 .issue-row .smry { font-family:'Pretendard',sans-serif; font-weight:400; font-size:11px;
      color:var(--ink-2); margin-top:3px; line-height:1.45; }
    .v2 .issue-row .cov { font-size:11px; color:var(--ink); text-align:right; }
    .v2 .issue-row .cov .small { color:var(--ink-3); }
    .v2 .heat-cell { display:flex; align-items:center; gap:6px; font-size:11px; }
    .v2 .heat-cell .gauge { flex:1; height:4px; background:var(--panel); position:relative; }
    .v2 .heat-cell .gauge .fill { height:100%; background:var(--green); }
    .v2 .heat-cell .gauge .fill.hot { background:var(--amber); }
    .v2 .heat-cell .gauge .fill.crit { background:var(--red); }
    .v2 .heat-cell .num { color:var(--ink); width:24px; text-align:right; }

    /* Heatmap matrix */
    .v2 .hm-wrap { overflow:hidden; }
    .v2 .hm { display:grid; grid-template-columns: 200px repeat(14, 1fr); gap:2px;
      background:transparent; }
    .v2 .hm .h-row { display:contents; }
    .v2 .hm .h-press { font-size:9px; color:var(--ink-2); writing-mode:vertical-rl;
      transform:rotate(180deg); padding:6px 0; font-family:'Pretendard',sans-serif;
      text-align:right; align-self:end; height:88px; }
    .v2 .hm .h-press.base { color:var(--amber); font-weight:600; }
    .v2 .hm .iss-label { font-family:'Pretendard',sans-serif; font-size:11px; color:var(--ink);
      padding:6px 8px 6px 0; display:flex; align-items:center; gap:8px; line-height:1.3; }
    .v2 .hm .iss-label .num { color:var(--green); font-family:'JetBrains Mono',monospace; }
    .v2 .hm .cell { aspect-ratio:1; background:var(--panel); display:flex; align-items:center;
      justify-content:center; font-size:9px; color:var(--ink-3); }
    .v2 .hm .cell.l1 { background:rgba(47,125,90,0.14); color:var(--green); }
    .v2 .hm .cell.l2 { background:rgba(47,125,90,0.42); color:var(--ink); }
    .v2 .hm .cell.l3 { background:var(--green); color:#fff; font-weight:600; }
    .v2 .hm .corner { padding:0 8px 4px 0; font-size:9px; letter-spacing:0.14em;
      color:var(--ink-3); text-transform:uppercase; align-self:end; }

    /* Missed alerts */
    .v2 .alerts { background:var(--bg); display:flex; flex-direction:column; gap:1px; }
    .v2 .alert { padding:14px 18px; background:var(--bg); border-left:2px solid var(--red);
      display:grid; grid-template-columns: 90px 1fr; gap:18px; }
    .v2 .alert .alert-tag { font-size:9px; color:var(--red); letter-spacing:0.18em; }
    .v2 .alert .alert-tag::before { content:"▲ "; }
    .v2 .alert .alert-title { font-family:'Pretendard',sans-serif; font-size:14px; font-weight:600;
      color:var(--ink); margin-bottom:6px; letter-spacing:-0.01em; }
    .v2 .alert .alert-meta { font-family:'Pretendard',sans-serif; font-size:11px; color:var(--ink-2);
      line-height:1.5; }
    .v2 .alert .alert-meta .lbl { color:var(--ink-3); margin-right:6px; }

    /* Press table */
    .v2 .press-table { display:grid; grid-template-columns: repeat(2, 1fr); gap:1px;
      background:var(--line-2); }
    .v2 .press-col { background:var(--bg); padding:0; }
    .v2 .press-col .ph { display:grid; grid-template-columns: 24px 1fr 40px 40px;
      padding:8px 14px; background:var(--panel); align-items:center;
      font-size:9px; letter-spacing:0.14em; color:var(--ink-3); text-transform:uppercase; }
    .v2 .press-col .pr { display:grid; grid-template-columns: 24px 1fr 40px 40px;
      padding:8px 14px; align-items:center; border-bottom:1px solid var(--line);
      font-family:'Pretendard',sans-serif; font-size:11px; }
    .v2 .press-col .pr:last-child { border-bottom:none; }
    .v2 .press-col .pr .idx { font-family:'JetBrains Mono',monospace; color:var(--ink-3); font-size:10px; }
    .v2 .press-col .pr .nm { color:var(--ink); font-weight:600; letter-spacing:-0.005em; display:flex; align-items:center; gap:8px; }
    .v2 .press-col .pr .nm .basebadge { font-size:8px; padding:2px 5px; background:var(--amber);
      color:#000; font-family:'JetBrains Mono',monospace; letter-spacing:0.1em; }
    .v2 .press-col .pr .bias-mini { font-family:'JetBrains Mono',monospace; font-size:9px;
      letter-spacing:0.1em; padding:2px 5px; text-align:center; }
    .v2 .press-col .pr .bias-mini.L { color:var(--blue); border:1px solid var(--blue); }
    .v2 .press-col .pr .bias-mini.R { color:var(--red); border:1px solid var(--red); }
    .v2 .press-col .pr .bias-mini.C { color:var(--ink-3); border:1px solid var(--line-2); }
    .v2 .press-col .pr .stcount { font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--ink-2); text-align:right; }
    .v2 .press-col .lead { padding:8px 14px 14px 14px; }
    .v2 .press-col .lead-line { display:flex; gap:8px; font-family:'Pretendard',sans-serif;
      font-size:11px; color:var(--ink-2); line-height:1.4; padding:4px 0; }
    .v2 .press-col .lead-line .bullet { color:var(--green); flex:0 0 auto; }
    .v2 .press-col .lead-line.bk .bullet { color:var(--red); }
    /* Issue cards — V3-style mosaic, V2 palette, uniform 3x2 grid */
    .v2 .iss-grid { display:grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: 1fr; gap:14px; }
    .v2 .iss-card { background:var(--panel); border:1px solid var(--line-2); border-radius:4px;
      padding:20px 22px; display:flex; flex-direction:column; gap:12px; position:relative; overflow:hidden; min-height:230px; }
    .v2 .iss-card .topic-block { position:absolute; right:0; top:0; bottom:0; width:3px; }
    .v2 .iss-card .iss-head { display:flex; justify-content:space-between; align-items:flex-start; gap:14px; }
    .v2 .iss-card .iss-meta { display:flex; flex-direction:column; gap:8px; }
    .v2 .iss-card .rank { font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--ink-3); letter-spacing:0.16em; }
    .v2 .iss-card .topic-pill { font-size:9px; letter-spacing:0.14em; padding:3px 8px; align-self:flex-start;
      border:1px solid currentColor; border-radius:2px; }
    .v2 .iss-card .topic-pill.경제{color:var(--amber)} .v2 .iss-card .topic-pill.정치{color:var(--blue)}
    .v2 .iss-card .topic-pill.사회{color:var(--red)} .v2 .iss-card .topic-pill.문화{color:var(--violet)}
    .v2 .iss-card h3 { margin:0; font-family:'Pretendard',sans-serif; font-size:16px; line-height:1.4; font-weight:700;
      letter-spacing:-0.015em; color:var(--ink); }
    .v2 .iss-card p { margin:0; font-family:'Pretendard',sans-serif; font-size:12px; color:var(--ink-2); line-height:1.5; }
    .v2 .iss-card .why { font-family:'Pretendard',sans-serif; font-size:11px; color:var(--ink-3); line-height:1.55;
      padding-top:10px; border-top:1px dashed var(--line-2); margin-top:auto; }
    .v2 .iss-card .why::before { content:"WHY "; color:var(--green); font-family:'JetBrains Mono',monospace;
      font-size:9px; letter-spacing:0.16em; }
    .v2 .iss-card .metrics { display:flex; gap:18px; padding-top:10px; border-top:1px dashed var(--line-2); }
    .v2 .iss-card .m-lbl { font-size:9px; letter-spacing:0.14em; color:var(--ink-3); text-transform:uppercase; }
    .v2 .iss-card .m-val { font-family:'JetBrains Mono',monospace; font-size:16px; color:var(--ink); margin-top:2px; font-weight:500; }
    .v2 .iss-card .heat-arc { width:54px; height:54px; flex-shrink:0; position:relative; }
    .v2 .iss-card .heat-arc svg { transform:rotate(-90deg); }
    .v2 .iss-card .heat-arc .num { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
      font-family:'JetBrains Mono',monospace; font-size:13px; font-weight:600; color:var(--ink); }
  `;

  // Topic color (V2 palette)
  const topicColor = {
    경제: 'var(--amber)',
    정치: 'var(--blue)',
    사회: 'var(--red)',
    문화: 'var(--violet)',
  };

  const HeatArc = ({ value, size = 54 }) => {
    const r = (size / 2) - 4;
    const c = 2 * Math.PI * r;
    const color = value > 85 ? 'var(--red)' : value > 70 ? 'var(--amber)' : 'var(--green)';
    return (
      <div className="heat-arc" style={{ width: size, height: size }}>
        <svg width={size} height={size}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(0,0,0,0.08)" strokeWidth="3" />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="3"
            strokeDasharray={c} strokeDashoffset={c - (c * value / 100)} strokeLinecap="round" />
        </svg>
        <div className="num">{value}</div>
      </div>
    );
  };
  return (
    <div className="v2">
      <style dangerouslySetInnerHTML={{ __html: css }} />

      <div className="topnav">
        <div className="left">
          <div className="logo">NEWSDESK ∙ TERMINAL</div>
          <div className="nav-tabs">
            <div className="nav-tab active">DASHBOARD</div>
            <div className="nav-tab">ISSUES</div>
            <div className="nav-tab">COVERAGE</div>
            <div className="nav-tab">KEYWORDS</div>
            <div className="nav-tab">ARCHIVE</div>
          </div>
        </div>
        <div className="status-bar">
          <span className="live">LIVE</span>
          <span>NEXT SLOT 14:00 KST</span>
          <span>{D.meta.lastSlot}</span>
        </div>
      </div>

      <div className="header-block">
        <div>
          <div style={{ fontSize: 10, letterSpacing: '0.2em', color: 'var(--ink-3)', marginBottom: 12 }}>
            DAILY BRIEF ∙ 2026.05.18 ∙ MON
          </div>
          <div className="header-title sans">
            오늘의 <span className="accent">시그널</span>
          </div>
          <div className="header-sub">
            14개 주요 언론사의 네이버 뉴스 헤드라인을 AI가 분석해 핵심 이슈, 키워드 분포, 우리가 놓친 기사를 추출합니다.
            기준 매체는 {D.meta.baseline}.
          </div>
        </div>
        <div className="metric-strip">
          <div className="metric">
            <div className="lbl">Tracked</div>
            <div className="val">14<span style={{ fontSize: 11, color: 'var(--ink-3)' }}> outlets</span></div>
            <div className="sub">L 2 ∙ C 9 ∙ R 3</div>
          </div>
          <div className="metric">
            <div className="lbl">Issues</div>
            <div className="val green">06</div>
            <div className="sub">heat avg 78.2</div>
          </div>
          <div className="metric">
            <div className="lbl">Missed</div>
            <div className="val amber">02</div>
            <div className="sub">vs. 국민일보</div>
          </div>
          <div className="metric">
            <div className="lbl">AI Calls</div>
            <div className="val">{D.meta.aiCalls}<span style={{ fontSize: 11, color: 'var(--ink-3)' }}>/{D.meta.aiQuota}</span></div>
            <div className="sub">{D.meta.model}</div>
          </div>
        </div>
      </div>

      <div className="grid-main">
        <div className="panel">
          <div className="panel-head">
            <h2>AI 에디터 ∙ 오늘의 흐름</h2>
            <span className="meta">UPDATED {D.meta.lastAnalysis}</span>
          </div>
          <div className="flow-text">
            <span className="hl">삼성전자 노조의 파업 강행</span>과 <span className="hl">법원의 쟁의 제한 결정</span>이 경제 및 사회면의 핵심 이슈로 부상했습니다. 이와 함께 <span className="hl">5·18 민주화운동 기념일</span> 관련 메시지와 역사 왜곡 논란, 칸 영화제 등 문화계 소식이 주요하게 다뤄지고 있습니다.
          </div>
          <div className="ed-row">
            <div className="badge">EDIT<br />NOTE</div>
            <div>{D.flow.editorial}</div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>키워드 빈도</h2>
            <span className="meta">N={D.press.reduce((a, p) => a + p.stories.length, 0)} HEADLINES</span>
          </div>
          <div className="kw-rows">
            {kwFreq.map((k, i) => (
              <div key={k.kw} className={"kw-row" + (i < 2 ? ' top' : i < 4 ? ' t2' : '')}>
                <span className={"name" + (i < 2 ? ' top' : '')}>{k.kw}</span>
                <span className="bar"><span className="fill" style={{ width: (k.n / maxFreq * 100) + '%' }} /></span>
                <span className="n">{String(k.n).padStart(2, '0')}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel" style={{ borderTop: '1px solid var(--line-2)' }}>
        <div className="panel-head">
          <h2>핵심 이슈 ∙ HEAT × COVERAGE</h2>
          <span className="meta">6 ISSUES · UNIFORM GRID</span>
        </div>
        <div className="iss-grid">
          {D.issues.map(iss => (
            <div className="iss-card" key={iss.n}>
              <div className="topic-block" style={{ background: topicColor[iss.topic] }} />
              <div className="iss-head">
                <div className="iss-meta">
                  <div className="rank">ISSUE #{String(iss.n).padStart(2, '0')}</div>
                  <span className={"topic-pill " + iss.topic}>{iss.topic}</span>
                </div>
                <HeatArc value={iss.heat} />
              </div>
              <h3>{iss.title}</h3>
              <p>{iss.summary}</p>
              <div className="metrics">
                <div>
                  <div className="m-lbl">Coverage</div>
                  <div className="m-val">{iss.coverage}<span style={{ color: 'var(--ink-3)', fontSize: 11 }}>/14</span></div>
                </div>
                <div>
                  <div className="m-lbl">Heat</div>
                  <div className="m-val">{iss.heat}</div>
                </div>
              </div>
              <div className="why">{iss.why}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel" style={{ borderTop: '1px solid var(--line-2)' }}>
        <div className="panel-head">
          <h2>이슈 × 언론사 보도 매트릭스</h2>
          <span className="meta">DARKER = MORE COVERAGE ∙ KEYWORD MATCH</span>
        </div>
        <div className="hm-wrap">
          <div className="hm">
            <div className="corner">ISSUE ↓ ∙ PRESS →</div>
            {D.press.map(p => (
              <div key={p.name} className={"h-press" + (p.tag ? ' base' : '')}>{p.name}</div>
            ))}
            {D.issues.map((iss, ri) => (
              <React.Fragment key={iss.n}>
                <div className="iss-label">
                  <span className="num">#{iss.n}</span>
                  <span>{iss.title.length > 22 ? iss.title.slice(0, 22) + '…' : iss.title}</span>
                </div>
                {heatMap[ri].map((v, ci) => (
                  <div key={ci} className={"cell" + (v > 0 ? ' l' + v : '')}>
                    {v > 0 ? v : ''}
                  </div>
                ))}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      <div className="panel" style={{ borderTop: '1px solid var(--line-2)' }}>
        <div className="panel-head">
          <h2>⚠ 우리가 놓친 기사</h2>
          <span className="meta">기준 = {D.meta.baseline} ∙ DETECTED IN OTHER OUTLETS</span>
        </div>
        <div className="alerts">
          {D.missed.map(m => (
            <div className="alert" key={m.n}>
              <div className="alert-tag">MISSED #{m.n}</div>
              <div>
                <div className="alert-title">{m.title}</div>
                <div className="alert-meta">
                  <span className="lbl">REASON</span>{m.reason}
                </div>
                <div className="alert-meta" style={{ marginTop: 4 }}>
                  <span className="lbl">SIGNAL</span>{m.where}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel" style={{ borderTop: '1px solid var(--line-2)' }}>
        <div className="panel-head">
          <h2>언론사별 리드 헤드라인</h2>
          <span className="meta">TOP 3 PER OUTLET</span>
        </div>
        <div className="press-table">
          {D.press.map(p => (
            <div className="press-col" key={p.name}>
              <div className="pr">
                <span className="idx" />
                <span className="nm">
                  {p.name}
                  {p.tag && <span className="basebadge">BASE</span>}
                </span>
                <span className={"bias-mini " + p.bias}>{p.bias}</span>
                <span className="stcount">{p.stories.length}</span>
              </div>
              <div className="lead">
                {p.stories.slice(0, 3).map((s, i) => (
                  <div key={i} className={"lead-line" + (s.startsWith('[속보]') ? ' bk' : '')}>
                    <span className="bullet">{s.startsWith('[속보]') ? '◆' : '▸'}</span>
                    <span>{s.replace(/^\[속보\]\s*/, '')}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// V3 — Insight Mosaic
// Magazine/editorial mosaic with hero issue, modular cards, soft warm dark
// palette. Visual rhythm via size variation and topic color blocks.

function NewsDashboardDesign({ data = sampleNewsDashboardData } = {}) {
  return <V2Terminal data={data} />;
}

export {
  NewsDashboardDesign,
  V2Terminal,
  sampleNewsDashboardData,
};

export default NewsDashboardDesign;
