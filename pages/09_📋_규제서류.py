"""📋 규제 & 서류"""
import streamlit as st
import pandas as pd

# page_config set in main app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *
st.markdown("# 📋 규제 검토 & 서류 작성 가이드")
st.markdown("---")

form = st.session_state.get("ai_formulation")

# 규제 로드맵
st.markdown("### 🗺️ 허가 절차 로드맵")
steps = [
    {"step":1,"icon":"📝","title":"품목제조보고서","desc":"제품명, 유형, 원재료, 유통기한 등","status":"작성 필요"},
    {"step":2,"icon":"🏷️","title":"식품유형 확인","desc":"식품공전 기준 유형 분류","status":"확인 필요"},
    {"step":3,"icon":"📊","title":"영양성분 분석","desc":"열량, 탄수화물, 단백질 등 9항목","status":"검사 필요"},
    {"step":4,"icon":"🧪","title":"자가품질검사","desc":"미생물, 이물, 잔류물질","status":"검사 필요"},
    {"step":5,"icon":"🏭","title":"HACCP 인증","desc":"위해요소중점관리기준","status":"선택적"},
    {"step":6,"icon":"✅","title":"제조 허가","desc":"관할 지자체 영업허가","status":"신고 필요"},
]
cols = st.columns(3)
for i, s in enumerate(steps):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"**{s['icon']} STEP {s['step']}. {s['title']}**")
            st.caption(s["desc"])
            st.info(s["status"])

# 품목제조보고서
st.markdown("---")
st.markdown("### 📝 품목제조보고서 (미리보기)")
report_data = {
    "제품명": form["productName"] if form else "(AI 카드에서 선택)",
    "식품유형": "혼합음료",
    "원재료명": ", ".join(i["name"] for i in form["ingredients"]) if form else "-",
    "내용량": form.get("totalVolume", "-") if form else "-",
    "유통기한": form.get("shelfLife", "-") if form else "-",
    "보관방법": "직사광선을 피하고 서늘한 곳에 보관",
    "포장재질": "PET / 알루미늄캔",
    "살균방법": "HTST (72°C, 15초) 또는 UHT (135°C, 2초)",
    "영양성분": f"열량 {form['calories']}kcal, Brix {form['brix']}°" if form else "-",
    "제조방법": "원료투입→용해→균질→살균→냉각→충전→검사→출하",
}
report_df = pd.DataFrame(list(report_data.items()), columns=["항목", "내용"])
st.dataframe(report_df, use_container_width=True, hide_index=True, height=400)

# 링크
st.markdown("---")
st.markdown("### 🔗 관련 사이트")
c1, c2, c3, c4 = st.columns(4)
c1.link_button("🔗 식품안전나라", "https://www.foodsafetykorea.go.kr", use_container_width=True)
c2.link_button("📖 식품공전", "https://various.foodsafetykorea.go.kr/fsd/#/ext/Document/FC", use_container_width=True)
c3.link_button("🏭 HACCP 정보", "https://www.haccp.or.kr", use_container_width=True)
c4.link_button("📊 FIS 통계", "https://www.atfis.or.kr", use_container_width=True)

# 학습 로드맵
st.markdown("---")
st.markdown("### 🎓 공정 디테일 학습 로드맵")
phases = [
    {"phase":"Phase 1","title":"배합비 확정","items":["원료 규격 확정","배합표 최종본","원가 계산"],"color":"blue"},
    {"phase":"Phase 2","title":"공정 설계","items":["CCP 선정","공정 흐름도","모니터링 계획"],"color":"violet"},
    {"phase":"Phase 3","title":"서류 작성","items":["품목제조보고서","자가품질검사 계획","HACCP 관리기준서"],"color":"orange"},
    {"phase":"Phase 4","title":"허가·인증","items":["관할 보건소 신고","영업허가 취득","HACCP 인증 (선택)"],"color":"green"},
]
cols = st.columns(4)
for i, p in enumerate(phases):
    with cols[i]:
        st.markdown(f"**{p['phase']}: {p['title']}**")
        for item in p["items"]:
            st.markdown(f"- {item}")

# ━━━ 챗봇 ━━━
render_chatbot("규제서류",
    page_context="품목제조보고서, 식품안전나라 연계, 규제 로드맵 페이지.",
    system_extra="품목제조보고, 식품위생법, 인허가 절차 관련 질문에 답변하세요.")
