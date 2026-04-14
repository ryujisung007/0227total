import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import random

# 1. 페이지 설정 및 제목
st.set_page_config(page_title="AI NPD SUITE - Trend Scraper", layout="wide")
st.title("🍹 저당 과일 음료 인스타그램 트렌드 분석")
st.sidebar.header("설정")

# 2. 크롤링 함수 (Senior Expert Logic: 에러 점검 및 예외 처리 강화)
def run_insta_crawler(keyword, count):
    # 크롬 옵션 설정 (스트림릿 서버 환경 필수 설정)
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 창이 뜨지 않도록 설정
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.instagram.com/explore/tags/{keyword}/"
        driver.get(url)
        
        # 스트림릿 상태 메시지
        with st.spinner(f"'{keyword}' 관련 데이터를 수집 중입니다..."):
            time.sleep(random.uniform(5, 7))
            results = []
            
            # 실제 스크롤 및 수집 로직 (샘플링)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            articles = soup.select('div._aabd')
            
            for i, article in enumerate(articles[:count]):
                try:
                    img_tag = article.select_one('img')
                    if img_tag:
                        results.append({
                            "순번": i + 1,
                            "내용": img_tag.get('alt', '내용 없음'),
                            "이미지링크": img_tag.get('src', '')
                        })
                except Exception as e:
                    continue
                    
        driver.quit()
        return pd.DataFrame(results)
    
    except Exception as e:
        st.error(f"크롤링 중 오류가 발생했습니다: {e}")
        return None

# 3. 사용자 입력 인터페이스
target_keyword = st.sidebar.text_input("분석할 해시태그 (예: 티즐제로, 저당음료)", "저당음료")
collect_count = st.sidebar.slider("수집할 게시물 수", 10, 50, 20)

if st.sidebar.button("데이터 수집 시작"):
    df = run_insta_crawler(target_keyword, collect_count)
    
    if df is not None and not df.empty:
        st.subheader(f"🔍 '{target_keyword}' 수집 결과")
        
        # 데이터프레임 표시
        st.dataframe(df, use_container_width=True)
        
        # CSV 다운로드 기능 추가
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="결과 데이터 CSV 다운로드",
            data=csv,
            file_name=f"insta_{target_keyword}.csv",
            mime="text/csv",
        )
    else:
        st.warning("수집된 데이터가 없습니다. 해시태그를 확인하거나 잠시 후 다시 시도해 주세요.")
