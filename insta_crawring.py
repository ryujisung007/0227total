import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from collections import Counter
import time
import json
import re

st.set_page_config(page_title="AI NPD SUITE - 트렌드 분석", layout="wide")

# ── Gemini 키워드 추천 ───────────────────────────────
def get_gemini_keywords(api_key, categories, trends, targets, season):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-pro:generateContent?key={api_key}"

    condition_text = f"""
- 음료 카테고리: {', '.join(categories) if categories else '전체'}
- 트렌드 방향: {', '.join(trends) if trends else '전체'}
- 타겟 소비자: {', '.join(targets) if targets else '전체'}
- 시즌: {season}
"""
    prompt = f"""당신은 한국 음료 시장 트렌드 전문가입니다.
아래 조건에 맞는 네이버 블로그·쇼핑 검색에 적합한 한국어 키워드 10개를 추천해주세요.

[조건]
{condition_text}

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
            st.error("Gemini 응답에 내용이 없습니다. (토큰 부족 가능성)")
            return []

        text = parts[0]["text"].strip()
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Gemini 오류: {e}")
        return []


# ── Claude 분석 ──────────────────────────────────────
def analyze_with_claude(api_key, blog_df, shop_df):
    blog_sample = blog_df.head(50).to_csv(index=False) if not blog_df.empty else "없음"
    shop_sample = shop_df.head(50).to_csv(index=False) if not shop_df.empty else "없음"

    prompt = f"""당신은 한국 음료 식품 R&D 전문가입니다.
아래 네이버 블로그 및 쇼핑 데이터를 분석하여 다음 항목을 보고서 형태로 작성해주세요.

## 분석 항목
1. **월별 트렌드**: 날짜 기반 월별 언급량 변화 및 해석
2. **플레이버 분석**: 주요 맛/향 키워드 추출 및 빈도 (레몬, 자몽, 복숭아 등)
3. **컨셉 분류**: 저당/제로/기능성/프리미엄/자연 등 컨셉별 분류
4. **히트 제품 분석**: 쇼핑 데이터 기반 인기 제품 특징 (가격대, 브랜드, 카테고리)
5. **소비자 니즈**: 블로그 내용 기반 소비자 관심사 및 구매 동기
6. **NPD 인사이트**: 데이터 기반 신제품 개발 방향 3가지 제언

## 블로그 데이터 (최근 50건)
{blog_sample}

## 쇼핑 데이터 (최근 50건)
{shop_sample}

각 항목을 구체적인 수치와 함께 마크다운 형식으로 작성해주세요."""

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
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=60
        )
        data = res.json()
        if "content" in data:
            return data["content"][0]["text"]
        else:
            st.error(f"Claude 오류: {data}")
            return ""
    except Exception as e:
        st.error(f"Claude 오류: {e}")
        return ""


# ── 네이버 API ───────────────────────────────────────
def naver_search(keyword, api_type, client_id, client_secret, display=20, sort="date"):
    url = f"https://openapi.naver.com/v1/search/{api_type}.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": keyword, "display": display, "sort": sort}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200:
        return res.json().get("items", [])
    else:
        st.error(f"API 오류 {res.status_code}: {res.text}")
        return []

def clean_html(text):
    return re.sub(r"<[^>]+>", "", text)

def search_blog(keywords, client_id, client_secret, display=20):
    all_rows = []
    for kw in keywords:
        items = naver_search(kw, "blog", client_id, client_secret, display=display)
        for item in items:
            all_rows.append({
                "키워드": kw,
                "제목": clean_html(item.get("title", "")),
                "요약": clean_html(item.get("description", ""))[:100],
                "날짜": item.get("postdate", ""),
                "URL": item.get("link", ""),
            })
        time.sleep(0.3)
    return pd.DataFrame(all_rows)

def search_shop(keywords, client_id, client_secret, display=20):
    all_rows = []
    for kw in keywords:
        items = naver_search(kw, "shop", client_id, client_secret, display=display, sort="sim")
        for item in items:
            price = item.get("lprice", "0")
            all_rows.append({
                "키워드": kw,
                "상품명": clean_html(item.get("title", "")),
                "가격(원)": int(price) if price else 0,
                "카테고리": item.get("category2", "") or item.get("category1", ""),
                "브랜드": item.get("brand", ""),
                "쇼핑몰": item.get("mallName", ""),
                "URL": item.get("link", ""),
            })
        time.sleep(0.3)
    return pd.DataFrame(all_rows)


# ── UI ───────────────────────────────────────────────
st.title("🍹 AI NPD SUITE — 네이버 음료 트렌드 분석")
st.caption("네이버 블로그 + 쇼핑 API · Gemini 키워드 추천 · Claude 심층 분석")

with st.sidebar:
    st.subheader("🔑 API 키 설정")
    client_id     = st.text_input("Naver Client ID",
                                  value=st.secrets.get("NAVER_CLIENT_ID", ""),
                                  type="password")
    client_secret = st.text_input("Naver Client Secret",
                                  value=st.secrets.get("NAVER_CLIENT_SECRET", ""),
                                  type="password")

    st.divider()

    # ── 키워드 입력 방식 ──
    st.subheader("🔍 분석 키워드")
    keyword_mode = st.radio(
        "키워드 입력 방식",
        ["✍️ 직접 입력", "🤖 Gemini AI 추천"],
        horizontal=True
    )

    if keyword_mode == "🤖 Gemini AI 추천":
        st.markdown("**검색 조건 선택**")

        category_options = ["탄산음료", "차(Tea)", "과일주스", "에너지음료",
                            "유제품음료", "기능성음료", "RTD커피", "발효음료"]
        trend_options    = ["저당/제로슈거", "프리미엄", "기능성/건강", "비건/식물성",
                            "자연/천연", "다이어트", "피로회복", "스트레스완화"]
        target_options   = ["10~20대", "30~40대", "50대 이상", "운동/헬스",
                            "다이어트", "직장인", "임산부/어린이"]
        season_options   = ["봄(3~5월)", "여름(6~8월)", "가을(9~11월)", "겨울(12~2월)", "연중"]

        sel_categories = st.multiselect("음료 카테고리", category_options,
                                        default=["탄산음료", "기능성음료"])
        sel_trends     = st.multiselect("트렌드 방향", trend_options,
                                        default=["저당/제로슈거", "기능성/건강"])
        sel_targets    = st.multiselect("타겟 소비자", target_options,
                                        default=["30~40대"])
        sel_season     = st.selectbox("시즌", season_options, index=0)

        if st.button("✨ AI 키워드 추천받기", use_container_width=True):
            google_api_key = st.secrets.get("GOOGLE_API_KEY", "")
            if not google_api_key:
                st.error("GOOGLE_API_KEY가 Secrets에 없습니다.")
            else:
                with st.spinner("Gemini가 조건에 맞는 키워드 분석 중..."):
                    suggested = get_gemini_keywords(
                        google_api_key,
                        sel_categories, sel_trends, sel_targets, sel_season
                    )
                    if suggested:
                        st.session_state["ai_keyword_list"] = suggested
                        st.success(f"{len(suggested)}개 키워드 추천 완료!")

        # 추천 키워드 체크박스로 복수 선택
        if "ai_keyword_list" in st.session_state:
            st.markdown("**추천 키워드 선택** (복수 선택 가능)")
            selected_kws = []
            cols = st.columns(2)
            for i, kw in enumerate(st.session_state["ai_keyword_list"]):
                with cols[i % 2]:
                    if st.checkbox(kw, value=True, key=f"kw_{i}"):
                        selected_kws.append(kw)
            raw_keywords = ", ".join(selected_kws)
            if raw_keywords:
                st.caption(f"선택된 키워드: `{raw_keywords}`")
        else:
            raw_keywords = ""
            st.caption("위 버튼을 눌러 키워드를 추천받으세요.")

    else:
        raw_keywords = st.text_input(
            "키워드 (콤마로 구분)",
            value="저당음료, 제로음료, 기능성음료"
        )

    display_count = st.slider("키워드당 수집 개수", 5, 100, 20, step=5)

    st.divider()

    do_blog    = st.checkbox("📝 블로그 분석", value=True)
    do_shop    = st.checkbox("🛒 쇼핑 분석", value=True)
    do_claude  = st.checkbox("🤖 Claude 심층 분석", value=False)

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
    blog_df  = pd.DataFrame()
    shop_df  = pd.DataFrame()

    # ── 블로그 ──
    if do_blog:
        st.subheader("📝 블로그 트렌드")
        with st.spinner("블로그 수집 중..."):
            blog_df = search_blog(keywords, client_id, client_secret, display_count)

        if not blog_df.empty:
            col1, col2 = st.columns([1, 2])
            with col1:
                cnt = blog_df["키워드"].value_counts().reset_index()
                cnt.columns = ["키워드", "게시글수"]
                st.bar_chart(cnt.set_index("키워드"))

                # 월별 분포
                blog_df["월"] = pd.to_datetime(
                    blog_df["날짜"], format="%Y%m%d", errors="coerce"
                ).dt.strftime("%Y-%m")
                monthly = blog_df["월"].value_counts().sort_index()
                if not monthly.empty:
                    st.caption("월별 게시글 수")
                    st.bar_chart(monthly)

            with col2:
                st.dataframe(blog_df, use_container_width=True,
                             column_config={"URL": st.column_config.LinkColumn("링크")})

            csv = blog_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇️ 블로그 CSV", csv,
                               file_name=f"blog_{datetime.today().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.warning("블로그 데이터 없음")

    # ── 쇼핑 ──
    if do_shop:
        st.divider()
        st.subheader("🛒 쇼핑 트렌드")
        with st.spinner("쇼핑 데이터 수집 중..."):
            shop_df = search_shop(keywords, client_id, client_secret, display_count)

        if not shop_df.empty:
            col1, col2, col3 = st.columns(3)
            col1.metric("총 상품 수", f"{len(shop_df)}개")
            col2.metric("평균 가격", f"{shop_df['가격(원)'].mean():,.0f}원")
            col3.metric("최저 가격", f"{shop_df['가격(원)'].min():,.0f}원")
            st.divider()

            col1, col2 = st.columns(2)
            with col1:
                avg_price = shop_df.groupby("키워드")["가격(원)"].mean().reset_index()
                avg_price.columns = ["키워드", "평균가격"]
                st.caption("키워드별 평균가격")
                st.bar_chart(avg_price.set_index("키워드"))
            with col2:
                if shop_df["브랜드"].any():
                    brand_cnt = shop_df["브랜드"].value_counts().head(10)
                    st.caption("브랜드 TOP 10")
                    st.bar_chart(brand_cnt)

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

        anthropic_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            st.error("ANTHROPIC_API_KEY가 Secrets에 없습니다.")
        elif blog_df.empty and shop_df.empty:
            st.warning("블로그 또는 쇼핑 데이터를 먼저 수집해주세요.")
        else:
            with st.spinner("Claude가 데이터를 분석 중입니다... (약 30~60초)"):
                report = analyze_with_claude(anthropic_key, blog_df, shop_df)
            if report:
                st.markdown(report)
                st.download_button(
                    "⬇️ 분석 리포트 다운로드",
                    data=report,
                    file_name=f"claude_report_{datetime.today().strftime('%Y%m%d')}.md",
                    mime="text/markdown"
                )
