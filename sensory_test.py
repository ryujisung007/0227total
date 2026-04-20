import streamlit as st
import pandas as pd
import numpy as np
import io from scipy
import stats from statsmodels.stats.multicomp
import pairwise_tukeyhsd
import matplotlib.pyplot as plt
import seaborn as sns

# 한글 설정
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(page_title="식품 R&D 관능분석 통합 솔루션", layout="wide")
st.title("🧪 식품 R&D 관능분석 통합 솔루션 (Total App)")

# 탭 구성
tabs = st.tabs(["📊 종합차이(평점법)", "🔄 차이식별(삼점/일-이점)", "🔢 순위법"])

# --- TAB 1: 종합차이식별 (기존 9점 척도 ANOVA) ---
with tabs[0]:
    st.header("종합적 차이 식별 (ANOVA)")
    st.info("9점 척도 등 계량 데이터를 분석하여 시료 간 유의차를 확인합니다.")
    
    # 템플릿 다운로드 로직 (생략 - 이전 코드와 동일)
    # ... (데이터 업로드 및 ANOVA 분석 로직 배치)

# --- TAB 2: 차이식별검사 (삼점검정, 일-이점검정) ---
with tabs[1]:
    st.header("차이 식별 검사 (Binomial Test)")
    
    col1, col2 = st.columns(2)
    with col1:
        test_type = st.radio("검사 종류 선택", ["삼점검정 (3-point)", "일-이점검정 (Duo-trio)"])
        total_panel = st.number_input("전체 패널 수", min_value=1, value=30)
        correct_ans = st.number_input("정답자(차이 인지) 수", min_value=0, max_value=total_panel, value=15)
        alpha = st.selectbox("유의수준(α)", [0.05, 0.01, 0.001])

    with col2:
        # 통계 계산: 기회확률(p0) 설정
        p0 = 1/3 if "삼점" in test_type else 1/2
        
        # 이항검정 수행 (단측검정: 우측)
        p_val = stats.binomtest(correct_ans, total_panel, p0, alternative='greater').pvalue
        
        st.subheader("분석 결과")
        st.write(f"기회 확률($P_0$): {p0:.2f}")
        st.write(f"유의 확률($P$-value): {p_val:.4f}")
        
        if p_val < alpha:
            st.success(f"결과: 두 시료 간에 유의미한 차이가 있습니다. (α={alpha})")
        else:
            st.warning("결과: 두 시료 간에 유의미한 차이가 없습니다.")

# --- TAB 3: 순위법 (Ranking Test) ---
with tabs[2]:
    st.header("순위법 분석 (Friedman Test)")
    st.markdown("여러 시료의 순위를 매긴 데이터를 분석합니다. (비모수 통계)")
    
    # 예시 데이터 입력
    st.write("데이터 예시 (행: 패널, 열: 시료별 순위)")
    rank_data = pd.DataFrame({
        '시료A': [1, 2, 1, 1, 2],
        '시료B': [2, 1, 2, 3, 1],
        '시료C': [3, 3, 3, 2, 3]
    })
    
    uploaded_rank = st.file_uploader("순위 데이터 업로드(CSV)", type="csv", key="rank_upload")
    
    target_df = pd.read_csv(uploaded_rank) if uploaded_rank else rank_data
    st.dataframe(target_df)
    
    # Friedman Test 수행
    try:
        f_stat, p_val_rank = stats.friedmanchisquare(*[target_df[col] for col in target_df.columns])
        
        st.subheader("통계 결과")
        st.write(f"Friedman 통계량: {f_stat:.4f}")
        st.write(f"P-값: {p_val_rank:.4f}")
        
        if p_val_rank < 0.05:
            st.success("결과: 시료 간 순위에 유의미한 차이가 있습니다.")
        else:
            st.info("결과: 시료 간 순위 차이가 유의미하지 않습니다.")
            
        # 순위 합계 시각화
        rank_sum = target_df.sum().sort_values()
        st.bar_chart(rank_sum)
        st.write("낮은 점수일수록 해당 특성이 강하거나 선호도가 높음을 의미합니다.")
    except Exception as e:
        st.error(f"분석 오류: {e}")
