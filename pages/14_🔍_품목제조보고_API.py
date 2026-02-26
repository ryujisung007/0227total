"""
🔍 식품안전나라 품목제조보고 조회 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
식품유형별 최신 제품 100건 조회 및 분석
API: 식품(첨가물)품목제조보고 (I1250)
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
# urllib 불필요 — API에 한글 직접 전달

# ━━━ 페이지 설정 ━━━
# set_page_config is in main app.py

# ━━━ 스타일 ━━━
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #f8f9fb; }
.big-num { font-size: 2.2rem; font-weight: 700; color: #1a2740; }
.sub-label { font-size: 0.85rem; color: #888; }
div[data-testid="stMetric"] { background: #f0f2f5; border-radius: 10px; padding: 12px; }
</style>
""", unsafe_allow_html=True)

# ━━━ API 설정 ━━━
API_KEY = "9171f7ffd72f4ffcb62f"
SERVICE_ID = "I1250"
BASE_URL = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/{SERVICE_ID}/json"

# ━━━ 식품유형 목록 ━━━
FOOD_TYPES = {
    "음료류": ["혼합음료", "과채음료", "과채주스", "탄산음료", "두유류", "유산균음료", "커피", "인삼·홍삼음료"],
    "과자류": ["과자", "캔디류", "추잉껌", "빙과", "아이스크림"],
    "빵·면류": ["빵류", "떡류", "면류", "즉석섭취식품"],
    "조미·소스류": ["소스", "복합조미식품", "향신료가공품", "식초", "드레싱"],
    "유가공품": ["치즈", "버터", "발효유", "우유류", "가공유"],
    "건강기능식품": ["건강기능식품"],
    "기타": ["잼류", "식용유지", "김치류", "두부류", "즉석조리식품", "레토르트식품"],
}

# ━━━ API 호출 함수 ━━━
@st.cache_data(ttl=600, show_spinner=False)
def fetch_food_data(food_type, start=1, end=100):
    """식품안전나라 I1250 API 호출 (서버사이드 필터링)"""

    # 방법 1: 서버사이드 필터링 시도 (PRDLST_DCNM 파라미터)
    url_filtered = f"{BASE_URL}/{start}/{end}/PRDLST_DCNM={food_type}"

    # 방법 2: 전체 조회 후 클라이언트 필터링 (fallback)
    url_all = f"{BASE_URL}/{start}/{end}"

    for attempt, (url, is_filtered) in enumerate([
        (url_filtered, True),
        (url_all, False),
    ]):
        try:
            # requests에 한글 인코딩 맡기지 않고 직접 바이트로 전송
            if is_filtered:
                response = requests.get(
                    url,
                    timeout=30,
                    headers={"Accept": "application/json"}
                )
            else:
                response = requests.get(url, timeout=30)

            response.raise_for_status()
            data = response.json()

            if SERVICE_ID not in data:
                if is_filtered:
                    continue  # fallback으로 재시도
                return None, "API 응답에 데이터가 없습니다.", 0

            result = data[SERVICE_ID]
            code = result.get("RESULT", {}).get("CODE", "")
            msg = result.get("RESULT", {}).get("MSG", "")

            if code == "ERROR-500" and is_filtered:
                continue  # 서버사이드 필터링 실패 → fallback

            if code == "INFO-200":
                if is_filtered:
                    continue  # 데이터 없으면 fallback 시도
                return [], "해당 식품유형의 데이터가 없습니다.", 0
            elif code != "INFO-000":
                if is_filtered:
                    continue
                return None, f"[{code}] {msg}", 0

            total = int(result.get("total_count", 0))
            rows = result.get("row", [])

            # fallback인 경우 클라이언트측 필터링
            if not is_filtered and rows:
                filtered = [r for r in rows if r.get("PRDLST_DCNM", "")
                           and food_type in r.get("PRDLST_DCNM", "")]
                return filtered, "정상 (클라이언트 필터링)", total
            else:
                return rows, "정상", total

        except requests.exceptions.Timeout:
            if is_filtered:
                continue
            return None, "API 응답 시간 초과 (30초)", 0
        except requests.exceptions.ConnectionError:
            return None, "API 서버 연결 실패", 0
        except Exception as e:
            if is_filtered:
                continue
            return None, f"오류: {str(e)}", 0

    return None, "모든 조회 방법 실패", 0

def fetch_multiple_types(types_list, per_type=20):
    """여러 식품유형을 한번에 조회"""
    all_rows = []
    progress = st.progress(0, text="조회 중...")
    status_msgs = {}

    for i, ft in enumerate(types_list):
        progress.progress((i + 1) / len(types_list), text=f"📡 {ft} 조회 중...")
        # fallback 대비 넉넉하게 요청 (서버필터링 실패 시 클라이언트 필터링)
        rows, msg, total = fetch_food_data(ft, 1, min(per_type * 5, 1000))
        if rows:
            rows = rows[:per_type]  # 요청 건수만큼만
        status_msgs[ft] = {"msg": msg, "total": total, "fetched": len(rows) if rows else 0}
        if rows:
            all_rows.extend(rows)
        time.sleep(0.5)  # API 부하 방지

    progress.empty()
    return all_rows, status_msgs

def to_dataframe(rows):
    """API 응답을 DataFrame으로 변환"""
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    col_map = {
        "PRDLST_NM": "제품명",
        "PRDLST_DCNM": "식품유형",
        "BSSH_NM": "제조사",
        "PRMS_DT": "보고일자",
        "POG_DAYCNT": "유통기한",
        "PRODUCTION": "생산종료",
        "INDUTY_CD_NM": "업종",
        "USAGE": "용법",
        "PRPOS": "용도",
        "LCNS_NO": "인허가번호",
        "PRDLST_REPORT_NO": "품목제조번호",
        "HIENG_LNTRT_DVS_NM": "고열량저영양",
        "CHILD_CRTFC_YN": "어린이기호식품인증",
        "LAST_UPDT_DTM": "최종수정일",
        "DISPOS": "제품형태",
        "FRMLC_MTRQLT": "포장재질",
        "QLITY_MNTNC_TMLMT_DAYCNT": "품질유지기한일수",
        "ETQTY_XPORT_PRDLST_YN": "내수겸용",
    }

    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)

    # 보고일자 정리
    if "보고일자" in df.columns:
        df["보고일자"] = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)

    return df

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  사이드바
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.markdown("## 🔍 조회 설정")
    st.markdown("---")

    # 조회 모드
    mode = st.radio(
        "조회 방식",
        ["📋 단일 유형 조회", "📊 복수 유형 비교"],
        help="단일: 한 유형 100건 상세 / 복수: 여러 유형 동시 비교"
    )

    st.markdown("---")

    if mode == "📋 단일 유형 조회":
        # 카테고리 → 유형 선택
        category = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
        food_type = st.selectbox("식품유형", FOOD_TYPES[category])

        # 직접 입력도 가능
        custom_type = st.text_input(
            "또는 직접 입력",
            placeholder="예: 혼합음료, 초콜릿, 잼류...",
            help="API의 PRDLST_DCNM 파라미터로 전달됩니다"
        )
        if custom_type.strip():
            food_type = custom_type.strip()

        count = st.slider("조회 건수", 10, 200, 100, step=10)

    else:
        st.markdown("**비교할 유형 선택:**")
        selected_types = []
        for cat, types in FOOD_TYPES.items():
            with st.expander(cat, expanded=(cat == "음료류")):
                for t in types:
                    if st.checkbox(t, value=(t in ["혼합음료", "과채음료"]), key=f"cb_{t}"):
                        selected_types.append(t)

        per_type = st.slider("유형별 조회 건수", 10, 50, 20, step=5)

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")

    st.markdown("---")
    st.caption("📡 데이터: 식품안전나라 I1250 API")
    st.caption(f"🔑 키: {API_KEY[:8]}...")
    st.caption("⚠️ 일일 API 호출 2,000회 제한")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("식품유형별 최신 품목제조보고 데이터를 실시간으로 조회합니다.")
st.markdown("---")

if run:
    # ━━━ 단일 유형 조회 ━━━
    if mode == "📋 단일 유형 조회":
        with st.spinner(f"📡 '{food_type}' 데이터 조회 중..."):
            # fallback(클라이언트 필터링) 대비 넉넉하게 요청
            request_count = min(count * 5, 1000)
            rows, msg, total = fetch_food_data(food_type, 1, request_count)
            if rows and len(rows) > count:
                rows = rows[:count]

        if rows is None:
            st.error(f"❌ 조회 실패: {msg}")
        elif len(rows) == 0:
            st.warning(f"⚠️ '{food_type}'에 해당하는 데이터가 없습니다.")
        else:
            if "클라이언트" in msg:
                st.info(f"ℹ️ 서버 필터링 불가 → 전체 데이터에서 '{food_type}' 추출 ({len(rows)}건)")
            df = to_dataframe(rows)

            # ━━ 상단 메트릭 ━━
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("조회 결과", f"{len(df)}건")
            c2.metric("전체 등록 수", f"{total:,}건")
            c3.metric("식품유형", food_type)
            if "제조사" in df.columns:
                c4.metric("제조사 수", f"{df['제조사'].nunique()}개")

            st.markdown("---")

            # ━━ 탭 ━━
            tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

            with tab1:
                st.markdown(f"### 📋 {food_type} 최신 품목제조보고 ({len(df)}건)")

                # 검색 필터
                col_a, col_b = st.columns(2)
                with col_a:
                    search = st.text_input("🔎 제품명/제조사 검색", placeholder="검색어 입력...")
                with col_b:
                    if "제조사" in df.columns:
                        makers = ["전체"] + sorted(df["제조사"].dropna().unique().tolist())
                        sel_maker = st.selectbox("제조사 필터", makers)

                filtered = df.copy()
                if search:
                    mask = filtered.apply(lambda r: search.lower() in str(r).lower(), axis=1)
                    filtered = filtered[mask]
                if "제조사" in df.columns and sel_maker != "전체":
                    filtered = filtered[filtered["제조사"] == sel_maker]

                # 테이블 표시
                show_cols = ["제품명", "식품유형", "제조사", "보고일자", "유통기한", "생산종료"]
                show_cols = [c for c in show_cols if c in filtered.columns]

                st.dataframe(
                    filtered[show_cols].reset_index(drop=True),
                    use_container_width=True,
                    height=500,
                )
                st.caption(f"총 {len(filtered)}건 표시 중")

            with tab2:
                st.markdown(f"### 📊 {food_type} 데이터 분석")

                ch1, ch2 = st.columns(2)

                # 제조사별 제품 수
                if "제조사" in df.columns:
                    with ch1:
                        maker_counts = df["제조사"].value_counts().head(15)
                        fig1 = px.bar(
                            x=maker_counts.values,
                            y=maker_counts.index,
                            orientation="h",
                            title="제조사별 제품 수 (상위 15)",
                            labels={"x": "제품 수", "y": "제조사"},
                            color=maker_counts.values,
                            color_continuous_scale="Blues",
                        )
                        fig1.update_layout(height=450, showlegend=False, yaxis=dict(autorange="reversed"))
                        fig1.update_coloraxes(showscale=False)
                        st.plotly_chart(fig1, use_container_width=True)

                # 보고일자 분포
                if "보고일자_dt" in df.columns:
                    with ch2:
                        df_dt = df.dropna(subset=["보고일자_dt"]).copy()
                        if not df_dt.empty:
                            df_dt["연월"] = df_dt["보고일자_dt"].dt.to_period("M").astype(str)
                            monthly = df_dt["연월"].value_counts().sort_index().tail(24)
                            fig2 = px.line(
                                x=monthly.index,
                                y=monthly.values,
                                title="월별 보고 건수 추이 (최근 24개월)",
                                labels={"x": "연월", "y": "건수"},
                                markers=True,
                            )
                            fig2.update_layout(height=450)
                            st.plotly_chart(fig2, use_container_width=True)

                # 생산종료 현황
                if "생산종료" in df.columns:
                    prod_counts = df["생산종료"].value_counts()
                    fig3 = px.pie(
                        values=prod_counts.values,
                        names=prod_counts.index,
                        title="생산종료 현황",
                        color_discrete_sequence=px.colors.qualitative.Set2,
                    )
                    fig3.update_layout(height=350)
                    st.plotly_chart(fig3, use_container_width=True)

            with tab3:
                st.markdown("### 📥 원시 데이터 (전체 필드)")
                st.dataframe(df, use_container_width=True, height=500)

                # CSV 다운로드
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 CSV 다운로드",
                    csv,
                    f"{food_type}_품목제조보고_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv",
                    use_container_width=True,
                )

    # ━━━ 복수 유형 비교 ━━━
    else:
        if not selected_types:
            st.warning("⚠️ 비교할 식품유형을 1개 이상 선택하세요.")
        else:
            all_rows, status_msgs = fetch_multiple_types(selected_types, per_type)

            # 조회 결과 요약
            st.markdown("### 📡 조회 결과 요약")
            summary_cols = st.columns(min(len(selected_types), 5))
            for i, ft in enumerate(selected_types):
                info = status_msgs[ft]
                with summary_cols[i % len(summary_cols)]:
                    if info["msg"] == "정상":
                        st.metric(ft, f"{info['fetched']}건", f"전체 {info['total']:,}건")
                    else:
                        st.metric(ft, "❌", info["msg"])

            if all_rows:
                df = to_dataframe(all_rows)

                st.markdown("---")

                tab1, tab2, tab3 = st.tabs(["📋 통합 목록", "📊 유형별 비교", "📥 데이터"])

                with tab1:
                    st.markdown(f"### 📋 통합 품목 목록 ({len(df)}건)")

                    # 유형별 필터
                    types_in_data = ["전체"] + sorted(df["식품유형"].dropna().unique().tolist())
                    sel_type = st.selectbox("식품유형 필터", types_in_data)

                    show_df = df if sel_type == "전체" else df[df["식품유형"] == sel_type]

                    show_cols = ["제품명", "식품유형", "제조사", "보고일자", "유통기한"]
                    show_cols = [c for c in show_cols if c in show_df.columns]
                    st.dataframe(show_df[show_cols].reset_index(drop=True), use_container_width=True, height=500)

                with tab2:
                    st.markdown("### 📊 식품유형별 비교 분석")

                    ch1, ch2 = st.columns(2)

                    with ch1:
                        type_counts = df["식품유형"].value_counts()
                        fig = px.bar(
                            x=type_counts.index,
                            y=type_counts.values,
                            title="식품유형별 조회 건수",
                            labels={"x": "식품유형", "y": "건수"},
                            color=type_counts.index,
                        )
                        fig.update_layout(height=400, showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

                    with ch2:
                        if "제조사" in df.columns:
                            maker_type = df.groupby("식품유형")["제조사"].nunique().reset_index()
                            maker_type.columns = ["식품유형", "제조사수"]
                            fig2 = px.bar(
                                maker_type, x="식품유형", y="제조사수",
                                title="유형별 제조사 다양성",
                                color="식품유형",
                            )
                            fig2.update_layout(height=400, showlegend=False)
                            st.plotly_chart(fig2, use_container_width=True)

                    # 유형별 상위 제조사
                    st.markdown("#### 🏢 유형별 상위 제조사")
                    for ft in selected_types:
                        ft_df = df[df["식품유형"] == ft]
                        if not ft_df.empty and "제조사" in ft_df.columns:
                            top = ft_df["제조사"].value_counts().head(5)
                            with st.expander(f"**{ft}** — 상위 제조사 (총 {len(ft_df)}건)"):
                                for rank, (maker, cnt) in enumerate(top.items(), 1):
                                    st.markdown(f"{rank}. **{maker}** — {cnt}건")

                with tab3:
                    st.dataframe(df, use_container_width=True, height=500)
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        "📥 CSV 다운로드",
                        csv,
                        f"품목제조보고_비교_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv",
                        use_container_width=True,
                    )

else:
    # 초기 안내
    st.info("👈 왼쪽 사이드바에서 식품유형을 선택하고 **[조회 실행]** 버튼을 누르세요.")

    st.markdown("""
    ### 사용 방법

    **단일 유형 조회** — 한 가지 식품유형의 최신 제품 100건을 상세 조회합니다.
    제품 목록, 제조사 분석, 보고일자 추이 차트를 확인할 수 있습니다.

    **복수 유형 비교** — 여러 식품유형을 동시에 조회하여 비교합니다.
    유형별 제품 수, 제조사 다양성 등을 한눈에 비교할 수 있습니다.

    ### API 정보

    | 항목 | 내용 |
    |---|---|
    | 서비스명 | 식품(첨가물)품목제조보고 |
    | 서비스ID | I1250 |
    | 제공기관 | 행정안전부 |
    | 서버필터링 | PRDLST_DCNM (식품유형명) |
    | 호출제한 | 1회 최대 1,000건 / 일 2,000회 |
    """)
