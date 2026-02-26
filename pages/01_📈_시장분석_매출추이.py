"""📈 매출 추이 분석"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# page_config set in main app.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *
st.markdown("# 📈 음료 세부유형별 매출 추이")
st.markdown("점선 = 전체 유형 평균 매출 | 매출액 높은 순 정렬 | 단위: 백만원")
st.markdown("---")

sorted_cats = get_sorted_categories()

# 데이터 가공
rows = []
for yr in YEARS:
    row = {"연도": yr}
    vals = []
    for cat in sorted_cats:
        v = SALES_DATA[cat][yr]
        row[cat] = v
        vals.append(v)
    row["평균"] = sum(vals) / len(vals)
    rows.append(row)
df = pd.DataFrame(rows)

# ━━━ 누적 바 + 평균 라인 ━━━
fig = go.Figure()
for i, cat in enumerate(sorted_cats):
    fig.add_trace(go.Bar(name=cat, x=df["연도"], y=df[cat], marker_color=COLORS[i % len(COLORS)]))
fig.add_trace(go.Scatter(
    name="⎯ 평균 매출", x=df["연도"], y=df["평균"], mode="lines+markers",
    line=dict(color="#FBBF24", width=3, dash="dash"), marker=dict(size=8),
))
fig.update_layout(barmode="stack", height=480, legend=dict(orientation="h", y=-0.15),
                  yaxis_title="매출액 (백만원)", xaxis_title="연도")
st.plotly_chart(fig, use_container_width=True)

# ━━━ 개별 라인 차트 ━━━
st.markdown("### 📊 유형별 추이 (개별 라인)")
sel = st.multiselect("유형 선택", sorted_cats, default=sorted_cats[:5])
if sel:
    fig2 = go.Figure()
    avg_2024 = sum(SALES_DATA[c]["2024"] for c in sorted_cats) / len(sorted_cats)
    fig2.add_hline(y=avg_2024, line_dash="dot", line_color="#FBBF24",
                   annotation_text=f"평균 {avg_2024/10000:.0f}만", annotation_position="top right")
    for i, cat in enumerate(sel):
        vals = [SALES_DATA[cat][yr] for yr in YEARS]
        fig2.add_trace(go.Scatter(x=YEARS, y=vals, name=cat, mode="lines+markers",
                                  line=dict(color=COLORS[sorted_cats.index(cat) % len(COLORS)], width=2.5)))
    fig2.update_layout(height=400, yaxis_title="매출액 (백만원)")
    st.plotly_chart(fig2, use_container_width=True)

# ━━━ 순위 카드 ━━━
st.markdown("### 🏆 2024 매출 순위")
cols = st.columns(5)
for i, cat in enumerate(sorted_cats[:10]):
    v24 = SALES_DATA[cat]["2024"]
    v23 = SALES_DATA[cat]["2023"]
    g = (v24 - v23) / v23 * 100
    with cols[i % 5]:
        st.metric(f"#{i+1} {cat}", f"{v24/10000:.0f}만", f"{g:+.1f}%")

# CSV 다운로드
st.markdown("---")
csv = df.to_csv(index=False).encode("utf-8-sig")
st.download_button("📥 매출 데이터 CSV 다운로드", csv, "음료매출추이.csv", "text/csv")

# ━━━ 챗봇 ━━━
render_chatbot("매출추이",
    page_context="음료 카테고리별 매출 추이 분석 페이지. 2019-2024년 10개 카테고리 데이터.",
    system_extra="매출 트렌드, 성장률, 카테고리 순위 관련 질문에 답변하세요.")
