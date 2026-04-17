import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from collections import Counter
import time
import json

st.set_page_config(page_title="AI NPD SUITE - 트렌드 분석", layout="wide")

# ── Gemini 키워드 추천 ───────────────────────────────
def get_gemini_keywords(api_key):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-pro:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": (
                "당신은 한국 음료 시장 트렌드 전문가입니다. "
                "현재 한국 소비자들이 네이버 블로그와 쇼핑에서 가장 많이 검색할 "
                "음료 관련 트렌드 키워드 8개를 추천해주세요. "
                "결과는 반드시 JSON 배열 형식으로만 응답하세요. 예시: "
                "[\"저당음료\", \"제로음료\", \"기능성음료\"]"
            )}]
        }],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.7}
    }
    try:
        res = requests.post(url, json=payload, timeout=20)
        data = res.json()

        # 디버그용 응답 출력
        st.write("📡 Gemini 응답 원문:", data)

        if "candidates" not in data:
            st.error(f"응답에 candidates 없음: {data}")
            return ""

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().replace("```json", "").replace("```", "").strip()
        keywords = json.loads(text)
        return ", ".join(keywords)
    except Exception as e:
        st.error(f"Gemini 오류: {e}")
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
    import re
    return re.sub(r"<[^>]+>", "", text)

def search_blog(keywords, client_id, client_secret, display=20):
    all_rows = []
    for kw in keywords:
        items = naver_search(kw, "blog", client_id, client_secret, display=display)
        for item in items:
            all_rows.append({
                "키워드": kw,
                "제목": clean_html(item.get("title", "")),
                "요약": clean_html(item.get("description", ""))[:80],
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
st.caption("네이버 블로그 + 쇼핑 API 기반 실시간 트렌드 수집")

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
    keyword_mode = st.radio(
        "키워드 입력 방식",
        ["✍️ 직접 입력", "🤖 Gemini AI 추천"],
        horizontal=True
    )

    if keyword_mode == "🤖 Gemini AI 추천":
        google_api_key = st.secrets.get("GOOGLE_API_KEY", "")
        if st.button("✨ AI 키워드 추천받기", use_container_width=True):
            with st.spinner("Gemini가 트렌드 키워드를 분석 중..."):
                suggested = get_gemini_keywords(google_api_key)
                if suggested:
                    st.session_state["ai_keywords"] = suggested
                    st.success("추천 완료!")

        raw_keywords = st.text_input(
            "추천 키워드 (수정 가능)",
            value=st.session_state.get("ai_keywords", ""),
            placeholder="AI 추천 버튼을 눌러주세요"
        )
    else:
        raw_keywords = st.text_input(
            "키워드 (콤마로 구분)",
            value="저당음료, 제로음료, 기능성음료"
        )

    display_count = st.slider("키워드당 수집 개수", 5, 100, 20, step=5)

    st.divider()

    do_blog = st.checkbox("📝 블로그 분석", value=True)
    do_shop = st.checkbox("🛒 쇼핑 분석", value=True)

    btn = st.button("🚀 분석 시작", use_container_width=True, type="primary")


# ── 실행 ─────────────────────────────────────────────
if btn:
    if not client_id or not client_secret:
        st.warning("⚠️ 사이드바에 Naver API 키를 입력해주세요.")
        st.stop()

    if not raw_keywords.strip():
        st.warning("⚠️ 키워드를 입력하거나 AI 추천을 받아주세요.")
        st.stop()

    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

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
            with col2:
                st.dataframe(blog_df, use_container_width=True,
                             column_config={"URL": st.column_config.LinkColumn("링크")})
            csv = blog_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇️ 블로그 CSV", csv,
                               file_name=f"blog_trend_{datetime.today().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.warning("블로그 데이터 없음")

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
            avg_price = shop_df.groupby("키워드")["가격(원)"].mean().reset_index()
            avg_price.columns = ["키워드", "평균가격"]
            st.bar_chart(avg_price.set_index("키워드"))
            st.dataframe(shop_df, use_container_width=True,
                         column_config={"URL": st.column_config.LinkColumn("링크")})
            csv = shop_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇️ 쇼핑 CSV", csv,
                               file_name=f"shop_trend_{datetime.today().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.warning("쇼핑 데이터 없음")
