import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from collections import Counter
import time
import json
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="AI NPD SUITE - 트렌드 분석", layout="wide")

# ── 패키지 파싱 유틸 ─────────────────────────────────
def parse_package(title, price):
    """
    제목에서 용량·개수 파싱 → 개당/100ml당 가격 계산
    카테고리 자동 분류: RTD음료 / 농축·분말 / 건강기능 / 대용량 / 기타
    """
    t = title.lower().replace(" ", "")
    unit_price = price
    per_100ml = None
    ml = None
    count = 1

    # ── 개수 파싱 (24개입, 30캔, 6팩 등)
    m_count = re.search(r'(\d+)\s*(개입?|캔|병|팩|입|box|박스|포)', t)
    if m_count:
        n = int(m_count.group(1))
        if 1 < n <= 200:          # 비현실적 숫자 제외
            count = n

    # ── 용량 파싱 (500ml, 1.5L, 355ml 등)
    m_ml = re.search(r'(\d+\.?\d*)\s*(ml|l\b)', t)
    if m_ml:
        val = float(m_ml.group(1))
        unit_str = m_ml.group(2)
        ml = val * 1000 if unit_str == 'l' else val
        if ml > 5000:             # 5L 초과 비현실적 용량 제외
            ml = None

    # ── 개당 가격 계산
    if price > 0 and count > 0:
        unit_price = round(price / count)

    # ── 100ml당 가격 계산
    if unit_price > 0 and ml and ml >= 50:
        per_100ml = round(unit_price / ml * 100)
        # 이상값 필터: 100ml당 50원~3,000원 범위만 유효 RTD로 인정
        if per_100ml < 30 or per_100ml > 600:  # 정상 RTD 범위: 30~600원/100ml
            per_100ml = None

    # ── 카테고리 자동 분류
    농축분말_kw = ['농축','분말','파우더','원액','스틱','스틱형','엑기스','엑스트랙']
    건강기능_kw = ['앰플','젤리','정','캡슐','환','타블렛','tablet','소프트젤','필름']
    대용량_kw   = ['말통','말박스','업소용','식당용']

    if any(k in t for k in 농축분말_kw):
        category = "농축·분말"
    elif any(k in t for k in 건강기능_kw):
        category = "건강기능식품"
    elif any(k in t for k in 대용량_kw) or (ml and ml > 2000):
        category = "대용량"
    elif ml and 50 <= ml <= 2000:
        category = "RTD음료"
    else:
        category = "기타"

    return {
        "개수": count,
        "용량(ml)": ml,
        "개당가격": unit_price,
        "100ml당가격": per_100ml,
        "상품유형": category,
    }


# ── Gemini 키워드 추천 ───────────────────────────────
def get_gemini_keywords(api_key, categories, trends, targets, season):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-pro:generateContent?key={api_key}"
    condition_text = f"""
- 음료 카테고리: {', '.join(categories) if categories else '전체'}
- 트렌드 방향: {', '.join(trends) if trends else '전체'}
- 타겟 소비자: {', '.join(targets) if targets else '전체'}
- 시즌: {season}"""
    prompt = f"""당신은 한국 음료 시장 트렌드 전문가입니다.
아래 조건에 맞는 네이버 블로그·쇼핑 검색에 적합한 한국어 키워드 10개를 추천해주세요.
[조건]{condition_text}
결과는 반드시 JSON 배열 형식으로만 응답하세요. 설명 없이 배열만.
예시: ["저당음료", "제로탄산", "기능성음료"]"""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.7}
    }
    try:
        res = requests.post(url, json=payload, timeout=30)
        data = res.json()
        if "candidates" not in data:
            st.error(f"Gemini 오류: {data}")
            return []
        parts = data["candidates"][0].get("content", {}).get("parts", [])
        if not parts:
            st.error("Gemini 응답 없음 (토큰 부족)")
            return []
        text = re.sub(r"```json|```", "", parts[0]["text"]).strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Gemini 오류: {e}")
        return []


# ── Claude 분석 ──────────────────────────────────────
def analyze_with_claude(api_key, blog_df, shop_df):
    blog_sample = blog_df.head(50).to_csv(index=False) if not blog_df.empty else "없음"
    shop_sample = shop_df.head(50).to_csv(index=False) if not shop_df.empty else "없음"

    prompt = f"""당신은 한국 음료 식품 R&D 전문가입니다.
아래 네이버 블로그·쇼핑 데이터를 분석하고 반드시 아래 JSON 형식으로만 응답하세요.
설명·마크다운 없이 JSON만 출력하세요.

{{
  "monthly_trend": {{
    "summary": "월별 트렌드 2~3줄 요약",
    "peak_month": "가장 활발한 월",
    "insight": "트렌드 해석 1줄"
  }},
  "flavor_ranking": [
    {{"rank": 1, "flavor": "플레이버명", "count": 숫자, "ratio": "퍼센트%", "desc": "특징 1줄"}},
    {{"rank": 2, "flavor": "...", "count": 숫자, "ratio": "...", "desc": "..."}}
  ],
  "concept_tags": [
    {{"concept": "컨셉명", "count": 숫자, "trend": "상승/하락/유지"}}
  ],
  "hit_products": [
    {{"rank": 1, "name": "상품명", "brand": "브랜드", "price": 숫자, "reason": "히트 요인 1줄"}},
    {{"rank": 2, "name": "...", "brand": "...", "price": 숫자, "reason": "..."}}
  ],
  "consumer_needs": ["니즈1", "니즈2", "니즈3"],
  "npd_ideas": [
    {{"idea": "신제품 컨셉명", "flavor": "플레이버", "concept": "컨셉", "reason": "근거 1줄", "price_range": "가격대"}},
    {{"idea": "...", "flavor": "...", "concept": "...", "reason": "...", "price_range": "..."}},
    {{"idea": "...", "flavor": "...", "concept": "...", "reason": "...", "price_range": "..."}}
  ]
}}

## 블로그 데이터
{blog_sample}

## 쇼핑 데이터
{shop_sample}"""

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        res = requests.post("https://api.anthropic.com/v1/messages",
                            headers=headers, json=payload, timeout=90)
        data = res.json()
        if "content" in data:
            raw = data["content"][0]["text"]
            raw = re.sub(r"```json|```", "", raw).strip()
            return json.loads(raw)
        else:
            st.error(f"Claude 오류: {data}")
            return None
    except Exception as e:
        st.error(f"Claude 오류: {e}")
        return None


# ── 네이버 API ───────────────────────────────────────
def naver_search(keyword, api_type, client_id, client_secret, display=20, sort="date"):
    url = f"https://openapi.naver.com/v1/search/{api_type}.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": keyword, "display": display, "sort": sort}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200:
        return res.json().get("items", [])
    else:
        st.error(f"API 오류 {res.status_code}: {res.text}")
        return []

def clean_html(text):
    return re.sub(r"<[^>]+>", "", text)

# ── 블로그 필터/점수 상수 ──────────────────────────
EXCLUDE_KW = [
    "여행","관광","호텔","펜션","숙소","항공","리조트","해외","투어",
    "병원","의원","이비인후과","피부과","치과","한의원","약국","한방",
    "시술","수술","처방","진료","증상","치료","임신","출산","육아","다이어트한약",
    "부동산","아파트","분양","전세","월세","인테리어",
    "전자담배","액상","니코틴","vape","pod","팟",
    "반려","강아지","고양이","펫","pet",
    "공연","전시","뮤지컬","콘서트",
    # ── 커피 중심 카페 블로그 제외 ──
    "아메리카노","에스프레소","콜드브루","드립커피","핸드드립",
    "원두","로스팅","커피원두","스페셜티","싱글오리진",
]

INCLUDE_KW = [
    "음료","카페","라떼","에이드","스무디","주스","티","차",
    "탄산","제로","저당","콤부차","RTD","이온",
    "편의점","마트","쿠팡","올리브영","다이소",
    "구매","리뷰","후기","추천","신제품","출시","한정판",
    "맛","향","성분","칼로리","당류","단백질","카페인","플레이버",
    "트렌드","인기","핫","요즘","베스트",
]

SCORE_RULES = [
    (["신제품","출시","한정판","리뉴얼","론칭"],          30, "신제품/출시"),
    (["카페","카페메뉴","시그니처","신메뉴","계절메뉴"],   25, "카페메뉴"),
    (["트렌드","인기","핫","요즘","베스트","유행"],        20, "소비트렌드"),
    (["구매","리뷰","후기","먹어봤","마셔봤","마심"],      20, "구매후기"),
    (["성분","칼로리","당류","카페인","단백질","영양"],    15, "성분분석"),
    (["편의점","마트","쿠팡","올리브영","네이버쇼핑"],     15, "구매채널"),
    (["가격","원","할인","세일","행사","특가"],            10, "가격정보"),
    (["음료","에이드","라떼","스무디","주스","탄산"],      10, "음료직접"),
]

# ── 플레이버 상수 ─────────────────────────────────────
FLAVOR_KW = {
    "레몬":       ["레몬","lemon"],
    "자몽":       ["자몽","grapefruit"],
    "유자":       ["유자","yuzu"],
    "라임":       ["라임","lime"],
    "복숭아":     ["복숭아","피치","peach"],
    "딸기":       ["딸기","스트로베리","strawberry"],
    "망고":       ["망고","mango"],
    "파인애플":   ["파인애플","pineapple"],
    "블루베리":   ["블루베리","blueberry"],
    "사과":       ["사과","청사과","apple"],
    "포도":       ["포도","grape","머스캣"],
    "히비스커스": ["히비스커스","hibiscus"],
    "콤부차":     ["콤부차","kombucha"],
    "녹차":       ["녹차","그린티","matcha","말차"],
    "얼그레이":   ["얼그레이","earl grey"],
    "루이보스":   ["루이보스","rooibos"],
    "보리차":     ["보리차"],
    "생강":       ["생강","진저","ginger"],
    "민트":       ["민트","페퍼민트","mint"],
    "초콜릿":     ["초콜릿","코코아","카카오","chocolate"],
    "바닐라":     ["바닐라","vanilla"],
    "커피":       ["커피","아메리카노","라떼","콜드브루","espresso"],
}

FLAVOR_SCORE = {
    "레몬": 15, "자몽": 15, "유자": 20, "라임": 15, "복숭아": 12,
    "딸기": 12, "망고": 12, "파인애플": 10, "블루베리": 10, "사과": 8,
    "포도": 8, "히비스커스": 18, "콤부차": 20, "녹차": 12, "얼그레이": 12,
    "루이보스": 15, "보리차": 8, "생강": 12, "민트": 10,
    "초콜릿": 8, "바닐라": 8, "커피": 5,
}

def extract_flavors(text):
    """텍스트에서 플레이버 추출 → [(플레이버, 점수), ...]"""
    text_lower = text.lower()
    found = []
    for flavor, kw_list in FLAVOR_KW.items():
        if any(kw in text_lower for kw in kw_list):
            found.append((flavor, FLAVOR_SCORE.get(flavor, 10)))
    return found


def score_blog_item(title, summary):
    """관련성 점수 계산. 제외 조건 해당 시 -999 반환"""
    text = (title + " " + summary).lower()

    # 제외 키워드 체크
    for kw in EXCLUDE_KW:
        if kw in text:
            return -999, "제외", ""

    # 포함 키워드 체크
    has_include = any(kw in text for kw in INCLUDE_KW)
    if not has_include:
        return 0, "기타", ""

    # 관련성 점수
    score = 0
    tags = []
    for kw_list, pts, tag in SCORE_RULES:
        if any(kw in text for kw in kw_list):
            score += pts
            tags.append(tag)

    # 플레이버 보너스 점수
    flavors = extract_flavors(text)
    flavor_bonus = sum(s for _, s in flavors)
    score += flavor_bonus
    flavor_str = "/".join(f for f, _ in flavors[:3])

    return score, "/".join(tags) if tags else "일반", flavor_str


def search_blog(keywords, client_id, client_secret, display=100):
    all_rows = []
    for kw in keywords:
        items = naver_search(kw, "blog", client_id, client_secret, display=display)
        for item in items:
            date_str = item.get("postdate", "")
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
            except:
                dt = None
            title   = clean_html(item.get("title", ""))
            summary = clean_html(item.get("description", ""))[:150]
            score, tag, flavor = score_blog_item(title, summary)

            if score == -999:          # 노이즈 제외
                continue

            all_rows.append({
                "키워드": kw,
                "제목": title,
                "요약": summary[:100],
                "관련성점수": score,
                "콘텐츠유형": tag,
                "플레이버": flavor,
                "날짜": dt,
                "날짜_원본": date_str,
                "URL": item.get("link", ""),
            })
        time.sleep(0.3)

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df.sort_values("관련성점수", ascending=False).reset_index(drop=True)
    return df

def search_shop(keywords, client_id, client_secret, display=100):
    all_rows = []
    for kw in keywords:
        items = naver_search(kw, "shop", client_id, client_secret, display=display, sort="sim")
        for i, item in enumerate(items):
            price = int(item.get("lprice", 0) or 0)
            title = clean_html(item.get("title", ""))
            pkg = parse_package(title, price)
            shop_flavor = "/".join(f for f, _ in extract_flavors(title)[:3])
            flavor_score = sum(s for _, s in extract_flavors(title))
            all_rows.append({
                "키워드": kw,
                "상품명": title,
                "가격(원)": price,
                "개당가격(원)": pkg["개당가격"],
                "100ml당가격(원)": pkg["100ml당가격"],
                "용량(ml)": pkg["용량(ml)"],
                "개수": pkg["개수"],
                "상품유형": pkg["상품유형"],
                "플레이버": shop_flavor,
                "플레이버점수": flavor_score,
                "카테고리": item.get("category2", "") or item.get("category1", ""),
                "브랜드": item.get("brand", ""),
                "쇼핑몰": item.get("mallName", ""),
                "인기순위": i + 1,
                "URL": item.get("link", ""),
            })
        time.sleep(0.3)
    return pd.DataFrame(all_rows)


# ── 블로그 차트 ──────────────────────────────────────
def render_blog_charts(blog_df):
    if blog_df.empty:
        return

    COLORS = px.colors.qualitative.Pastel
    LB = dict(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
              margin=dict(l=10, r=10, t=45, b=10))

    now = datetime.now()
    six_months_ago = now - timedelta(days=183)   # 6개월 = 약 183일
    df_dated  = blog_df.dropna(subset=["날짜"]).copy()
    df_recent = df_dated[df_dated["날짜"] >= six_months_ago].copy()

    # ━━ Row 1: 점수 분포 + 콘텐츠 유형 파이 ━━
    col1, col2 = st.columns(2)

    with col1:
        # 키워드별 평균 관련성점수 가로바
        score_kw = blog_df.groupby("키워드")["관련성점수"].agg(
            평균점수="mean", 게시글수="count"
        ).reset_index().sort_values("평균점수", ascending=True)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=score_kw["평균점수"],
            y=score_kw["키워드"],
            orientation="h",
            marker_color=COLORS[:len(score_kw)],
            text=score_kw["평균점수"].round(1),
            textposition="outside",
            customdata=score_kw["게시글수"],
            hovertemplate="%{y}<br>평균점수: %{x:.1f}<br>게시글수: %{customdata}<extra></extra>"
        ))
        fig.update_layout(title="키워드별 평균 관련성 점수", height=350,
                          xaxis_title="평균 관련성 점수", yaxis_title="",
                          showlegend=False, **LB)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # 콘텐츠 유형 파이차트
        type_cnt = blog_df["콘텐츠유형"].value_counts().reset_index()
        type_cnt.columns = ["유형","수"]
        fig2 = px.pie(type_cnt, names="유형", values="수",
                      color_discrete_sequence=COLORS,
                      title="콘텐츠 유형 분포",
                      hole=0.4)
        fig2.update_traces(textposition="outside", textinfo="percent+label")
        fig2.update_layout(height=350, showlegend=False, **LB)
        st.plotly_chart(fig2, use_container_width=True)

    # ━━ Row 2: 월별 추이 + 점수 TOP 게시글 ━━
    col3, col4 = st.columns([1.4, 1.6])

    with col3:
        if not df_recent.empty:
            df_recent = df_recent.copy()

            # ── 실제 수집 기간
            actual_min = df_recent["날짜"].min()
            actual_max = df_recent["날짜"].max()
            period_str = (f"{actual_min.strftime('%Y.%m.%d')} ~ "
                          f"{actual_max.strftime('%Y.%m.%d')}")
            keywords_list = df_recent["키워드"].unique().tolist()

            # ── 탭: 주차별 / 일별 선택
            tab_week, tab_day = st.tabs(["📅 주차별 (최근 2개월)", "📆 일별 (최근 30일)"])

            # ── 주차별 탭 ──────────────────────────
            with tab_week:
                two_months_ago = now - timedelta(days=60)
                df_w = df_recent[df_recent["날짜"] >= two_months_ago].copy()

                def get_week_label(d):
                    """날짜 → 'M월 N주' 변환 (해당 월 기준 1~5주)"""
                    # 해당 월 1일
                    first_day = d.replace(day=1)
                    # 1일이 속한 주의 월요일
                    first_monday_offset = first_day.weekday()
                    # 이 날짜가 월의 몇 번째 주인지 계산
                    week_num = (d.day + first_monday_offset - 1) // 7 + 1
                    return f"{d.month}월 {week_num}주"

                df_w["주차표시"] = df_w["날짜"].apply(get_week_label)

                # 최근 2개월 전체 주 목록 생성 (M월 1주 ~ M월 5주 순서)
                all_week_labels = []
                for days_back in range(60, -1, -1):
                    d = now - timedelta(days=days_back)
                    lbl = get_week_label(d)
                    if lbl not in all_week_labels:
                        all_week_labels.append(lbl)

                full_week_idx = pd.MultiIndex.from_product(
                    [all_week_labels, keywords_list], names=["주차표시","키워드"]
                )
                weekly_raw = df_w.groupby(["주차표시","키워드"]).agg(
                    게시글수=("제목","count"),
                    평균점수=("관련성점수","mean")
                )
                weekly = weekly_raw.reindex(full_week_idx, fill_value=0).reset_index()
                weekly.loc[weekly["게시글수"]==0, "평균점수"] = None

                fig_w = go.Figure()
                for i, kw in enumerate(keywords_list):
                    df_kw = weekly[weekly["키워드"]==kw]
                    color = COLORS[i % len(COLORS)]
                    fig_w.add_trace(go.Bar(
                        x=df_kw["주차표시"],
                        y=df_kw["게시글수"],
                        name=kw,
                        marker_color=color,
                        opacity=0.85,
                        hovertemplate=(
                            f"<b>{kw}</b><br>%{{x}}<br>"
                            "게시글수: %{y}건<extra></extra>"
                        ),
                    ))
                fig_w.update_layout(
                    title=dict(text="주차별 언급량 (최근 2개월 · M월 N주 기준)",
                               font=dict(size=13)),
                    barmode="group",
                    height=400,
                    xaxis=dict(
                        title="",
                        categoryorder="array",
                        categoryarray=all_week_labels,
                        tickfont=dict(size=11),
                        tickangle=-40,
                        showgrid=False,
                    ),
                    yaxis=dict(title="게시글 수", rangemode="tozero",
                               showgrid=True, gridcolor="rgba(200,200,200,0.25)"),
                    legend=dict(orientation="h", y=-0.30, x=0.5,
                                xanchor="center", font=dict(size=10),
                                bgcolor="rgba(0,0,0,0)"),
                    hovermode="x unified",
                    margin=dict(l=10,r=10,t=45,b=100),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_w, use_container_width=True)
                if df_w.empty:
                    st.info("최근 2개월 데이터가 없습니다.")

            # ── 일별 탭 ──────────────────────────
            with tab_day:
                thirty_ago = now - timedelta(days=30)
                df_d = df_recent[df_recent["날짜"] >= thirty_ago].copy()
                df_d["일표시"] = df_d["날짜"].dt.strftime("%m/%d")

                # 30일 전체 날짜 목록
                all_days = pd.date_range(start=thirty_ago, end=now, freq="D")
                day_labels = [d.strftime("%m/%d") for d in all_days]
                full_day_idx = pd.MultiIndex.from_product(
                    [day_labels, keywords_list], names=["일표시","키워드"]
                )
                daily_raw = df_d.groupby(["일표시","키워드"]).agg(
                    게시글수=("제목","count"),
                ).rename(columns={"게시글수":"게시글수"})
                daily = daily_raw.reindex(full_day_idx, fill_value=0).reset_index()

                fig_d = go.Figure()
                for i, kw in enumerate(keywords_list):
                    df_kw = daily[daily["키워드"]==kw]
                    color = COLORS[i % len(COLORS)]
                    fig_d.add_trace(go.Bar(
                        x=df_kw["일표시"],
                        y=df_kw["게시글수"],
                        name=kw,
                        marker_color=color,
                        opacity=0.85,
                        hovertemplate=f"<b>{kw}</b><br>날짜: %{{x}}<br>게시글수: %{{y}}건<extra></extra>",
                    ))
                fig_d.update_layout(
                    title=dict(text="일별 언급량 (최근 30일)", font=dict(size=13)),
                    barmode="stack",
                    height=380,
                    xaxis=dict(
                        title="날짜",
                        tickmode="array",
                        tickvals=day_labels[::3],   # 3일 간격으로 표시
                        ticktext=day_labels[::3],
                        tickangle=-45,
                        tickfont=dict(size=10),
                        showgrid=False,
                    ),
                    yaxis=dict(title="게시글 수", rangemode="tozero",
                               showgrid=True, gridcolor="rgba(200,200,200,0.25)"),
                    legend=dict(orientation="h", y=-0.28, x=0.5,
                                xanchor="center", font=dict(size=10),
                                bgcolor="rgba(0,0,0,0)"),
                    hovermode="x unified",
                    margin=dict(l=10,r=10,t=45,b=90),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_d, use_container_width=True)
                if df_d.empty:
                    st.info("최근 30일 데이터가 없습니다.")

            st.caption(
                f"📌 네이버 API 실제 수집 기간: **{period_str}** (총 {len(df_recent)}건) "
                f"— 데이터 밀도가 낮은 구간은 0으로 표시됩니다."
            )
        else:
            st.info("수집된 날짜 데이터가 없습니다.")

    with col4:
        # 관련성점수 TOP15 게시글 테이블
        top_posts = blog_df.nlargest(15, "관련성점수")[
            ["관련성점수","콘텐츠유형","키워드","제목","날짜_원본","URL"]
        ].copy()
        top_posts["날짜_원본"] = pd.to_datetime(
            top_posts["날짜_원본"], format="%Y%m%d", errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        top_posts = top_posts.rename(columns={"날짜_원본":"날짜"})
        st.markdown("**🏆 관련성 점수 TOP 15 게시글**")
        st.dataframe(
            top_posts,
            use_container_width=True,
            height=380,
            column_config={
                "관련성점수": st.column_config.ProgressColumn(
                    "점수", min_value=0, max_value=100, format="%d"),
                "URL": st.column_config.LinkColumn("링크"),
                "제목": st.column_config.TextColumn("제목", width="large"),
            }
        )

    # ━━ Row 3: 키워드 × 콘텐츠유형 히트맵 ━━
    pivot = blog_df.groupby(["키워드","콘텐츠유형"])["관련성점수"].mean().unstack(fill_value=0)
    if not pivot.empty and pivot.shape[1] > 1:
        fig4 = px.imshow(pivot.round(1),
                         color_continuous_scale="Blues",
                         title="키워드 × 콘텐츠유형 평균 관련성 점수 히트맵",
                         text_auto=True, aspect="auto")
        fig4.update_layout(height=300, xaxis_title="콘텐츠 유형",
                           yaxis_title="", coloraxis_showscale=False, **LB)
        st.plotly_chart(fig4, use_container_width=True)

    # ━━ Row 4: 블로그 플레이버 랭킹 ━━
    blog_flavors = blog_df[blog_df["플레이버"] != ""]["플레이버"].str.split("/").explode()
    if not blog_flavors.empty:
        fc = blog_flavors.value_counts().reset_index()
        fc.columns = ["플레이버","언급수"]
        fc = fc[fc["플레이버"].str.strip() != ""].head(15)
        fc["점수합계"] = fc["플레이버"].map(
            lambda f: FLAVOR_SCORE.get(f, 10) * fc.loc[fc["플레이버"]==f, "언급수"].values[0]
        )
        fc = fc.sort_values("점수합계", ascending=True)
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            fig_fl = px.bar(fc, x="언급수", y="플레이버", orientation="h",
                            color="언급수", color_continuous_scale="Teal",
                            text="언급수",
                            title="🍹 블로그 플레이버 언급 순위")
            fig_fl.update_traces(textposition="outside")
            fig_fl.update_layout(height=420, showlegend=False,
                                 coloraxis_showscale=False,
                                 xaxis_title="언급 수", yaxis_title="", **LB)
            st.plotly_chart(fig_fl, use_container_width=True)
        with col_f2:
            fig_fs = px.bar(fc.sort_values("점수합계", ascending=True),
                            x="점수합계", y="플레이버", orientation="h",
                            color="점수합계", color_continuous_scale="Oranges",
                            text="점수합계",
                            title="⭐ 블로그 플레이버 가중 점수 순위",
                            hover_data={"언급수": True})
            fig_fs.update_traces(textposition="outside")
            fig_fs.update_layout(height=420, showlegend=False,
                                 coloraxis_showscale=False,
                                 xaxis_title="가중 점수 합계", yaxis_title="", **LB)
            st.plotly_chart(fig_fs, use_container_width=True)


# ── 쇼핑 차트 ────────────────────────────────────────
def render_shop_charts(shop_df):
    if shop_df.empty:
        return

    COLORS = px.colors.qualitative.Pastel
    layout_base = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=45, b=10)
    )

    # ── RTD 음료만 필터 (가격 왜곡 제거)
    rtd = shop_df[shop_df["상품유형"] == "RTD음료"].copy()
    rtd_valid = rtd[rtd["100ml당가격(원)"].notna() & (rtd["100ml당가격(원)"] > 0)].copy()

    # ━━ Row 1: 상품유형 분포 파이 + 키워드×가격대 히트맵 ━━
    col1, col2 = st.columns(2)

    with col1:
        # 상품유형 파이차트
        type_cnt = shop_df["상품유형"].value_counts().reset_index()
        type_cnt.columns = ["상품유형", "수"]
        fig_pie = px.pie(
            type_cnt, names="상품유형", values="수",
            color_discrete_sequence=COLORS,
            title="수집 상품 유형 분포",
            hole=0.4
        )
        fig_pie.update_traces(textposition="outside", textinfo="percent+label")
        fig_pie.update_layout(height=360, showlegend=False, **layout_base)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        # 키워드 × 100ml당 가격대 히트맵 (RTD만)
        rtd_ml_valid = rtd[rtd["100ml당가격(원)"].notna() & (rtd["100ml당가격(원)"] > 0)]
        if not rtd_ml_valid.empty:
            bins_ml   = [0, 50, 100, 150, 200, 300, 500, 9999]
            labels_ml = ["~50원","51~100","101~150","151~200","201~300","301~500","500원+"]
            rtd_ml_valid = rtd_ml_valid.copy()
            rtd_ml_valid["100ml가격대"] = pd.cut(
                rtd_ml_valid["100ml당가격(원)"], bins=bins_ml, labels=labels_ml)
            hmap = rtd_ml_valid.groupby(
                ["키워드","100ml가격대"], observed=True).size().unstack(fill_value=0)
            fig_hmap = px.imshow(
                hmap,
                color_continuous_scale="Blues",
                title="키워드 × 100ml당 가격대 분포 (RTD만)",
                aspect="auto",
                text_auto=True
            )
            fig_hmap.update_layout(height=360,
                                   xaxis_title="100ml당 가격대",
                                   yaxis_title="",
                                   coloraxis_showscale=False,
                                   **layout_base)
            st.plotly_chart(fig_hmap, use_container_width=True)
        elif not rtd.empty:
            st.info("100ml 가격 계산 가능한 RTD 상품이 없습니다. (용량 미표기)")
        else:
            st.info("RTD음료로 분류된 상품이 없습니다.")

    # ━━ Row 2: 인기순위 TOP20 스트립 + 100ml당 가격 박스플롯 ━━
    col3, col4 = st.columns(2)

    with col3:
        # 인기순위 TOP20 — 키워드별 색상 스트립차트
        top20 = shop_df[shop_df["인기순위"] <= 20].copy()
        top20["개당가격_표시"] = top20["개당가격(원)"].fillna(top20["가격(원)"])
        fig_strip = px.strip(
            top20,
            x="키워드",
            y="개당가격_표시",
            color="키워드",
            hover_name="상품명",
            hover_data={"상품유형": True, "용량(ml)": True, "개수": True},
            color_discrete_sequence=COLORS,
            title="인기순위 TOP20 — 키워드별 개당 가격 분포",
            stripmode="overlay"
        )
        fig_strip.update_layout(height=380, showlegend=False,
                                yaxis_title="개당 가격(원)", xaxis_title="",
                                **layout_base)
        st.plotly_chart(fig_strip, use_container_width=True)

    with col4:
        # 100ml당 가격 박스플롯 (RTD + 이상값 제거)
        if not rtd_valid.empty:
            fig_box = px.box(
                rtd_valid,
                x="키워드",
                y="100ml당가격(원)",
                color="키워드",
                color_discrete_sequence=COLORS,
                points="all",
                hover_name="상품명",
                title="RTD음료 100ml당 가격 분포 (이상값 제거)",
            )
            fig_box.update_layout(height=380, showlegend=False,
                                  xaxis_title="", yaxis_title="100ml당 가격(원)",
                                  **layout_base)
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            st.info("100ml당 가격 계산 가능한 RTD음료 데이터가 없습니다.")

    # ━━ Row 3: 브랜드 포지셔닝 (평균가격 × 상품수 버블) ━━
    brand_has = shop_df[shop_df["브랜드"].str.strip() != ""]
    if not brand_has.empty:
        brand_agg = brand_has.groupby(["브랜드","키워드"]).agg(
            상품수=("상품명","count"),
            평균개당가격=("개당가격(원)","mean"),
            최고인기순위=("인기순위","min")
        ).reset_index()
        brand_top = brand_agg.sort_values("상품수", ascending=False).head(25)

        fig_brand = px.scatter(
            brand_top,
            x="평균개당가격",
            y="최고인기순위",
            size="상품수",
            color="키워드",
            text="브랜드",
            hover_data={"상품수": True, "평균개당가격": ":,.0f", "최고인기순위": True},
            color_discrete_sequence=COLORS,
            title="브랜드 포지셔닝 맵 — 가격 × 인기순위 (버블=상품수)",
            size_max=40,
        )
        fig_brand.update_traces(textposition="top center", textfont_size=11)
        fig_brand.update_yaxes(autorange="reversed")   # 1위가 위쪽
        fig_brand.update_layout(height=420,
                                xaxis_title="평균 개당가격(원)",
                                yaxis_title="최고 인기순위 (낮을수록 상위)",
                                **layout_base)
        st.plotly_chart(fig_brand, use_container_width=True)

        # 제외된 상품 유형 현황 알림
        excluded = shop_df[shop_df["상품유형"] != "RTD음료"]["상품유형"].value_counts()
        if not excluded.empty:
            with st.expander("ℹ️ 가격 분석에서 제외된 상품 유형"):
                for typ, cnt in excluded.items():
                    st.markdown(f"- **{typ}**: {cnt}개 (가격 왜곡 방지를 위해 100ml 분석에서 제외)")

    # ━━ 쇼핑 플레이버 랭킹 ━━
    shop_fl_df = shop_df[shop_df["플레이버"] != ""]["플레이버"].str.split("/").explode()
    if not shop_fl_df.empty:
        sfc = shop_fl_df.value_counts().reset_index()
        sfc.columns = ["플레이버","상품수"]
        sfc = sfc[sfc["플레이버"].str.strip() != ""].head(15)

        # 플레이버별 평균 100ml 가격 (RTD만)
        rtd_fl = shop_df[(shop_df["상품유형"]=="RTD음료") &
                         shop_df["100ml당가격(원)"].notna() &
                         (shop_df["플레이버"]!="")].copy()
        rtd_fl_exp = rtd_fl.assign(
            fl=rtd_fl["플레이버"].str.split("/")
        ).explode("fl")
        fl_price = rtd_fl_exp.groupby("fl")["100ml당가격(원)"].mean().reset_index()
        fl_price.columns = ["플레이버","평균100ml가격"]

        sfc = sfc.merge(fl_price, on="플레이버", how="left")
        sfc["가중점수"] = sfc["플레이버"].map(
            lambda f: FLAVOR_SCORE.get(f, 10)) * sfc["상품수"]
        sfc_asc = sfc.sort_values("상품수", ascending=True)

        col_s1, col_s2 = st.columns(2)
        layout_shop = dict(plot_bgcolor="rgba(0,0,0,0)",
                           paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(l=10, r=10, t=45, b=10))
        with col_s1:
            fig_sfl = px.bar(sfc_asc, x="상품수", y="플레이버", orientation="h",
                             color="상품수", color_continuous_scale="Teal",
                             text="상품수",
                             title="🛒 쇼핑 플레이버 상품 수 순위")
            fig_sfl.update_traces(textposition="outside")
            fig_sfl.update_layout(height=440, showlegend=False,
                                  coloraxis_showscale=False,
                                  xaxis_title="상품 수", yaxis_title="",
                                  **layout_shop)
            st.plotly_chart(fig_sfl, use_container_width=True)

        with col_s2:
            sfc_price = sfc[sfc["평균100ml가격"].notna()].sort_values(
                "평균100ml가격", ascending=True)
            if not sfc_price.empty:
                fig_sp = px.bar(sfc_price, x="평균100ml가격", y="플레이버",
                                orientation="h",
                                color="평균100ml가격",
                                color_continuous_scale="RdYlGn_r",
                                text=sfc_price["평균100ml가격"].round(0).astype(int),
                                title="💰 플레이버별 평균 100ml당 가격 (RTD)")
                fig_sp.update_traces(textposition="outside",
                                     texttemplate="%{text}원")
                fig_sp.update_layout(height=440, showlegend=False,
                                     coloraxis_showscale=False,
                                     xaxis_title="평균 100ml당 가격(원)",
                                     yaxis_title="", **layout_shop)
                st.plotly_chart(fig_sp, use_container_width=True)
            else:
                st.info("100ml 가격 계산 가능한 플레이버 데이터가 없습니다.")


# ── Claude 분석 카드 렌더링 ──────────────────────────
def render_claude_cards(result):
    if not result:
        return

    # ── Row 1: 월별트렌드 + 플레이버 랭킹 + 컨셉 태그
    col1, col2, col3 = st.columns([1.2, 1.4, 1.4])

    with col1:
        st.markdown("#### 📅 월별 트렌드")
        mt = result.get("monthly_trend", {})
        st.info(mt.get("summary", "-"))
        st.markdown(f"**피크:** {mt.get('peak_month', '-')}")
        st.markdown(f"**해석:** {mt.get('insight', '-')}")

    with col2:
        st.markdown("#### 🍋 플레이버 랭킹")
        flavors = result.get("flavor_ranking", [])
        for f in flavors[:6]:
            ratio_str = f.get('ratio', '0%').replace('%', '')
            try:
                ratio = float(ratio_str)
            except:
                ratio = 0
            bar = "█" * int(ratio / 5) + "░" * (20 - int(ratio / 5))
            st.markdown(
                f"`{f.get('rank','')}.` **{f.get('flavor','')}** {f.get('ratio','')}  \n"
                f"<span style='font-size:11px;color:gray'>{bar[:15]}</span>  \n"
                f"<span style='font-size:12px;color:#555'>{f.get('desc','')}</span>",
                unsafe_allow_html=True
            )

    with col3:
        st.markdown("#### 🏷️ 컨셉 태그")
        concepts = result.get("concept_tags", [])
        trend_colors = {"상승": "🟢", "하락": "🔴", "유지": "🟡"}
        for c in concepts:
            icon = trend_colors.get(c.get("trend", "유지"), "⚪")
            st.markdown(
                f"{icon} **{c.get('concept','')}** "
                f"<span style='font-size:12px;color:gray'>({c.get('count',0)}건 · {c.get('trend','')})</span>",
                unsafe_allow_html=True
            )

    st.divider()

    # ── Row 2: 히트제품 + 소비자 니즈
    col4, col5 = st.columns([1.6, 1.4])

    with col4:
        st.markdown("#### 🏆 히트 제품")
        hits = result.get("hit_products", [])
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, h in enumerate(hits[:5]):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            price = h.get('price', 0)
            price_str = f"{price:,}원" if isinstance(price, (int, float)) and price > 0 else "-"
            st.markdown(
                f"{medal} **{h.get('name','')}** ({h.get('brand','-')})  \n"
                f"<span style='font-size:12px;color:gray'>{price_str} · {h.get('reason','')}</span>",
                unsafe_allow_html=True
            )

    with col5:
        st.markdown("#### 💬 소비자 니즈")
        needs = result.get("consumer_needs", [])
        for n in needs:
            st.markdown(f"▸ {n}")

    st.divider()

    # ── Row 3: NPD 아이디어 3카드
    st.markdown("#### 💡 NPD 인사이트 — 신제품 아이디어 3선")
    ideas = result.get("npd_ideas", [])
    idea_cols = st.columns(3)
    colors = ["#EBF5FB", "#EAF7F0", "#FEF9E7"]
    for i, idea in enumerate(ideas[:3]):
        with idea_cols[i]:
            st.markdown(
                f"""<div style='background:{colors[i]};border-radius:12px;padding:16px;height:180px'>
                <div style='font-size:15px;font-weight:600;margin-bottom:8px'>💡 {idea.get('idea','')}</div>
                <div style='font-size:13px;color:#555;margin-bottom:4px'>🍹 {idea.get('flavor','')} · {idea.get('concept','')}</div>
                <div style='font-size:12px;color:#777;margin-bottom:6px'>{idea.get('reason','')}</div>
                <div style='font-size:13px;font-weight:500;color:#2471A3'>💰 {idea.get('price_range','')}</div>
                </div>""",
                unsafe_allow_html=True
            )


# ══════════════════════════════════════════════════════
# ── UI ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════
# ── HTML 리포트 생성 ──────────────────────────────────
# ══════════════════════════════════════════════════════
def build_html_report(blog_df, shop_df, claude_result=None):
    """BCG 스타일 HTML 리포트 생성 → str 반환"""
    today = datetime.today().strftime("%Y년 %m월 %d일")
    keywords = ", ".join(blog_df["키워드"].unique()[:6]) if not blog_df.empty else "-"

    # ── 블로그 TOP10 테이블
    blog_rows = ""
    if not blog_df.empty:
        top = blog_df.nlargest(10, "관련성점수")
        medals = ["🥇","🥈","🥉","④","⑤","⑥","⑦","⑧","⑨","⑩"]
        for i, (_, r) in enumerate(top.iterrows()):
            m = medals[i] if i < len(medals) else str(i+1)
            blog_rows += f"""
            <tr>
              <td>{m}</td>
              <td><span class="score">{int(r.get('관련성점수',0))}</span></td>
              <td><span class="tag">{r.get('콘텐츠유형','')}</span></td>
              <td>{r.get('키워드','')}</td>
              <td><a href="{r.get('URL','#')}" target="_blank">{str(r.get('제목',''))[:50]}</a></td>
            </tr>"""

    # ── 쇼핑 TOP10 테이블
    shop_rows = ""
    if not shop_df.empty:
        rtd = shop_df[shop_df["상품유형"]=="RTD음료"].head(10)
        for i, (_, r) in enumerate(rtd.iterrows()):
            u = f"{int(r['개당가격(원)']):,}원" if r.get('개당가격(원)') else "-"
            _ml = r.get('100ml당가격(원)')
            m = f"{int(float(_ml)):,}원" if _ml and str(_ml) not in ('nan','None','') and float(str(_ml)) > 0 else "-"
            shop_rows += f"""
            <tr>
              <td>{i+1}</td>
              <td>{r.get('키워드','')}</td>
              <td><a href="{r.get('URL','#')}" target="_blank">{str(r.get('상품명',''))[:40]}</a></td>
              <td>{r.get('브랜드','')}</td>
              <td class="price">{u}</td>
              <td class="price">{m}</td>
              <td><span class="tag">{r.get('상품유형','')}</span></td>
            </tr>"""

    # ── NPD 아이디어 카드
    npd_cards = ""
    if claude_result and "npd_ideas" in claude_result:
        colors = ["#00B4D8","#0096B4","#007A96"]
        for i, idea in enumerate(claude_result["npd_ideas"][:3]):
            c = colors[i % 3]
            npd_cards += f"""
            <div class="npd-card">
              <div class="npd-num" style="background:{c}">{i+1}</div>
              <div class="npd-body">
                <div class="npd-title">{idea.get('idea','')}</div>
                <div class="npd-meta">🍹 {idea.get('flavor','')} &nbsp;|&nbsp; 🏷️ {idea.get('concept','')} &nbsp;|&nbsp; 💰 {idea.get('price_range','')}</div>
                <div class="npd-reason">{idea.get('reason','')}</div>
              </div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI NPD SUITE — 음료 트렌드 분석 리포트</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
        background:#f0f4f8;color:#1a2535;font-size:14px}}
  .cover{{background:linear-gradient(135deg,#1E3A5F 0%,#0f1f35 100%);
           color:#fff;padding:60px 80px;position:relative;overflow:hidden}}
  .cover::before{{content:'';position:absolute;right:-80px;top:-80px;
                   width:400px;height:400px;border-radius:50%;
                   background:rgba(0,180,216,0.08)}}
  .cover-badge{{display:inline-block;background:#00B4D8;color:#fff;
                 font-size:11px;font-weight:700;letter-spacing:2px;
                 padding:4px 12px;border-radius:20px;margin-bottom:16px}}
  .cover h1{{font-size:36px;font-weight:700;line-height:1.3;margin-bottom:12px}}
  .cover-sub{{color:#b0c4d8;font-size:15px;margin-bottom:32px}}
  .cover-meta{{display:flex;gap:40px}}
  .cover-meta-item label{{display:block;color:#b0c4d8;font-size:11px;
                            letter-spacing:1px;margin-bottom:4px}}
  .cover-meta-item span{{font-size:18px;font-weight:600;color:#00B4D8}}
  .container{{max-width:1100px;margin:0 auto;padding:40px 24px}}
  .section{{background:#fff;border-radius:12px;margin-bottom:24px;
             box-shadow:0 2px 12px rgba(0,0,0,0.06);overflow:hidden}}
  .section-header{{background:#1E3A5F;color:#fff;padding:16px 24px;
                    display:flex;align-items:center;gap:10px}}
  .section-header h2{{font-size:16px;font-weight:600}}
  .section-header .icon{{font-size:18px}}
  .section-body{{padding:24px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#f5f7fa;color:#1E3A5F;font-weight:600;padding:10px 12px;
      text-align:left;border-bottom:2px solid #e2e8f0}}
  td{{padding:9px 12px;border-bottom:1px solid #f0f4f8;vertical-align:middle}}
  tr:hover td{{background:#f8fbff}}
  a{{color:#00B4D8;text-decoration:none}}
  a:hover{{text-decoration:underline}}
  .score{{display:inline-block;background:#1E3A5F;color:#00B4D8;
           font-weight:700;padding:2px 8px;border-radius:6px;font-size:13px}}
  .tag{{display:inline-block;background:#e8f4f8;color:#00B4D8;
         font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}}
  .price{{color:#1E3A5F;font-weight:600}}
  .npd-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
  .npd-card{{border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}}
  .npd-num{{background:#00B4D8;color:#fff;font-size:22px;font-weight:700;
             text-align:center;padding:16px}}
  .npd-body{{padding:16px}}
  .npd-title{{font-size:15px;font-weight:700;color:#1E3A5F;margin-bottom:8px}}
  .npd-meta{{font-size:12px;color:#666;margin-bottom:8px;line-height:1.6}}
  .npd-reason{{font-size:13px;color:#444;line-height:1.6;
                background:#f8fbff;border-radius:6px;padding:8px}}
  .footer{{text-align:center;color:#888;font-size:12px;padding:32px;}}
  @media(max-width:768px){{
    .cover{{padding:32px 24px}}
    .cover h1{{font-size:24px}}
    .npd-grid{{grid-template-columns:1fr}}
    .cover-meta{{flex-wrap:wrap;gap:20px}}
  }}
</style>
</head>
<body>
<div class="cover">
  <div class="cover-badge">AI NPD SUITE</div>
  <h1>네이버 음료 트렌드<br>분석 리포트</h1>
  <div class="cover-sub">블로그 + 쇼핑 데이터 기반 실시간 시장 인텔리전스</div>
  <div class="cover-meta">
    <div class="cover-meta-item"><label>분석 키워드</label><span>{keywords}</span></div>
    <div class="cover-meta-item"><label>블로그 수집</label><span>{len(blog_df):,}건</span></div>
    <div class="cover-meta-item"><label>쇼핑 수집</label><span>{len(shop_df):,}개</span></div>
    <div class="cover-meta-item"><label>생성일</label><span>{today}</span></div>
  </div>
</div>

<div class="container">

  <div class="section">
    <div class="section-header"><span class="icon">📝</span><h2>블로그 트렌드 — 관련성 점수 TOP 10</h2></div>
    <div class="section-body">
      <table>
        <thead><tr><th>순위</th><th>점수</th><th>유형</th><th>키워드</th><th>제목</th></tr></thead>
        <tbody>{blog_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-header"><span class="icon">🛒</span><h2>쇼핑 트렌드 — RTD음료 TOP 10</h2></div>
    <div class="section-body">
      <table>
        <thead><tr><th>순위</th><th>키워드</th><th>상품명</th><th>브랜드</th><th>개당가격</th><th>100ml당</th><th>유형</th></tr></thead>
        <tbody>{shop_rows}</tbody>
      </table>
    </div>
  </div>

  {"" if not npd_cards else f'''
  <div class="section">
    <div class="section-header"><span class="icon">💡</span><h2>NPD 인사이트 — Claude AI 신제품 아이디어</h2></div>
    <div class="section-body">
      <div class="npd-grid">{npd_cards}</div>
    </div>
  </div>'''}

</div>
<div class="footer">AI NPD SUITE &nbsp;|&nbsp; Powered by Naver API · Anthropic Claude &nbsp;|&nbsp; {today}</div>
</body>
</html>"""
    return html

st.title("🍹 AI NPD SUITE — 네이버 음료 트렌드 분석")
st.caption("네이버 블로그 + 쇼핑 API · Gemini 키워드 추천 · Claude 심층 분석")

# ── 앱 소개 패널 ──────────────────────────────────────
if "show_intro" not in st.session_state:
    st.session_state["show_intro"] = False

col_btn, _ = st.columns([1, 6])
with col_btn:
    if st.button("📖 앱 소개 · 개발 과정"):
        st.session_state["show_intro"] = not st.session_state["show_intro"]

if st.session_state["show_intro"]:
    st.markdown("""
<div style="user-select:text;-webkit-user-select:text;background:linear-gradient(135deg,#f8f9ff 0%,#f0f4ff 100%);
            border:1px solid #d0d8f0;border-radius:16px;padding:28px 32px;margin-bottom:16px">

<h2 style="margin:0 0 6px;color:#1a237e;font-size:22px">🍹 AI NPD SUITE — 음료 트렌드 분석기</h2>
<p style="color:#555;font-size:13px;margin:0 0 24px">
  네이버 블로그 + 쇼핑 데이터 기반 실시간 음료 시장 인텔리전스 플랫폼
</p>

<hr style="border:none;border-top:1px solid #dde3f5;margin:0 0 24px">

<h3 style="color:#1565c0;font-size:15px;margin:0 0 12px">🛠️ 바이브 코딩으로 만든 개발 과정</h3>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px">
  <div style="background:#fff;border-radius:12px;padding:14px;border:1px solid #e3e8f5">
    <div style="font-size:22px;margin-bottom:6px">①</div>
    <div style="font-weight:600;font-size:13px;color:#1a237e;margin-bottom:4px">Instagram 크롤러</div>
    <div style="font-size:12px;color:#666">Selenium 기반 시도<br>→ Instagram 봇 차단<br>→ instaloader 교체<br>→ 최종 실패 확인</div>
  </div>
  <div style="background:#fff;border-radius:12px;padding:14px;border:1px solid #e3e8f5">
    <div style="font-size:22px;margin-bottom:6px">②</div>
    <div style="font-weight:600;font-size:13px;color:#1a237e;margin-bottom:4px">네이버 API 전환</div>
    <div style="font-size:12px;color:#666">블로그 + 쇼핑 API<br>→ Streamlit Cloud 배포<br>→ requirements.txt<br>→ Secrets 관리</div>
  </div>
  <div style="background:#fff;border-radius:12px;padding:14px;border:1px solid #e3e8f5">
    <div style="font-size:22px;margin-bottom:6px">③</div>
    <div style="font-weight:600;font-size:13px;color:#1a237e;margin-bottom:4px">AI 기능 추가</div>
    <div style="font-size:12px;color:#666">Gemini 키워드 추천<br>→ 조건별 멀티셀렉트<br>→ Claude 심층분석<br>→ JSON 구조화 응답</div>
  </div>
  <div style="background:#fff;border-radius:12px;padding:14px;border:1px solid #e3e8f5">
    <div style="font-size:22px;margin-bottom:6px">④</div>
    <div style="font-weight:600;font-size:13px;color:#1a237e;margin-bottom:4px">데이터 품질 개선</div>
    <div style="font-size:12px;color:#666">노이즈 필터링 추가<br>→ 관련성 점수 체계<br>→ 가격 이상값 제거<br>→ Plotly 시각화</div>
  </div>
</div>

<hr style="border:none;border-top:1px solid #dde3f5;margin:0 0 24px">

<h3 style="color:#1565c0;font-size:15px;margin:0 0 12px">⚙️ 주요 기능</h3>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
  <div style="background:#e8f5e9;border-radius:12px;padding:14px">
    <div style="font-weight:600;font-size:13px;color:#1b5e20;margin-bottom:6px">📝 블로그 트렌드 분석</div>
    <ul style="margin:0;padding-left:16px;font-size:12px;color:#333;line-height:1.8">
      <li>노이즈 자동 필터링<br><span style="color:#888">(여행·의료·부동산 제외)</span></li>
      <li>관련성 점수 자동 산정<br><span style="color:#888">(신제품/카페/트렌드/후기)</span></li>
      <li>최근 6개월 월별 추이</li>
      <li>콘텐츠 유형 파이차트</li>
      <li>TOP 15 게시글 순위</li>
    </ul>
  </div>
  <div style="background:#fff3e0;border-radius:12px;padding:14px">
    <div style="font-weight:600;font-size:13px;color:#bf360c;margin-bottom:6px">🛒 쇼핑 트렌드 분석</div>
    <ul style="margin:0;padding-left:16px;font-size:12px;color:#333;line-height:1.8">
      <li>상품유형 자동 분류<br><span style="color:#888">(RTD/농축/건강기능/대용량)</span></li>
      <li>개당·100ml당 가격 계산</li>
      <li>가격 이상값 자동 제거<br><span style="color:#888">(100ml 30~600원 범위)</span></li>
      <li>브랜드 포지셔닝 맵</li>
      <li>키워드×가격대 히트맵</li>
    </ul>
  </div>
  <div style="background:#e3f2fd;border-radius:12px;padding:14px">
    <div style="font-weight:600;font-size:13px;color:#0d47a1;margin-bottom:6px">🤖 AI 분석</div>
    <ul style="margin:0;padding-left:16px;font-size:12px;color:#333;line-height:1.8">
      <li>Gemini 조건별 키워드 추천<br><span style="color:#888">(카테고리/트렌드/타겟/시즌)</span></li>
      <li>Claude 심층 분석 리포트</li>
      <li>플레이버 랭킹 자동 추출</li>
      <li>NPD 아이디어 3선 제안</li>
      <li>JSON 구조화 카드 출력</li>
    </ul>
  </div>
</div>

<hr style="border:none;border-top:1px solid #dde3f5;margin:0 0 16px">

<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
  <div style="background:#fafafa;border-radius:8px;padding:12px;border:1px solid #eee">
    <div style="font-size:11px;color:#888;margin-bottom:4px">사용 API</div>
    <div style="font-size:12px;font-weight:500">Naver 검색 API<br>Google Gemini 2.5 Pro<br>Anthropic Claude Sonnet</div>
  </div>
  <div style="background:#fafafa;border-radius:8px;padding:12px;border:1px solid #eee">
    <div style="font-size:11px;color:#888;margin-bottom:4px">개발 방식</div>
    <div style="font-size:12px;font-weight:500">바이브 코딩<br>(Claude와 대화형 개발)<br>Streamlit Cloud 배포</div>
  </div>
  <div style="background:#fafafa;border-radius:8px;padding:12px;border:1px solid #eee">
    <div style="font-size:11px;color:#888;margin-bottom:4px">활용 목적</div>
    <div style="font-size:12px;font-weight:500">음료 NPD 시장조사<br>플레이버 트렌드 분석<br>경쟁 제품 가격 인텔리전스</div>
  </div>
</div>

</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.subheader("🔑 API 키 설정")
    client_id     = st.text_input("Naver Client ID",
                                  value=st.secrets.get("NAVER_CLIENT_ID", ""),
                                  type="password")
    client_secret = st.text_input("Naver Client Secret",
                                  value=st.secrets.get("NAVER_CLIENT_SECRET", ""),
                                  type="password")
    st.divider()

    st.subheader("🔍 분석 키워드")
    keyword_mode = st.radio("입력 방식", ["✍️ 직접 입력", "🤖 Gemini AI 추천"], horizontal=True)

    if keyword_mode == "🤖 Gemini AI 추천":
        st.markdown("**검색 조건 선택**")
        sel_categories = st.multiselect("음료 카테고리",
            ["탄산음료","차(Tea)","과일주스","에너지음료","유제품음료","기능성음료","RTD커피","발효음료"],
            default=["탄산음료","기능성음료"])
        sel_trends = st.multiselect("트렌드 방향",
            ["저당/제로슈거","프리미엄","기능성/건강","비건/식물성","자연/천연","다이어트","피로회복","스트레스완화"],
            default=["저당/제로슈거","기능성/건강"])
        sel_targets = st.multiselect("타겟 소비자",
            ["10~20대","30~40대","50대 이상","운동/헬스","다이어트","직장인","임산부/어린이"],
            default=["30~40대"])
        sel_season = st.selectbox("시즌",
            ["봄(3~5월)","여름(6~8월)","가을(9~11월)","겨울(12~2월)","연중"], index=0)

        if st.button("✨ AI 키워드 추천받기", use_container_width=True):
            gkey = st.secrets.get("GOOGLE_API_KEY", "")
            if not gkey:
                st.error("GOOGLE_API_KEY가 Secrets에 없습니다.")
            else:
                with st.spinner("Gemini 분석 중..."):
                    suggested = get_gemini_keywords(gkey, sel_categories, sel_trends, sel_targets, sel_season)
                    if suggested:
                        st.session_state["ai_keyword_list"] = suggested
                        st.success(f"{len(suggested)}개 키워드 추천 완료!")

        if "ai_keyword_list" in st.session_state:
            st.markdown("**추천 키워드 선택**")
            selected_kws = []
            cols = st.columns(2)
            for i, kw in enumerate(st.session_state["ai_keyword_list"]):
                with cols[i % 2]:
                    if st.checkbox(kw, value=True, key=f"kw_{i}"):
                        selected_kws.append(kw)
            raw_keywords = ", ".join(selected_kws)
            if raw_keywords:
                st.caption(f"선택: `{raw_keywords}`")
        else:
            raw_keywords = ""
            st.caption("버튼을 눌러 키워드를 추천받으세요.")
    else:
        raw_keywords = st.text_input("키워드 (콤마 구분)", value="저당음료, 제로음료, 기능성음료")

    display_count = st.slider("키워드당 수집 개수", 10, 100, 30, step=10)
    st.divider()
    do_blog   = st.checkbox("📝 블로그 분석", value=True)
    do_shop   = st.checkbox("🛒 쇼핑 분석", value=True)
    do_claude = st.checkbox("🤖 Claude 심층 분석", value=False)
    btn = st.button("🚀 분석 시작", use_container_width=True, type="primary")


# ── 실행 ─────────────────────────────────────────────
if btn:
    if not client_id or not client_secret:
        st.warning("⚠️ Naver API 키를 입력해주세요.")
        st.stop()
    if not raw_keywords.strip():
        st.warning("⚠️ 키워드를 입력하거나 AI 추천을 받아주세요.")
        st.stop()

    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
    blog_df = pd.DataFrame()
    shop_df = pd.DataFrame()
    # session_state 초기화 (새 분석 시작 시)
    st.session_state.pop("blog_df_ppt", None)
    st.session_state.pop("shop_df_ppt", None)
    st.session_state.pop("ppt_bytes_cache", None)
    st.session_state.pop("html_cache", None)

    # ── 블로그 ──
    if do_blog:
        st.subheader("📝 블로그 트렌드")
        with st.spinner("블로그 수집 중..."):
            blog_df = search_blog(keywords, client_id, client_secret, display_count)
            if not blog_df.empty:
                st.session_state["blog_df_ppt"] = blog_df
        if not blog_df.empty:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("유효 게시글", f"{len(blog_df)}건",
                      help="노이즈 제거 후 음료 관련 게시글만 집계")
            m2.metric("평균 관련성 점수", f"{blog_df['관련성점수'].mean():.1f}점")
            high = len(blog_df[blog_df["관련성점수"] >= 40])
            m3.metric("고관련 게시글(40점↑)", f"{high}건")
            recent = blog_df.dropna(subset=["날짜"])
            m4.metric("최신 게시글",
                      recent["날짜"].max().strftime("%Y-%m-%d") if not recent.empty else "-")
            render_blog_charts(blog_df)
            with st.expander("📋 블로그 원본 데이터 보기 (점수순 정렬)"):
                st.dataframe(blog_df.drop(columns=["날짜"]), use_container_width=True,
                             column_config={
                                 "URL": st.column_config.LinkColumn("링크"),
                                 "관련성점수": st.column_config.ProgressColumn(
                                     "점수", min_value=0, max_value=100, format="%d"),
                             })
            csv = blog_df.drop(columns=["날짜"]).to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇️ 블로그 CSV", csv,
                               file_name=f"blog_{datetime.today().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.warning("블로그 데이터 없음 — 키워드를 더 구체적으로 입력해보세요.")

    # ── 쇼핑 ──
    if do_shop:
        st.divider()
        st.subheader("🛒 쇼핑 트렌드")
        with st.spinner("쇼핑 데이터 수집 중..."):
            shop_df = search_shop(keywords, client_id, client_secret, display_count)
            if not shop_df.empty:
                st.session_state["shop_df_ppt"] = shop_df
        if not shop_df.empty:
            # RTD 음료만 추출해서 지표 계산
            rtd_df   = shop_df[shop_df["상품유형"] == "RTD음료"]
            rtd_ml   = rtd_df[rtd_df["100ml당가격(원)"].notna() & (rtd_df["100ml당가격(원)"] > 0)]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 상품 수", f"{len(shop_df)}개",
                      help="RTD·농축·건강기능·대용량 포함 전체")
            m2.metric("RTD 평균 개당가격",
                      f"{rtd_df['개당가격(원)'].mean():,.0f}원" if not rtd_df.empty else "-",
                      help="RTD음료만 기준 (8,000원 초과 이상값 제외)")
            m3.metric("RTD 평균 100ml당",
                      f"{rtd_ml['100ml당가격(원)'].mean():,.0f}원" if not rtd_ml.empty else "-",
                      help="용량 파악된 RTD음료만 / 30~600원 범위만 유효")
            m4.metric("RTD음료 수", f"{len(rtd_df)}개")
            render_shop_charts(shop_df)
            with st.expander("📋 쇼핑 원본 데이터 보기"):
                st.dataframe(shop_df, use_container_width=True,
                             column_config={"URL": st.column_config.LinkColumn("링크")})
            csv = shop_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇️ 쇼핑 CSV", csv,
                               file_name=f"shop_{datetime.today().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.warning("쇼핑 데이터 없음")

    # ── Claude 심층 분석 ──
    if do_claude:
        st.divider()
        st.subheader("🤖 Claude 심층 분석 리포트")
        akey = st.secrets.get("ANTHROPIC_API_KEY", "")
        if not akey:
            st.error("ANTHROPIC_API_KEY가 Secrets에 없습니다.")
        elif blog_df.empty and shop_df.empty:
            st.warning("블로그 또는 쇼핑 데이터를 먼저 수집해주세요.")
        else:
            with st.spinner("Claude가 데이터를 분석 중입니다... (30~60초)"):
                result = analyze_with_claude(akey, blog_df, shop_df)
            if result:
                render_claude_cards(result)
                st.session_state["claude_result"] = result
                st.download_button(
                    "⬇️ 분석 JSON 다운로드",
                    data=json.dumps(result, ensure_ascii=False, indent=2),
                    file_name=f"claude_report_{datetime.today().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )




# ══════════════════════════════════════════════════════
# ── 리포트 출력 (if btn 블록 밖 — 항상 렌더링) ────────
# ══════════════════════════════════════════════════════
st.divider()
st.subheader("📤 분석 결과 리포트 다운로드")
st.caption("수집된 블로그·쇼핑 데이터를 PPT 또는 HTML 리포트로 생성합니다.")

_blog = st.session_state.get("blog_df_ppt", pd.DataFrame())
_shop = st.session_state.get("shop_df_ppt", pd.DataFrame())
claude_res = st.session_state.get("claude_result", None)

col_r1, col_r2, col_r3 = st.columns([1, 1, 3])
with col_r1:
    ppt_btn = st.button("📥 PPT 생성", use_container_width=True, type="primary")
with col_r2:
    html_btn = st.button("🌐 HTML 생성", use_container_width=True)

# 캐시된 파일 다운로드 버튼 (항상 표시)
c1, c2 = st.columns(2)
with c1:
    if "ppt_bytes_cache" in st.session_state:
        st.download_button(
            "⬇️ PPT 다운로드",
            data=st.session_state["ppt_bytes_cache"],
            file_name=st.session_state.get("ppt_fname","report.pptx"),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )
with c2:
    if "html_cache" in st.session_state:
        st.download_button(
            "⬇️ HTML 다운로드",
            data=st.session_state["html_cache"],
            file_name=st.session_state.get("html_fname","report.html"),
            mime="text/html",
            use_container_width=True,
        )

if _blog.empty and _shop.empty and (ppt_btn or html_btn):
    st.warning("⚠️ 먼저 🚀 분석 시작을 눌러 데이터를 수집해주세요.")

# PPT 생성
if ppt_btn and (not _blog.empty or not _shop.empty):
    try:
        from ppt_gen import build_ppt
        with st.spinner("PPT 생성 중..."):
            ppt_bytes = build_ppt(_blog, _shop, claude_res)
        fname = f"NPD_트렌드분석_{datetime.today().strftime('%Y%m%d')}.pptx"
        st.session_state["ppt_bytes_cache"] = ppt_bytes
        st.session_state["ppt_fname"] = fname
        st.success("✅ PPT 생성 완료! 위 ⬇️ PPT 다운로드 버튼을 클릭하세요.")
    except ImportError:
        st.error("requirements.txt에 python-pptx 추가 후 재배포해주세요.")
    except Exception as e:
        st.error(f"PPT 오류: {e}")

# HTML 생성
if html_btn and (not _blog.empty or not _shop.empty):
    with st.spinner("HTML 리포트 생성 중..."):
        html_str = build_html_report(_blog, _shop, claude_res)
    fname_h = f"NPD_트렌드분석_{datetime.today().strftime('%Y%m%d')}.html"
    st.session_state["html_cache"] = html_str.encode("utf-8")
    st.session_state["html_fname"] = fname_h
    st.success("✅ HTML 생성 완료! 위 ⬇️ HTML 다운로드 버튼을 클릭하세요.")
