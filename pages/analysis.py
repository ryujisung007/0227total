import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
import base64

# --- [Gemini API 설정] ---
# 사용자 지시사항에 따른 API 호출 설정
apiKey = "" # 환경변수에서 자동으로 주입됨

def get_gemini_response(user_query, system_prompt):
    """Gemini 2.5 Flash 모델을 사용하여 AI 인사이트 및 배합비 생성"""
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={apiKey}"
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }
    
    # 지수 백오프 적용된 호출 로직
    for delay in [1, 2, 4, 8, 16]:
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "")
        except:
            import time
            time.sleep(delay)
    return "AI 분석 서비스 일시적인 오류입니다. 잠시 후 다시 시도해주세요."

# --- [1] 페이지 설정 및 테마 ---
st.set_page_config(
    page_title="음료 R&D 통합 분석 시스템", 
    page_icon="🧪",
    layout="wide"
)

# --- [2] 데이터 로드 로직 (Senior Level Path Management) ---
@st.cache_data
def load_beverage_data(target_filename):
    possible_paths = [
        target_filename,
        os.path.join("/content", target_filename),
        os.path.join(".", target_filename)
    ]
    
    final_path = None
    for path in possible_paths:
        if os.path.exists(path):
            final_path = path
            break
            
    if final_path:
        try:
            # [MODIFIED] 컬럼명 공백 제거 및 인코딩 최적화
            df = pd.read_csv(final_path, encoding='utf-8-sig')
            df.columns = [col.strip() for col in df.columns]
            return df, None
        except UnicodeDecodeError:
            df = pd.read_csv(final_path, encoding='cp949')
            df.columns = [col.strip() for col in df.columns]
            return df, None
        except Exception as e:
            return None, f"데이터를 해석할 수 없습니다: {str(e)}"
    else:
        return None, "File Not Found"

# --- [3] 메인 애플리케이션 시작 ---
def main():
    st.title("🥤 음료 품목제조 데이터 분석 및 AI R&D 지원 시스템")
    
    target_file = "I1250_음료조회_20260324_0345.csv"
    df, error_msg = load_beverage_data(target_file)
    
    # 파일 부재 시 업로더 UI
    if df is None:
        st.info(f"💡 시스템에서 '{target_file}'를 탐색 중입니다.")
        uploaded_file = st.file_uploader("분석할 음료 데이터(CSV)를 업로드하세요", type=['csv'])
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
            except:
                df = pd.read_csv(uploaded_file, encoding='cp949')
            df.columns = [col.strip() for col in df.columns]
            st.success("데이터 로드 완료!")
        else:
            st.stop()

    # --- [4] 데이터 전처리 (Robust Logic) ---
    df['허가일자'] = pd.to_datetime(df['허가일자'], format='%Y%m%d', errors='coerce')
    # 유통기한 숫자 추출 로직 강화
    df['유통기한_추출'] = df['유통기한'].astype(str).str.extract(r'(\d+)').astype(float)
    
    # --- [5] 멀티 탭 구성 ---
    tab1, tab2 = st.tabs(["📊 시장 점유율 및 트렌드 분석", "🤖 AI 신제품 기획 & 배합비"])

    with tab1:
        # 사이드바 필터
        st.sidebar.header("🔍 분석 필터")
        all_companies = sorted(df['업소명'].unique())
        selected_companies = st.sidebar.multiselect("분석 대상 업체", all_companies)
        
        all_types = sorted(df['식품유형'].unique())
        selected_types = st.sidebar.multiselect("식품유형 필터", all_types, default=all_types[:5])
        
        # 필터 적용
        filtered_df = df.copy()
        if selected_companies:
            filtered_df = filtered_df[filtered_df['업소명'].isin(selected_companies)]
        if selected_types:
            filtered_df = filtered_df[filtered_df['식품유형'].isin(selected_types)]

        # 주요 지표 (SyntaxError 방지를 위해 f-string 로직 분리)
        total_items = len(filtered_df)
        total_comps = filtered_df['업소명'].nunique()
        avg_shelf = filtered_df['유통기한_추출'].mean()
        # 최근 30일 데이터 필터링
        one_month_ago = datetime.now() - timedelta(days=30)
        recent_reg = len(filtered_df[filtered_df['허가일자'] >= one_month_ago])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 품목 수", f"{total_items:,}건")
        m2.metric("참여 업체", f"{total_comps:,}개")
        m3.metric("평균 유통기한", f"{avg_shelf:.1f}개월" if not pd.isna(avg_shelf) else "N/A")
        m4.metric("최근 30일 신규", f"{recent_reg:,}건")

        st.divider()

        # 시각화 영역
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📊 식품 유형별 비중")
            type_counts = filtered_df['식품유형'].value_counts().reset_index()
            fig_pie = px.pie(type_counts, values='count', names='식품유형', hole=0.3,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with c2:
            st.subheader("🏢 업체별 품목 수 (Top 10)")
            comp_counts = filtered_df['업소명'].value_counts().head(10).reset_index()
            fig_bar = px.bar(comp_counts, x='count', y='업소명', orientation='h',
                             color='count', color_continuous_scale='Blues')
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("📑 제품 상세 명세 데이터")
        search_kw = st.text_input("제품명 또는 특징 키워드 검색", placeholder="예: 무설탕, 멸균, 제로...")
        if search_kw:
            display_df = filtered_df[filtered_df['제품명'].str.contains(search_kw, na=False)]
        else:
            display_df = filtered_df
        
        st.dataframe(display_df[['제품명', '업소명', '식품유형', '유통기한', '허가일자', '포장재질', 'DISPOS']], 
                     use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("🧪 AI 신제품 기획 및 배합비 생성")
        st.markdown("데이터상의 트렌드를 반영하여 새로운 식품 배합비와 마케팅 전략을 생성합니다.")
        
        col_in1, col_in2 = st.columns(2)
        with col_in1:
            target_type = st.selectbox("기획할 식품유형", all_types)
            concept = st.text_input("제품 컨셉", placeholder="예: 고단백 저칼로리 초코 음료")
        with col_in2:
            target_age = st.selectbox("주 타겟층", ["MZ세대", "영유아", "고령친화", "운동선수", "일반인"])
            packaging = st.selectbox("희망 용기", ["PET", "알루미늄 캔", "멸균팩(Tetra)", "유리병"])

        if st.button("🚀 AI R&D 리포트 생성"):
            with st.spinner("전문가 AI가 배합비와 전략을 도출 중입니다..."):
                system_prompt = f"""
                당신은 20년 경력의 식품연구원 및 식품기술사입니다.
                사용자가 요청한 컨셉에 대해 다음 내용을 포함한 전문적인 리포트를 작성하세요.
                1. 마케팅 전략 (SWOT 분석 포함)
                2. 표준 식품 배합비 (표 형식: 원료명, 배합비(%), 사용 목적, 용도/용법, 주의사항 포함)
                3. 포장 및 유통기한 설계 제언 (포장기술사 관점)
                모든 배합비는 문헌 및 논문 근거를 바탕으로 하며 전문 용어를 사용하세요.
                """
                user_query = f"유형: {target_type}, 컨셉: {concept}, 타겟: {target_age}, 포장: {packaging}에 대한 신제품 기획안 작성"
                
                ai_report = get_gemini_response(user_query, system_prompt)
                st.markdown(ai_report)
                
                # 결과 다운로드 기능
                st.download_button("결과 리포트 다운로드(TXT)", ai_report, file_name=f"RND_Report_{datetime.now().strftime('%Y%m%d')}.txt")

    # --- [6] 연구원 인사이트 사이드바 ---
    st.sidebar.divider()
    st.sidebar.markdown("### 💡 R&D Insight")
    if not filtered_df.empty:
        # [MODIFIED] 통계 기반 제언
        mode_pkg = filtered_df['포장재질'].mode()
        pkg_text = mode_pkg[0] if not mode_pkg.empty else "데이터 부족"
        st.sidebar.warning(f"""
        **포장 기술 검토:** 선택된 카테고리에서 가장 빈번한 포장재는 **{pkg_text}**입니다. 
        신제품의 유통기한을 {avg_shelf:.1f}개월 이상 확보하려면 산소차단성(OTR) 및 광차단 성능을 재점검하십시오.
        """)

if __name__ == "__main__":
    main()
