"""
🔍 식품안전나라 품목제조보고 조회 v4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
속도 전략: total_count 사전조회 없이 마지막 N페이지만 직접 병렬 호출
AI 분석: 트렌드 / 플레이버 / 추천 레시피 + 차트 기반 시각 분석
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# ══════════════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════════════
def _secret(*keys, default=""):
    try:
        for k in keys:
            v = st.secrets.get(k, "")
            if v:
                return v
    except Exception:
        pass
    return default

FOOD_API_KEY = _secret("FOOD_SAFETY_API_KEY", default="9171f7ffd72f4ffcb62f")
GEMINI_KEY   = _secret("GEMINI_API_KEY", "GOOGLE_API_KEY")
SERVICE_ID   = "I1250"
BASE_URL     = f"http://openapi.foodsafetykorea.go.kr/api/{FOOD_API_KEY}/{SERVICE_ID}/json"

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.5-flash-preview-04-17",
]

FOOD_TYPES = {
    "음료류": [
        "혼합음료", "다류", "커피",
        "농축과.채즙", "과.채주스", "과.채음료",
        "탄산음료", "탄산수",
        "두유류", "유산균음료", "발효음료류",
        "인삼.홍삼음료", "기타음료",
    ],
    "과자류":      ["과자", "캔디류", "추잉껌", "빙과", "아이스크림"],
    "빵.면류":     ["빵류", "떡류", "면류", "즉석섭취식품"],
    "조미.소스류": ["소스", "복합조미식품", "향신료가공품", "식초", "드레싱"],
    "유가공품":    ["치즈", "버터", "발효유", "우유류", "가공유"],
    "건강기능식품": ["건강기능식품"],
    "기타":        ["잼류", "식용유지", "김치류", "두부류", "즉석조리식품", "레토르트식품"],
}
TYPE_TO_CAT = {t: c for c, ts in FOOD_TYPES.items() for t in ts}

COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형", "BSSH_NM": "제조사",
    "PRMS_DT": "보고일자", "POG_DAYCNT": "유통기한", "PRODUCTION": "생산종료",
    "INDUTY_CD_NM": "업종", "LCNS_NO": "인허가번호",
    "PRDLST_REPORT_NO": "품목제조번호", "LAST_UPDT_DTM": "최종수정일",
    "DISPOS": "제품형태", "FRMLC_MTRQLT": "포장재질",
}


# ══════════════════════════════════════════════════════
#  초고속 조회 — total_count 없이 끝 N페이지 직접 호출
# ══════════════════════════════════════════════════════

# 총 레코드 수 추정값 (캐시)
# → 첫 실행 시 1회 조회 후 session_state에 저장, 이후 재사용
def _get_total() -> int:
    """
    DB 총 건수 조회 — session_state 캐시 우선.
    반드시 st 컨텍스트(캐시 함수 밖)에서 호출해야 함.
    """
    if "db_total" in st.session_state:
        return st.session_state["db_total"]
    try:
        r = requests.get(f"{BASE_URL}/1/1", timeout=6)
        total = int(r.json().get(SERVICE_ID, {}).get("total_count", 0))
        if total > 0:
            st.session_state["db_total"] = total
            return total
    except Exception:
        pass
    st.session_state["db_total"] = 500000  # 추정값
    return 500000


# requests Session — TCP 연결 재사용으로 속도 향상
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=10, pool_maxsize=20,
    max_retries=0,   # 재시도는 코드에서 직접 제어
)
_session.mount("http://", _adapter)


def _fetch_page(start: int, end: int) -> list:
    """단일 페이지 호출 — timeout 8초, 실패 시 빈 리스트 즉시 반환"""
    url = f"{BASE_URL}/{start}/{end}"
    try:
        r = _session.get(url, timeout=8)
        r.raise_for_status()
        result = r.json().get(SERVICE_ID, {})
        if result.get("RESULT", {}).get("CODE") == "INFO-000":
            return result.get("row", [])
    except Exception:
        pass
    return []


@st.cache_data(ttl=600, show_spinner=False)
def fetch_fast(food_type: str, count: int,
               scan_pages: int, total: int) -> tuple:
    """
    total을 파라미터로 받음 (캐시 함수 내부에서 session_state 접근 불가 문제 해결).
    DB 끝 scan_pages 페이지만 병렬 호출.
    """
    PAGE = 1000
    pages = []
    end = total
    for _ in range(scan_pages):
        if end <= 0:
            break
        start = max(end - PAGE + 1, 1)
        pages.append((start, end))
        end = start - 1

    collected = []
    ok_pages  = 0

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_page, s, e): None for s, e in pages}
        for fut in as_completed(futures):
            rows = fut.result()
            if rows:
                ok_pages += 1
                collected.extend(
                    r for r in rows
                    if r.get("PRDLST_DCNM", "").strip() == food_type.strip()
                )

    collected.sort(key=lambda r: r.get("PRMS_DT", ""), reverse=True)
    return collected[:count], ok_pages


def to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {k: v for k, v in COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    if "보고일자" in df.columns:
        df["보고일자"] = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════
#  차트
# ══════════════════════════════════════════════════════
def render_charts(df: pd.DataFrame, food_type: str):
    st.markdown("### 📊 데이터 분석")

    c1, c2 = st.columns(2)

    # 제조사별 제품 수
    if "제조사" in df.columns:
        with c1:
            mc = df["제조사"].value_counts().head(15)
            fig = px.bar(x=mc.values, y=mc.index, orientation="h",
                         title="제조사별 제품 수 (상위 15)",
                         labels={"x": "제품 수", "y": "제조사"},
                         color=mc.values, color_continuous_scale="Blues")
            fig.update_layout(height=420, showlegend=False,
                               yaxis=dict(autorange="reversed"))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    # 월별 보고 추이
    if "보고일자_dt" in df.columns:
        with c2:
            tmp = df.dropna(subset=["보고일자_dt"]).copy()
            if not tmp.empty:
                tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
                mo = tmp["연월"].value_counts().sort_index().tail(24)
                fig2 = px.area(x=mo.index, y=mo.values,
                               title="월별 신규 보고 건수 (최근 24개월)",
                               labels={"x": "연월", "y": "건수"})
                fig2.update_traces(fill="tozeroy", line_color="#1975BC")
                fig2.update_layout(height=420)
                st.plotly_chart(fig2, use_container_width=True)

    # 유통기한 분포
    c3, c4 = st.columns(2)
    if "생산종료" in df.columns:
        with c3:
            pc = df["생산종료"].value_counts()
            fig3 = px.pie(values=pc.values, names=pc.index,
                          title="생산종료 현황",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig3.update_layout(height=320)
            st.plotly_chart(fig3, use_container_width=True)

    # 제조사 상위 10 점유율
    if "제조사" in df.columns:
        with c4:
            top10 = df["제조사"].value_counts().head(10)
            others = len(df) - top10.sum()
            labels = list(top10.index) + (["기타"] if others > 0 else [])
            values = list(top10.values) + ([others] if others > 0 else [])
            fig4 = px.pie(values=values, names=labels,
                          title="제조사 점유율 (상위 10)",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig4.update_layout(height=320)
            st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════
#  Gemini AI 분석
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def _gemini(prompt: str, model_name: str) -> str:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel(model_name)
    return model.generate_content(prompt).text


def _build_context(df: pd.DataFrame, food_type: str) -> dict:
    """AI 프롬프트용 데이터 컨텍스트 준비"""
    monthly = {}
    if "보고일자_dt" in df.columns:
        tmp = df.dropna(subset=["보고일자_dt"]).copy()
        if not tmp.empty:
            tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
            monthly = tmp["연월"].value_counts().sort_index().tail(24).to_dict()

    maker_top = df["제조사"].value_counts().head(10).to_dict() if "제조사" in df.columns else {}
    maker_n   = df["제조사"].nunique() if "제조사" in df.columns else "N/A"

    cols = [c for c in ["제품명", "제조사", "보고일자"] if c in df.columns]
    recent30 = df[cols].head(30).to_dict(orient="records")

    # 제품명에서 키워드 추출 (빈도)
    if "제품명" in df.columns:
        import re
        all_names = " ".join(df["제품명"].dropna().astype(str).tolist())
        words = re.findall(r"[가-힣a-zA-Z]{2,}", all_names)
        from collections import Counter
        kw_freq = dict(Counter(words).most_common(30))
    else:
        kw_freq = {}

    return {
        "food_type": food_type,
        "total": len(df),
        "monthly": monthly,
        "maker_top": maker_top,
        "maker_n": maker_n,
        "recent30": recent30,
        "kw_freq": kw_freq,
    }


def render_ai_section(df: pd.DataFrame, food_type: str, model_name: str):
    st.markdown("---")
    st.markdown("## 🤖 AI 연구원 분석")

    if not GENAI_AVAILABLE:
        st.error("google-generativeai 미설치\n```bash\npip install google-generativeai\n```")
        return
    if not GEMINI_KEY:
        st.warning(
            "**Gemini API 키 없음**\n\n"
            "`.streamlit/secrets.toml`:\n"
            "```toml\nGEMINI_API_KEY = \"AIza...\"\n```\n\n"
            "[🔑 Google AI Studio 무료 발급](https://aistudio.google.com/app/apikey)"
        )
        return

    st.info(f"모델: **{model_name}** | 대상: **{food_type}** {len(df)}건 | 총 4개 분석 항목")

    if not st.button("🔬 AI 분석 시작", key="btn_ai", type="primary",
                     use_container_width=True):
        return

    ctx = _build_context(df, food_type)
    prefix = (
        f"당신은 15년 경력의 식품 R&D 수석 연구원입니다.\n"
        f"식품안전나라 품목제조보고 DB의 **{food_type}** 카테고리 {ctx['total']}건 데이터를 분석합니다.\n"
        f"실무에서 바로 활용할 수 있는 구체적이고 전문적인 인사이트를 한국어로 작성하세요.\n\n"
    )

    analyses = [
        {
            "title": "📈 시장 트렌드 분석",
            "prompt": (
                prefix
                + f"### 월별 신규 보고 건수 (최근 24개월)\n{ctx['monthly']}\n\n"
                + f"### 최신 보고 제품 30건\n{ctx['recent30']}\n\n"
                + f"### 제조사별 제품 수 (상위 10)\n{ctx['maker_top']}\n"
                + f"전체 제조사 수: {ctx['maker_n']}개\n\n"
                + "다음 항목을 분석하세요 (각 3~4문장):\n"
                + "## 1. 시장 성장성\n월별 보고 건수 트렌드를 보고 시장이 성장/정체/위축 중인지 판단하세요.\n"
                + "## 2. 경쟁 구도\n시장 집중도, 주요 플레이어, 진입 여지를 분석하세요.\n"
                + "## 3. 출시 패턴\n특정 시기에 집중 출시되는 패턴이 있는지 분석하세요.\n"
                + "## 4. R&D 전략 시사점\n이 데이터로 볼 때 어떤 방향으로 제품 개발을 해야 할지 제언하세요."
            ),
        },
        {
            "title": "🍋 플레이버 & 원료 트렌드",
            "prompt": (
                prefix
                + f"### 제품명 키워드 빈도 (상위 30)\n{ctx['kw_freq']}\n\n"
                + f"### 최신 제품명 30건\n{ctx['recent30']}\n\n"
                + "다음 항목을 분석하세요 (각 3~4문장):\n"
                + "## 1. 주요 플레이버 트렌드\n제품명 키워드를 기반으로 어떤 맛/향이 주류인지 분석하세요.\n"
                + "## 2. 기능성 원료 트렌드\n건강 기능성 소재(콜라겐, 비타민, 프로바이오틱스 등)의 등장 패턴을 분석하세요.\n"
                + "## 3. 신흥 플레이버\n최근 새롭게 등장하거나 주목받는 플레이버를 찾아내세요.\n"
                + "## 4. 포뮬레이션 방향 제언\n이 플레이버 트렌드를 반영한 신제품 개발 방향을 제안하세요."
            ),
        },
        {
            "title": "🧪 추천 레시피 (3종)",
            "prompt": (
                prefix
                + f"### 제품명 키워드 빈도 (상위 30)\n{ctx['kw_freq']}\n\n"
                + f"### 최신 출시 제품 30건\n{ctx['recent30']}\n\n"
                + f"### 월별 트렌드\n{ctx['monthly']}\n\n"
                + "위 시장 데이터를 반영하여 **{food_type}** 신제품 레시피 3종을 제안하세요.\n\n"
                + "각 레시피는 반드시 아래 형식으로 작성하세요:\n\n"
                + "## 레시피 1: [제품명]\n"
                + "**컨셉**: (한 줄 설명)\n"
                + "**타겟**: (소비자 타겟)\n"
                + "**주요 원료 및 배합비**:\n"
                + "| 원료명 | 함량(%) | 역할 |\n|---|---|---|\n"
                + "| 정제수 | 00.0 | 기제 |\n"
                + "| (원료) | 00.0 | (기능) |\n\n"
                + "**제조 공정 포인트**: (2~3줄)\n"
                + "**예상 규격**: pH, 당도(Brix), 칼로리 등\n"
                + "**차별화 포인트**: (경쟁 제품 대비 강점)\n\n"
                + "---\n\n"
                + "레시피 2, 3도 동일 형식으로 작성하세요.\n"
                + "배합비는 실제 식품 R&D 관점에서 현실적인 수치를 사용하고, 합계가 100%가 되도록 하세요."
            ),
        },
        {
            "title": "💡 종합 R&D 인사이트",
            "prompt": (
                prefix
                + f"### 전체 분석 데이터 요약\n"
                + f"- 조회 건수: {ctx['total']}건\n"
                + f"- 제조사 수: {ctx['maker_n']}개\n"
                + f"- 월별 트렌드: {ctx['monthly']}\n"
                + f"- 주요 키워드: {ctx['kw_freq']}\n\n"
                + "다음 항목을 작성하세요 (각 3~4문장):\n"
                + "## 1. 시장 기회\n지금 이 카테고리에서 아직 포화되지 않은 빈 틈새를 찾아내세요.\n"
                + "## 2. 리스크 요인\n과포화 플레이버, 쇠퇴 트렌드 등 피해야 할 방향을 제시하세요.\n"
                + "## 3. 6개월 내 출시 추천 컨셉\n지금 당장 개발을 시작하면 좋을 제품 컨셉을 1~2가지 제안하세요.\n"
                + "## 4. 중장기 R&D 방향\n1~3년 후를 바라보는 기술 개발 방향을 제언하세요."
            ),
        },
    ]

    all_results = {}
    for item in analyses:
        st.markdown(f"#### {item['title']}")
        box = st.empty()
        box.info("분석 중…")
        try:
            text = _gemini(item["prompt"], model_name)
            all_results[item["title"]] = text
            box.markdown(text)
        except Exception as e:
            msg = f"❌ 분석 실패: {e}"
            all_results[item["title"]] = msg
            box.error(msg)
        st.markdown("")

    # 전체 다운로드
    if all_results:
        full = "\n\n---\n\n".join(f"{t}\n\n{c}" for t, c in all_results.items())
        st.download_button(
            "📥 AI 분석 전체 다운로드 (TXT)",
            full.encode("utf-8"),
            f"{food_type}_AI분석_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            "text/plain", use_container_width=True,
        )


# ══════════════════════════════════════════════════════
#  페이지 설정
# ══════════════════════════════════════════════════════
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #f8f9fb; }
div[data-testid="stMetric"] {
    background: #f0f2f5; border-radius: 10px; padding: 12px;
}
.stTabs [data-baseweb="tab"] { font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  사이드바
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🔍 조회 설정")
    st.markdown("---")

    mode = st.radio("조회 방식", ["📋 단일 유형 조회", "📊 복수 유형 비교"])
    st.markdown("---")

    if mode == "📋 단일 유형 조회":
        category  = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
        food_type = st.selectbox("식품유형", FOOD_TYPES[category])
        custom    = st.text_input("직접 입력 (DB 표기 그대로)",
                                  placeholder="예: 과.채주스")
        if custom.strip():
            food_type = custom.strip()

        count = st.slider("조회 건수", 10, 200, 100, step=10)

        st.markdown("**⚡ 조회 속도 설정**")
        speed = st.radio(
            "스캔 범위",
            ["🚀 초고속 (최근 1만건)", "⚡ 빠름 (최근 3만건)", "🔍 보통 (최근 10만건)"],
            index=0,
        )
        scan_pages = {"🚀 초고속 (최근 1만건)": 10,
                      "⚡ 빠름 (최근 3만건)": 30,
                      "🔍 보통 (최근 10만건)": 100}[speed]

    else:
        st.markdown("**비교할 유형 선택:**")
        selected_types = []
        for cat, types in FOOD_TYPES.items():
            with st.expander(cat, expanded=(cat == "음료류")):
                for t in types:
                    if st.checkbox(t, key=f"cb_{t}",
                                   value=t in ["혼합음료", "과.채주스"]):
                        selected_types.append(t)
        per_type = st.slider("유형별 조회 건수", 10, 50, 20, step=5)

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### 🤖 Gemini 설정")
    if GEMINI_KEY:
        st.success("API 키 연결됨", icon="✅")
    else:
        st.warning("GEMINI_API_KEY 없음", icon="⚠️")
        st.caption("secrets.toml에 GEMINI_API_KEY 추가 필요")
    gemini_model = st.selectbox("모델", GEMINI_MODELS, index=0)

    st.markdown("---")
    st.caption("📡 식품안전나라 I1250")
    st.caption("⚠️ 일일 2,000회 호출 제한")
    if st.button("🔄 DB 총 건수 캐시 초기화", use_container_width=True):
        st.session_state.pop("db_total", None)
        st.cache_data.clear()
        st.success("초기화 완료")


# ══════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("식품유형별 최신 품목제조보고를 초고속으로 조회합니다.")
st.markdown("---")

if not run:
    st.info("👈 사이드바에서 식품유형을 선택하고 **[조회 실행]**을 누르세요.")
    c1, c2, c3 = st.columns(3)
    c1.metric("🚀 초고속", "3~8초", "최근 1만건 스캔")
    c2.metric("⚡ 빠름",   "8~15초", "최근 3만건 스캔")
    c3.metric("🔍 보통",   "20~40초", "최근 10만건 스캔")
    st.info("💡 결과가 너무 적으면 스캔 범위를 늘리거나 캐시를 초기화하세요.")


# ─────────────── 단일 유형 조회 ───────────────
elif mode == "📋 단일 유형 조회":
    import time
    t0 = time.time()
    msg = st.empty()
    msg.info(f"📡 **'{food_type}'** 최근 {scan_pages * 1000:,}건 스캔 중…")

    # total은 캐시 함수 밖에서 계산 (session_state 사용 가능)
    total = _get_total()
    rows, ok_pages = fetch_fast(food_type, count, scan_pages, total)
    elapsed = time.time() - t0
    df = to_df(rows)

    if df.empty:
        msg.warning(
            f"⚠️ **'{food_type}'** 결과 없음 (최근 {scan_pages*1000:,}건 내)\n\n"
            "스캔 범위를 늘리거나 식품유형명을 확인하세요."
        )
    else:
        msg.success(
            f"✅ **{len(df)}건** 조회 완료 | "
            f"소요: **{elapsed:.1f}초** | "
            f"응답 성공: {ok_pages}/{scan_pages}페이지"
        )

        # 메트릭
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("조회 결과",    f"{len(df)}건")
        m2.metric("전체 DB 규모", f"{total:,}건")
        m3.metric("식품유형",      food_type)
        if "제조사" in df.columns:
            m4.metric("제조사 수", f"{df['제조사'].nunique()}개")

        st.markdown("---")

        # 탭
        tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

        with tab1:
            st.markdown(f"### 📋 {food_type} 최신 제품 목록")
            ca, cb = st.columns(2)
            with ca:
                kw = st.text_input("🔎 검색", placeholder="제품명·제조사")
            with cb:
                makers = (["전체"] + sorted(df["제조사"].dropna().unique().tolist())
                          if "제조사" in df.columns else ["전체"])
                sel_mk = st.selectbox("제조사 필터", makers)

            fdf = df.copy()
            if kw:
                fdf = fdf[fdf.apply(lambda r: kw.lower() in str(r).lower(), axis=1)]
            if "제조사" in df.columns and sel_mk != "전체":
                fdf = fdf[fdf["제조사"] == sel_mk]

            sc = [c for c in ["제품명", "식품유형", "제조사", "보고일자", "유통기한", "생산종료"]
                  if c in fdf.columns]
            st.dataframe(fdf[sc].reset_index(drop=True),
                         use_container_width=True, height=480)
            st.caption(f"총 {len(fdf)}건 표시")

        with tab2:
            render_charts(df, food_type)

        with tab3:
            st.dataframe(df, use_container_width=True, height=480)
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 CSV 다운로드", csv,
                f"{food_type}_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv", use_container_width=True,
            )

        # AI 분석 (탭 밖, 결과 바로 아래)
        render_ai_section(df, food_type, gemini_model)


# ─────────────── 복수 유형 비교 ───────────────
else:
    if not selected_types:
        st.warning("⚠️ 유형을 1개 이상 선택하세요.")
    else:
        import time
        t0 = time.time()
        all_rows, status_map = [], {}
        prog = st.progress(0)
        total = _get_total()   # 캐시 함수 밖에서 1회 계산

        for i, ft in enumerate(selected_types):
            prog.progress((i + 1) / len(selected_types),
                          text=f"📡 {ft} 조회 중… ({i+1}/{len(selected_types)})")
            rows, _ = fetch_fast(ft, per_type, 10, total)
            status_map[ft] = {"fetched": len(rows), "total": total}
            all_rows.extend(rows)
        prog.empty()

        elapsed = time.time() - t0
        st.success(f"✅ {len(selected_types)}개 유형 완료 ({elapsed:.1f}초)")

        # 요약 메트릭
        cols = st.columns(min(len(selected_types), 5))
        for i, ft in enumerate(selected_types):
            info = status_map[ft]
            with cols[i % len(cols)]:
                st.metric(ft, f"{info['fetched']}건",
                          f"전체 {info['total']:,}건")

        if not all_rows:
            st.warning("조회된 데이터가 없습니다.")
        else:
            df = to_df(all_rows)
            st.markdown("---")

            tab1, tab2, tab3 = st.tabs(["📋 통합 목록", "📊 유형별 비교", "📥 데이터"])

            with tab1:
                types_in = ["전체"] + sorted(df["식품유형"].dropna().unique().tolist())
                sel_t    = st.selectbox("식품유형 필터", types_in)
                sdf      = df if sel_t == "전체" else df[df["식품유형"] == sel_t]
                sc       = [c for c in ["제품명", "식품유형", "제조사", "보고일자", "유통기한"]
                            if c in sdf.columns]
                st.dataframe(sdf[sc].reset_index(drop=True),
                             use_container_width=True, height=480)

            with tab2:
                c1, c2 = st.columns(2)
                with c1:
                    tc = df["식품유형"].value_counts()
                    fig = px.bar(x=tc.index, y=tc.values, title="유형별 조회 건수",
                                 labels={"x": "식품유형", "y": "건수"}, color=tc.index)
                    fig.update_layout(height=380, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    if "제조사" in df.columns:
                        mt = (df.groupby("식품유형")["제조사"]
                              .nunique().reset_index()
                              .rename(columns={"제조사": "제조사수"}))
                        fig2 = px.bar(mt, x="식품유형", y="제조사수",
                                      title="유형별 제조사 다양성", color="식품유형")
                        fig2.update_layout(height=380, showlegend=False)
                        st.plotly_chart(fig2, use_container_width=True)

                for ft in selected_types:
                    ft_df = df[df["식품유형"] == ft]
                    if not ft_df.empty and "제조사" in ft_df.columns:
                        top = ft_df["제조사"].value_counts().head(5)
                        with st.expander(f"**{ft}** 상위 제조사 ({len(ft_df)}건)"):
                            for rank, (mk, cnt) in enumerate(top.items(), 1):
                                st.markdown(f"{rank}. **{mk}** — {cnt}건")

            with tab3:
                st.dataframe(df, use_container_width=True, height=480)
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 CSV 다운로드", csv,
                    f"품목비교_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv", use_container_width=True,
                )
