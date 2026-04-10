"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
마침표 유형별 검색어 직접 매핑 + 클라이언트 정확 매칭
"""
import streamlit as st
import pandas as pd
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime

DRINK_TYPES = [
    "과.채주스", "과.채음료", "농축과.채즙", "탄산음료", "탄산수",
    "두유", "가공두유", "원액두유", "인삼.홍삼음료", "혼합음료",
    "유산균음료", "음료베이스", "효모음료", "커피", "침출차", "고형차", "액상차",
]

# 마침표 포함 유형 → API 검색에 쓸 키워드 (여러 개 = 순차 시도)
SEARCH_TERMS = {
    "과.채주스":     ["채주스"],
    "과.채음료":     ["채음료"],
    "농축과.채즙":   ["농축", "채즙"],
    "인삼.홍삼음료": ["홍삼음료", "홍삼"],
}

COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형",
    "BSSH_NM": "제조사", "PRMS_DT": "보고일자",
    "RAWMTRL_NM": "주요원재료", "POG_DAYCNT": "유통기한",
    "PRODUCTION": "생산종료", "LAST_UPDT_DTM": "최종수정일",
    "PRDLST_REPORT_NO": "품목제조번호",
}

BASE_URLS = [
    "https://openapi.foodsafetykorea.go.kr/api",
    "http://openapi.foodsafetykorea.go.kr/api",
]


def _normalize(s):
    return s.strip().replace("·", ".").replace("‧", ".").replace(" ", "")


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_working_base(api_key):
    if "working_base" in st.session_state:
        return st.session_state["working_base"]
    for base in BASE_URLS:
        try:
            data = api_get(f"{base}/{api_key}/I1250/json/1/1", timeout=15)
            if data.get("I1250", {}).get("RESULT", {}).get("CODE") == "INFO-000":
                st.session_state["working_base"] = base
                return base
        except Exception:
            continue
    st.session_state["working_base"] = BASE_URLS[0]
    return BASE_URLS[0]


def _get_search_terms(food_type):
    """검색어 후보 리스트 반환"""
    if food_type in SEARCH_TERMS:
        return SEARCH_TERMS[food_type]
    if "." in food_type:
        return [food_type.split(".")[-1], food_type.replace(".", "")]
    return [food_type]


def _fetch_with_term(base_url, api_key, search_term, food_type, max_rows, log):
    """하나의 검색어로 수집 시도"""
    encoded = urllib.parse.quote(search_term)
    norm_target = _normalize(food_type)
    all_data = []
    start = 1
    page_size = 500
    retries = 0

    while start <= max_rows and len(all_data) < max_rows:
        end = min(start + page_size - 1, max_rows)
        url = f"{base_url}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded}"

        try:
            data = api_get(url, timeout=20)
            svc = data.get("I1250", {})
            code = svc.get("RESULT", {}).get("CODE", "")

            if code == "INFO-300":
                log("❌ 인증키 오류"); return []
            if code != "INFO-000" or not svc.get("row"):
                break

            rows = svc.get("row", [])
            total = svc.get("total_count", "0")
            matched = [r for r in rows
                       if _normalize(r.get("PRDLST_DCNM", "")) == norm_target]
            all_data.extend(matched)

            log(f"📦 {start}~{end} → {len(matched)}/{len(rows)}건 "
                f"(누적: {len(all_data)} / DB: {total})")

            if len(rows) < page_size:
                break
            start += page_size
            time.sleep(0.2)
            retries = 0

        except TimeoutError:
            retries += 1
            if retries > 2:
                log("⏰ 타임아웃 3회 — 중단")
                break
            log(f"⏰ 타임아웃 — 재시도 ({retries}/3)")
            time.sleep(1)
            continue
        except Exception as e:
            log(f"⚠️ {e}")
            break

    return all_data[:max_rows]


def fetch_data(api_key, food_type, max_rows, log):
    base_url = find_working_base(api_key)
    proto = base_url.split("://")[0]
    terms = _get_search_terms(food_type)

    for term in terms:
        if term != food_type:
            log(f"🚀 {food_type} → '{term}'로 검색 ({proto})")
        else:
            log(f"🚀 {food_type} 수집 시작 ({proto})")

        result = _fetch_with_term(base_url, api_key, term, food_type, max_rows, log)

        if result:
            log(f"✅ '{term}' 검색으로 {len(result)}건 수집 성공!")
            return result
        else:
            log(f"⚠️ '{term}' 검색 0건 — 다음 검색어 시도")

    return []


# ── UI ──
st.title("🥤 음료 품목제조보고 조회")

with st.sidebar:
    st.markdown("### 🔑 API 키")
    api_key = st.text_input("식품안전나라 API 키", type="password")
    st.markdown("### 🍹 조회 설정")
    food_type = st.selectbox("식품유형", DRINK_TYPES)
    max_rows  = st.slider("최대 수집 건수", 10, 1000, 200, step=10)
    st.markdown("---")
    run = st.button("🚀 조회 시작", type="primary", use_container_width=True)
    if st.button("🔄 연결 초기화"):
        st.session_state.pop("working_base", None)
        st.success("완료")

if not api_key:
    st.info("👈 사이드바에서 API 키를 입력하세요.\n\n"
            "[키 발급](https://www.foodsafetykorea.go.kr/api/openApiInfo.do) → I1250 신청")
    st.stop()

if run:
    log_box = st.empty()
    log_lines = []
    def log(msg):
        log_lines.append(msg)
        log_box.code("\n".join(log_lines))

    t0 = time.time()
    raw_rows = fetch_data(api_key, food_type, max_rows, log)
    elapsed = time.time() - t0

    if not raw_rows:
        st.error("❌ 수집된 데이터가 없습니다. API 키를 확인하세요.")
        st.stop()

    df = pd.DataFrame(raw_rows)
    avail = [c for c in COL_MAP if c in df.columns]
    df = df[avail].rename(columns=COL_MAP)
    if "보고일자" in df.columns:
        df = df.sort_values("보고일자", ascending=False).reset_index(drop=True)

    st.success(f"✅ {len(df)}건 수집 ({elapsed:.1f}초)")
    c1, c2, c3 = st.columns(3)
    c1.metric("수집 건수", f"{len(df)}건")
    if "제조사" in df.columns:
        c2.metric("제조사 수", f"{df['제조사'].nunique()}개소")
    if "보고일자" in df.columns:
        c3.metric("최근 보고일", df["보고일자"].max())

    st.markdown("---")
    show = [c for c in ["식품유형","제품명","보고일자","제조사","주요원재료","유통기한","생산종료"]
            if c in df.columns]
    st.dataframe(df[show], use_container_width=True, height=500)
    st.caption(f"총 {len(df)}건")

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV", csv,
                       f"{food_type.replace('.','_')}_{datetime.now():%Y%m%d_%H%M}.csv",
                       "text/csv", use_container_width=True)
