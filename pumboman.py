"""
🔍 식품안전나라 품목제조보고 조회 시스템 v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- API 키: st.secrets (FOOD_SAFETY_API_KEY, GEMINI_API_KEY / GOOGLE_API_KEY)
- 조회 속도: 포털 내부 Ajax → I1250 병렬 페이지네이션 (fallback)
- AI 분석: Gemini 2.0 Flash, 조회 결과 바로 아래 표시
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# ══════════════════════════════════════════════════════
#  설정 — secrets.toml 에서 로드
# ══════════════════════════════════════════════════════
def _get_secret(*keys, default=""):
    """여러 키 이름 중 하나라도 있으면 반환"""
    try:
        for k in keys:
            v = st.secrets.get(k, "")
            if v:
                return v
    except Exception:
        pass
    return default

FOOD_API_KEY = _get_secret("FOOD_SAFETY_API_KEY", "FOODSAFETY_API_KEY",
                            default="9171f7ffd72f4ffcb62f")  # 기본값 fallback
GEMINI_KEY   = _get_secret("GEMINI_API_KEY", "GOOGLE_API_KEY")

SERVICE_ID = "I1250"
BASE_URL   = f"http://openapi.foodsafetykorea.go.kr/api/{FOOD_API_KEY}/{SERVICE_ID}/json"

PORTAL_URLS = [
    "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoProductList.do",
    "https://www.foodsafetykorea.go.kr/portal/specialinfo/getSearchInfoProductList.do",
    "https://www.foodsafetykorea.go.kr/portal/product/retrieveProductList.do",
]
PORTAL_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":         "https://www.foodsafetykorea.go.kr/portal/specialinfo/searchInfoProduct.do",
    "Accept":          "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With":"XMLHttpRequest",
    "Content-Type":    "application/x-www-form-urlencoded; charset=UTF-8",
}

CATEGORY_CODES = {
    "음료류": "D007", "과자류": "D004", "빵.면류": "D005",
    "조미.소스류": "D010", "유가공품": "D002", "건강기능식품": "J001", "기타": "",
}

FOOD_TYPES = {
    "음료류": [
        "혼합음료",
        "다류",          # 침출차·액상차·고형차 포함
        "커피",          # 볶은커피·인스턴트커피·조제커피·액상커피 포함
        "농축과.채즙",
        "과.채주스",
        "과.채음료",
        "탄산음료",
        "탄산수",
        "두유류",
        "유산균음료",
        "인삼.홍삼음료",
        "기타음료",
    ],
    "과자류":      ["과자", "캔디류", "추잉껌", "빙과", "아이스크림"],
    "빵.면류":    ["빵류", "떡류", "면류", "즉석섭취식품"],
    "조미.소스류": ["소스", "복합조미식품", "향신료가공품", "식초", "드레싱"],
    "유가공품":    ["치즈", "버터", "발효유", "우유류", "가공유"],
    "건강기능식품": ["건강기능식품"],
    "기타":        ["잼류", "식용유지", "김치류", "두부류", "즉석조리식품", "레토르트식품"],
}
TYPE_TO_CAT = {t: c for c, ts in FOOD_TYPES.items() for t in ts}

COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형", "BSSH_NM": "제조사",
    "PRMS_DT": "보고일자", "POG_DAYCNT": "유통기한", "PRODUCTION": "생산종료",
    "INDUTY_CD_NM": "업종", "USAGE": "용법", "PRPOS": "용도",
    "LCNS_NO": "인허가번호", "PRDLST_REPORT_NO": "품목제조번호",
    "HIENG_LNTRT_DVS_NM": "고열량저영양", "CHILD_CRTFC_YN": "어린이기호식품인증",
    "LAST_UPDT_DTM": "최종수정일", "DISPOS": "제품형태",
    "FRMLC_MTRQLT": "포장재질", "QLITY_MNTNC_TMLMT_DAYCNT": "품질유지기한일수",
}

AI_ICONS = {
    "트렌드 요약": "📈",
    "제조사 경쟁구도": "🏢",
    "신제품 출시 패턴": "🆕",
    "원료·성분 특징 요약": "🧪",
}

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.5-flash-preview-04-17",
]


# ══════════════════════════════════════════════════════
#  데이터 조회
# ══════════════════════════════════════════════════════
def _try_portal(food_type: str, category: str, count: int):
    """포털 내부 Ajax API 시도 (서버사이드 필터, 빠름)"""
    cat_code = CATEGORY_CODES.get(category, "")
    variants = [
        {"prdlst_dcnm": food_type, "prdlst_dcnm_cd": cat_code,
         "pageIndex": "1", "rows": str(count), "sort_column": "PRMS_DT", "sort_order": "desc"},
        {"PRDLST_DCNM": food_type, "PRDLST_DCNM_CD": cat_code,
         "pageIndex": "1", "pageSize": str(count)},
        {"searchType": "PRDLST_DCNM", "searchKeyword": food_type,
         "catCd": cat_code, "pageIndex": "1", "rows": str(count)},
    ]
    for url in PORTAL_URLS:
        for params in variants:
            try:
                r = requests.post(url, data=params, headers=PORTAL_HEADERS, timeout=15)
                if r.status_code != 200:
                    continue
                ct = r.headers.get("Content-Type", "")
                if "json" not in ct and "javascript" not in ct:
                    continue
                data = r.json()
                rows = (data if isinstance(data, list)
                        else next((data[k] for k in
                                   ("list","rows","data","items","result","productList","row")
                                   if k in data and isinstance(data[k], list)), None))
                if rows:
                    # 컬럼명 정규화
                    pmap = {"prdlst_nm":"PRDLST_NM","bssh_nm":"BSSH_NM",
                            "prdlst_dcnm":"PRDLST_DCNM","prms_dt":"PRMS_DT",
                            "pog_daycnt":"POG_DAYCNT","production":"PRODUCTION",
                            "induty_cd_nm":"INDUTY_CD_NM","lcns_no":"LCNS_NO",
                            "prdlst_report_no":"PRDLST_REPORT_NO","last_updt_dtm":"LAST_UPDT_DTM"}
                    rows = [{pmap.get(k.lower(), k.upper()): v for k, v in row.items()}
                            for row in rows]
                    for row in rows:
                        row.setdefault("PRDLST_DCNM", food_type)
                    return rows, f"포털 내부 API"
            except Exception:
                continue
    return None, "포털 내부 API 미응답"


def _fetch_page(start: int, end: int):
    """I1250 단일 페이지 호출 (스레드 워커)"""
    try:
        r = requests.get(f"{BASE_URL}/{start}/{end}", timeout=30)
        r.raise_for_status()
        result = r.json().get(SERVICE_ID, {})
        if result.get("RESULT", {}).get("CODE") == "INFO-000":
            return result.get("row", [])
        return []
    except Exception:
        return []


def _try_server_filter(food_type: str, count: int) -> tuple:
    """
    I1250 URL 경로 필터 시도.
    URL: {BASE}/1/{count}/PRDLST_DCNM={인코딩 유형명}
    반환 행의 90% 이상이 food_type과 일치하면 서버필터 성공으로 판정.
    성공 시 (rows, msg), 실패 시 (None, reason).
    """
    import urllib.parse
    encoded = urllib.parse.quote(food_type.strip(), safe="")
    url = f"{BASE_URL}/1/{min(count, 1000)}/PRDLST_DCNM={encoded}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        result = r.json().get(SERVICE_ID, {})
        if result.get("RESULT", {}).get("CODE") != "INFO-000":
            return None, "서버필터 응답 코드 오류"
        rows = result.get("row", [])
        if not rows:
            return None, "서버필터 결과 없음"
        matched = [row for row in rows
                   if row.get("PRDLST_DCNM", "").strip() == food_type.strip()]
        if len(matched) / len(rows) >= 0.9:
            return matched, "I1250 서버필터"
        return None, f"서버필터 미작동 (일치율 {len(matched)/len(rows):.0%})"
    except Exception as e:
        return None, f"서버필터 예외: {e}"


def _fetch_parallel(food_type: str, count: int, max_pages: int = 30):
    """
    I1250 병렬 역순 스캔.

    max_pages 제한이 핵심:
      - 최신 레코드가 DB 뒤에 쌓이므로 끝 페이지부터 스캔
      - 기본 30페이지 = 최근 3만건만 탐색 → 대부분 5~10초 내 완료
      - max_pages=None 이면 전체 DB 스캔 (느림)
    """
    PAGE        = 1000
    MAX_WORKERS = 8

    try:
        r     = requests.get(f"{BASE_URL}/1/1", timeout=15)
        total = int(r.json().get(SERVICE_ID, {}).get("total_count", 0))
    except Exception as e:
        return None, f"total_count 조회 실패: {e}", 0

    if total == 0:
        return [], "데이터 없음", 0

    # 역순 페이지 목록 (끝 → 처음)
    all_pages = []
    end = total
    while end > 0:
        start = max(end - PAGE + 1, 1)
        all_pages.append((start, end))
        end = start - 1

    # max_pages 제한 적용
    if max_pages and len(all_pages) > max_pages:
        pages = all_pages[:max_pages]   # 최신 max_pages개만
        scope_msg = f"최근 {max_pages * PAGE:,}건"
    else:
        pages = all_pages
        scope_msg = "전체"

    collected, done = [], False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_page, s, e): None for s, e in pages}
        for fut in as_completed(futures):
            if done:
                fut.cancel()
                continue
            rows = fut.result() or []
            collected.extend(
                row for row in rows
                if row.get("PRDLST_DCNM", "").strip() == food_type.strip()
            )
            if len(collected) >= count:
                done = True

    return collected[:count], f"I1250 병렬-역순 ({scope_msg} 스캔)", total


@st.cache_data(ttl=600, show_spinner=False)
def fetch_food_data(food_type: str, count: int, category: str = "",
                    max_pages: int = 30):
    """
    조회 우선순위:
      1) 포털 내부 Ajax API (서버사이드 필터, 가장 빠름)
      2) I1250 URL 경로 서버필터 (PRDLST_DCNM=값)
      3) I1250 병렬 역순 스캔 (max_pages로 범위 제한)
    """
    cat = category or TYPE_TO_CAT.get(food_type, "")

    # 1순위: 포털 내부 Ajax
    rows, msg = _try_portal(food_type, cat, count)
    if rows is not None:
        return rows, msg, len(rows)

    # 2순위: I1250 서버필터
    rows, msg = _try_server_filter(food_type, count)
    if rows is not None:
        return rows, msg, len(rows)

    # 3순위: I1250 병렬 역순 스캔 (범위 제한)
    return _fetch_parallel(food_type, count, max_pages=max_pages)


def fetch_multiple(types_list: list, per_type: int, max_pages: int = 30):
    all_rows, status = [], {}
    prog = st.progress(0)
    for i, ft in enumerate(types_list):
        prog.progress((i + 1) / len(types_list), text=f"📡 {ft} 조회 중…")
        rows, msg, total = fetch_food_data(ft, per_type, max_pages=max_pages)
        status[ft] = {"msg": msg, "total": total, "fetched": len(rows) if rows else 0}
        if rows:
            all_rows.extend(rows)
    prog.empty()
    return all_rows, status


def to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).rename(columns={k: v for k, v in COL_MAP.items()
                                             if k in pd.DataFrame(rows).columns})
    if "보고일자" in df.columns:
        df["보고일자"] = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════
#  Gemini AI 분석
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def _gemini_call(prompt: str, model_name: str) -> str:
    """결과 텍스트만 캐시 (모델 객체는 캐시 불가 — 반드시 함수 내부에서 생성)"""
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel(model_name)
    return model.generate_content(prompt).text


def build_prompts(df: pd.DataFrame, food_type: str) -> dict:
    """분석 데이터 준비 및 프롬프트 생성"""
    prefix = (
        f"당신은 식품 R&D 전문가입니다. "
        f"식품안전나라 품목제조보고 DB에서 조회한 **{food_type}** {len(df)}건 데이터입니다.\n"
        f"한국어로, 식품 R&D 담당자가 즉시 활용 가능한 실무적 인사이트로 작성하세요.\n\n"
    )

    monthly = {}
    if "보고일자_dt" in df.columns:
        tmp = df.dropna(subset=["보고일자_dt"]).copy()
        if not tmp.empty:
            tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
            monthly = tmp["연월"].value_counts().sort_index().tail(24).to_dict()

    maker_top = df["제조사"].value_counts().head(10).to_dict() if "제조사" in df.columns else {}
    maker_n   = df["제조사"].nunique() if "제조사" in df.columns else "N/A"

    cols = [c for c in ["제품명", "제조사", "보고일자"] if c in df.columns]
    recent = df[cols].head(30).to_dict(orient="records")

    return {
        "트렌드 요약": (
            prefix
            + f"### 월별 보고 건수 (최근 24개월)\n{monthly}\n\n"
            + f"### 최신 보고 제품 30건\n{recent}\n\n"
            + "분석 항목 (각 2~3문장):\n"
            + "1. 신제품 출시 트렌드 (증감·계절성)\n"
            + "2. 주목할 제품명 패턴·키워드\n"
            + "3. R&D 관점 시사점"
        ),
        "제조사 경쟁구도": (
            prefix
            + f"### 제조사별 제품 수 상위 10\n{maker_top}\n"
            + f"전체 제조사 수: {maker_n}개\n\n"
            + "분석 항목 (각 2~3문장):\n"
            + "1. 시장 집중도 (상위 3개사 점유율 추정)\n"
            + "2. 경쟁 구도 특징 (과점/분산/신규 진입)\n"
            + "3. 중소 제조사 진입 여지"
        ),
        "신제품 출시 패턴": (
            prefix
            + f"### 최신 보고 제품 30건\n{recent}\n\n"
            + f"### 월별 보고 건수\n{monthly}\n\n"
            + "분석 항목 (각 2~3문장):\n"
            + "1. 제품명 공통 키워드·트렌드 (기능성·원료·포맷)\n"
            + "2. 출시 시기 패턴\n"
            + "3. 예상 다음 트렌드"
        ),
        "원료·성분 특징 요약": (
            prefix
            + f"### 최신 보고 제품 30건 (제품명 기준)\n{recent}\n\n"
            + "분석 항목 (각 2~3문장):\n"
            + "1. 자주 등장하는 원료·기능성 소재 키워드\n"
            + "2. 무가당·저칼로리·기능성 헬스 포지셔닝 비중\n"
            + "3. R&D 포뮬레이션 관점 주목 소재\n"
            + "※ 제품명 기반 추정임을 명시하세요."
        ),
    }


def render_ai_section(df: pd.DataFrame, food_type: str, model_name: str):
    """조회 결과 아래 AI 분석 섹션 렌더링"""
    st.markdown("---")
    st.markdown("## 🤖 Gemini AI 분석")

    if not GENAI_AVAILABLE:
        st.error("google-generativeai 패키지 없음\n```bash\npip install google-generativeai\n```")
        return

    if not GEMINI_KEY:
        st.warning(
            "**Gemini API 키가 없습니다.**\n\n"
            "`.streamlit/secrets.toml`에 아래 중 하나를 추가하세요:\n"
            "```toml\nGEMINI_API_KEY = \"AIza...\"\n"
            "# 또는\nGOOGLE_API_KEY = \"AIza...\"\n```\n\n"
            "[🔑 Google AI Studio에서 무료 발급](https://aistudio.google.com/app/apikey)"
        )
        return

    st.info(f"모델: **{model_name}** | 대상: **{food_type}** {len(df)}건")

    if not st.button("🔍 AI 분석 실행", key="btn_ai", type="primary",
                     use_container_width=True):
        return

    prompts = build_prompts(df, food_type)
    ai_results = {}

    for title, prompt in prompts.items():
        st.markdown(f"#### {AI_ICONS[title]} {title}")
        box = st.empty()
        box.info("분석 중…")
        try:
            text = _gemini_call(prompt, model_name)
            ai_results[title] = text
            box.markdown(text)
        except Exception as e:
            msg = str(e)
            ai_results[title] = f"❌ {msg}"
            box.error(f"분석 실패: {msg}")
        st.markdown("")

    if any(not v.startswith("❌") for v in ai_results.values()):
        full = "\n\n".join(f"## {AI_ICONS.get(t,'')} {t}\n{c}"
                           for t, c in ai_results.items())
        st.download_button(
            "📥 AI 분석 결과 TXT 다운로드",
            full.encode("utf-8"),
            f"{food_type}_AI분석_{datetime.now().strftime('%Y%m%d')}.txt",
            "text/plain", use_container_width=True,
        )


# ══════════════════════════════════════════════════════
#  차트 헬퍼
# ══════════════════════════════════════════════════════
def render_charts(df: pd.DataFrame, food_type: str):
    st.markdown(f"### 📊 {food_type} 데이터 분석")
    ch1, ch2 = st.columns(2)

    if "제조사" in df.columns:
        with ch1:
            mc = df["제조사"].value_counts().head(15)
            fig = px.bar(x=mc.values, y=mc.index, orientation="h",
                         title="제조사별 제품 수 (상위 15)",
                         labels={"x": "제품 수", "y": "제조사"},
                         color=mc.values, color_continuous_scale="Blues")
            fig.update_layout(height=450, showlegend=False,
                               yaxis=dict(autorange="reversed"))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    if "보고일자_dt" in df.columns:
        with ch2:
            tmp = df.dropna(subset=["보고일자_dt"]).copy()
            if not tmp.empty:
                tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
                mo = tmp["연월"].value_counts().sort_index().tail(24)
                fig2 = px.line(x=mo.index, y=mo.values,
                               title="월별 보고 건수 추이 (최근 24개월)",
                               labels={"x": "연월", "y": "건수"}, markers=True)
                fig2.update_layout(height=450)
                st.plotly_chart(fig2, use_container_width=True)

    if "생산종료" in df.columns:
        pc = df["생산종료"].value_counts()
        fig3 = px.pie(values=pc.values, names=pc.index, title="생산종료 현황",
                      color_discrete_sequence=px.colors.qualitative.Set2)
        fig3.update_layout(height=350)
        st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════
#  페이지 설정 & 스타일
# ══════════════════════════════════════════════════════
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #f8f9fb; }
div[data-testid="stMetric"] {
    background: #f0f2f5; border-radius: 10px; padding: 12px;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  사이드바
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🔍 조회 설정")
    st.markdown("---")

    mode = st.radio("조회 방식",
                    ["📋 단일 유형 조회", "📊 복수 유형 비교"])

    st.markdown("---")

    if mode == "📋 단일 유형 조회":
        category  = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
        food_type = st.selectbox("식품유형", FOOD_TYPES[category])
        custom    = st.text_input("직접 입력",
                                  placeholder="예: 혼합음료 (마침표 . 사용)")
        if custom.strip():
            food_type = custom.strip()
            category  = TYPE_TO_CAT.get(food_type, category)
        count = st.slider("조회 건수", 10, 300, 100, step=10)

        st.markdown("**조회 범위 (속도 조절)**")
        scope_opt = st.radio(
            "스캔 범위",
            ["⚡ 빠름 — 최근 3만건", "🔍 보통 — 최근 10만건", "🌐 전체 DB (느림)"],
            index=0,
            help="'최근 N만건'은 DB 끝(최신)부터 역순 스캔합니다.\n결과가 없으면 범위를 늘려보세요.",
        )
        scope_pages = {"⚡ 빠름 — 최근 3만건": 30,
                       "🔍 보통 — 최근 10만건": 100,
                       "🌐 전체 DB (느림)": None}[scope_opt]

    else:
        st.markdown("**비교할 유형 선택:**")
        selected_types = []
        for cat, types in FOOD_TYPES.items():
            with st.expander(cat, expanded=(cat == "음료류")):
                for t in types:
                    if st.checkbox(t, value=(t in ["혼합음료", "과.채주스", "과.채음료"]),
                                   key=f"cb_{t}"):
                        selected_types.append(t)
        per_type = st.slider("유형별 조회 건수", 10, 50, 20, step=5)

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")

    # Gemini 설정
    st.markdown("---")
    st.markdown("### 🤖 Gemini 설정")
    if GEMINI_KEY:
        st.success("API 키 연결됨", icon="✅")
    else:
        st.warning("GEMINI_API_KEY 없음", icon="⚠️")
        st.caption("`.streamlit/secrets.toml` 참고")

    gemini_model = st.selectbox("모델", GEMINI_MODELS, index=0)

    st.markdown("---")
    st.caption("📡 식품안전나라 I1250 API")
    st.caption("⚠️ 일일 API 호출 2,000회 제한")
    st.caption("조회 우선순위: 포털 내부 API → I1250 병렬")


# ══════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("식품유형별 최신 품목제조보고 데이터를 실시간으로 조회합니다.")
st.markdown("---")

if not run:
    st.info("👈 사이드바에서 식품유형을 선택하고 **[조회 실행]** 버튼을 누르세요.")
    st.markdown("""
| 조회 방식 | 예상 소요 |
|---|---|
| 🏃 포털 내부 API (서버 필터) | 1~3초 |
| ⚡ I1250 병렬 페이지네이션 (fallback) | 10~20초 |

> ⚠️ **마침표 주의**: 식품안전나라 DB는 `과.채주스` (마침표 `.`) 표기를 사용합니다.
""")

# ────────────────────────── 단일 유형 조회 ──────────────────────────
elif mode == "📋 단일 유형 조회":
    t0  = time.time()
    msg_box = st.empty()
    msg_box.info(f"📡 **'{food_type}'** 조회 중… (포털 → 서버필터 → 병렬스캔 순 시도)")

    rows, src, total = fetch_food_data(food_type, count, category,
                                       max_pages=scope_pages)
    elapsed = time.time() - t0

    if rows is None:
        st.error(f"❌ 조회 실패: {src}")

    elif len(rows) == 0:
        st.warning(
            f"⚠️ **'{food_type}'** 데이터가 없습니다.\n\n"
            "DB의 실제 PRDLST_DCNM 값과 완전일치하는지 확인하세요. "
            "(DB 표기: 마침표 `.` — 예: 과.채주스, 인삼.홍삼음료)"
        )

    else:
        badge = ("🏃 포털 내부 API" if "포털" in src
                 else "⚡ I1250 서버필터" if "서버필터" in src
                 else "🔄 I1250 병렬-역순")
        msg_box.success(f"✅ {badge} — **{len(rows)}건** 조회 완료 ({elapsed:.1f}초)")

        df = to_df(rows)

        # 메트릭
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("조회 결과",    f"{len(df)}건")
        c2.metric("전체 등록 수", f"{total:,}건" if total > len(df) else "-")
        c3.metric("식품유형",      food_type)
        if "제조사" in df.columns:
            c4.metric("제조사 수", f"{df['제조사'].nunique()}개")

        st.markdown("---")

        # 탭
        tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

        with tab1:
            st.markdown(f"### 📋 {food_type} 품목 목록 ({len(df)}건)")
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

            sc = [c for c in ["제품명","식품유형","제조사","보고일자","유통기한","생산종료"]
                  if c in fdf.columns]
            st.dataframe(fdf[sc].reset_index(drop=True),
                         use_container_width=True, height=500)
            st.caption(f"총 {len(fdf)}건 표시")

        with tab2:
            render_charts(df, food_type)

        with tab3:
            st.markdown("### 📥 원시 데이터")
            st.dataframe(df, use_container_width=True, height=500)
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 CSV 다운로드", csv,
                f"{food_type}_품목제조보고_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv", use_container_width=True,
            )

        # AI 분석 — 탭 바깥, 조회 결과 바로 아래
        render_ai_section(df, food_type, gemini_model)


# ────────────────────────── 복수 유형 비교 ──────────────────────────
else:
    if not selected_types:
        st.warning("⚠️ 비교할 식품유형을 1개 이상 선택하세요.")
    else:
        t0 = time.time()
        all_rows, status = fetch_multiple(selected_types, per_type, max_pages=30)
        elapsed = time.time() - t0

        st.success(f"✅ {len(selected_types)}개 유형 조회 완료 ({elapsed:.1f}초)")
        st.markdown("### 📡 조회 결과 요약")

        cols = st.columns(min(len(selected_types), 5))
        for i, ft in enumerate(selected_types):
            info = status[ft]
            with cols[i % len(cols)]:
                if info["fetched"] > 0:
                    st.metric(ft, f"{info['fetched']}건",
                              f"전체 {info['total']:,}건")
                else:
                    st.metric(ft, "0건", info["msg"])

        if not all_rows:
            st.warning("조회된 데이터가 없습니다.")
        else:
            df = to_df(all_rows)
            st.markdown("---")

            tab1, tab2, tab3 = st.tabs(["📋 통합 목록", "📊 유형별 비교", "📥 데이터"])

            with tab1:
                st.markdown(f"### 📋 통합 목록 ({len(df)}건)")
                types_in = ["전체"] + sorted(df["식품유형"].dropna().unique().tolist())
                sel_t    = st.selectbox("식품유형 필터", types_in)
                sdf      = df if sel_t == "전체" else df[df["식품유형"] == sel_t]
                sc       = [c for c in ["제품명","식품유형","제조사","보고일자","유통기한"]
                            if c in sdf.columns]
                st.dataframe(sdf[sc].reset_index(drop=True),
                             use_container_width=True, height=500)

            with tab2:
                st.markdown("### 📊 식품유형별 비교")
                ch1, ch2 = st.columns(2)

                with ch1:
                    tc = df["식품유형"].value_counts()
                    fig = px.bar(x=tc.index, y=tc.values,
                                 title="유형별 조회 건수",
                                 labels={"x":"식품유형","y":"건수"},
                                 color=tc.index)
                    fig.update_layout(height=400, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

                with ch2:
                    if "제조사" in df.columns:
                        mt = (df.groupby("식품유형")["제조사"]
                              .nunique().reset_index()
                              .rename(columns={"제조사": "제조사수"}))
                        fig2 = px.bar(mt, x="식품유형", y="제조사수",
                                      title="유형별 제조사 다양성",
                                      color="식품유형")
                        fig2.update_layout(height=400, showlegend=False)
                        st.plotly_chart(fig2, use_container_width=True)

                st.markdown("#### 🏢 유형별 상위 제조사")
                for ft in selected_types:
                    ft_df = df[df["식품유형"] == ft]
                    if not ft_df.empty and "제조사" in ft_df.columns:
                        top = ft_df["제조사"].value_counts().head(5)
                        with st.expander(f"**{ft}** (총 {len(ft_df)}건)"):
                            for rank, (mk, cnt) in enumerate(top.items(), 1):
                                st.markdown(f"{rank}. **{mk}** — {cnt}건")

            with tab3:
                st.dataframe(df, use_container_width=True, height=500)
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 CSV 다운로드", csv,
                    f"품목제조보고_비교_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv", use_container_width=True,
                )
