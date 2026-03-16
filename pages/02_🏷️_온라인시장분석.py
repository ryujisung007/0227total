"""
🛍️ 식품 쇼핑 인텔리전스 v9.0
마켓컬리 + 네이버 쇼핑 + OpenAI/Gemini 분석
변경사항:
  - 네이버 탭: 단일분석 / 비교분석 모드 분리
  - 단일분석: 수집 → AI분석 2단계 분리
  - 비교분석: A vs B 동시 비교, 플레이버 차트, 트렌드 히트맵
  - 제품 테이블에 이미지 컬럼 추가 (네이버만)
  - 다크모드 최적화
"""
import streamlit as st
import requests
import pandas as pd
import json
import io
import re
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go

from datetime import datetime, date, timedelta
from google import genai
from pydantic import BaseModel

st.set_page_config(
    page_title="식품 쇼핑 인텔리전스",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 음료 카테고리 / 브랜드
# ============================================================
BEV_CATS = [
    "", "제로음료", "주스/과즙음료", "사이다", "콜라", "이온음료", "과즙탄산음료",
    "에이드음료", "아이스티음료", "파우더/스무디", "녹차/홍차음료", "전통/곡물음료",
    "아이스티/녹차/홍차", "기타탄산음료"
]

BEV_BRANDS = [
    "", "델몬트", "웅진식품", "자연은", "롯데칠성음료", "웅진", "카프리썬", "참존", "코코팜",
    "돈시몬", "풀무원", "해태에이치티비", "미닛메이드", "매일유업", "홀베리", "서울우유", "일화",
    "모구모구", "팔도", "농심", "스위트컵", "갈아만든배", "아임요", "가야농장", "코카콜라", "과일촌",
    "흥국에프엔비", "오션스프레이", "초록매실", "동원", "과수원", "차그림", "빙그레", "포모나",
    "해태제과", "아임리얼", "세미", "이롬", "노브랜드", "커클랜드", "봉봉", "나탈리스", "카고메",
    "그린트리", "피크닉", "DOLE", "오케이에프", "르씨엘", "롯데", "서울팩토리", "하니앤손스"
]

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');

/* 폰트만 지정 — 배경/텍스트 색상은 Streamlit 테마에 맡김 */
html, body { font-family: 'Noto Sans KR', sans-serif !important; }

/* ── 헤더 배너 (의도적 브랜드 색상) ── */
.main-header { background: linear-gradient(135deg, #2D1B69 0%, #7B2D8E 50%, #A855F7 100%); padding: 26px 30px; border-radius: 14px; margin-bottom: 22px; }
.main-header h1 { color: #FFFFFF; font-size: 28px; font-weight: 900; margin: 0; }
.main-header p  { color: #D8B4FE; font-size: 14px; margin: 5px 0 0; }
.naver-header { background: linear-gradient(135deg, #065F46 0%, #059669 50%, #10B981 100%); padding: 26px 30px; border-radius: 14px; margin-bottom: 22px; }
.naver-header h1 { color: #FFFFFF; font-size: 28px; font-weight: 900; margin: 0; }
.naver-header p  { color: #A7F3D0; font-size: 14px; margin: 5px 0 0; }

/* ── 메트릭 카드 ── */
.metric-row { display: flex; gap: 12px; margin: 16px 0 22px; flex-wrap: wrap; }
.metric-card { flex: 1; min-width: 130px; padding: 18px 14px; border-radius: 14px; text-align: center; color: white; box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
.metric-card .num   { font-size: 30px; font-weight: 900; letter-spacing: -1px; }
.metric-card .label { font-size: 12px; opacity: 0.9; margin-top: 3px; }
.mc-purple { background: linear-gradient(135deg, #7C3AED, #A855F7); }
.mc-blue   { background: linear-gradient(135deg, #2563EB, #3B82F6); }
.mc-red    { background: linear-gradient(135deg, #DC2626, #EF4444); }
.mc-amber  { background: linear-gradient(135deg, #D97706, #F59E0B); }
.mc-green  { background: linear-gradient(135deg, #059669, #10B981); }
.mc-teal   { background: linear-gradient(135deg, #0D9488, #14B8A6); }

/* ── 바 차트 ── */
.bar-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
.bar-label      { width: 75px;  text-align: right; font-size: 13px; font-weight: 500; flex-shrink: 0; }
.bar-label-wide { width: 110px; text-align: right; font-size: 13px; font-weight: 500; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar { height: 22px; border-radius: 5px; }
.bar-purple { background: linear-gradient(90deg, #A855F7, #7C3AED); }
.bar-blue   { background: linear-gradient(90deg, #3B82F6, #2563EB); }
.bar-green  { background: linear-gradient(90deg, #10B981, #059669); }
.bar-red    { background: linear-gradient(90deg, #EF4444, #DC2626); }
.bar-count  { font-size: 12px; opacity: 0.7; white-space: nowrap; }

/* ── 섹션 타이틀 ── */
.section-title { font-size: 17px; font-weight: 700; margin: 18px 0 10px; padding-bottom: 5px; border-bottom: 2px solid rgba(128,128,128,0.3); }
.st-purple { color: #A855F7; } .st-blue { color: #3B82F6; } .st-green { color: #10B981; } .st-red { color: #EF4444; }

/* ── 제품 테이블 (배경 제거 — 테마 따름) ── */
.product-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.product-table thead tr { background: linear-gradient(90deg, #7C3AED, #A855F7); color: white; }
.product-table.naver thead tr { background: linear-gradient(90deg, #059669, #10B981); color: white; }
.product-table th { padding: 11px 7px; font-weight: 600; position: sticky; top: 0; z-index: 10; font-size: 13px; }
.product-table thead tr th { background: inherit; }
.product-table td { padding: 6px 7px; border-bottom: 1px solid rgba(128,128,128,0.2); font-size: 13px; vertical-align: middle; }
.product-name a { text-decoration: none; font-weight: 500; font-size: 13px; }
.product-name a:hover { color: #A855F7; }
.product-table.naver .product-name a:hover { color: #10B981; }
.product-desc { font-size: 11px; opacity: 0.5; margin-top: 2px; }
.price-original  { text-decoration: line-through; opacity: 0.5; font-size: 12px; }
.price-discount  { color: #EF4444; font-weight: 700; font-size: 14px; }
.discount-rate   { color: #EF4444; font-weight: 700; }

/* ── 배지 ── */
.badge { display: inline-block; padding: 3px 7px; border-radius: 8px; font-size: 11px; font-weight: 700; margin: 1px; }
.badge-top10  { background: rgba(124,58,237,0.2); color: #A855F7; }
.badge-new    { background: rgba(37,99,235,0.2);  color: #3B82F6; }
.badge-sale   { background: rgba(220,38,38,0.2);  color: #EF4444; }
.badge-low    { background: rgba(217,119,6,0.2);  color: #F59E0B; }
.badge-naver  { background: rgba(5,150,105,0.2);  color: #10B981; }
.badge-brand  { background: rgba(37,99,235,0.2);  color: #3B82F6; }

/* ── 상세 패널 ── */
.detail-panel   { border: 1px solid rgba(128,128,128,0.2); border-radius: 14px; overflow: hidden; }
.detail-header  { background: linear-gradient(135deg, #7C3AED, #A855F7); padding: 16px 20px; }
.detail-header.naver { background: linear-gradient(135deg, #059669, #10B981); }
.detail-header h3 { margin: 0; font-size: 16px; font-weight: 700; color: white; }
.detail-header p  { margin: 4px 0 0; font-size: 12px; color: rgba(255,255,255,0.8); }
.detail-body { padding: 16px 20px; }
.detail-img  { width: 100%; border-radius: 10px; margin-bottom: 14px; max-height: 320px; object-fit: contain; }
.detail-price-box { background: rgba(124,58,237,0.15); border-radius: 10px; padding: 14px; margin-bottom: 14px; }
.detail-price-box.naver { background: rgba(5,150,105,0.15); }
.detail-price-big { font-size: 24px; font-weight: 900; color: #A855F7; }
.detail-price-box.naver .detail-price-big { color: #10B981; }
.detail-info-grid  { display: grid; grid-template-columns: 85px 1fr; gap: 6px 12px; font-size: 14px; margin-bottom: 14px; }
.detail-info-label { opacity: 0.6; font-weight: 600; }
.detail-option      { padding: 8px 12px; margin: 4px 0; border-radius: 8px; font-size: 13px; display: flex; justify-content: space-between; border: 1px solid rgba(128,128,128,0.2); }
.detail-option-name  { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.detail-option-price { color: #A855F7; font-weight: 700; margin-left: 8px; }
.detail-allergy     { background: rgba(217,119,6,0.15); border: 1px solid rgba(217,119,6,0.3); border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #F59E0B; margin-top: 10px; }
.detail-placeholder { text-align: center; padding: 80px 20px; opacity: 0.4; }
.detail-placeholder .icon { font-size: 48px; margin-bottom: 12px; }

/* ── AI 박스 ── */
.ai-box { background: rgba(67,56,202,0.1); border: 1px solid rgba(99,102,241,0.3); border-radius: 14px; padding: 20px; margin: 16px 0; }
.ai-box h3 { color: #818CF8; font-size: 17px; font-weight: 700; margin: 0 0 12px; }
.ai-box .ai-content { font-size: 14px; line-height: 1.8; white-space: pre-wrap; }

/* ── 트렌드 테이블 ── */
.trend-table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 10px; }
.trend-table th { padding: 10px 8px; background: linear-gradient(90deg, #059669, #10B981); color: white; font-weight: 600; text-align: center; }
.trend-table td { padding: 9px 8px; border-bottom: 1px solid rgba(128,128,128,0.2); text-align: center; }
.trend-rank { font-size: 18px; font-weight: 900; color: #10B981; }

/* ── 비교 레이블 ── */
.compare-label-a { color: #3B82F6; font-weight: 700; font-size: 16px; }
.compare-label-b { color: #10B981; font-weight: 700; font-size: 16px; }

footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# API 설정
# ============================================================
KURLY_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.kurly.com/",
    "Origin": "https://www.kurly.com"
}
KURLY_BASE = "https://api.kurly.com/collection/v2/home/sites/market"
KURLY_SORT = {"신상품순": "0", "추천순": "4", "판매량순": "1", "혜택순": "5", "높은가격순": "3", "낮은가격순": "2"}

NAVER_ANALYSIS_SORT = {
    "판매 많은순(추천)": "sim",
    "신상품순": "date",
    "낮은가격순": "asc",
    "높은가격순": "dsc",
}

CATEGORY_QUERY_MAP = {
    "제로음료": "제로음료", "주스/과즙음료": "주스 과즙음료",
    "사이다": "사이다 음료", "콜라": "콜라 음료", "이온음료": "이온음료",
    "과즙탄산음료": "과즙탄산음료", "에이드음료": "에이드 음료",
    "아이스티음료": "아이스티 음료", "파우더/스무디": "파우더 스무디 음료",
    "녹차/홍차음료": "녹차 홍차 음료", "전통/곡물음료": "전통 곡물음료",
    "아이스티/녹차/홍차": "아이스티 녹차 홍차", "기타탄산음료": "탄산음료", "": "음료"
}

# ============================================================
# 키 로딩
# ============================================================
def load_naver_keys():
    for sec in ["naver_shopping", "naver_search"]:
        try:
            cid  = st.secrets[sec]["NAVER_CLIENT_ID"]
            csec = st.secrets[sec]["NAVER_CLIENT_SECRET"]
            if cid and cid.strip() and csec and csec.strip():
                return cid.strip(), csec.strip(), sec
        except Exception:
            pass
    return "", "", ""

def load_openai_key():
    try:
        key = st.secrets["openai"]["OPENAI_API_KEY"]
        return key.strip() if key and key.strip() else ""
    except Exception:
        return ""

def load_gemini_key():
    """GOOGLE_API_KEY / GEMINI_API_KEY 모든 위치에서 탐색"""
    try:
        # 최상위 직접 키
        for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "google_api_key", "gemini_api_key"):
            v = st.secrets.get(k, "")
            if v and v.strip():
                return v.strip()
        # 중첩 섹션
        for sec in ("gemini", "google"):
            try:
                for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "api_key"):
                    v = st.secrets[sec].get(k, "")
                    if v and v.strip():
                        return v.strip()
            except Exception:
                pass
    except Exception:
        pass
    return ""

# ============================================================
# OpenAI 분석 (컬리용)
# ============================================================
def ai_analyze(products_info, context="네이버 쇼핑", api_key=""):
    if not api_key:
        return "⚠️ OpenAI API 키가 설정되지 않았습니다."
    prompt = f"""
당신은 한국 식품/음료 시장의 데이터 기반 분석 전문가이자 15년 경력의 음료 마케팅 기획자입니다.
[데이터 해석 주의사항]
- 아래 데이터는 {context}의 검색 노출 상품 목록이며 시장 전체 판매 데이터가 아닙니다.
- "추정", "가능성", "검색 노출 기준" 같은 표현을 사용하세요.
[분석 대상 데이터]
{products_info}
[출력 형식] 아래 8개 항목 순서대로 출력 (각 항목: 데이터 한계 / 분석 / 시사점)
### 1. 고유 SKU 분석 ### 2. 입수/용량 보정 가격 분석 ### 3. 판매채널 구조
### 4. 번들/기획팩 구성 특성 ### 5. 맛/플레이버 키워드 ### 6. R&D 시사점
### 7. 회의용 멘트 ### 8. 마케팅 기획자 페르소나 스크립트
"""
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [
                {"role": "system", "content": "한국 식품/음료 시장 트렌드 분석 전문가."},
                {"role": "user", "content": prompt}
            ], "temperature": 0.7, "max_tokens": 2000},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return f"⚠️ API 오류 ({resp.status_code}): {resp.text[:200]}"
    except Exception as e:
        return f"⚠️ 요청 실패: {str(e)}"

# ============================================================
# 컬리 API
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def kurly_load_tree():
    r = requests.get(f"{KURLY_BASE}/category-groups", headers=KURLY_H, timeout=10)
    r.raise_for_status()
    tree = {}
    for c in r.json()["data"]["main"]:
        code, name = str(c["code"]), c["name"]
        tree[code] = {"name": name, "subs": {str(s["code"]): s["name"] for s in c.get("sub_category_groups", [])}}
    return tree

@st.cache_data(ttl=600, show_spinner=False)
def kurly_fetch(cat_code, sort_type, max_items):
    items, pp = [], 96
    for page in range(1, (max_items // pp) + 2):
        try:
            resp = requests.get(
                f"{KURLY_BASE}/product-categories/{cat_code}/products",
                headers=KURLY_H,
                params={"sort_type": sort_type, "page": page, "per_page": pp, "filters": ""},
                timeout=10
            )
            if resp.status_code != 200:
                break
            prods = resp.json().get("data", [])
            if not prods:
                break
            for rank, p in enumerate(prods, start=len(items)+1):
                items.append({
                    "순위": rank, "카테고리코드": cat_code,
                    "상품번호": p.get("no",""), "상품명": p.get("name",""),
                    "설명": p.get("short_description",""),
                    "판매가": p.get("sales_price", 0),
                    "할인가": p.get("discounted_price"),
                    "할인율": p.get("discount_rate", 0),
                    "리뷰수": p.get("review_count",""),
                    "품절": "Y" if p.get("is_sold_out") else "N",
                    "배송유형": ", ".join(d.get("description","") for d in p.get("delivery_type_infos",[])),
                    "이미지URL": p.get("list_image_url",""),
                    "상품URL": f"https://www.kurly.com/goods/{p.get('no','')}",
                    "저재고": "Y" if p.get("is_low_stock") else "N"
                })
            if len(items) >= max_items:
                break
        except Exception:
            break
    return items[:max_items]

@st.cache_data(ttl=600, show_spinner=False)
def kurly_detail(pno):
    try:
        r = requests.get(
            f"https://www.kurly.com/goods/{pno}",
            headers={"User-Agent": KURLY_H["User-Agent"]}, timeout=10
        )
        if "__NEXT_DATA__" not in r.text:
            return None
        mk = '__NEXT_DATA__" type="application/json">'
        s = r.text.find(mk) + len(mk)
        e = r.text.find("</script>", s)
        return json.loads(r.text[s:e]).get("props",{}).get("pageProps",{}).get("product")
    except Exception:
        return None

# ============================================================
# 네이버 API 공통
# ============================================================
def clean_html(t):
    return re.sub(r'<[^>]+>', '', t) if t else ""

def safe_int(x, default=0):
    try:
        return int(float(str(x).replace(",","").strip()))
    except Exception:
        return default

@st.cache_data(ttl=300, show_spinner=False)
def naver_search_raw(query, cid, csec, display=100, start=1, sort="sim"):
    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec}
    resp = requests.get(
        "https://openapi.naver.com/v1/search/shop.json",
        headers=headers,
        params={"query": query, "display": display, "start": start, "sort": sort},
        timeout=15
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("items", [])

def build_naver_query(category: str, brand: str) -> str:
    base = CATEGORY_QUERY_MAP.get(category, "음료")
    return f"{brand} {base}".strip() if brand and brand.strip() else base.strip()

def normalize_title(title: str) -> str:
    t = clean_html(title).lower()
    t = re.sub(r"\[[^\]]+\]", " ", t)
    t = re.sub(r"\([^)]+\)", " ", t)
    for p in [r"\b\d+(\.\d+)?\s?(ml|l|g|kg|ea|개|입|병|캔|팩|포)\b",
              r"\b\d+\s?[xX]\s?\d+\b", r"\b\d+\s?개입\b",
              r"\b증정\b", r"\b기획\b", r"\b세트\b", r"\b묶음\b",
              r"\b대용량\b", r"\b무료배송\b", r"\b정품\b"]:
        t = re.sub(p, " ", t)
    t = re.sub(r"[^0-9a-zA-Z가-힣\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def extract_core_keywords(title: str, max_words=3) -> str:
    tokens = [t for t in normalize_title(title).split() if t]
    return " ".join(tokens[:max_words]) if tokens else "기타"

def collect_naver_products(query: str, cid: str, csec: str, sort_label: str, limit: int = 500) -> pd.DataFrame:
    sort_api = NAVER_ANALYSIS_SORT.get(sort_label, "sim")
    rows = []
    for start in [1, 101, 201, 301, 401]:
        if len(rows) >= limit:
            break
        items = naver_search_raw(query, cid, csec, display=100, start=start, sort=sort_api)
        if not items:
            break
        for idx, item in enumerate(items, start=start):
            rows.append({
                "rank": idx, "query": query,
                "title": clean_html(item.get("title","")),
                "normalized_title": normalize_title(item.get("title","")),
                "core_group": extract_core_keywords(item.get("title",""), 3),
                "link": item.get("link",""), "image": item.get("image",""),
                "lprice": safe_int(item.get("lprice",0)),
                "hprice": safe_int(item.get("hprice",0)),
                "mallName": item.get("mallName",""), "brand": item.get("brand",""),
                "maker": item.get("maker",""), "category1": item.get("category1",""),
                "category2": item.get("category2",""), "category3": item.get("category3",""),
                "productType": item.get("productType",""), "productId": item.get("productId","")
            })
        if len(items) < 100:
            break
        time.sleep(0.1)
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["rank","query","title","normalized_title","core_group",
                                    "link","image","lprice","hprice","mallName","brand",
                                    "maker","category1","category2","category3","productType","productId"])
    return df.head(limit).reset_index(drop=True)

def aggregate_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    total_n = len(work)
    work["rank_score_raw"] = work["rank"].apply(lambda x: max(total_n - x + 1, 1))
    grouped = (
        work.groupby("normalized_title", dropna=False)
        .agg(
            대표상품명=("title", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
            대표링크=("link","first"), 대표이미지=("image","first"),
            대표판매처=("mallName", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
            대표브랜드=("brand", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
            대표제조사=("maker", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
            핵심제품군=("core_group", lambda s: s.mode().iloc[0] if not s.mode().empty else s.iloc[0]),
            상품수=("title","count"),
            평균최저가=("lprice","mean"), 최저가최소=("lprice","min"), 최저가최대=("lprice","max"),
            평균순위원점수=("rank_score_raw","mean"), 최고순위=("rank","min")
        ).reset_index()
    )
    max_count = max(grouped["상품수"].max(), 1)
    max_rank  = max(grouped["평균순위원점수"].max(), 1)
    grouped["추천점수"]   = (grouped["상품수"] / max_count * 100).round(2)
    grouped["판매순위점수"] = (grouped["평균순위원점수"] / max_rank * 100).round(2)
    grouped["순위점수"]   = (grouped["판매순위점수"] * 0.7 + grouped["추천점수"] * 0.3).round(2)
    grouped["평균최저가"] = grouped["평균최저가"].round(0).astype(int)
    return grouped.sort_values(["순위점수","상품수","최고순위"], ascending=[False,False,True]).reset_index(drop=True)

# ============================================================
# 태그 사전
# ============================================================
FLAVOR_DICT = {
    "레몬":["레몬","lemon"], "포도":["포도","grape"], "복숭아":["복숭아","peach"],
    "청포도":["청포도"], "오렌지":["오렌지","orange"], "사과":["사과","apple"],
    "자몽":["자몽","grapefruit"], "망고":["망고","mango"], "딸기":["딸기","strawberry"],
    "파인애플":["파인애플","pineapple"], "유자":["유자"], "매실":["매실"], "배":["배"],
    "석류":["석류"], "블루베리":["블루베리"], "콜라":["콜라","cola"],
    "사이다":["사이다","cider"], "녹차":["녹차","green tea"], "홍차":["홍차","black tea"],
    "아이스티":["아이스티","ice tea"], "커피":["커피","coffee"],
    "요거트":["요거트","yogurt","요구르트"],
}
TREND_DICT = {
    "제로/저당":["제로","zero","무설탕","저당","sugar free"],
    "기능성/건강":["비타민","콜라겐","프로틴","단백질","유산균","식이섬유","건강"],
    "과일감성":["과즙","fruit","과일","자연은"],
    "카페형":["에이드","스무디","티","tea","라떼"],
    "탄산/청량":["탄산","sparkling","사이다","콜라"],
    "RTD/간편":["캔","병","파우치","팩"],
    "프리미엄":["착즙","nfc","100%","프리미엄"],
}

def match_tags(text: str, dictionary: dict) -> list:
    t = normalize_title(text)
    return [label for label, patterns in dictionary.items()
            if any(p.lower() in t for p in patterns)]

def enrich_tags(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        df["flavor_tags"] = [[] for _ in range(len(df))]
        df["trend_tags"]  = [[] for _ in range(len(df))]
        return df
    out = df.copy()
    out["flavor_tags"] = out["대표상품명"].apply(lambda x: match_tags(x, FLAVOR_DICT))
    out["trend_tags"]  = out["대표상품명"].apply(lambda x: match_tags(x, TREND_DICT))
    return out

def explode_tag_stats(df: pd.DataFrame, tag_col: str, score_col="순위점수") -> pd.DataFrame:
    if df.empty or tag_col not in df.columns:
        return pd.DataFrame(columns=["태그","빈도","평균순위점수","평균가격"])
    rows = []
    for _, r in df.iterrows():
        tags = r[tag_col]
        if not isinstance(tags, list):
            continue
        for t in tags:
            rows.append({"태그": t, "순위점수": r.get(score_col,0), "평균최저가": r.get("평균최저가",0)})
    if not rows:
        return pd.DataFrame(columns=["태그","빈도","평균순위점수","평균가격"])
    temp = pd.DataFrame(rows)
    stat = (temp.groupby("태그", dropna=False)
            .agg(빈도=("태그","count"), 평균순위점수=("순위점수","mean"), 평균가격=("평균최저가","mean"))
            .reset_index()
            .sort_values(["빈도","평균순위점수"], ascending=[False,False])
            .reset_index(drop=True))
    stat["평균순위점수"] = stat["평균순위점수"].round(2)
    stat["평균가격"]     = stat["평균가격"].round(0).astype(int)
    return stat

# ============================================================
# Gemini Structured Output
# ============================================================
class ProductInsight(BaseModel):
    product_name: str
    normalized_name: str
    primary_flavor: str
    secondary_flavors: list[str]
    trend_keywords: list[str]
    functional_positioning: list[str]
    package_format: str
    sugar_positioning: str
    confidence: float

class InsightBatch(BaseModel):
    items: list[ProductInsight]

def call_gemini_extract(df: pd.DataFrame, gemini_client, batch_size: int = 25) -> pd.DataFrame:
    """
    속도 개선:
    - 상위 30건으로 제한 (기존: 전체)
    - 1회 단일 호출 (기존: 25건씩 순차 배치)
    """
    if df.empty:
        return pd.DataFrame()

    # 상위 30건만 처리 (속도 최우선)
    target = df.head(30).copy()
    product_lines = [
        {"product_name": r["대표상품명"], "normalized_name": r["normalized_title"]}
        for _, r in target.iterrows()
    ]

    prompt = f"""다음 한국 네이버 쇼핑 음료 상품명 목록의 각 상품에 대해 추출하라.
규칙: primary_flavor=대표flavor 1개 / secondary_flavors=보조flavor들 /
trend_keywords=소비자 관점 키워드 2~5개 / functional_positioning=건강·기능·편의·프리미엄 등 /
package_format=캔·병·팩·파우치·분말·기타 / sugar_positioning=제로·저당·일반·불명 / confidence=0~1
입력: {json.dumps(product_lines, ensure_ascii=False)}"""

    results = []
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-pro", contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": InsightBatch}
        )
        parsed = response.parsed
        if parsed and hasattr(parsed, "items"):
            for item in parsed.items:
                results.append({
                    "normalized_title": item.normalized_name,
                    "gemini_primary_flavor": item.primary_flavor,
                    "gemini_secondary_flavors": item.secondary_flavors,
                    "gemini_trend_keywords": item.trend_keywords,
                    "gemini_functional_positioning": item.functional_positioning,
                    "gemini_package_format": item.package_format,
                    "gemini_sugar_positioning": item.sugar_positioning,
                    "gemini_confidence": item.confidence
                })
    except Exception:
        for _, r in target.iterrows():
            results.append({
                "normalized_title": r["normalized_title"],
                "gemini_primary_flavor": "", "gemini_secondary_flavors": [],
                "gemini_trend_keywords": [], "gemini_functional_positioning": [],
                "gemini_package_format": "", "gemini_sugar_positioning": "", "gemini_confidence": 0.0
            })

    out = pd.DataFrame(results)
    return out.drop_duplicates(subset=["normalized_title"]).reset_index(drop=True) if not out.empty else out


def generate_market_report(agg_df, flavor_stats, trend_stats, query, sort_label, d1, d2, gemini_client) -> str:
    """프롬프트 압축 버전 — 토큰 절약으로 응답 속도 향상"""
    top_products = agg_df.head(10)[["대표상품명","대표브랜드","상품수","평균최저가","순위점수"]].to_dict(orient="records")
    top_flavors  = flavor_stats.head(8).to_dict(orient="records") if not flavor_stats.empty else []
    top_trends   = trend_stats.head(8).to_dict(orient="records")  if not trend_stats.empty else []

    payload = {
        "검색어": query, "정렬": sort_label, "기간": f"{d1}~{d2}",
        "제품수": int(len(agg_df)),
        "top_products": top_products,
        "top_flavors": top_flavors,
        "top_trends": top_trends,
    }
    prompt = (
        f"한국 음료 시장 분석보고서를 한국어로 작성하라.\n"
        f"항목: 시장요약 / 핵심플레이버트렌드 / 브랜드시사점 / 가격대시사점 / 신제품개발제안 / 데이터한계\n"
        f"조건: 실무형, 최소 6문단, 마크다운 사용, 네이버 쇼핑 검색 기반 한계 명시\n"
        f"데이터: {json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        resp = gemini_client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
        return resp.text if hasattr(resp, "text") else "보고서 생성 실패"
    except Exception as e:
        return f"보고서 생성 실패: {e}"

# ============================================================
# 공통 렌더링
# ============================================================
def render_metrics(cards):
    h = '<div class="metric-row">'
    for num, label, cls in cards:
        h += f'<div class="metric-card {cls}"><div class="num">{num}</div><div class="label">{label}</div></div>'
    st.markdown(h + '</div>', unsafe_allow_html=True)

def render_bars(title, tcls, data, bcls, wide=False, pct=False, total=1):
    if not data:
        return
    mx = max(data.values()) if data.values() else 1
    lc = "bar-label-wide" if wide else "bar-label"
    h = f'<div class="section-title {tcls}">{title}</div>'
    for lb, cnt in data.items():
        w = int(cnt / mx * 260) if mx > 0 else 0
        p = f" ({cnt/total*100:.0f}%)" if pct and total > 0 else ""
        h += f'<div class="bar-row"><div class="{lc}">{lb}</div><div class="bar {bcls}" style="width:{w}px;"></div><div class="bar-count">{cnt}개{p}</div></div>'
    st.markdown(h, unsafe_allow_html=True)

def to_excel(df):
    buf = io.BytesIO()
    cols = [c for c in df.columns if c not in ["이미지URL","그룹키"]]
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df[cols].to_excel(w, sheet_name="전체", index=False)
    return buf.getvalue()

def to_csv(df):
    cols = [c for c in df.columns if c not in ["이미지URL","그룹키"]]
    return df[cols].to_csv(index=False).encode("utf-8-sig")

# ============================================================
# 네이버 제품 테이블 렌더링 (이미지 포함)
# ============================================================
def render_naver_product_table(agg_df: pd.DataFrame, max_rows: int = 200):
    rows_html = ""
    for i, row in agg_df.head(max_rows).iterrows():
        url = row.get("대표링크","")
        img = row.get("대표이미지","")
        nm  = str(row.get("대표상품명",""))[:38]

        # 이미지 셀
        if img:
            img_html = (f'<img src="{img}" width="56" height="56" '
                        f'style="border-radius:6px;object-fit:cover;background:rgba(128,128,128,0.1);" '
                        f'onerror="this.style.display=\'none\'">')
        else:
            img_html = '<div style="width:56px;height:56px;background:rgba(128,128,128,0.15);border-radius:6px;"></div>'

        # 배지
        bd = ""
        if row.get("대표브랜드"):
            bd += f'<span class="badge badge-brand">{str(row["대표브랜드"])[:8]}</span>'
        if row.get("gemini_primary_flavor"):
            bd += f'<span class="badge badge-naver">{str(row["gemini_primary_flavor"])[:8]}</span>'

        rows_html += (
            f'<tr>'
            f'<td style="text-align:center;color:#34D399;font-weight:700;">{i+1}</td>'
            f'<td style="text-align:center;padding:6px;">{img_html}</td>'
            f'<td class="product-name"><a href="{url}" target="_blank">{nm}</a>'
            f'<div class="product-desc">{row.get("대표판매처","")}</div></td>'
            f'<td style="text-align:right;font-weight:600;color:inherit;">₩{int(row.get("평균최저가",0)):,}</td>'
            f'<td style="text-align:center;">{int(row.get("상품수",0))}</td>'
            f'<td style="text-align:center;">{bd}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="max-height:520px;overflow-y:auto;border:1px solid rgba(128,128,128,0.2);border-radius:10px;">'
        f'<table class="product-table naver">'
        f'<thead><tr><th>#</th><th>사진</th><th>상품명</th><th>평균가</th><th>중복수</th><th>정보</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>',
        unsafe_allow_html=True
    )

# ============================================================
# 비교 분석 시각화
# ============================================================
def render_flavor_compare(agg_a: pd.DataFrame, agg_b: pd.DataFrame, label_a: str, label_b: str):
    """플레이버 빈도 A vs B 가로 바 차트"""
    st.markdown('<div class="section-title st-blue">🍋 플레이버 분포 비교</div>', unsafe_allow_html=True)

    fa = explode_tag_stats(agg_a.rename(columns={"flavor_tags":"_f"}), "_f") if not agg_a.empty else pd.DataFrame()
    fb = explode_tag_stats(agg_b.rename(columns={"flavor_tags":"_f"}), "_f") if not agg_b.empty else pd.DataFrame()

    all_tags = list(set(
        (fa["태그"].tolist() if not fa.empty else []) +
        (fb["태그"].tolist() if not fb.empty else [])
    ))
    if not all_tags:
        st.info("플레이버 데이터 없음")
        return

    fa_map = dict(zip(fa["태그"], fa["빈도"])) if not fa.empty else {}
    fb_map = dict(zip(fb["태그"], fb["빈도"])) if not fb.empty else {}

    tags_sorted = sorted(all_tags, key=lambda t: fa_map.get(t,0) + fb_map.get(t,0), reverse=True)[:12]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=label_a, y=tags_sorted,
        x=[fa_map.get(t,0) for t in tags_sorted],
        orientation="h", marker_color="#3B82F6"
    ))
    fig.add_trace(go.Bar(
        name=label_b, y=tags_sorted,
        x=[fb_map.get(t,0) for t in tags_sorted],
        orientation="h", marker_color="#10B981"
    ))
    fig.update_layout(
        barmode="group", height=420,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=None), legend=dict(orientation="h", y=1.1),
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(title="빈도", gridcolor="rgba(128,128,128,0.2)"),
        yaxis=dict(autorange="reversed", gridcolor="rgba(128,128,128,0.2)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_trend_heatmap(agg_a: pd.DataFrame, agg_b: pd.DataFrame, label_a: str, label_b: str):
    """트렌드 히트맵 (행=A/B, 열=트렌드 키워드, 값=비율%)"""
    st.markdown('<div class="section-title st-green">🔥 트렌드 히트맵</div>', unsafe_allow_html=True)

    trend_keys = list(TREND_DICT.keys())
    data = {}
    for df, label in [(agg_a, label_a), (agg_b, label_b)]:
        if df.empty or "trend_tags" not in df.columns:
            data[label] = {k: 0 for k in trend_keys}
            continue
        total = max(len(df), 1)
        row_data = {}
        for k in trend_keys:
            cnt = df["trend_tags"].apply(lambda tags: k in tags if isinstance(tags, list) else False).sum()
            row_data[k] = round(cnt / total * 100, 1)
        data[label] = row_data

    heat_df = pd.DataFrame(data).T  # 행=라벨, 열=트렌드
    heat_df = heat_df[trend_keys]

    fig = px.imshow(
        heat_df,
        text_auto=True, aspect="auto",
        color_continuous_scale="Teal",
        labels=dict(x="트렌드", y="검색어", color="비율(%)"),
    )
    fig.update_layout(
        height=220, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=None), margin=dict(l=10, r=10, t=20, b=10),
        coloraxis_showscale=True,
    )
    fig.update_xaxes(side="bottom")
    st.plotly_chart(fig, use_container_width=True)


def render_price_compare(agg_a: pd.DataFrame, agg_b: pd.DataFrame, label_a: str, label_b: str):
    """가격대 분포 비교"""
    st.markdown('<div class="section-title st-purple">💰 가격대 분포 비교</div>', unsafe_allow_html=True)
    fig = go.Figure()
    for df, label, color in [(agg_a, label_a, "#3B82F6"), (agg_b, label_b, "#10B981")]:
        if df.empty:
            continue
        ps = df["평균최저가"].replace(0, np.nan).dropna()
        if ps.empty:
            continue
        fig.add_trace(go.Histogram(
            x=ps, name=label, nbinsx=15,
            marker_color=color, opacity=0.75
        ))
    fig.update_layout(
        barmode="overlay", height=320,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=None),
        xaxis=dict(title="평균최저가(원)", gridcolor="rgba(128,128,128,0.2)"),
        yaxis=dict(title="제품 수", gridcolor="rgba(128,128,128,0.2)"),
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 🟣 컬리 탭
# ============================================================
def tab_kurly():
    tree = kurly_load_tree()
    oai_key = load_openai_key()
    if "k_df"  not in st.session_state: st.session_state.k_df  = None
    if "k_sel" not in st.session_state: st.session_state.k_sel = None

    with st.sidebar:
        st.markdown("### 🟣 컬리 설정")
        mo = {info["name"]: code for code, info in tree.items()}
        sm_names = st.multiselect("대분류", list(mo.keys()), [], placeholder="선택", key="k_main")
        smc = [mo[n] for n in sm_names]
        so = {}
        if smc:
            for mc in smc:
                for sc, sn in tree[mc]["subs"].items():
                    so[f"{tree[mc]['name']} > {sn}"] = sc
        if so:
            asub = st.checkbox("✅ 하위 전체", True, key="k_allsub")
            ssn  = list(so.keys()) if asub else st.multiselect("하위", list(so.keys()), [], key="k_sub")
            ssc  = [so[n] for n in ssn]
        else:
            ssc = []
        st.markdown("---")
        ks = st.selectbox("정렬", list(KURLY_SORT.keys()), 0, key="k_sort")
        km = st.slider("최대 출력", 10, 300, 100, 10, key="k_max")
        kw = st.text_input("키워드", placeholder="콤부차,제로", key="k_kw")
        kp = st.slider("가격", 0, 100000, (0, 100000), 1000, format="₩%d", key="k_pr")
        st.markdown("---")
        k_d1 = st.date_input("시작일", date.today()-timedelta(days=30), key="k_d1")
        k_d2 = st.date_input("종료일", date.today(), key="k_d2")
        st.caption("※ 컬리 API 날짜 필터 미지원 → 신상품순으로 최신성 확보")
        ke = st.checkbox("품절 제외", True, key="k_excl")
        kr = st.button("🔍 컬리 수집", type="primary", use_container_width=True, disabled=not smc, key="k_run")

    st.markdown('<div class="main-header"><h1>🛒 마켓컬리 신제품 인텔리전스</h1><p>카테고리별 트렌드 · 상품 선택 시 우측 상세 · AI 분석</p></div>', unsafe_allow_html=True)

    if kr and smc:
        tgts = []
        if ssc:
            for sc in ssc:
                nm = sc
                for info in tree.values():
                    if sc in info["subs"]: nm = info["subs"][sc]; break
                tgts.append((sc, nm))
        else:
            for mc in smc: tgts.append((mc, tree[mc]["name"]))
        if tgts:
            pg = st.progress(0, "📡 수집...")
            ad = []
            for i, (code, name) in enumerate(tgts):
                pg.progress((i+1)/len(tgts), f"📡 [{i+1}/{len(tgts)}] {name}")
                its = kurly_fetch(code, KURLY_SORT[ks], km)
                for it in its: it["카테고리명"] = name
                ad.extend(its)
            pg.empty()
            if ad:
                df = pd.DataFrame(ad).drop_duplicates(subset=["상품번호"], keep="first")
                if kw.strip():
                    kws = [k.strip() for k in kw.split(",") if k.strip()]
                    df  = df[df["상품명"].str.contains("|".join(kws), case=False, na=False)]
                if ke: df = df[df["품절"]=="N"]
                pmin, pmax = kp
                df = df[(df["판매가"]>=pmin)&(df["판매가"]<=pmax)].head(km).reset_index(drop=True)
                st.session_state.k_df  = df
                st.session_state.k_sel = None

    df = st.session_state.k_df
    if df is None or len(df) == 0:
        st.markdown('<div style="text-align:center;padding:60px;color:#6B7280;"><div style="font-size:48px;">🛍️</div><div style="font-size:18px;font-weight:600;color:#C084FC;">사이드바에서 카테고리 선택 → 수집 시작</div></div>', unsafe_allow_html=True)
        return

    total = len(df); avg_p = df["판매가"].mean()
    dc = (df["할인율"]>0).sum(); ad = df.loc[df["할인율"]>0,"할인율"].mean() if dc>0 else 0
    lc = (df["저재고"]=="Y").sum()
    render_metrics([(f"{total:,}","총 상품","mc-purple"),(f"₩{avg_p:,.0f}","평균가격","mc-blue"),
                    (f"{dc:,}",f"할인(평균{ad:.0f}%)","mc-red"),(f"{lc:,}","품절임박⚡","mc-amber")])

    if oai_key and total>0:
        if st.button("🤖 AI 트렌드 분석 (컬리 TOP 상품)", key="k_ai"):
            with st.spinner("🤖 AI 분석 중..."):
                lines = []
                for _, row in df.head(20).iterrows():
                    lines.append(f"{row['순위']}위: {row['상품명']} | ₩{row['판매가']:,}")
                result = ai_analyze("\n".join(lines), f"마켓컬리 ({', '.join(sm_names)})", oai_key)
            st.markdown(f'<div class="ai-box"><h3>🤖 AI 트렌드 분석</h3><div class="ai-content">{result}</div></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        bins = [0,3000,5000,10000,20000,30000,50000,float("inf")]
        labels = ["~3천","3~5천","5천~1만","1~2만","2~3만","3~5만","5만~"]
        df["가격대"] = pd.cut(df["판매가"], bins=bins, labels=labels)
        pd_d = df["가격대"].value_counts().sort_index()
        render_bars("💰 가격대","st-purple",{str(k):int(v) for k,v in pd_d.items() if v>0},"bar-purple",pct=True,total=total)
    with c2:
        if df["카테고리명"].nunique()>1:
            cd = df["카테고리명"].value_counts().head(10)
            render_bars("📁 카테고리별","st-blue",{str(k)[:12]:int(v) for k,v in cd.items()},"bar-blue",wide=True)

    st.markdown("---")
    col_l, col_r = st.columns([6,4])
    with col_l:
        pl = [f"[{r['순위']}] {r['상품명'][:28]} | ₩{r['판매가']:,}" for _,r in df.iterrows()]
        pn = [r["상품번호"] for _,r in df.iterrows()]
        ci = 0
        if st.session_state.k_sel and st.session_state.k_sel in pn:
            ci = pn.index(st.session_state.k_sel)
        si = st.selectbox("🔍 상품 선택 → 우측 상세", range(len(pl)), ci, format_func=lambda i: pl[i], key="k_psel")
        st.session_state.k_sel = pn[si]
        rows = ""
        for _, row in df.iterrows():
            nm = str(row["상품명"])[:36]; url = row["상품URL"]
            if row["할인가"] and row["할인율"] and row["할인율"]>0:
                ph = f'<span class="price-original">₩{row["판매가"]:,}</span><br><span class="price-discount">₩{row["할인가"]:,}</span>'
                dh = f'<span class="discount-rate">{row["할인율"]}%</span>'
            else:
                ph = f'₩{row["판매가"]:,}'; dh = "-"
            bd = ""
            if row["순위"]<=10: bd += '<span class="badge badge-top10">🆕TOP10</span>'
            elif row["순위"]<=30: bd += '<span class="badge badge-new">NEW</span>'
            if row["할인율"] and row["할인율"]>=20: bd += '<span class="badge badge-sale">🔥SALE</span>'
            if row.get("저재고")=="Y": bd += '<span class="badge badge-low">⚡임박</span>'
            cn = str(row.get("카테고리명",""))[:8]
            rows += f'<tr><td style="text-align:center;color:#C084FC;font-weight:700;">{row["순위"]}</td><td style="text-align:center;font-size:12px;">{cn}</td><td class="product-name"><a href="{url}" target="_blank">{nm}</a></td><td style="text-align:right;">{ph}</td><td style="text-align:center;">{dh}</td><td style="text-align:center;">{bd}</td></tr>'
        st.markdown(f'<div style="max-height:520px;overflow-y:auto;border:1px solid rgba(128,128,128,0.2);border-radius:10px;"><table class="product-table"><thead><tr><th>#</th><th>카테고리</th><th>상품명</th><th>가격</th><th>할인</th><th>상태</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
        d1c, d2c = st.columns(2)
        with d1c: st.download_button("📥 엑셀", to_excel(df), f"kurly_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", type="primary", key="k_dl")
        with d2c: st.download_button("📥 CSV",  to_csv(df),   f"kurly_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",  type="secondary", key="k_csv")

    with col_r:
        st.markdown('<div class="section-title st-purple">📦 상품 상세</div>', unsafe_allow_html=True)
        pno = st.session_state.k_sel
        if pno:
            with st.spinner("로딩..."): det = kurly_detail(pno)
            if det:
                name = det.get("name",""); img = det.get("mainImageUrl","")
                bp = det.get("basePrice",0); dpv = det.get("discountedPrice"); drv = det.get("discountRate",0)
                prh = (f'<span class="detail-price-big">₩{dpv:,}</span> <span style="text-decoration:line-through;color:#6B7280;">₩{bp:,}</span> <span style="background:#EF4444;color:white;padding:2px 8px;border-radius:10px;font-size:13px;font-weight:700;">{drv}%</span>'
                       if dpv and drv and drv>0 else f'<span class="detail-price-big">₩{bp:,}</span>')
                vol = det.get("volume",""); seller = det.get("sellerName","")
                brand = det.get("brandInfo",{}).get("name","-") if det.get("brandInfo") else "-"
                rc = det.get("reviewCount",0)
                allergy = det.get("allergy","")
                delivery = ", ".join(str(d) for d in det.get("deliveryTypeNames",[]))
                opts = "".join(f'<div class="detail-option"><span class="detail-option-name">{dp.get("name","")[:30]}</span><span class="detail-option-price">₩{dp.get("basePrice",0):,}</span></div>' for dp in det.get("dealProducts",[])[:6])
                alh = f'<div class="detail-allergy">⚠️ {allergy.replace(chr(10),"<br>")}</div>' if allergy and allergy.strip() else ""
                st.markdown(f'<div class="detail-panel"><div class="detail-header"><h3>📦 {name}</h3></div><div class="detail-body"><img class="detail-img" src="{img}" onerror="this.style.display=\'none\'"><div class="detail-price-box">{prh}</div><div class="detail-info-grid"><span class="detail-info-label">용량</span><span class="detail-info-value">{vol}</span><span class="detail-info-label">배송</span><span class="detail-info-value">{delivery}</span><span class="detail-info-label">판매자</span><span class="detail-info-value">{seller}</span><span class="detail-info-label">브랜드</span><span class="detail-info-value">{brand}</span><span class="detail-info-label">리뷰</span><span class="detail-info-value">⭐ {rc:,}개</span></div>{opts}{alh}</div></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align:center;margin-top:12px;"><a href="https://www.kurly.com/goods/{pno}" target="_blank" style="display:inline-block;padding:10px 24px;background:linear-gradient(135deg,#7C3AED,#A855F7);color:white;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">🔗 컬리에서 보기</a></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="detail-panel"><div class="detail-placeholder"><div class="icon">⚠️</div><div>상세 로딩 실패</div></div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="detail-panel"><div class="detail-placeholder"><div class="icon">👆</div><div style="font-size:15px;font-weight:600;color:#C084FC;">상품을 선택하세요</div></div></div>', unsafe_allow_html=True)


# ============================================================
# 🟢 네이버 탭 — 단일분석 / 비교분석 모드
# ============================================================
def tab_naver():
    # ── session_state 초기화 ──
    for k, v in {
        # 단일
        "n_raw_df": None, "n_agg_df": None, "n_report": "",
        "n_flavor_stats": None, "n_trend_stats": None,
        "n_query": "", "n_detail_idx": 0, "n_csv_df": None,
        "n_collected": False,   # 수집 완료 여부 (2단계 분리)
        # 비교
        "cmp_agg_a": None, "cmp_agg_b": None,
        "cmp_label_a": "", "cmp_label_b": "",
        "cmp_collected": False,
    }.items():
        if k not in st.session_state: st.session_state[k] = v

    auto_id, auto_sec, auto_src = load_naver_keys()
    gemini_key = load_gemini_key()

    with st.sidebar:
        st.markdown("### 🟢 네이버 쇼핑 설정")

        if auto_id and auto_sec:
            st.success(f"🔑 네이버 API 키 로딩 ({auto_src})")
            n_id, n_sec = auto_id, auto_sec
        else:
            st.warning("네이버 API 키 없음")
            n_id  = st.text_input("Client ID",     type="password", key="n_id")
            n_sec = st.text_input("Client Secret", type="password", key="n_sec")

        if gemini_key: st.success("✨ Gemini API 키 로딩")
        else:
            st.warning("Gemini API 키 없음")
            gemini_key = st.text_input("Gemini API Key", type="password", key="g_key")

        st.markdown("---")

        # ── 모드 선택 ──
        naver_mode = st.radio("분석 모드", ["📊 단일 분석", "⚡ 비교 분석"], key="naver_mode")

        st.markdown("---")

        if naver_mode == "📊 단일 분석":
            n_bev    = st.selectbox("음료분류", BEV_CATS, 0, key="n_bev",
                                    format_func=lambda x: x if x else "전체 (음료)")
            n_brand  = st.selectbox("브랜드", BEV_BRANDS, 0, key="n_brand",
                                    format_func=lambda x: x if x else "전체")
            n_sort   = st.selectbox("정렬", list(NAVER_ANALYSIS_SORT.keys()), 0, key="n_sort")
            n_limit  = st.slider("최대 결과", 100, 500, 300, 100, key="n_max")
            st.markdown("**📅 검색 기간 (표시용)**")
            nd1 = st.date_input("시작일", date.today()-timedelta(days=30), key="n_d1")
            nd2 = st.date_input("종료일", date.today(), key="n_d2")
            st.caption("※ 네이버 API는 날짜 직접 필터 미지원")

            btn_collect = st.button("1️⃣ 수집 실행", type="primary",
                                    use_container_width=True,
                                    disabled=not(n_id and n_sec), key="n_collect")
            btn_ai = st.button("2️⃣ AI 분석 실행", type="secondary",
                                use_container_width=True,
                                disabled=not(gemini_key and st.session_state.n_collected),
                                key="n_ai")

        else:  # 비교 분석
            st.markdown("**─── 검색 A ───**")
            cmp_bev_a   = st.selectbox("음료분류 A", BEV_CATS, 0, key="cmp_bev_a",
                                        format_func=lambda x: x if x else "전체 (음료)")
            cmp_brand_a = st.selectbox("브랜드 A", BEV_BRANDS, 0, key="cmp_brand_a",
                                        format_func=lambda x: x if x else "전체")
            st.markdown("**─── 검색 B ───**")
            cmp_bev_b   = st.selectbox("음료분류 B", BEV_CATS, 1, key="cmp_bev_b",
                                        format_func=lambda x: x if x else "전체 (음료)")
            cmp_brand_b = st.selectbox("브랜드 B", BEV_BRANDS, 0, key="cmp_brand_b",
                                        format_func=lambda x: x if x else "전체")
            cmp_sort  = st.selectbox("정렬", list(NAVER_ANALYSIS_SORT.keys()), 0, key="cmp_sort")
            cmp_limit = st.slider("유형별 최대 결과", 100, 300, 200, 100, key="cmp_max")

            btn_collect = st.button("1️⃣ 비교 수집 실행", type="primary",
                                    use_container_width=True,
                                    disabled=not(n_id and n_sec), key="cmp_collect")
            btn_ai = None  # 비교는 AI 보고서 없음 (시각화만)

        st.markdown("---")
        st.caption("📡 네이버 쇼핑 Open API")

    # ══════════════════════════════════════════════════════
    # 헤더
    # ══════════════════════════════════════════════════════
    st.markdown('<div class="naver-header"><h1>🟢 네이버 쇼핑 인텔리전스</h1><p>중복 통합 · 플레이버/트렌드 추출 · Gemini 분석보고서 · A vs B 비교</p></div>', unsafe_allow_html=True)

    if not (n_id and n_sec):
        st.info("사이드바에 네이버 API 키를 설정해주세요.")
        return

    # ══════════════════════════════════════════════════════
    # 📊 단일 분석 모드
    # ══════════════════════════════════════════════════════
    if naver_mode == "📊 단일 분석":

        # ── 1단계: 수집 ──
        if btn_collect:
            query = build_naver_query(n_bev, n_brand)
            with st.spinner(f"🔍 '{query}' 수집 · 중복 통합 중…"):
                raw_df = collect_naver_products(query, n_id, n_sec, n_sort, n_limit)
                agg_df = aggregate_duplicates(raw_df)
                agg_df = enrich_tags(agg_df)

                # gemini_* 컬럼 초기화 (AI 전까지)
                for col, default in [
                    ("gemini_primary_flavor",""), ("gemini_secondary_flavors",[]),
                    ("gemini_trend_keywords",[]), ("gemini_functional_positioning",[]),
                    ("gemini_package_format",""), ("gemini_sugar_positioning",""),
                    ("gemini_confidence",0.0)
                ]:
                    agg_df[col] = [default]*len(agg_df) if isinstance(default, list) else default

                flavor_stats = explode_tag_stats(
                    agg_df.rename(columns={"flavor_tags":"_f"}), "_f")
                trend_stats  = explode_tag_stats(
                    agg_df.rename(columns={"trend_tags":"_t"}), "_t")

                st.session_state.n_raw_df      = raw_df
                st.session_state.n_agg_df      = agg_df
                st.session_state.n_flavor_stats = flavor_stats
                st.session_state.n_trend_stats  = trend_stats
                st.session_state.n_query        = query
                st.session_state.n_report       = ""
                st.session_state.n_collected    = True
                st.session_state.n_detail_idx   = 0
            st.success(f"✅ 수집 완료 — 원본 {len(raw_df)}건 → 통합 {len(agg_df)}건 | 2️⃣ AI 분석 버튼으로 Gemini 분석을 실행하세요")

        # ── 2단계: AI 분석 (병렬 실행) ──
        if btn_ai and st.session_state.n_collected:
            if not gemini_key:
                st.error("Gemini API 키가 없습니다.")
            else:
                agg_df = st.session_state.n_agg_df
                try:
                    gemini_client = genai.Client(api_key=gemini_key)
                except Exception as e:
                    st.error(f"Gemini 클라이언트 생성 실패: {e}")
                    return

                import concurrent.futures
                fs = st.session_state.n_flavor_stats
                ts = st.session_state.n_trend_stats

                with st.spinner("✨ Gemini 분석 중… (플레이버 추출 + 보고서 동시 생성)"):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                        fut_extract = ex.submit(call_gemini_extract, agg_df, gemini_client)
                        fut_report  = ex.submit(
                            generate_market_report,
                            agg_df, fs, ts,
                            st.session_state.n_query, n_sort, nd1, nd2, gemini_client
                        )
                        g_df   = fut_extract.result()
                        report = fut_report.result()

                if not g_df.empty:
                    agg_df = agg_df.merge(g_df, on="normalized_title", how="left",
                                          suffixes=("","_gem"))

                st.session_state.n_agg_df = agg_df
                st.session_state.n_report = report
                st.success("✅ AI 분석 완료!")

        # ── 결과 렌더링 ──
        raw_df       = st.session_state.n_raw_df
        agg_df       = st.session_state.n_agg_df
        flavor_stats = st.session_state.n_flavor_stats
        trend_stats  = st.session_state.n_trend_stats
        report_text  = st.session_state.n_report
        query        = st.session_state.n_query

        if raw_df is None or len(raw_df) == 0:
            st.markdown('<div style="text-align:center;padding:60px;color:#6B7280;"><div style="font-size:48px;">🔍</div><div style="font-size:18px;font-weight:600;color:#34D399;">1️⃣ 수집 실행으로 시작하세요</div></div>', unsafe_allow_html=True)
            return

        total_raw = len(raw_df); total_agg = len(agg_df)
        avg_price   = agg_df["평균최저가"].mean() if len(agg_df)>0 else 0
        brand_count = agg_df["대표브랜드"].nunique() if "대표브랜드" in agg_df.columns else 0

        render_metrics([
            (f"{total_raw:,}", "원본 상품수", "mc-green"),
            (f"{total_agg:,}", "중복통합 후", "mc-teal"),
            (f"₩{avg_price:,.0f}", "평균최저가", "mc-blue"),
            (f"{brand_count:,}", "브랜드수", "mc-amber"),
        ])

        # TOP 10 요약
        st.markdown('<div class="section-title st-green">🏆 요약 트렌드 TOP 10</div>', unsafe_allow_html=True)
        trows = ""
        for idx, row in agg_df.head(10).iterrows():
            trows += (f'<tr><td><span class="trend-rank">{idx+1}</span></td>'
                      f'<td style="text-align:left;font-weight:600;color:inherit;">{str(row["대표상품명"])[:40]}</td>'
                      f'<td style="color:inherit;">{row.get("대표브랜드","")}</td>'
                      f'<td style="color:inherit;">₩{int(row["평균최저가"]):,}</td>'
                      f'<td style="color:inherit;">{row["상품수"]}</td>'
                      f'<td style="font-weight:700;color:#34D399;">{row["순위점수"]}</td></tr>')
        st.markdown(f'<div style="overflow-x:auto;border-radius:10px;border:1px solid rgba(128,128,128,0.2);"><table class="trend-table"><thead><tr><th>#</th><th>제품군</th><th>브랜드</th><th>평균가</th><th>상품수</th><th>종합점수</th></tr></thead><tbody>{trows}</tbody></table></div>', unsafe_allow_html=True)

        st.markdown("---")
        c1, c2 = st.columns([1.05, 1.2])
        with c1:
            if flavor_stats is not None and len(flavor_stats)>0:
                st.markdown('<div class="section-title st-green">🍋 플레이버 통계</div>', unsafe_allow_html=True)
                st.dataframe(flavor_stats, use_container_width=True, hide_index=True)
        with c2:
            if flavor_stats is not None and len(flavor_stats)>0:
                top_f = flavor_stats.head(10).iloc[::-1]
                fig = go.Figure(go.Bar(
                    x=top_f["빈도"], y=top_f["태그"], orientation="h",
                    marker_color="#10B981"
                ))
                fig.update_layout(height=340, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font=dict(color=None), margin=dict(l=10,r=10,t=20,b=10),
                                  xaxis=dict(gridcolor="rgba(128,128,128,0.2)"), yaxis=dict(gridcolor="rgba(128,128,128,0.2)"))
                st.plotly_chart(fig, use_container_width=True)

        c3, c4 = st.columns([1.05, 1.2])
        with c3:
            if trend_stats is not None and len(trend_stats)>0:
                st.markdown('<div class="section-title st-blue">💡 트렌드 통계</div>', unsafe_allow_html=True)
                st.dataframe(trend_stats, use_container_width=True, hide_index=True)
        with c4:
            if trend_stats is not None and len(trend_stats)>0:
                top_t = trend_stats.head(10).iloc[::-1]
                fig2 = go.Figure(go.Bar(
                    x=top_t["빈도"], y=top_t["태그"], orientation="h",
                    marker_color="#3B82F6"
                ))
                fig2.update_layout(height=340, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                   font=dict(color=None), margin=dict(l=10,r=10,t=20,b=10),
                                   xaxis=dict(gridcolor="rgba(128,128,128,0.2)"), yaxis=dict(gridcolor="rgba(128,128,128,0.2)"))
                st.plotly_chart(fig2, use_container_width=True)

        # 가격 분포
        st.markdown("---")
        st.markdown('<div class="section-title st-purple">💰 가격대 분포</div>', unsafe_allow_html=True)
        ps = agg_df["평균최저가"].replace(0, np.nan).dropna()
        if len(ps)>0:
            fig3 = go.Figure(go.Histogram(x=ps, nbinsx=15, marker_color="#A855F7"))
            fig3.update_layout(height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               font=dict(color=None), margin=dict(l=10,r=10,t=10,b=10),
                               xaxis=dict(gridcolor="rgba(128,128,128,0.2)"), yaxis=dict(gridcolor="rgba(128,128,128,0.2)"))
            st.plotly_chart(fig3, use_container_width=True)

        st.markdown("---")
        col_l, col_r = st.columns([6,4])

        with col_l:
            st.markdown('<div class="section-title st-green">📋 중복 통합 제품 목록</div>', unsafe_allow_html=True)
            product_labels = [
                f"[{i+1}] {r['대표상품명'][:30]} | ₩{int(r['평균최저가']):,}"
                for i, (_, r) in enumerate(agg_df.iterrows())
            ]
            if product_labels:
                sel_idx = st.selectbox(
                    "🔍 제품 선택 → 우측 상세",
                    range(len(product_labels)),
                    index=min(st.session_state.n_detail_idx, len(product_labels)-1),
                    format_func=lambda i: product_labels[i], key="n_detail_sel"
                )
                st.session_state.n_detail_idx = sel_idx

            render_naver_product_table(agg_df)

            d1b, d2b = st.columns(2)
            with d1b:
                st.download_button("📥 CSV",  agg_df.to_csv(index=False).encode("utf-8-sig"),
                                   f"naver_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", type="primary", key="n_csv")
            with d2b:
                st.download_button("📥 엑셀", to_excel(agg_df),
                                   f"naver_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", type="secondary", key="n_xls")

        with col_r:
            st.markdown('<div class="section-title st-green">📦 상품 상세</div>', unsafe_allow_html=True)
            if len(agg_df)>0:
                row = agg_df.iloc[st.session_state.n_detail_idx]
                img    = row.get("대표이미지","")
                name   = row.get("대표상품명","")
                price  = int(row.get("평균최저가",0))
                flavor = ", ".join(row.get("flavor_tags",[])) if isinstance(row.get("flavor_tags",[]), list) else ""
                trends = ", ".join(row.get("trend_tags",[]))  if isinstance(row.get("trend_tags",[]),  list) else ""
                gflavor = row.get("gemini_primary_flavor","-") or "-"
                gsugar  = row.get("gemini_sugar_positioning","-") or "-"
                gpkg    = row.get("gemini_package_format","-") or "-"
                st.markdown(
                    f'<div class="detail-panel">'
                    f'<div class="detail-header naver"><h3>📦 {name}</h3><p>{row.get("대표판매처","")}</p></div>'
                    f'<div class="detail-body">'
                    f'<img class="detail-img" src="{img}" onerror="this.style.display=\'none\'">'
                    f'<div class="detail-price-box naver"><span class="detail-price-big">₩{price:,}</span></div>'
                    f'<div class="detail-info-grid">'
                    f'<span class="detail-info-label">브랜드</span><span class="detail-info-value">{row.get("대표브랜드","-") or "-"}</span>'
                    f'<span class="detail-info-label">제조사</span><span class="detail-info-value">{row.get("대표제조사","-") or "-"}</span>'
                    f'<span class="detail-info-label">중복수</span><span class="detail-info-value">{int(row.get("상품수",0))}</span>'
                    f'<span class="detail-info-label">주요플레이버</span><span class="detail-info-value">{gflavor}</span>'
                    f'<span class="detail-info-label">당 포지션</span><span class="detail-info-value">{gsugar}</span>'
                    f'<span class="detail-info-label">패키지</span><span class="detail-info-value">{gpkg}</span>'
                    f'<span class="detail-info-label">Flavor 태그</span><span class="detail-info-value">{flavor or "-"}</span>'
                    f'<span class="detail-info-label">Trend 태그</span><span class="detail-info-value">{trends or "-"}</span>'
                    f'</div></div></div>',
                    unsafe_allow_html=True
                )
                st.markdown(f'<div style="text-align:center;margin-top:12px;"><a href="{row["대표링크"]}" target="_blank" style="display:inline-block;padding:10px 24px;background:linear-gradient(135deg,#059669,#10B981);color:white;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">🔗 쇼핑몰에서 보기</a></div>', unsafe_allow_html=True)

        # Gemini 보고서
        if report_text:
            st.markdown("---")
            st.markdown(f'<div class="ai-box"><h3>✨ Gemini 분석 보고서</h3><div class="ai-content">{report_text}</div></div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════
    # ⚡ 비교 분석 모드
    # ══════════════════════════════════════════════════════
    else:
        if btn_collect:
            q_a = build_naver_query(cmp_bev_a, cmp_brand_a)
            q_b = build_naver_query(cmp_bev_b, cmp_brand_b)
            label_a = cmp_bev_a or "전체음료"
            label_b = cmp_bev_b or "전체음료"
            if cmp_brand_a: label_a += f" / {cmp_brand_a}"
            if cmp_brand_b: label_b += f" / {cmp_brand_b}"

            col_prog1, col_prog2 = st.columns(2)
            with col_prog1:
                with st.spinner(f"🔍 A: '{q_a}' 수집 중…"):
                    raw_a = collect_naver_products(q_a, n_id, n_sec, cmp_sort, cmp_limit)
                    agg_a = aggregate_duplicates(raw_a)
                    agg_a = enrich_tags(agg_a)
            with col_prog2:
                with st.spinner(f"🔍 B: '{q_b}' 수집 중…"):
                    raw_b = collect_naver_products(q_b, n_id, n_sec, cmp_sort, cmp_limit)
                    agg_b = aggregate_duplicates(raw_b)
                    agg_b = enrich_tags(agg_b)

            st.session_state.cmp_agg_a    = agg_a
            st.session_state.cmp_agg_b    = agg_b
            st.session_state.cmp_label_a  = label_a
            st.session_state.cmp_label_b  = label_b
            st.session_state.cmp_collected = True
            st.success(f"✅ 수집 완료 | A: {len(agg_a)}개 제품군 / B: {len(agg_b)}개 제품군")

        agg_a   = st.session_state.cmp_agg_a
        agg_b   = st.session_state.cmp_agg_b
        label_a = st.session_state.cmp_label_a
        label_b = st.session_state.cmp_label_b

        if not st.session_state.cmp_collected or agg_a is None:
            st.markdown('<div style="text-align:center;padding:60px;color:#6B7280;"><div style="font-size:48px;">⚡</div><div style="font-size:18px;font-weight:600;color:#34D399;">A / B 카테고리를 설정하고 수집 실행하세요</div></div>', unsafe_allow_html=True)
            return

        # ── 비교 요약 메트릭 ──
        st.markdown(f'<div style="display:flex;gap:16px;margin-bottom:8px;"><span class="compare-label-a">🔵 A: {label_a}</span><span class="compare-label-b">🟢 B: {label_b}</span></div>', unsafe_allow_html=True)

        ca1, ca2, cb1, cb2 = st.columns(4)
        avg_a = agg_a["평균최저가"].mean() if len(agg_a)>0 else 0
        avg_b = agg_b["평균최저가"].mean() if len(agg_b)>0 else 0
        ca1.metric(f"🔵 A 제품군 수",   f"{len(agg_a):,}")
        ca2.metric(f"🔵 A 평균최저가",  f"₩{avg_a:,.0f}")
        cb1.metric(f"🟢 B 제품군 수",   f"{len(agg_b):,}")
        cb2.metric(f"🟢 B 평균최저가",  f"₩{avg_b:,.0f}")

        st.markdown("---")

        # ── 플레이버 비교 차트 ──
        render_flavor_compare(agg_a, agg_b, label_a, label_b)

        st.markdown("---")

        # ── 트렌드 히트맵 ──
        render_trend_heatmap(agg_a, agg_b, label_a, label_b)

        st.markdown("---")

        # ── 가격대 비교 ──
        render_price_compare(agg_a, agg_b, label_a, label_b)

        st.markdown("---")

        # ── 제품 목록 A / B 탭 ──
        st.markdown('<div class="section-title st-green">📋 제품 목록 비교</div>', unsafe_allow_html=True)
        tab_a, tab_b = st.tabs([f"🔵 A: {label_a}", f"🟢 B: {label_b}"])
        with tab_a:
            render_naver_product_table(agg_a)
            st.download_button("📥 A CSV", agg_a.to_csv(index=False).encode("utf-8-sig"),
                               f"naver_A_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", key="cmp_dl_a")
        with tab_b:
            render_naver_product_table(agg_b)
            st.download_button("📥 B CSV", agg_b.to_csv(index=False).encode("utf-8-sig"),
                               f"naver_B_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", key="cmp_dl_b")


# ============================================================
# 메인
# ============================================================
def main():
    t1, t2 = st.tabs(["🟣 마켓컬리 신제품", "🟢 네이버 쇼핑"])
    with t1:
        tab_kurly()
    with t2:
        tab_naver()

if __name__ == "__main__":
    main()
