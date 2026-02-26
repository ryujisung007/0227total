"""🏭 공정 & 리스크"""
import streamlit as st
import plotly.express as px
import pandas as pd

# page_config set in main app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *
st.markdown("# 🏭 식품 공정 설계 & 리스크 검토")

form = st.session_state.get("ai_formulation")
if form:
    st.caption(f'"{form["productName"]}" 기준 제조공정')
st.markdown("---")

# 공정 흐름도
st.markdown("### 📋 공정 흐름도 (클릭하여 상세 확인)")
step_names = [f"{s['icon']} {s['name']}" for s in PROCESS_STEPS]
selected_step = st.radio("공정 단계", step_names, horizontal=True)
idx = step_names.index(selected_step)
step = PROCESS_STEPS[idx]

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"### {step['icon']} STEP {step['id']}. {step['name']}")
    st.markdown("---")
    st.error(f"⚠️ **위해 요소:** {step['risk']}")
    st.success(f"✅ **관리 기준:** {step['control']}")

    level_map = {"high": ("🔴 높음", "error"), "mid": ("🟡 보통", "warning"), "low": ("🟢 낮음", "info")}
    lbl, typ = level_map[step["level"]]
    getattr(st, typ)(f"리스크 레벨: **{lbl}**")

with c2:
    st.markdown("### 📊 HACCP CCP 판정")
    ccp_data = []
    for s in PROCESS_STEPS:
        is_ccp = s["level"] == "high"
        ccp_data.append({
            "공정": f"{s['icon']} {s['name']}",
            "CCP": "✅ CCP" if is_ccp else "—",
            "위해요소": s["risk"],
            "리스크": {"high":"🔴높음","mid":"🟡보통","low":"🟢낮음"}[s["level"]],
        })
    st.dataframe(pd.DataFrame(ccp_data), use_container_width=True, hide_index=True)

# 리스크 매트릭스
st.markdown("---")
st.markdown("### 🎯 공정별 리스크 레벨 요약")
risk_df = pd.DataFrame([
    {"공정": s["name"], "레벨": {"high":3,"mid":2,"low":1}[s["level"]], "레벨명": {"high":"높음","mid":"보통","low":"낮음"}[s["level"]]}
    for s in PROCESS_STEPS
])
fig = px.bar(risk_df, x="공정", y="레벨", color="레벨명",
             color_discrete_map={"높음":"#EF4444","보통":"#F59E0B","낮음":"#10B981"},
             text="레벨명")
fig.update_layout(height=350, yaxis_title="리스크 레벨", showlegend=False)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
if st.button("📋 규제·서류 검토로 이동 →", use_container_width=True, type="primary"):
    st.switch_page("pages/6_📋_규제서류.py")

# ━━━ 챗봇 ━━━
render_chatbot("공정리스크",
    page_context="8단계 제조 공정 흐름, HACCP CCP, 리스크 매트릭스 페이지.",
    system_extra="공정 설계, HACCP 관리, 살균 조건, 위해분석 관련 질문에 답변하세요.")
