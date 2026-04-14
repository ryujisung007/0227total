import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import random
import os

st.set_page_config(page_title="AI NPD SUITE - Trend Scraper", layout="wide")

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # [시니어 팁] 실제 브라우저처럼 보이게 하는 필수 설정
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")

    # 스트림릿 클라우드(리눅스)의 표준 경로 설정
    try:
        # 1순위: 시스템에 설치된 chromedriver 경로 직접 지정
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"드라이버 연결 실패: {e}")
        st.info("로컬 환경이시라면 'streamlit run'을 실행한 터미널의 크롬 버전을 확인해주세요.")
        return None

# --- 이하 스크레이핑 로직은 동일 ---
def scrape_instagram(keyword, count):
    driver = init_driver()
    if not driver: return None

    results = []
    url = f"https://www.instagram.com/explore/tags/{keyword}/"
    
    try:
        driver.get(url)
        with st.spinner(f"'{keyword}' 데이터를 불러오는 중..."):
            time.sleep(10) # 인스타그램은 충분한 대기가 필요합니다.
            
            # 간단한 수집 로직
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            articles = soup.select('div._aabd')
            
            for article in articles[:count]:
                img_tag = article.select_one('img')
                if img_tag:
                    results.append({
                        "내용": img_tag.get('alt', '내용 없음'),
                        "이미지링크": img_tag.get('src', '')
                    })
    finally:
        driver.quit()
    return pd.DataFrame(results)

st.title("🍹 신제품 개발용 인스타그램 트렌드 분석")

with st.sidebar:
    target = st.text_input("분석 키워드", value="저당음료")
    limit = st.slider("수집 개수", 5, 30, 10)
    btn = st.button("분석 시작")

if btn:
    df = scrape_instagram(target, limit)
    if df is not None and not df.empty:
        st.dataframe(df)
    else:
        st.warning("데이터를 가져오지 못했습니다.")
