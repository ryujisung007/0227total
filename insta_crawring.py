import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import random
import os

# 페이지 설정
st.set_page_config(page_title="AI NPD SUITE - Trend Scraper", layout="wide")

def init_driver():
    """
    [시니어 가이드] 스트림릿 클라우드 리눅스 환경에 최적화된 드라이버 설정
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # 봇 차단 방지용 User-Agent
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")

    # [수정] 스트림릿 클라우드에서 크롬 바이너리 위치 강제 지정
    if os.path.exists("/usr/bin/chromium"):
        chrome_options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        chrome_options.binary_location = "/usr/bin/chromium-browser"

    try:
        # webdriver-manager를 사용하되, 실패 시 시스템 드라이버 경로 시도
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.info("시스템 드라이버 경로로 재시도 중...")
        try:
            # 클라우드 환경의 기본 경로 직접 지정
            service = Service("/usr/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e2:
            st.error(f"드라이버 로드 최종 실패: {e2}")
            return None

def scrape_instagram(keyword, count):
    driver = init_driver()
    if not driver:
        return None

    results = []
    url = f"https://www.instagram.com/explore/tags/{keyword}/"
    
    try:
        driver.get(url)
        with st.spinner(f"'{keyword}' 트렌드 수집 중..."):
            time.sleep(random.uniform(8, 12)) # 인스타그램 로딩 대기

            last_height = driver.execute_script("return document.body.scrollHeight")
            
            while len(results) < count:
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                articles = soup.select('div._aabd')
                
                for article in articles:
                    if len(results) >= count: break
                    img_tag = article.select_one('img')
                    if img_tag:
                        img_src = img_tag.get('src', '')
                        alt_text = img_tag.get('alt', '내용 없음')
                        
                        if not any(res['이미지링크'] == img_src for res in results):
                            results.append({
                                "No": len(results) + 1,
                                "수집내용": alt_text,
                                "이미지링크": img_src
                            })

                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(3, 5))
                
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height: break
                last_height = new_height

    except Exception as e:
        st.warning(f"수집 중 중단됨: {e}")
    finally:
        driver.quit()

    return pd.DataFrame(results)

# --- 메인 UI ---
st.title("📋 저당 과일 음료 시장 트렌드 분석")
st.info("LG생활건강 R&D 기획용 - 인스타그램 에스노그래피 분석 도구")

with st.sidebar:
    st.subheader("📊 수집 파라미터")
    target = st.text_input("분석 키워드", value="저당음료")
    limit = st.slider("수집 개수", 5, 50, 20)
    btn = st.button("분석 시작")

if btn:
    df = scrape_instagram(target, limit)
    if df is not None and not df.empty:
        st.subheader(f"🔍 {target} 분석 결과")
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 데이터 다운로드 (CSV)", csv, f"trend_{target}.csv", "text/csv")
    else:
        st.error("데이터 수집에 실패했습니다. 키워드나 설정을 다시 확인해 주세요.")
