"""
🔍 식품안전나라 품목제조보고 조회 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
품목유형별 최신 제품 조회 및 AI 현황 분석
API: 식품(첨가물)품목제조보고 (I1250)
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
import time
import json

# ━━━ 스타일 ━━━
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #f8f9fb; }
.big-num { font-size: 2.2rem; font-weight: 700; color: #1a2740; }
.sub-label { font-size: 0.85rem; color: #888; }
div[data-testid="stMetric"] { background: #f0f2f5; border-radius: 10px; padding: 12px; }
</style>
""", unsafe_allow_html=True)

# ━━━ session_state 초기화 ━━━
if "result_df"       not in st.session_state: st.session_state["result_df"]       = None
if "result_label"    not in st.session_state: st.session_state["result_label"]     = ""
if "result_total"    not in st.session_state: st.session_state["result_total"]     = 0
if "result_mode"     not in st.session_state: st.session_state["result_mode"]      = ""
if "status_msgs"     not in st.session_state: st.session_state["status_msgs"]      = {}
if "result_msg"      not in st.session_state: st.session_state["result_msg"]       = ""

# ━━━ API 설정 ━━━
API_KEY    = "9171f7ffd72f4ffcb62f"
SERVICE_ID = "I1250"
BASE_URL   = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/{SERVICE_ID}/json"

# ━━━ 품목유형 목록 ━━━
FOOD_TYPES = {
    "음료류": [
        "혼합음료", "탄산음료", "탄산수",
        "과.채주스", "과.채음료", "음료베이스",
        "침출차", "추출차", "액상차",
        "두유류", "유산균음료", "커피", "인삼.홍삼음료",
    ],
    "과자류":     ["과자", "캔디류", "추잉껌", "빙과", "아이스크림"],
    "빵·면류":    ["빵류", "떡류", "면류", "즉석섭취식품"],
    "조미·소스류": ["소스", "복합조미식품", "향신료가공품", "식초", "드레싱"],
    "유가공품":   ["치즈", "버터", "발효유", "우유류", "가공유"],
    "건강기능식품": ["건강기능식품"],
    "기타":       ["잼류", "식용유지", "김치류", "두부류", "즉석조리식품", "레토르트식품"],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  API 호출 (역순 페이지네이션 + 완전일치)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_data(ttl=600, show_spinner=False)
def fetch_food_data(food_type: str, top_n: int = 100, max_scan_pages: int = 100):
    """
    전체 DB를 max_scan_pages 페이지만큼 스캔 후 보고일자 정렬 → 최신 top_n건 반환.

    핵심 수정:
      - DB 인덱스 순서 ≠ 보고일자 순서임이 확인됨.
        1987~2026 데이터가 DB 끝부분에 뒤섞여 있어 역순 N건 수집으로는
        최신 신고 제품을 올바르게 포착할 수 없음.
      - 해결: target_count 달성 즉시 중단 제거 →
        max_scan_pages 페이지 전체 스캔 후 PRMS_DT 기준 정렬 → 상위 top_n 반환.
      - DB 끝(최근 등록분)부터 역순 스캔해 API 호출을 최소화.
    """
    collected  = []
    page_size  = 1000

    # 1단계: probe → total_count
    try:
        probe = requests.get(f"{BASE_URL}/1/1", timeout=30)
        probe.raise_for_status()
    except requests.exceptions.Timeout:
        return None, "API 응답 시간 초과 (30초)", 0, 0
    except requests.exceptions.ConnectionError:
        return None, "API 서버 연결 실패", 0, 0
    except Exception as e:
        return None, f"HTTP 오류: {str(e)}", 0, 0

    raw = probe.text.strip()
    if not raw:
        return None, f"API 빈 응답 (HTTP {probe.status_code}) — 서버 점검 중이거나 API 키 확인 필요", 0, 0
    try:
        probe_data = probe.json()
    except Exception:
        preview = raw[:300].replace("\n", " ")
        return None, f"JSON 파싱 실패 (HTTP {probe.status_code}) — 응답: {preview}", 0, 0

    if SERVICE_ID not in probe_data:
        result_info = probe_data.get("RESULT", probe_data)
        return None, f"API 오류 응답: {result_info}", 0, 0

    total_count = int(probe_data[SERVICE_ID].get("total_count", 0))
    if total_count == 0:
        return [], "전체 DB 레코드 0건", 0, 0

    # 2단계: DB 끝에서 역순으로 max_scan_pages 페이지 전체 스캔
    cursor     = total_count
    pages_done = 0

    while cursor > 0 and pages_done < max_scan_pages:
        p_start = max(1, cursor - page_size + 1)
        p_end   = cursor
        url     = f"{BASE_URL}/{p_start}/{p_end}"

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            return None, "API 응답 시간 초과 (30초)", 0, 0
        except requests.exceptions.ConnectionError:
            return None, "API 서버 연결 실패", 0, 0
        except Exception as e:
            return None, f"HTTP 오류: {str(e)}", 0, 0

        raw = resp.text.strip()
        if not raw:
            return None, f"API 빈 응답 (HTTP {resp.status_code}) — 서버 점검 중이거나 API 키 확인 필요", 0, 0
        try:
            data = resp.json()
        except Exception:
            preview = raw[:300].replace("\n", " ")
            return None, f"JSON 파싱 실패 (HTTP {resp.status_code}) — 응답: {preview}", 0, 0

        if SERVICE_ID not in data:
            result_info = data.get("RESULT", data)
            return None, f"API 오류 응답: {result_info}", 0, 0

        result = data[SERVICE_ID]
        code   = result.get("RESULT", {}).get("CODE", "")
        msg    = result.get("RESULT", {}).get("MSG", "")

        if code == "INFO-200":
            break
        if code != "INFO-000":
            return None, f"[{code}] {msg}", 0, 0

        rows = result.get("row", [])
        if rows:
            matched = [
                r for r in rows
                if r.get("PRDLST_DCNM", "").strip() == food_type.strip()
            ]
            collected.extend(matched)

        cursor     = p_start - 1
        pages_done += 1
        time.sleep(0.2)

    # 3단계: 보고일자 기준 정렬 → 최신 top_n 반환
    if collected:
        def sort_key(r):
            try:
                return r.get("PRMS_DT", "0") or "0"
            except Exception:
                return "0"
        collected.sort(key=sort_key, reverse=True)
        collected = collected[:top_n]

    scanned = min(pages_done * page_size, total_count)
    coverage = round(scanned / total_count * 100, 1) if total_count else 0
    msg = f"정상 — {pages_done}페이지({scanned:,}건) 스캔, DB 커버리지 {coverage}%"
    return collected, msg, total_count, pages_done


def fetch_multiple_types(types_list: list, per_type: int = 20, scan_pages: int = 100):
    all_rows    = []
    status_msgs = {}
    progress    = st.progress(0, text="조회 중...")

    for i, ft in enumerate(types_list):
        progress.progress((i + 1) / len(types_list), text=f"📡 {ft} 조회 중...")
        rows, msg, total, _ = fetch_food_data(ft, top_n=per_type, max_scan_pages=scan_pages)
        status_msgs[ft] = {"msg": msg, "total": total, "fetched": len(rows) if rows else 0}
        if rows:
            all_rows.extend(rows)
        time.sleep(0.3)

    progress.empty()
    return all_rows, status_msgs


def to_dataframe(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    col_map = {
        "PRDLST_NM":                "제품명",
        "PRDLST_DCNM":              "품목유형",
        "BSSH_NM":                  "제조사",
        "PRMS_DT":                  "보고일자",
        "RAWMTRL_NM":               "주요원재료",          # ✅ 신규 추가
        "POG_DAYCNT":               "유통기한",
        "PRODUCTION":               "생산종료",
        "INDUTY_CD_NM":             "업종",
        "USAGE":                    "용법",
        "PRPOS":                    "용도",
        "LCNS_NO":                  "인허가번호",
        "PRDLST_REPORT_NO":         "품목제조번호",
        "HIENG_LNTRT_DVS_NM":       "고열량저영양",
        "CHILD_CRTFC_YN":           "어린이기호식품인증",
        "LAST_UPDT_DTM":            "최종수정일",
        "DISPOS":                   "제품형태",
        "FRMLC_MTRQLT":             "포장재질",
        "QLITY_MNTNC_TMLMT_DAYCNT": "품질유지기한일수",
        "ETQTY_XPORT_PRDLST_YN":    "내수겸용",
    }

    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df     = df.rename(columns=rename)

    if "보고일자" in df.columns:
        df["보고일자"]    = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)

    return df


def apply_date_filter(df: pd.DataFrame, date_from, date_to) -> pd.DataFrame:
    """보고일자 기간 필터"""
    if "보고일자_dt" not in df.columns or df.empty:
        return df
    mask = pd.Series([True] * len(df), index=df.index)
    if date_from:
        mask &= df["보고일자_dt"] >= pd.Timestamp(date_from)
    if date_to:
        mask &= df["보고일자_dt"] <= pd.Timestamp(date_to)
    return df[mask].reset_index(drop=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GPT-4o-mini 현황 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def analyze_with_gpt(df: pd.DataFrame, openai_key: str) -> dict | None:
    sample = df[["제품명", "주요원재료"]].fillna("").head(150) \
             if "주요원재료" in df.columns \
             else df[["제품명"]].fillna("").head(150)

    lines = []
    for _, row in sample.iterrows():
        ingr = row.get("주요원재료", "") if "주요원재료" in row else ""
        lines.append(f"{row['제품명']} / {ingr}")
    product_text = "\n".join(lines)

    system_prompt = """당신은 식품 R&D 전문가입니다.
아래 제품 목록(제품명 / 주요원재료)을 분석하여 JSON만 반환하세요.
JSON 외 텍스트, 마크다운 코드블록 절대 금지.

반환 형식:
{"flavors":{"딸기":12,"복숭아":8},"concepts":{"제로슈거":15,"프리미엄":6}}

분류 기준:
- flavors: 주요 플레이버/과일/향 (딸기, 복숭아, 사과, 레몬, 오렌지, 포도, 망고, 파인애플,
  메론, 자몽, 블루베리, 라임, 녹차, 홍차, 커피, 콜라, 오리지널, 기타)
- concepts: 마케팅·기능 컨셉 (제로슈거, 저칼로리, 탄산, 프리미엄, 유기농, 기능성,
  비타민, 단백질, 발효, 식이섬유, 무첨가, 어린이, 기타)
각 항목 값은 제품 수(정수), 상위 10개만."""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            json={
                "model":       "gpt-4o-mini",
                "messages":    [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": f"{len(lines)}개 제품 분석:\n\n{product_text}"},
                ],
                "max_tokens":  600,
                "temperature": 0.2,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        st.error(f"GPT 분석 오류: {str(e)}")
        return None


def render_ai_tab(df: pd.DataFrame, label: str, openai_key: str):
    st.markdown(f"### 🤖 AI 현황 분석 — {label}")

    if not openai_key:
        st.info("👈 사이드바에서 OpenAI API Key를 입력하면 GPT-4o-mini 분석이 활성화됩니다.")
        return

    st.caption(f"분석 대상: {min(len(df), 150)}건 / GPT-4o-mini (약 5~15초 소요)")
    if not st.button("🔍 AI 분석 실행", key=f"ai_{label[:10]}", type="primary"):
        return

    with st.spinner("GPT-4o-mini 분석 중…"):
        result = analyze_with_gpt(df, openai_key)

    if result is None:
        return

    flavors  = result.get("flavors", {})
    concepts = result.get("concepts", {})

    col1, col2 = st.columns(2)

    with col1:
        if flavors:
            fl = pd.DataFrame(list(flavors.items()), columns=["플레이버", "제품수"]).sort_values("제품수", ascending=False)
            fig = px.bar(fl, x="제품수", y="플레이버", orientation="h",
                         title="🍓 플레이버별 제품 현황",
                         color="제품수", color_continuous_scale="Oranges")
            fig.update_layout(height=420, showlegend=False, yaxis=dict(autorange="reversed"))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if concepts:
            co = pd.DataFrame(list(concepts.items()), columns=["컨셉", "제품수"]).sort_values("제품수", ascending=False)
            fig2 = px.bar(co, x="제품수", y="컨셉", orientation="h",
                          title="💡 컨셉별 제품 현황",
                          color="제품수", color_continuous_scale="Blues")
            fig2.update_layout(height=420, showlegend=False, yaxis=dict(autorange="reversed"))
            fig2.update_coloraxes(showscale=False)
            st.plotly_chart(fig2, use_container_width=True)

    if flavors:
        fig3 = px.pie(values=list(flavors.values()), names=list(flavors.keys()),
                      title="플레이버 비중",
                      color_discrete_sequence=px.colors.qualitative.Pastel)
        fig3.update_layout(height=360)
        st.plotly_chart(fig3, use_container_width=True)

    st.caption(f"※ GPT-4o-mini가 {min(len(df),150)}건의 제품명·원재료를 분석한 추정 결과입니다.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  공통: 제품 목록 테이블 + 필터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_product_table(df: pd.DataFrame, show_type_filter: bool = False, key_prefix: str = ""):
    n_cols = 3 if show_type_filter else 2
    cols   = st.columns(n_cols)

    with cols[0]:
        search = st.text_input("🔎 제품명/원재료 검색", placeholder="검색어 입력...",
                               key=f"{key_prefix}_search")
    with cols[1]:
        makers    = ["전체"] + sorted(df["제조사"].dropna().unique().tolist()) \
                    if "제조사" in df.columns else ["전체"]
        sel_maker = st.selectbox("제조사 필터", makers, key=f"{key_prefix}_maker")

    sel_type = "전체"
    if show_type_filter and "품목유형" in df.columns:
        with cols[2]:
            type_opts = ["전체"] + sorted(df["품목유형"].dropna().unique().tolist())
            sel_type  = st.selectbox("품목유형 필터", type_opts, key=f"{key_prefix}_type")

    filtered = df.copy()
    if search:
        mask     = filtered.apply(lambda r: search.lower() in str(r).lower(), axis=1)
        filtered = filtered[mask]
    if sel_maker != "전체" and "제조사" in filtered.columns:
        filtered = filtered[filtered["제조사"] == sel_maker]
    if sel_type != "전체" and "품목유형" in filtered.columns:
        filtered = filtered[filtered["품목유형"] == sel_type]

    show_cols = ["제품명", "품목유형", "제조사", "보고일자", "주요원재료", "유통기한", "생산종료"]
    show_cols = [c for c in show_cols if c in filtered.columns]
    st.dataframe(filtered[show_cols].reset_index(drop=True),
                 use_container_width=True, height=500)
    st.caption(f"총 {len(filtered)}건 표시 중")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  사이드바
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.markdown("## 🔍 조회 설정")
    st.markdown("---")

    mode = st.radio(
        "조회 방식",
        ["📋 단일 유형 조회", "📊 복수 유형 비교"],
        help="단일: 한 유형 상세 / 복수: 여러 유형 동시 비교",
    )
    st.markdown("---")

    if mode == "📋 단일 유형 조회":
        category     = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
        category_all = st.checkbox(
            "카테고리 전체 조회", value=False,
            help="선택 카테고리 전체 품목유형 합산 조회",
        )
        if not category_all:
            food_type   = st.selectbox("품목유형", FOOD_TYPES[category])
            custom_type = st.text_input(
                "또는 직접 입력", placeholder="예: 혼합음료, 잼류...",
                help="API PRDLST_DCNM 값과 완전일치 명칭 입력",
            )
            if custom_type.strip():
                food_type = custom_type.strip()
            count = st.slider("출력 건수 (최신순)", 10, 500, 100, step=10)
        else:
            food_type = None
            st.info(f"**{category}** 내 {len(FOOD_TYPES[category])}개 품목유형 전체 조회")
            count = st.slider("품목유형별 출력 건수", 10, 100, 20, step=5)
    else:
        st.markdown("**비교할 유형 선택:**")
        selected_types = []
        for cat, types in FOOD_TYPES.items():
            with st.expander(cat, expanded=(cat == "음료류")):
                for t in types:
                    if st.checkbox(t, value=(t in ["혼합음료", "과.채음료"]), key=f"cb_{t}"):
                        selected_types.append(t)
        per_type = st.slider("유형별 출력 건수", 10, 100, 20, step=5)

    st.markdown("---")
    st.markdown("#### 🔭 스캔 범위 설정")
    max_scan_pages = st.slider(
        "스캔 페이지 수",
        min_value=10, max_value=300, value=100, step=10,
        help="1페이지 = DB 1,000건 스캔. 클수록 최신 데이터 정확도↑, API 호출↑\n"
             "권장: 혼합음료·탄산음료 등 대형 카테고리 → 200 이상\n"
             "소형 카테고리(탄산수, 액상차 등) → 50~100"
    )
    st.caption(f"스캔 범위: DB 최근 {max_scan_pages*1000:,}건 / API {max_scan_pages+1}회 사용")

    st.markdown("---")

    # ✅ 보고일자 기간 필터
    st.markdown("#### 📅 보고일자 기간 필터")
    use_date_filter = st.checkbox("기간 필터 사용", value=False)
    if use_date_filter:
        date_from = st.date_input("시작일", value=date.today() - timedelta(days=365), key="date_from")
        date_to   = st.date_input("종료일", value=date.today(), key="date_to")
    else:
        date_from = None
        date_to   = None

    st.markdown("---")

    # ✅ OpenAI API 키
    st.markdown("#### 🤖 AI 현황분석 설정")
    openai_key = st.text_input(
        "OpenAI API Key", type="password", placeholder="sk-...",
        help="GPT-4o-mini 플레이버/컨셉 분석에 사용",
    )

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")
    st.markdown("---")
    st.caption("📡 데이터: 식품안전나라 I1250 API")
    st.caption(f"🔑 키: {API_KEY[:8]}...")
    st.caption("⚠️ 일일 API 호출 2,000회 제한")
    st.caption("✅ 필터: PRDLST_DCNM 완전일치 (역순 페이지네이션)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("품목유형별 최신 품목제조보고 데이터를 실시간으로 조회합니다.")
st.markdown("---")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  조회 실행 → session_state에 결과 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if run:
    if mode == "📋 단일 유형 조회":

        if category_all:
            types_in_cat                      = FOOD_TYPES[category]
            all_rows, s_msgs                  = fetch_multiple_types(types_in_cat, count, scan_pages=max_scan_pages)
            st.session_state["status_msgs"]   = s_msgs
            if all_rows:
                df = to_dataframe(all_rows)
                if use_date_filter:
                    df = apply_date_filter(df, date_from, date_to)
                st.session_state["result_df"]    = df
                st.session_state["result_label"] = category
                st.session_state["result_total"] = 0
                st.session_state["result_mode"]  = "category_all"
                st.session_state["result_msg"]   = f"카테고리 전체 조회 완료 → {len(df)}건"
            else:
                st.session_state["result_df"] = pd.DataFrame()

        else:
            with st.spinner(f"📡 '{food_type}' 조회 중…"):
                rows, msg, total, _ = fetch_food_data(food_type, top_n=count, max_scan_pages=max_scan_pages)
            if rows is None:
                st.session_state["result_df"]    = None
                st.session_state["result_msg"]   = f"❌ 조회 실패: {msg}"
                st.session_state["result_mode"]  = "error"
            elif len(rows) == 0:
                st.session_state["result_df"]    = pd.DataFrame()
                st.session_state["result_msg"]   = f"⚠️ '{food_type}'에 해당하는 데이터가 없습니다."
                st.session_state["result_mode"]  = "empty"
            else:
                df = to_dataframe(rows)
                if use_date_filter:
                    df = apply_date_filter(df, date_from, date_to)
                st.session_state["result_df"]    = df
                st.session_state["result_label"] = food_type
                st.session_state["result_total"] = total
                st.session_state["result_mode"]  = "single"
                st.session_state["result_msg"]   = f"✅ {msg} | 출력: {len(df)}건"

    else:  # 복수 유형 비교
        if not selected_types:
            st.warning("⚠️ 비교할 품목유형을 1개 이상 선택하세요.")
        else:
            all_rows, s_msgs                  = fetch_multiple_types(selected_types, per_type, scan_pages=max_scan_pages)
            st.session_state["status_msgs"]   = s_msgs
            if all_rows:
                df = to_dataframe(all_rows)
                if use_date_filter:
                    df = apply_date_filter(df, date_from, date_to)
                st.session_state["result_df"]    = df
                st.session_state["result_label"] = ", ".join(selected_types[:3]) + ("..." if len(selected_types) > 3 else "")
                st.session_state["result_total"] = 0
                st.session_state["result_mode"]  = "multi"
                st.session_state["result_msg"]   = f"복수 유형 조회 완료 → {len(df)}건"
            else:
                st.session_state["result_df"] = pd.DataFrame()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  결과 렌더링 (session_state 기반 — rerun에 영향 없음)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
df         = st.session_state.get("result_df")
res_mode   = st.session_state.get("result_mode", "")
res_label  = st.session_state.get("result_label", "")
res_total  = st.session_state.get("result_total", 0)
res_msg    = st.session_state.get("result_msg", "")
s_msgs     = st.session_state.get("status_msgs", {})

if res_mode == "error":
    st.error(res_msg)

elif res_mode == "empty":
    st.warning(res_msg)

elif df is None:
    # 초기 상태
    st.info("👈 왼쪽 사이드바에서 품목유형을 선택하고 **[조회 실행]** 버튼을 누르세요.")
    st.markdown("""
### 신규 기능 안내

| 기능 | 설명 |
|---|---|
| **주요원재료** | 제품 목록에 원재료 컬럼 추가 (API `RAWMTRL_NM`) |
| **제조사 필터** | 모든 조회 모드의 제품 목록 탭에 제조사 드롭다운 필터 적용 |
| **보고일자 기간 필터** | 사이드바에서 시작일~종료일 설정 후 조회 결과에 적용 |
| **🤖 AI 현황분석 탭** | GPT-4o-mini로 플레이버·컨셉 자동 분류 → 바차트·파이차트 출력 |

### API 정보

| 항목 | 내용 |
|---|---|
| 서비스ID | I1250 (식품(첨가물)품목제조보고) |
| 호출제한 | 1회 최대 1,000건 / 일 2,000회 |
""")

elif df.empty:
    st.warning("⚠️ 조회된 데이터가 없습니다.")

else:
    st.success(res_msg)

    # ── 카테고리 전체 조회 결과 요약 메트릭 ──
    if res_mode == "category_all" and s_msgs:
        types_in_cat = list(s_msgs.keys())
        scols = st.columns(min(len(types_in_cat), 5))
        for i, ft in enumerate(types_in_cat):
            info = s_msgs.get(ft, {"msg": "", "fetched": 0, "total": 0})
            with scols[i % len(scols)]:
                if "정상" in info.get("msg", ""):
                    st.metric(ft, f"{info['fetched']}건", f"전체 {info['total']:,}건")
                else:
                    st.metric(ft, "❌", info.get("msg", "")[:20])
        st.markdown("---")

    # ── 복수 유형 결과 요약 메트릭 ──
    elif res_mode == "multi" and s_msgs:
        scols = st.columns(min(len(s_msgs), 5))
        for i, (ft, info) in enumerate(s_msgs.items()):
            with scols[i % len(scols)]:
                if "정상" in info.get("msg", ""):
                    st.metric(ft, f"{info['fetched']}건", f"전체 {info['total']:,}건")
                else:
                    st.metric(ft, "❌", info.get("msg", ""))
        st.markdown("---")

    # ── 공통 상단 메트릭 ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("조회 결과", f"{len(df)}건")
    if res_mode == "single":
        c2.metric("전체 DB 레코드", f"{res_total:,}건")
        c3.metric("품목유형", res_label)
    else:
        c2.metric("카테고리/유형", res_label)
        c3.metric("품목유형 수", f"{df['품목유형'].nunique()}개")
    if "제조사" in df.columns:
        c4.metric("제조사 수", f"{df['제조사'].nunique()}개")
    st.markdown("---")

    # ── 탭 구성 ──
    show_type_filter = (res_mode != "single")
    tab_labels = ["📋 제품 목록", "📊 분석 차트", "🤖 AI 현황분석", "📥 원시 데이터"]
    tab1, tab2, tab3, tab4 = st.tabs(tab_labels)

    # ── 탭1: 제품 목록 ──
    with tab1:
        st.markdown(f"### 📋 {res_label} 품목제조보고 ({len(df)}건)")
        render_product_table(df, show_type_filter=show_type_filter, key_prefix="result")

    # ── 탭2: 분석 차트 ──
    with tab2:
        st.markdown(f"### 📊 {res_label} 데이터 분석")

        if res_mode != "single" and "품목유형" in df.columns:
            ch1, ch2 = st.columns(2)
            with ch1:
                tc  = df["품목유형"].value_counts()
                fig = px.bar(x=tc.index, y=tc.values, title="품목유형별 조회 건수",
                             labels={"x": "품목유형", "y": "건수"}, color=tc.index)
                fig.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with ch2:
                if "제조사" in df.columns:
                    mt = df.groupby("품목유형")["제조사"].nunique().reset_index()
                    mt.columns = ["품목유형", "제조사수"]
                    fig2 = px.bar(mt, x="품목유형", y="제조사수",
                                  title="품목유형별 제조사 다양성", color="품목유형")
                    fig2.update_layout(height=400, showlegend=False)
                    st.plotly_chart(fig2, use_container_width=True)

        ch1, ch2 = st.columns(2)
        if "제조사" in df.columns:
            with ch1:
                mc   = df["제조사"].value_counts().head(15)
                fig1 = px.bar(x=mc.values, y=mc.index, orientation="h",
                              title="제조사별 제품 수 (상위 15)",
                              labels={"x": "제품 수", "y": "제조사"},
                              color=mc.values, color_continuous_scale="Blues")
                fig1.update_layout(height=450, showlegend=False, yaxis=dict(autorange="reversed"))
                fig1.update_coloraxes(showscale=False)
                st.plotly_chart(fig1, use_container_width=True)

        if "보고일자_dt" in df.columns:
            with ch2:
                df_dt = df.dropna(subset=["보고일자_dt"]).copy()
                if not df_dt.empty:
                    df_dt["연월"] = df_dt["보고일자_dt"].dt.to_period("M").astype(str)
                    monthly       = df_dt["연월"].value_counts().sort_index().tail(24)
                    fig2 = px.line(x=monthly.index, y=monthly.values,
                                   title="월별 보고 건수 추이 (최근 24개월)",
                                   labels={"x": "연월", "y": "건수"}, markers=True)
                    fig2.update_layout(height=450)
                    st.plotly_chart(fig2, use_container_width=True)

        if "생산종료" in df.columns:
            pc   = df["생산종료"].value_counts()
            fig3 = px.pie(values=pc.values, names=pc.index, title="생산종료 현황",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig3.update_layout(height=350)
            st.plotly_chart(fig3, use_container_width=True)

    # ── 탭3: AI 현황분석 ──
    with tab3:
        render_ai_tab(df, res_label, openai_key)

    # ── 탭4: 원시 데이터 ──
    with tab4:
        st.dataframe(df, use_container_width=True, height=500)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        fname = f"{res_label}_품목제조보고_{datetime.now().strftime('%Y%m%d')}.csv"
        st.download_button("📥 CSV 다운로드", csv, fname, "text/csv", use_container_width=True)
    st.markdown("""
### 신규 기능 안내

| 기능 | 설명 |
|---|---|
| **주요원재료** | 제품 목록에 원재료 컬럼 추가 (API `RAWMTRL_NM`) |
| **제조사 필터** | 모든 조회 모드의 제품 목록 탭에 제조사 드롭다운 필터 적용 |
| **보고일자 기간 필터** | 사이드바에서 시작일~종료일 설정 후 조회 결과에 적용 |
| **🤖 AI 현황분석 탭** | GPT-4o-mini로 플레이버·컨셉 자동 분류 → 바차트·파이차트 출력 |

### API 정보

| 항목 | 내용 |
|---|---|
| 서비스ID | I1250 (식품(첨가물)품목제조보고) |
| 호출제한 | 1회 최대 1,000건 / 일 2,000회 |
""")
