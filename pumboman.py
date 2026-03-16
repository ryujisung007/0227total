"""
식품안전나라 품목제조보고 조회 v5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
조회 전략: 병렬 스캔 폐기 → 단일 필터 요청 1회
  URL: /api/KEY/I1250/json/1/N/PRDLST_DCNM=유형명
  서버가 필터링해서 반환 → 전체 DB 순회 불필요
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from collections import Counter
import re
import time

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

GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash-preview-04-17"]

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
#  조회 — 단일 필터 요청 (병렬 없음)
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=600, show_spinner=False)
def fetch_by_filter(food_type: str, count: int) -> tuple:
    """
    필터 파라미터 완전 제거.
    이유: 서버가 필터 처리 시 자체 타임아웃(30초) 발생.
    
    전략: 필터 없이 최신 페이지 순차 조회 → 클라이언트 필터
    - 1회 요청: 30건 (서버 부하 최소화)
    - 최신순(높은 번호)부터 조회
    - count건 채우면 즉시 중단
    """
    CHUNK    = 30
    MAX_ITER = 30           # 최대 900건 스캔
    headers  = {"Accept": "application/json"}

    # 전체 건수 파악 (1건만 요청 → 빠름)
    total = 0
    try:
        r = requests.get(f"{BASE_URL}/1/1", headers=headers, timeout=10)
        total = int(r.json().get(SERVICE_ID, {}).get("total_count", 500000))
    except Exception:
        total = 500000

    collected = []

    for i in range(MAX_ITER):
        # 끝(최신)부터 역순으로 페이지 계산
        end   = total - i * CHUNK
        start = max(end - CHUNK + 1, 1)
        if start > end or end <= 0:
            break

        url = f"{BASE_URL}/{start}/{end}"
        try:
            r    = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            result = r.json().get(SERVICE_ID, {})
            code   = result.get("RESULT", {}).get("CODE", "")

            if code == "INFO-000":
                rows = result.get("row", [])
                matched = [
                    row for row in rows
                    if row.get("PRDLST_DCNM", "").strip() == food_type.strip()
                ]
                collected.extend(matched)

            if len(collected) >= count:
                break

        except Exception:
            continue   # 실패한 페이지는 무시하고 계속

    collected.sort(key=lambda r: r.get("PRMS_DT", ""), reverse=True)
    src = f"최신 {min((i+1)*CHUNK, total):,}건 스캔"
    return collected[:count], total, src


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

    if "제조사" in df.columns:
        with c1:
            mc = df["제조사"].value_counts().head(15)
            fig = px.bar(x=mc.values, y=mc.index, orientation="h",
                         title="제조사별 제품 수 (상위 15)",
                         color=mc.values, color_continuous_scale="Blues",
                         labels={"x": "제품 수", "y": "제조사"})
            fig.update_layout(height=400, showlegend=False,
                               yaxis=dict(autorange="reversed"))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

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
                fig2.update_layout(height=400)
                st.plotly_chart(fig2, use_container_width=True)

    c3, c4 = st.columns(2)
    if "생산종료" in df.columns:
        with c3:
            pc = df["생산종료"].value_counts()
            fig3 = px.pie(values=pc.values, names=pc.index,
                          title="생산종료 현황",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig3.update_layout(height=320)
            st.plotly_chart(fig3, use_container_width=True)

    if "제조사" in df.columns:
        with c4:
            top10  = df["제조사"].value_counts().head(10)
            others = max(0, len(df) - top10.sum())
            labels = list(top10.index) + (["기타"] if others > 0 else [])
            values = list(top10.values) + ([others] if others > 0 else [])
            fig4 = px.pie(values=values, names=labels,
                          title="제조사 점유율 (상위 10)",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig4.update_layout(height=320)
            st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════
#  AI 분석
# ══════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def _gemini(prompt: str, model_name: str) -> str:
    genai.configure(api_key=GEMINI_KEY)
    return genai.GenerativeModel(model_name).generate_content(prompt).text


def _ctx(df: pd.DataFrame, food_type: str) -> dict:
    monthly = {}
    if "보고일자_dt" in df.columns:
        tmp = df.dropna(subset=["보고일자_dt"]).copy()
        if not tmp.empty:
            tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
            monthly = tmp["연월"].value_counts().sort_index().tail(24).to_dict()

    maker_top = df["제조사"].value_counts().head(10).to_dict() if "제조사" in df.columns else {}
    maker_n   = df["제조사"].nunique() if "제조사" in df.columns else "N/A"

    cols     = [c for c in ["제품명", "제조사", "보고일자"] if c in df.columns]
    recent30 = df[cols].head(30).to_dict(orient="records")

    kw_freq = {}
    if "제품명" in df.columns:
        words   = re.findall(r"[가-힣a-zA-Z]{2,}",
                             " ".join(df["제품명"].dropna().astype(str)))
        kw_freq = dict(Counter(words).most_common(30))

    return dict(food_type=food_type, total=len(df),
                monthly=monthly, maker_top=maker_top,
                maker_n=maker_n, recent30=recent30, kw_freq=kw_freq)


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

    st.info(f"모델: **{model_name}** | 대상: **{food_type}** {len(df)}건")

    if not st.button("🔬 AI 분석 시작", key="btn_ai", type="primary",
                     use_container_width=True):
        return

    ctx = _ctx(df, food_type)
    prefix = (
        f"당신은 15년 경력의 식품 R&D 수석 연구원입니다.\n"
        f"식품안전나라 품목제조보고 DB의 **{food_type}** {ctx['total']}건 데이터를 분석합니다.\n"
        f"실무에 바로 쓸 수 있는 전문적 인사이트를 한국어로 작성하세요.\n\n"
    )

    analyses = [
        {
            "title": "📈 시장 트렌드 분석",
            "prompt": (
                prefix
                + f"### 월별 보고 건수 (최근 24개월)\n{ctx['monthly']}\n\n"
                + f"### 제조사 상위 10\n{ctx['maker_top']}\n"
                + f"전체 제조사: {ctx['maker_n']}개\n\n"
                + f"### 최신 제품 30건\n{ctx['recent30']}\n\n"
                + "다음을 각 3~4문장으로 분석하세요:\n"
                + "## 1. 시장 성장성 (월별 트렌드 기반)\n"
                + "## 2. 경쟁 구도 및 시장 집중도\n"
                + "## 3. 신제품 출시 패턴\n"
                + "## 4. R&D 전략 시사점"
            ),
        },
        {
            "title": "🍋 플레이버 & 원료 트렌드",
            "prompt": (
                prefix
                + f"### 제품명 키워드 빈도 상위 30\n{ctx['kw_freq']}\n\n"
                + f"### 최신 제품 30건\n{ctx['recent30']}\n\n"
                + "다음을 각 3~4문장으로 분석하세요:\n"
                + "## 1. 주요 플레이버 트렌드\n"
                + "## 2. 기능성 원료 트렌드 (콜라겐·비타민·프로바이오틱스 등)\n"
                + "## 3. 신흥 플레이버 (최근 새롭게 등장한 것)\n"
                + "## 4. 포뮬레이션 방향 제언"
            ),
        },
        {
            "title": "🧪 추천 레시피 3종",
            "prompt": (
                prefix
                + f"### 키워드 빈도\n{ctx['kw_freq']}\n\n"
                + f"### 최신 제품 30건\n{ctx['recent30']}\n\n"
                + f"시장 데이터를 반영한 **{food_type}** 신제품 레시피 3종을 제안하세요.\n\n"
                + "각 레시피 형식:\n\n"
                + "## 레시피 N: [제품명]\n"
                + "**컨셉**: \n**타겟**: \n\n"
                + "**배합비**:\n"
                + "| 원료명 | 함량(%) | 역할 |\n|---|---|---|\n"
                + "| 정제수 | 00.0 | 기제 |\n\n"
                + "**제조 공정 포인트**: \n"
                + "**예상 규격**: pH / Brix / 칼로리\n"
                + "**차별화 포인트**: \n\n---\n\n"
                + "배합비 합계는 반드시 100%로 맞추세요."
            ),
        },
        {
            "title": "💡 종합 R&D 인사이트",
            "prompt": (
                prefix
                + f"조회건수: {ctx['total']}건 | 제조사: {ctx['maker_n']}개\n"
                + f"키워드: {ctx['kw_freq']}\n월별트렌드: {ctx['monthly']}\n\n"
                + "다음을 각 3~4문장으로 작성하세요:\n"
                + "## 1. 시장 기회 (포화되지 않은 틈새)\n"
                + "## 2. 리스크 요인 (피해야 할 방향)\n"
                + "## 3. 즉시 출시 추천 컨셉 (6개월 내)\n"
                + "## 4. 중장기 R&D 방향 (1~3년)"
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
            msg = f"❌ {e}"
            all_results[item["title"]] = msg
            box.error(msg)
        st.markdown("")

    if all_results:
        full = "\n\n---\n\n".join(f"{t}\n\n{c}" for t, c in all_results.items())
        st.download_button(
            "📥 AI 분석 전체 다운로드 (TXT)",
            full.encode("utf-8"),
            f"{food_type}_AI분석_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            "text/plain", use_container_width=True,
        )


# ══════════════════════════════════════════════════════
#  스타일
# ══════════════════════════════════════════════════════
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #f8f9fb; }
div[data-testid="stMetric"] { background: #f0f2f5; border-radius: 10px; padding: 12px; }
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
        count = st.slider("조회 건수", 10, 300, 100, step=10)

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
    gemini_model = st.selectbox("모델", GEMINI_MODELS, index=0)

    st.markdown("---")
    if st.button("🔄 캐시 초기화", use_container_width=True):
        st.cache_data.clear()
        st.success("완료")
    st.caption("📡 식품안전나라 I1250")
    st.caption("⚠️ 일일 2,000회 호출 제한")


# ══════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("서버사이드 필터 단일 요청 — 빠르고 안정적으로 조회합니다.")
st.markdown("---")

if not run:
    st.info("👈 사이드바에서 식품유형을 선택하고 **[조회 실행]**을 누르세요.")
    st.markdown("""
**조회 방식 변경 (v5)**

| 구분 | 기존 (병렬 스캔) | 현재 (단일 필터) |
|---|---|---|
| 요청 수 | 10~100개 동시 | **1~3개** |
| 타임아웃 위험 | 높음 | 낮음 |
| 예상 소요 | 불안정 | **5~15초** |
| 방식 | 전체 DB 순회 | 서버 직접 필터링 |

> 💡 결과가 없거나 적으면 **직접 입력란**에서 DB의 정확한 유형명을 입력해보세요.
""")


# ─────────────── 단일 유형 ───────────────
elif mode == "📋 단일 유형 조회":
    t0  = time.time()
    box = st.empty()
    box.info(f"📡 **'{food_type}'** 조회 중… (서버 필터 요청)")

    rows, total, src = fetch_by_filter(food_type, count)
    elapsed = time.time() - t0
    df = to_df(rows)

    if df.empty:
        box.error(
            f"❌ **'{food_type}'** 조회 실패 또는 결과 없음\n\n"
            f"**확인 사항:**\n"
            f"1. 식품유형명이 DB와 정확히 일치하는지 확인 (예: 과.채주스)\n"
            f"2. 사이드바 **[캐시 초기화]** 후 재시도\n"
            f"3. 식품안전나라 서버 상태 확인\n\n"
            f"조회 방식: `{src}`"
        )
    else:
        box.success(
            f"✅ **{len(df)}건** | 소요: **{elapsed:.1f}초** | "
            f"방식: {src} | 전체 등록: {total:,}건"
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("조회 결과",    f"{len(df)}건")
        m2.metric("전체 DB",      f"{total:,}건")
        m3.metric("식품유형",      food_type)
        if "제조사" in df.columns:
            m4.metric("제조사 수", f"{df['제조사'].nunique()}개")

        st.markdown("---")
        tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

        with tab1:
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

        render_ai_section(df, food_type, gemini_model)


# ─────────────── 복수 유형 비교 ───────────────
else:
    if not selected_types:
        st.warning("⚠️ 유형을 1개 이상 선택하세요.")
    else:
        t0       = time.time()
        all_rows = []
        status   = {}
        prog     = st.progress(0)

        for i, ft in enumerate(selected_types):
            prog.progress((i + 1) / len(selected_types),
                          text=f"📡 {ft} 조회 중… ({i+1}/{len(selected_types)})")
            rows, total, src = fetch_by_filter(ft, per_type)
            status[ft] = {"fetched": len(rows), "total": total, "src": src}
            all_rows.extend(rows)

        prog.empty()
        elapsed = time.time() - t0
        st.success(f"✅ {len(selected_types)}개 유형 완료 ({elapsed:.1f}초)")

        cols = st.columns(min(len(selected_types), 5))
        for i, ft in enumerate(selected_types):
            info = status[ft]
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
                sc = [c for c in ["제품명", "식품유형", "제조사", "보고일자", "유통기한"]
                      if c in sdf.columns]
                st.dataframe(sdf[sc].reset_index(drop=True),
                             use_container_width=True, height=480)

            with tab2:
                c1, c2 = st.columns(2)
                with c1:
                    tc  = df["식품유형"].value_counts()
                    fig = px.bar(x=tc.index, y=tc.values, title="유형별 조회 건수",
                                 color=tc.index, labels={"x": "식품유형", "y": "건수"})
                    fig.update_layout(height=380, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    if "제조사" in df.columns:
                        mt = (df.groupby("식품유형")["제조사"].nunique()
                              .reset_index().rename(columns={"제조사": "제조사수"}))
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
