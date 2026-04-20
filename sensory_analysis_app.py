"""
식품 R&D 관능분석 통합 솔루션 (Full Package v2.0)
=================================================
- Tab 1: 종합차이 (ANOVA + Tukey HSD)
- Tab 2: 차이식별 (삼점/일-이점 Binomial Test)
- Tab 3: 순위법 (Friedman + Wilcoxon pairwise)
- Tab 4: 패널 신뢰도 (ICC, CV, 개별 F-value)
- Tab 5: 블라인드 코드 생성기
- Tab 6: 통합 리포트 + Claude AI 해석

v2.0 신규:
- 각 탭별 조사지 양식(빈 폼) 다운로드
- 랜덤 응답 데이터 자동 생성 (데모/테스트용)
- 조사지 업로드 → 분석 완전 통합
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import random
import datetime
import requests
from scipy import stats
from scipy.stats import f_oneway, binomtest, friedmanchisquare, wilcoxon, binom
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
import matplotlib.pyplot as plt
import matplotlib
import plotly.express as px
import plotly.graph_objects as go

# ============================================================================
# 초기 설정
# ============================================================================

for font in ['Malgun Gothic', 'AppleGothic', 'NanumGothic', 'DejaVu Sans']:
    if font in [f.name for f in matplotlib.font_manager.fontManager.ttflist]:
        plt.rcParams['font.family'] = font
        break
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(
    page_title="식품 R&D 관능분석 통합 솔루션 v2.0",
    layout="wide", page_icon="🧪"
)

for key, default in [
    ('results', {}), ('api_key', ''),
    ('claude_model', 'claude-sonnet-4-5'),
    ('interpretations', {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ============================================================================
# 공통 유틸리티
# ============================================================================

def call_claude_api(prompt, api_key, model="claude-sonnet-4-5"):
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
        "통계적 유의성뿐 아니라 제품개발에 주는 함의, 후속 실험 제안을 포함하세요. "
        "답변은 한국어로, 마크다운 구조(### 헤딩, 불릿)를 활용해 작성하세요."
    )
    payload = {
        "model": model, "max_tokens": 2000, "system": system_msg,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    except requests.exceptions.HTTPError:
        return f"❌ API 오류 ({r.status_code}): {r.text[:300]}"
    except Exception as e:
        return f"❌ 호출 오류: {str(e)}"


def df_to_csv_download(df, filename, label, key=None, help_text=None):
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(label, data=csv, file_name=filename,
        mime="text/csv", key=key, help=help_text, use_container_width=True)


# ============================================================================
# 조사지 양식 & 랜덤 데이터 생성 함수
# ============================================================================

def gen_anova_form(n_panels, samples, random_fill=False, seed=None):
    """ANOVA Long format (패널 × 시료)"""
    if seed is not None:
        np.random.seed(seed)
    rows = []
    if random_fill:
        base_means = np.random.uniform(5.0, 8.0, len(samples))
        base_means = np.sort(base_means)
        for i in range(1, len(base_means)):
            if base_means[i] - base_means[i-1] < 0.8:
                base_means[i] = base_means[i-1] + np.random.uniform(0.8, 1.5)
        base_means = np.clip(base_means, 3.5, 8.5)
        np.random.shuffle(base_means)
        sample_means = dict(zip(samples, base_means))
    
    for p in range(n_panels):
        panel_bias = np.random.normal(0, 0.3) if random_fill else 0
        for s in samples:
            row = {'패널': f'P{p+1:02d}', '시료': s}
            if random_fill:
                score = np.random.normal(sample_means[s] + panel_bias, 0.8)
                row['점수'] = int(np.clip(round(score), 1, 9))
            else:
                row['점수'] = ''
            rows.append(row)
    return pd.DataFrame(rows)


def gen_discrimination_form(n_panels, test_type, random_fill=False,
                             p_true=0.55, seed=None):
    """삼점/일-이점 조사지"""
    if seed is not None:
        np.random.seed(seed)
    p0 = 1/3 if "삼점" in test_type else 1/2
    actual_p = p_true if p_true > p0 else p0
    
    rows = []
    for p in range(n_panels):
        row = {'패널': f'P{p+1:02d}'}
        if random_fill:
            row['정답여부'] = int(np.random.random() < actual_p)
        else:
            row['정답여부'] = ''
        rows.append(row)
    return pd.DataFrame(rows)


def gen_ranking_form(n_panels, samples, random_fill=False, seed=None):
    """순위법 Wide format"""
    if seed is not None:
        np.random.seed(seed)
    n_samples = len(samples)
    true_pref = np.random.uniform(3, 8, n_samples) if random_fill else None
    
    rows = []
    for p in range(n_panels):
        row = {'패널': f'P{p+1:02d}'}
        if random_fill:
            noisy_pref = true_pref + np.random.normal(0, 1.2, n_samples)
            ranks = pd.Series(noisy_pref).rank(ascending=False, method='first').astype(int).tolist()
            for s, r in zip(samples, ranks):
                row[s] = r
        else:
            for s in samples:
                row[s] = ''
        rows.append(row)
    return pd.DataFrame(rows)


def gen_reliability_form(n_panels, samples, n_reps, random_fill=False, seed=None):
    """신뢰도 Long + 반복"""
    if seed is not None:
        np.random.seed(seed)
    rows = []
    sample_means = {}
    if random_fill:
        base = np.random.uniform(5, 8, len(samples))
        base = np.sort(base)
        for i in range(1, len(base)):
            if base[i] - base[i-1] < 0.8:
                base[i] = base[i-1] + 1.0
        sample_means = dict(zip(samples, base))
    
    for p in range(n_panels):
        panel_bias = np.random.normal(0, 0.5) if random_fill else 0
        if random_fill:
            if np.random.random() < 0.8:
                panel_noise = np.random.uniform(0.3, 0.7)
            else:
                panel_noise = np.random.uniform(1.0, 1.8)
        else:
            panel_noise = 1.0
        
        for s in samples:
            for r in range(n_reps):
                row = {'패널': f'P{p+1:02d}', '시료': s, '반복': r+1}
                if random_fill:
                    score = np.random.normal(sample_means[s] + panel_bias, panel_noise)
                    row['점수'] = int(np.clip(round(score), 1, 9))
                else:
                    row['점수'] = ''
                rows.append(row)
    return pd.DataFrame(rows)


def form_manager_ui(tab_key, form_type):
    """각 탭 상단 공통 조사지 관리 UI"""
    with st.expander("📋 조사지 관리 — 양식 다운로드 / 랜덤 데이터 생성", expanded=False):
        st.caption("👉 **빈 양식**: 조사 진행용 / **랜덤 데이터**: 앱 테스트용 데모")
        
        if form_type == 'anova':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 3, 100, 10, key=f"{tab_key}_np")
                samples_str = st.text_input("시료명 (쉼표 구분)", "A,B,C", key=f"{tab_key}_s")
            with c2:
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
                samples = [s.strip() for s in samples_str.split(",") if s.strip()]
            
            if samples:
                blank = gen_anova_form(n, samples, random_fill=False)
                rand = gen_anova_form(n, samples, random_fill=True, seed=int(seed))
                d1, d2 = st.columns(2)
                with d1:
                    df_to_csv_download(blank, f"ANOVA_조사지양식_{n}명.csv",
                        "📥 빈 조사지 양식", key=f"{tab_key}_dl1")
                with d2:
                    df_to_csv_download(rand, f"ANOVA_랜덤데이터_{n}명.csv",
                        "🎲 랜덤 응답 데이터", key=f"{tab_key}_dl2")
                st.markdown("**미리보기** (랜덤 응답):")
                st.dataframe(rand.head(6), use_container_width=True)
        
        elif form_type == 'discrimination':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 5, 500, 30, key=f"{tab_key}_np")
                t_type = st.radio("검사 종류",
                    ["삼점검정", "일-이점검정"], key=f"{tab_key}_tt", horizontal=True)
            with c2:
                p_true = st.slider("진짜 정답확률 (랜덤생성용)", 0.1, 0.95, 0.55, 0.05,
                    key=f"{tab_key}_pt",
                    help="실제 식별 가능성. 0.33(삼점)/0.5(일-이점)보다 높아야 유의차 발생")
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
            
            blank = gen_discrimination_form(n, t_type, random_fill=False)
            rand = gen_discrimination_form(n, t_type, random_fill=True,
                p_true=p_true, seed=int(seed))
            d1, d2 = st.columns(2)
            with d1:
                df_to_csv_download(blank, f"{t_type}_조사지양식_{n}명.csv",
                    "📥 빈 조사지 양식", key=f"{tab_key}_dl1")
            with d2:
                df_to_csv_download(rand, f"{t_type}_랜덤데이터_{n}명.csv",
                    "🎲 랜덤 응답 데이터", key=f"{tab_key}_dl2")
            st.caption("💡 정답여부: 1=다른시료 식별 성공, 0=실패")
            st.markdown("**미리보기** (랜덤 응답):")
            st.dataframe(rand.head(6), use_container_width=True)
        
        elif form_type == 'ranking':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 3, 100, 10, key=f"{tab_key}_np")
                samples_str = st.text_input("시료명 (쉼표 구분)", "시료A,시료B,시료C",
                    key=f"{tab_key}_s")
            with c2:
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
                samples = [s.strip() for s in samples_str.split(",") if s.strip()]
            
            if samples:
                blank = gen_ranking_form(n, samples, random_fill=False)
                rand = gen_ranking_form(n, samples, random_fill=True, seed=int(seed))
                d1, d2 = st.columns(2)
                with d1:
                    df_to_csv_download(blank, f"순위법_조사지양식_{n}명.csv",
                        "📥 빈 조사지 양식", key=f"{tab_key}_dl1")
                with d2:
                    df_to_csv_download(rand, f"순위법_랜덤데이터_{n}명.csv",
                        "🎲 랜덤 응답 데이터", key=f"{tab_key}_dl2")
                st.caption("💡 1=가장 선호/강함, 숫자 클수록 낮은 순위")
                st.markdown("**미리보기** (랜덤 응답):")
                st.dataframe(rand.head(6), use_container_width=True)
        
        elif form_type == 'reliability':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 3, 50, 8, key=f"{tab_key}_np")
                samples_str = st.text_input("시료명 (쉼표 구분)", "A,B,C", key=f"{tab_key}_s")
            with c2:
                n_reps = st.number_input("반복 횟수", 2, 5, 2, key=f"{tab_key}_nr")
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
                samples = [s.strip() for s in samples_str.split(",") if s.strip()]
            
            if samples:
                blank = gen_reliability_form(n, samples, n_reps, random_fill=False)
                rand = gen_reliability_form(n, samples, n_reps, random_fill=True,
                    seed=int(seed))
                d1, d2 = st.columns(2)
                with d1:
                    df_to_csv_download(blank, f"신뢰도_조사지양식_{n}명_{n_reps}반복.csv",
                        "📥 빈 조사지 양식", key=f"{tab_key}_dl1")
                with d2:
                    df_to_csv_download(rand, f"신뢰도_랜덤데이터_{n}명_{n_reps}반복.csv",
                        "🎲 랜덤 응답 데이터", key=f"{tab_key}_dl2")
                st.markdown("**미리보기** (랜덤 응답):")
                st.dataframe(rand.head(8), use_container_width=True)


# ============================================================================
# HTML 리포트 생성
# ============================================================================

def generate_html_report(project, author, sections, results, interpretations):
    import re
    def md_to_html(text):
        text = re.sub(r'### (.+)', r'<h4>\1</h4>', text)
        text = re.sub(r'## (.+)', r'<h3>\1</h3>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = text.replace('\n\n', '</p><p>')
        return f'<p>{text}</p>'
    
    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>{project}</title>
<style>
body {{ font-family: 'Malgun Gothic', sans-serif; max-width: 1100px;
       margin: 40px auto; padding: 20px; color: #1e293b; line-height: 1.7; }}
.header {{ background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
          color: white; padding: 40px; border-radius: 12px; }}
.header h1 {{ margin: 0; font-size: 32px; }}
.section {{ background: #f8fafc; border-left: 4px solid #0ea5e9;
           padding: 25px; margin: 25px 0; border-radius: 8px; }}
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
.ai-box {{ background: #fef3c7; border-left: 4px solid #f59e0b;
          padding: 20px; border-radius: 8px; margin: 15px 0; }}
.badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px;
         font-size: 12px; font-weight: bold; }}
.badge.sig {{ background: #dcfce7; color: #166534; }}
.badge.nosig {{ background: #fee2e2; color: #991b1b; }}
</style></head><body>
<div class="header">
  <h1>🧪 {project}</h1>
  <p>관능분석 통합 리포트 | 작성자: {author} | {datetime.date.today()}</p>
</div>
"""
    if 'anova' in sections and 'anova' in results:
        r = results['anova']
        sig = r['p_sample'] < r['alpha']
        html += f"""<div class="section"><h2>📊 종합차이 (ANOVA)</h2>
<p><strong>분석 유형:</strong> {r['model_type']}</p>
<div class="metric-grid">
  <div class="metric"><div class="label">F-value</div><div class="value">{r['f_sample']:.3f}</div></div>
  <div class="metric"><div class="label">p-value</div><div class="value">{r['p_sample']:.4f}</div></div>
  <div class="metric"><div class="label">α</div><div class="value">{r['alpha']}</div></div>
  <div class="metric"><div class="label">결과</div><div class="value"><span class="badge {'sig' if sig else 'nosig'}">{'유의' if sig else '비유의'}</span></div></div>
</div>
<h4>ANOVA 표</h4>{r['anova_table'].to_html(float_format='%.4f')}
<h4>Tukey HSD</h4>{r['tukey'].to_html(index=False, float_format='%.4f')}
<h4>시료별 평균</h4>{r['summary'].to_html(index=False, float_format='%.3f')}"""
        if 'anova' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["anova"])}</div>'
        html += "</div>"
    
    if 'discrimination' in sections and 'discrimination' in results:
        r = results['discrimination']
        html += f"""<div class="section"><h2>🔄 차이식별 검사</h2>
<p><strong>검사:</strong> {r['test_type']}</p>
<div class="metric-grid">
  <div class="metric"><div class="label">패널</div><div class="value">{r['n']}</div></div>
  <div class="metric"><div class="label">정답자</div><div class="value">{r['correct']}</div></div>
  <div class="metric"><div class="label">p-value</div><div class="value">{r['p_value']:.4f}</div></div>
  <div class="metric"><div class="label">최소정답</div><div class="value">{r['min_correct']}</div></div>
  <div class="metric"><div class="label">결과</div><div class="value"><span class="badge {'sig' if r['significant'] else 'nosig'}">{'유의' if r['significant'] else '비유의'}</span></div></div>
</div>"""
        if 'discrimination' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["discrimination"])}</div>'
        html += "</div>"
    
    if 'friedman' in sections and 'friedman' in results:
        r = results['friedman']
        sig = r['p_value'] < 0.05
        html += f"""<div class="section"><h2>🔢 순위법 (Friedman)</h2>
<div class="metric-grid">
  <div class="metric"><div class="label">패널</div><div class="value">{r['n_panel']}</div></div>
  <div class="metric"><div class="label">시료</div><div class="value">{r['n_samples']}</div></div>
  <div class="metric"><div class="label">χ²</div><div class="value">{r['f_stat']:.3f}</div></div>
  <div class="metric"><div class="label">p-value</div><div class="value">{r['p_value']:.4f}</div></div>
  <div class="metric"><div class="label">결과</div><div class="value"><span class="badge {'sig' if sig else 'nosig'}">{'유의' if sig else '비유의'}</span></div></div>
</div>
<h4>순위합</h4>{r['rank_sum'].to_html(index=False)}"""
        if r.get('pairs') is not None:
            html += f"<h4>Wilcoxon 쌍별 비교</h4>{r['pairs'].to_html(index=False, float_format='%.4f')}"
        if 'friedman' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["friedman"])}</div>'
        html += "</div>"
    
    if 'reliability' in sections and 'reliability' in results:
        r = results['reliability']
        html += f"""<div class="section"><h2>👥 패널 신뢰도</h2>
<div class="metric-grid">
  <div class="metric"><div class="label">ICC</div><div class="value">{r['icc']:.3f}</div></div>
  <div class="metric"><div class="label">우수패널</div><div class="value">{(r['discrim_df']['p-value']<0.05).sum()}/{len(r['discrim_df'])}</div></div>
  <div class="metric"><div class="label">평균CV</div><div class="value">{r['cv_df']['평균 CV(%)'].mean():.1f}%</div></div>
</div>
<h4>패널별 식별력</h4>{r['discrim_df'].to_html(index=False, float_format='%.4f')}
<h4>패널별 일관성 (CV)</h4>{r['cv_df'].to_html(index=False, float_format='%.2f')}"""
        if 'reliability' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["reliability"])}</div>'
        html += "</div>"
    
    if 'blind_codes' in sections and 'blind_codes' in results:
        r = results['blind_codes']
        html += f"""<div class="section"><h2>🎲 블라인드 코드</h2>
<h4>상위 20개</h4>{r['code_df'].head(20).to_html(index=False)}</div>"""
    
    html += '<footer style="text-align:center;color:#94a3b8;padding:20px;"><p>© Sweet Lab · Natural Lab R&D</p></footer></body></html>'
    return html


# ============================================================================
# 사이드바
# ============================================================================

with st.sidebar:
    st.title("⚙️ 설정")
    st.subheader("🤖 Claude AI 해석")
    st.session_state.api_key = st.text_input(
        "Anthropic API Key", value=st.session_state.api_key,
        type="password", help="결과 해석 시에만 사용")
    st.session_state.claude_model = st.selectbox(
        "모델", ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"])
    st.divider()
    st.caption("💡 **Workflow**\n"
                "1. 조사지 양식 다운로드\n"
                "2. 조사 실시 & 작성\n"
                "3. CSV 업로드\n"
                "4. 분석 실행")
    st.caption(f"v2.0 | {datetime.date.today()}")


# ============================================================================
# 메인
# ============================================================================

st.title("🧪 식품 R&D 관능분석 통합 솔루션")
st.caption("Full Package v2.0 — 조사지 양식 · 랜덤 데이터 · 통합 분석")

tabs = st.tabs([
    "📊 종합차이(ANOVA)",
    "🔄 차이식별(삼점/일-이점)",
    "🔢 순위법(Friedman)",
    "👥 패널 신뢰도",
    "🎲 블라인드 코드",
    "📑 통합 리포트"
])


# ============================================================================
# TAB 1: ANOVA
# ============================================================================

with tabs[0]:
    st.header("📊 종합적 차이 식별 (ANOVA)")
    st.info("9점 척도 등 계량 데이터로 시료 간 유의차를 검정합니다.")
    
    form_manager_ui("t1", "anova")
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    uploaded = st.file_uploader("작성된 조사지 CSV", type="csv", key="t1_up")
    
    if uploaded:
        df = pd.read_csv(uploaded)
        # 점수 컬럼의 빈값 제거 (빈 양식 업로드 대응)
        if '점수' in df.columns:
            df = df[pd.to_numeric(df['점수'], errors='coerce').notna()].copy()
            df['점수'] = df['점수'].astype(float)
        
        if len(df) == 0:
            st.error("❌ 점수가 입력되지 않은 빈 조사지입니다.")
        else:
            st.success(f"✅ {len(df)}행 로드")
            st.dataframe(df.head(8), use_container_width=True)
            
            c1, c2, c3 = st.columns(3)
            sample_col = c1.selectbox("시료 컬럼", df.columns,
                index=list(df.columns).index('시료') if '시료' in df.columns else 0,
                key="t1_sc")
            num_cols = df.select_dtypes(include=np.number).columns.tolist()
            score_col = c2.selectbox("점수 컬럼", num_cols,
                index=num_cols.index('점수') if '점수' in num_cols else 0,
                key="t1_scc") if num_cols else None
            panel_options = ["(없음)"] + list(df.columns)
            panel_col = c3.selectbox("패널 컬럼 (Two-way)", panel_options,
                index=panel_options.index('패널') if '패널' in panel_options else 0,
                key="t1_pc")
            
            alpha = st.slider("유의수준 α", 0.001, 0.10, 0.05, 0.001, key="t1_a")
            
            if st.button("🚀 ANOVA 분석 실행", type="primary", key="t1_run") and score_col:
                try:
                    if panel_col == "(없음)":
                        formula = f"Q('{score_col}') ~ C(Q('{sample_col}'))"
                        model_type = "One-way ANOVA"
                    else:
                        formula = f"Q('{score_col}') ~ C(Q('{sample_col}')) + C(Q('{panel_col}'))"
                        model_type = "Two-way ANOVA (시료 + 패널)"
                    
                    model = ols(formula, data=df).fit()
                    anova_table = anova_lm(model, typ=2)
                    
                    st.subheader(f"📋 {model_type} 결과")
                    st.dataframe(anova_table.style.format("{:.4f}"),
                        use_container_width=True)
                    
                    sample_idx = [idx for idx in anova_table.index if sample_col in idx][0]
                    p_sample = anova_table.loc[sample_idx, "PR(>F)"]
                    f_sample = anova_table.loc[sample_idx, "F"]
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("F-value (시료)", f"{f_sample:.3f}")
                    c2.metric("p-value (시료)", f"{p_sample:.4f}")
                    c3.metric("유의여부", "🟢 유의" if p_sample < alpha else "🔴 비유의")
                    
                    st.subheader("🔬 Tukey HSD 사후검정")
                    tukey = pairwise_tukeyhsd(df[score_col], df[sample_col], alpha=alpha)
                    tukey_df = pd.DataFrame(
                        data=tukey._results_table.data[1:],
                        columns=tukey._results_table.data[0])
                    def highlight_sig(row):
                        return ['background-color: #d4edda' if row['reject'] else '' for _ in row]
                    st.dataframe(tukey_df.style.apply(highlight_sig, axis=1),
                        use_container_width=True)
                    
                    st.subheader("📈 시각화")
                    c_v1, c_v2 = st.columns(2)
                    with c_v1:
                        fig_box = px.box(df, x=sample_col, y=score_col,
                            color=sample_col, points="all",
                            title="시료별 점수 분포",
                            color_discrete_sequence=px.colors.qualitative.Set2)
                        st.plotly_chart(fig_box, use_container_width=True)
                    with c_v2:
                        summary = df.groupby(sample_col)[score_col].agg(['mean','std','count']).reset_index()
                        summary['se'] = summary['std']/np.sqrt(summary['count'])
                        fig_bar = go.Figure()
                        fig_bar.add_trace(go.Bar(
                            x=summary[sample_col], y=summary['mean'],
                            error_y=dict(type='data', array=summary['se']),
                            marker_color=px.colors.qualitative.Set2[:len(summary)],
                            text=summary['mean'].round(2), textposition='outside'))
                        fig_bar.update_layout(title="시료별 평균 ± SE", yaxis_title=score_col)
                        st.plotly_chart(fig_bar, use_container_width=True)
                    
                    st.session_state.results['anova'] = {
                        'model_type': model_type, 'anova_table': anova_table,
                        'tukey': tukey_df, 'alpha': alpha, 'summary': summary,
                        'f_sample': f_sample, 'p_sample': p_sample,
                    }
                    
                    if st.session_state.api_key:
                        with st.spinner("Claude 해석 중..."):
                            prompt = f"""관능검사 ANOVA 결과:
분석: {model_type}, α={alpha}

ANOVA:
{anova_table.to_string()}

Tukey HSD:
{tukey_df.to_string()}

시료별 통계:
{summary.to_string()}

식품개발자 관점에서 해석과 후속 실험을 제안해주세요."""
                            interp = call_claude_api(prompt, st.session_state.api_key,
                                st.session_state.claude_model)
                            st.session_state.interpretations['anova'] = interp
                            st.markdown("### 🤖 Claude AI 해석")
                            st.markdown(interp)
                except Exception as e:
                    st.error(f"분석 오류: {e}")
                    import traceback
                    with st.expander("상세 오류"):
                        st.code(traceback.format_exc())


# ============================================================================
# TAB 2: 차이식별
# ============================================================================

with tabs[1]:
    st.header("🔄 차이 식별 검사 (Binomial Test)")
    st.info("**삼점:** 3개 중 다른 1개 식별 / **일-이점:** 기준과 동일한 것 식별")
    
    form_manager_ui("t2", "discrimination")
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    
    sub_a, sub_b = st.tabs(["📂 조사지 업로드", "⌨️ 직접 입력"])
    
    with sub_a:
        uploaded_d = st.file_uploader("작성된 조사지 CSV", type="csv", key="t2_up")
        if uploaded_d:
            dfd = pd.read_csv(uploaded_d)
            ans_col = None
            for c in dfd.columns:
                if '정답' in c or 'correct' in c.lower():
                    ans_col = c
                    break
            if ans_col is None:
                ans_col = st.selectbox("정답 컬럼", dfd.columns, key="t2_ac")
            
            dfd_clean = dfd[pd.to_numeric(dfd[ans_col], errors='coerce').notna()].copy()
            if len(dfd_clean) == 0:
                st.error("❌ 정답 데이터가 입력되지 않았습니다.")
            else:
                dfd_clean[ans_col] = dfd_clean[ans_col].astype(int)
                total_u = len(dfd_clean)
                correct_u = int(dfd_clean[ans_col].sum())
                st.success(f"✅ 전체 {total_u}명, 정답자 {correct_u}명")
                
                c1, c2 = st.columns(2)
                tt_u = c1.radio("검사 종류",
                    ["삼점검정 (Triangle)", "일-이점검정 (Duo-Trio)"], key="t2_tt_u")
                alpha_u = c2.selectbox("유의수준 α", [0.05, 0.01, 0.001], key="t2_a_u")
                
                p0_u = 1/3 if "삼점" in tt_u else 1/2
                r_u = binomtest(correct_u, total_u, p0_u, alternative='greater')
                p_val_u = r_u.pvalue
                
                min_c_u = total_u
                for x in range(total_u+1):
                    if binomtest(x, total_u, p0_u, alternative='greater').pvalue < alpha_u:
                        min_c_u = x
                        break
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("정답률", f"{correct_u/total_u*100:.1f}%")
                m2.metric("p-value", f"{p_val_u:.4f}")
                m3.metric("최소정답자", f"{min_c_u}명")
                m4.metric("결과", "🟢 유의" if p_val_u < alpha_u else "🔴 비유의")
                
                if p_val_u < alpha_u:
                    st.success(f"✅ **유의차 있음** (p={p_val_u:.4f} < α={alpha_u})")
                else:
                    st.warning(f"⚠️ **유의차 없음** (p={p_val_u:.4f} ≥ α={alpha_u})")
                
                c_v1, c_v2 = st.columns(2)
                with c_v1:
                    expected = total_u * p0_u
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=['기대(우연)','실제정답자','최소유의'],
                        y=[expected, correct_u, min_c_u],
                        marker_color=['#94a3b8',
                            '#10b981' if p_val_u < alpha_u else '#f59e0b',
                            '#3b82f6'],
                        text=[f"{expected:.1f}", f"{correct_u}", f"{min_c_u}"],
                        textposition='outside'))
                    fig.update_layout(title="정답자수 비교")
                    st.plotly_chart(fig, use_container_width=True)
                with c_v2:
                    k = np.arange(0, total_u+1)
                    pmf = binom.pmf(k, total_u, p0_u)
                    colors = ['#ef4444' if ki >= min_c_u else '#cbd5e1' for ki in k]
                    fig2 = go.Figure()
                    fig2.add_trace(go.Bar(x=k, y=pmf, marker_color=colors))
                    fig2.add_vline(x=correct_u, line_dash="dash", line_color="green",
                        annotation_text=f"실제({correct_u})")
                    fig2.update_layout(title="이항분포 (빨강=유의영역)")
                    st.plotly_chart(fig2, use_container_width=True)
                
                st.session_state.results['discrimination'] = {
                    'test_type': tt_u, 'n': total_u, 'correct': correct_u,
                    'p_value': p_val_u, 'alpha': alpha_u, 'min_correct': min_c_u,
                    'significant': p_val_u < alpha_u
                }
    
    with sub_b:
        col1, col2 = st.columns(2)
        with col1:
            tt = st.radio("검사 종류",
                ["삼점검정 (Triangle)", "일-이점검정 (Duo-Trio)"], key="t2_tt")
            total_p = st.number_input("전체 패널 수", 5, 500, 30, key="t2_n")
            correct_p = st.number_input("정답자 수", 0, int(total_p), 15, key="t2_c")
            alpha = st.selectbox("유의수준 α", [0.05, 0.01, 0.001], key="t2_a")
        with col2:
            p0 = 1/3 if "삼점" in tt else 1/2
            r = binomtest(correct_p, total_p, p0, alternative='greater')
            p_val = r.pvalue
            min_c = total_p
            for x in range(total_p+1):
                if binomtest(x, total_p, p0, alternative='greater').pvalue < alpha:
                    min_c = x
                    break
            
            st.caption(f"P₀ = {p0:.4f}")
            m1, m2, m3 = st.columns(3)
            m1.metric("정답률", f"{correct_p/total_p*100:.1f}%")
            m2.metric("p-value", f"{p_val:.4f}")
            m3.metric("최소정답", f"{min_c}명")
            
            if p_val < alpha:
                st.success(f"✅ **유의차 있음** (p={p_val:.4f})")
            else:
                st.warning(f"⚠️ **유의차 없음** (p={p_val:.4f})")
            
            st.session_state.results['discrimination'] = {
                'test_type': tt, 'n': total_p, 'correct': correct_p,
                'p_value': p_val, 'alpha': alpha, 'min_correct': min_c,
                'significant': p_val < alpha
            }
    
    with st.expander("📚 표준 최소 정답자수 기준표"):
        st.markdown("**삼점검정 (α=0.05)**")
        st.dataframe(pd.DataFrame({
            '패널수': [12,15,18,20,24,27,30,36,42,48,54,60],
            '최소정답': [8,9,10,11,13,14,15,17,19,21,23,26]
        }).T, use_container_width=True)
        st.markdown("**일-이점검정 (α=0.05)**")
        st.dataframe(pd.DataFrame({
            '패널수': [10,12,15,18,20,24,30,36,42,48],
            '최소정답': [8,9,11,13,15,17,20,23,26,29]
        }).T, use_container_width=True)
    
    if st.button("🤖 Claude AI 해석", key="t2_ai") and st.session_state.api_key:
        r = st.session_state.results.get('discrimination', {})
        if r:
            prompt = f"""{r['test_type']} 결과:
- 패널: {r['n']}명, 정답자: {r['correct']}명
- p-value: {r['p_value']:.4f}, α: {r['alpha']}
- 최소정답자: {r['min_correct']}명
- 결론: {'유의차 있음' if r['significant'] else '유의차 없음'}

식품개발 관점에서 해석해주세요."""
            with st.spinner("해석 중..."):
                interp = call_claude_api(prompt, st.session_state.api_key,
                    st.session_state.claude_model)
                st.session_state.interpretations['discrimination'] = interp
                st.markdown(interp)


# ============================================================================
# TAB 3: 순위법
# ============================================================================

with tabs[2]:
    st.header("🔢 순위법 분석 (Friedman Test)")
    st.info("여러 시료의 **순위 데이터**를 비모수 검정합니다. (1=가장 선호)")
    
    form_manager_ui("t3", "ranking")
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    uploaded_rank = st.file_uploader("순위 데이터 CSV", type="csv", key="t3_up")
    
    if uploaded_rank:
        df_rank_full = pd.read_csv(uploaded_rank)
        st.dataframe(df_rank_full.head(8), use_container_width=True)
        
        numeric_cols = df_rank_full.select_dtypes(include=np.number).columns.tolist()
        panel_col_t3 = st.selectbox("패널 ID 컬럼 (선택사항)",
            ["(없음)"] + list(df_rank_full.columns), key="t3_pc")
        sample_cols_t3 = st.multiselect("시료 컬럼 선택",
            df_rank_full.columns,
            default=[c for c in numeric_cols if c != panel_col_t3][:10],
            key="t3_sc")
        
        if len(sample_cols_t3) >= 3:
            df_rank = df_rank_full[sample_cols_t3].apply(pd.to_numeric, errors='coerce').dropna()
            
            if len(df_rank) < 3:
                st.error("❌ 유효 데이터가 3행 미만입니다. 순위가 입력되었는지 확인하세요.")
            else:
                st.success(f"✅ {len(df_rank)}명 × {len(sample_cols_t3)}시료")
                try:
                    f_stat, p_val = friedmanchisquare(*[df_rank[c] for c in df_rank.columns])
                    
                    st.subheader("📋 Friedman 검정")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Friedman χ²", f"{f_stat:.4f}")
                    c2.metric("p-value", f"{p_val:.4f}")
                    c3.metric("결과", "🟢 유의" if p_val < 0.05 else "🔴 비유의")
                    
                    pair_df = None
                    if p_val < 0.05:
                        st.success("✅ 시료 간 순위 차이 유의")
                        st.subheader("🔬 Wilcoxon 쌍별 비교 (Bonferroni)")
                        cols = df_rank.columns.tolist()
                        n_pairs = len(cols) * (len(cols)-1) // 2
                        bonf_alpha = 0.05 / n_pairs
                        
                        pair_results = []
                        for i in range(len(cols)):
                            for j in range(i+1, len(cols)):
                                try:
                                    stat, p = wilcoxon(df_rank[cols[i]], df_rank[cols[j]])
                                    pair_results.append({
                                        '시료1': cols[i], '시료2': cols[j],
                                        'W-stat': stat, 'p-value': p,
                                        'p-adj(Bonf)': min(p*n_pairs, 1.0),
                                        '유의': '✓' if p < bonf_alpha else '✗'
                                    })
                                except Exception:
                                    pair_results.append({
                                        '시료1': cols[i], '시료2': cols[j],
                                        'W-stat': np.nan, 'p-value': np.nan,
                                        'p-adj(Bonf)': np.nan, '유의': '계산불가'
                                    })
                        pair_df = pd.DataFrame(pair_results)
                        st.dataframe(pair_df, use_container_width=True)
                        st.caption(f"보정 α' = 0.05/{n_pairs} = {bonf_alpha:.4f}")
                    else:
                        st.warning("⚠️ 유의차 없음, 사후검정 생략")
                    
                    st.subheader("📊 시각화")
                    c_v1, c_v2 = st.columns(2)
                    with c_v1:
                        rank_sum = df_rank.sum().sort_values().reset_index()
                        rank_sum.columns = ['시료','순위합']
                        fig = px.bar(rank_sum, x='시료', y='순위합', color='시료',
                            text='순위합', title="시료별 순위합 (낮을수록 선호)",
                            color_discrete_sequence=px.colors.qualitative.Pastel)
                        st.plotly_chart(fig, use_container_width=True)
                    with c_v2:
                        rank_long = df_rank.reset_index().melt(
                            id_vars='index', var_name='시료', value_name='순위')
                        fig2 = px.box(rank_long, x='시료', y='순위', color='시료',
                            title="시료별 순위 분포",
                            color_discrete_sequence=px.colors.qualitative.Pastel)
                        fig2.update_yaxes(autorange="reversed")
                        st.plotly_chart(fig2, use_container_width=True)
                    
                    st.session_state.results['friedman'] = {
                        'f_stat': f_stat, 'p_value': p_val,
                        'rank_sum': rank_sum, 'pairs': pair_df,
                        'n_panel': len(df_rank), 'n_samples': len(df_rank.columns)
                    }
                    
                    if st.button("🤖 Claude AI 해석", key="t3_ai") and st.session_state.api_key:
                        prompt = f"""Friedman 순위 검정:
패널: {len(df_rank)}, 시료: {len(df_rank.columns)}
χ² = {f_stat:.4f}, p = {p_val:.4f}

순위합:
{rank_sum.to_string()}

{'쌍별: ' + chr(10) + pair_df.to_string() if pair_df is not None else ''}

제품개발 관점에서 해석해주세요."""
                        with st.spinner("해석 중..."):
                            interp = call_claude_api(prompt, st.session_state.api_key,
                                st.session_state.claude_model)
                            st.session_state.interpretations['friedman'] = interp
                            st.markdown(interp)
                except Exception as e:
                    st.error(f"분석 오류: {e}")
        else:
            st.info("시료 컬럼을 최소 3개 이상 선택하세요.")


# ============================================================================
# TAB 4: 패널 신뢰도
# ============================================================================

with tabs[3]:
    st.header("👥 패널 신뢰도 평가")
    st.info("반복 측정 데이터로 **재현성/일관성/식별력**을 평가합니다.")
    
    form_manager_ui("t4", "reliability")
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    uploaded_rel = st.file_uploader("반복측정 CSV", type="csv", key="t4_up")
    
    if uploaded_rel:
        df_rel_raw = pd.read_csv(uploaded_rel)
        if '점수' in df_rel_raw.columns:
            df_rel_raw = df_rel_raw[pd.to_numeric(df_rel_raw['점수'], errors='coerce').notna()].copy()
            df_rel_raw['점수'] = df_rel_raw['점수'].astype(float)
        
        if len(df_rel_raw) == 0:
            st.error("❌ 점수가 입력되지 않은 빈 조사지입니다.")
        else:
            df_rel = df_rel_raw.copy()
            st.success(f"✅ {len(df_rel)}행 로드")
            st.dataframe(df_rel.head(10))
            
            c1, c2, c3, c4 = st.columns(4)
            panel_c = c1.selectbox("패널", df_rel.columns,
                index=list(df_rel.columns).index('패널') if '패널' in df_rel.columns else 0,
                key="t4_p")
            sample_c = c2.selectbox("시료", df_rel.columns,
                index=list(df_rel.columns).index('시료') if '시료' in df_rel.columns else 1,
                key="t4_s")
            rep_c = c3.selectbox("반복", df_rel.columns,
                index=list(df_rel.columns).index('반복') if '반복' in df_rel.columns else 2,
                key="t4_r")
            num_cols = df_rel.select_dtypes(include=np.number).columns.tolist()
            score_c = c4.selectbox("점수", num_cols,
                index=num_cols.index('점수') if '점수' in num_cols else 0,
                key="t4_sc") if num_cols else None
            
            if st.button("🔍 신뢰도 분석 실행", type="primary", key="t4_run") and score_c:
                try:
                    cv_data = []
                    for p in df_rel[panel_c].unique():
                        sub = df_rel[df_rel[panel_c] == p]
                        cvs = []
                        for s in sub[sample_c].unique():
                            scores = sub[sub[sample_c] == s][score_c].values
                            if len(scores) > 1 and abs(scores.mean()) > 0:
                                cvs.append(scores.std()/abs(scores.mean())*100)
                        cv_data.append({
                            '패널': p,
                            '평균 CV(%)': np.mean(cvs) if cvs else np.nan,
                            '평균 점수': sub[score_c].mean()
                        })
                    cv_df = pd.DataFrame(cv_data).sort_values('평균 CV(%)')
                    
                    discrim_data = []
                    for p in df_rel[panel_c].unique():
                        sub = df_rel[df_rel[panel_c] == p]
                        groups = [sub[sub[sample_c]==s][score_c].values
                                  for s in sub[sample_c].unique()]
                        groups = [g for g in groups if len(g) >= 2]
                        if len(groups) >= 2:
                            try:
                                f, pv = f_oneway(*groups)
                                discrim_data.append({
                                    '패널': p, 'F-value': f, 'p-value': pv,
                                    '식별력': '🟢 우수' if pv < 0.05 else '🟡 보통' if pv < 0.20 else '🔴 낮음'
                                })
                            except Exception:
                                discrim_data.append({'패널': p, 'F-value': np.nan,
                                    'p-value': np.nan, '식별력': '계산불가'})
                    discrim_df = pd.DataFrame(discrim_data).sort_values('F-value', ascending=False)
                    
                    try:
                        formula = f"Q('{score_c}') ~ C(Q('{panel_c}')) + C(Q('{sample_c}'))"
                        mod = ols(formula, data=df_rel).fit()
                        aov = anova_lm(mod, typ=2)
                        panel_idx = [i for i in aov.index if panel_c in i][0]
                        ms_p = aov.loc[panel_idx, "sum_sq"] / aov.loc[panel_idx, "df"]
                        ms_r = aov.loc["Residual", "sum_sq"] / aov.loc["Residual", "df"]
                        k = df_rel[sample_c].nunique()
                        icc = (ms_p - ms_r) / (ms_p + (k-1)*ms_r)
                    except Exception:
                        icc = np.nan
                    
                    st.subheader("📊 결과")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("ICC", f"{icc:.3f}" if not np.isnan(icc) else "N/A",
                        help="0.75↑우수 / 0.5~0.75보통 / 0.5↓낮음")
                    c2.metric("우수패널",
                        f"{(discrim_df['p-value']<0.05).sum()}/{len(discrim_df)}")
                    c3.metric("평균 CV", f"{cv_df['평균 CV(%)'].mean():.1f}%")
                    
                    st.markdown("#### 🎯 패널별 시료 식별력")
                    st.dataframe(discrim_df, use_container_width=True)
                    st.markdown("#### 🔁 패널별 반복 일관성 (CV)")
                    st.dataframe(cv_df, use_container_width=True)
                    st.caption("CV 10% 이하가 이상적")
                    
                    st.subheader("🗺️ 패널 × 시료 평균 히트맵")
                    pivot = df_rel.groupby([panel_c, sample_c])[score_c].mean().unstack()
                    fig = px.imshow(pivot, text_auto='.2f', aspect='auto',
                        color_continuous_scale='RdYlGn', title="패널별 시료 평균")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    fig_f = px.bar(discrim_df, x='패널', y='F-value',
                        color='식별력', title="패널별 식별력",
                        color_discrete_map={'🟢 우수':'#10b981',
                            '🟡 보통':'#f59e0b','🔴 낮음':'#ef4444'})
                    st.plotly_chart(fig_f, use_container_width=True)
                    
                    st.session_state.results['reliability'] = {
                        'icc': icc, 'cv_df': cv_df,
                        'discrim_df': discrim_df, 'pivot': pivot
                    }
                    
                    if st.session_state.api_key:
                        with st.spinner("Claude 해석 중..."):
                            prompt = f"""패널 신뢰도:
ICC: {icc:.3f}
우수패널: {(discrim_df['p-value']<0.05).sum()}/{len(discrim_df)}
평균 CV: {cv_df['평균 CV(%)'].mean():.1f}%

식별력:
{discrim_df.to_string()}

일관성:
{cv_df.to_string()}

재훈련 권장 패널과 개선방안을 제안해주세요."""
                            interp = call_claude_api(prompt, st.session_state.api_key,
                                st.session_state.claude_model)
                            st.session_state.interpretations['reliability'] = interp
                            st.markdown("### 🤖 Claude AI 해석")
                            st.markdown(interp)
                except Exception as e:
                    st.error(f"분석 오류: {e}")
                    import traceback
                    with st.expander("상세 오류"):
                        st.code(traceback.format_exc())


# ============================================================================
# TAB 5: 블라인드 코드
# ============================================================================

with tabs[4]:
    st.header("🎲 블라인드 코드 자동 생성")
    st.info("관능검사용 **3자리 난수 코드**와 **라틴방격 제시순서**를 자동 생성합니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        n_samples = st.number_input("시료 수", 2, 26, 3, key="t5_ns")
        n_panelists = st.number_input("패널 수", 2, 200, 12, key="t5_np")
        sample_names = st.text_input("시료명 (쉼표 구분)",
            value=",".join([f"시료{chr(65+i)}" for i in range(n_samples)]),
            key="t5_sn")
        seed = st.number_input("난수 시드", value=42, key="t5_seed")
    with col2:
        balanced = st.checkbox("제시순서 균형화 (라틴방격)", True, key="t5_bal")
        unique_per_panel = st.radio("코드 부여 방식",
            ["패널별로 다른 코드 (완전 블라인드)", "시료별로 동일 코드 (간편)"],
            key="t5_upp")
    
    if st.button("🎲 코드 생성", type="primary", key="t5_gen"):
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
                    order = [(s+p)%n_samples for s in range(n_samples)] if balanced else list(range(n_samples))
                    for presentation, s_idx in enumerate(order, 1):
                        rows.append({
                            '패널': f"P{p+1:02d}", '제시순서': presentation,
                            '시료명': names[s_idx], '블라인드코드': codes[s_idx]
                        })
            else:
                sample_codes = random.sample(range(100, 1000), n_samples)
                for p in range(n_panelists):
                    order = [(s+p)%n_samples for s in range(n_samples)] if balanced else list(range(n_samples))
                    for presentation, s_idx in enumerate(order, 1):
                        rows.append({
                            '패널': f"P{p+1:02d}", '제시순서': presentation,
                            '시료명': names[s_idx], '블라인드코드': sample_codes[s_idx]
                        })
            
            code_df = pd.DataFrame(rows)
            st.success(f"✅ 총 {len(code_df)}개 코드 생성")
            
            ta, tb = st.tabs(["📋 상세", "📊 피벗"])
            with ta:
                st.dataframe(code_df, use_container_width=True, height=400)
            with tb:
                pv_code = code_df.pivot(index='패널', columns='제시순서', values='블라인드코드')
                pv_name = code_df.pivot(index='패널', columns='제시순서', values='시료명')
                st.markdown("**블라인드 코드**")
                st.dataframe(pv_code, use_container_width=True)
                st.markdown("**정답지 (실제 시료명)**")
                st.dataframe(pv_name, use_container_width=True)
            
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                df_to_csv_download(code_df, "blind_codes.csv", "📥 CSV 다운로드", key="t5_dl1")
            with c_d2:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                    code_df.to_excel(writer, sheet_name='상세', index=False)
                    pv_code.to_excel(writer, sheet_name='코드피벗')
                    pv_name.to_excel(writer, sheet_name='정답지')
                st.download_button("📥 Excel (3시트)", data=buf.getvalue(),
                    file_name="blind_codes.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="t5_dl2")
            
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
    st.info("현재 세션에서 수행한 모든 분석을 하나의 HTML로 통합합니다. "
             "PDF는 HTML을 브라우저에서 **인쇄 → PDF로 저장**하세요.")
    
    if not st.session_state.results:
        st.warning("⚠️ 수행된 분석이 없습니다. 다른 탭에서 먼저 분석하세요.")
    else:
        labels_map = {
            'anova': '📊 종합차이 (ANOVA)',
            'discrimination': '🔄 차이식별',
            'friedman': '🔢 순위법',
            'reliability': '👥 패널 신뢰도',
            'blind_codes': '🎲 블라인드 코드'
        }
        available = list(st.session_state.results.keys())
        to_include = st.multiselect("포함할 분석", available,
            default=available, format_func=lambda x: labels_map.get(x, x))
        
        project_name = st.text_input("프로젝트명", "Natural Lab Sensory Study")
        author = st.text_input("작성자", "Sweet Lab")
        
        if st.button("📑 HTML 리포트 생성", type="primary", key="t6_gen"):
            html = generate_html_report(project_name, author, to_include,
                st.session_state.results, st.session_state.interpretations)
            st.download_button("📥 HTML 리포트 다운로드",
                data=html.encode('utf-8'),
                file_name=f"sensory_report_{datetime.date.today()}.html",
                mime="text/html", use_container_width=True)
            with st.expander("🔍 미리보기"):
                st.components.v1.html(html, height=800, scrolling=True)
