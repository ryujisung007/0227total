"""💰 원가 분석"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
PAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGE_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *

# page_config set in main app.py
st.markdown("# 💰 원재료 원가 분석")
st.markdown("배합비 기반 원가 자동 계산 · 원재료 단가표 · 원가 구성 시각화")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 배합비 원가 계산", "📋 원재료 단가표", "🔧 단가 수정"])

# ━━━ TAB 1: 배합비 원가 계산 ━━━
with tab1:
    st.markdown("### 📊 배합비 → 원가 자동 계산")

    volume = st.number_input("기준 용량 (ml)", 100, 2000, 500, 50)
    batch = st.number_input("생산 배치 (병)", 1, 1000000, 1000, 100)

    # 입력 소스 선택
    src = st.radio("배합비 입력", ["직접 입력 (CSV)", "세션에서 가져오기", "샘플 배합비"], horizontal=True)

    csv_text = ""
    if src == "직접 입력 (CSV)":
        csv_text = st.text_area("CSV 배합비 (원료명, 비율(%))", height=200,
            placeholder="원료명,비율(%),기능,등급\n정제수,86.0,용매,식품용수\n과당포도당액,11.0,감미,식품첨가물")
    elif src == "세션에서 가져오기":
        csv_text, source_msg = get_current_formula_csv()
        if csv_text:
            st.success(f"📎 {source_msg}")
            st.code(csv_text[:400] + "..." if len(csv_text) > 400 else csv_text)
        else:
            st.info("배합비가 없습니다. [⚗️ 배합비설계] 또는 [🤖 AI제품카드]에서 먼저 배합비를 생성하세요.")
    else:
        smp = st.selectbox("샘플 선택", list(SAMPLE_FORMULATIONS.keys()))
        csv_text = SAMPLE_FORMULATIONS[smp]

    if csv_text.strip():
        df_parsed, msg = parse_csv_formula(csv_text)
        if df_parsed is not None and "비율(%)" in df_parsed.columns:
            # 원가 계산
            cost_df = calc_cost_table(df_parsed, volume)
            total_cost = cost_df["원가(원)"].sum()
            batch_cost = total_cost * batch

            # 메트릭
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("1병 원재료비", f"{total_cost:,.1f}원")
            m2.metric(f"{batch:,}병 원재료비", f"{batch_cost:,.0f}원")
            m3.metric("원료 종류", f"{len(cost_df)}종")
            m4.metric("비율 합계", f"{cost_df['비율(%)'].sum():.1f}%")

            st.markdown("---")

            # 원가 테이블
            st.markdown("### 📋 원가표")
            display_df = cost_df.copy()
            display_df["배치원가(원)"] = (display_df["원가(원)"] * batch).round(0)
            display_df["원가비중(%)"] = (display_df["원가(원)"] / total_cost * 100).round(1) if total_cost > 0 else 0

            st.dataframe(
                display_df.style.format({
                    "비율(%)": "{:.2f}", "함량(g)": "{:.2f}",
                    "단가(원/kg)": "{:,.0f}", "원가(원)": "{:,.2f}",
                    "배치원가(원)": "{:,.0f}", "원가비중(%)": "{:.1f}",
                }),
                use_container_width=True, hide_index=True,
            )

            # 합계 행
            st.info(f"**합계:** 1병 원재료비 **{total_cost:,.1f}원** | {batch:,}병 기준 **{batch_cost:,.0f}원** ({batch_cost/10000:,.1f}만원)")

            # 차트
            c1, c2 = st.columns(2)
            with c1:
                fig = px.pie(cost_df[cost_df["원가(원)"] > 0], values="원가(원)", names="원료명",
                             title="원가 구성 비율", hole=0.4, color_discrete_sequence=COLORS)
                fig.update_layout(height=380)
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                fig2 = px.bar(cost_df.sort_values("원가(원)", ascending=True),
                              y="원료명", x="원가(원)", orientation="h",
                              title="원료별 원가 (1병 기준, 원)", color="원료명",
                              color_discrete_sequence=COLORS, text="원가(원)")
                fig2.update_traces(texttemplate="%{text:.1f}원", textposition="outside")
                fig2.update_layout(height=380, showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)

            # 매칭 안 된 원료 경고
            unmatched = cost_df[cost_df["매칭원료"] == ""]
            if len(unmatched) > 0:
                st.warning(f"⚠️ 단가DB에 없는 원료 {len(unmatched)}건: {', '.join(unmatched['원료명'].tolist())} → 0원 처리됨. [🔧 단가 수정] 탭에서 추가 가능")

            # 다운로드
            st.markdown("---")
            csv_dl = display_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 원가표 CSV", csv_dl, "원가분석표.csv", "text/csv")
        else:
            st.error(f"파싱 오류: {msg}")

# ━━━ TAB 2: 원재료 단가표 ━━━
with tab2:
    st.markdown("### 📋 원재료 단가 데이터베이스")
    search = st.text_input("🔍 원료 검색", placeholder="예: 구연산, 향료")

    price_rows = []
    for name, info in INGREDIENT_COSTS.items():
        if search and search.lower() not in name.lower():
            continue
        price_rows.append({
            "원료명": name, "단가": f"{info['unit_price']:,}", "단위": info["unit"],
            "공급처": info["supplier"], "MOQ": info["moq"],
        })
    price_df = pd.DataFrame(price_rows)
    st.dataframe(price_df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"총 {len(price_df)}개 원료 등록")

# ━━━ TAB 3: 단가 수정 ━━━
with tab3:
    st.markdown("### 🔧 원재료 단가 추가/수정")
    st.caption("세션 내에서만 유효합니다 (새로고침 시 초기화)")

    if "custom_costs" not in st.session_state:
        st.session_state.custom_costs = {}

    with st.form("add_cost"):
        c1, c2, c3 = st.columns(3)
        new_name = c1.text_input("원료명")
        new_price = c2.number_input("단가 (원/kg)", 0, 1000000, 5000)
        new_supplier = c3.text_input("공급처", "미정")
        if st.form_submit_button("추가/수정", type="primary"):
            if new_name:
                INGREDIENT_COSTS[new_name] = {
                    "unit_price": new_price, "unit": "원/kg",
                    "supplier": new_supplier, "moq": "-",
                }
                st.session_state.custom_costs[new_name] = new_price
                st.success(f"✅ '{new_name}' {new_price:,}원/kg 등록 완료")

    if st.session_state.custom_costs:
        st.markdown("**이번 세션에서 추가/수정된 원료:**")
        for k, v in st.session_state.custom_costs.items():
            st.write(f"- {k}: {v:,}원/kg")

# ━━━ 챗봇 ━━━
render_chatbot("원가분석",
    page_context="원재료 단가 DB(36종) + 배합비 기반 원가 자동 계산 페이지.",
    system_extra="원가 분석, 단가 트렌드, 원가 절감 방안, 공급처 관련 질문에 답변하세요.")
