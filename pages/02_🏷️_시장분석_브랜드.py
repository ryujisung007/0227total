"""🏷️ 브랜드 분석"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
# Streamlit Cloud 호환 경로
PAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGE_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *

# page_config set in main app.py
st.markdown("# 🏷️ 브랜드별 연도별 매출 분석")
st.markdown("---")

# 유형 선택
cat = st.selectbox("음료 유형 선택", list(BRAND_DATA.keys()))
brands = BRAND_DATA[cat]
brands_sorted = sorted(brands, key=lambda b: b["2024"], reverse=True)
brand_names = [b["brand"] for b in brands_sorted]

# 브랜드 멀티셀렉 (매출순)
sel = st.multiselect("브랜드 선택 (매출 높은 순)", brand_names, default=brand_names[:3],
                     help="복수 선택하여 비교 가능")

if sel:
    # 라인 차트
    fig = go.Figure()
    for b in brands_sorted:
        if b["brand"] in sel:
            vals = [b[yr] for yr in YEARS]
            idx = brand_names.index(b["brand"])
            fig.add_trace(go.Scatter(x=YEARS, y=vals, name=b["brand"], mode="lines+markers",
                                     line=dict(color=COLORS[idx % len(COLORS)], width=3)))
    fig.update_layout(height=420, yaxis_title="매출액 (백만원)", xaxis_title="연도")
    st.plotly_chart(fig, use_container_width=True)

    # 점유율 & 성장률
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### 🥧 2024 점유율")
        pie_data = pd.DataFrame([{"브랜드": b["brand"], "매출": b["2024"]} for b in brands_sorted])
        fig_pie = px.pie(pie_data, values="매출", names="브랜드", hole=0.4,
                         color_discrete_sequence=COLORS)
        fig_pie.update_layout(height=350)
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        st.markdown("#### 📊 YoY 성장률")
        growth_data = []
        for b in brands_sorted:
            g = (b["2024"] - b["2023"]) / b["2023"] * 100
            growth_data.append({"브랜드": b["brand"], "성장률(%)": round(g, 1), "매출24": b["2024"]})
        gdf = pd.DataFrame(growth_data)
        fig_g = px.bar(gdf, x="브랜드", y="성장률(%)", color="성장률(%)",
                       color_continuous_scale="RdYlGn", text="성장률(%)")
        fig_g.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
        fig_g.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig_g, use_container_width=True)

    # 상세 테이블
    st.markdown("#### 📋 상세 데이터")
    table_data = []
    for b in brands_sorted:
        row = {"브랜드": b["brand"]}
        for yr in YEARS:
            row[yr] = f"{b[yr]:,}"
        row["성장률"] = f"{(b['2024']-b['2023'])/b['2023']*100:+.1f}%"
        table_data.append(row)
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

# ━━━ 챗봇 ━━━
render_chatbot("브랜드분석",
    page_context="음료 브랜드별 매출·점유율 분석 페이지. 탄산/커피/에너지/생수/유산균 5개 카테고리.",
    system_extra="브랜드 경쟁, 시장 점유율, 마케팅 전략 관련 질문에 답변하세요.")
