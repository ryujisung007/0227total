"""✏️ 배합비 작성 연습"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import io

# page_config set in main app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *
st.markdown("# ✏️ 배합비 작성 연습")
st.markdown("CSV 작성 → 실시간 검증 → 표준배합비 비교 → 원가 계산 → 저장")
st.markdown("---")

student = st.session_state.get("student_name", "")

# ━━━ 사이드바 ━━━
with st.sidebar:
    st.markdown("### 📎 샘플 배합비")
    for name in SAMPLE_FORMULATIONS:
        if st.button(f"📋 {name}", key=f"smp_{name}", use_container_width=True):
            st.session_state.csv_input = SAMPLE_FORMULATIONS[name]
            st.session_state.formula_name = name
            st.rerun()

    st.markdown("---")
    st.markdown("### 📎 표준배합비 불러오기")
    for name, std in STANDARD_FORMULATIONS.items():
        if st.button(f"🏷️ {name}", key=f"std_{name}", use_container_width=True):
            df_s = pd.DataFrame(std["ingredients"])
            st.session_state.csv_input = df_s.to_csv(index=False)
            st.session_state.formula_name = name
            st.rerun()

    st.markdown("---")
    st.markdown("### 💾 저장된 배합비")
    saved = load_saved_formulas()
    if saved:
        for s in saved[:10]:
            label = f"{s['name']} ({s.get('student','?')}) {s['timestamp'][:10]}"
            if st.button(f"📂 {label}", key=f"load_{s['filename']}", use_container_width=True):
                df_s = pd.DataFrame(s["ingredients"])
                st.session_state.csv_input = df_s.to_csv(index=False)
                st.session_state.formula_name = s["name"]
                st.rerun()
    else:
        st.caption("저장된 배합비 없음")

# ━━━ AI 카드에서 넘어온 경우 ━━━
if "practice_csv" in st.session_state:
    if "csv_input" not in st.session_state or not st.session_state.get("csv_input"):
        st.session_state.csv_input = st.session_state.practice_csv
        st.session_state.formula_name = st.session_state.get("practice_name", "AI 배합비")
    del st.session_state.practice_csv

# ━━━ 제품 기본정보 ━━━
with st.expander("📋 제품 기본정보", expanded=True):
    c1, c2, c3, c4, c5 = st.columns(5)
    formula_name = c1.text_input("제품명", value=st.session_state.get("formula_name", "나의 배합비"))
    volume = c2.text_input("기준용량(ml)", value="500")
    brix = c3.text_input("목표 Brix(°)", placeholder="예: 10.5")
    pH_val = c4.text_input("목표 pH", placeholder="예: 3.5")
    shelf = c5.text_input("유통기한", placeholder="예: 12개월")

# ━━━ 좌우 레이아웃 ━━━
left, right = st.columns([1, 1])

with left:
    st.markdown("### 📝 CSV 입력 (100% 기준)")

    uploaded = st.file_uploader("CSV 파일 업로드", type=["csv", "txt"], label_visibility="collapsed")
    if uploaded:
        content = uploaded.read().decode("utf-8-sig")
        st.session_state.csv_input = content
        st.rerun()

    csv_text = st.text_area(
        "배합비 CSV (직접 입력 또는 수정)",
        value=st.session_state.get("csv_input", ""),
        height=300,
        placeholder="원료명,비율(%),기능,등급\n정제수,86.0,용매,식품용수\n과당포도당액,11.0,감미,식품첨가물\n구연산,0.5,산미조절,식품첨가물\n...",
        key="csv_editor",
    )
    st.session_state.csv_input = csv_text

    b1, b2, b3 = st.columns(3)
    do_validate = b1.button("🔍 검증", use_container_width=True, type="primary")
    do_save = b2.button("💾 저장", use_container_width=True)
    do_clear = b3.button("🗑️ 초기화", use_container_width=True)

    if do_clear:
        st.session_state.csv_input = ""
        st.session_state.formula_name = "나의 배합비"
        st.rerun()

with right:
    df_parsed, msg = parse_csv_formula(csv_text)

    if df_parsed is not None and "비율(%)" in df_parsed.columns:
        total_pct = df_parsed["비율(%)"].sum()
        st.markdown(f"### 📊 배합표 ({len(df_parsed)}종 원료)")

        color = "green" if 99 <= total_pct <= 101 else "red"
        st.markdown(f"**비율 합계: :{color}[{total_pct:.2f}%]**")

        # 함량 자동 계산
        vol_ml = int(volume) if volume.isdigit() else 500
        show_df = df_parsed.copy()
        if "함량(g)" not in show_df.columns:
            show_df["함량(g)"] = (show_df["비율(%)"] * vol_ml / 100).round(2)

        st.dataframe(show_df.style.format({"비율(%)": "{:.3f}", "함량(g)": "{:.2f}"}),
                     use_container_width=True, hide_index=True)

        # 파이 차트
        pie_df = df_parsed[df_parsed["비율(%)"] > 0]
        if len(pie_df) > 0:
            fig = px.pie(pie_df, values="비율(%)", names="원료명", hole=0.4,
                         color_discrete_sequence=COLORS)
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

        # 검증
        if do_validate:
            meta = {}
            try:
                if brix: meta["brix"] = float(brix)
            except: pass
            try:
                if pH_val: meta["pH"] = float(pH_val)
            except: pass
            result = validate_formula(df_parsed, meta)
            if result["passed"]:
                st.success("✅ 검증 통과!")
            else:
                st.error("⚠️ 수정이 필요합니다")
            for iss in result["issues"]:
                st.error(f"❌ {iss}")
            for w in result["warnings"]:
                st.warning(f"⚠️ {w}")

        # 저장
        if do_save:
            if not student:
                st.warning("⚠️ 메인 페이지에서 이름을 먼저 입력하세요")
            else:
                meta = {"brix": brix, "pH": pH_val, "volume": volume, "shelfLife": shelf}
                filepath = save_formula(formula_name, df_parsed, meta, student)
                st.success(f"✅ 저장 완료! ({os.path.basename(filepath)})")

        # 다운로드
        st.markdown("---")
        dc1, dc2 = st.columns(2)
        with dc1:
            csv_dl = show_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV", csv_dl, f"{formula_name}.csv", "text/csv", use_container_width=True)
        with dc2:
            buf = io.BytesIO()
            show_df.to_excel(buf, index=False, engine="openpyxl")
            st.download_button("📥 Excel", buf.getvalue(), f"{formula_name}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             use_container_width=True)

        # ━━━ 표준배합비 비교 (하단) ━━━
        st.markdown("---")
        st.markdown("### 🔀 표준배합비 비교")

        std_name = st.selectbox("비교할 표준배합비", ["선택 안 함"] + list(STANDARD_FORMULATIONS.keys()))

        if std_name != "선택 안 함":
            std_data = STANDARD_FORMULATIONS[std_name]
            df_std = pd.DataFrame(std_data["ingredients"])
            st.caption(f"표준: {std_name} — Brix {std_data['brix']}° / pH {std_data['pH']}")

            cmp_df = compare_formulations(df_parsed, df_std)

            if len(cmp_df) > 0:
                def color_j(val):
                    if isinstance(val, str):
                        if "초과" in val: return "background-color: #FEE2E2"
                        if "부족" in val: return "background-color: #FEF3C7"
                        if "동일" in val: return "background-color: #D1FAE5"
                    return ""

                styled = cmp_df.style.map(color_j, subset=["판정"]).format({
                    "내 배합(%)": "{:.3f}", "표준(%)": "{:.3f}", "차이(%)": "{:.3f}",
                })
                st.dataframe(styled, use_container_width=True, hide_index=True)

                # 비교 차트
                chart_df = cmp_df.melt(
                    id_vars=["원료명"], value_vars=["내 배합(%)", "표준(%)"],
                    var_name="구분", value_name="비율(%)"
                )
                fig = px.bar(chart_df, x="원료명", y="비율(%)", color="구분",
                             barmode="group", title="내 배합 vs 표준",
                             color_discrete_map={"내 배합(%)": "#3B82F6", "표준(%)": "#F59E0B"})
                fig.update_layout(height=350, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

                csv_cmp = cmp_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("📥 비교표 CSV", csv_cmp, "비교분석.csv", "text/csv")

    elif csv_text.strip():
        st.error(f"❌ 파싱 오류: {msg}")
    else:
        st.info("""
        **입력 방법:**
        1. 좌측에 CSV 직접 작성 (비율은 100% 기준)
        2. CSV 파일 업로드
        3. 사이드바에서 샘플/표준 배합비 불러오기
        4. AI 카드에서 생성된 배합비 가져오기

        **CSV 형식:**
        ```
        원료명,비율(%),기능,등급
        정제수,86.0,용매,식품용수
        과당포도당액,11.0,감미,식품첨가물
        ```
        """)

# ━━━ 챗봇 ━━━
render_chatbot("배합연습",
    page_context="CSV 배합비 작성 연습 + 검증 + 표준비교 + 저장 페이지.",
    system_extra="배합비 작성법, CSV 형식, 검증 기준, 원료 선택 관련 질문에 답변하세요.")
