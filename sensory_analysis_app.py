"""
식품 R&D 관능분석 통합 솔루션 (Full Package v3.0)
=================================================
v3.0 신규:
- ANOVA 7점/9점 척도 선택 + 지표 정의 + 해석 자동 생성
- 차이식별: Claude 기반 연습 시나리오 생성
- 순위법: 3가지 검정법(범위/차이/χ²) 병렬 + 동질군 표시
- 평점법 신규 탭: 12항목 리커트 7점, 3기준 합격 판정
- AI 가상 소비자 조사: 배합비 모드 + 컨셉 모드, 패널 5~30명 조정 가능 (기본 20명)
- 강의 모드 토글: 교재 콘텐츠 자동 펼침
- 핸드아웃 HTML 자동 생성
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import json
import random
import datetime
import requests
from scipy import stats
from scipy.stats import f_oneway, binomtest, friedmanchisquare, wilcoxon, binom, chi2
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
    page_title="식품 R&D 관능분석 통합 솔루션 v3.0",
    layout="wide", page_icon="🧪"
)

# ============================================================================
# Session State 초기화
# ============================================================================

for key, default in [
    ('results', {}), ('api_key', ''),
    ('claude_model', 'claude-sonnet-4-5'),
    ('interpretations', {}),
    ('teaching_mode', False),
    ('ai_sessions', []),  # AI 평가 세션 리스트 (최대 5개)
    ('current_recipe_parse', None),
    ('current_concept_parse', None),
    ('current_flavor_profile', None),
    ('current_concept_profile', None),
    ('current_evaluations', None),
    ('last_scenario', None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Secrets에서 API 키 자동 로드
if not st.session_state.api_key:
    try:
        if 'ANTHROPIC_API_KEY' in st.secrets:
            st.session_state.api_key = st.secrets['ANTHROPIC_API_KEY']
            st.session_state.api_key_source = 'secrets'
    except Exception:
        pass


# ============================================================================
# 기본 스타일 (기능에 필요한 최소 CSS만)
# ============================================================================

BASE_STYLE = """
<style>
/* 강의 모드 하이라이트 박스 */
.teaching-highlight {
    background: #fffbeb;
    border-left: 4px solid #f59e0b;
    padding: 16px;
    margin: 12px 0;
    border-radius: 6px;
    position: relative;
}

.teaching-highlight::before {
    content: "🎓 강의 포인트";
    position: absolute;
    top: -10px;
    left: 12px;
    background: #fff;
    color: #b45309;
    padding: 0 10px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    border: 1px solid #f59e0b;
    border-radius: 3px;
}

.teaching-highlight h4 {
    color: #92400e !important;
    margin-top: 8px;
}

/* 개념 설명 박스 */
.concept-box {
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 6px;
    padding: 16px;
    margin: 10px 0;
}

.concept-box strong {
    color: #0369a1;
}

/* 합격 배지 */
.pass-badge-full {
    background: #dcfce7;
    color: #166534;
    padding: 8px 16px;
    border-radius: 20px;
    display: inline-block;
    font-weight: bold;
    border: 1px solid #86efac;
}

.pass-badge-conditional {
    background: #fef3c7;
    color: #92400e;
    padding: 8px 16px;
    border-radius: 20px;
    display: inline-block;
    font-weight: bold;
    border: 1px solid #fcd34d;
}

.pass-badge-fail {
    background: #fee2e2;
    color: #991b1b;
    padding: 8px 16px;
    border-radius: 20px;
    display: inline-block;
    font-weight: bold;
    border: 1px solid #fca5a5;
}

/* 페르소나 카드 */
.persona-card {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 12px;
    margin: 8px 0;
    transition: all 0.2s;
}

.persona-card:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
}

.persona-card h4 {
    color: #1e40af !important;
    margin: 0 0 8px 0;
    font-size: 14px;
}

.persona-card .demo {
    color: #64748b;
    font-size: 12px;
}

.persona-card .tag {
    display: inline-block;
    background: #dbeafe;
    color: #1e40af;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10px;
    margin: 2px;
}
</style>
"""

st.markdown(BASE_STYLE, unsafe_allow_html=True)


# ============================================================================
# Plotly 공통 테마 (기본 밝은 배경)
# ============================================================================

PLOTLY_THEME = {
    'template': 'plotly_white',
    'colorway': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444',
                  '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'],
}


def apply_plotly_theme(fig, title=None):
    """Plotly figure에 기본 테마 적용"""
    fig.update_layout(
        template='plotly_white',
        colorway=PLOTLY_THEME['colorway'],
    )
    if title:
        fig.update_layout(title=title)
    return fig


# ============================================================================
# 공통 유틸리티
# ============================================================================

def call_claude_api(prompt, api_key, model="claude-sonnet-4-5",
                    system_msg=None, max_tokens=4000, timeout=300, max_retries=2):
    """Claude API REST 호출 (타임아웃 300초 + 재시도 2회)
    
    Args:
        timeout: 응답 대기 시간 (초, 기본 300 = 5분)
        max_retries: 타임아웃/네트워크 오류 시 재시도 횟수
    """
    if not api_key:
        return "⚠️ 사이드바에서 Claude API 키를 입력하세요."
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    if system_msg is None:
        system_msg = (
            "당신은 식품 R&D 전문 통계 컨설턴트입니다. "
            "관능검사 분석 결과를 식품개발자 관점에서 명확하고 실무적으로 해석해주세요. "
            "답변은 한국어로, 마크다운 구조를 활용해 작성하세요."
        )
    payload = {
        "model": model, "max_tokens": max_tokens, "system": system_msg,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()["content"][0]["text"]
        except requests.exceptions.Timeout as e:
            last_error = f"⏱️ 타임아웃 (attempt {attempt + 1}/{max_retries + 1})"
            if attempt < max_retries:
                # 재시도 시 짧은 대기
                import time
                time.sleep(2)
                continue
            return (f"❌ 타임아웃 ({timeout}초): Claude가 응답하지 않습니다.\n"
                    f"• 패널 수를 줄이거나 (권장: 10~15명)\n"
                    f"• 잠시 후 다시 시도해주세요.\n"
                    f"상세: {str(e)[:200]}")
        except requests.exceptions.ConnectionError as e:
            last_error = f"🌐 연결 오류 (attempt {attempt + 1}/{max_retries + 1})"
            if attempt < max_retries:
                import time
                time.sleep(3)
                continue
            return f"❌ 네트워크 연결 실패: {str(e)[:200]}"
        except requests.exceptions.HTTPError as e:
            status = r.status_code if 'r' in dir() else 'N/A'
            if status == 429:  # Rate limit
                if attempt < max_retries:
                    import time
                    time.sleep(10)  # 10초 대기 후 재시도
                    continue
                return f"❌ API 사용량 한도 초과 (429). 잠시 후 다시 시도하세요."
            elif status == 529:  # Overloaded
                if attempt < max_retries:
                    import time
                    time.sleep(5)
                    continue
                return f"❌ Anthropic 서버 과부하 (529). 잠시 후 재시도하세요."
            return f"❌ API 오류 ({status}): {r.text[:300] if 'r' in dir() else str(e)[:200]}"
        except Exception as e:
            return f"❌ 호출 오류: {str(e)[:200]}"
    
    return f"❌ 재시도 모두 실패: {last_error}"


def call_claude_api_json(prompt, api_key, model="claude-sonnet-4-5",
                          system_msg=None, max_tokens=6000, timeout=300):
    """Claude API 호출 후 JSON 파싱 시도 (타임아웃 연장)"""
    response = call_claude_api(prompt, api_key, model, system_msg, max_tokens, timeout)
    if response.startswith("❌") or response.startswith("⚠️"):
        return None, response
    # JSON 추출 시도
    try:
        text = response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        text = text.strip()
        if "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            parsed = json.loads(text[start:end])
            return parsed, response
        elif "[" in text and "]" in text:
            start = text.index("[")
            end = text.rindex("]") + 1
            parsed = json.loads(text[start:end])
            return parsed, response
        return None, response
    except Exception as e:
        return None, f"JSON 파싱 실패: {str(e)}\n원본 (처음 500자): {response[:500]}"


def df_to_csv_download(df, filename, label, key=None, help_text=None):
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(label, data=csv, file_name=filename,
        mime="text/csv", key=key, help=help_text, use_container_width=True)


def teaching_box(title, content, always_open=False):
    """교재 콘텐츠 박스 (강의 모드에서 자동 펼침)"""
    expanded = st.session_state.teaching_mode or always_open
    with st.expander(f"📖 {title}", expanded=expanded):
        st.markdown(f'<div class="concept-box">{content}</div>',
                    unsafe_allow_html=True)


def teaching_highlight(content):
    """강의 포인트 하이라이트 박스 (강의 모드에서만 표시)"""
    if st.session_state.teaching_mode:
        st.markdown(
            f'<div class="teaching-highlight">{content}</div>',
            unsafe_allow_html=True
        )


def info_tooltip(label, tip):
    """레이블 + 툴팁 형태 (메트릭 옆 ℹ 정보)"""
    return st.popover(f"ℹ {label}", use_container_width=False)


# ============================================================================
# 교재 콘텐츠 (Teaching Content)
# ============================================================================

TEACHING_CONTENT = {
    'anova_concept': """
<strong>▸ 평점법(Rating Scale Method)이란?</strong><br>
여러 시료의 품질 특성을 9점 또는 7점 척도에 점수화하여 정량적으로 비교하는 방법입니다.<br><br>

<strong>▸ 언제 사용하는가?</strong><br>
• 시료 간 품질 차이의 <em>크기</em>를 알고 싶을 때<br>
• 어떤 시료가 얼마나 더 나은지 수치로 비교할 때<br>
• 소비자 수용성의 정량 평가가 필요할 때<br><br>

<strong>▸ 삼점검정과의 차이</strong><br>
• <strong>삼점검정</strong>: "차이가 있나?" (이진 판단)<br>
• <strong>평점법</strong>: "얼마나 차이가 있나?" (정도 비교)<br><br>

<strong>▸ 7점/9점 척도 선택 기준</strong><br>
• <strong>9점</strong>: 정밀 분석, 전문 패널, 미세 차이 감지<br>
• <strong>7점</strong>: 일반 소비자, 리커트 기반, 해석 용이
""",

    'anova_metrics': """
<strong>▸ F-value</strong><br>
시료 간 분산 대비 오차 분산의 비율. 클수록 시료 간 차이가 뚜렷합니다.<br>
일반적 기준: <code>F > 3</code> 이상이면 주목할 만한 차이.<br><br>

<strong>▸ p-value</strong><br>
"시료들이 동일하다"는 귀무가설이 맞을 확률. 작을수록 유의한 차이.<br>
• <code>p < 0.05</code>: 유의한 차이<br>
• <code>p < 0.01</code>: 매우 유의한 차이<br>
• <code>p < 0.001</code>: 극도로 유의한 차이<br><br>

<strong>▸ p-adj (Tukey HSD)</strong><br>
다중 비교 시 누적되는 오류를 보정한 p-value.<br>
3개 이상 시료 비교 시 필수 사용.<br><br>

<strong>▸ Two-way ANOVA</strong><br>
두 요인(시료 + 패널)의 영향을 분리 분석.<br>
• 패널 효과 유의 → 평가자 간 편차 존재 (재훈련 고려)<br>
• 시료 효과만 유의 → 순수한 시료 차이 검출
""",

    'anova_teaching': """
<h4>강의 시 강조할 3가지 포인트</h4>
<strong>1. F값과 실무 차이의 구분</strong><br>
F값이 크다고 무조건 의미 있는 차이는 아닙니다. 통계적 유의성과 실무적 차이
(평균값의 크기)는 다릅니다. 예: F=100이지만 평균차 0.1점이면 실무 무의미.<br><br>

<strong>2. Tukey HSD vs Bonferroni</strong><br>
• Tukey: 쌍별 비교에 최적화 (일반적 선택)<br>
• Bonferroni: 보수적 (유의차 놓치기 쉬움)<br><br>

<strong>3. 패널 효과 해석</strong><br>
Two-way ANOVA에서 패널 효과가 시료 효과보다 크다면
패널 훈련이 부족합니다. Tab 5(패널 신뢰도) 참조하세요.
""",

    'discrimination_concept': """
<strong>▸ 차이식별 검정이란?</strong><br>
두 시료 간 <em>감지 가능한 차이</em>의 유무를 판정하는 방법입니다.
차이의 크기는 측정하지 않고, 있다/없다만 판단합니다.<br><br>

<strong>▸ 삼점검정 (Triangle Test)</strong><br>
• 3개 시료 중 2개는 같고 1개 다름 → 다른 것 찾기<br>
• 우연 정답 확률: 1/3 (33.3%)<br>
• 사용: 원료 대체, 공정 변경의 감지 여부<br><br>

<strong>▸ 일-이점검정 (Duo-Trio Test)</strong><br>
• 기준시료 R 제시 후, 2개 중 R과 같은 것 찾기<br>
• 우연 정답 확률: 1/2 (50%)<br>
• 사용: 기준품이 명확할 때, 친숙한 제품 비교<br><br>

<strong>▸ 선택 기준</strong><br>
기준이 있음 → 일-이점 / 기준이 없음 → 삼점
""",

    'discrimination_teaching': """
<h4>실무 Tips</h4>
<strong>1. 패널 수의 중요성</strong><br>
• 삼점검정: 30명 이상 권장<br>
• 일-이점검정: 20명 이상 권장<br>
패널이 적으면 검정력이 부족해 실제 차이를 놓칠 수 있습니다.<br><br>

<strong>2. "유의차 없음"의 의미</strong><br>
유의차가 없다고 해서 "두 시료가 동일하다"는 뜻이 아닙니다.
"현재 패널로는 차이를 감지하지 못했다"는 의미입니다.
동등성 검정은 별도 방법(equivalence test)이 필요합니다.<br><br>

<strong>3. 재훈련 판단 기준</strong><br>
훈련 패널의 삼점검정 정답률이 70% 미만을 반복한다면
재훈련 또는 패널 교체를 고려해야 합니다.
""",

    'ranking_concept': """
<strong>▸ 순위법이란?</strong><br>
비모수 검정의 일종으로, 각 패널이 시료에 순위(1, 2, 3...)를 부여하고
순위합으로 시료 간 차이를 판정합니다.<br><br>

<strong>▸ 장점</strong><br>
• 정규분포 가정 불필요 (비모수)<br>
• 소규모 패널에도 적용 가능<br>
• 이상치에 강함<br>
• 훈련되지 않은 패널도 가능<br><br>

<strong>▸ 단점</strong><br>
• 차이의 크기 정보 손실 (순서만 남음)<br>
• 동점 허용 안 됨 (엄격한 순위)<br>
• 많은 시료 비교 시 어려움 (5개 이상 권장 X)
""",

    'ranking_three_tests': """
<h4>3가지 검정법 비교</h4>
<strong>(1) 순위합 범위 검정 (Kramer's Rank Sum)</strong><br>
• 용도: 개별 시료가 <em>특이값</em>인지 판정<br>
• 방식: 순위합이 유의 범위 <code>[R_lower, R_upper]</code> 밖에 있으면 유의<br>
• 장점: 빠른 스크리닝<br><br>

<strong>(2) 순위합 차이값 검정 ⭐ (동질군 표시 기준)</strong><br>
• 용도: 시료끼리 <em>쌍별 비교</em><br>
• 방식: 두 시료의 순위합 차이가 임계값 이상이면 유의<br>
• 임계값: <code>z × √(n×k×(k+1)/6)</code><br>
• 출력: a, b, ab 동질군 문자<br><br>

<strong>(3) Friedman χ² 검정</strong><br>
• 용도: 전체 시료 간 <em>어딘가에 차이가 있는가?</em><br>
• 공식: <code>χ² = 12/[n×k×(k+1)] × ΣR² - 3n(k+1)</code><br>
• 자유도: k-1 (시료 수 - 1)<br><br>

<strong>▸ 실무 순서</strong><br>
1. Friedman χ² → 전체 차이 유무 확인<br>
2. 차이 있다면 → 순위합 차이 검정으로 쌍별 비교<br>
3. 동질군(a, b, ab) 표시로 시각화 → 보고서
""",

    'ranking_homogeneous': """
<h4>동질군 (a, b, ab) 해석</h4>
<strong>▸ 기본 원리</strong><br>
같은 문자를 공유하는 시료끼리는 통계적으로 유의한 차이가 없음을 의미합니다.<br><br>

<strong>▸ 예시</strong><br>
<code>시료 A (a) / 시료 B (ab) / 시료 C (b)</code><br>
• A와 B는 'a'를 공유 → 차이 <strong>없음</strong><br>
• B와 C는 'b'를 공유 → 차이 <strong>없음</strong><br>
• A와 C는 공유 문자 없음 → 유의한 <strong>차이 있음</strong><br><br>

<strong>▸ 보고서 해석 예시</strong><br>
"A는 C보다 유의하게 선호되었으나, B는 A, C 둘 다와 구분되지 않는다.
B는 A와 C의 중간적 특성을 보인다."
""",

    'ranking_teaching': """
<h4>순위법의 숨은 함정</h4>
<strong>1. 동점 처리 문제</strong><br>
엄격한 순위는 동점을 허용하지 않습니다. 그러나 실무에서
"어떤 것이 더 좋은지 모르겠다"는 경우가 흔하며, 강제 순위화가
데이터 왜곡을 일으킬 수 있습니다.<br><br>

<strong>2. 자유도(df)의 이해</strong><br>
자유도는 "자유롭게 변할 수 있는 값의 개수"입니다.<br>
• 시료 k개 → df = k - 1<br>
• 예: 시료 4개 → df = 3 → χ²(0.05, df=3) = 7.815<br>
이 임계값은 암기할 필요 없지만 <em>원리</em>는 이해해야 합니다.<br><br>

<strong>3. 언제 평점법 대신 순위법?</strong><br>
• 전문 패널 훈련이 어려울 때<br>
• 빠른 선호도 조사가 필요할 때<br>
• 점수의 절대값보다 상대 우위가 중요할 때<br>
• 소비자가 척도 사용에 익숙하지 않을 때
""",

    'scaling_concept': """
<strong>▸ 평점법(Scaling Test)이란?</strong><br>
리커트 척도 등으로 여러 속성을 동시 평가하는 방법입니다.
제품의 다차원 품질 프로파일을 얻을 수 있습니다.<br><br>

<strong>▸ 기호도 조사 vs 평점법</strong><br>
• <strong>기호도</strong>: "얼마나 좋은가?" (소비자 수용성)<br>
• <strong>평점법</strong>: "각 속성이 어떠한가?" (다차원 특성)<br><br>

<strong>▸ 리커트 7점 척도 (관능강도형)</strong><br>
1 = 매우 약함 / 매우 나쁨<br>
4 = 보통<br>
7 = 매우 강함 / 매우 좋음<br><br>

<strong>▸ 합격 기준의 의미</strong><br>
• 전반적 맛 ≥ 5.0: 소비자 수용 가능 수준<br>
• 구입 의향 ≥ 5.0: 실제 구매 행동 연결 가능<br>
• 전반 만족도 ≥ 5.0: 재구매 의향<br>
3기준 모두 충족 시 시장 출시 가능성이 높습니다.
""",

    'scaling_questionnaire_design': """
<h4>조사지 설계 원리</h4>
<strong>▸ 페이지 분리의 중요성</strong><br>
한 페이지에 여러 속성을 묶으면 이전 응답이 다음 응답에 영향(오염)을
미칩니다. 주요 속성은 별도 페이지에 배치합니다.<br><br>

<strong>▸ 평가 순서의 의미</strong><br>
<code>시각 → 외관 → 시음 → 끝맛 → 종합</code><br>
소비자의 실제 제품 경험 순서를 따라야 자연스러운 평가가 가능합니다.<br><br>

<strong>▸ 정량(척도) + 정성(서술) 혼합</strong><br>
점수만으로는 <em>"왜 그런 점수를 줬는지"</em> 알 수 없습니다.
자유 서술 공간을 두어 정성 데이터를 함께 수집합니다.<br><br>

<strong>▸ 구매 의향 배치</strong><br>
구매 의향을 종합 만족도 <em>앞에</em> 배치하면 편향을 줄일 수 있습니다.
(만족도 → 구매의향 순서는 만족도가 구매의향을 과대평가하게 만듦)<br><br>

<strong>▸ 12항목 선정 근거</strong><br>
실제 업계 표준 조사지(25항목)를 연구 목적에 맞게 핵심 12항목으로 축약했습니다.
제품 카테고리에 따라 추가/변경 가능합니다.
""",

    'ai_panel_overview': """
<strong>⚠️ AI 가상 소비자 조사의 목적과 한계</strong><br><br>

<strong>✓ 적합한 사용</strong><br>
• 초기 컨셉/배합 탐색 단계의 방향성 파악<br>
• 실제 조사 전 가설 수립 및 예상 결과 시뮬레이션<br>
• 교육/훈련 자료로 활용<br>
• 여러 대안 간 상대적 비교<br><br>

<strong>✗ 부적합한 사용</strong><br>
• 실제 제품 출시 결정의 <em>유일한 근거</em>로 사용 금지<br>
• 안전성 평가나 법적 근거로 사용 금지<br>
• 소수/특수 소비자 집단의 정확한 반응 예측 불가<br>
• 실제 관능 수치 대체 불가
""",

    'ai_panel_mechanism': """
<h4>AI 가상 패널의 동작 원리 (3단계)</h4>

<strong>Stage 0: 입력 정규화</strong><br>
자유 텍스트로 입력한 배합비나 컨셉을 Claude가 식품공학 지식을 활용해
구조화된 데이터로 변환합니다. 누락 정보는 추정치로 보완하되 투명하게 표시합니다.<br><br>

<strong>Stage 1: 프로파일 추론</strong><br>
• 배합비 모드: 예상 Brix, pH, 맛 노트, 강도 등 <em>관능 특성 프로파일</em> 추론<br>
• 컨셉 모드: 예상 소비자 첫인상, 경쟁 제품, 가격 인식 등 <em>인식 프로파일</em> 추론<br>
주의: 추정치일 뿐이며 실제 측정값과 오차가 존재합니다.<br><br>

<strong>Stage 2: 페르소나 평가</strong><br>
설정된 수의 가상 패널(기본 20명, 5~30명 조정 가능)이 각자의 고유 특성
(인구통계/선호/미각/구매성향)을 반영해 8개 항목에 점수를 부여하고
자연어 코멘트를 작성합니다.<br><br>

<strong>총 API 호출: 3회 / 소요 시간 약 30초 (패널 수에 따라 가변)</strong>
""",

    'ai_panel_training': """
<h4>AI는 정말로 '훈련'된 것인가?</h4>

❌ 엄밀히 말하면 '훈련(training)'이 아닙니다.<br><br>

현재 AI 기술의 소비자 시뮬레이션은 다음 기법들로 작동합니다:<br><br>

<strong>1. 프롬프트 엔지니어링 (Prompt Engineering)</strong><br>
각 페르소나의 특성을 상세히 지시합니다.<br><br>

<strong>2. 인컨텍스트 학습 (In-Context Learning)</strong><br>
실제 소비자 리뷰 예시를 프롬프트에 포함하여 톤과 패턴을 모방합니다.<br><br>

<strong>3. Chain-of-Thought 추론</strong><br>
단계별 사고 과정을 거쳐 판단하도록 유도합니다.<br><br>

<strong>4. 제약 조건 (Response Constraints)</strong><br>
답변 분포의 다양성을 강제합니다 (예: 극단값이 최소 2명 이상 나오도록).<br><br>

→ 진짜 '훈련'(모델 가중치 수정)은 API 사용자에겐 불가능.
대신 <strong>'페르소나 주입(Persona Injection)'</strong>으로 유사 효과를 달성합니다.<br><br>

<strong>교육 포인트</strong><br>
AI 도구를 올바로 활용하려면 "무엇이 가능하고, 무엇이 불가능한지"를
구분하는 것이 중요합니다.
""",

    'ai_panel_modes': """
<h4>배합비 모드 vs 컨셉 모드</h4>

<strong>🧪 배합비 모드 — "맛이 어떨까?" (R&D 관점)</strong><br>
적합한 질문:<br>
• 새 원료로 대체해도 맛이 유지될까?<br>
• 이 배합이 소비자 수용 가능할까?<br>
• 어느 버전이 맛이 더 나을까?<br>
평가 항목: 맛, 색상, 풍미, 단맛, 식감, 끝맛, 만족도, 구입의향<br><br>

<strong>💭 컨셉 모드 — "시장에서 먹힐까?" (마케팅 관점)</strong><br>
적합한 질문:<br>
• 이 포지셔닝이 타겟에 먹힐까?<br>
• 가격이 수용 가능할까?<br>
• 차별화 인식이 형성될까?<br>
평가 항목: 컨셉 매력, 타겟 적합성, 차별화, 신뢰도, 가격, 건강이미지, 프리미엄, 구입의향<br><br>

<strong>⭐ 권장 실무 워크플로</strong><br>
[1] 컨셉 모드 → 컨셉 검증 → 합격 컨셉 선정<br>
[2] 배합비 모드 → 맛 검증 → 최적 배합 선정<br>
[3] 실제 조사 → 최종 검증 → 출시 결정<br><br>

각 단계마다 검증해야 리스크를 최소화할 수 있습니다.
""",
}


# ============================================================================
# 조사지 생성 함수 (기존 유지)
# ============================================================================

def gen_anova_form(n_panels, samples, scale=9, random_fill=False, seed=None):
    """ANOVA Long format (패널 × 시료)
    scale: 9 또는 7 (척도 점수)
    """
    if seed is not None:
        np.random.seed(seed)
    rows = []
    if random_fill:
        mid = (scale + 1) / 2
        base_means = np.random.uniform(mid - 1, mid + 1.5, len(samples))
        base_means = np.sort(base_means)
        for i in range(1, len(base_means)):
            if base_means[i] - base_means[i-1] < 0.8:
                base_means[i] = base_means[i-1] + np.random.uniform(0.8, 1.5)
        base_means = np.clip(base_means, 2, scale - 0.5)
        np.random.shuffle(base_means)
        sample_means = dict(zip(samples, base_means))
    
    for p in range(n_panels):
        panel_bias = np.random.normal(0, 0.3) if random_fill else 0
        for s in samples:
            row = {'패널': f'P{p+1:02d}', '시료': s}
            if random_fill:
                score = np.random.normal(sample_means[s] + panel_bias, 0.7)
                row['점수'] = int(np.clip(round(score), 1, scale))
            else:
                row['점수'] = ''
            rows.append(row)
    return pd.DataFrame(rows)


def gen_discrimination_form(n_panels, test_type, random_fill=False,
                             p_true=0.55, seed=None):
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
            panel_noise = np.random.uniform(0.3, 0.7) if np.random.random() < 0.8 else np.random.uniform(1.0, 1.8)
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


# 평점법 12항목 정의
SCALING_ATTRIBUTES = [
    '전반적 만족도', '구입 의향', '색상', '전반적 맛',
    '풍미', '재료 맛 조화', '재료 고유의 맛', '단맛',
    '쓴맛', '전반적 식감', '재료 식감 조화', '끝맛 여운'
]

SCALING_PASS_CRITERIA = ['전반적 만족도', '구입 의향', '전반적 맛']


def gen_scaling_form(n_panels, product_name="시료A", random_fill=False, 
                      pass_scenario=True, seed=None):
    """평점법 (Scaling) 조사지 - 패널 × 12항목 (리커트 7점)
    pass_scenario: True=합격 시나리오 생성, False=불합격
    """
    if seed is not None:
        np.random.seed(seed)
    rows = []
    if random_fill:
        # 항목별 기본 평균 (합격/불합격 시나리오)
        if pass_scenario:
            base_mean = {attr: np.random.uniform(5.2, 6.3) for attr in SCALING_ATTRIBUTES}
        else:
            base_mean = {attr: np.random.uniform(3.5, 4.8) for attr in SCALING_ATTRIBUTES}
    
    for p in range(n_panels):
        panel_bias = np.random.normal(0, 0.4) if random_fill else 0
        row = {'패널': f'P{p+1:02d}', '시료': product_name}
        for attr in SCALING_ATTRIBUTES:
            if random_fill:
                score = np.random.normal(base_mean[attr] + panel_bias, 0.8)
                row[attr] = int(np.clip(round(score), 1, 7))
            else:
                row[attr] = ''
        rows.append(row)
    return pd.DataFrame(rows)
# ============================================================================
# 페르소나 20명 (고정 프로필) — 한국 인구 분포 반영
# ============================================================================

PERSONA_PANEL_20 = [
    # ─── 20대 여성 (3명) ───
    {
        "id": "P01", "name": "김민지", "age": 24, "gender": "여",
        "region": "서울 관악구", "occupation": "대학원생",
        "lifestyle": "SNS 활발, 카페 투어, 최근 다이어트 시작",
        "loves": ["복숭아", "딸기", "부드러운 단맛", "탄산"],
        "hates": ["쓴맛", "과한 산미", "인공 향"],
        "taste_profile": "단맛 선호, 쓴맛 내성 낮음, 부드러운 텍스처 선호",
        "purchase": "가격민감 중, 건강의식 상승중, 신제품 적극 시도",
        "bias": "관대 (+0.3)",
        "comment_style": "이모지 사용, 짧은 문장, SNS 어투"
    },
    {
        "id": "P02", "name": "이서연", "age": 26, "gender": "여",
        "region": "서울 마포구", "occupation": "디자이너",
        "lifestyle": "홈카페 매니아, 인테리어 관심",
        "loves": ["커피", "진한 초콜릿", "시트러스"],
        "hates": ["과한 인공감미료", "흐릿한 맛"],
        "taste_profile": "쓴맛 내성 높음, 진한 맛 선호, 복합적 풍미 선호",
        "purchase": "가격 둔감, 프리미엄 선호, 디자인 중시",
        "bias": "엄격 (-0.2)",
        "comment_style": "감성적, 심미적 표현"
    },
    {
        "id": "P03", "name": "박예린", "age": 22, "gender": "여",
        "region": "경기 수원", "occupation": "대학생 4학년",
        "lifestyle": "편의점 자주 이용, 예산 제한",
        "loves": ["젤리", "바닐라", "밀크티", "탄산음료"],
        "hates": ["씁쓸함", "알코올", "너무 진한 맛"],
        "taste_profile": "단맛 적극 선호, 부드러운 맛, 간편함 중시",
        "purchase": "가격매우민감, 브랜드 낮음, 충동구매",
        "bias": "관대 (+0.4)",
        "comment_style": "간결, 솔직, 직설적"
    },
    # ─── 30대 여성 (3명) ───
    {
        "id": "P04", "name": "정수진", "age": 32, "gender": "여",
        "region": "서울 송파구", "occupation": "회사원 (마케팅)",
        "lifestyle": "워킹맘, 효율 중시, 건강 관리",
        "loves": ["감칠맛", "견과류", "그릭요거트"],
        "hates": ["과한 단맛", "인공 색소", "자극적 향"],
        "taste_profile": "균형 선호, 자연스러운 맛 추구",
        "purchase": "건강의식 높음, 라벨 확인, 중고가격대",
        "bias": "중립 (0.0)",
        "comment_style": "분석적, 실용적"
    },
    {
        "id": "P05", "name": "한지영", "age": 35, "gender": "여",
        "region": "인천 연수구", "occupation": "프리랜서",
        "lifestyle": "홈베이킹 취미, 비건 지향 (부분)",
        "loves": ["천연 재료", "허브", "은은한 과일향"],
        "hates": ["합성 향료", "아스파탐", "과한 첨가물"],
        "taste_profile": "천연 맛 선호, 인공 성분 거부, 섬세함",
        "purchase": "성분표 필독, 유기농 선호, 프리미엄",
        "bias": "인공성분에 엄격 (-0.5)",
        "comment_style": "상세, 성분 분석, 대안 제안"
    },
    {
        "id": "P06", "name": "최유나", "age": 38, "gender": "여",
        "region": "부산 수영구", "occupation": "초등학교 교사",
        "lifestyle": "자녀 둘, 가족 건강 중심",
        "loves": ["자극 적은 맛", "영양 보완", "친숙한 맛"],
        "hates": ["강한 탄산", "인공 색소", "모르는 원료"],
        "taste_profile": "안정적, 보수적, 친숙함 선호",
        "purchase": "검증된 브랜드, 가족 단위 구매",
        "bias": "중립적 보수 (0.0)",
        "comment_style": "가족 관점, 자녀 언급"
    },
    # ─── 40대 여성 (3명) ───
    {
        "id": "P07", "name": "강혜경", "age": 42, "gender": "여",
        "region": "서울 강남구", "occupation": "변호사",
        "lifestyle": "바쁜 전문직, 프리미엄 선호",
        "loves": ["고급 와인", "담백함", "깊은 풍미"],
        "hates": ["유치한 단맛", "싸구려 느낌"],
        "taste_profile": "성숙한 미각, 복잡성 선호, 품질 중시",
        "purchase": "가격 둔감, 고급 브랜드, 희소성",
        "bias": "엄격 (-0.3)",
        "comment_style": "격식있고 전문적"
    },
    {
        "id": "P08", "name": "윤미영", "age": 45, "gender": "여",
        "region": "대전 서구", "occupation": "주부 (전업)",
        "lifestyle": "가족 중심, 절약, 전통 선호",
        "loves": ["한식 베이스", "은은한 단맛", "차류"],
        "hates": ["강한 자극", "낯선 외국 재료"],
        "taste_profile": "전통적, 친숙한 맛, 은은함 선호",
        "purchase": "가격민감, 대용량, 가족용",
        "bias": "중립 (0.0)",
        "comment_style": "소박, 실용적"
    },
    {
        "id": "P09", "name": "임선애", "age": 48, "gender": "여",
        "region": "광주 북구", "occupation": "자영업 (카페)",
        "lifestyle": "미각 훈련됨, 신제품 호기심",
        "loves": ["스페셜티 커피", "과일 풍미", "복합미"],
        "hates": ["단순한 맛", "균형 없는 배합"],
        "taste_profile": "전문적 미각, 분석적, 밸런스 중시",
        "purchase": "연구 목적 구매, 원가 대비 가치",
        "bias": "전문가 시각 (0.0)",
        "comment_style": "전문적, 기술적 용어"
    },
    # ─── 50대+ 여성 (2명) ───
    {
        "id": "P10", "name": "오경숙", "age": 55, "gender": "여",
        "region": "대구 수성구", "occupation": "은퇴 준비 (교사)",
        "lifestyle": "건강 적극 관리, 전통 중시",
        "loves": ["녹차", "약재 차", "담백한 맛"],
        "hates": ["과한 단맛", "인공 첨가물", "강한 탄산"],
        "taste_profile": "건강 지향, 담백 선호, 보수적",
        "purchase": "건강 기능성, 검증된 제품",
        "bias": "단맛·인공성분 엄격 (-0.4)",
        "comment_style": "신중, 건강 우선"
    },
    {
        "id": "P11", "name": "김명순", "age": 62, "gender": "여",
        "region": "충남 천안", "occupation": "은퇴",
        "lifestyle": "전통 선호, 손주 간식 구매",
        "loves": ["친숙한 맛", "한국 전통 맛", "영양"],
        "hates": ["낯선 맛", "강한 향", "복잡한 성분"],
        "taste_profile": "전통적, 단순함 선호, 익숙함",
        "purchase": "친숙 브랜드, 손주 중심",
        "bias": "새로운 것에 소극 (-0.2)",
        "comment_style": "소박, 어르신 어투"
    },
    # ─── 20대 남성 (2명) ───
    {
        "id": "P12", "name": "김태훈", "age": 25, "gender": "남",
        "region": "서울 영등포구", "occupation": "IT 개발자",
        "lifestyle": "에너지드링크 애호, 야근 많음",
        "loves": ["강한 맛", "카페인", "탄산", "단맛"],
        "hates": ["밍밍함", "약한 강도"],
        "taste_profile": "강한 맛 선호, 자극 추구, 단맛 수용",
        "purchase": "가격 중, 편의성, 구독 서비스",
        "bias": "강한 맛에 관대 (+0.3)",
        "comment_style": "테크 블로거 스타일, 분석적"
    },
    {
        "id": "P13", "name": "박지훈", "age": 28, "gender": "남",
        "region": "서울 서초구", "occupation": "스타트업 직원",
        "lifestyle": "운동 매니아, 단백질 보충",
        "loves": ["담백함", "프로틴 관련", "깔끔한 맛"],
        "hates": ["과한 설탕", "칼로리 높은 음료"],
        "taste_profile": "건강 지향, 운동 중심, 담백 선호",
        "purchase": "건강 기능 우선, 성분 확인",
        "bias": "당분 엄격 (-0.3)",
        "comment_style": "피트니스 관점, 성분 중시"
    },
    # ─── 30대 남성 (3명) ───
    {
        "id": "P14", "name": "정민호", "age": 32, "gender": "남",
        "region": "경기 분당", "occupation": "회사원 (대기업)",
        "lifestyle": "가정 있음, 실용주의",
        "loves": ["맥주", "스포츠 음료", "친숙한 맛"],
        "hates": ["낯선 조합", "과한 단맛"],
        "taste_profile": "중립적, 실용적, 검증 선호",
        "purchase": "중가격대, 편의점 주 이용",
        "bias": "중립 (0.0)",
        "comment_style": "간결, 평범함"
    },
    {
        "id": "P15", "name": "이동현", "age": 35, "gender": "남",
        "region": "울산", "occupation": "엔지니어 (중공업)",
        "lifestyle": "맥주 애호, 등산 취미",
        "loves": ["쌉쌀함", "깊은 풍미", "보리차"],
        "hates": ["과한 감미료", "물탄 느낌"],
        "taste_profile": "쓴맛 선호, 진한 맛, 바디감 중시",
        "purchase": "가격 중, 주류 애호",
        "bias": "엄격 (-0.2)",
        "comment_style": "직설적, 경험 기반"
    },
    {
        "id": "P16", "name": "최영수", "age": 38, "gender": "남",
        "region": "대전", "occupation": "공무원",
        "lifestyle": "자녀 있음, 안정 추구",
        "loves": ["대중적 맛", "한국식 음료", "전통"],
        "hates": ["실험적 맛", "과한 트렌드"],
        "taste_profile": "보수적, 안정감, 대중성 선호",
        "purchase": "검증 우선, 대중 브랜드",
        "bias": "보수적 (-0.1)",
        "comment_style": "무난, 보편적"
    },
    # ─── 40대 남성 (2명) ───
    {
        "id": "P17", "name": "박성호", "age": 45, "gender": "남",
        "region": "부산 해운대", "occupation": "회사 부장",
        "lifestyle": "주말 등산, 전통차 애호, 건강 관리",
        "loves": ["녹차", "담백한 맛", "은근한 감칠맛"],
        "hates": ["과한 단맛", "인공 향료", "강한 탄산"],
        "taste_profile": "담백·보수, 쓴맛 내성 매우 높음",
        "purchase": "원재료 중시, 라벨 꼼꼼히 확인",
        "bias": "엄격 (-0.4)",
        "comment_style": "진지, 구체적 이유 제시"
    },
    {
        "id": "P18", "name": "장재욱", "age": 48, "gender": "남",
        "region": "인천", "occupation": "중소기업 임원",
        "lifestyle": "접대 많음, 가끔 폭음",
        "loves": ["숙취 해소류", "시원한 음료", "진한 맛"],
        "hates": ["약한 강도", "단조로움"],
        "taste_profile": "강한 맛 선호, 기능성 중시",
        "purchase": "중상 가격, 기능 음료 애호",
        "bias": "중립 (0.0)",
        "comment_style": "실용적, 기능 중심"
    },
    # ─── 50대+ 남성 (2명) ───
    {
        "id": "P19", "name": "김대석", "age": 55, "gender": "남",
        "region": "강원 춘천", "occupation": "자영업 (한식당)",
        "lifestyle": "전통 식문화, 건강 관심",
        "loves": ["구수한 맛", "식혜", "전통 음료"],
        "hates": ["서양식 단맛", "낯선 향"],
        "taste_profile": "전통 지향, 구수함 선호, 보수적",
        "purchase": "전통 브랜드, 경험 기반",
        "bias": "전통 외 엄격 (-0.3)",
        "comment_style": "한국적, 전통 언급"
    },
    {
        "id": "P20", "name": "윤태선", "age": 63, "gender": "남",
        "region": "제주", "occupation": "은퇴 (공무원)",
        "lifestyle": "건강 최우선, 단조로운 식단",
        "loves": ["담백함", "약재 차", "순한 맛"],
        "hates": ["자극", "강한 단맛", "복잡한 향"],
        "taste_profile": "매우 담백, 자극 회피, 단순 선호",
        "purchase": "건강 기능 우선, 신중",
        "bias": "자극에 매우 엄격 (-0.5)",
        "comment_style": "조심스러움, 건강 우선"
    },
    # ─── 확장 풀 (P21~P30) — 사용자가 20명 초과 지정 시 사용 ───
    {
        "id": "P21", "name": "송가영", "age": 23, "gender": "여",
        "region": "서울 강북구", "occupation": "인플루언서 준비생",
        "lifestyle": "트렌드 민감, 새 제품 최초 구매",
        "loves": ["이색 맛", "인증샷 가치", "비주얼"],
        "hates": ["평범함", "식상함"],
        "taste_profile": "트렌드 추종, 단맛·비주얼 선호",
        "purchase": "중 가격대, 트렌드 우선, 충동 구매",
        "bias": "신선함에 관대 (+0.4)",
        "comment_style": "감탄사 많음, 감성적, 트렌디"
    },
    {
        "id": "P22", "name": "안지혜", "age": 29, "gender": "여",
        "region": "경기 고양", "occupation": "간호사",
        "lifestyle": "교대 근무, 영양 챙김, 피로 회복 음료 애용",
        "loves": ["비타민류", "전해질", "담백함"],
        "hates": ["피로 악화 요소", "카페인 과다"],
        "taste_profile": "기능성 선호, 균형, 과하지 않음",
        "purchase": "기능성 우선, 검증된 브랜드",
        "bias": "중립 (0.0)",
        "comment_style": "실용적, 근무 중 기준"
    },
    {
        "id": "P23", "name": "한소연", "age": 36, "gender": "여",
        "region": "충북 청주", "occupation": "공무원",
        "lifestyle": "아이 둘, 가족 간식 구매, 가성비",
        "loves": ["가족 공용", "대용량", "순함"],
        "hates": ["자극적", "고가"],
        "taste_profile": "보편성, 자극 회피, 순함 선호",
        "purchase": "가격매우민감, 대용량",
        "bias": "보수적 (-0.2)",
        "comment_style": "엄마 관점, 실용적"
    },
    {
        "id": "P24", "name": "노수빈", "age": 27, "gender": "여",
        "region": "대구 달서구", "occupation": "학원 강사",
        "lifestyle": "저녁 회식 잦음, 주말 카페투어",
        "loves": ["커피", "디저트", "달달함"],
        "hates": ["밍밍함", "물 같은 음료"],
        "taste_profile": "단맛·진한 맛 선호, 강한 풍미",
        "purchase": "중가격대, 카페 기반 소비",
        "bias": "관대 (+0.3)",
        "comment_style": "친근, 구체적 비교"
    },
    {
        "id": "P25", "name": "장미경", "age": 50, "gender": "여",
        "region": "전북 전주", "occupation": "공방 운영",
        "lifestyle": "전통 차 애호, 수공예 작업",
        "loves": ["전통차", "은은함", "깊은 맛"],
        "hates": ["화학 첨가물", "인공적 달콤함"],
        "taste_profile": "전통적, 복합 풍미, 천연 선호",
        "purchase": "고가도 허용, 원산지 확인",
        "bias": "인공에 엄격 (-0.4)",
        "comment_style": "수공예가 관점, 섬세함"
    },
    {
        "id": "P26", "name": "이성민", "age": 23, "gender": "남",
        "region": "서울 동작구", "occupation": "대학생",
        "lifestyle": "기숙사 생활, 편의점 주 이용",
        "loves": ["편의점 신제품", "단맛", "탄산"],
        "hates": ["물 같은", "비싼"],
        "taste_profile": "단맛·자극 선호, 강한 맛 수용",
        "purchase": "가격매우민감, 충동 구매",
        "bias": "관대 (+0.3)",
        "comment_style": "직설적, MZ 말투"
    },
    {
        "id": "P27", "name": "오승준", "age": 31, "gender": "남",
        "region": "경기 수원", "occupation": "금융권 회사원",
        "lifestyle": "싱글, 자취, 외식 많음",
        "loves": ["깔끔한 맛", "커피", "맥주"],
        "hates": ["끈적함", "인공 단맛"],
        "taste_profile": "쓴맛 내성 높음, 드라이 선호",
        "purchase": "중상 가격, 브랜드 의식",
        "bias": "단맛 엄격 (-0.3)",
        "comment_style": "차분, 분석적"
    },
    {
        "id": "P28", "name": "백준호", "age": 36, "gender": "남",
        "region": "광주 서구", "occupation": "셰프",
        "lifestyle": "외식업 종사, 미각 훈련됨",
        "loves": ["복합미", "감칠맛", "재료 균형"],
        "hates": ["단순함", "불균형"],
        "taste_profile": "전문적 미각, 매우 섬세함",
        "purchase": "연구 목적, 원가 분석",
        "bias": "엄격 전문가 (-0.3)",
        "comment_style": "전문 용어, 구조적 분석"
    },
    {
        "id": "P29", "name": "조성환", "age": 47, "gender": "남",
        "region": "경북 포항", "occupation": "중견기업 부장",
        "lifestyle": "건강 관리 시작, 금주 시도",
        "loves": ["무알콜 음료", "건강 기능성", "담백"],
        "hates": ["고칼로리", "자극적"],
        "taste_profile": "중년 전환기, 건강 우선",
        "purchase": "건강 기능성 우선",
        "bias": "엄격 (-0.3)",
        "comment_style": "진지, 건강 관점"
    },
    {
        "id": "P30", "name": "황기태", "age": 58, "gender": "남",
        "region": "강원 원주", "occupation": "자영업 (정비소)",
        "lifestyle": "육체 노동, 수분 보충 중요",
        "loves": ["시원함", "갈증 해소", "스포츠 음료"],
        "hates": ["미지근함", "약한 맛"],
        "taste_profile": "기능성 중시, 강한 맛 수용",
        "purchase": "가격 중, 기능 우선",
        "bias": "중립 (0.0)",
        "comment_style": "실용적, 직설적"
    },
]


def select_personas(n_panels):
    """사용자가 지정한 수만큼 페르소나를 한국 인구 분포를 반영해 선택
    
    Args:
        n_panels: 선택할 패널 수 (5 ~ 30)
    
    Returns:
        선택된 페르소나 리스트
    """
    full_pool = PERSONA_PANEL_20
    
    if n_panels <= 0:
        return []
    
    # 기본 20명 = P01~P20 반환 (재현성 보장)
    if n_panels == 20:
        return full_pool[:20]
    
    # 최대 30명 제한
    n_panels = min(n_panels, len(full_pool))
    
    # 그룹별 페르소나 분류 (각 그룹 내에서는 P번호 순)
    def age_group(p):
        age = p['age']
        g = p['gender']
        if 20 <= age < 30: return f"20대{g}"
        elif 30 <= age < 40: return f"30대{g}"
        elif 40 <= age < 50: return f"40대{g}"
        else: return f"50대+{g}"
    
    groups = {}
    for p in full_pool:
        grp = age_group(p)
        groups.setdefault(grp, []).append(p)
    
    # 20명 기준 분포 비율
    group_order = ['20대여', '20대남', '30대여', '30대남',
                    '40대여', '40대남', '50대+여', '50대+남']
    base_ratios = {
        '20대여': 3, '20대남': 2,
        '30대여': 3, '30대남': 3,
        '40대여': 3, '40대남': 2,
        '50대+여': 2, '50대+남': 2,
    }
    
    # 비례 할당
    allocations = {}
    for g in group_order:
        allocations[g] = max(1, round(n_panels * base_ratios[g] / 20))
    
    # 합계 보정 (무한루프 방지: 최대 100회만 시도)
    for _ in range(100):
        total = sum(allocations.values())
        if total == n_panels:
            break
        if total < n_panels:
            # 늘릴 때: 그룹에 사용 가능한 페르소나가 남아있는 것 중 우선순위로
            for g in ['30대여', '30대남', '20대여', '40대여',
                       '40대남', '20대남', '50대+여', '50대+남']:
                if allocations[g] < len(groups.get(g, [])):
                    allocations[g] += 1
                    break
            else:
                break  # 모든 그룹 가득참
        else:
            # 줄일 때: 가장 많이 할당된 그룹부터
            largest = max(allocations, key=lambda k: allocations[k])
            if allocations[largest] > 1:
                allocations[largest] -= 1
            else:
                # 1 이상인 어떤 것도 줄일 수 없으면 중단
                break
    
    # 선택
    selected = []
    for g in group_order:
        available = groups.get(g, [])
        n_take = min(allocations.get(g, 0), len(available))
        selected.extend(available[:n_take])
    
    # 여전히 부족하면 남은 페르소나로 보충
    if len(selected) < n_panels:
        remaining = [p for p in full_pool if p not in selected]
        selected.extend(remaining[:n_panels - len(selected)])
    
    return selected[:n_panels]


# ============================================================================
# 인쇄용 질문지 HTML
# ============================================================================

QUESTIONNAIRE_CSS = """
<style>
@page { size: A4; margin: 1.5cm; }
body { font-family: 'Malgun Gothic', 'Nanum Gothic', sans-serif;
       color: #000; line-height: 1.6; font-size: 14px; background: #fff; }
.page { page-break-after: always; padding: 10px 20px; max-width: 720px;
        margin: 0 auto; min-height: 900px; }
.page:last-child { page-break-after: auto; }
h1 { text-align: center; font-size: 22px; border-bottom: 3px double #000;
     padding-bottom: 10px; margin-bottom: 20px; }
h2 { text-align: center; font-size: 20px; color: #0369a1;
     border-bottom: 2px solid #0369a1; padding-bottom: 8px; }
.info-box { border: 1px solid #666; padding: 12px; margin: 15px 0;
            background: #f8f8f8; border-radius: 4px; }
.info-box strong { font-size: 15px; }
table { width: 100%; border-collapse: collapse; margin: 15px 0; }
th, td { border: 1.5px solid #333; padding: 10px; text-align: center;
         font-size: 14px; }
th { background: #e5e7eb; font-weight: bold; }
.code { font-size: 28px; font-weight: bold; letter-spacing: 3px;
        font-family: 'Courier New', monospace; }
.code-big { font-size: 48px; font-weight: bold; letter-spacing: 4px;
            font-family: 'Courier New', monospace; display: inline-block;
            padding: 15px 30px; border: 2px solid #000;
            margin: 10px 15px; background: #fff; }
.score-box { display: inline-block; border: 1.5px solid #000;
             width: 28px; height: 28px; line-height: 28px; margin: 1px;
             text-align: center; font-size: 13px; }
.likert-row { display: flex; align-items: center; margin: 6px 0; }
.likert-row .attr { flex: 0 0 200px; font-weight: bold; }
.likert-row .scale { flex: 1; display: flex; gap: 4px; }
.instruction { background: #fffbe0; padding: 12px; border-left: 4px solid #f59e0b;
               margin: 15px 0; font-size: 14px; }
.rank-input { border: 1.5px solid #000; width: 60px; height: 32px;
              display: inline-block; }
.footer { text-align: center; font-size: 11px; color: #666;
          margin-top: 30px; border-top: 1px solid #ccc; padding-top: 10px; }
.print-notice { background: #dbeafe; padding: 10px; margin-bottom: 20px;
                border-radius: 4px; text-align: center; font-size: 13px; }
.scale-labels { display: flex; justify-content: space-between;
                font-size: 10px; color: #666; margin-top: 2px; }
@media print { .no-print { display: none !important; } }
</style>
"""

PRINT_NOTICE = """
<div class="print-notice no-print">
📄 <strong>이 문서는 인쇄용입니다.</strong>
브라우저에서 <kbd>Ctrl+P</kbd> (Mac: <kbd>Cmd+P</kbd>)를 눌러 인쇄하세요.
</div>
"""


def build_anova_questionnaire(n_panels, samples, attribute, scale, seed):
    """ANOVA 질문지 (척도 선택 가능)"""
    random.seed(seed)
    n_samples = len(samples)
    all_codes = random.sample(range(100, 1000), n_panels * n_samples)
    
    pages_html = []
    code_map = []
    
    scale_label = "9점 척도" if scale == 9 else "7점 척도"
    scale_guide = ("1=매우 약함/나쁨, 5=보통, 9=매우 강함/좋음" if scale == 9
                    else "1=매우 약함/나쁨, 4=보통, 7=매우 강함/좋음")
    
    for p in range(n_panels):
        codes = all_codes[p*n_samples:(p+1)*n_samples]
        order = [(i + p) % n_samples for i in range(n_samples)]
        
        rows = ""
        for i, s_idx in enumerate(order, 1):
            s = samples[s_idx]
            code = codes[s_idx]
            score_boxes = "".join([f'<span class="score-box">{n}</span>' 
                                    for n in range(1, scale + 1)])
            rows += f"""<tr>
                <td><strong>{i}</strong></td>
                <td><span class="code">{code}</span></td>
                <td>{score_boxes}</td>
            </tr>"""
            code_map.append({
                '패널': f'P{p+1:02d}', '제시순서': i,
                '시료명': s, '블라인드코드': code
            })
        
        pages_html.append(f"""
<div class="page">
    <h1>관능검사 조사지 — 평점법 (ANOVA, {scale_label})</h1>
    <div class="info-box">
        패널: <strong>P{p+1:02d}</strong> | 날짜: _______ | 시간: _______<br>
        성명: _______ | 성별: □남 □여 | 연령: □20대 □30대 □40대 □50대↑
    </div>
    <div class="instruction">
        <strong>📋 평가 속성: {attribute}</strong><br>
        제시된 순서대로 시음하고 <strong>{scale_label}</strong>에서 
        해당 숫자에 ○ 치세요.<br>
        <small>({scale_guide})</small><br>
        각 시료 사이 <strong>물로 헹궈주세요.</strong>
    </div>
    <table>
        <tr><th style="width:15%">순서</th><th style="width:20%">시료 코드</th>
            <th>점수 (해당 숫자에 ○)</th></tr>
        {rows}
    </table>
    <div class="info-box"><strong>자유 의견:</strong><br>
        _______________________________________________________________________<br><br>
        _______________________________________________________________________
    </div>
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>""")
    
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>ANOVA 조사지</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}{"".join(pages_html)}</body></html>"""
    return html, pd.DataFrame(code_map)


def build_triangle_questionnaire(n_panels, attribute, seed):
    random.seed(seed)
    pages_html = []
    answer_info = []
    for p in range(n_panels):
        codes_3 = random.sample(range(100, 1000), 3)
        odd_position = random.randint(0, 2)
        odd_code = codes_3[odd_position]
        pages_html.append(f"""
<div class="page">
    <h1>관능검사 조사지 — 삼점검정 (Triangle Test)</h1>
    <div class="info-box">
        패널: <strong>P{p+1:02d}</strong> | 날짜: _______ | 시간: _______<br>
        성명: _______
    </div>
    <div class="instruction">
        아래 3개 시료 중 <strong>2개 동일, 1개 다른 시료</strong>입니다.<br>
        <strong>{attribute}</strong>을 기준으로 <u>왼쪽부터</u> 시음하고
        <strong>다른 하나</strong>를 찾으세요.<br>
        각 시료 사이 물로 헹굼 / 반드시 하나 선택.
    </div>
    <div style="text-align:center; margin: 35px 0;">
        <div class="code-big">{codes_3[0]}</div>
        <div class="code-big">{codes_3[1]}</div>
        <div class="code-big">{codes_3[2]}</div>
    </div>
    <div class="info-box" style="text-align:center; padding: 20px;">
        <strong>다른 시료 코드:</strong>
        <span style="border-bottom: 2px solid #000; padding: 0 40px; font-size: 24px;">
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
    </div>
    <p><strong>확신도:</strong>
        □ 확실 □ 거의 확실 □ 모호 □ 추측</p>
    <p><strong>차이 강도:</strong>
        □ 약함 □ 중간 □ 강함 □ 매우 강함</p>
    <div class="info-box"><strong>어떤 점이 달랐나요?</strong><br>
        _______________________________________________________________________<br><br>
        _______________________________________________________________________
    </div>
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>""")
        answer_info.append({
            '패널': f'P{p+1:02d}',
            '코드1': codes_3[0], '코드2': codes_3[1], '코드3': codes_3[2],
            '정답위치': f'{odd_position + 1}번째', '정답코드': odd_code
        })
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>삼점검정 조사지</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}{"".join(pages_html)}</body></html>"""
    return html, pd.DataFrame(answer_info)


def build_duotrio_questionnaire(n_panels, attribute, seed):
    random.seed(seed)
    pages_html = []
    answer_info = []
    for p in range(n_panels):
        r_code = random.randint(100, 999)
        codes_2 = random.sample([c for c in range(100, 1000) if c != r_code], 2)
        same_position = random.randint(0, 1)
        same_code = codes_2[same_position]
        pages_html.append(f"""
<div class="page">
    <h1>관능검사 조사지 — 일-이점검정 (Duo-Trio)</h1>
    <div class="info-box">
        패널: <strong>P{p+1:02d}</strong> | 날짜: _______ | 성명: _______
    </div>
    <div class="instruction">
        먼저 <strong>기준시료 R</strong>을 시음 후, 아래 2개 중
        <strong>R과 동일한 것</strong>을 찾으세요.<br>
        <strong>{attribute}</strong> 기준으로 평가. 각 시료 사이 물로 헹굼.
    </div>
    <div style="text-align:center; margin: 30px 0;">
        <div style="border: 3px solid #dc2626; display:inline-block; padding: 20px 40px; 
             margin-bottom: 20px; background: #fee2e2;">
            <span style="font-size:20px; font-weight:bold; color: #991b1b;">기준시료</span><br>
            <span class="code" style="font-size:36px;">R ({r_code})</span>
        </div>
        <br>
        <div style="margin-top: 20px;">
            <div class="code-big">{codes_2[0]}</div>
            <div class="code-big">{codes_2[1]}</div>
        </div>
    </div>
    <div class="info-box" style="text-align:center; padding: 20px;">
        <strong>R과 같은 시료 코드:</strong>
        <span style="border-bottom: 2px solid #000; padding: 0 40px; font-size: 24px;">
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
    </div>
    <p><strong>확신도:</strong> □ 확실 □ 거의 확실 □ 모호 □ 추측</p>
    <div class="info-box"><strong>자유 의견:</strong><br>
        _______________________________________________________________________
    </div>
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>""")
        answer_info.append({
            '패널': f'P{p+1:02d}', '기준시료_R': r_code,
            '코드1': codes_2[0], '코드2': codes_2[1],
            '정답위치': f'{same_position + 1}번째', '정답코드(R과동일)': same_code
        })
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>일-이점검정 조사지</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}{"".join(pages_html)}</body></html>"""
    return html, pd.DataFrame(answer_info)


def build_ranking_questionnaire(n_panels, samples, attribute, seed):
    random.seed(seed)
    n_samples = len(samples)
    all_codes = random.sample(range(100, 1000), n_panels * n_samples)
    pages_html = []
    code_map = []
    for p in range(n_panels):
        codes = all_codes[p*n_samples:(p+1)*n_samples]
        order = list(range(n_samples))
        random.shuffle(order)
        rows = ""
        for s_idx in order:
            s = samples[s_idx]
            code = codes[s_idx]
            rows += f"""<tr>
                <td><span class="code">{code}</span></td>
                <td><span class="rank-input"></span></td>
            </tr>"""
            code_map.append({'패널': f'P{p+1:02d}', '시료명': s, '블라인드코드': code})
        pages_html.append(f"""
<div class="page">
    <h1>관능검사 조사지 — 순위법</h1>
    <div class="info-box">
        패널: <strong>P{p+1:02d}</strong> | 날짜: _______ | 성명: _______
    </div>
    <div class="instruction">
        아래 시료를 <strong>{attribute}</strong> 기준으로 순위를 매기세요.<br>
        <strong>1=가장 강함/선호, 숫자가 클수록 약함/덜 선호</strong><br>
        <u>동점 불가</u>. 모든 시료에 다른 순위 부여.
    </div>
    <table style="max-width: 500px; margin: 0 auto;">
        <tr><th style="width:50%">시료 코드</th><th>순위 (1=최상)</th></tr>
        {rows}
    </table>
    <div class="info-box" style="margin-top: 30px;">
        <strong>순위 결정 기준:</strong><br>
        _______________________________________________________________________
    </div>
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>""")
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>순위법 조사지</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}{"".join(pages_html)}</body></html>"""
    return html, pd.DataFrame(code_map)


def build_reliability_questionnaire(n_panels, samples, n_reps, attribute, seed):
    random.seed(seed)
    n_samples = len(samples)
    pages_html = []
    code_map = []
    for p in range(n_panels):
        for r in range(n_reps):
            codes = random.sample(range(100, 1000), n_samples)
            order = [(i + p + r) % n_samples for i in range(n_samples)]
            rows = ""
            for i, s_idx in enumerate(order, 1):
                s = samples[s_idx]
                code = codes[s_idx]
                score_boxes = "".join([f'<span class="score-box">{n}</span>' for n in range(1, 10)])
                rows += f"""<tr>
                    <td><strong>{i}</strong></td>
                    <td><span class="code">{code}</span></td>
                    <td>{score_boxes}</td>
                </tr>"""
                code_map.append({'패널': f'P{p+1:02d}', '반복': r+1,
                    '제시순서': i, '시료명': s, '블라인드코드': code})
            pages_html.append(f"""
<div class="page">
    <h1>관능검사 조사지 — 반복측정 (신뢰도)</h1>
    <div class="info-box">
        패널: <strong>P{p+1:02d}</strong> | <strong>반복 {r+1}/{n_reps}회차</strong>
        | 날짜: _______ | 성명: _______
    </div>
    <div class="instruction">
        <strong>평가 속성: {attribute}</strong> (9점 척도)<br>
        <small>(1=매우 약함, 5=보통, 9=매우 강함)</small>
        <strong>※ 이전 회차 참고 금지</strong>
    </div>
    <table>
        <tr><th style="width:15%">순서</th><th style="width:20%">시료 코드</th><th>점수</th></tr>
        {rows}
    </table>
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>""")
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>신뢰도 조사지</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}{"".join(pages_html)}</body></html>"""
    return html, pd.DataFrame(code_map)


def build_scaling_questionnaire(n_panels, product_name, seed):
    """평점법 12항목 인쇄용 질문지 (리커트 7점)"""
    random.seed(seed)
    pages_html = []
    code_map = []
    
    scale_html = lambda: "".join([
        f'<span class="score-box">{n}</span>' for n in range(1, 8)
    ])
    
    for p in range(n_panels):
        code = random.randint(100, 999)
        attr_rows = ""
        for i, attr in enumerate(SCALING_ATTRIBUTES, 1):
            attr_rows += f"""<tr>
                <td style="text-align:left; padding-left:12px;">
                    <strong>{i}. {attr}</strong>
                </td>
                <td>{scale_html()}</td>
            </tr>"""
        code_map.append({
            '패널': f'P{p+1:02d}', '시료명': product_name, '블라인드코드': code
        })
        pages_html.append(f"""
<div class="page">
    <h1>관능검사 조사지 — 평점법 (Scaling Test)</h1>
    <div class="info-box">
        패널: <strong>P{p+1:02d}</strong> | 시료 코드: 
        <span class="code">{code}</span><br>
        날짜: _______ | 성명: _______ | 
        성별: □남 □여 | 연령: □20 □30 □40 □50↑
    </div>
    <div class="instruction">
        <strong>📋 평가 방법: 리커트 7점 척도</strong><br>
        각 항목에 대해 해당하는 숫자에 ○ 치세요.<br>
        <small>(1=매우 약함/매우 나쁨, 4=보통, 7=매우 강함/매우 좋음)</small><br>
        <strong>⚠️ 이전 항목의 점수가 다음 항목에 영향주지 않도록 독립적으로 평가하세요.</strong>
    </div>
    <table>
        <tr><th style="width:35%; text-align:left; padding-left:12px;">평가 항목</th>
            <th>점수 (1 ─── 7)</th></tr>
        {attr_rows}
    </table>
    <div class="scale-labels">
        <span>← 매우 약함/나쁨</span><span>보통</span><span>매우 강함/좋음 →</span>
    </div>
    <div class="info-box">
        <strong>자유 의견 (개선 사항, 특이점 등):</strong><br>
        _______________________________________________________________________<br><br>
        _______________________________________________________________________<br><br>
        _______________________________________________________________________
    </div>
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>""")
    
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>평점법 조사지</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}{"".join(pages_html)}</body></html>"""
    return html, pd.DataFrame(code_map)


def build_answer_key_html(test_type, df_answer):
    title_map = {
        'anova': 'ANOVA 평점법', 'triangle': '삼점검정',
        'duo_trio': '일-이점검정', 'ranking': '순위법',
        'reliability': '반복측정 (신뢰도)', 'scaling': '평점법'
    }
    title = title_map.get(test_type, test_type)
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>정답지 — {title}</title>{QUESTIONNAIRE_CSS}</head>
<body>{PRINT_NOTICE}
<div class="page">
    <h2>🔑 정답지 (Answer Key) — {title}</h2>
    <div class="info-box" style="background: #fef3c7; border: 2px solid #f59e0b;">
        <strong>⚠️ 기밀 문서</strong> — 연구자 전용. 패널에게 공개하지 마세요.<br>
        이 문서는 조사 종료 후 결과 집계(CSV 작성)에 사용됩니다.
    </div>
    {df_answer.to_html(index=False, escape=False)}
    <div class="footer">Sweet Lab · Natural Lab R&D · {datetime.date.today()}</div>
</div>
</body></html>"""
    return html


# ============================================================================
# 통계 함수 (순위법 3가지 검정)
# ============================================================================

def friedman_rank_range_test(rank_sums, n, k, alpha=0.05):
    """(1) 순위합 범위 검정
    각 시료의 순위합이 유의 범위 밖이면 특이값
    """
    mean_R = n * (k + 1) / 2  # 귀무가설 하 기대 순위합
    se = np.sqrt(n * k * (k + 1) / 12)
    z_crit = stats.norm.ppf(1 - alpha / 2)  # 양측
    R_lower = mean_R - z_crit * se
    R_upper = mean_R + z_crit * se
    
    results = []
    for sample, R in rank_sums.items():
        significant = R < R_lower or R > R_upper
        results.append({
            '시료': sample,
            '순위합': R,
            '하한': round(R_lower, 2),
            '상한': round(R_upper, 2),
            '유의': '✓ 특이값' if significant else '✗ 범위 내'
        })
    return pd.DataFrame(results), {'mean_R': mean_R, 'R_lower': R_lower, 
                                     'R_upper': R_upper, 'z_crit': z_crit}


def friedman_rank_difference_test(rank_sums, n, k, alpha=0.05):
    """(2) 순위합 차이값 검정 (LSD for ranks)
    두 시료의 순위합 차이가 임계값 이상이면 유의차
    → 동질군(a, b, ab) 표시의 근거
    """
    z_crit = stats.norm.ppf(1 - alpha / 2)
    threshold = z_crit * np.sqrt(n * k * (k + 1) / 6)
    
    samples = list(rank_sums.keys())
    results = []
    pair_matrix = {}  # (s1, s2) -> is_significant
    
    for i in range(len(samples)):
        for j in range(i+1, len(samples)):
            s1, s2 = samples[i], samples[j]
            diff = abs(rank_sums[s1] - rank_sums[s2])
            significant = diff > threshold
            pair_matrix[(s1, s2)] = significant
            pair_matrix[(s2, s1)] = significant
            results.append({
                '시료1': s1, '시료2': s2,
                '|R1-R2|': round(diff, 2),
                '임계값': round(threshold, 2),
                '유의차': '✓' if significant else '✗'
            })
    
    # 동질군 계산 (Fisher's LSD-style grouping)
    homogeneous_groups = compute_homogeneous_groups(samples, rank_sums, pair_matrix)
    
    return pd.DataFrame(results), {
        'threshold': threshold, 'z_crit': z_crit,
        'homogeneous_groups': homogeneous_groups
    }


def compute_homogeneous_groups(samples, rank_sums, pair_matrix):
    """동질군 a, b, ab 자동 계산 (Maximal Non-significant Intervals)
    알고리즘: 
    1. 순위합 오름차순 정렬
    2. 각 시작점에서 가능한 최대 비유의 구간 찾기
    3. 중복(포함) 구간 제거
    4. 남은 최대 구간들에 letter 부여
    """
    sorted_samples = sorted(samples, key=lambda s: rank_sums[s])
    n = len(sorted_samples)
    
    # 1. 모든 최대 비유의 구간 [i, j]
    maximal_intervals = []
    for i in range(n):
        j = i
        for k in range(i + 1, n):
            all_nonsig = True
            for a in range(i, k):
                if pair_matrix.get((sorted_samples[a], sorted_samples[k]), False):
                    all_nonsig = False
                    break
            if all_nonsig:
                j = k
            else:
                break
        maximal_intervals.append((i, j))
    
    # 2. 다른 구간에 완전히 포함되는 것 제거
    filtered = []
    for a, b in maximal_intervals:
        is_subset = False
        for c, d in maximal_intervals:
            if (c, d) != (a, b) and c <= a and b <= d:
                is_subset = True
                break
        if not is_subset:
            filtered.append((a, b))
    filtered = list(set(filtered))
    filtered.sort()
    
    # 3. 각 최대 구간에 letter 부여
    groups = {s: set() for s in sorted_samples}
    letters = 'abcdefghijk'
    for idx, (a, b) in enumerate(filtered):
        letter = letters[idx]
        for k in range(a, b + 1):
            groups[sorted_samples[k]].add(letter)
    
    # 4. 결과
    result = {}
    for s in samples:
        sorted_letters = sorted(list(groups[s]))
        result[s] = ''.join(sorted_letters) if sorted_letters else 'a'
    return result


def friedman_chi_square_full(rank_sums, n, k, alpha=0.05):
    """(3) Friedman χ² 검정 완전판"""
    sum_R_squared = sum(R**2 for R in rank_sums.values())
    chi2_stat = (12 / (n * k * (k + 1))) * sum_R_squared - 3 * n * (k + 1)
    df = k - 1
    p_value = 1 - chi2.cdf(chi2_stat, df)
    chi2_crit = chi2.ppf(1 - alpha, df)
    
    return {
        'chi2_stat': chi2_stat,
        'p_value': p_value,
        'df': df,
        'chi2_crit': chi2_crit,
        'significant': chi2_stat > chi2_crit,
        'alpha': alpha
    }
# ============================================================================
# AI 소비자 조사 - 프롬프트 템플릿 (배합비 모드)
# ============================================================================

def prompt_stage0_recipe(recipe_text, process_text=""):
    """Stage 0: 배합비 자유 텍스트 → 표준화 JSON"""
    return f"""당신은 20년 경력의 식품 R&D 배합 전문가입니다. 
현장에서 비정형적으로 작성된 배합 메모를 해석하여 표준 형식으로 정리하는 역할입니다.

다음은 사용자가 입력한 배합 정보입니다:
---
{recipe_text}
---

제조 공정 정보:
---
{process_text if process_text else "(입력 없음)"}
---

이를 해석하여 다음 원칙에 따라 정규화하세요:

1. **원료 식별**: 
   - 약어/상품명은 표준 원료명으로 변환 (예: "PCJ" → "복숭아 농축액")
   - 모호한 표현은 식품 R&D 일반 기준으로 추정하되 추정 사실을 표시

2. **단위 통일**:
   - 모든 비율을 중량%로 통일
   - g/100mL, mg, kg 등은 환산
   - 합계가 100%가 되지 않으면 물/잔량으로 자동 채움

3. **공정 정보 분리**:
   - 배합비(정량)와 공정(온도/시간)을 분리

4. **범위값 처리**:
   - "3~5%"는 중간값 4%로 설정

5. **누락/불명확 부분**:
   - 각 원료별 예상 Brix, pH 추정치도 함께 제시
   - 부족한 정보는 "추정" 플래그 부여

다음 JSON 형식으로만 출력하세요 (다른 설명 없이):

```json
{{
  "product_category": "음료/유제품/빙과/스낵/베이커리/주류/기타 중 하나",
  "normalized_recipe": [
    {{
      "ingredient": "복숭아 농축액",
      "ratio_pct": 15.0,
      "original_input": "원문 일부",
      "function": "주원료 (향미/당도)",
      "estimated_brix": 65,
      "is_estimated": false
    }}
  ],
  "process": [
    {{"step": "혼합", "condition": "상온"}},
    {{"step": "살균", "condition": "80°C 10분"}}
  ],
  "warnings": [
    "주의사항 문구"
  ],
  "assumptions_made": [
    "설탕 '좀'을 4%로 추정",
    "물의 비율을 잔량으로 자동 계산"
  ]
}}
```
"""


def prompt_stage1_flavor(normalized_recipe_json):
    """Stage 1: 배합비 → 맛 프로파일 (감각 몰입형)"""
    return f"""당신은 20년 경력의 식품 관능 전문가입니다. 각 원료의 물성과 
관능 특성에 대해 깊은 감각 기억을 가지고 있습니다.

다음 배합의 음료/식품을 실제로 시음했다고 상상해보세요:

```json
{json.dumps(normalized_recipe_json, ensure_ascii=False, indent=2)}
```

이 제품을 혀에 올렸을 때의 감각을 당신의 미각 경험으로 재구성하세요. 
공식 계산이 아닌 <<실제 감각 기억>>으로 서술해야 합니다.

다음 단계로 사고하세요:
1. 제품을 컵에 따랐을 때 — 색, 점도, 향이 어떤가?
2. 첫 한 모금을 입에 넣었을 때 — 혀 앞쪽에서 무엇을 느끼나?
3. 혀 전체로 퍼질 때 — 단맛/산미/쓴맛의 밸런스는?
4. 삼킨 후 — 끝맛과 여운은 어떤가?
5. 전체적인 인상과 예상 강점/약점은?

다음 JSON 형식으로만 출력하세요:

```json
{{
  "physical": {{
    "estimated_brix": 10.5,
    "estimated_ph": 3.5,
    "estimated_acidity_pct": 0.25,
    "sweetness_acid_ratio": 42
  }},
  "visual": {{
    "color": "연한 주황빛 분홍",
    "clarity": "약간 불투명",
    "viscosity": "물보다 약간 진함"
  }},
  "aroma": {{
    "top_notes": ["복숭아", "약간의 풋과실"],
    "intensity": 6,
    "character": "달콤하고 부드러운 과일향"
  }},
  "taste": {{
    "first_impression": "혀 끝에서 먼저 느껴지는 단맛",
    "mid_palate": "복숭아의 과일감이 혀 전체로 퍼지며 가벼운 산미가 균형을 잡음",
    "finish": "빠르게 사라지는 가벼운 여운, 인공향의 기미",
    "sweetness": 6,
    "acidity": 4,
    "bitterness": 1,
    "umami": 1,
    "astringency": 2
  }},
  "texture": {{
    "body": 3,
    "mouthfeel": "가볍고 매끄러움",
    "carbonation": 0
  }},
  "overall": {{
    "balance": "단맛 우세, 복숭아 향이 뚜렷",
    "strengths": ["명확한 복숭아 향", "부드러운 단맛"],
    "weaknesses": ["바디감 부족", "인공향 잔존"],
    "target_fit": "10-30대 여성에게 호평 예상"
  }}
}}
```
"""


def prompt_stage2_panel_eval_recipe(product_name, flavor_profile_json, personas):
    """Stage 2: N명 페르소나 배합비 모드 평가"""
    persona_text = json.dumps(personas, ensure_ascii=False, indent=1)
    flavor_text = json.dumps(flavor_profile_json, ensure_ascii=False, indent=1)
    n_panels = len(personas)
    
    return f"""당신은 관능검사 시뮬레이션 엔진입니다. 
{n_panels}명의 한국 소비자 패널이 동일한 제품을 시음한 후 각자의 취향으로 평가하는 
상황을 매우 현실적으로 재현해주세요.

**시음 제품**: {product_name}

**맛 프로파일** (이 제품의 실제 관능 특성):
```json
{flavor_text}
```

**패널 명단 ({n_panels}명)**:
```json
{persona_text}
```

**중요한 시뮬레이션 규칙**:

1. **몰입**: 각 패널의 1인칭 시점으로 제품을 시음했다고 상상하세요.
   "이 페르소나는 이 점수를 줄 것이다"가 아니라
   "내가 민지라면 이 맛을 어떻게 느낄까?"를 실제로 사고하세요.

2. **다양성 필수**: {n_panels}명이 모두 비슷한 점수를 주면 실패입니다.
   실제 소비자 조사의 점수 분포는:
   - 극호(6-7점): 15-20%
   - 호(5-6점): 30-40%
   - 중립(4점): 20-30%
   - 불호(3점 이하): 15-20%
   - 극불호(1-2점): 5-10%

3. **일관된 개성**: 각 패널의 프로필(선호/혐오/성향)에 <<반드시>> 충실하세요.
   - 단맛 선호형이 단맛 강한 제품에 낮은 점수 → 모순
   - 건강 지향형이 아무 거부감 없이 단 제품에 만점 → 모순
   - 프로필과 점수 사이에 <<명확한 인과관계>>가 있어야 함

4. **현실성**: 점수는 1-7 정수 (반정수 X). 실제 소비자도 
   "6.5는 아니고 6 정도" 식으로 평가합니다.

5. **코멘트 진정성**: 각 패널의 코멘트는 그 사람이 실제로 쓸 법한 어투:
   - 20대: 이모지, 짧은 문장, SNS 어투
   - 40대+: 차분, 구체적 설명
   - 식품 관심자: 원료/공정 언급

**참고: 실제 소비자 리뷰 예시** (어투 참조용):

예시1 (26세 여성, 저탄산 제품 평): 
"처음엔 좀 밍밍한 느낌이었는데 마실수록 부담 없어서 좋아요. 
회사에서 일하면서 마시기 딱이에요."

예시2 (45세 남성, 프리미엄 녹차 평):
"가격 대비 품질이 확실히 느껴집니다. 쓴맛이 깊이 있으면서도 
뒷맛이 깔끔해요."

**평가 항목 (1-7 리커트, 관능 강도형)**
[1=매우 약함/매우 나쁨, 4=보통, 7=매우 강함/매우 좋음]
1. 전반적 만족도
2. 구입 의향
3. 색상
4. 전반적 맛
5. 풍미 (입 안의 향)
6. 단맛
7. 전반적 식감
8. 끝맛 여운

**출력 형식** (JSON만, 다른 설명 없이):

```json
{{
  "evaluations": [
    {{
      "panel_id": "P01",
      "panel_name": "김민지 (24세, 여)",
      "sensory_experience": "첫 모금에서 복숭아 향이 확 퍼지는데, 기대보다 단맛이 강해 부담스러움. 뒷맛에 인공향이 살짝 느껴짐.",
      "scores": {{
        "전반적만족도": 5, "구입의향": 4, "색상": 6,
        "전반적맛": 5, "풍미": 6, "단맛": 6,
        "전반적식감": 4, "끝맛여운": 4
      }},
      "comment": "복숭아 향은 진짜 좋은데 🍑 근데 살짝 너무 단 느낌? 다이어트 중이라 설탕 4%가 부담되긴 해요.",
      "reasoning": "단맛 선호하지만 최근 다이어트 시작해 당분 민감화"
    }}
  ]
}}
```

반드시 **{n_panels}명 전부** 평가하세요. 위 규칙을 엄격히 따르세요.
"""


def prompt_stage0_concept(concept_data):
    """Stage 0: 컨셉 정보 정규화"""
    return f"""당신은 식품 브랜드 마케팅 전문가입니다. 
사용자가 입력한 제품 컨셉 정보를 구조화하고 누락/모호함을 식별하세요.

**입력된 컨셉 정보**:
- 제품명: {concept_data.get('name', '(미입력)')}
- 타겟 소비자: {concept_data.get('target', '(미입력)')}
- 주요 소구점: {concept_data.get('selling_points', '(미입력)')}
- 가격대: {concept_data.get('price', '(미입력)')}원
- 유통 채널: {concept_data.get('channel', '(미입력)')}
- 포지셔닝: {concept_data.get('positioning', '(미입력)')}

이를 다음 JSON 형식으로 구조화하세요:

```json
{{
  "product_name": "정제된 제품명",
  "category": "음료/유제품/빙과/스낵/베이커리/주류/기타",
  "target_analysis": {{
    "primary": "주 타겟 상세 기술",
    "secondary": "부 타겟 (있다면)",
    "demographic": {{"age": "20-30대", "gender": "여성", "lifestyle": "워킹우먼"}}
  }},
  "value_propositions": [
    "소구점 1 (정제)",
    "소구점 2",
    "소구점 3"
  ],
  "price_tier": "저가/중가/프리미엄",
  "distribution": "채널 정제",
  "positioning_statement": "한 문장 포지셔닝",
  "warnings": [
    "누락/모호 정보 경고"
  ],
  "assumptions": [
    "추정한 사항"
  ]
}}
```
"""


def prompt_stage1_concept_perception(concept_normalized_json):
    """Stage 1: 컨셉 → 인식 프로파일"""
    return f"""당신은 10년차 소비재 마케팅 전문가입니다. 
다음 제품 컨셉을 받았다고 가정하고, 소비자가 이 제품을 처음 접했을 때의 
인상을 예측 분석하세요.

**컨셉 정보**:
```json
{json.dumps(concept_normalized_json, ensure_ascii=False, indent=2)}
```

다음 관점에서 예상 반응을 추론하세요:

1. **예상 소비자 첫인상**:
   - 매력도 (1-10)
   - 혼란/의구심 요소
   - 기대 포인트

2. **경쟁 제품 연상**:
   - 소비자가 떠올릴 기존 브랜드
   - 차별성 인식 정도

3. **가격 인식**:
   - 해당 카테고리 대비 적정성
   - 가격-가치 매칭 예상

4. **타겟 핏**:
   - 명시 타겟과 실제 호응 타겟의 차이
   - 예상 실제 구매층

5. **예상 리스크**:
   - 설명의 모호함/과장
   - 신뢰도 우려 요소

다음 JSON으로만 출력:

```json
{{
  "first_impression": {{
    "appeal_score": 7,
    "confusion_points": ["점 1", "점 2"],
    "expectation_points": ["기대 1", "기대 2"]
  }},
  "competitive_context": {{
    "associated_brands": ["브랜드 1", "브랜드 2"],
    "differentiation_score": 6,
    "differentiation_analysis": "차별성 분석"
  }},
  "price_perception": {{
    "category_avg_estimate": 2000,
    "price_fit_score": 7,
    "value_alignment": "가격-가치 매칭 분석"
  }},
  "target_fit": {{
    "stated_target_fit": 7,
    "actual_target_prediction": "실제 호응할 타겟",
    "gap_analysis": "명시 vs 실제 차이 분석"
  }},
  "risks": {{
    "credibility_concerns": ["우려 1"],
    "ambiguity_concerns": ["모호점 1"],
    "overall_risk_level": "중"
  }},
  "overall": {{
    "market_readiness": 6,
    "strengths": ["강점 1", "강점 2"],
    "improvement_needed": ["개선점 1"]
  }}
}}
```
"""


def prompt_stage2_panel_eval_concept(concept_name, perception_json, personas):
    """Stage 2: N명 페르소나 컨셉 모드 평가"""
    persona_text = json.dumps(personas, ensure_ascii=False, indent=1)
    perception_text = json.dumps(perception_json, ensure_ascii=False, indent=1)
    n_panels = len(personas)
    
    return f"""당신은 관능검사·마케팅 리서치 시뮬레이션 엔진입니다. 
{n_panels}명의 한국 소비자가 제품 <<컨셉 설명>>을 보고 평가하는 상황을 재현하세요.
(실제 시음이 아닌 <<컨셉 노출>> 상황입니다)

**제품 컨셉**: {concept_name}

**컨셉 인식 프로파일** (예상 소비자 반응 지표):
```json
{perception_text}
```

**패널 명단 ({n_panels}명)**:
```json
{persona_text}
```

**중요 시뮬레이션 규칙**:

1. **몰입**: 각 패널이 실제로 이 컨셉 광고/설명을 보고 반응한다고 상상.

2. **다양성**: 배합비 모드와 같은 분포 규칙 (극호~극불호 적절 분포).

3. **일관된 개성**: 페르소나의 특성(가격민감도, 건강의식, 신제품 수용성, 
   브랜드 선호 등)이 컨셉 평가에 직접 반영되어야 함.

4. **컨셉 평가의 특수성**: 
   - 실제 맛을 몰라도 평가함 (인상 기반)
   - 타겟 부합도가 중요 (자신이 타겟인지)
   - 가격 합리성 판단

5. **현실성**: 1-7 정수. 컨셉 평가는 종종 <<설명의 구체성/신뢰감>>에 좌우됨.

**평가 항목 (1-7 리커트)**:
1. 컨셉 매력도 (얼마나 끌리는가)
2. 구입 의향
3. 타겟 적합성 (나에게 맞는가)
4. 차별화 인식 (기존 제품과 달라 보이는가)
5. 신뢰도 (믿을 만한가)
6. 가격 수용도 (제시 가격이 합리적인가)
7. 건강 이미지
8. 프리미엄 인식

**참고 코멘트 스타일**:

예시1 (35세 여성): "프리미엄이라는데 왜 그런지 설명이 부족해요. 
천연 재료라고만 써있고 구체적이지 않아서 믿음이 덜 가요."

예시2 (27세 여성, 트렌드 민감): "우와, 저칼로리 복숭아 스파클링?? 
제가 딱 찾던 거! 2,500원이면 살짝 비싼데 편의점이면 그 정도는 괜찮아요."

**출력 형식** (JSON만):

```json
{{
  "evaluations": [
    {{
      "panel_id": "P01",
      "panel_name": "김민지 (24세, 여)",
      "concept_impression": "저칼로리 복숭아 스파클링이라는 설명에 바로 관심이 감. 다이어트 중인 나에게 딱.",
      "scores": {{
        "컨셉매력도": 7, "구입의향": 6, "타겟적합성": 7,
        "차별화인식": 5, "신뢰도": 5, "가격수용도": 4,
        "건강이미지": 6, "프리미엄인식": 5
      }},
      "comment": "완전 내 취향! 🍑✨ 편의점에서 딱 보면 살 것 같아요. 가격이 조금만 더 싸면 자주 마실 듯",
      "reasoning": "다이어트+단맛선호+SNS감성 페르소나 특성 반영"
    }}
  ]
}}
```

반드시 {n_panels}명 전부 평가. 위 규칙 엄격히 따르기.
"""


# ============================================================================
# 시나리오 생성 프롬프트 (Tab 2)
# ============================================================================

def prompt_scenario_generation(category, test_type):
    """차이식별 검정 연습 시나리오 생성"""
    return f"""당신은 식품 R&D 실무 교육 과정의 강사입니다. 
수강생에게 제공할 현실적인 {test_type} 연습 시나리오를 만들어주세요.

**제품 카테고리**: {category}
**검정 유형**: {test_type}

다음 구조의 케이스 스터디를 작성하세요:

## 🎯 {test_type} 케이스 스터디: [구체적 제목]

### 📌 상황 배경
구체적인 현업 상황 설명 (3-5줄). 실제로 일어날 법한 시나리오로.
(예: 원료 가격 변동, 공급망 변경, 공정 최적화, 신제품 개발 등)

### 🧪 검정 설계
- **목적**: 이 검정으로 답하려는 질문 1줄
- **패널 구성**: 권장 인원 및 특성
- **시료 준비**: 구체적 시료 설명
- **평가 속성**: 구체적 감각 속성 (예: 단맛 강도, 쓴맛, 풍미)
- **제시 조건**: 온도, 분량, 시료 제시 순서

### 📚 학습 포인트
이 케이스에서 배워야 할 핵심 개념 3가지
1. (개념 1)
2. (개념 2)  
3. (개념 3)

### 💭 토론 질문
수업에서 논의할 질문 3-4개:
1. (질문 1)
2. (질문 2)
3. (질문 3)

### 🎓 강사 해설
수업에서 강조해야 할 포인트 (5-7줄).
- 올바른 해석 방향
- 흔한 오해
- 실무 적용 시 주의사항

한국어로, 실제 {category} 업계 현실감 있게 작성하세요.
마크다운 형식으로 출력.
"""


# ============================================================================
# 핸드아웃 HTML 생성
# ============================================================================

HANDOUT_CSS = """
<style>
body { font-family: 'Roboto', 'Malgun Gothic', sans-serif;
       max-width: 1000px; margin: 0 auto; padding: 40px;
       color: #1e293b; line-height: 1.7; background: #f8fafc; }
.header { background: linear-gradient(135deg, #0f172a 0%, #1e40af 100%);
          color: #22d3ee; padding: 30px; border-radius: 8px;
          margin-bottom: 30px; border-left: 6px solid #22d3ee; }
.header h1 { color: #22d3ee; margin: 0 0 10px 0; font-size: 28px; }
.header p { color: #94a3b8; margin: 5px 0; }
.section { background: white; border: 1px solid #cbd5e1;
           border-left: 4px solid #0ea5e9; padding: 20px;
           margin: 20px 0; border-radius: 6px; }
.section h2 { color: #0c4a6e; border-bottom: 2px solid #e2e8f0;
              padding-bottom: 8px; margin-top: 0; }
.section h3 { color: #0369a1; margin-top: 16px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; 
        font-size: 13px; background: white; }
th { background: #0c4a6e; color: white; padding: 8px; text-align: left; }
td { padding: 8px; border-bottom: 1px solid #e2e8f0; }
tr:hover { background: #f1f5f9; }
.teaching { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-left: 4px solid #f59e0b; padding: 16px;
            border-radius: 6px; margin: 12px 0; }
.teaching h3 { color: #78350f; margin-top: 0; }
.worksheet { background: #e0f2fe; border: 2px dashed #0ea5e9;
             padding: 16px; border-radius: 6px; margin: 12px 0; }
.worksheet h3 { color: #075985; margin-top: 0; }
.worksheet ol { padding-left: 20px; }
.worksheet li { margin: 6px 0; }
.disclaimer { background: #fee2e2; border: 1px solid #ef4444;
              padding: 12px; border-radius: 6px; margin: 20px 0;
              font-size: 12px; color: #991b1b; }
.metric-card { display: inline-block; background: white;
               border: 1px solid #cbd5e1; padding: 12px 16px;
               margin: 6px; border-radius: 6px; min-width: 120px; }
.metric-card .label { font-size: 11px; color: #64748b; }
.metric-card .value { font-size: 20px; font-weight: bold;
                     color: #0ea5e9; font-family: 'Roboto Mono', monospace; }
.badge { display: inline-block; padding: 4px 12px; border-radius: 12px;
         font-size: 12px; font-weight: bold; }
.badge-pass { background: #dcfce7; color: #166534; }
.badge-cond { background: #fef3c7; color: #92400e; }
.badge-fail { background: #fee2e2; color: #991b1b; }
.footer { text-align: center; color: #64748b; font-size: 12px;
          padding: 20px; margin-top: 30px; }
@media print { body { background: white; } .no-print { display: none; } }
</style>
"""


def generate_ai_handout_html(session_data, teaching_notes):
    """AI 평가 결과 핸드아웃 HTML 생성"""
    mode_label = "배합비 모드" if session_data.get('mode') == 'recipe' else "컨셉 모드"
    mode_icon = "🧪" if session_data.get('mode') == 'recipe' else "💭"
    
    # 평균 점수 테이블
    mean_scores = session_data.get('mean_scores', {})
    scores_table = "<tr><th>평가 항목</th><th>평균</th><th>해석</th></tr>"
    for attr, val in mean_scores.items():
        interp = ("우수" if val >= 5.5 else
                  "양호" if val >= 5.0 else
                  "보통" if val >= 4.0 else "미흡")
        scores_table += f"<tr><td>{attr}</td><td>{val:.2f}</td><td>{interp}</td></tr>"
    
    # 합격 판정
    pass_status = session_data.get('pass_status', '미판정')
    badge_class = ("badge-pass" if "완전" in pass_status else
                   "badge-cond" if "조건부" in pass_status else "badge-fail")
    
    # 강사 노트 (teaching_notes가 있으면 사용, 없으면 기본 노트)
    instructor_notes = teaching_notes or [
        "이 데이터가 의미하는 바를 수강생과 토론해보세요.",
        "실제 조사와 AI 시뮬레이션의 차이점을 설명하세요.",
        "합격 기준을 왜 이렇게 설정했는지 근거를 제시하세요.",
    ]
    notes_html = "".join([f"<li>{n}</li>" for n in instructor_notes])
    
    # 워크시트 질문
    n_eval = len(session_data.get('evaluations', []))
    worksheet_qs = [
        f"이 {mode_label}의 장점과 한계를 각각 3가지씩 나열하시오.",
        "합격 판정 결과가 당신의 예상과 일치하는가? 이유는?",
        f"{n_eval}명의 패널 중 점수가 가장 낮았던 그룹의 공통점은 무엇인가?",
        "이 결과를 바탕으로 어떤 개선을 제안할 것인가?",
        "실제 조사를 진행한다면 어떤 추가 변수를 고려해야 하는가?",
    ]
    ws_html = "".join([f"<li>{q}</li>" for q in worksheet_qs])
    
    evaluations = session_data.get('evaluations', [])
    eval_summary = f"총 {len(evaluations)}명의 가상 패널 평가"
    
    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>AI 가상 소비자 조사 핸드아웃</title>{HANDOUT_CSS}</head>
<body>
<div class="header">
    <h1>{mode_icon} AI 가상 소비자 조사 핸드아웃</h1>
    <p><strong>제품</strong>: {session_data.get('product_name', 'N/A')}</p>
    <p><strong>모드</strong>: {mode_label} | 
       <strong>생성일</strong>: {datetime.date.today()}</p>
    <p><strong>패널</strong>: {eval_summary}</p>
</div>

<div class="section">
    <h2>📊 평가 결과 요약</h2>
    <p><strong>종합 판정:</strong> <span class="badge {badge_class}">{pass_status}</span></p>
    <h3>항목별 평균 점수</h3>
    <table>{scores_table}</table>
</div>

<div class="section">
    <h2>{mode_icon} 입력 정보</h2>
    <pre style="background:#f1f5f9; padding:12px; border-radius:4px; 
         font-family:'Roboto Mono', monospace; font-size:12px;">
{json.dumps(session_data.get('input_data', {}), ensure_ascii=False, indent=2)}
    </pre>
</div>

<div class="teaching">
    <h3>📚 강사 노트</h3>
    <p>수업 진행 시 다음 포인트를 강조하세요:</p>
    <ul>{notes_html}</ul>
</div>

<div class="worksheet">
    <h3>📝 학생 워크시트</h3>
    <p>다음 질문에 답하며 결과를 분석하세요:</p>
    <ol>{ws_html}</ol>
    <p><em>답변란:</em></p>
    <div style="border-bottom: 1px dashed #64748b; margin: 20px 0;"> </div>
    <div style="border-bottom: 1px dashed #64748b; margin: 20px 0;"> </div>
    <div style="border-bottom: 1px dashed #64748b; margin: 20px 0;"> </div>
    <div style="border-bottom: 1px dashed #64748b; margin: 20px 0;"> </div>
    <div style="border-bottom: 1px dashed #64748b; margin: 20px 0;"> </div>
</div>

<div class="disclaimer">
    <strong>⚠️ 면책 사항</strong><br>
    본 AI 가상 소비자 조사는 교육 및 초기 개발 탐색 목적으로 설계되었습니다.<br>
    • 실제 시장 반응의 완전한 예측이 아닙니다.<br>
    • 실제 소비자 조사를 대체하지 않습니다.<br>
    • 제품 출시 결정의 유일한 근거로 사용해서는 안 됩니다.<br>
    • AI의 추정치는 오차를 포함합니다.
</div>

<div class="footer">
    Sweet Lab · Natural Lab R&D · 식품 R&D 관능분석 통합 솔루션 v3.0<br>
    Generated with Claude AI · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>

</body></html>"""
    return html


# ============================================================================
# 조사지 관리 UI (공통 함수)
# ============================================================================

def _render_questionnaire_section(tab_key, test_type, html_fn):
    """질문지 HTML + 정답지 + 코드매핑 CSV 다운로드 UI"""
    try:
        html, df_meta = html_fn()
        d1, d2, d3 = st.columns(3)
        with d1:
            st.download_button(
                "📄 인쇄용 질문지 (HTML)",
                data=html.encode('utf-8'),
                file_name=f"질문지_{test_type}_{datetime.date.today()}.html",
                mime="text/html", key=f"{tab_key}_q_html",
                use_container_width=True
            )
        with d2:
            key_html = build_answer_key_html(test_type, df_meta)
            st.download_button(
                "🔑 정답지 / 코드매핑 (HTML)",
                data=key_html.encode('utf-8'),
                file_name=f"정답지_{test_type}_{datetime.date.today()}.html",
                mime="text/html", key=f"{tab_key}_a_html",
                use_container_width=True
            )
        with d3:
            df_to_csv_download(df_meta, f"코드매핑_{test_type}.csv",
                "📊 코드매핑 CSV", key=f"{tab_key}_map_csv")
    except Exception as e:
        st.error(f"질문지 생성 오류: {e}")


def form_manager_ui(tab_key, form_type, scale=9):
    """각 탭 상단 조사지 관리 UI"""
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
                blank = gen_anova_form(n, samples, scale=scale, random_fill=False)
                rand = gen_anova_form(n, samples, scale=scale, random_fill=True, seed=int(seed))
                d1, d2 = st.columns(2)
                with d1:
                    df_to_csv_download(blank, f"ANOVA_조사지양식_{n}명.csv",
                        "📥 빈 조사지 양식 (CSV)", key=f"{tab_key}_dl1")
                with d2:
                    df_to_csv_download(rand, f"ANOVA_랜덤데이터_{n}명.csv",
                        "🎲 랜덤 응답 데이터 (CSV)", key=f"{tab_key}_dl2")
                
                st.divider()
                st.markdown(f"**📄 인쇄용 질문지 ({scale}점 척도, 난수 코드 적용)**")
                attribute = st.text_input("평가 속성", "전반적 기호도",
                    key=f"{tab_key}_attr")
                _render_questionnaire_section(tab_key, 'anova',
                    lambda: build_anova_questionnaire(n, samples, attribute, scale, int(seed)))
                
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
                    help="0.33(삼점)/0.5(일-이점)보다 높아야 유의차")
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
            
            blank = gen_discrimination_form(n, t_type, random_fill=False)
            rand = gen_discrimination_form(n, t_type, random_fill=True,
                p_true=p_true, seed=int(seed))
            d1, d2 = st.columns(2)
            with d1:
                df_to_csv_download(blank, f"{t_type}_조사지양식_{n}명.csv",
                    "📥 빈 조사지 양식 (CSV)", key=f"{tab_key}_dl1")
            with d2:
                df_to_csv_download(rand, f"{t_type}_랜덤데이터_{n}명.csv",
                    "🎲 랜덤 응답 데이터 (CSV)", key=f"{tab_key}_dl2")
            
            st.divider()
            st.markdown("**📄 인쇄용 질문지**")
            attribute = st.text_input("평가 속성", "단맛 강도", key=f"{tab_key}_attr")
            
            if t_type == "삼점검정":
                _render_questionnaire_section(tab_key, 'triangle',
                    lambda: build_triangle_questionnaire(n, attribute, int(seed)))
            else:
                _render_questionnaire_section(tab_key, 'duo_trio',
                    lambda: build_duotrio_questionnaire(n, attribute, int(seed)))
            
            st.caption("💡 CSV 정답여부: 1=식별 성공, 0=실패")
            st.markdown("**미리보기**:")
            st.dataframe(rand.head(6), use_container_width=True)
        
        elif form_type == 'ranking':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 3, 100, 10, key=f"{tab_key}_np")
                samples_str = st.text_input("시료명 (쉼표 구분)", 
                    "시료A,시료B,시료C,시료D", key=f"{tab_key}_s")
            with c2:
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
                samples = [s.strip() for s in samples_str.split(",") if s.strip()]
            
            if samples:
                blank = gen_ranking_form(n, samples, random_fill=False)
                rand = gen_ranking_form(n, samples, random_fill=True, seed=int(seed))
                d1, d2 = st.columns(2)
                with d1:
                    df_to_csv_download(blank, f"순위법_조사지양식_{n}명.csv",
                        "📥 빈 조사지 양식 (CSV)", key=f"{tab_key}_dl1")
                with d2:
                    df_to_csv_download(rand, f"순위법_랜덤데이터_{n}명.csv",
                        "🎲 랜덤 응답 데이터 (CSV)", key=f"{tab_key}_dl2")
                
                st.divider()
                st.markdown("**📄 인쇄용 질문지**")
                attribute = st.text_input("평가 속성", "전반적 선호도",
                    key=f"{tab_key}_attr")
                _render_questionnaire_section(tab_key, 'ranking',
                    lambda: build_ranking_questionnaire(n, samples, attribute, int(seed)))
                
                st.caption("💡 1=가장 선호/강함, 숫자 클수록 낮은 순위")
                st.markdown("**미리보기**:")
                st.dataframe(rand.head(6), use_container_width=True)
        
        elif form_type == 'scaling':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 10, 200, 30, key=f"{tab_key}_np")
                prod_name = st.text_input("시료명", "신제품A",
                    key=f"{tab_key}_s")
            with c2:
                pass_scenario = st.radio("랜덤 시나리오",
                    ["합격 데이터", "불합격 데이터"],
                    key=f"{tab_key}_scn", horizontal=True)
                seed = st.number_input("난수 시드", value=42, key=f"{tab_key}_seed")
            
            blank = gen_scaling_form(n, prod_name, random_fill=False)
            rand = gen_scaling_form(n, prod_name, random_fill=True,
                pass_scenario=(pass_scenario == "합격 데이터"), seed=int(seed))
            d1, d2 = st.columns(2)
            with d1:
                df_to_csv_download(blank, f"평점법_조사지양식_{n}명.csv",
                    "📥 빈 조사지 양식 (CSV)", key=f"{tab_key}_dl1")
            with d2:
                df_to_csv_download(rand, f"평점법_랜덤데이터_{n}명.csv",
                    "🎲 랜덤 응답 데이터 (CSV)", key=f"{tab_key}_dl2")
            
            st.divider()
            st.markdown("**📄 인쇄용 질문지 (12항목 리커트 7점)**")
            _render_questionnaire_section(tab_key, 'scaling',
                lambda: build_scaling_questionnaire(n, prod_name, int(seed)))
            
            st.caption("💡 리커트 7점: 1=매우 약함/나쁨, 4=보통, 7=매우 강함/좋음")
            st.markdown("**미리보기**:")
            st.dataframe(rand.head(6), use_container_width=True)
        
        elif form_type == 'reliability':
            c1, c2 = st.columns(2)
            with c1:
                n = st.number_input("패널 수", 3, 50, 8, key=f"{tab_key}_np")
                samples_str = st.text_input("시료명 (쉼표 구분)", "A,B,C",
                    key=f"{tab_key}_s")
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
                        "📥 빈 조사지 양식 (CSV)", key=f"{tab_key}_dl1")
                with d2:
                    df_to_csv_download(rand, f"신뢰도_랜덤데이터_{n}명_{n_reps}반복.csv",
                        "🎲 랜덤 응답 데이터 (CSV)", key=f"{tab_key}_dl2")
                
                st.divider()
                st.markdown(f"**📄 인쇄용 질문지 ({n_reps}회차 × {n}명)**")
                attribute = st.text_input("평가 속성", "전반적 기호도",
                    key=f"{tab_key}_attr")
                _render_questionnaire_section(tab_key, 'reliability',
                    lambda: build_reliability_questionnaire(n, samples, n_reps, attribute, int(seed)))
                
                st.markdown("**미리보기**:")
                st.dataframe(rand.head(8), use_container_width=True)
# ============================================================================
# HTML 통합 리포트 생성 (기존 유지 + 확장)
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
body {{ font-family: 'Roboto', 'Malgun Gothic', sans-serif; max-width: 1100px;
       margin: 40px auto; padding: 20px; color: #1e293b; line-height: 1.7;
       background: #f8fafc; }}
.header {{ background: linear-gradient(135deg, #0f172a 0%, #1e40af 100%);
          color: #22d3ee; padding: 40px; border-radius: 12px;
          border-left: 6px solid #22d3ee; }}
.header h1 {{ margin: 0; font-size: 32px; color: #22d3ee; }}
.section {{ background: white; border-left: 4px solid #0ea5e9;
           padding: 25px; margin: 25px 0; border-radius: 8px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 15px; margin: 15px 0; }}
.metric {{ background: #f1f5f9; padding: 15px; border-radius: 8px; }}
.metric .label {{ color: #64748b; font-size: 13px; }}
.metric .value {{ font-size: 24px; font-weight: bold; color: #0ea5e9;
                  font-family: 'Roboto Mono', monospace; }}
table {{ width: 100%; border-collapse: collapse; margin: 15px 0;
         background: white; border-radius: 8px; overflow: hidden; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
th {{ background: #0c4a6e; color: white; }}
.ai-box {{ background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
          border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; }}
.badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px;
         font-size: 12px; font-weight: bold; }}
.badge.sig {{ background: #dcfce7; color: #166534; }}
.badge.nosig {{ background: #fee2e2; color: #991b1b; }}
</style></head><body>
<div class="header">
  <h1>◈ {project}</h1>
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
        html += f"""<div class="section"><h2>🔄 차이식별</h2>
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
</div>
<h4>순위합</h4>{r['rank_sum'].to_html(index=False)}"""
        if r.get('pairs') is not None:
            html += f"<h4>쌍별 비교</h4>{r['pairs'].to_html(index=False, float_format='%.4f')}"
        if 'friedman' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["friedman"])}</div>'
        html += "</div>"
    
    if 'scaling' in sections and 'scaling' in results:
        r = results['scaling']
        html += f"""<div class="section"><h2>📝 평점법 (Scaling Test)</h2>
<p><strong>제품:</strong> {r.get('product_name', 'N/A')} | 
   <strong>패널:</strong> {r.get('n_panel', 'N/A')}명</p>
<div class="metric-grid">
  <div class="metric"><div class="label">전반적 맛</div><div class="value">{r['mean_scores'].get('전반적 맛', 0):.2f}</div></div>
  <div class="metric"><div class="label">구입 의향</div><div class="value">{r['mean_scores'].get('구입 의향', 0):.2f}</div></div>
  <div class="metric"><div class="label">전반 만족도</div><div class="value">{r['mean_scores'].get('전반적 만족도', 0):.2f}</div></div>
  <div class="metric"><div class="label">합격 판정</div><div class="value" style="font-size:14px;">{r.get('pass_status', 'N/A')}</div></div>
</div>
<h4>12항목 평균</h4>
{pd.DataFrame([r['mean_scores']]).T.reset_index().rename(columns={{'index':'항목', 0:'평균'}}).to_html(index=False, float_format='%.2f')}
"""
        if 'scaling' in interpretations:
            html += f'<div class="ai-box"><h4>🤖 Claude AI 해석</h4>{md_to_html(interpretations["scaling"])}</div>'
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
    
    html += '<footer style="text-align:center;color:#94a3b8;padding:20px;"><p>© Sweet Lab · Natural Lab R&D · v3.0</p></footer></body></html>'
    return html


# ============================================================================
# 사이드바
# ============================================================================

with st.sidebar:
    st.title("⚙️ 설정")
    
    # 강의 모드 토글 (신규)
    st.session_state.teaching_mode = st.toggle(
        "🎓 강의 모드",
        value=st.session_state.teaching_mode,
        help="체크 시 교재 콘텐츠가 자동으로 펼쳐지고 강의 포인트가 하이라이트됩니다"
    )
    if st.session_state.teaching_mode:
        st.success("📚 강의 모드 ON")
    
    st.divider()
    st.subheader("🤖 Claude AI 해석")
    
    secrets_loaded = st.session_state.get('api_key_source') == 'secrets'
    
    if secrets_loaded:
        st.success("✅ API 키 자동 연결됨")
        if st.checkbox("다른 API 키 사용", key="override_key"):
            new_key = st.text_input(
                "Anthropic API Key (임시)", value="",
                type="password", help="이 세션에서만 사용됩니다")
            if new_key:
                st.session_state.api_key = new_key
                st.session_state.api_key_source = 'manual'
    else:
        st.session_state.api_key = st.text_input(
            "Anthropic API Key", value=st.session_state.api_key,
            type="password", help="결과 해석 시에만 사용")
        if st.session_state.api_key:
            st.caption("🔑 키 입력됨 (세션만 유지)")
    
    st.session_state.claude_model = st.selectbox(
        "모델", ["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"])
    
    st.divider()
    st.caption("💡 **Workflow**\n"
                "1. 조사지 양식 다운로드\n"
                "2. 조사 실시 & 작성\n"
                "3. CSV 업로드\n"
                "4. 분석 실행\n"
                "5. 통합 리포트 생성")
    st.caption(f"◈ v3.0 | {datetime.date.today()}")


# ============================================================================
# 메인 타이틀
# ============================================================================

st.title("🧪 식품 R&D 관능분석 통합 솔루션 v3.0")
st.caption("Sensory Analytics · AI Consumer Simulation")

tabs = st.tabs([
    "📊 종합차이(ANOVA)",
    "🔄 차이식별",
    "🔢 순위법",
    "📝 평점법",
    "👥 패널 신뢰도",
    "🎲 블라인드 코드",
    "📑 통합 리포트"
])


# ============================================================================
# TAB 1: ANOVA (개선)
# ============================================================================

with tabs[0]:
    st.header("종합적 차이 식별 (ANOVA)")
    st.info("9점 또는 7점 척도로 시료 간 유의차를 검정합니다.")
    
    # 교재 콘텐츠
    teaching_box("평점법(ANOVA) 개념", TEACHING_CONTENT['anova_concept'])
    teaching_highlight(TEACHING_CONTENT['anova_teaching'])
    
    # 척도 선택 (신규)
    col_scale, col_empty = st.columns([1, 2])
    with col_scale:
        selected_scale = st.radio(
            "📏 척도 선택",
            ["9점 척도", "7점 척도 (리커트)"],
            key="t1_scale",
            horizontal=True,
            help="9점: 정밀 분석 / 7점: 리커트 기반 표준"
        )
    scale_value = 9 if "9점" in selected_scale else 7
    
    form_manager_ui("t1", "anova", scale=scale_value)
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    uploaded = st.file_uploader("작성된 조사지 CSV", type="csv", key="t1_up")
    
    if uploaded:
        df = pd.read_csv(uploaded)
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
                    
                    # 지표 해석 expander (신규)
                    teaching_box("ANOVA 지표 정의 (F-value, p-value, p-adj 설명)",
                                TEACHING_CONTENT['anova_metrics'])
                    
                    st.dataframe(anova_table.style.format("{:.4f}"),
                        use_container_width=True)
                    
                    sample_idx = [idx for idx in anova_table.index if sample_col in idx][0]
                    p_sample = anova_table.loc[sample_idx, "PR(>F)"]
                    f_sample = anova_table.loc[sample_idx, "F"]
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("F-value (시료)", f"{f_sample:.3f}")
                    c2.metric("p-value (시료)", f"{p_sample:.4f}")
                    c3.metric("유의여부", "🟢 유의" if p_sample < alpha else "🔴 비유의")
                    
                    # 자동 해석 문구 (신규)
                    st.markdown("#### 🔍 결과 자동 해석")
                    interpretation_parts = []
                    
                    # 시료 효과 해석
                    if p_sample < 0.001:
                        sig_level = "**극도로 유의**(p<0.001)"
                    elif p_sample < 0.01:
                        sig_level = "**매우 유의**(p<0.01)"
                    elif p_sample < alpha:
                        sig_level = f"**유의**(p<{alpha})"
                    else:
                        sig_level = f"**비유의**(p≥{alpha})"
                    
                    interpretation_parts.append(
                        f"▸ **시료 효과**: F={f_sample:.3f}, p={p_sample:.4f} — "
                        f"시료 간 차이가 {sig_level}합니다."
                    )
                    
                    if p_sample < alpha:
                        interpretation_parts.append(
                            "  → 최소 한 쌍 이상의 시료 간 유의한 차이가 존재합니다. "
                            "구체적인 차이는 아래 Tukey HSD 사후검정을 확인하세요."
                        )
                    else:
                        interpretation_parts.append(
                            "  → 현재 데이터로는 시료 간 통계적 차이를 검출하지 못했습니다. "
                            "(차이가 없다는 증거가 아님에 주의)"
                        )
                    
                    # Two-way 패널 효과 해석 (있을 경우)
                    if panel_col != "(없음)":
                        panel_idx = [idx for idx in anova_table.index if panel_col in idx]
                        if panel_idx:
                            p_panel = anova_table.loc[panel_idx[0], "PR(>F)"]
                            f_panel = anova_table.loc[panel_idx[0], "F"]
                            if p_panel < alpha:
                                interpretation_parts.append(
                                    f"\n▸ **패널 효과**: F={f_panel:.3f}, p={p_panel:.4f} — "
                                    f"**패널 간 편차가 유의**합니다."
                                )
                                interpretation_parts.append(
                                    "  ⚠️ 평가자 간 기준이 일관되지 않을 가능성이 있습니다. "
                                    "Tab 5(패널 신뢰도)에서 상세 분석하세요."
                                )
                            else:
                                interpretation_parts.append(
                                    f"\n▸ **패널 효과**: F={f_panel:.3f}, p={p_panel:.4f} — "
                                    f"**패널 간 차이 비유의**. 평가 일관성 양호."
                                )
                    
                    st.info("\n".join(interpretation_parts))
                    
                    # Tukey HSD
                    st.subheader("🔬 Tukey HSD 사후검정")
                    tukey = pairwise_tukeyhsd(df[score_col], df[sample_col], alpha=alpha)
                    tukey_df = pd.DataFrame(
                        data=tukey._results_table.data[1:],
                        columns=tukey._results_table.data[0])
                    def highlight_sig(row):
                        return ['background-color: #d4edda' if row['reject'] else '' for _ in row]
                    st.dataframe(tukey_df.style.apply(highlight_sig, axis=1),
                        use_container_width=True)
                    
                    # Tukey 자동 해석
                    sig_pairs = tukey_df[tukey_df['reject'] == True]
                    if len(sig_pairs) > 0:
                        pair_text = ", ".join([f"{row['group1']} vs {row['group2']}" 
                                                for _, row in sig_pairs.iterrows()])
                        st.success(f"✅ 유의차 쌍 ({len(sig_pairs)}개): {pair_text}")
                    else:
                        st.warning("⚠️ Tukey HSD에서 유의한 쌍이 없음 — 추가 분석 고려")
                    
                    # 시각화
                    st.subheader("📈 시각화")
                    c_v1, c_v2 = st.columns(2)
                    with c_v1:
                        fig_box = px.box(df, x=sample_col, y=score_col,
                            color=sample_col, points="all",
                            title=f"시료별 점수 분포 ({scale_value}점 척도)")
                        apply_plotly_theme(fig_box)
                        st.plotly_chart(fig_box, use_container_width=True)
                    with c_v2:
                        summary = df.groupby(sample_col)[score_col].agg(['mean','std','count']).reset_index()
                        summary['se'] = summary['std']/np.sqrt(summary['count'])
                        fig_bar = go.Figure()
                        fig_bar.add_trace(go.Bar(
                            x=summary[sample_col], y=summary['mean'],
                            error_y=dict(type='data', array=summary['se']),
                            marker_color=PLOTLY_THEME['colorway'][:len(summary)],
                            text=summary['mean'].round(2), textposition='outside'))
                        fig_bar.update_layout(title=f"시료별 평균 ± SE",
                            yaxis_title=score_col, yaxis_range=[0, scale_value + 1])
                        apply_plotly_theme(fig_bar)
                        st.plotly_chart(fig_bar, use_container_width=True)
                    
                    st.session_state.results['anova'] = {
                        'model_type': model_type, 'anova_table': anova_table,
                        'tukey': tukey_df, 'alpha': alpha, 'summary': summary,
                        'f_sample': f_sample, 'p_sample': p_sample,
                        'scale': scale_value
                    }
                    
                    if st.session_state.api_key:
                        with st.spinner("Claude 해석 중..."):
                            prompt = f"""관능검사 ANOVA 결과:
분석: {model_type}, 척도: {scale_value}점, α={alpha}

ANOVA:
{anova_table.to_string()}

Tukey HSD:
{tukey_df.to_string()}

시료별 통계:
{summary.to_string()}

식품개발자 관점에서 실무적 해석과 후속 실험을 제안해주세요."""
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
# TAB 2: 차이식별 (시나리오 생성 추가)
# ============================================================================

with tabs[1]:
    st.header("차이 식별 검사 (Binomial Test)")
    st.info("**삼점**: 3개 중 다른 1개 식별 / **일-이점**: 기준과 동일한 것 식별")
    
    teaching_box("차이식별 검정 개념", TEACHING_CONTENT['discrimination_concept'])
    teaching_highlight(TEACHING_CONTENT['discrimination_teaching'])
    
    # 🎓 시나리오 생성 (신규)
    with st.expander("🎓 연습 시나리오 생성 — Claude가 케이스 스터디를 만들어줍니다",
                      expanded=st.session_state.teaching_mode):
        c1, c2 = st.columns(2)
        with c1:
            category = st.selectbox("제품 카테고리",
                ["음료", "유제품", "빙과", "스낵", "베이커리", "주류"],
                key="t2_cat")
        with c2:
            scenario_type = st.radio("검정 유형",
                ["삼점검정", "일-이점검정"],
                key="t2_scn_type", horizontal=True)
        
        if st.button("🚀 시나리오 생성", key="t2_gen_scn",
                     disabled=not st.session_state.api_key):
            if not st.session_state.api_key:
                st.warning("사이드바에서 API 키를 확인하세요.")
            else:
                with st.spinner("Claude가 케이스를 구성 중..."):
                    prompt = prompt_scenario_generation(category, scenario_type)
                    scenario = call_claude_api(prompt, st.session_state.api_key,
                        st.session_state.claude_model,
                        system_msg="당신은 식품 R&D 교육 과정의 전문 강사입니다.",
                        max_tokens=3000)
                    st.session_state.last_scenario = {
                        'category': category,
                        'type': scenario_type,
                        'content': scenario
                    }
        
        if st.session_state.last_scenario:
            scn = st.session_state.last_scenario
            st.markdown(f"**카테고리**: {scn['category']} | **유형**: {scn['type']}")
            st.markdown(scn['content'])
            # 다운로드
            scenario_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>케이스 스터디</title>{HANDOUT_CSS}</head><body>
<div class="header"><h1>🎓 연습 케이스 스터디</h1>
<p>{scn['category']} | {scn['type']} | {datetime.date.today()}</p></div>
<div class="section">{scn['content']}</div>
</body></html>"""
            st.download_button("📥 케이스 스터디 HTML 다운로드",
                data=scenario_html.encode('utf-8'),
                file_name=f"케이스_{scn['category']}_{datetime.date.today()}.html",
                mime="text/html", key="t2_scn_dl")
    
    st.divider()
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
                        marker_color=['#64748b', '#3b82f6' if p_val_u < alpha_u else '#f59e0b', '#10b981'],
                        text=[f"{expected:.1f}", f"{correct_u}", f"{min_c_u}"],
                        textposition='outside'))
                    fig.update_layout(title="정답자수 비교")
                    apply_plotly_theme(fig)
                    st.plotly_chart(fig, use_container_width=True)
                with c_v2:
                    k = np.arange(0, total_u+1)
                    pmf = binom.pmf(k, total_u, p0_u)
                    colors = ['#ef4444' if ki >= min_c_u else '#475569' for ki in k]
                    fig2 = go.Figure()
                    fig2.add_trace(go.Bar(x=k, y=pmf, marker_color=colors))
                    fig2.add_vline(x=correct_u, line_dash="dash", line_color="#3b82f6",
                        annotation_text=f"실제({correct_u})")
                    fig2.update_layout(title="이항분포 (빨강=유의영역)")
                    apply_plotly_theme(fig2)
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
                ["삼점검정 (Triangle)", "일-이점검정 (Duo-Trio)"], key="t2_tt_direct")
            total_p = st.number_input("전체 패널 수", 5, 500, 30, key="t2_n_direct")
            correct_p = st.number_input("정답자 수", 0, int(total_p), 15, key="t2_c_direct")
            alpha = st.selectbox("유의수준 α", [0.05, 0.01, 0.001], key="t2_a_direct")
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

식품개발 관점에서 해석과 후속 액션을 제안해주세요."""
            with st.spinner("해석 중..."):
                interp = call_claude_api(prompt, st.session_state.api_key,
                    st.session_state.claude_model)
                st.session_state.interpretations['discrimination'] = interp
                st.markdown(interp)
# ============================================================================
# TAB 3: 순위법 (3가지 검정 병렬 + 동질군 표시)
# ============================================================================

with tabs[2]:
    st.header("순위법 (Friedman Test)")
    st.info("비모수 검정 + 3가지 방법 병렬 분석 + 동질군(a, b, ab) 표시")
    
    # 교재 콘텐츠
    teaching_box("순위법 개념", TEACHING_CONTENT['ranking_concept'])
    teaching_box("3가지 검정법 비교", TEACHING_CONTENT['ranking_three_tests'])
    teaching_box("동질군 (a, b, ab) 해석", TEACHING_CONTENT['ranking_homogeneous'])
    teaching_highlight(TEACHING_CONTENT['ranking_teaching'])
    
    form_manager_ui("t3", "ranking")
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    uploaded_r = st.file_uploader("작성된 조사지 CSV", type="csv", key="t3_up")
    
    if uploaded_r:
        dfr = pd.read_csv(uploaded_r)
        st.success(f"✅ {len(dfr)}행 로드")
        st.dataframe(dfr.head(), use_container_width=True)
        
        num_cols = dfr.select_dtypes(include=np.number).columns.tolist()
        sample_cols = st.multiselect(
            "시료 컬럼 선택 (순위값이 있는 컬럼들)", num_cols,
            default=num_cols if len(num_cols) <= 6 else num_cols[:4],
            key="t3_sc",
            help="예: 시료A, 시료B, 시료C ..."
        )
        alpha_r = st.slider("유의수준 α", 0.001, 0.10, 0.05, 0.001, key="t3_a")
        
        if st.button("🚀 순위법 분석 실행 (3가지 검정)", type="primary", key="t3_run"):
            if len(sample_cols) < 2:
                st.error("시료 컬럼을 2개 이상 선택하세요.")
            else:
                try:
                    # 데이터 정리
                    data_clean = dfr[sample_cols].dropna()
                    data_matrix = data_clean.values
                    n = len(data_matrix)  # 패널 수
                    k = len(sample_cols)  # 시료 수
                    
                    st.markdown(f"**분석 조건:** 패널 n = {n}, 시료 k = {k}")
                    
                    if n < 3:
                        st.error("패널이 3명 이상 필요합니다.")
                    else:
                        # 순위합 계산
                        rank_sums = {}
                        for i, s in enumerate(sample_cols):
                            rank_sums[s] = int(data_matrix[:, i].sum())
                        
                        st.subheader("📊 순위합 요약")
                        rs_df = pd.DataFrame([
                            {'시료': s, '순위합': R, '평균순위': R/n}
                            for s, R in sorted(rank_sums.items(), key=lambda x: x[1])
                        ])
                        st.dataframe(rs_df.style.format({'평균순위': '{:.2f}'}),
                                    use_container_width=True)
                        st.caption("💡 순위합이 **낮을수록 선호도 높음** (1=최상)")
                        
                        # ═══════════════════════════════════════════════════
                        # (1) 순위합 범위 검정
                        # ═══════════════════════════════════════════════════
                        st.markdown("---")
                        st.subheader("🔬 (1) 순위합 범위 검정 (Kramer's Rank Sum)")
                        range_df, range_info = friedman_rank_range_test(
                            rank_sums, n, k, alpha=alpha_r)
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("기댓값 E(R)", f"{range_info['mean_R']:.1f}")
                        c2.metric("유의 하한", f"{range_info['R_lower']:.2f}")
                        c3.metric("유의 상한", f"{range_info['R_upper']:.2f}")
                        c4.metric("z(α/2)", f"{range_info['z_crit']:.3f}")
                        
                        def highlight_range(row):
                            return ['background-color: #fef3c7' if '✓' in row['유의'] 
                                    else '' for _ in row]
                        st.dataframe(range_df.style.apply(highlight_range, axis=1),
                                    use_container_width=True)
                        st.caption(f"💡 순위합이 [{range_info['R_lower']:.1f}, "
                                  f"{range_info['R_upper']:.1f}] 범위 **밖**이면 특이값")
                        
                        # ═══════════════════════════════════════════════════
                        # (2) 순위합 차이값 검정 ⭐ 동질군 근거
                        # ═══════════════════════════════════════════════════
                        st.markdown("---")
                        st.subheader("🔬 (2) 순위합 차이값 검정 ⭐ (동질군 근거)")
                        diff_df, diff_info = friedman_rank_difference_test(
                            rank_sums, n, k, alpha=alpha_r)
                        
                        c1, c2 = st.columns(2)
                        c1.metric("임계값 (LSD)", f"{diff_info['threshold']:.2f}")
                        c2.metric("z(α/2)", f"{diff_info['z_crit']:.3f}")
                        
                        def highlight_diff(row):
                            return ['background-color: #dcfce7' if '✓' in row['유의차'] 
                                    else '' for _ in row]
                        st.dataframe(diff_df.style.apply(highlight_diff, axis=1),
                                    use_container_width=True)
                        st.caption(f"💡 |R1-R2| > {diff_info['threshold']:.2f} 이면 유의차")
                        
                        # 동질군 표시
                        st.markdown("#### 🏷️ 동질군 (Homogeneous Groups)")
                        homo = diff_info['homogeneous_groups']
                        
                        homo_display = []
                        for s in sorted(rank_sums.keys(), key=lambda x: rank_sums[x]):
                            homo_display.append({
                                '시료': s,
                                '순위합': rank_sums[s],
                                '동질군': homo[s],
                                '해석': f"{s} ({homo[s]})"
                            })
                        homo_df = pd.DataFrame(homo_display)
                        st.dataframe(homo_df, use_container_width=True)
                        
                        # 동질군 해석 자동 문구
                        unique_groups = set(homo.values())
                        if len(unique_groups) == 1:
                            st.warning("⚠️ 모든 시료가 동일 그룹 — 유의차 없음")
                        else:
                            groups_explanation = []
                            # 각 그룹별 시료 집합
                            grp_to_samples = {}
                            for s, g in homo.items():
                                grp_to_samples.setdefault(g, []).append(s)
                            
                            explanations = []
                            for g, samps in grp_to_samples.items():
                                explanations.append(
                                    f"• **그룹 '{g}'**: {', '.join(samps)}"
                                )
                            
                            st.success("✅ 동질군 분리 완료:\n" + "\n".join(explanations))
                        
                        # ═══════════════════════════════════════════════════
                        # (3) Friedman χ² 검정
                        # ═══════════════════════════════════════════════════
                        st.markdown("---")
                        st.subheader("🔬 (3) Friedman χ² 검정")
                        chi2_result = friedman_chi_square_full(
                            rank_sums, n, k, alpha=alpha_r)
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("χ² 통계량", f"{chi2_result['chi2_stat']:.3f}")
                        c2.metric("자유도 df", f"{chi2_result['df']}",
                                help=f"df = k - 1 = {k} - 1 = {chi2_result['df']}")
                        c3.metric(f"χ² 임계값 (α={alpha_r})", 
                                f"{chi2_result['chi2_crit']:.3f}")
                        c4.metric("p-value", f"{chi2_result['p_value']:.4f}")
                        
                        # 자유도 강조 박스
                        st.markdown(
                            f'<div style="background: #fef3c7; '
                            f'border-left: 3px solid #f59e0b; padding: 12px; '
                            f'margin: 10px 0; border-radius: 4px;">'
                            f'<strong style="color: #b45309;">📌 자유도 기본값</strong><br>'
                            f'시료 수 <code>k = {k}</code> → 자유도 <code>df = k - 1 = {chi2_result["df"]}</code><br>'
                            f'χ²({alpha_r}, df={chi2_result["df"]}) = <strong>{chi2_result["chi2_crit"]:.3f}</strong>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        
                        if chi2_result['significant']:
                            st.success(
                                f"✅ **유의차 있음** — "
                                f"χ²={chi2_result['chi2_stat']:.3f} > "
                                f"임계값 {chi2_result['chi2_crit']:.3f}"
                            )
                        else:
                            st.warning(
                                f"⚠️ **유의차 없음** — "
                                f"χ²={chi2_result['chi2_stat']:.3f} ≤ "
                                f"임계값 {chi2_result['chi2_crit']:.3f}"
                            )
                        
                        # ═══════════════════════════════════════════════════
                        # 종합 시각화 (동질군 포함 막대그래프)
                        # ═══════════════════════════════════════════════════
                        st.markdown("---")
                        st.subheader("📈 종합 시각화")
                        
                        c_v1, c_v2 = st.columns(2)
                        
                        with c_v1:
                            # 순위합 막대그래프 + 동질군 문자
                            sorted_samples = sorted(rank_sums.keys(), 
                                                   key=lambda x: rank_sums[x])
                            bar_x = sorted_samples
                            bar_y = [rank_sums[s] for s in sorted_samples]
                            bar_text = [f"{rank_sums[s]}<br><b>({homo[s]})</b>" 
                                       for s in sorted_samples]
                            
                            fig_bar = go.Figure()
                            fig_bar.add_trace(go.Bar(
                                x=bar_x, y=bar_y,
                                text=bar_text, textposition='outside',
                                marker=dict(
                                    color=bar_y,
                                    colorscale=[[0, '#10b981'], [1, '#ef4444']],
                                    line=dict(color='#94a3b8', width=1)
                                )
                            ))
                            # 유의 범위 표시
                            fig_bar.add_hline(
                                y=range_info['R_upper'], line_dash="dot",
                                line_color="#f59e0b",
                                annotation_text=f"유의 상한 {range_info['R_upper']:.1f}",
                                annotation_position="top right"
                            )
                            fig_bar.add_hline(
                                y=range_info['R_lower'], line_dash="dot",
                                line_color="#f59e0b",
                                annotation_text=f"유의 하한 {range_info['R_lower']:.1f}",
                                annotation_position="bottom right"
                            )
                            fig_bar.add_hline(
                                y=range_info['mean_R'], line_dash="dash",
                                line_color="#94a3b8",
                                annotation_text=f"E(R)={range_info['mean_R']:.1f}"
                            )
                            fig_bar.update_layout(
                                title="순위합 + 동질군 (낮을수록 선호)",
                                yaxis_title="순위합", xaxis_title="시료"
                            )
                            apply_plotly_theme(fig_bar)
                            st.plotly_chart(fig_bar, use_container_width=True)
                        
                        with c_v2:
                            # 평균 순위 (역순으로 뒤집기 - 높을수록 선호)
                            mean_ranks = {s: (k + 1) - (rank_sums[s] / n) 
                                         for s in sample_cols}
                            mr_df = pd.DataFrame([
                                {'시료': s, '선호도_점수': mr}
                                for s, mr in sorted(mean_ranks.items(), 
                                                   key=lambda x: -x[1])
                            ])
                            fig_pref = go.Figure()
                            fig_pref.add_trace(go.Bar(
                                x=mr_df['시료'], y=mr_df['선호도_점수'],
                                text=mr_df['선호도_점수'].round(2),
                                textposition='outside',
                                marker=dict(
                                    color=PLOTLY_THEME['colorway'][:len(mr_df)],
                                    line=dict(color='#94a3b8', width=1)
                                )
                            ))
                            fig_pref.update_layout(
                                title="선호도 점수 (변환: k+1 - 평균순위)",
                                yaxis_title="선호도 (높을수록 선호)"
                            )
                            apply_plotly_theme(fig_pref)
                            st.plotly_chart(fig_pref, use_container_width=True)
                        
                        # ═══════════════════════════════════════════════════
                        # 결과 저장 & AI 해석
                        # ═══════════════════════════════════════════════════
                        rank_sum_df = pd.DataFrame([
                            {'시료': s, '순위합': R, '동질군': homo[s]}
                            for s, R in sorted(rank_sums.items(), key=lambda x: x[1])
                        ])
                        
                        st.session_state.results['friedman'] = {
                            'f_stat': chi2_result['chi2_stat'],
                            'p_value': chi2_result['p_value'],
                            'n_panel': n, 'n_samples': k,
                            'rank_sum': rank_sum_df,
                            'pairs': diff_df,
                            'homogeneous_groups': homo,
                            'df': chi2_result['df'],
                            'chi2_crit': chi2_result['chi2_crit'],
                            'range_test': range_df.to_dict(orient='records'),
                            'diff_threshold': diff_info['threshold']
                        }
                        
                        # AI 해석
                        if st.session_state.api_key:
                            with st.spinner("Claude 해석 중..."):
                                homo_text = ", ".join([f"{s}({g})" for s, g in homo.items()])
                                prompt = f"""순위법(Friedman Test) 3가지 검정 결과:

[데이터] 패널 {n}명 × 시료 {k}개, α={alpha_r}

[순위합 (낮을수록 선호)]
{rank_sum_df.to_string()}

[(1) 순위합 범위 검정]
기댓값 E(R)={range_info['mean_R']:.1f}, 유의범위 [{range_info['R_lower']:.1f}, {range_info['R_upper']:.1f}]
특이값 시료: {', '.join([r['시료'] for r in range_df.to_dict(orient='records') if '✓' in r['유의']])}

[(2) 순위합 차이값 검정 (LSD for ranks)]
임계값 = {diff_info['threshold']:.2f}
동질군: {homo_text}
{diff_df.to_string()}

[(3) Friedman χ² 검정]
χ² = {chi2_result['chi2_stat']:.3f} (자유도 {chi2_result['df']})
p-value = {chi2_result['p_value']:.4f}
임계값 χ²({alpha_r}, df={chi2_result['df']}) = {chi2_result['chi2_crit']:.3f}
결론: {'유의차 있음' if chi2_result['significant'] else '유의차 없음'}

식품 R&D 관점에서 다음을 해석해주세요:
1. 3가지 검정 결과의 종합 해석
2. 동질군 패턴이 의미하는 실무적 함의
3. 가장 선호된 시료와 그 원인 추정
4. 후속 실험 제안
"""
                                interp = call_claude_api(prompt, 
                                    st.session_state.api_key,
                                    st.session_state.claude_model,
                                    max_tokens=3500)
                                st.session_state.interpretations['friedman'] = interp
                                st.markdown("### 🤖 Claude AI 해석")
                                st.markdown(interp)
                
                except Exception as e:
                    st.error(f"분석 오류: {e}")
                    import traceback
                    with st.expander("상세 오류"):
                        st.code(traceback.format_exc())
# ============================================================================
# TAB 4: 평점법 (Scaling Test) - 신규 탭 ⭐
# ============================================================================

with tabs[3]:
    st.header("평점법 (Scaling Test)")
    st.info(
        "리커트 7점 척도로 12항목을 평가하는 단일 시료 다차원 분석.\n\n"
        "**합격 기준 3가지**: 전반적 맛 / 구입 의향 / 전반적 만족도 모두 ≥ 5.0"
    )
    
    # 교재 콘텐츠
    teaching_box("평점법(Scaling Test) 개념", TEACHING_CONTENT['scaling_concept'])
    teaching_box("조사지 설계 원리", TEACHING_CONTENT['scaling_questionnaire_design'])
    
    # 4-1. 조사지 관리
    form_manager_ui("t4", "scaling")
    
    st.divider()
    
    # 4-2. 실제 조사 업로드 & 분석
    st.subheader("📤 실제 조사 결과 업로드 & 분석")
    st.caption("오프라인 조사에서 수집한 12항목 리커트 점수를 업로드하세요.")
    
    uploaded_sc = st.file_uploader(
        "작성된 조사지 CSV (12항목 × N명)",
        type="csv", key="t4_up"
    )
    
    if uploaded_sc:
        try:
            dfsc = pd.read_csv(uploaded_sc)
            st.success(f"✅ {len(dfsc)}행 로드")
            st.dataframe(dfsc.head(10), use_container_width=True)
            
            # 항목 컬럼 매핑 확인
            missing_attrs = [a for a in SCALING_ATTRIBUTES if a not in dfsc.columns]
            if missing_attrs:
                st.warning(f"⚠️ 누락 항목: {', '.join(missing_attrs)}")
            
            available_attrs = [a for a in SCALING_ATTRIBUTES if a in dfsc.columns]
            
            if len(available_attrs) < 3:
                st.error("최소 3개 이상의 평가 항목이 필요합니다.")
            else:
                # 시료명 확인
                if '시료' in dfsc.columns:
                    product_name = dfsc['시료'].iloc[0] if len(dfsc) > 0 else "시료A"
                else:
                    product_name = st.text_input("제품명", "신제품A", key="t4_pn")
                
                if st.button("🚀 평점법 분석 실행", type="primary", key="t4_run"):
                    # 각 항목 통계 계산
                    stats_rows = []
                    for attr in available_attrs:
                        col_data = pd.to_numeric(dfsc[attr], errors='coerce').dropna()
                        if len(col_data) > 0:
                            mean = col_data.mean()
                            std = col_data.std()
                            se = std / np.sqrt(len(col_data))
                            stats_rows.append({
                                '항목': attr,
                                '평균': mean,
                                'SD': std,
                                'SE': se,
                                'N': len(col_data),
                                '판정': '✓ 합격선 통과' if mean >= 5.0 else '✗ 미달'
                            })
                    stats_df = pd.DataFrame(stats_rows)
                    mean_scores = dict(zip(stats_df['항목'], stats_df['평균']))
                    
                    # ──────────────────────────────
                    # 1. 통계 표
                    # ──────────────────────────────
                    st.markdown("### 📊 12항목 평균/SD/SE")
                    
                    def highlight_pass(row):
                        bg = '#dcfce7' if '✓' in row['판정'] else '#fef3c7'
                        return [f'background-color: {bg}' for _ in row]
                    
                    st.dataframe(
                        stats_df.style
                        .apply(highlight_pass, axis=1)
                        .format({'평균': '{:.2f}', 'SD': '{:.2f}', 'SE': '{:.3f}'}),
                        use_container_width=True
                    )
                    
                    # ──────────────────────────────
                    # 2. 합격 판정 (3단계)
                    # ──────────────────────────────
                    st.markdown("### 🏆 합격 판정")
                    
                    criteria_results = {}
                    for c in SCALING_PASS_CRITERIA:
                        if c in mean_scores:
                            criteria_results[c] = {
                                'score': mean_scores[c],
                                'pass': mean_scores[c] >= 5.0
                            }
                    
                    passed_count = sum(1 for r in criteria_results.values() if r['pass'])
                    total_criteria = len(criteria_results)
                    
                    if total_criteria == 0:
                        pass_status = "판정 불가 (합격 기준 항목 없음)"
                        badge_class = "pass-badge-fail"
                    elif passed_count == total_criteria:
                        pass_status = "🟢 완전 합격 (3기준 모두 통과)"
                        badge_class = "pass-badge-full"
                    elif passed_count == 2:
                        pass_status = "🟡 조건부 합격 (2기준 통과)"
                        badge_class = "pass-badge-conditional"
                    else:
                        pass_status = f"🔴 불합격 ({passed_count}/{total_criteria} 기준만 통과)"
                        badge_class = "pass-badge-fail"
                    
                    st.markdown(
                        f'<div style="text-align: center; margin: 20px 0;">'
                        f'<span class="{badge_class}" style="font-size: 18px; '
                        f'padding: 14px 24px;">{pass_status}</span></div>',
                        unsafe_allow_html=True
                    )
                    
                    # 합격 기준 상세
                    cc1, cc2, cc3 = st.columns(3)
                    for i, (c, r) in enumerate(criteria_results.items()):
                        col = [cc1, cc2, cc3][i % 3]
                        with col:
                            score = r['score']
                            status = "🟢 통과" if r['pass'] else "🔴 미달"
                            st.metric(c, f"{score:.2f}", status,
                                     delta_color="normal")
                    
                    # ──────────────────────────────
                    # 3. 시각화
                    # ──────────────────────────────
                    st.markdown("### 📈 시각화")
                    v1, v2 = st.columns(2)
                    
                    with v1:
                        # 막대그래프 (합격선 5.0)
                        colors_bar = ['#3b82f6' if m >= 5.0 else '#f59e0b' 
                                      for m in stats_df['평균']]
                        # 합격 3기준은 진한 색
                        for i, attr in enumerate(stats_df['항목']):
                            if attr in SCALING_PASS_CRITERIA:
                                if stats_df['평균'].iloc[i] >= 5.0:
                                    colors_bar[i] = '#10b981'
                                else:
                                    colors_bar[i] = '#ef4444'
                        
                        fig_bar = go.Figure()
                        fig_bar.add_trace(go.Bar(
                            x=stats_df['항목'], y=stats_df['평균'],
                            error_y=dict(type='data', array=stats_df['SE']),
                            marker=dict(color=colors_bar,
                                       line=dict(color='#94a3b8', width=1)),
                            text=stats_df['평균'].round(2), textposition='outside'
                        ))
                        fig_bar.add_hline(y=5.0, line_dash="dash",
                            line_color="#3b82f6",
                            annotation_text="합격선 5.0",
                            annotation_position="right")
                        fig_bar.update_layout(
                            title="12항목 평균 점수 ± SE",
                            yaxis=dict(range=[0, 7.5], title="점수 (리커트 7점)"),
                            xaxis=dict(tickangle=-35),
                            height=500
                        )
                        apply_plotly_theme(fig_bar)
                        st.plotly_chart(fig_bar, use_container_width=True)
                    
                    with v2:
                        # 레이더차트
                        fig_radar = go.Figure()
                        fig_radar.add_trace(go.Scatterpolar(
                            r=stats_df['평균'].tolist() + [stats_df['평균'].iloc[0]],
                            theta=stats_df['항목'].tolist() + [stats_df['항목'].iloc[0]],
                            fill='toself', name=product_name,
                            line=dict(color='#3b82f6', width=2),
                            fillcolor='rgba(59, 130, 246, 0.25)'
                        ))
                        # 합격선 5.0 원
                        fig_radar.add_trace(go.Scatterpolar(
                            r=[5.0] * (len(stats_df) + 1),
                            theta=stats_df['항목'].tolist() + [stats_df['항목'].iloc[0]],
                            name='합격선 5.0', 
                            line=dict(color='#f59e0b', dash='dash', width=1),
                            showlegend=True
                        ))
                        fig_radar.update_layout(
                            polar=dict(
                                radialaxis=dict(visible=True, range=[0, 7],
                                               gridcolor='rgba(30, 64, 175, 0.3)'),
                                angularaxis=dict(gridcolor='rgba(30, 64, 175, 0.3)'),
                                bgcolor='rgba(248, 250, 252, 0.5)'
                            ),
                            title="품질 프로파일 (Radar Chart)",
                            height=500
                        )
                        apply_plotly_theme(fig_radar)
                        st.plotly_chart(fig_radar, use_container_width=True)
                    
                    # 결과 저장
                    st.session_state.results['scaling'] = {
                        'product_name': product_name,
                        'n_panel': len(dfsc),
                        'stats_df': stats_df,
                        'mean_scores': mean_scores,
                        'pass_status': pass_status,
                        'criteria_results': criteria_results
                    }
                    
                    # AI 해석
                    if st.session_state.api_key:
                        if st.button("🤖 Claude AI 해석 실행", key="t4_ai_run"):
                            with st.spinner("Claude가 종합 해석 중..."):
                                prompt = f"""평점법(Scaling Test) 결과 해석:

[제품] {product_name}
[패널] {len(dfsc)}명

[12항목 평균 점수 (리커트 7점)]
{stats_df.to_string()}

[합격 판정 (3기준 모두 ≥ 5.0 요구)]
{pass_status}

합격 기준별 점수:
{chr(10).join([f"- {c}: {r['score']:.2f} ({'통과' if r['pass'] else '미달'})" 
               for c, r in criteria_results.items()])}

식품 R&D 관점에서 다음을 해석해주세요:
1. 전체 품질 프로파일의 강점과 약점
2. 합격 판정 결과에 대한 실무적 해석
3. 점수가 낮은 항목들이 시사하는 개발 방향
4. 균형 있는 프로파일인지, 특정 항목 편향이 있는지
5. 소비자 수용성 및 시장성 예측
6. 구체적 개선 제안 3가지
"""
                                interp = call_claude_api(
                                    prompt, st.session_state.api_key,
                                    st.session_state.claude_model,
                                    max_tokens=3500
                                )
                                st.session_state.interpretations['scaling'] = interp
                                st.markdown("### 🤖 Claude AI 해석")
                                st.markdown(interp)
        except Exception as e:
            st.error(f"분석 오류: {e}")
            import traceback
            with st.expander("상세 오류"):
                st.code(traceback.format_exc())
    
    st.divider()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 4-3. AI 가상 소비자 조사 ⭐⭐⭐
    # ═══════════════════════════════════════════════════════════════════════
    st.subheader("🤖 AI 가상 소비자 조사")
    
    # 섹션 안내 (상시 표시)
    st.warning(TEACHING_CONTENT['ai_panel_overview'].replace('<br>', '\n').replace('<strong>', '**').replace('</strong>', '**').replace('<em>', '_').replace('</em>', '_'), icon="⚠️")
    
    # 교재 Expander들
    teaching_box("AI 가상 패널의 동작 원리 (3단계)", TEACHING_CONTENT['ai_panel_mechanism'])
    teaching_box("AI는 정말로 '훈련'된 것인가?", TEACHING_CONTENT['ai_panel_training'])
    teaching_box("배합비 모드 vs 컨셉 모드", TEACHING_CONTENT['ai_panel_modes'])
    
    # 패널 수 선택 (신규)
    st.markdown("#### 👥 가상 패널 구성")
    
    n_col1, n_col2 = st.columns([1, 2])
    with n_col1:
        n_panels = st.slider(
            "패널 수",
            min_value=5, max_value=30, value=20, step=5,
            key="t4_n_panels",
            help="한국 인구 분포를 유지하며 선택됩니다 (기본 20명). "
                 "패널이 많을수록 API 호출 시간이 늘어납니다."
        )
    with n_col2:
        # 예상 소요 시간 동적 계산
        est_min = n_panels * 3
        est_max = n_panels * 8
        st.caption(
            f"📊 **{n_panels}명** 평가 진행 (예상 소요: 약 {est_min}~{est_max}초)\n\n"
            "• 5~10명: 빠른 테스트 (데모용)\n"
            "• 15~20명: 표준 (권장)\n"
            "• 25~30명: 정밀 평가 (시간·비용 증가)"
        )
        if n_panels >= 25:
            st.warning(
                f"⚠️ {n_panels}명은 API 응답에 2~4분 걸릴 수 있습니다. "
                "타임아웃 발생 시 패널 수를 줄여 재시도하세요.",
                icon="⏱️"
            )
    
    # 선택된 페르소나 미리 계산 (재사용)
    selected_personas = select_personas(n_panels)
    
    # 페르소나 열람 expander
    with st.expander(f"👥 선택된 {len(selected_personas)}명 가상 패널 프로필 열람",
                      expanded=False):
        st.caption("각 패널의 인구통계, 선호/혐오, 미각 특성, 구매 성향을 확인하세요. "
                   f"(한국 인구 분포 반영 · 총 {len(selected_personas)}명)")
        
        # 분포 요약
        from collections import Counter
        dist = Counter()
        for p in selected_personas:
            age = p['age']; gender = p['gender']
            if 20 <= age < 30: key = f"20대 {gender}"
            elif 30 <= age < 40: key = f"30대 {gender}"
            elif 40 <= age < 50: key = f"40대 {gender}"
            else: key = f"50대+ {gender}"
            dist[key] += 1
        dist_text = " · ".join([f"{k} {v}명" for k, v in sorted(dist.items())])
        st.caption(f"**분포:** {dist_text}")
        
        for i in range(0, len(selected_personas), 4):
            cols = st.columns(4)
            for j, p in enumerate(selected_personas[i:i+4]):
                with cols[j]:
                    tags_html = "".join([
                        f'<span class="tag">{t}</span>' 
                        for t in p['loves'][:3]
                    ])
                    card_html = f"""
                    <div class="persona-card">
                        <h4>{p['id']} · {p['name']}</h4>
                        <div class="demo">
                            {p['age']}세 · {p['gender']} · {p['region']}<br>
                            {p['occupation']}
                        </div>
                        <hr style="border-color: #cbd5e1; margin: 8px 0;">
                        <div style="font-size: 11px; color: #94a3b8;">
                            <strong>좋아함:</strong><br>{tags_html}
                        </div>
                        <div style="font-size: 10px; color: #64748b; margin-top: 8px;">
                            <strong>성향:</strong> {p['bias']}
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 모드 선택
    st.markdown("#### 🎯 평가 모드 선택")
    
    mode_choice = st.radio(
        "어떤 관점으로 평가할까요?",
        ["🧪 배합비 모드 — 원료와 비율 기반 맛 평가",
         "💭 컨셉 모드 — 제품 컨셉/포지셔닝 기반 인식 평가"],
        key="t4_mode", horizontal=False
    )
    
    is_recipe_mode = "배합비" in mode_choice
    # ═══════════════════════════════════════════════════════════════════════
    # 🧪 배합비 모드
    # ═══════════════════════════════════════════════════════════════════════
    if is_recipe_mode:
        st.markdown("#### 🧪 배합비 입력")
        
        recipe_col1, recipe_col2 = st.columns(2)
        with recipe_col1:
            recipe_product_name = st.text_input(
                "제품명", "복숭아 스파클링 v1",
                key="t4_recipe_name"
            )
        with recipe_col2:
            st.caption("💡 자유 형식으로 입력하세요. AI가 자동 정규화합니다.")
        
        recipe_text = st.text_area(
            "배합비 (자유 서술)",
            placeholder="예시:\n복숭아 농축액 15%, 설탕 4%, 구연산 0.3%, 향료 0.2%\n또는\n복숭아 주스에 설탕 좀, 산도조절용 구연산",
            height=140,
            key="t4_recipe_text"
        )
        
        process_text = st.text_area(
            "제조 공정 (선택)",
            placeholder="예: 80°C × 10분 살균, 냉각 후 충전",
            height=80, key="t4_process_text"
        )
        
        # Stage 0 실행 버튼
        run_btn_col1, run_btn_col2 = st.columns([1, 2])
        with run_btn_col1:
            run_stage0 = st.button(
                "🔍 Step 1: 배합비 해석",
                key="t4_run_s0_recipe",
                disabled=not (st.session_state.api_key and recipe_text),
                use_container_width=True
            )
        
        if run_stage0 and recipe_text:
            with st.spinner("Stage 0: Claude가 배합비를 분석 중..."):
                prompt = prompt_stage0_recipe(recipe_text, process_text)
                parsed, raw = call_claude_api_json(
                    prompt, st.session_state.api_key,
                    st.session_state.claude_model,
                    system_msg="당신은 20년 경력의 식품 R&D 배합 전문가입니다.",
                    max_tokens=4000
                )
                if parsed:
                    st.session_state.current_recipe_parse = parsed
                    st.success("✅ 배합비 해석 완료")
                else:
                    st.error(f"JSON 파싱 실패\n{raw[:500]}")
        
        # Stage 0 결과 표시
        if st.session_state.current_recipe_parse:
            parsed = st.session_state.current_recipe_parse
            
            with st.container():
                st.markdown("#### 📋 배합비 해석 결과")
                
                # 정규화된 배합 표
                if 'normalized_recipe' in parsed:
                    recipe_df = pd.DataFrame(parsed['normalized_recipe'])
                    st.markdown("**정규화된 배합비**")
                    st.dataframe(recipe_df, use_container_width=True)
                
                # 공정
                if 'process' in parsed and parsed['process']:
                    st.markdown("**제조 공정**")
                    for p in parsed['process']:
                        st.markdown(f"- {p.get('step', '')}: {p.get('condition', '')}")
                
                # 경고/가정
                cc1, cc2 = st.columns(2)
                with cc1:
                    if parsed.get('warnings'):
                        st.markdown("**⚠️ 주의사항**")
                        for w in parsed['warnings']:
                            st.warning(w)
                with cc2:
                    if parsed.get('assumptions_made'):
                        st.markdown("**💭 가정 사항**")
                        for a in parsed['assumptions_made']:
                            st.info(a)
            
            # Stage 1 실행
            st.markdown("---")
            run_s1 = st.button(
                "🍑 Step 2: 맛 프로파일 추론",
                key="t4_run_s1_recipe",
                disabled=not st.session_state.api_key,
                use_container_width=True
            )
            
            if run_s1:
                with st.spinner("Stage 1: Claude가 맛을 상상 중..."):
                    prompt = prompt_stage1_flavor(parsed)
                    flavor, raw = call_claude_api_json(
                        prompt, st.session_state.api_key,
                        st.session_state.claude_model,
                        system_msg="당신은 20년 경력의 식품 관능 전문가입니다.",
                        max_tokens=4000
                    )
                    if flavor:
                        st.session_state.current_flavor_profile = flavor
                        st.success("✅ 맛 프로파일 추론 완료")
                    else:
                        st.error(f"파싱 실패: {raw[:500]}")
            
            # Stage 1 결과 표시
            if st.session_state.current_flavor_profile:
                flavor = st.session_state.current_flavor_profile
                
                with st.expander("🍑 추론된 맛 프로파일 보기 (Stage 1)",
                                expanded=True):
                    # 물리화학
                    if 'physical' in flavor:
                        phys = flavor['physical']
                        cc1, cc2, cc3 = st.columns(3)
                        cc1.metric("Brix", f"{phys.get('estimated_brix', 0):.1f}")
                        cc2.metric("pH", f"{phys.get('estimated_ph', 0):.1f}")
                        cc3.metric("산도",
                            f"{phys.get('estimated_acidity_pct', 0):.2f}%")
                    
                    # 맛
                    if 'taste' in flavor:
                        taste = flavor['taste']
                        st.markdown(f"**▸ 첫인상:** {taste.get('first_impression', '')}")
                        st.markdown(f"**▸ 중반:** {taste.get('mid_palate', '')}")
                        st.markdown(f"**▸ 끝맛:** {taste.get('finish', '')}")
                        
                        st.markdown("**관능 강도**")
                        intensities = {
                            '단맛': taste.get('sweetness', 0),
                            '산미': taste.get('acidity', 0),
                            '쓴맛': taste.get('bitterness', 0),
                            '감칠맛': taste.get('umami', 0),
                            '떫은맛': taste.get('astringency', 0)
                        }
                        int_df = pd.DataFrame({
                            '속성': list(intensities.keys()),
                            '강도(1-10)': list(intensities.values())
                        })
                        st.dataframe(int_df, use_container_width=True,
                                    hide_index=True)
                    
                    # 전반
                    if 'overall' in flavor:
                        ov = flavor['overall']
                        st.markdown(f"**▸ 밸런스:** {ov.get('balance', '')}")
                        st.markdown(
                            f"**▸ 강점:** {', '.join(ov.get('strengths', []))}")
                        st.markdown(
                            f"**▸ 약점:** {', '.join(ov.get('weaknesses', []))}")
                        st.markdown(f"**▸ 타겟 예상:** {ov.get('target_fit', '')}")
                
                # Stage 2 실행
                st.markdown("---")
                run_s2 = st.button(
                    f"👥 Step 3: {n_panels}명 패널 평가 실행",
                    key="t4_run_s2_recipe",
                    type="primary",
                    disabled=not st.session_state.api_key,
                    use_container_width=True
                )
                
                if run_s2:
                    # 패널 수에 비례해 max_tokens 계산 (1명당 약 400토큰)
                    dynamic_tokens = max(6000, min(16000, n_panels * 450))
                    spinner_msg = (
                        f"Stage 2: {n_panels}명 페르소나가 평가 중... "
                        f"(예상 {n_panels * 4}~{n_panels * 8}초)"
                    )
                    with st.spinner(spinner_msg):
                        prompt = prompt_stage2_panel_eval_recipe(
                            recipe_product_name, flavor, selected_personas
                        )
                        eval_result, raw = call_claude_api_json(
                            prompt, st.session_state.api_key,
                            st.session_state.claude_model,
                            system_msg="당신은 관능검사 시뮬레이션 엔진입니다.",
                            max_tokens=dynamic_tokens,
                            timeout=300
                        )
                        if eval_result and 'evaluations' in eval_result:
                            st.session_state.current_evaluations = {
                                'mode': 'recipe',
                                'product_name': recipe_product_name,
                                'evaluations': eval_result['evaluations'],
                                'recipe_parse': parsed,
                                'flavor_profile': flavor,
                                'timestamp': datetime.datetime.now().strftime('%H:%M'),
                                'n_panels': n_panels,
                                'personas_used': selected_personas,
                                'input_data': {
                                    'recipe': recipe_text,
                                    'process': process_text
                                }
                            }
                            st.success(
                                f"✅ {len(eval_result['evaluations'])}명 평가 완료"
                            )
                        else:
                            st.error(f"파싱 실패: {raw[:500]}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 💭 컨셉 모드
    # ═══════════════════════════════════════════════════════════════════════
    else:
        st.markdown("#### 💭 컨셉 정보 입력")
        
        cc1, cc2 = st.columns(2)
        with cc1:
            concept_name = st.text_input(
                "제품명", "피치 스파클링",
                key="t4_concept_name"
            )
            concept_target = st.text_input(
                "타겟 소비자",
                "20-30대 여성, 워킹우먼",
                key="t4_concept_target"
            )
            concept_price = st.number_input(
                "가격 (원)",
                min_value=100, max_value=100000, value=2500, step=100,
                key="t4_concept_price"
            )
        with cc2:
            concept_channel = st.selectbox(
                "유통 채널",
                ["편의점", "대형마트", "온라인", "전문매장", "카페/레스토랑"],
                key="t4_concept_channel"
            )
            concept_positioning = st.text_input(
                "포지셔닝",
                "프리미엄 건강 음료",
                key="t4_concept_positioning"
            )
        
        concept_selling_points = st.text_area(
            "주요 소구점",
            placeholder="예시:\n저칼로리 (100kcal 미만)\n천연 복숭아 15% 함유\n탄산 청량감\n편의점 단독 출시",
            height=100,
            key="t4_concept_sp"
        )
        
        # Stage 0 실행
        run_c0 = st.button(
            "🔍 Step 1: 컨셉 해석",
            key="t4_run_s0_concept",
            disabled=not (st.session_state.api_key and 
                         concept_name and concept_selling_points),
            use_container_width=True
        )
        
        if run_c0:
            with st.spinner("Stage 0: Claude가 컨셉을 분석 중..."):
                concept_data = {
                    'name': concept_name,
                    'target': concept_target,
                    'selling_points': concept_selling_points,
                    'price': concept_price,
                    'channel': concept_channel,
                    'positioning': concept_positioning
                }
                prompt = prompt_stage0_concept(concept_data)
                parsed, raw = call_claude_api_json(
                    prompt, st.session_state.api_key,
                    st.session_state.claude_model,
                    system_msg="당신은 식품 브랜드 마케팅 전문가입니다.",
                    max_tokens=3000
                )
                if parsed:
                    st.session_state.current_concept_parse = parsed
                    st.success("✅ 컨셉 해석 완료")
                else:
                    st.error(f"파싱 실패: {raw[:500]}")
        
        # Stage 0 결과
        if st.session_state.current_concept_parse:
            parsed_c = st.session_state.current_concept_parse
            
            with st.container():
                st.markdown("#### 📋 컨셉 해석 결과")
                
                st.markdown(f"**제품**: {parsed_c.get('product_name', '')}")
                st.markdown(f"**카테고리**: {parsed_c.get('category', '')}")
                st.markdown(f"**가격 티어**: {parsed_c.get('price_tier', '')}")
                st.markdown(
                    f"**포지셔닝**: *{parsed_c.get('positioning_statement', '')}*"
                )
                
                if parsed_c.get('value_propositions'):
                    st.markdown("**🎯 정제된 소구점**")
                    for vp in parsed_c['value_propositions']:
                        st.markdown(f"- {vp}")
                
                if parsed_c.get('target_analysis'):
                    ta = parsed_c['target_analysis']
                    st.markdown("**👥 타겟 분석**")
                    st.markdown(f"- **주 타겟**: {ta.get('primary', '')}")
                    if ta.get('secondary'):
                        st.markdown(f"- **부 타겟**: {ta['secondary']}")
                
                ccw1, ccw2 = st.columns(2)
                with ccw1:
                    if parsed_c.get('warnings'):
                        st.markdown("**⚠️ 주의사항**")
                        for w in parsed_c['warnings']:
                            st.warning(w)
                with ccw2:
                    if parsed_c.get('assumptions'):
                        st.markdown("**💭 가정 사항**")
                        for a in parsed_c['assumptions']:
                            st.info(a)
            
            # Stage 1 실행
            st.markdown("---")
            run_c1 = st.button(
                "🎨 Step 2: 인식 프로파일 추론",
                key="t4_run_s1_concept",
                disabled=not st.session_state.api_key,
                use_container_width=True
            )
            
            if run_c1:
                with st.spinner("Stage 1: 소비자 인식 프로파일 추론 중..."):
                    prompt = prompt_stage1_concept_perception(parsed_c)
                    perception, raw = call_claude_api_json(
                        prompt, st.session_state.api_key,
                        st.session_state.claude_model,
                        system_msg="당신은 10년차 소비재 마케팅 전문가입니다.",
                        max_tokens=3500
                    )
                    if perception:
                        st.session_state.current_concept_profile = perception
                        st.success("✅ 인식 프로파일 추론 완료")
                    else:
                        st.error(f"파싱 실패: {raw[:500]}")
            
            # Stage 1 결과
            if st.session_state.current_concept_profile:
                perc = st.session_state.current_concept_profile
                
                with st.expander("🎨 인식 프로파일 보기 (Stage 1)", expanded=True):
                    # 첫인상
                    if 'first_impression' in perc:
                        fi = perc['first_impression']
                        st.markdown("**👁️ 예상 첫인상**")
                        st.metric("매력도 (1-10)", f"{fi.get('appeal_score', 0)}")
                        if fi.get('expectation_points'):
                            st.markdown(
                                "**기대 포인트:** " + 
                                ", ".join(fi['expectation_points'])
                            )
                        if fi.get('confusion_points'):
                            st.markdown(
                                "**혼란 요소:** " + 
                                ", ".join(fi['confusion_points'])
                            )
                    
                    # 경쟁 맥락
                    if 'competitive_context' in perc:
                        cc_ctx = perc['competitive_context']
                        st.markdown("**🏁 경쟁 제품 연상**")
                        st.markdown(
                            f"연상 브랜드: {', '.join(cc_ctx.get('associated_brands', []))}"
                        )
                        st.markdown(
                            f"차별화 점수: {cc_ctx.get('differentiation_score', 0)}/10"
                        )
                        st.markdown(cc_ctx.get('differentiation_analysis', ''))
                    
                    # 가격
                    if 'price_perception' in perc:
                        pp = perc['price_perception']
                        st.markdown("**💰 가격 인식**")
                        st.markdown(
                            f"카테고리 평균 추정: {pp.get('category_avg_estimate', 0):,}원"
                        )
                        st.markdown(f"가격 적합도: {pp.get('price_fit_score', 0)}/10")
                        st.markdown(pp.get('value_alignment', ''))
                    
                    # 리스크
                    if 'risks' in perc:
                        r = perc['risks']
                        st.markdown("**⚠️ 예상 리스크**")
                        st.markdown(f"전반 위험도: **{r.get('overall_risk_level', '중')}**")
                        if r.get('credibility_concerns'):
                            st.markdown(
                                "신뢰도 우려: " + 
                                ", ".join(r['credibility_concerns'])
                            )
                
                # Stage 2 실행
                st.markdown("---")
                run_c2 = st.button(
                    f"👥 Step 3: {n_panels}명 패널 컨셉 평가",
                    key="t4_run_s2_concept",
                    type="primary",
                    disabled=not st.session_state.api_key,
                    use_container_width=True
                )
                
                if run_c2:
                    dynamic_tokens = max(6000, min(16000, n_panels * 450))
                    spinner_msg = (
                        f"Stage 2: {n_panels}명이 컨셉을 평가 중... "
                        f"(예상 {n_panels * 4}~{n_panels * 8}초)"
                    )
                    with st.spinner(spinner_msg):
                        prompt = prompt_stage2_panel_eval_concept(
                            concept_name, perc, selected_personas
                        )
                        eval_result, raw = call_claude_api_json(
                            prompt, st.session_state.api_key,
                            st.session_state.claude_model,
                            system_msg="당신은 관능검사·마케팅 리서치 시뮬레이션 엔진입니다.",
                            max_tokens=dynamic_tokens,
                            timeout=300
                        )
                        if eval_result and 'evaluations' in eval_result:
                            st.session_state.current_evaluations = {
                                'mode': 'concept',
                                'product_name': concept_name,
                                'evaluations': eval_result['evaluations'],
                                'concept_parse': parsed_c,
                                'concept_profile': perc,
                                'timestamp': datetime.datetime.now().strftime('%H:%M'),
                                'n_panels': n_panels,
                                'personas_used': selected_personas,
                                'input_data': {
                                    'name': concept_name,
                                    'target': concept_target,
                                    'selling_points': concept_selling_points,
                                    'price': concept_price,
                                    'channel': concept_channel,
                                    'positioning': concept_positioning
                                }
                            }
                            st.success(
                                f"✅ {len(eval_result['evaluations'])}명 컨셉 평가 완료"
                            )
                        else:
                            st.error(f"파싱 실패: {raw[:500]}")
    # ═══════════════════════════════════════════════════════════════════════
    # 공통 결과 분석 & 시각화 (배합비/컨셉 모두)
    # ═══════════════════════════════════════════════════════════════════════
    if st.session_state.current_evaluations:
        eval_data = st.session_state.current_evaluations
        evaluations = eval_data['evaluations']
        mode = eval_data['mode']
        
        st.markdown("---")
        st.markdown(f"## 📊 AI 평가 결과 — {eval_data['product_name']}")
        
        # 평가 항목 결정
        if mode == 'recipe':
            attr_list = ['전반적만족도', '구입의향', '색상', '전반적맛',
                        '풍미', '단맛', '전반적식감', '끝맛여운']
            pass_criteria = ['전반적맛', '구입의향', '전반적만족도']
        else:
            attr_list = ['컨셉매력도', '구입의향', '타겟적합성', '차별화인식',
                        '신뢰도', '가격수용도', '건강이미지', '프리미엄인식']
            pass_criteria = ['컨셉매력도', '구입의향', '타겟적합성']
        
        # 점수 DataFrame 구성
        rows = []
        for e in evaluations:
            scores = e.get('scores', {})
            row = {
                'ID': e.get('panel_id', ''),
                '이름': e.get('panel_name', '')
            }
            for a in attr_list:
                row[a] = scores.get(a, None)
            rows.append(row)
        ai_df = pd.DataFrame(rows)
        
        # 평균 계산
        mean_ai = {}
        for a in attr_list:
            col = pd.to_numeric(ai_df[a], errors='coerce').dropna()
            if len(col) > 0:
                mean_ai[a] = col.mean()
        
        # 합격 판정
        passed_ai = sum(1 for c in pass_criteria 
                       if c in mean_ai and mean_ai[c] >= 5.0)
        total_crit = len(pass_criteria)
        
        if passed_ai == total_crit:
            ai_pass_status = "🟢 완전 합격 (3기준 모두 통과)"
            ai_badge = "pass-badge-full"
        elif passed_ai == 2:
            ai_pass_status = "🟡 조건부 합격 (2기준 통과)"
            ai_badge = "pass-badge-conditional"
        else:
            ai_pass_status = f"🔴 불합격 ({passed_ai}/{total_crit})"
            ai_badge = "pass-badge-fail"
        
        # 판정 배지 + 재평가 버튼
        cc_pass1, cc_pass2 = st.columns([3, 1])
        with cc_pass1:
            st.markdown(
                f'<div style="margin: 15px 0;">'
                f'<span class="{ai_badge}" style="font-size: 18px;">'
                f'{ai_pass_status}</span></div>',
                unsafe_allow_html=True
            )
        with cc_pass2:
            if st.button("🔁 재평가", key="t4_reeval",
                        help="같은 입력으로 다시 시뮬레이션",
                        use_container_width=True):
                # Stage 2만 다시 실행
                # 저장된 페르소나 우선 사용, 없으면 기본 20명
                personas_for_retry = eval_data.get('personas_used', 
                                                    select_personas(20))
                n_retry = len(personas_for_retry)
                dynamic_tokens = max(6000, min(16000, n_retry * 450))
                
                with st.spinner(f"다시 평가 중... ({n_retry}명, 최대 5분)"):
                    if mode == 'recipe':
                        prompt = prompt_stage2_panel_eval_recipe(
                            eval_data['product_name'],
                            eval_data['flavor_profile'], personas_for_retry
                        )
                    else:
                        prompt = prompt_stage2_panel_eval_concept(
                            eval_data['product_name'],
                            eval_data['concept_profile'], personas_for_retry
                        )
                    new_eval, raw = call_claude_api_json(
                        prompt, st.session_state.api_key,
                        st.session_state.claude_model,
                        max_tokens=dynamic_tokens,
                        timeout=300
                    )
                    if new_eval and 'evaluations' in new_eval:
                        st.session_state.current_evaluations['evaluations'] = \
                            new_eval['evaluations']
                        st.session_state.current_evaluations['timestamp'] = \
                            datetime.datetime.now().strftime('%H:%M')
                        st.rerun()
                    else:
                        st.error(f"❌ 재평가 실패: {raw[:400]}")
        
        # 합격 기준 상세
        st.markdown("#### 🎯 합격 기준별 점수")
        cc_k1, cc_k2, cc_k3 = st.columns(3)
        for i, crit in enumerate(pass_criteria):
            col = [cc_k1, cc_k2, cc_k3][i]
            with col:
                if crit in mean_ai:
                    score = mean_ai[crit]
                    status = "🟢 통과" if score >= 5.0 else "🔴 미달"
                    st.metric(crit, f"{score:.2f}", status)
        
        # 탭 구성: 평균/개별코멘트/점수분포/세션비교
        ai_tab1, ai_tab2, ai_tab3, ai_tab4 = st.tabs([
            "📊 항목별 평균", "💬 개별 코멘트",
            "🔥 점수 분포", "💾 세션 비교"
        ])
        
        with ai_tab1:
            # 평균 막대그래프 + 레이더
            v1, v2 = st.columns(2)
            with v1:
                # 막대그래프
                attrs = list(mean_ai.keys())
                values = list(mean_ai.values())
                colors_b = []
                for attr, val in zip(attrs, values):
                    if attr in pass_criteria:
                        colors_b.append('#10b981' if val >= 5.0 else '#ef4444')
                    else:
                        colors_b.append('#3b82f6' if val >= 5.0 else '#f59e0b')
                
                fig_ai_bar = go.Figure()
                fig_ai_bar.add_trace(go.Bar(
                    x=attrs, y=values,
                    marker=dict(color=colors_b,
                               line=dict(color='#94a3b8', width=1)),
                    text=[f"{v:.2f}" for v in values],
                    textposition='outside'
                ))
                fig_ai_bar.add_hline(y=5.0, line_dash="dash",
                    line_color="#3b82f6",
                    annotation_text="합격선 5.0")
                fig_ai_bar.update_layout(
                    title="8항목 평균 (진한 색=합격 기준 항목)",
                    yaxis=dict(range=[0, 7.5]),
                    xaxis=dict(tickangle=-35)
                )
                apply_plotly_theme(fig_ai_bar)
                st.plotly_chart(fig_ai_bar, use_container_width=True)
            
            with v2:
                # 레이더
                fig_ai_radar = go.Figure()
                fig_ai_radar.add_trace(go.Scatterpolar(
                    r=values + [values[0]],
                    theta=attrs + [attrs[0]],
                    fill='toself', name=eval_data['product_name'],
                    line=dict(color='#3b82f6', width=2),
                    fillcolor='rgba(59, 130, 246, 0.25)'
                ))
                fig_ai_radar.add_trace(go.Scatterpolar(
                    r=[5.0] * (len(attrs) + 1),
                    theta=attrs + [attrs[0]],
                    name='합격선 5.0',
                    line=dict(color='#f59e0b', dash='dash', width=1)
                ))
                fig_ai_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 7],
                                       gridcolor='rgba(30, 64, 175, 0.3)'),
                        bgcolor='rgba(248, 250, 252, 0.5)'
                    ),
                    title="Radar Profile"
                )
                apply_plotly_theme(fig_ai_radar)
                st.plotly_chart(fig_ai_radar, use_container_width=True)
            
            st.markdown("#### 📋 평균 점수표")
            mean_table = pd.DataFrame([
                {'항목': a, '평균': v,
                 '판정': '✓' if v >= 5.0 else '✗'}
                for a, v in mean_ai.items()
            ])
            st.dataframe(mean_table.style.format({'평균': '{:.2f}'}),
                        use_container_width=True)
        
        with ai_tab2:
            # 개별 코멘트
            st.caption("각 가상 패널의 평가 점수와 코멘트, 추론 근거")
            
            for e in evaluations:
                pid = e.get('panel_id', '')
                pname = e.get('panel_name', '')
                comment = e.get('comment', '')
                reasoning = e.get('reasoning', '')
                scores = e.get('scores', {})
                
                # 이 패널의 평균
                p_avg = np.mean([scores.get(a, 0) for a in attr_list 
                                if isinstance(scores.get(a), (int, float))])
                
                # 색상 결정
                if p_avg >= 5.5:
                    badge_color = "#10b981"
                elif p_avg >= 4.5:
                    badge_color = "#3b82f6"
                elif p_avg >= 3.5:
                    badge_color = "#f59e0b"
                else:
                    badge_color = "#ef4444"
                
                with st.expander(
                    f"{pid} · {pname} — 평균 {p_avg:.1f}점",
                    expanded=False
                ):
                    st.markdown(
                        f"**💬 코멘트:** {comment}"
                    )
                    st.caption(f"📐 추론: {reasoning}")
                    
                    # 점수 표시
                    score_cols = st.columns(len(attr_list))
                    for i, a in enumerate(attr_list):
                        with score_cols[i]:
                            v = scores.get(a, 0)
                            if isinstance(v, (int, float)):
                                st.metric(a, f"{v}")
        
        with ai_tab3:
            # 점수 분포 히트맵
            st.caption(f"{len(evaluations)}명 × 8항목 점수 히트맵")
            
            score_matrix = []
            panel_labels = []
            for e in evaluations:
                scores = e.get('scores', {})
                row = [scores.get(a, None) for a in attr_list]
                score_matrix.append(row)
                panel_labels.append(f"{e.get('panel_id', '')} {e.get('panel_name', '').split()[0]}")
            
            score_np = np.array(score_matrix, dtype=float)
            
            fig_heatmap = go.Figure(data=go.Heatmap(
                z=score_np,
                x=attr_list,
                y=panel_labels,
                colorscale=[
                    [0.0, '#7f1d1d'],
                    [0.3, '#ef4444'],
                    [0.5, '#f59e0b'],
                    [0.7, '#3b82f6'],
                    [1.0, '#10b981']
                ],
                zmin=1, zmax=7,
                text=score_np,
                texttemplate="%{text:.0f}",
                textfont={"size": 10},
                colorbar=dict(title="점수", tickfont=dict(color='#e2e8f0'))
            ))
            fig_heatmap.update_layout(
                title=f"{eval_data['product_name']} — 패널별 점수 히트맵",
                height=600,
                xaxis=dict(tickangle=-35)
            )
            apply_plotly_theme(fig_heatmap)
            st.plotly_chart(fig_heatmap, use_container_width=True)
            
            # 분포 통계
            st.markdown("#### 📈 점수 분포 통계")
            dist_rows = []
            for a in attr_list:
                col = pd.to_numeric(ai_df[a], errors='coerce').dropna()
                if len(col) > 0:
                    dist_rows.append({
                        '항목': a,
                        '평균': col.mean(),
                        '표준편차': col.std(),
                        '최소': col.min(),
                        '최대': col.max(),
                        '중앙값': col.median()
                    })
            dist_df = pd.DataFrame(dist_rows)
            st.dataframe(dist_df.style.format({
                '평균': '{:.2f}', '표준편차': '{:.2f}',
                '최소': '{:.0f}', '최대': '{:.0f}', '중앙값': '{:.1f}'
            }), use_container_width=True)
        
        with ai_tab4:
            # 세션 비교
            st.caption("현재 및 과거 평가를 선택해 비교할 수 있습니다 (세션 중 최대 5개 보관)")
            
            # 현재 결과를 세션에 저장하는 버튼
            if st.button("💾 현재 평가를 세션에 저장",
                        key="t4_save_session"):
                # 세션 저장 데이터 생성
                session_entry = {
                    'id': f"AI_{datetime.datetime.now().strftime('%H%M%S')}",
                    'timestamp': eval_data['timestamp'],
                    'mode': mode,
                    'product_name': eval_data['product_name'],
                    'mean_scores': mean_ai,
                    'pass_status': ai_pass_status,
                    'evaluations': evaluations,
                    'input_data': eval_data.get('input_data', {})
                }
                
                # FIFO 5개 유지
                st.session_state.ai_sessions.insert(0, session_entry)
                if len(st.session_state.ai_sessions) > 5:
                    st.session_state.ai_sessions = st.session_state.ai_sessions[:5]
                
                st.success(f"✅ 세션 저장됨 (현재 {len(st.session_state.ai_sessions)}/5)")
                st.rerun()
            
            if not st.session_state.ai_sessions:
                st.info("저장된 세션이 없습니다. 평가 후 '세션에 저장'을 눌러주세요.")
            else:
                # 세션 선택
                session_options = []
                for s in st.session_state.ai_sessions:
                    mode_icon = "🧪" if s['mode'] == 'recipe' else "💭"
                    session_options.append(
                        f"{mode_icon} {s['id']} · {s['product_name']} "
                        f"({s['timestamp']})"
                    )
                
                selected_sessions = st.multiselect(
                    "비교할 세션 선택 (2-5개)",
                    options=list(range(len(session_options))),
                    format_func=lambda i: session_options[i],
                    default=list(range(min(2, len(session_options)))),
                    key="t4_sess_select"
                )
                
                if len(selected_sessions) >= 2:
                    # 비교 레이더차트
                    fig_compare = go.Figure()
                    for i, idx in enumerate(selected_sessions):
                        s = st.session_state.ai_sessions[idx]
                        # 공통 속성만 (첫 세션 기준)
                        common_attrs = list(s['mean_scores'].keys())
                        values = [s['mean_scores'].get(a, 0) for a in common_attrs]
                        color = PLOTLY_THEME['colorway'][i % len(PLOTLY_THEME['colorway'])]
                        fig_compare.add_trace(go.Scatterpolar(
                            r=values + [values[0]],
                            theta=common_attrs + [common_attrs[0]],
                            fill='toself', opacity=0.4,
                            name=f"{s['product_name']} ({s['timestamp']})",
                            line=dict(color=color)
                        ))
                    
                    fig_compare.update_layout(
                        polar=dict(
                            radialaxis=dict(visible=True, range=[0, 7],
                                           gridcolor='rgba(30, 64, 175, 0.3)'),
                            bgcolor='rgba(248, 250, 252, 0.5)'
                        ),
                        title="세션 간 비교 (Radar Overlay)",
                        height=550
                    )
                    apply_plotly_theme(fig_compare)
                    st.plotly_chart(fig_compare, use_container_width=True)
                    
                    # 비교 표
                    st.markdown("#### 📊 요약 비교표")
                    compare_rows = []
                    all_attrs = set()
                    for idx in selected_sessions:
                        all_attrs.update(st.session_state.ai_sessions[idx]['mean_scores'].keys())
                    
                    for a in sorted(all_attrs):
                        row = {'항목': a}
                        for idx in selected_sessions:
                            s = st.session_state.ai_sessions[idx]
                            val = s['mean_scores'].get(a, None)
                            row[f"{s['product_name'][:12]}"] = (f"{val:.2f}" 
                                                                if val else "-")
                        compare_rows.append(row)
                    st.dataframe(pd.DataFrame(compare_rows), use_container_width=True)
                else:
                    st.info("비교하려면 세션 2개 이상을 선택하세요.")
            
            # 핸드아웃 다운로드
            st.markdown("---")
            st.markdown("#### 📚 수업 핸드아웃 다운로드")
            
            handout_data = {
                'mode': mode,
                'product_name': eval_data['product_name'],
                'mean_scores': mean_ai,
                'pass_status': ai_pass_status,
                'evaluations': evaluations,
                'input_data': eval_data.get('input_data', {})
            }
            
            # 강사 노트 생성 (모드별)
            if mode == 'recipe':
                teaching_notes = [
                    "Stage 0 배합비 해석에서 AI가 '가정'한 부분을 수강생과 검토하세요.",
                    "실제 시음 결과와 AI 예측이 다를 수 있는 이유를 토론하세요.",
                    "합격 기준 5.0이 어떻게 설정되었는지, 업계 실정과 비교하세요.",
                    "가장 낮은 점수를 준 페르소나의 프로필을 분석하게 하세요.",
                    "원료 한 가지를 바꾸면 결과가 어떻게 달라질지 예측해보게 하세요.",
                ]
            else:
                teaching_notes = [
                    "컨셉 평가가 실제 제품 경험과 다른 이유를 설명하세요.",
                    "타겟 적합성 점수가 낮다면 왜 그런지 페르소나별로 분석하세요.",
                    "가격 수용도와 프리미엄 인식의 관계를 토론하세요.",
                    "컨셉 모드에서 '신뢰도' 점수가 낮다면 설명의 어떤 점을 보완해야 할지 논하세요.",
                    "이 컨셉을 리뉴얼한다면 어떤 소구점을 강화/제거할지 워크숍 하세요.",
                ]
            
            handout_html = generate_ai_handout_html(handout_data, teaching_notes)
            
            hc1, hc2 = st.columns(2)
            with hc1:
                st.download_button(
                    "📥 핸드아웃 HTML 다운로드",
                    data=handout_html.encode('utf-8'),
                    file_name=f"핸드아웃_{eval_data['product_name']}_{datetime.date.today()}.html",
                    mime="text/html",
                    key="t4_handout_dl",
                    use_container_width=True
                )
            with hc2:
                # 평가 CSV 다운로드
                df_to_csv_download(
                    ai_df,
                    f"AI평가_{eval_data['product_name']}_{datetime.date.today()}.csv",
                    "📥 평가 데이터 CSV",
                    key="t4_eval_csv"
                )
        
        # 면책 문구 (하단 상시)
        st.markdown(
            '<div class="disclaimer" style="background: #fef2f2; '
            'border: 1px solid #ef4444; padding: 12px; border-radius: 6px; '
            'margin: 20px 0; font-size: 12px; color: #991b1b;">'
            '<strong>⚠️ 면책:</strong> 본 AI 시뮬레이션은 교육 및 초기 탐색 목적이며, '
            '실제 소비자 조사를 대체할 수 없습니다. 제품 출시 결정의 유일한 근거로 사용하지 마세요.'
            '</div>',
            unsafe_allow_html=True
        )
# ============================================================================
# TAB 5: 패널 신뢰도 (기존 유지, 테마 통합)
# ============================================================================

with tabs[4]:
    st.header("패널 신뢰도 평가")
    st.info("반복측정으로 패널 일관성과 식별력을 평가합니다.")
    
    form_manager_ui("t5", "reliability")
    
    st.divider()
    st.subheader("📤 조사지 업로드 & 분석")
    up_rel = st.file_uploader("작성된 조사지 CSV", type="csv", key="t5_up")
    
    if up_rel:
        dfrel = pd.read_csv(up_rel)
        if '점수' in dfrel.columns:
            dfrel = dfrel[pd.to_numeric(dfrel['점수'], errors='coerce').notna()].copy()
            dfrel['점수'] = dfrel['점수'].astype(float)
        
        if len(dfrel) == 0:
            st.error("❌ 점수가 입력되지 않은 빈 조사지입니다.")
        else:
            st.success(f"✅ {len(dfrel)}행 로드")
            st.dataframe(dfrel.head(), use_container_width=True)
            
            required = ['패널', '시료', '반복', '점수']
            if not all(c in dfrel.columns for c in required):
                st.error(f"필수 컬럼 누락: {required}")
            else:
                if st.button("🚀 패널 신뢰도 분석", type="primary", key="t5_run"):
                    try:
                        # 패널별 식별력
                        discrim_rows = []
                        for panel in sorted(dfrel['패널'].unique()):
                            pd_panel = dfrel[dfrel['패널']==panel]
                            agg = pd_panel.groupby('시료')['점수'].mean().reset_index()
                            groups = [pd_panel[pd_panel['시료']==s]['점수'].values 
                                     for s in agg['시료']]
                            if len(groups) >= 2:
                                f, p = f_oneway(*groups)
                                discrim_rows.append({
                                    '패널': panel, 'F': f, 'p-value': p,
                                    '판정': '우수' if p<0.05 else '보통'
                                })
                        discrim_df = pd.DataFrame(discrim_rows)
                        
                        # 패널별 CV
                        cv_rows = []
                        for panel in sorted(dfrel['패널'].unique()):
                            cvs = []
                            for s in dfrel['시료'].unique():
                                scores = dfrel[(dfrel['패널']==panel)&(dfrel['시료']==s)]['점수']
                                if scores.mean() > 0 and len(scores) > 1:
                                    cvs.append(scores.std()/scores.mean()*100)
                            if cvs:
                                avg_cv = np.mean(cvs)
                                cv_rows.append({
                                    '패널': panel,
                                    '평균 CV(%)': avg_cv,
                                    '판정': ('매우 일관' if avg_cv < 10 
                                           else '일관' if avg_cv < 20 
                                           else '편차 큼')
                                })
                        cv_df = pd.DataFrame(cv_rows)
                        
                        # ICC
                        try:
                            avg_by_panel_sample = dfrel.groupby(['패널','시료'])['점수'].mean().reset_index()
                            wide = avg_by_panel_sample.pivot(index='시료', columns='패널', values='점수')
                            
                            n_samples = wide.shape[0]
                            k_panels = wide.shape[1]
                            grand_mean = wide.values.mean()
                            msb = n_samples * wide.mean(axis=0).var(ddof=1)
                            msw = wide.var(axis=1, ddof=1).mean()
                            
                            if msw > 0 and (msb + (k_panels - 1) * msw) > 0:
                                icc = (msb - msw) / (msb + (k_panels - 1) * msw)
                            else:
                                icc = 0
                        except Exception:
                            icc = 0
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("ICC", f"{icc:.3f}",
                            "우수" if icc >= 0.75 
                            else "양호" if icc >= 0.5 else "낮음")
                        c2.metric("우수 패널",
                            f"{(discrim_df['p-value']<0.05).sum()}/{len(discrim_df)}")
                        c3.metric("평균 CV", f"{cv_df['평균 CV(%)'].mean():.1f}%")
                        
                        v1, v2 = st.columns(2)
                        with v1:
                            st.subheader("식별력 (F-value)")
                            disp = discrim_df.copy()
                            disp['색'] = disp['p-value'].apply(
                                lambda x: '#10b981' if x < 0.05 else '#ef4444')
                            fig = px.bar(disp, x='패널', y='F',
                                color='판정', hover_data=['p-value'])
                            apply_plotly_theme(fig)
                            st.plotly_chart(fig, use_container_width=True)
                            st.dataframe(discrim_df.style.format({
                                'F':'{:.3f}','p-value':'{:.4f}'}),
                                use_container_width=True)
                        with v2:
                            st.subheader("일관성 (CV%)")
                            fig2 = px.bar(cv_df, x='패널', y='평균 CV(%)',
                                color='판정', title="CV% (낮을수록 일관)")
                            fig2.add_hline(y=10, line_dash="dash", line_color="#10b981")
                            fig2.add_hline(y=20, line_dash="dash", line_color="#f59e0b")
                            apply_plotly_theme(fig2)
                            st.plotly_chart(fig2, use_container_width=True)
                            st.dataframe(cv_df.style.format({'평균 CV(%)':'{:.2f}'}),
                                use_container_width=True)
                        
                        st.session_state.results['reliability'] = {
                            'discrim_df': discrim_df, 'cv_df': cv_df, 'icc': icc
                        }
                        
                        if st.session_state.api_key:
                            with st.spinner("Claude 해석 중..."):
                                prompt = f"""패널 신뢰도 분석:

[ICC] {icc:.3f}
[우수 패널] {(discrim_df['p-value']<0.05).sum()}/{len(discrim_df)}
[평균 CV] {cv_df['평균 CV(%)'].mean():.1f}%

[패널별 식별력]
{discrim_df.to_string()}

[패널별 일관성]
{cv_df.to_string()}

패널 품질과 개선방안을 식품개발자 관점에서 해석해주세요."""
                                interp = call_claude_api(prompt,
                                    st.session_state.api_key,
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
# TAB 6: 블라인드 코드 생성기 (기존 유지)
# ============================================================================

with tabs[5]:
    st.header("블라인드 코드 생성기")
    st.info("난수 3자리 블라인드 코드 + 패널/시료 매핑")
    
    col1, col2, col3 = st.columns(3)
    n_panels_b = col1.number_input("패널 수", 1, 100, 10, key="t6_np")
    samples_str_b = col2.text_input("시료명", "A,B,C,D", key="t6_s")
    seed_b = col3.number_input("난수 시드", value=42, key="t6_seed")
    
    samples_b = [s.strip() for s in samples_str_b.split(",") if s.strip()]
    
    if st.button("🎲 코드 생성", type="primary", key="t6_gen") and samples_b:
        random.seed(int(seed_b))
        rows = []
        for p in range(n_panels_b):
            for s in samples_b:
                rows.append({
                    '패널': f'P{p+1:02d}',
                    '시료': s,
                    '블라인드코드': random.randint(100, 999)
                })
        code_df = pd.DataFrame(rows)
        
        st.dataframe(code_df, use_container_width=True)
        df_to_csv_download(code_df, f"블라인드코드_{datetime.date.today()}.csv",
            "📥 코드 매핑 CSV 다운로드", key="t6_dl")
        
        st.session_state.results['blind_codes'] = {'code_df': code_df}


# ============================================================================
# TAB 7: 통합 리포트
# ============================================================================

with tabs[6]:
    st.header("📑 통합 리포트 생성")
    st.info("분석한 결과들을 하나의 HTML 리포트로 생성합니다.")
    
    if not st.session_state.results:
        st.warning("⚠️ 먼저 분석을 실행하세요.")
    else:
        project = st.text_input("프로젝트명", "2026 신제품 개발 — 복숭아 RTD",
            key="t7_pn")
        author = st.text_input("작성자", "류지성 (Sweet Lab)", key="t7_au")
        
        available = []
        if 'anova' in st.session_state.results: available.append("ANOVA")
        if 'discrimination' in st.session_state.results: available.append("차이식별")
        if 'friedman' in st.session_state.results: available.append("순위법")
        if 'scaling' in st.session_state.results: available.append("평점법")
        if 'reliability' in st.session_state.results: available.append("패널 신뢰도")
        if 'blind_codes' in st.session_state.results: available.append("블라인드 코드")
        
        st.markdown("**포함할 섹션**")
        sel = st.multiselect("", available, default=available, key="t7_sel")
        
        section_map = {
            "ANOVA": "anova", "차이식별": "discrimination",
            "순위법": "friedman", "평점법": "scaling",
            "패널 신뢰도": "reliability", "블라인드 코드": "blind_codes"
        }
        selected_keys = [section_map[s] for s in sel]
        
        st.markdown("#### 👁️ 분석 결과 미리보기")
        for s in sel:
            with st.expander(f"📊 {s}"):
                k = section_map[s]
                r = st.session_state.results[k]
                if k == 'anova':
                    st.markdown(f"**모델**: {r['model_type']}")
                    st.markdown(f"**척도**: {r.get('scale', 9)}점")
                    st.dataframe(r['anova_table'])
                elif k == 'discrimination':
                    st.markdown(f"**검사**: {r['test_type']}")
                    st.markdown(
                        f"**결과**: 정답자 {r['correct']}/{r['n']}명, p={r['p_value']:.4f}"
                    )
                elif k == 'friedman':
                    st.markdown(
                        f"**χ²**: {r['f_stat']:.3f}, p={r['p_value']:.4f}, df={r.get('df', 'N/A')}"
                    )
                    st.dataframe(r['rank_sum'])
                elif k == 'scaling':
                    st.markdown(f"**제품**: {r.get('product_name', 'N/A')}")
                    st.markdown(f"**합격 판정**: {r.get('pass_status', 'N/A')}")
                    if 'stats_df' in r:
                        st.dataframe(r['stats_df'])
                elif k == 'reliability':
                    st.markdown(f"**ICC**: {r['icc']:.3f}")
                elif k == 'blind_codes':
                    st.dataframe(r['code_df'].head(10))
        
        st.divider()
        if st.button("📄 통합 HTML 리포트 생성", type="primary", key="t7_gen"):
            try:
                html = generate_html_report(project, author, selected_keys,
                    st.session_state.results, st.session_state.interpretations)
                st.success("✅ 리포트 생성 완료")
                st.download_button("📥 HTML 리포트 다운로드",
                    data=html.encode('utf-8'),
                    file_name=f"{project}_리포트_{datetime.date.today()}.html",
                    mime="text/html", key="t7_dl")
                with st.expander("👁️ 리포트 미리보기 (HTML)"):
                    st.components.v1.html(html, height=800, scrolling=True)
            except Exception as e:
                st.error(f"❌ 리포트 생성 오류: {e}")
                import traceback
                with st.expander("오류 상세"):
                    st.code(traceback.format_exc())


# ============================================================================
# Footer
# ============================================================================

st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #64748b; font-size: 12px; '
    'padding: 20px;">'
    'Sweet Lab · Natural Lab R&D<br>'
    '식품 R&D 관능분석 통합 솔루션 v3.0<br>'
    'Powered by Claude AI · Streamlit · Python'
    '</div>',
    unsafe_allow_html=True
)
