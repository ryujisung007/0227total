"""📖 법령 조회"""
import streamlit as st
import pandas as pd
PAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGE_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.label_engine import *

# page_config set in main app.py
st.markdown("# 📖 법령 조회 & 검색")
st.markdown("학습된 법령 내용 검색 · 검토항목별 관련 조항 확인 · AI 해석")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🔍 키워드 검색", "📑 항목별 조항", "🤖 AI 법령 해석"])

# ━━━ TAB 1: 키워드 검색 ━━━
with tab1:
    st.markdown("### 🔍 법령 키워드 검색")

    search_q = st.text_input("검색어", placeholder="예: 소비기한, 원산지, 알레르기, 용출시험, 영양성분")

    if search_q:
        total_found = 0
        for doc_key, schema in REGULATION_SCHEMA.items():
            results = search_knowledge(doc_key, search_q)
            if results:
                total_found += len(results)
                st.markdown(f"---")
                st.markdown(f"### 📖 {schema['법령명']} — {len(results)}건")
                for i, text in enumerate(results[:8]):
                    with st.expander(f"결과 {i+1}", expanded=i < 2):
                        # 키워드 하이라이트 (간단)
                        display = text[:800]
                        st.text(display)
                        if len(text) > 800:
                            st.caption(f"... (총 {len(text)}자)")

        if total_found == 0:
            kb_count = len(load_all_knowledge())
            if kb_count == 0:
                st.info("📤 먼저 [📄 법령학습] 페이지에서 PDF를 업로드하세요")
            else:
                st.warning(f"'{search_q}'에 대한 검색 결과가 없습니다. 다른 키워드를 시도하세요.")
    else:
        st.info("검색어를 입력하면 학습된 법령에서 관련 내용을 찾아줍니다")

# ━━━ TAB 2: 항목별 조항 ━━━
with tab2:
    st.markdown("### 📑 검토항목별 관련 조항")

    for doc_key, schema in REGULATION_SCHEMA.items():
        st.markdown(f"---")
        st.markdown(f"### 📖 {schema['법령명']}")

        kb = load_knowledge(doc_key)

        for item in schema["검토항목"]:
            with st.container(border=True):
                ic1, ic2 = st.columns([3, 2])
                with ic1:
                    st.markdown(f"**[{item['id']}] {item['항목']}** {'✅필수' if item['필수'] else '선택'}")
                    st.caption(item["설명"])
                    st.markdown(f"📖 관련조항: **{item['관련조항']}**")

                with ic2:
                    if kb:
                        # 자동으로 관련 조항 찾기
                        clause_nums = re.findall(r'제(\d+)조', item["관련조항"])
                        for num in clause_nums[:1]:
                            matches = search_knowledge(doc_key, f"제{num}조")
                            if matches:
                                with st.popover(f"📖 원문 보기"):
                                    st.text(matches[0][:600])
                            else:
                                st.caption(f"제{num}조 원문 미확인")
                    else:
                        st.caption("PDF 미학습")

# ━━━ TAB 3: AI 법령 해석 ━━━
with tab3:
    st.markdown("### 🤖 AI 법령 해석")
    st.caption("특정 조항이나 상황에 대해 AI가 법령을 해석합니다")

    render_api_key_input()

    question = st.text_area("질문", height=100,
        placeholder="예:\n- 과채음료에서 과즙함량 표시 기준은?\n- 수입 원료의 원산지 표시 방법은?\n- PET 용기의 용출시험 기준은?")

    if st.button("🤖 AI 해석 실행", type="primary") and question:
        with st.spinner("법령을 분석 중..."):
            # 지식베이스 컨텍스트
            kb_context = ""
            for doc_key in REGULATION_SCHEMA:
                # 질문에서 키워드 추출하여 관련 청크만
                keywords = [w for w in question.split() if len(w) > 1][:5]
                for kw in keywords:
                    matches = search_knowledge(doc_key, kw)
                    if matches:
                        kb_context += f"\n[{REGULATION_SCHEMA[doc_key]['법령명']}]\n"
                        kb_context += "\n".join(m[:400] for m in matches[:3])
                        break

            answer, err = call_openai(
                f"""당신은 한국 식품법 전문가입니다.
식품등의 표시기준, 원산지 표시요령, 기구용기 규격에 대해 조항을 정확히 인용하며 해석합니다.

참조 법령:
{kb_context if kb_context else "(PDF 미업로드 — 일반 지식으로 답변)"}""",
                question, 1500
            )
            if answer:
                st.markdown(answer)
            else:
                st.warning(f"⚠️ {err}")

render_chatbot("법령조회", "법령 검색 및 AI 해석 페이지.")
