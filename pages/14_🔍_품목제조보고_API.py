"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
마침표 포함 유형은 뒷부분으로 검색 → 클라이언트 정확 매칭
예: 과.채주스 → "채주스"로 API 호출 → PRDLST_DCNM=="과.채주스" 필터
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


def _search_term(food_type):
    """API 검색어 생성 — 마침표 포함 시 뒷부분만 사용
    과.채주스 → 채주스 / 인삼.홍삼음료 → 홍삼음료 / 탄산음료 → 탄산음료
    """
    if "." in food_type:
        return food_type.split(".")[-1]   # 마지막 마침표 뒤
    return food_type


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
            url = f"{base}/{api_key}/I1250/json/1/1"
            data = api_get(url, timeout=15)
            if data.get("I1250", {}).get("RESULT", {}).get("CODE") == "INFO-000":
                st.session_state["working_base"] = base
                return base
        except Exception:
            continue
    st.session_state["working_base"] = BASE_URLS[0]
    return BASE_URLS[0]


def fetch_data(api_key, food_type, max_rows, log):
    base_url = find_working_base(api_key)
    proto = base_url.split("://")[0]

    # 검색어: 마침표 있으면 뒷부분만
    search = _search_term(food_type)
    encoded = urllib.parse.quote(search)
    norm_target = _normalize(food_type)

    if search != food_type:
        log(f"🚀 {food_type} → '{search}'로 검색 후 필터링 ({proto})")
    else:
        log(f"🚀 {food_type} 수집 시작 ({proto})")

    all_data = []
    start = 1
    page_size = 500

    while start <= max_rows and len(all_data) < max_rows:
        end = min(start + page_size - 1, max_rows)
        url = f"{base_url}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded}"

        try:
            data = api_get(url, timeout=20)
            svc = data.get("I1250", {})
            code = svc.get("RESULT", {}).get("CODE", "")

            if code == "INFO-300":
                log("❌ 인증키 오류"); break
            if code == "INFO-200" or code != "INFO-000":
                log(f"ℹ️ 응답: {code}"); break

            rows = svc.get("row", [])
            if not rows:
                break
            total = svc.get("total_count", "0")

            # 정확 매칭 필터
            matched = [r for r in rows
                       if _normalize(r.get("PRDLST_DCNM", "")) == norm_target]
            all_data.extend(matched)

            log(f"📦 {start}~{end} → {len(matched)}/{len(rows)}건 일치 "
                f"(누적: {len(all_data)} / DB: {total})")

            if len(rows) < page_size:
                break
            start += page_size
            time.sleep(0.2)

        except TimeoutError:
            log("⏰ 타임아웃 — 재시도")
            time.sleep(1)
            continue
        except Exception as e:
            log(f"⚠️ {e}")
            break

    return all_data[:max_rows]


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
