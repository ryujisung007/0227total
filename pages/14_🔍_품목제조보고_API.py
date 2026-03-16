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

import json

GENAI_AVAILABLE = True  # REST API 직접 호출 — SDK 불필요


# ══════════════════════════════════════════════════════
#  설정 — Lazy loading (앱 시작 후 secrets 접근)
# ══════════════════════════════════════════════════════
def _secret(*keys, default=""):
    """st.secrets를 lazy하게 읽음 (모듈 최상단에서 호출 금지)"""
    try:
        for k in keys:
            v = st.secrets.get(k, "")
            if v:
                return v
    except Exception:
        pass
    return default

def get_food_api_key():
    return _secret("FOOD_SAFETY_API_KEY", default="9171f7ffd72f4ffcb62f")

def get_gemini_key():
    return _secret("GOOGLE_API_KEY", "GEMINI_API_KEY", "google_api_key",
                   "GEMINI_KEY", "gemini_api_key")

SERVICE_ID = "I1250"

def get_base_url():
    return f"http://openapi.foodsafetykorea.go.kr/api/{get_food_api_key()}/{SERVICE_ID}/json"

GEMINI_MODELS = ["gemini-2.0-flash-001"]  # REST API 정식 모델명

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
    "PRMS_DT": "보고일자", "RAWMTRL_NM": "주요원재료",
    "POG_DAYCNT": "유통기한", "PRODUCTION": "생산종료",
    "INDUTY_CD_NM": "업종", "LCNS_NO": "인허가번호",
    "PRDLST_REPORT_NO": "품목제조번호", "LAST_UPDT_DTM": "최종수정일",
    "HIENG_LNTRT_DVS_NM": "고열량저영양", "CHILD_CRTFC_YN": "어린이기호식품인증",
    "DISPOS": "제품형태", "FRMLC_MTRQLT": "포장재질",
}


# ══════════════════════════════════════════════════════
#  조회 — 페이지 단위 캐시 + 진행 표시 + normalize 비교
# ══════════════════════════════════════════════════════
def _norm(s: str) -> str:
    """DB 표기 정규화: 가운뎃점↔마침표, 공백 제거, 소문자"""
    return s.strip().replace("·", ".").replace(" ", "").lower()


def _safe_get(url: str):
    """GET 요청 → (dict | None, error_msg | None)"""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        return None, "응답 시간 초과 (30초)"
    except requests.exceptions.ConnectionError:
        return None, "서버 연결 실패"
    except Exception as e:
        return None, f"HTTP 오류: {e}"
    raw = r.text.strip()
    if not raw:
        return None, f"빈 응답 (HTTP {r.status_code})"
    try:
        return r.json(), None
    except Exception:
        return None, f"JSON 파싱 실패: {raw[:200]}"


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_page(base_url: str, p_s: int, p_e: int):
    """페이지 단위 캐시 — 같은 페이지 재요청 시 즉시 반환"""
    return _safe_get(f"{base_url}/{p_s}/{p_e}")


def fetch_food_data(food_type: str, top_n: int = 100, max_pages: int = 100,
                    prog_bar=None, status_text=None):
    """
    역순 스캔 + 진행 표시.
    - @st.cache_data 제거 → st.progress 사용 가능
    - 페이지 단위 캐시(_fetch_page)로 재실행 시 빠름
    - _norm()으로 가운뎃점/마침표 혼용 문제 해결
    반환: (rows | None, msg, total, pages_done)
    """
    base_url = get_base_url()
    t_start  = time.time()

    # total_count 파악
    data, err = _safe_get(f"{base_url}/1/1")
    if err:
        return None, err, 0, 0
    if SERVICE_ID not in data:
        return None, f"API 오류: {data}", 0, 0

    total = int(data[SERVICE_ID].get("total_count", 0))
    if total == 0:
        return [], "DB 레코드 0건", 0, 0

    collected  = []
    cursor     = total
    pages_done = 0
    page_size  = 1000
    norm_type  = _norm(food_type)

    while cursor > 0 and pages_done < max_pages:
        p_s = max(1, cursor - page_size + 1)
        p_e = cursor

        # 진행 표시 업데이트
        elapsed = time.time() - t_start
        pct     = min(pages_done / max(max_pages, 1), 0.99)
        if prog_bar:
            prog_bar.progress(pct)
        if status_text:
            status_text.markdown(
                f"📡 스캔 중… **{pages_done}페이지** / "
                f"수집 **{len(collected)}건** / "
                f"경과 **{elapsed:.0f}초**"
            )

        d, err = _fetch_page(base_url, p_s, p_e)
        if err:
            return None, err, total, pages_done

        if SERVICE_ID not in d:
            return None, f"API 오류: {d}", total, pages_done

        res  = d[SERVICE_ID]
        code = res.get("RESULT", {}).get("CODE", "")
        msg  = res.get("RESULT", {}).get("MSG", "")

        if code == "INFO-200":
            break
        if code != "INFO-000":
            return None, f"[{code}] {msg}", total, pages_done

        # ③ normalize 비교로 가운뎃점/마침표 혼용 해결
        for row in res.get("row", []):
            if _norm(row.get("PRDLST_DCNM", "")) == norm_type:
                collected.append(row)
                if len(collected) >= top_n:
                    break

        if len(collected) >= top_n:
            break

        cursor     = p_s - 1
        pages_done += 1
        time.sleep(0.2)

    if collected:
        collected.sort(key=lambda r: r.get("PRMS_DT", "0") or "0", reverse=True)

    scanned  = min((pages_done + 1) * page_size, total)
    coverage = round(scanned / total * 100, 1) if total else 0
    elapsed  = time.time() - t_start
    src_msg  = (f"{pages_done+1}페이지({scanned:,}건 스캔) / "
                f"커버리지 {coverage}% / {elapsed:.1f}초")
    return collected[:top_n], src_msg, total, pages_done + 1


def fetch_multiple(types_list: list, per_type: int, max_pages: int):
    """복수 유형 순차 조회"""
    all_rows, status = [], {}
    prog        = st.progress(0.0)
    status_text = st.empty()
    for i, ft in enumerate(types_list):
        pct = (i + 1) / len(types_list)
        prog.progress(pct)
        status_text.markdown(f"📡 **{ft}** 조회 중… ({i+1}/{len(types_list)})")
        rows, msg, total, _ = fetch_food_data(ft, top_n=per_type, max_pages=max_pages)
        status[ft] = {
            "msg":     msg or "",
            "total":   total,
            "fetched": len(rows) if rows else 0,
        }
        if rows:
            all_rows.extend(rows)
        time.sleep(0.2)
    prog.empty()
    status_text.empty()
    return all_rows, status


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
def _gemini(prompt: str, api_key: str) -> str:
    """
    Gemini REST API 직접 호출.
    사용자 작동 코드와 동일한 방식 — gemini-2.0-flash / v1beta
    캐시 없음: 캐시된 오류가 계속 반환되는 문제 방지
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
        f"/gemini-2.0-flash:generateContent?key={api_key}"
    )
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


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


def render_ai_section(df: pd.DataFrame, food_type: str, api_key: str):
    st.markdown("---")
    st.markdown("## 🤖 AI 연구원 분석")

    if not api_key:
        st.warning(
            "**Gemini API 키 없음**\n\n"
            "`.streamlit/secrets.toml`:\n"
            "```toml\nGOOGLE_API_KEY = \"AIza...\"\n```"
        )
        return

    st.info(f"모델: **gemini-2.0-flash** | 대상: **{food_type}** {len(df)}건")

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
            text = _gemini(item["prompt"], api_key)
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
    st.markdown("#### 🔭 스캔 범위")
    max_pages = st.slider(
        "스캔 페이지 수", 10, 200, 50, step=10,
        help="1페이지 = DB 1,000건 / 혼합음료 등 대형 유형은 100 이상 권장",
    )
    st.caption(f"최대 DB {max_pages*1000:,}건 스캔")

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### 🤖 Gemini 설정")
    if get_gemini_key():
        st.success("API 키 연결됨", icon="✅")
    else:
        st.warning("GOOGLE_API_KEY 없음", icon="⚠️")
        st.caption("secrets.toml: GOOGLE_API_KEY = \"AIza...\"")
    gemini_model = get_gemini_key()   # api_key 전달용
    st.caption("모델: 자동 감지 (gemini-2.0-flash 계열)")

    st.markdown("---")
    if st.button("🔄 캐시 초기화", use_container_width=True):
        st.cache_data.clear()
        st.success("완료")
    st.caption("📡 식품안전나라 I1250")
    st.caption("⚠️ 일일 2,000회 호출 제한")


# ══════════════════════════════════════════════════════
#  session_state 초기화
# ══════════════════════════════════════════════════════
for _k, _v in {
    "result_df":    None,   # 조회 결과 DataFrame
    "result_label": "",     # 식품유형명
    "result_total": 0,      # 전체 DB 건수
    "result_src":   "",     # 조회 방식 메시지
    "result_mode":  "",     # single / multi
    "status_msgs":  {},     # 복수 유형 상태
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("---")

# ── 조회 실행 (run 버튼 눌렸을 때만 API 호출) ──
if run:
    if mode == "📋 단일 유형 조회":
        t0          = time.time()
        prog_bar    = st.progress(0.0)
        status_text = st.empty()

        rows, src, total, _ = fetch_food_data(
            food_type, top_n=count, max_pages=max_pages,
            prog_bar=prog_bar, status_text=status_text,
        )
        elapsed = time.time() - t0
        prog_bar.empty()
        status_text.empty()

        if rows is None:
            st.error(f"❌ 조회 실패: {src}")
        else:
            df = to_df(rows)
            st.session_state.update({
                "result_df":    df,
                "result_label": food_type,
                "result_total": total,
                "result_src":   f"✅ **{len(df)}건** | {elapsed:.1f}초 | {src} | 전체: {total:,}건",
                "result_mode":  "single",
                "status_msgs":  {},
            })

    else:  # 복수 유형
        if not selected_types:
            st.warning("⚠️ 유형을 1개 이상 선택하세요.")
        else:
            t0 = time.time()
            all_rows, status = fetch_multiple(selected_types, per_type, max_pages)
            elapsed = time.time() - t0
            df = to_df(all_rows)
            label = ", ".join(selected_types[:3]) + ("…" if len(selected_types) > 3 else "")
            st.session_state.update({
                "result_df":    df,
                "result_label": label,
                "result_total": 0,
                "result_src":   f"✅ {len(selected_types)}개 유형 완료 | {elapsed:.1f}초 | {len(df)}건",
                "result_mode":  "multi",
                "status_msgs":  status,
            })

# ── 결과 렌더링 (session_state 기반 → 버튼 눌러도 유지) ──
df     = st.session_state["result_df"]
r_mode = st.session_state["result_mode"]
r_lbl  = st.session_state["result_label"]
r_tot  = st.session_state["result_total"]
r_src  = st.session_state["result_src"]
smsgs  = st.session_state["status_msgs"]

if df is None:
    st.info("👈 사이드바에서 식품유형을 선택하고 **[조회 실행]**을 누르세요.")

elif df.empty:
    st.warning(f"⚠️ **'{r_lbl}'** 결과 없음 — 스캔 범위를 늘리거나 유형명을 확인하세요.")

else:
    st.success(r_src)

    # 복수 유형 요약 메트릭
    if smsgs:
        cols = st.columns(min(len(smsgs), 6))
        for i, (ft, info) in enumerate(smsgs.items()):
            with cols[i % len(cols)]:
                st.metric(ft, f"{info['fetched']}건", f"전체 {info['total']:,}건")
        st.markdown("---")

    # 상단 메트릭
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("조회 결과", f"{len(df)}건")
    if r_mode == "single":
        m2.metric("전체 DB",   f"{r_tot:,}건")
        m3.metric("식품유형",   r_lbl)
    else:
        m2.metric("유형 수",    f"{df['식품유형'].nunique()}개" if "식품유형" in df.columns else "-")
        m3.metric("카테고리",   r_lbl)
    if "제조사" in df.columns:
        m4.metric("제조사 수",  f"{df['제조사'].nunique()}개")

    st.markdown("---")

    # ── 탭 ──
    tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

    with tab1:
        ca, cb = st.columns(2)
        with ca:
            kw = st.text_input("🔎 검색", placeholder="제품명·제조사·원재료", key="kw_input")
        with cb:
            makers = (["전체"] + sorted(df["제조사"].dropna().unique().tolist())
                      if "제조사" in df.columns else ["전체"])
            sel_mk = st.selectbox("제조사 필터", makers, key="maker_sel")

        fdf = df.copy()
        if kw:
            fdf = fdf[fdf.apply(lambda r: kw.lower() in str(r).lower(), axis=1)]
        if "제조사" in df.columns and sel_mk != "전체":
            fdf = fdf[fdf["제조사"] == sel_mk]

        sc = [c for c in ["제품명", "식품유형", "제조사", "보고일자",
                           "주요원재료", "유통기한", "생산종료"]
              if c in fdf.columns]
        st.dataframe(fdf[sc].reset_index(drop=True),
                     use_container_width=True, height=480)
        st.caption(f"총 {len(fdf)}건 표시")

    with tab2:
        render_charts(df, r_lbl)

    with tab3:
        st.dataframe(df, use_container_width=True, height=480)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 CSV 다운로드", csv,
            f"{r_lbl}_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv", use_container_width=True,
        )

    # ── AI 분석 (탭 밖 → session_state df 사용) ──
    render_ai_section(df, r_lbl, gemini_model)
