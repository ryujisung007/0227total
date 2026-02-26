"""🔍 적부 판정"""
import streamlit as st
import pandas as pd
import io

# page_config set in main app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.label_engine import *
st.markdown("# 🔍 표시사항 적부 판정")
st.markdown("제품 표시사항을 입력하면 3개 법령 기준으로 자동 검토합니다")
st.markdown("---")

# ━━━ 입력 방법 선택 ━━━
input_method = st.radio("입력 방법", [
    "✍️ 직접 입력/붙여넣기",
    "📄 CSV 업로드",
    "📎 샘플 데이터",
], horizontal=True)

label_data = {}

# ━━━ 방법 1: 직접 입력 ━━━
if input_method == "✍️ 직접 입력/붙여넣기":
    st.markdown("### ✍️ 표시사항 입력")
    st.caption("다른 곳에서 복사한 텍스트를 각 칸에 붙여넣으세요")

    with st.form("label_input"):
        st.markdown("**📋 식품등의 표시기준 항목**")
        c1, c2 = st.columns(2)
        with c1:
            label_data["제품명"] = st.text_input("제품명 *", placeholder="예: 스파클링 레몬에이드")
            label_data["식품유형"] = st.text_input("식품유형 *", placeholder="예: 탄산음료")
            label_data["업소명"] = st.text_input("업소명 *", placeholder="예: 주식회사 OO식품")
            label_data["소재지"] = st.text_input("소재지 *", placeholder="예: 서울시 강남구 OO로 123")
            label_data["소비기한"] = st.text_input("소비기한 *", placeholder="예: 제조일로부터 12개월")
            label_data["내용량"] = st.text_input("내용량 *", placeholder="예: 500ml")
        with c2:
            label_data["원재료명"] = st.text_area("원재료명 * (함량순)", height=80,
                placeholder="예: 정제수, 과당포도당액(국산), 구연산, 이산화탄소, 레몬농축액(이탈리아산)3%")
            label_data["영양성분"] = st.text_area("영양성분 * (9종)", height=80,
                placeholder="예: 열량 45kcal, 탄수화물 11g, 당류 10g, 단백질 0g, 지방 0g, 포화지방 0g, 트랜스지방 0g, 콜레스테롤 0mg, 나트륨 15mg")
            label_data["알레르기"] = st.text_input("알레르기 유발물질 *", placeholder="예: 대두, 우유 (또는 해당없음)")
            label_data["보관방법"] = st.text_input("보관방법 *", placeholder="예: 직사광선을 피하고 서늘한 곳에 보관")
            label_data["주의사항"] = st.text_input("주의사항 *", placeholder="예: 개봉 후 냉장보관")
            label_data["카페인함량"] = st.text_input("카페인 함량", placeholder="예: 총카페인 함량 80mg / 고카페인 함유")

        st.markdown("**🌏 원산지 표시요령 항목**")
        c3, c4 = st.columns(2)
        with c3:
            label_data["과즙함량"] = st.text_input("과즙함량", placeholder="예: 레몬과즙 3%")
            label_data["원산지(주원료1)"] = st.text_input("원산지 (주원료1) *", placeholder="예: 정제수(국산)")
        with c4:
            label_data["원산지(주원료2)"] = st.text_input("원산지 (주원료2)", placeholder="예: 과당포도당액(국산)")

        st.markdown("**📦 기구용기 규격 항목**")
        c5, c6 = st.columns(2)
        with c5:
            label_data["용기재질"] = st.text_input("용기 재질 *", placeholder="예: PET, PP, 유리, 알루미늄캔")
            label_data["용기용출시험"] = st.selectbox("용출시험 결과", ["적합", "미확인", "부적합"])
        with c6:
            label_data["재활용표시"] = st.text_input("재활용 표시", placeholder="예: PET 1등급")

        submitted = st.form_submit_button("🔍 적부 판정 실행", type="primary", use_container_width=True)

# ━━━ 방법 2: CSV 업로드 ━━━
elif input_method == "📄 CSV 업로드":
    st.markdown("### 📄 CSV 파일 업로드")

    # 템플릿 다운로드
    st.download_button(
        "📥 CSV 양식 다운로드",
        CSV_TEMPLATE.encode("utf-8-sig"),
        "표시사항_양식.csv", "text/csv",
    )

    uploaded_csv = st.file_uploader("CSV 파일 업로드", type=["csv"])
    submitted = False

    if uploaded_csv:
        try:
            csv_df = pd.read_csv(uploaded_csv, encoding="utf-8-sig")
            if "항목" in csv_df.columns and "내용" in csv_df.columns:
                for _, row in csv_df.iterrows():
                    label_data[row["항목"]] = str(row["내용"]) if pd.notna(row["내용"]) else ""
            else:
                # 가로형 (컬럼이 항목명)
                for col in csv_df.columns:
                    label_data[col] = str(csv_df[col].iloc[0]) if len(csv_df) > 0 else ""

            st.success(f"✅ {len(label_data)}개 항목 로드됨")
            st.dataframe(pd.DataFrame(list(label_data.items()), columns=["항목","내용"]),
                        use_container_width=True, hide_index=True)
            submitted = st.button("🔍 적부 판정 실행", type="primary", use_container_width=True)
        except Exception as e:
            st.error(f"CSV 파싱 오류: {e}")

    # 또는 텍스트 붙여넣기
    st.markdown("---")
    st.markdown("**또는 텍스트 통째로 붙여넣기:**")
    raw_text = st.text_area("제품 표시사항 전문 (자유 형식)", height=200,
        placeholder="제품명: 스파클링 레몬에이드\n식품유형: 탄산음료\n업소명: ...\n또는 제품 라벨 내용을 그대로 붙여넣기")

    if raw_text and not label_data:
        # 자유 형식 파싱
        for line in raw_text.split("\n"):
            if ":" in line:
                parts = line.split(":", 1)
                label_data[parts[0].strip()] = parts[1].strip()
            elif "：" in line:
                parts = line.split("：", 1)
                label_data[parts[0].strip()] = parts[1].strip()
        if label_data:
            st.success(f"✅ {len(label_data)}개 항목 파싱됨")
            submitted = st.button("🔍 적부 판정 실행", type="primary", use_container_width=True, key="btn_text")

# ━━━ 방법 3: 샘플 ━━━
elif input_method == "📎 샘플 데이터":
    st.markdown("### 📎 샘플 표시사항")
    sample_name = st.selectbox("샘플 선택", list(SAMPLE_LABELS.keys()))
    label_data = SAMPLE_LABELS[sample_name].copy()

    st.dataframe(pd.DataFrame(list(label_data.items()), columns=["항목","내용"]),
                use_container_width=True, hide_index=True)
    submitted = st.button("🔍 적부 판정 실행", type="primary", use_container_width=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 적부 판정 결과
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if submitted and label_data:
    st.session_state.last_label = label_data
    st.session_state.last_results = check_compliance(label_data)

if st.session_state.get("last_results"):
    results = st.session_state.last_results
    summary = get_summary(results)
    label_data = st.session_state.get("last_label", {})

    st.markdown("---")
    st.markdown("## 📊 적부 판정 결과")

    # 요약 메트릭
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("종합 판정", summary["overall"])
    mc2.metric("적합률", f"{summary['rate']:.0f}%")
    mc3.metric("✅ 적합", f"{summary['ok']}건")
    mc4.metric("⚠️ 주의", f"{summary['warn']}건")
    mc5.metric("❌ 부적합", f"{summary['fail']}건")

    # 법령별 결과
    st.markdown("---")

    for doc_key, schema in REGULATION_SCHEMA.items():
        doc_results = [r for r in results if r["법령"] == schema["약칭"]]
        if not doc_results:
            continue

        doc_ok = sum(1 for r in doc_results if r["판정"] == "적합")
        doc_total = len(doc_results)

        with st.expander(f"**{schema['법령명']}** — {doc_ok}/{doc_total} 적합", expanded=True):
            for r in doc_results:
                color_map = {"적합": "🟢", "주의": "🟡", "부적합": "🔴", "미확인": "⚪"}
                icon = color_map.get(r["판정"], "⚪")

                with st.container(border=True):
                    hc1, hc2 = st.columns([3, 1])
                    with hc1:
                        st.markdown(f"{icon} **[{r['id']}] {r['항목']}** — {r['판정']}")
                        st.caption(f"📝 입력: {r['입력값'][:60]}{'...' if len(r['입력값']) > 60 else ''}")
                        st.markdown(f"💬 {r['사유']}")
                    with hc2:
                        st.markdown(f"📖 **{r['조항']}**")

                        # 지식베이스에서 관련 조항 검색
                        kb_doc_key = [k for k, v in REGULATION_SCHEMA.items() if v["약칭"] == r["법령"]]
                        if kb_doc_key:
                            # 조항 번호 추출
                            clause_nums = re.findall(r'제(\d+)조', r['조항'])
                            for num in clause_nums[:1]:
                                matches = search_knowledge(kb_doc_key[0], f"제{num}조")
                                if matches:
                                    with st.popover(f"📖 제{num}조 원문"):
                                        st.text(matches[0][:500])

    # 결과 다운로드
    st.markdown("---")
    result_df = pd.DataFrame(results)
    c1, c2 = st.columns(2)
    with c1:
        csv_dl = result_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 판정결과 CSV", csv_dl, "적부판정결과.csv", "text/csv", use_container_width=True)
    with c2:
        buf = io.BytesIO()
        result_df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("📥 판정결과 Excel", buf.getvalue(), "적부판정결과.xlsx",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         use_container_width=True)

    # AI 심화분석
    st.markdown("---")
    st.markdown("### 🤖 AI 심화 분석")
    if st.button("🤖 GPT로 심화 분석 실행", type="primary", use_container_width=True):
        with st.spinner("AI가 법령을 분석하고 있습니다..."):
            # 지식베이스 컨텍스트
            kb_context = ""
            for doc_key in REGULATION_SCHEMA:
                kb_data = load_knowledge(doc_key)
                if kb_data:
                    kb_context += f"\n[{REGULATION_SCHEMA[doc_key]['법령명']}]\n"
                    kb_context += "\n".join(c["text"][:500] for c in kb_data.get("chunks", [])[:5])

            label_summary = "\n".join(f"- {k}: {v}" for k, v in label_data.items() if v)
            fail_items = "\n".join(f"- [{r['id']}] {r['항목']}: {r['사유']}" for r in results if r["판정"] in ("부적합","주의"))

            prompt = f"""아래 식품 표시사항의 법령 적합성을 심화 분석하세요.

[제품 표시사항]
{label_summary}

[규칙 기반 판정에서 부적합/주의 항목]
{fail_items if fail_items else "(없음)"}

[참조 법령]
{kb_context if kb_context else "(PDF 미업로드)"}

다음을 분석하세요:
1. 부적합 항목별 구체적 시정 방법
2. 놓칠 수 있는 추가 위반 사항
3. 표시 개선 권고사항
4. 관련 조항 인용과 해석

한국어로 전문적이고 구체적으로 작성하세요."""

            answer, err = call_openai(
                "당신은 식품위생법·표시기준 전문 법률가입니다. 조항을 정확히 인용하며 답변하세요.",
                prompt, 2000
            )
            if answer:
                st.markdown(answer)
            else:
                st.warning(f"⚠️ {err}")

render_chatbot("적부판정", "표시사항 입력 및 적부 판정 페이지. 3개 법령 기반 검토.")
