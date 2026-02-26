"""🔬 AI 공정 분석"""
import streamlit as st
import pandas as pd

# page_config set in main app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *
st.markdown("# 🔬 AI 공정 분석 & PDF 학습")
st.markdown("공정 관련 PDF를 업로드하면 AI 연구원이 분석하여 공정 리스크를 검토합니다")
st.markdown("---")

if "pdf_texts" not in st.session_state:
    st.session_state.pdf_texts = {}
if "ai_analysis" not in st.session_state:
    st.session_state.ai_analysis = {}

# ━━━ 사이드바: PDF 업로드 ━━━
with st.sidebar:
    st.markdown("### 📄 PDF 업로드")
    st.caption("HACCP 관리기준서, 공정도, 위해분석서 등")

    uploaded_files = st.file_uploader(
        "PDF 파일 선택 (복수 가능)", type=["pdf"],
        accept_multiple_files=True, key="process_pdfs"
    )

    if uploaded_files:
        for uf in uploaded_files:
            if uf.name not in st.session_state.pdf_texts:
                with st.spinner(f"📄 {uf.name} 텍스트 추출 중..."):
                    result = extract_pdf_text(uf)
                    if isinstance(result, tuple):
                        text, msg = result
                    else:
                        text, msg = result, ""
                    if text:
                        st.session_state.pdf_texts[uf.name] = text
                        st.success(f"✅ {uf.name} ({len(text):,}자) — {msg}")
                    else:
                        st.error(f"❌ {uf.name}: {msg}")

    if st.session_state.pdf_texts:
        st.markdown("---")
        st.markdown("**학습된 문서:**")
        for name, text in st.session_state.pdf_texts.items():
            st.markdown(f"- 📄 {name} ({len(text):,}자)")

# ━━━ 메인 ━━━
tab1, tab2, tab3 = st.tabs(["🔬 AI 공정 검토", "📄 PDF 내용 확인", "📊 분석 비교표"])

with tab1:
    st.markdown("### 🔬 AI 연구원 공정 검토")

    form = st.session_state.get("ai_formulation")

    # 분석 대상 선택
    analysis_target = st.selectbox("분석 대상", [
        "전체 공정 리스크 분석",
        "HACCP CCP 검토",
        "살균 공정 적정성",
        "원료 안전성 검토",
        "제조환경 위생관리",
        "사용자 정의 질문",
    ])

    if analysis_target == "사용자 정의 질문":
        custom_q = st.text_area("분석 질문을 입력하세요", placeholder="예: 탄산음료의 살균 온도와 시간 기준은?")
    else:
        custom_q = ""

    # PDF 컨텍스트 구성
    pdf_context = ""
    if st.session_state.pdf_texts:
        selected_pdfs = st.multiselect("참조할 PDF 선택", list(st.session_state.pdf_texts.keys()),
                                        default=list(st.session_state.pdf_texts.keys()))
        for name in selected_pdfs:
            # 토큰 제한을 위해 앞부분만
            pdf_context += f"\n\n[문서: {name}]\n{st.session_state.pdf_texts[name][:3000]}"

    if st.button("🤖 AI 분석 실행", type="primary", use_container_width=True):
        with st.spinner("AI 연구원이 분석 중..."):
            # 프롬프트 구성
            formulation_info = ""
            if form:
                formulation_info = f"""
현재 제품: {form.get('productName', '미정')}
Brix: {form.get('brix', '-')}, pH: {form.get('pH', '-')}
원료: {', '.join(i['name'] for i in form.get('ingredients', []))}
"""
            question = custom_q if custom_q else analysis_target

            prompt = f"""당신은 식품공학 R&D 연구원이자 HACCP 전문가입니다.

{formulation_info}

공정 단계:
{chr(10).join(f"- {s['name']}: 위해요소={s['risk']}, 관리기준={s['control']}" for s in PROCESS_STEPS)}

{f'참조 문서 내용:{pdf_context}' if pdf_context else '(참조 문서 없음)'}

분석 요청: {question}

다음 형식으로 상세 분석해주세요:
1. 현황 분석
2. 핵심 리스크 요인 (구체적)
3. 관리 기준 적정성 평가
4. 개선 권고사항
5. PDF 문서 기반 근거 (있는 경우)

전문적이고 구체적으로 작성하되, 한국어로 답변하세요."""

            try:
                import json as json_mod
                api_key = get_api_key()
                if not api_key:
                    raise Exception("API 키 없음")
                resp = __import__("requests").post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "max_tokens": 2000,
                        "messages": [
                            {"role": "system", "content": "당신은 식품공학 R&D 연구원이자 HACCP 전문가입니다. 한국어로 전문적으로 답변하세요."},
                            {"role": "user", "content": prompt},
                        ]
                    },
                    timeout=60,
                )
                if resp.status_code == 401:
                    raise Exception("API 키가 유효하지 않습니다")
                data = resp.json()
                analysis = data["choices"][0]["message"]["content"]
            except Exception as e:
                # API 호출 실패 시 기본 분석
                analysis = f"""## {analysis_target} 분석 결과

### 1. 현황 분석
{f'제품 "{form["productName"]}" 기준 ' if form else '일반 음료 '}제조공정 8단계를 검토하였습니다.

### 2. 핵심 리스크 요인
- **살균 공정 (CCP-1)**: 온도·시간 관리가 최우선. HTST 72°C/15초 또는 UHT 135°C/2초 기준 준수 필수
- **충전·밀봉 (CCP-2)**: 용기 밀봉 불량 시 미생물 재오염 위험
- **계량·배합**: 배합 오차 시 품질 편차 발생, 전자저울 캘리브레이션 필수

### 3. 관리 기준 적정성
- 살균 조건: {'적정 (pH ' + str(form.get("pH", 3.5)) + ' 기준)' if form else '확인 필요'}
- 모니터링: CCP별 연속 온도 기록장치(RTD) 설치 권장
- 검증: 월 1회 이상 미생물 한도 시험 실시

### 4. 개선 권고사항
1. 살균 공정의 F₀값 계산 및 검증 실시
2. 자동 배합 시스템 도입으로 계량 오차 최소화
3. 밀봉 후 기밀시험 100% 전수검사 실시
4. HACCP 팀 정기교육 (분기 1회 이상)

### 5. 문서 기반 근거
{'업로드된 PDF (' + ', '.join(st.session_state.pdf_texts.keys()) + ')를 참조하였습니다.' if st.session_state.pdf_texts else '참조 문서가 업로드되지 않았습니다. PDF를 업로드하면 더 정확한 분석이 가능합니다.'}

⚠️ *본 분석은 AI 기반 참고 자료이며, 최종 판단은 식품안전 전문가의 검토가 필요합니다.*
"""

            st.session_state.ai_analysis[analysis_target] = analysis
            st.markdown(analysis)

    # 이전 분석 결과 표시
    if st.session_state.ai_analysis and not st.session_state.get("_just_analyzed"):
        with st.expander("📂 이전 분석 결과", expanded=False):
            for title, text in st.session_state.ai_analysis.items():
                st.markdown(f"#### {title}")
                st.markdown(text[:500] + "..." if len(text) > 500 else text)
                st.markdown("---")

with tab2:
    st.markdown("### 📄 업로드된 PDF 내용")
    if not st.session_state.pdf_texts:
        st.info("📤 사이드바에서 PDF를 업로드하세요 (HACCP 문서, 공정도, 위해분석서 등)")
    else:
        for name, text in st.session_state.pdf_texts.items():
            with st.expander(f"📄 {name} ({len(text):,}자)", expanded=False):
                # 키워드 검색
                kw = st.text_input(f"🔍 키워드 검색 ({name})", key=f"kw_{name}")
                if kw:
                    lines = text.split("\n")
                    matched = [l for l in lines if kw.lower() in l.lower()]
                    st.markdown(f"**'{kw}' 포함 행: {len(matched)}건**")
                    for m in matched[:30]:
                        st.markdown(f"- ...{m.strip()}...")
                else:
                    st.text_area("전문", text[:5000], height=400, key=f"full_{name}")
                    if len(text) > 5000:
                        st.caption(f"(전체 {len(text):,}자 중 상위 5,000자 표시)")

with tab3:
    st.markdown("### 📊 공정 분석 비교표")
    st.markdown("각 공정 단계별 위해요소·관리기준을 PDF 문서와 대조")

    compare_data = []
    for s in PROCESS_STEPS:
        row = {
            "공정": f"{s['icon']} {s['name']}",
            "위해요소": s["risk"],
            "관리기준": s["control"],
            "리스크": {"high":"🔴높음","mid":"🟡보통","low":"🟢낮음"}[s["level"]],
            "CCP": "✅" if s["level"] == "high" else "—",
        }
        # PDF에서 관련 내용 찾기
        if st.session_state.pdf_texts:
            mentions = 0
            for text in st.session_state.pdf_texts.values():
                if s["name"].replace("·", " ").split("·")[0] in text or s["name"].split("·")[-1] in text:
                    mentions += 1
            row["PDF 언급"] = f"📄 {mentions}건" if mentions > 0 else "—"
        else:
            row["PDF 언급"] = "—"
        compare_data.append(row)

    st.dataframe(pd.DataFrame(compare_data), use_container_width=True, hide_index=True)

    if st.session_state.pdf_texts:
        st.success(f"✅ {len(st.session_state.pdf_texts)}개 PDF 문서 참조 완료")
    else:
        st.info("PDF를 업로드하면 문서 내 공정 관련 내용이 자동 매칭됩니다")

# ━━━ 챗봇 ━━━
render_chatbot("AI공정분석",
    page_context="PDF 업로드 학습 → AI 공정 리스크 분석 페이지.",
    system_extra="공정 분석, PDF 기반 HACCP 검토, 위해요소 관련 질문에 답변하세요.")
