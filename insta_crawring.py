import time
import random
from selenium import webdriver
from bs4 import BeautifulSoup

def instagram_crawler(keyword, count=100):
    # 1. 크롬 드라이버 설정 (Senior Tech: Headless 모드 및 User-Agent 설정으로 차단 회피)
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    
    # 2. 인스타그램 해시태그 페이지 접속
    url = f"https://www.instagram.com/explore/tags/{keyword}/"
    driver.get(url)
    time.sleep(random.uniform(5, 7)) # 탐지 회피를 위한 랜덤 대기

    results = []
    
    # 3. 데이터 스크롤 및 수집
    for _ in range(count // 10):
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # 이미지 설명(Alt text)과 본문 텍스트 추출
        articles = soup.select('div._aabd') 
        
        for article in articles:
            try:
                # 시각적 분석을 위한 이미지 URL과 텍스트 데이터 매칭
                img_url = article.select_one('img')['src']
                content = article.select_one('img')['alt']
                results.append({'url': img_url, 'text': content})
            except:
                continue
        
        # 스크롤 다운
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2, 4))
        
    return results
