"""
식품 R&D 관능분석 통합 솔루션 (Full Package)
=============================================
- Tab 1: 종합차이 (ANOVA + Tukey HSD)
- Tab 2: 차이식별 (삼점/일-이점 Binomial Test)
- Tab 3: 순위법 (Friedman + Wilcoxon pairwise)
- Tab 4: 패널 신뢰도 (ICC, CV, 개별 F-value)
- Tab 5: 블라인드 코드 생성기 (3자리 + 라틴방격)
- Tab 6: 통합 리포트 + Claude AI 해석

requirements.txt:
    streamlit>=1.28
    pandas
    numpy
    scipy
    statsmodels
    matplotlib
    seaborn
    plotly
    requests
    openpyxl
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import random
import datetime
import base64
import requests
from scipy import stats
from scipy.stats import f_oneway, binomtest, friedmanchisquare, wilcoxon
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
import matplotlib.pyplot as plt
import matplotlib
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go

# ============================================================================
# 초기 설정
# ============================================================================

# 한글 폰트 (Streamlit Cloud 호환)
for font in ['Malgun Gothic', 'AppleGothic', 'NanumGothic', 'DejaVu Sans']:
    if font in [f.name for f in matplotlib.font_manager.fontManager.ttflist]:
        plt.rcParams['font.family'] = font
        break
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(
    page_title="식품 R&D 관능분석 통합 솔루션",
    layout="wide",
    page_icon="🧪"
)

# Session state 초기화
for key, default in [
    ('results', {}),
    ('api_key', ''),
    ('claude_model', 'claude-sonnet-4-5'),
    ('interpretations', {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ============================================================================
# 공통 유틸리티
# ============================================================================

def call_claude_api(prompt: str, api_key: str, model: str = "claude-sonnet-4-5") -> str:
    """Claude API 직접 호출 (REST)"""
    if not api_key:
        return "⚠️ 사이드바에서 Claude API 키를 입력하세요."
    
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    system_msg = (
        "당신은 식품 R&D 전문 통계 컨설턴트입니다. "
        "관능검사 분석 결과를 식품개발자 관점에서 명확하고 실무적으로 해석해주세요. "
        "통계적 유의성뿐 아니라 제품개발에 주는 함의(차별화 포인트, 후속 실험 제안 등)를 포함하세요. "
        "답변은 한국어로, 마크다운 구조(### 헤딩, 불릿)를 활용해 작성하세요."
    )
    payload = {
        "model": model,
        "max_tokens": 2000,
        "system": system_msg,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    except requests.exceptions.HTTPError as e:
        return f"❌ API 오류 ({r.status_code}): {r.text[:300]}"
    except Exception as e:
        return f"❌ 호출 오류: {str(e)}"


def df_to_csv_download(df: pd.DataFrame, filename: str, label: str = "CSV 다운로드"):
    """DataFrame → CSV 다운로드 버튼"""
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(label, data=csv, file_name=filename, mime="text/csv")


def fig_to_base64(fig) -> str:
    """Matplotlib figure → base64 (HTML 리포트용)"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def generate_html_report(project, author, sections, results, interpretations):
    """통합 HTML 리포트 생성"""
    import re
    
    def md_to_html(text):
        text = re.sub(r'### (.+)', r'<h4>\1</h4>', text)
        text = re.sub(r'## (.+)', r'<h3>\1</h3>', text)
        text = re.sub(r'# (.+)', r'<h2>\1</h2>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = text.replace('\n\n', '</p><p>')
        return f'<p>{text}</p>'
    
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{project} - 관능분석 리포트</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 1100px; 
          margin: 40px auto; padding: 20px; color: #1e293b; line-height: 1.7; }}
  .header {{ background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); 
            color: white; padding: 40px; border-radius: 12px; }}
  .header h1 {{ margin: 0; font-size: 32px; }}
  .header p {{ opacity: 0.9; margin: 5px 0; }}
  .section {{ background: #f8fafc; border-left: 4px solid #0ea5e9;
             padding: 25px; margin: 25px 0; border-radius: 8px; }}
  .section h2 {{ color: #0c4a6e; margin-top: 0; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); 
                  gap: 15px; margin: 15px 0; }}
  .metric {{ background: white; padding: 15px; border-radius: 8px; 
             box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .metric .label {{ color: #64748b; font-size: 13px; }}
  .metric .value {{ font-size: 24px; font-weight: bold; color: #0ea5e9; }}
  table {{ width: 100%; border-collapse: collapse; margin: 15px 0; 
           background: white; border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
  th {{ background: #0ea5e9; color: white; }}
  tr:hover {{ background: #f1f5f9; }}
  .ai-box {{ background: #fef3c7; border-left: 4px solid #f59e0b; 
            padding: 20px; border-radius: 8px; margin: 15px 0; }}
  .ai-box h4 {{ color: #92400e; margin-top: 0; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px; 
           font-size: 12px; font-weight: bold; }}
  .badge.sig {{ background: #dcfce7; color: #166534; }}
  .badge.nosig {{ background: #fee2e2; color: #991b1b; }}
  footer {{ text-align: center; color: #94a3b8; padding: 20px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🧪 {project}</h1>
  <p>관능분석 통합 리포트</p>
  <p>작성자: {author}  |  생성일: {datetime.date.today()}</p>
</div>
"""
    
    # ANOVA
    if 'anova' in sections and 'anova' in results:
        r = results['anova']
        sig = r['p_sample'] < r['alpha']
        html += f"""
<div class="section">
  <h2>📊 종합적 차이 식별 (ANOVA)</h2>
  <p><strong>분석 유형:</strong> {r['model_type']}</p>
  <div class="metric-grid">
    <div class="metric"><div class="label">F-value</div><div class="value">{r['f_sample']:.3f}</div></div>
    <div class="metric"><div class="label">p-value</div><div class="value">{r['p_sample']:.4f}</div></div>
    <div class="metric"><div class="label">유의수준 α</div><div class="value">{r['alpha']}</div></div>
    <div class="metric"><div class="label">결과</div><div class="value"><span class="badge {'sig' if sig else 'nosig'}">{'유의' if sig else '비유의'}</span></div></div>
  </div>
  <h4>ANOVA 표</h4>
  {r['anova_table'].to_html(float_format='%.4f')}
  <h4>Tukey HSD 사후검정</h4>
  {r['tukey'].to_html(index=False, float_format='%.4f')}
  <h4>시료별 평균</h4>
  {r['summary'].to_html(index=False, float_format='%.3f')}
"""
        if 'anova' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["anova"])}</div>'
        html += "</div>"
    
    # Discrimination
    if 'discrimination' in sections and 'discrimination' in results:
        r = results['discrimination']
        html += f"""
<div class="section">
  <h2>🔄 차이 식별 검사</h2>
  <p><strong>검사 종류:</strong> {r['test_type']}</p>
  <div class="metric-grid">
    <div class="metric"><div class="label">패널 수</div><div class="value">{r['n']}</div></div>
    <div class="metric"><div class="label">정답자</div><div class="value">{r['correct']}</div></div>
    <div class="metric"><div class="label">p-value</div><div class="value">{r['p_value']:.4f}</div></div>
    <div class="metric"><div class="label">최소 정답자수</div><div class="value">{r['min_correct']}</div></div>
    <div class="metric"><div class="label">결과</div><div class="value"><span class="badge {'sig' if r['significant'] else 'nosig'}">{'유의' if r['significant'] else '비유의'}</span></div></div>
  </div>
"""
        if 'discrimination' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["discrimination"])}</div>'
        html += "</div>"
    
    # Friedman
    if 'friedman' in sections and 'friedman' in results:
        r = results['friedman']
        sig = r['p_value'] < 0.05
        html += f"""
<div class="section">
  <h2>🔢 순위법 (Friedman)</h2>
  <div class="metric-grid">
    <div class="metric"><div class="label">패널 수</div><div class="value">{r['n_panel']}</div></div>
    <div class="metric"><div class="label">시료 수</div><div class="value">{r['n_samples']}</div></div>
    <div class="metric"><div class="label">χ²</div><div class="value">{r['f_stat']:.3f}</div></div>
    <div class="metric"><div class="label">p-value</div><div class="value">{r['p_value']:.4f}</div></div>
    <div class="metric"><div class="label">결과</div><div class="value"><span class="badge {'sig' if sig else 'nosig'}">{'유의' if sig else '비유의'}</span></div></div>
  </div>
  <h4>순위합</h4>
  {r['rank_sum'].to_html(index=False)}
"""
        if r['pairs'] is not None:
            html += f"<h4>Wilcoxon 쌍별 비교</h4>{r['pairs'].to_html(index=False, float_format='%.4f')}"
        if 'friedman' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["friedman"])}</div>'
        html += "</div>"
    
    # Reliability
    if 'reliability' in sections and 'reliability' in results:
        r = results['reliability']
        html += f"""
<div class="section">
  <h2>👥 패널 신뢰도</h2>
  <div class="metric-grid">
    <div class="metric"><div class="label">ICC</div><div class="value">{r['icc']:.3f}</div></div>
    <div class="metric"><div class="label">우수 패널</div><div class="value">{(r['discrim_df']['p-value']<0.05).sum()}/{len(r['discrim_df'])}</div></div>
    <div class="metric"><div class="label">평균 CV</div><div class="value">{r['cv_df']['평균 CV(%)'].mean():.1f}%</div></div>
  </div>
  <h4>패널별 식별력</h4>
  {r['discrim_df'].to_html(index=False, float_format='%.4f')}
  <h4>패널별 일관성 (CV)</h4>
  {r['cv_df'].to_html(index=False, float_format='%.2f')}
"""
        if 'reliability' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["reliability"])}</div>'
        html += "</div>"
    
    # Blind codes
    if 'blind_codes' in sections and 'blind_codes' in results:
        r = results['blind_codes']
        html += f"""
<div class="section">
  <h2>🎲 블라인드 코드</h2>
  <div class="metric-grid">
    <div class="metric"><div class="label">시료 수</div><div class="value">{r['n_samples']}</div></div>
    <div class="metric"><div class="label">패널 수</div><div class="value">{r['n_panelists']}</div></div>
    <div class="metric"><div class="label">제시순서 균형화</div><div class="value">{'✓' if r['balanced'] else '✗'}</div></div>
  </div>
  <h4>전체 코드 리스트 (상위 20개)</h4>
  {r['code_df'].head(20).to_html(index=False)}
</div>
"""
    
    html += """
<footer>
  <p>© Sweet Lab · Natural Lab R&D · Generated with Claude AI</p>
</footer>
</body></html>
"""
    return html


# ============================================================================
# 사이드바: 공통 설정
# ============================================================================

with st.sidebar:
    st.title("⚙️ 설정")
    
    st.subheader("🤖 Claude AI 해석")
    st.session_state.api_key = st.text_input(
        "Anthropic API Key",
        value=st.session_state.api_key,
        type="password",
        help="결과 해석 시에만 사용됩니다. 공백이면 해석 기능 비활성화."
    )
    st.session_state.claude_model = st.selectbox(
        "모델",
        ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"],
        index=0
    )
    
    st.divider()
    st.subheader("🎨 시각화")
    color_palette = st.selectbox("컬러 팔레트", ["Set2", "Pastel1", "Spectral", "viridis"])
    
    st.divider()
    st.caption("ℹ️ 모든 분석 결과는 세션에 저장되며, Tab 6에서 통합 리포트로 다운받을 수 있습니다.")


# ============================================================================
# 메인 타이틀
# ============================================================================

st.title("🧪 식품 R&D 관능분석 통합 솔루션")
st.caption(f"Full Package v1.0  |  실행일: {datetime.date.today()}")

tabs = st.tabs([
    "📊 종합차이(ANOVA)",
    "🔄 차이식별(삼점/일-이점)",
    "🔢 순위법(Friedman)",
    "👥 패널 신뢰도",
    "🎲 블라인드 코드",
    "📑 통합 리포트"
])


# ============================================================================
# TAB 1: 종합차이 - ANOVA + Tukey HSD
# ============================================================================

with tabs[0]:
    st.header("📊 종합적 차이 식별 (ANOVA)")
    st.info("9점 척도, 100점 척도 등 **계량 데이터**로 시료 간 유의차를 검정합니다.")
    
    with st.expander("📋 데이터 포맷 (Long format)"):
        st.markdown("""
        **필요한 컬럼:**
        - `패널` : 평가자 ID (예: P01, P02 ...)
        - `시료` : 시료명 (예: A, B, C ...)
        - `점수` : 평가 점수 (숫자)
        - `반복` : (선택) 반복 회차
        """)
        template = pd.DataFrame({
            '패널': ['P01', 'P01', 'P01', 'P02', 'P02', 'P02'],
            '시료': ['A', 'B', 'C', 'A', 'B', 'C'],
            '점수': [7, 6, 8, 6, 7, 8]
        })
        st.dataframe(template, use_container_width=True)
        df_to_csv_download(template, "anova_template.csv", "📥 템플릿 다운로드")
    
    uploaded = st.file_uploader("CSV 업로드", type="csv", key="anova_upload")
    
    if uploaded:
        df = pd.read_csv(uploaded)
        st.success(f"✅ {len(df)}행 로드 완료")
        st.dataframe(df.head(10), use_container_width=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            sample_col = st.selectbox("시료 컬럼", df.columns, key="a_s")
        with col2:
            score_col = st.selectbox("점수 컬럼", df.select_dtypes(include=np.number).columns, key="a_sc")
        with col3:
            panel_col = st.selectbox("패널 컬럼 (Two-way)", ["(없음)"] + list(df.columns), key="a_p")
        
        alpha = st.slider("유의수준 α", 0.001, 0.10, 0.05, 0.001)
        
        if st.button("🚀 ANOVA 분석 실행", key="run_anova", type="primary"):
            try:
                # ANOVA 수행
                if panel_col == "(없음)":
                    formula = f"{score_col} ~ C({sample_col})"
                    model_type = "One-way ANOVA"
                else:
                    formula = f"{score_col} ~ C({sample_col}) + C({panel_col})"
                    model_type = "Two-way ANOVA (시료 + 패널)"
                
                model = ols(formula, data=df).fit()
                anova_table = anova_lm(model, typ=2)
                
                st.subheader(f"📋 {model_type} 결과")
                st.dataframe(anova_table.style.format("{:.4f}"), use_container_width=True)
                
                p_sample = anova_table.loc[f"C({sample_col})", "PR(>F)"]
                f_sample = anova_table.loc[f"C({sample_col})", "F"]
                
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("F-value (시료)", f"{f_sample:.3f}")
                col_b.metric("p-value (시료)", f"{p_sample:.4f}")
                col_c.metric("유의여부", "🟢 유의" if p_sample < alpha else "🔴 비유의")
                
                # Tukey HSD 사후검정
                st.subheader("🔬 Tukey HSD 사후검정")
                tukey = pairwise_tukeyhsd(df[score_col], df[sample_col], alpha=alpha)
                tukey_df = pd.DataFrame(
                    data=tukey._results_table.data[1:],
                    columns=tukey._results_table.data[0]
                )
                
                def highlight_sig(row):
                    return ['background-color: #d4edda' if row['reject'] else '' for _ in row]
                st.dataframe(tukey_df.style.apply(highlight_sig, axis=1), use_container_width=True)
                
                # 시각화
                st.subheader("📈 시각화")
                col_v1, col_v2 = st.columns(2)
                
                with col_v1:
                    fig_box = px.box(df, x=sample_col, y=score_col, 
                                     color=sample_col, points="all",
                                     title="시료별 점수 분포 (Box Plot)",
                                     color_discrete_sequence=px.colors.qualitative.Set2)
                    st.plotly_chart(fig_box, use_container_width=True)
                
                with col_v2:
                    summary = df.groupby(sample_col)[score_col].agg(['mean', 'std', 'count']).reset_index()
                    summary['se'] = summary['std'] / np.sqrt(summary['count'])
                    fig_bar = go.Figure()
                    fig_bar.add_trace(go.Bar(
                        x=summary[sample_col], y=summary['mean'],
                        error_y=dict(type='data', array=summary['se']),
                        marker_color=px.colors.qualitative.Set2[:len(summary)],
                        text=summary['mean'].round(2), textposition='outside'
                    ))
                    fig_bar.update_layout(title="시료별 평균 ± SE", yaxis_title=score_col)
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                # 결과 저장
                st.session_state.results['anova'] = {
                    'model_type': model_type,
                    'anova_table': anova_table,
                    'tukey': tukey_df,
                    'alpha': alpha,
                    'summary': summary,
                    'f_sample': f_sample,
                    'p_sample': p_sample,
                }
                
                # Claude 해석
                if st.session_state.api_key:
                    with st.spinner("Claude가 결과를 해석 중..."):
                        prompt = f"""
다음은 관능검사 ANOVA 분석 결과입니다. 식품개발자가 바로 활용할 수 있도록 해석해주세요.

**분석 유형:** {model_type}
**유의수준:** α = {alpha}

**ANOVA 결과:**
{anova_table.to_string()}

**Tukey HSD 사후검정:**
{tukey_df.to_string()}

**시료별 통계:**
{summary.to_string()}

다음 항목을 포함해주세요:
1. 시료 간 유의차 여부 (쉬운 말로)
2. 어느 시료 쌍에서 차이가 있는지
3. 평균값 순위 및 제품개발 시사점
4. 후속 실험 제안 (있다면)
"""
                        interp = call_claude_api(prompt, st.session_state.api_key, st.session_state.claude_model)
                        st.session_state.interpretations['anova'] = interp
                        st.markdown("### 🤖 Claude AI 해석")
                        st.markdown(interp)
                
            except Exception as e:
                st.error(f"분석 오류: {e}")


# ============================================================================
# TAB 2: 차이식별 - 삼점/일-이점 Binomial Test
# ============================================================================

with tabs[1]:
    st.header("🔄 차이 식별 검사 (Binomial Test)")
    st.info("**삼점검정:** 3개 시료 중 다른 1개를 식별 / **일-이점검정:** 기준시료와 동일한 것을 식별")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("입력")
        test_type = st.radio("검사 종류", ["삼점검정 (Triangle)", "일-이점검정 (Duo-Trio)"])
        total_panel = st.number_input("전체 패널 수 (n)", min_value=5, max_value=500, value=30)
        correct_ans = st.number_input("정답자 수 (x)", min_value=0, max_value=int(total_panel), value=15)
        alpha = st.selectbox("유의수준 α", [0.05, 0.01, 0.001], index=0)
        
        p0 = 1/3 if "삼점" in test_type else 1/2
        st.caption(f"기회확률 P₀ = {p0:.4f}")
    
    with col2:
        st.subheader("분석 결과")
        
        # Binomial test
        result = binomtest(correct_ans, total_panel, p0, alternative='greater')
        p_val = result.pvalue
        
        # 정답률
        correct_rate = correct_ans / total_panel
        
        # 최소 정답자수 역산 (이진탐색)
        min_correct = total_panel
        for x in range(0, total_panel + 1):
            if binomtest(x, total_panel, p0, alternative='greater').pvalue < alpha:
                min_correct = x
                break
        
        m1, m2, m3 = st.columns(3)
        m1.metric("정답률", f"{correct_rate*100:.1f}%")
        m2.metric("p-value", f"{p_val:.4f}")
        m3.metric("최소 정답자수", f"{min_correct}명")
        
        if p_val < alpha:
            st.success(f"✅ **시료 간 유의미한 차이가 있습니다** (p={p_val:.4f} < α={alpha})")
        else:
            st.warning(f"⚠️ **시료 간 유의미한 차이가 없습니다** (p={p_val:.4f} ≥ α={alpha})")
    
    # 시각화
    st.subheader("📊 시각화")
    col_v1, col_v2 = st.columns(2)
    
    with col_v1:
        # 정답자 vs 기대값
        expected = total_panel * p0
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=['기대값 (우연)', '실제 정답자', '최소 유의 정답자'],
            y=[expected, correct_ans, min_correct],
            marker_color=['#94a3b8', '#10b981' if p_val < alpha else '#f59e0b', '#3b82f6'],
            text=[f"{expected:.1f}", f"{correct_ans}", f"{min_correct}"],
            textposition='outside'
        ))
        fig.update_layout(title="정답자수 비교", yaxis_title="인원")
        st.plotly_chart(fig, use_container_width=True)
    
    with col_v2:
        # 이항분포 PMF
        from scipy.stats import binom
        k = np.arange(0, total_panel + 1)
        pmf = binom.pmf(k, total_panel, p0)
        colors = ['#ef4444' if ki >= min_correct else '#cbd5e1' for ki in k]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=k, y=pmf, marker_color=colors, name='PMF'))
        fig2.add_vline(x=correct_ans, line_dash="dash", line_color="green", 
                       annotation_text=f"실제 ({correct_ans})")
        fig2.update_layout(title="이항분포 (빨강 = 유의 영역)", 
                           xaxis_title="정답자수", yaxis_title="확률")
        st.plotly_chart(fig2, use_container_width=True)
    
    # 기준표
    with st.expander("📚 표준 최소 정답자수 기준표"):
        st.markdown("**삼점검정 최소 정답자수 (α=0.05)**")
        ref_triangle = pd.DataFrame({
            '패널수': [12, 15, 18, 20, 24, 27, 30, 36, 42, 48, 54, 60],
            '최소정답': [8, 9, 10, 11, 13, 14, 15, 17, 19, 21, 23, 26]
        })
        st.dataframe(ref_triangle.T, use_container_width=True)
        
        st.markdown("**일-이점검정 최소 정답자수 (α=0.05)**")
        ref_duotrio = pd.DataFrame({
            '패널수': [10, 12, 15, 18, 20, 24, 30, 36, 42, 48],
            '최소정답': [8, 9, 11, 13, 15, 17, 20, 23, 26, 29]
        })
        st.dataframe(ref_duotrio.T, use_container_width=True)
    
    # 저장
    st.session_state.results['discrimination'] = {
        'test_type': test_type, 'n': total_panel, 'correct': correct_ans,
        'p_value': p_val, 'alpha': alpha, 'min_correct': min_correct,
        'significant': p_val < alpha
    }
    
    # Claude 해석
    if st.button("🤖 Claude AI 해석", key="ai_disc"):
        if st.session_state.api_key:
            prompt = f"""
{test_type} 결과입니다:
- 전체 패널: {total_panel}명
- 정답자: {correct_ans}명 ({correct_rate*100:.1f}%)
- 기회확률 P₀: {p0:.4f}
- p-value: {p_val:.4f}
- 유의수준 α: {alpha}
- 최소 유의 정답자수: {min_correct}명
- 결론: {'유의차 있음' if p_val < alpha else '유의차 없음'}

식품개발자 관점에서 이 결과를 해석하고, 다음 액션을 제안해주세요.
"""
            with st.spinner("분석 중..."):
                interp = call_claude_api(prompt, st.session_state.api_key, st.session_state.claude_model)
                st.session_state.interpretations['discrimination'] = interp
                st.markdown(interp)
        else:
            st.warning("사이드바에서 API 키를 입력하세요.")


# ============================================================================
# TAB 3: 순위법 - Friedman + Wilcoxon pairwise
# ============================================================================

with tabs[2]:
    st.header("🔢 순위법 분석 (Friedman Test)")
    st.info("여러 시료의 **순위 데이터**를 비모수 검정으로 분석합니다. (1=가장 강함/선호)")
    
    with st.expander("📋 데이터 포맷 (Wide format)"):
        st.markdown("행 = 패널, 열 = 시료, 값 = 순위 (1, 2, 3 ...)")
        sample_rank = pd.DataFrame({
            '시료A': [1, 2, 1, 1, 2, 3, 1, 2],
            '시료B': [2, 1, 2, 3, 1, 1, 2, 1],
            '시료C': [3, 3, 3, 2, 3, 2, 3, 3]
        })
        st.dataframe(sample_rank)
        df_to_csv_download(sample_rank, "rank_template.csv", "📥 템플릿 다운로드")
    
    uploaded_rank = st.file_uploader("순위 데이터 CSV", type="csv", key="rank_upload")
    
    if uploaded_rank or st.checkbox("예시 데이터로 테스트"):
        df_rank = pd.read_csv(uploaded_rank) if uploaded_rank else pd.DataFrame({
            '시료A': [1, 2, 1, 1, 2, 3, 1, 2],
            '시료B': [2, 1, 2, 3, 1, 1, 2, 1],
            '시료C': [3, 3, 3, 2, 3, 2, 3, 3]
        })
        st.dataframe(df_rank, use_container_width=True)
        
        try:
            # Friedman test
            f_stat, p_val = friedmanchisquare(*[df_rank[c] for c in df_rank.columns])
            
            st.subheader("📋 Friedman 검정 결과")
            c1, c2, c3 = st.columns(3)
            c1.metric("Friedman χ²", f"{f_stat:.4f}")
            c2.metric("p-value", f"{p_val:.4f}")
            c3.metric("결과", "🟢 유의" if p_val < 0.05 else "🔴 비유의")
            
            if p_val < 0.05:
                st.success("✅ 시료 간 순위에 유의미한 차이가 있습니다.")
                
                # Wilcoxon pairwise (Bonferroni 보정)
                st.subheader("🔬 Wilcoxon 쌍별 비교 (Bonferroni 보정)")
                cols = df_rank.columns.tolist()
                n_pairs = len(cols) * (len(cols) - 1) // 2
                bonf_alpha = 0.05 / n_pairs
                
                pair_results = []
                for i in range(len(cols)):
                    for j in range(i+1, len(cols)):
                        try:
                            stat, p = wilcoxon(df_rank[cols[i]], df_rank[cols[j]])
                            pair_results.append({
                                '시료1': cols[i], '시료2': cols[j],
                                'W-stat': stat, 'p-value': p,
                                'p-adj (Bonf)': min(p * n_pairs, 1.0),
                                '유의차': '✓' if p < bonf_alpha else '✗'
                            })
                        except Exception:
                            pair_results.append({
                                '시료1': cols[i], '시료2': cols[j],
                                'W-stat': np.nan, 'p-value': np.nan,
                                'p-adj (Bonf)': np.nan, '유의차': '계산불가'
                            })
                pair_df = pd.DataFrame(pair_results)
                st.dataframe(pair_df, use_container_width=True)
                st.caption(f"보정 유의수준: α' = 0.05 / {n_pairs} = {bonf_alpha:.4f}")
            else:
                st.warning("⚠️ 시료 간 순위 차이가 유의하지 않아 사후검정 생략.")
                pair_df = None
            
            # 시각화
            st.subheader("📊 시각화")
            col_v1, col_v2 = st.columns(2)
            
            with col_v1:
                rank_sum = df_rank.sum().sort_values().reset_index()
                rank_sum.columns = ['시료', '순위합']
                fig = px.bar(rank_sum, x='시료', y='순위합', 
                             color='시료', text='순위합',
                             title="시료별 순위합 (낮을수록 강함/선호)",
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            
            with col_v2:
                rank_long = df_rank.reset_index().melt(id_vars='index', 
                                                       var_name='시료', value_name='순위')
                fig2 = px.box(rank_long, x='시료', y='순위', color='시료',
                              title="시료별 순위 분포",
                              color_discrete_sequence=px.colors.qualitative.Pastel)
                fig2.update_yaxes(autorange="reversed")  # 1위가 위로
                st.plotly_chart(fig2, use_container_width=True)
            
            # 저장
            st.session_state.results['friedman'] = {
                'f_stat': f_stat, 'p_value': p_val,
                'rank_sum': rank_sum, 'pairs': pair_df,
                'n_panel': len(df_rank), 'n_samples': len(df_rank.columns)
            }
            
            # Claude 해석
            if st.button("🤖 Claude AI 해석", key="ai_fried"):
                if st.session_state.api_key:
                    prompt = f"""
Friedman 순위 검정 결과:
- 패널 수: {len(df_rank)}, 시료 수: {len(df_rank.columns)}
- χ² = {f_stat:.4f}, p = {p_val:.4f}

순위합 (낮을수록 강함/선호):
{rank_sum.to_string()}

{'쌍별 비교 (Bonferroni):' + chr(10) + pair_df.to_string() if pair_df is not None else ''}

식품개발 관점에서 해석하고 제품전략을 제안해주세요.
"""
                    with st.spinner("분석 중..."):
                        interp = call_claude_api(prompt, st.session_state.api_key, st.session_state.claude_model)
                        st.session_state.interpretations['friedman'] = interp
                        st.markdown(interp)
                else:
                    st.warning("사이드바에서 API 키를 입력하세요.")
        
        except Exception as e:
            st.error(f"분석 오류: {e}")


# ============================================================================
# TAB 4: 패널 신뢰도
# ============================================================================

with tabs[3]:
    st.header("👥 패널 신뢰도 평가")
    st.info("반복 측정 데이터로 **패널의 재현성/일관성/식별력**을 평가합니다.")
    
    with st.expander("📋 데이터 포맷 (Long format + 반복)"):
        st.markdown("""
        필요한 컬럼: `패널`, `시료`, `반복`, `점수`
        
        - 각 패널이 각 시료를 **2회 이상 반복** 평가한 데이터
        """)
        rel_template = pd.DataFrame({
            '패널': ['P01']*4 + ['P02']*4,
            '시료': ['A', 'A', 'B', 'B']*2,
            '반복': [1, 2, 1, 2]*2,
            '점수': [7, 7, 5, 6, 6, 7, 5, 5]
        })
        st.dataframe(rel_template)
        df_to_csv_download(rel_template, "reliability_template.csv", "📥 템플릿 다운로드")
    
    uploaded_rel = st.file_uploader("반복측정 CSV", type="csv", key="rel_upload")
    
    if uploaded_rel:
        df_rel = pd.read_csv(uploaded_rel)
        st.success(f"✅ {len(df_rel)}행 로드")
        st.dataframe(df_rel.head(10))
        
        c1, c2, c3, c4 = st.columns(4)
        panel_c = c1.selectbox("패널", df_rel.columns, key="r_p")
        sample_c = c2.selectbox("시료", df_rel.columns, key="r_s")
        rep_c = c3.selectbox("반복", df_rel.columns, key="r_r")
        score_c = c4.selectbox("점수", df_rel.select_dtypes(include=np.number).columns, key="r_sc")
        
        if st.button("🔍 신뢰도 분석 실행", type="primary", key="run_rel"):
            try:
                # 1. 패널별 CV (변동계수) - 반복 간 일관성
                cv_data = []
                for p in df_rel[panel_c].unique():
                    sub = df_rel[df_rel[panel_c] == p]
                    cvs = []
                    for s in sub[sample_c].unique():
                        scores = sub[sub[sample_c] == s][score_c].values
                        if len(scores) > 1 and scores.mean() != 0:
                            cvs.append(scores.std() / abs(scores.mean()) * 100)
                    cv_data.append({
                        '패널': p,
                        '평균 CV(%)': np.mean(cvs) if cvs else np.nan,
                        '평균 점수': sub[score_c].mean()
                    })
                cv_df = pd.DataFrame(cv_data).sort_values('평균 CV(%)')
                
                # 2. 패널별 시료 식별력 (개별 One-way ANOVA F-value)
                discrim_data = []
                for p in df_rel[panel_c].unique():
                    sub = df_rel[df_rel[panel_c] == p]
                    groups = [sub[sub[sample_c] == s][score_c].values 
                              for s in sub[sample_c].unique()]
                    groups = [g for g in groups if len(g) >= 2]
                    if len(groups) >= 2:
                        try:
                            f, p_val = f_oneway(*groups)
                            discrim_data.append({
                                '패널': p, 'F-value': f, 'p-value': p_val,
                                '식별력': '🟢 우수' if p_val < 0.05 else '🟡 보통' if p_val < 0.20 else '🔴 낮음'
                            })
                        except Exception:
                            discrim_data.append({'패널': p, 'F-value': np.nan, 
                                                 'p-value': np.nan, '식별력': '계산불가'})
                discrim_df = pd.DataFrame(discrim_data).sort_values('F-value', ascending=False)
                
                # 3. ICC (Intraclass Correlation) - 2-way mixed
                # ICC(3,1) 근사 계산: Panelist × Sample 변동 기반
                try:
                    formula = f"{score_c} ~ C({panel_c}) + C({sample_c})"
                    mod = ols(formula, data=df_rel).fit()
                    aov = anova_lm(mod, typ=2)
                    
                    ms_panel = aov.loc[f"C({panel_c})", "sum_sq"] / aov.loc[f"C({panel_c})", "df"]
                    ms_res = aov.loc["Residual", "sum_sq"] / aov.loc["Residual", "df"]
                    k = df_rel[sample_c].nunique()
                    icc = (ms_panel - ms_res) / (ms_panel + (k - 1) * ms_res)
                except Exception:
                    icc = np.nan
                
                # 결과 표시
                st.subheader("📊 분석 결과")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("ICC (패널 일관성)", 
                          f"{icc:.3f}" if not np.isnan(icc) else "N/A",
                          help="0.75↑ 우수 / 0.5~0.75 보통 / 0.5↓ 낮음")
                c2.metric("우수 패널", 
                          f"{(discrim_df['p-value'] < 0.05).sum()}/{len(discrim_df)}명")
                c3.metric("평균 CV", 
                          f"{cv_df['평균 CV(%)'].mean():.1f}%")
                
                st.markdown("#### 🎯 패널별 시료 식별력 (개별 ANOVA)")
                st.dataframe(discrim_df, use_container_width=True)
                st.caption("식별력이 낮은 패널은 재훈련 또는 배제를 고려하세요.")
                
                st.markdown("#### 🔁 패널별 반복 일관성 (CV)")
                st.dataframe(cv_df, use_container_width=True)
                st.caption("CV 10% 이하가 이상적입니다.")
                
                # 시각화: 히트맵
                st.subheader("🗺️ 패널 × 시료 평균 점수 히트맵")
                pivot = df_rel.groupby([panel_c, sample_c])[score_c].mean().unstack()
                fig = px.imshow(pivot, text_auto='.2f', aspect='auto',
                                color_continuous_scale='RdYlGn',
                                title="패널별 시료 평균 점수")
                st.plotly_chart(fig, use_container_width=True)
                
                # F-value 차트
                fig_f = px.bar(discrim_df, x='패널', y='F-value',
                               color='식별력', title="패널별 식별력 (F-value)",
                               color_discrete_map={'🟢 우수': '#10b981', 
                                                    '🟡 보통': '#f59e0b', 
                                                    '🔴 낮음': '#ef4444'})
                st.plotly_chart(fig_f, use_container_width=True)
                
                # 저장
                st.session_state.results['reliability'] = {
                    'icc': icc, 'cv_df': cv_df, 'discrim_df': discrim_df,
                    'pivot': pivot
                }
                
                # Claude 해석
                if st.session_state.api_key:
                    with st.spinner("Claude 해석 중..."):
                        prompt = f"""
패널 신뢰도 평가 결과:

- ICC (패널 일관성): {icc:.3f}
- 우수 패널(p<0.05): {(discrim_df['p-value'] < 0.05).sum()}/{len(discrim_df)}명
- 평균 CV: {cv_df['평균 CV(%)'].mean():.1f}%

패널별 식별력:
{discrim_df.to_string()}

패널별 일관성:
{cv_df.to_string()}

다음을 분석해주세요:
1. 패널의 전체적 신뢰도 평가
2. 재훈련/배제 권장 패널
3. 개선 방안
"""
                        interp = call_claude_api(prompt, st.session_state.api_key, st.session_state.claude_model)
                        st.session_state.interpretations['reliability'] = interp
                        st.markdown("### 🤖 Claude AI 해석")
                        st.markdown(interp)
                        
            except Exception as e:
                st.error(f"분석 오류: {e}")
                import traceback
                st.code(traceback.format_exc())


# ============================================================================
# TAB 5: 블라인드 코드 생성기
# ============================================================================

with tabs[4]:
    st.header("🎲 블라인드 코드 자동 생성")
    st.info("관능검사용 **3자리 난수 코드**와 **라틴방격 제시 순서**를 자동 생성합니다.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        n_samples = st.number_input("시료 수", min_value=2, max_value=26, value=3)
        n_panelists = st.number_input("패널 수", min_value=2, max_value=200, value=12)
        sample_names = st.text_input(
            "시료명 (쉼표로 구분)", 
            value=",".join([f"시료{chr(65+i)}" for i in range(n_samples)])
        )
        seed = st.number_input("난수 시드 (재현성 보장)", value=42)
    
    with col2:
        balanced = st.checkbox("제시순서 균형화 (라틴방격)", value=True)
        unique_per_panel = st.radio(
            "코드 부여 방식",
            ["패널별로 다른 코드 (완전 블라인드)", "시료별로 동일 코드 (간편)"]
        )
    
    if st.button("🎲 코드 생성", type="primary", key="gen_code"):
        try:
            names = [s.strip() for s in sample_names.split(",")][:n_samples]
            while len(names) < n_samples:
                names.append(f"시료{chr(65+len(names))}")
            
            random.seed(int(seed))
            
            rows = []
            if "패널별로" in unique_per_panel:
                total_codes = n_samples * n_panelists
                all_codes = random.sample(range(100, 1000), total_codes)
                for p in range(n_panelists):
                    codes = all_codes[p*n_samples:(p+1)*n_samples]
                    # 라틴방격 순서 로테이션
                    if balanced:
                        order = [(s + p) % n_samples for s in range(n_samples)]
                    else:
                        order = list(range(n_samples))
                    for presentation, s_idx in enumerate(order, 1):
                        rows.append({
                            '패널': f"P{p+1:02d}",
                            '제시순서': presentation,
                            '시료명': names[s_idx],
                            '블라인드코드': codes[s_idx]
                        })
            else:
                # 시료별 공통 코드
                sample_codes = random.sample(range(100, 1000), n_samples)
                for p in range(n_panelists):
                    if balanced:
                        order = [(s + p) % n_samples for s in range(n_samples)]
                    else:
                        order = list(range(n_samples))
                    for presentation, s_idx in enumerate(order, 1):
                        rows.append({
                            '패널': f"P{p+1:02d}",
                            '제시순서': presentation,
                            '시료명': names[s_idx],
                            '블라인드코드': sample_codes[s_idx]
                        })
            
            code_df = pd.DataFrame(rows)
            st.success(f"✅ 총 {len(code_df)}개 블라인드 코드 생성 완료")
            
            # 테이블 뷰
            tab_a, tab_b = st.tabs(["📋 상세 리스트", "📊 피벗 뷰"])
            with tab_a:
                st.dataframe(code_df, use_container_width=True, height=400)
            with tab_b:
                pivot_view = code_df.pivot(index='패널', columns='제시순서', 
                                           values='블라인드코드')
                pivot_names = code_df.pivot(index='패널', columns='제시순서', 
                                            values='시료명')
                st.markdown("**블라인드 코드**")
                st.dataframe(pivot_view, use_container_width=True)
                st.markdown("**실제 시료명 (정답지)**")
                st.dataframe(pivot_names, use_container_width=True)
            
            # 다운로드
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                df_to_csv_download(code_df, "blind_codes.csv", "📥 전체 리스트 CSV")
            with col_d2:
                # Excel 다운로드
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    code_df.to_excel(writer, sheet_name='상세리스트', index=False)
                    pivot_view.to_excel(writer, sheet_name='코드피벗')
                    pivot_names.to_excel(writer, sheet_name='정답지')
                st.download_button(
                    "📥 Excel (3시트)", data=buf.getvalue(),
                    file_name="blind_codes.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            # 저장
            st.session_state.results['blind_codes'] = {
                'code_df': code_df, 'n_samples': n_samples, 
                'n_panelists': n_panelists, 'balanced': balanced
            }
            
        except Exception as e:
            st.error(f"생성 오류: {e}")


# ============================================================================
# TAB 6: 통합 리포트
# ============================================================================

with tabs[5]:
    st.header("📑 통합 리포트 생성")
    st.info("현재 세션에서 수행한 모든 분석을 하나의 HTML 리포트로 생성합니다.")
    
    if not st.session_state.results:
        st.warning("⚠️ 아직 수행된 분석이 없습니다. 다른 탭에서 분석을 먼저 수행하세요.")
    else:
        st.markdown("#### 포함할 분석")
        available = list(st.session_state.results.keys())
        labels_map = {
            'anova': '📊 종합차이 (ANOVA)',
            'discrimination': '🔄 차이식별 검사',
            'friedman': '🔢 순위법',
            'reliability': '👥 패널 신뢰도',
            'blind_codes': '🎲 블라인드 코드'
        }
        to_include = st.multiselect(
            "분석 선택", available, default=available,
            format_func=lambda x: labels_map.get(x, x)
        )
        
        project_name = st.text_input("프로젝트명", value="Natural Lab Sensory Study")
        author = st.text_input("작성자", value="Sweet Lab")
        
        if st.button("📑 HTML 리포트 생성", type="primary"):
            html = generate_html_report(project_name, author, to_include, 
                                        st.session_state.results,
                                        st.session_state.interpretations)
            
            st.download_button(
                "📥 HTML 리포트 다운로드",
                data=html.encode('utf-8'),
                file_name=f"sensory_report_{datetime.date.today()}.html",
                mime="text/html"
            )
            
            with st.expander("🔍 리포트 미리보기"):
                st.components.v1.html(html, height=800, scrolling=True)



