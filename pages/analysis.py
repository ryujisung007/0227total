import streamlit as st
import pandas as pd
import plotly.express as px
import json
import requests
from datetime import datetime

# --- 초기 설정 및 전문가 페르소나 ---
# 20년차 시니어 AI 및 식품공학 코딩 전문가 모드
st.set_page_config(page_title="음료 개발 인사이트 시스템", layout="wide")

# API 설정 (환경 변수에서 제공됨)
const_api_key = ""

def call_openai_api(prompt, system_instruction):
    """
    OpenAI(Gemini-2.5-flash)를 호출하여 마케팅 전략 및 배합비를 생성합니다.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={const_api_key}"
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        }
    }
    
    # 지수 백오프를 적용한 리트라이 로직
    import time
    for i in range(5):
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "결과를 가져오지 못했습니다.")
            time.sleep(2**i)
        except Exception:
            time.sleep(2**i)
    return "연결 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

# --- 데이터 로드 및 전처리 ---
@st.cache_data
def load_data():
    try:
        # 업로드된 파일 경로 (Canvas 환경)
        df = pd.read_csv("I1250_음료조회_20260324_0345.csv")
        # 데이터 정제: 유통기한 등 텍스트 데이터 클리닝
        df['식품유형'] = df['식품유형'].fillna('미분류')
        df['업소명'] = df['업소명'].fillna('알수없음')
        return df
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return None

df = load_data()

if df is not None:
    st.title("🥤 음료 개발 및 시장 분석 인사이트 시스템")
    st.markdown(f"**기준일자:** {datetime.now().strftime('%Y-%m-%d')} | **분석 대상 제품 수:** {len(df):,}개")

    # 사이드바 필터
    st.sidebar.header("🔍 데이터 필터링")
    selected_type = st.sidebar.multiselect("식품유형 선택", options=sorted(df['식품유형'].unique()), default=[])
    selected_company = st.sidebar.multiselect("업소명 선택", options=sorted(df['업소명'].unique()[:50]), default=[])

    filtered_df = df.copy()
    if selected_type:
        filtered_df = filtered_df[filtered_df['식품유형'].isin(selected_type)]
    if selected_company:
        filtered_df = filtered_df[filtered_df['업소명'].isin(selected_company)]

    # 탭 구성
    tab1, tab2, tab3, tab4 = st.tabs(["📊 시장 현황", "📦 포장/유통 분석", "🔎 제품 검색", "💡 신제품 기획(AI)"])

    with tab1:
        st.subheader("음료 시장 분포 분석")
        col1, col2 = st.columns(2)
        
        with col1:
            type_counts = filtered_df['식품유형'].value_counts().reset_index()
            fig_type = px.pie(type_counts, values='count', names='식품유형', title="식품유형별 비중", hole=0.4)
            st.plotly_chart(fig_type, use_container_width=True)
            
        with col2:
            comp_counts = filtered_df['업소명'].value_counts().head(10).reset_index()
            fig_comp = px.bar(comp_counts, x='count', y='업소명', orientation='h', title="주요 제조사 TOP 10", color='count')
            st.plotly_chart(fig_comp, use_container_width=True)

    with tab2:
        st.subheader("포장재질 및 유통기한 연구")
        col3, col4 = st.columns(2)
        
        with col3:
            # 포장재질 분석 (데이터 내 '포장재질' 컬럼 활용)
            if '포장재질' in filtered_df.columns:
                pkg_counts = filtered_df['포장재질'].value_counts().head(10).reset_index()
                fig_pkg = px.bar(pkg_counts, x='포장재질', y='count', title="주요 포장재질 분포", color='포장재질')
                st.plotly_chart(fig_pkg, use_container_width=True)
            else:
                st.info("포장재질 데이터가 부족합니다.")

        with col4:
            # 성상/디스플레이 분석
            if 'DISPOS' in filtered_df.columns:
                st.write("**성상 및 제품 특징 요약**")
                st.dataframe(filtered_df[['제품명', 'DISPOS']].head(10), use_container_width=True)

    with tab3:
        st.subheader("세부 제품 데이터 조회")
        st.dataframe(filtered_df[['제품명', '식품유형', '업소명', '유통기한', '허가일자']], use_container_width=True)

    with tab4:
        st.subheader("🚀 AI 기반 신제품 개발 가이드")
        st.info("식품기술사/포장기술사 관점에서 시장 데이터를 바탕으로 신제품 컨셉과 표준 배합비를 제안합니다.")
        
        target_type = st.selectbox("기획할 음료 카테고리", options=df['식품유형'].unique())
        concept_keyword = st.text_input("강조하고 싶은 키워드 (예: 저당, 고단백, 천연향료, 친환경 패키징)")
        
        if st.button("신제품 기획서 생성"):
            with st.spinner("AI 전문가가 분석 중입니다..."):
                system_prompt = """
                당신은 20년 경력의 시니어 식품연구원 및 마케팅 전략가입니다. 
                사용자가 선택한 음료 카테고리에 대해 시장 경쟁력이 있는 신제품 기획서를 작성하세요.
                내용에는 다음이 포함되어야 합니다:
                1. 마케팅 전략: 타겟 고객 및 차별화 포인트
                2. 표준 배합비: 문헌 및 논문에 근거한 표준 비율 (표 형식, 사용 목적 명시)
                3. 배합 상세: 용도, 용법, 사용주의사항 포함
                4. 포장 제안: 식품유형에 적합한 보존성을 고려한 포장재질 추천
                """
                
                user_prompt = f"카테고리: {target_type}, 핵심 키워드: {concept_keyword}. 이 정보를 바탕으로 신제품 개발 기획서를 작성해줘."
                
                ai_response = call_openai_api(user_prompt, system_prompt)
                st.markdown(ai_response)

else:
    st.warning("데이터 파일이 올바른 경로에 있는지 확인해주세요.")
