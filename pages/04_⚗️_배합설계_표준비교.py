"""⚗️ 배합비 설계"""
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
st.markdown("# ⚗️ 배합비 설계 & 표준 비교")
st.markdown("배합비 100% 기준 설계 · 표준배합비 대비 비교분석 · 원가 연동")
st.markdown("---")

tab_input, tab_compare, tab_cost = st.tabs(["📋 배합표 (100%)", "🔀 표준배합비 비교", "💰 원가 연동"])

# ━━━━━ TAB 1: 배합표 100% 기준 ━━━━━
with tab_input:
    form = st.session_state.get("ai_formulation")

    input_mode = st.radio("배합비 입력 방식", [
        "🤖 AI 생성 배합비",
        "✏️ 직접 입력 (CSV)",
        "📋 표준배합비에서 시작",
    ], horizontal=True)

    df_current = None

    if input_mode == "🤖 AI 생성 배합비":
        if not form:
            st.warning("먼저 [🤖 AI제품카드] 페이지에서 제품을 선택하세요.")
            if st.button("🤖 AI 카드로 이동"):
                st.switch_page("pages/03_🤖_제품기획_AI카드.py")
        else:
            st.markdown(f"### 🧪 {form['productName']}")
            st.caption(form.get("concept", ""))
            rows = []
            for ing in form["ingredients"]:
                rows.append({
                    "원료명": ing["name"],
                    "비율(%)": ing["pct"],
                    "함량(g)": ing["amount"],
                    "기능": ing["function"],
                    "등급": ing["grade"],
                })
            df_current = pd.DataFrame(rows)

    elif input_mode == "✏️ 직접 입력 (CSV)":
        csv_text = st.text_area("CSV 배합비 (비율은 반드시 100% 기준)",
            value=st.session_state.get("csv_input", ""),
            height=250,
            placeholder="원료명,비율(%),기능,등급\n정제수,86.0,용매,식품용수\n과당포도당액,11.0,감미,식품첨가물\n구연산,0.5,산미조절,식품첨가물\n탄산가스,0.8,탄산,식품첨가물\n천연향료,0.3,풍미,천연향료\n카라멜색소,0.16,착색,식품첨가물")
        if csv_text.strip():
            df_current, msg = parse_csv_formula(csv_text)
            if df_current is None:
                st.error(f"파싱 오류: {msg}")

    elif input_mode == "📋 표준배합비에서 시작":
        sel_std = st.selectbox("표준배합비 선택", list(STANDARD_FORMULATIONS.keys()))
        std = STANDARD_FORMULATIONS[sel_std]
        df_current = pd.DataFrame(std["ingredients"])
        st.info(f"📎 {sel_std} — Brix {std['brix']}° / pH {std['pH']}")

    # ─── 배합표 표시 ───
    if df_current is not None and "비율(%)" in df_current.columns:
        st.markdown("---")
        total_pct = df_current["비율(%)"].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("비율 합계", f"{total_pct:.2f}%",
                  delta="✅ 적정" if 99 <= total_pct <= 101 else "⚠️ 조정필요")
        m2.metric("원료 종류", f"{len(df_current)}종")
        if form:
            m3.metric("Brix / pH", f"{form.get('brix','-')}° / {form.get('pH','-')}")

        if total_pct > 0 and (total_pct < 99 or total_pct > 101):
            if st.button("🔄 100%로 자동 정규화"):
                df_current["비율(%)"] = (df_current["비율(%)"] / total_pct * 100).round(3)
                st.rerun()

        st.markdown("### 📋 배합표 (100% 기준)")
        display_df = df_current.copy()
        display_df["비율(%)"] = display_df["비율(%)"].round(3)
        if "함량(g)" not in display_df.columns:
            display_df["함량(g)"] = (display_df["비율(%)"] * 5).round(2)

        st.dataframe(
            display_df.style.format({"비율(%)": "{:.3f}", "함량(g)": "{:.2f}"}),
            use_container_width=True, hide_index=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            pie_df = df_current[df_current["비율(%)"] > 0]
            fig = px.pie(pie_df, values="비율(%)", names="원료명", hole=0.4,
                         title="배합비 구성 (%)", color_discrete_sequence=COLORS)
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            bar_df = df_current[df_current["비율(%)"] > 0].sort_values("비율(%)", ascending=True)
            fig2 = px.bar(bar_df, y="원료명", x="비율(%)", orientation="h",
                          title="원료별 배합비율 (%)", color="원료명",
                          color_discrete_sequence=COLORS, text="비율(%)")
            fig2.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
            fig2.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        st.session_state.current_formula_df = df_current

        st.markdown("---")
        bc1, bc2, bc3 = st.columns(3)
        csv_dl = display_df.to_csv(index=False).encode("utf-8-sig")
        bc1.download_button("📥 배합표 CSV", csv_dl, "배합표_100pct.csv", "text/csv", use_container_width=True)
        if bc2.button("💰 원가분석 →", use_container_width=True, type="primary"):
            st.session_state.csv_input = display_df.to_csv(index=False)
            st.switch_page("pages/06_💰_원가분석.py")
        if bc3.button("🏭 공정설계 →", use_container_width=True):
            st.switch_page("pages/07_🏭_공정설계_리스크.py")


# ━━━━━ TAB 2: 표준배합비 비교 ━━━━━
with tab_compare:
    st.markdown("### 🔀 내 배합비 vs 표준배합비 비교")

    df_mine = st.session_state.get("current_formula_df")
    if df_mine is None or "비율(%)" not in getattr(df_mine, 'columns', []):
        st.warning("먼저 [📋 배합표] 탭에서 배합비를 입력하거나 AI로 생성하세요")
    else:
        std_name = st.selectbox("비교할 표준배합비", list(STANDARD_FORMULATIONS.keys()), key="cmp_std")
        std_data = STANDARD_FORMULATIONS[std_name]
        df_std = pd.DataFrame(std_data["ingredients"])

        st.info(f"📎 표준: {std_name} — Brix {std_data['brix']}° / pH {std_data['pH']}")

        cmp_df = compare_formulations(df_mine, df_std)

        if len(cmp_df) > 0:
            st.markdown("#### 📊 비교 분석표")

            def color_judgment(val):
                if isinstance(val, str):
                    if "초과" in val: return "background-color: #FEE2E2"
                    if "부족" in val: return "background-color: #FEF3C7"
                    if "동일" in val: return "background-color: #D1FAE5"
                return ""

            styled = cmp_df.style.applymap(color_judgment, subset=["판정"]).format({
                "내 배합(%)": "{:.3f}", "표준(%)": "{:.3f}", "차이(%)": "{:.3f}",
            })
            st.dataframe(styled, use_container_width=True, hide_index=True)

            same = len(cmp_df[cmp_df["판정"].str.contains("동일")])
            over = len(cmp_df[cmp_df["판정"].str.contains("초과")])
            under = len(cmp_df[cmp_df["판정"].str.contains("부족")])
            only_mine = len(cmp_df[(cmp_df["표준(%)"] == 0) & (cmp_df["내 배합(%)"] > 0)])
            only_std = len(cmp_df[(cmp_df["내 배합(%)"] == 0) & (cmp_df["표준(%)"] > 0)])

            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            mc1.metric("✅ 동일", f"{same}건")
            mc2.metric("⬆️ 초과", f"{over}건")
            mc3.metric("⬇️ 부족", f"{under}건")
            mc4.metric("➕ 내것만", f"{only_mine}건")
            mc5.metric("➖ 표준만", f"{only_std}건")

            st.markdown("---")
            c1, c2 = st.columns(2)

            with c1:
                chart_df = cmp_df.melt(
                    id_vars=["원료명"], value_vars=["내 배합(%)", "표준(%)"],
                    var_name="구분", value_name="비율(%)"
                )
                fig = px.bar(chart_df, x="원료명", y="비율(%)", color="구분", barmode="group",
                             title="원료별 배합비 비교",
                             color_discrete_map={"내 배합(%)": "#3B82F6", "표준(%)": "#F59E0B"})
                fig.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                diff_df = cmp_df[cmp_df["차이(%)"].abs() > 0.001].sort_values("차이(%)")
                colors = ["#EF4444" if v < 0 else "#10B981" for v in diff_df["차이(%)"]]
                fig2 = go.Figure(go.Bar(
                    y=diff_df["원료명"], x=diff_df["차이(%)"],
                    orientation="h", marker_color=colors,
                    text=[f"{v:+.3f}%" for v in diff_df["차이(%)"]],
                    textposition="outside"
                ))
                fig2.update_layout(title="차이 분석 (내 배합 − 표준)", height=400,
                                   xaxis_title="차이 (%)")
                fig2.add_vline(x=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig2, use_container_width=True)

            csv_cmp = cmp_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 비교표 CSV", csv_cmp, "표준비교분석.csv", "text/csv")


# ━━━━━ TAB 3: 원가 연동 ━━━━━
with tab_cost:
    st.markdown("### 💰 배합비 기반 원가 계산")

    df_mine = st.session_state.get("current_formula_df")
    if df_mine is None or "비율(%)" not in getattr(df_mine, 'columns', []):
        st.warning("먼저 [📋 배합표] 탭에서 배합비를 입력하세요")
    else:
        vol = st.number_input("기준 용량 (ml)", 100, 2000, 500, 50, key="cost_vol")
        batch = st.number_input("배치 수량 (병)", 1, 1000000, 1000, 100, key="cost_batch")

        cost_df = calc_cost_table(df_mine, vol)
        total_cost = cost_df["원가(원)"].sum()

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("1병 원재료비", f"{total_cost:,.1f}원")
        mc2.metric(f"{batch:,}병 원재료비", f"{total_cost * batch:,.0f}원")
        mc3.metric("원료 종류", f"{len(cost_df)}종")

        st.dataframe(
            cost_df.style.format({
                "비율(%)": "{:.3f}", "함량(g)": "{:.2f}",
                "단가(원/kg)": "{:,.0f}", "원가(원)": "{:,.2f}",
            }),
            use_container_width=True, hide_index=True,
        )

        unmatched = cost_df[cost_df["매칭원료"] == ""]
        if len(unmatched) > 0:
            st.warning(f"⚠️ 단가 미등록 원료: {', '.join(unmatched['원료명'].tolist())}")

        if st.button("💰 상세 원가분석 →", type="primary"):
            st.session_state.csv_input = df_mine.to_csv(index=False)
            st.switch_page("pages/06_💰_원가분석.py")

# ━━━ 챗봇 ━━━
render_chatbot("배합비설계",
    page_context="배합비 100% 기준 설계 + 표준배합비 비교 + 원가 연동 페이지.",
    system_extra="배합비 설계 원칙, 원료 기능, 표준 대비 차이 분석, Brix/pH 조절 관련 질문에 답변하세요.")
