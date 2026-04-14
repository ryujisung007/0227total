import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import random

# [수정사항] 페이지 설정 및 시니어 전문가용 UI 구성
st.set_page_config(page_title="AI NPD SUITE - Trend Scraper", layout="wide")

def init_driver():
    """
    [개선] 스트림릿 클라우드와 로컬 환경을 모두 지원하는 드라이버 초기화 로직
    """
    chrome_options = Options()
    
    # [핵심 수정] 클라우드 환경 필수 설정
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # [개선] 봇 탐지 방지를 위한 User-Agent 설정
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")

    try:
        # [수정] webdriver_manager를 통한 자동 설치 및 경로 설정
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"드라이버 초기화 실패: {e}")
        return None

def scrape_instagram(keyword, count):
    """
    [논리 보강] 인스타그램 해시태그 기반 데이터 수집 로직
    """
    driver = init_driver()
    if not driver:
        return None

    results = []
    # [수정] 인스타그램 탐지 회피를 위한 대기 시간 최적화
    url = f"https://www.instagram.com/explore/tags/{keyword}/"
    
    try:
        driver.get(url)
        with st.spinner(f"'{keyword}' 트렌드 분석 중... (약 10~20초 소요)"):
            time.sleep(random.uniform(7, 10)) # [수정] 초기 로딩 대기 시간 확장

            # [개선] 페이지 소스 획득 및 파싱
            last_height = driver.execute_script("return document.body.scrollHeight")
            
            # 수집 루프
            while len(results) < count:
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                articles = soup.select('div._aabd') # 인스타그램 게시글 그리드 클래스
                
                for article in articles:
                    if len(results) >= count: break
                    
                    img_tag = article.select_one('img')
                    if img_tag:
                        alt_text = img_tag.get('alt', '')
                        img_src = img_tag.get('src', '')
                        
                        # [중복 제거 로직]
                        if not any(res['이미지링크'] == img_src for res in results):
                            results.append({
                                "No": len(results) + 1,
                                "수집내용": alt_text,
                                "이미지링크": img_src,
                                "분석키워드": keyword
                            })

                # [개선] 다음 컨텐츠를 위한 부드러운 스크롤
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 4))
                
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height: break # 더 이상 읽을 데이터가 없음
                last_height = new_height

    except Exception as e:
        st.warning(f"수집 중 일부 오류 발생: {e}")
    finally:
        driver.quit()

    return pd.DataFrame(results)

# --- UI 레이아웃 ---
st.header("📋 저당 과일 혼합음료 트렌드 크롤러")
st.markdown("---")

col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("⚙️ 수집 설정")
    target = st.text_input("분석 해시태그", value="저당음료", help="샵(#) 제외 입력")
    limit = st.slider("수집 개수", 5, 100, 20)
    start_btn = st.button("실시간 분석 시작")

with col2:
    if start_btn:
        df = scrape_instagram(target, limit)
        
        if df is not None and not df.empty:
            st.success(f"총 {len(df)}개의 트렌드 데이터를 확보했습니다.")
            
            # [수정] 데이터 프레임 출력 및 다운로드 기능
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 분석 결과 보고서 다운로드 (CSV)",
                data=csv,
                file_name=f"trend_{target}_{time.strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("데이터를 가져오지 못했습니다. 잠시 후 다시 시도하거나 키워드를 변경해 주세요.")

# [시니어 가이드] 하단에 분석 팁 추가
st.sidebar.markdown("""
### 💡 Senior's Insight
- **혼합음료** 카테고리는 식품유형상 배합이 자유로워 인스타그램 내 '기능성' 언급량이 많습니다.
- 수집된 '수집내용(Alt text)'에는 소비자가 직접 쓴 해시태그가 포함되어 있어 **감성 분석**에 매우 유리합니다.
""")
