"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
마침표 인코딩 자동 전환 (safe="." → safe="" fallback)
HTTPS 필터 미작동 시 대량 수집 + 클라이언트 필터
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
    "http://openapi.foodsafetykorea.go.kr/api",
    "https://openapi.foodsafetykorea.go.kr/api",
]


def _normalize(s):
    return s.strip().replace("·", ".").replace("‧", ".").replace(" ", "")


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_working_base(api_key):
    if "working_base" in st.session_state:
        return st.session_state["working_base"]

    test_enc = urllib.parse.quote("탄산음료")
    for base in BASE_URLS:
        url = f"{base}/{api_key}/I1250/json/1/3/PRDLST_DCNM={test_enc}"
        try:
            data = api_get(url, timeout=15)
            svc = data.get("I1250", {})
            rows = svc.get("row", [])
            if rows and rows[0].get("PRDLST_DCNM") == "탄산음료":
                st.session_state["working_base"] = base
                return base
        except Exception:
            continue

    st.session_state["working_base"] = BASE_URLS[0]
    return BASE_URLS[0]


def _fetch_page(base_url, api_key, encoded_type, start, end):
    """한 페이지 호출"""
    url = f"{base_url}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded_type}"
    data = api_get(url, timeout=20)
    svc = data.get("I1250")
    if not svc:
        return [], "0", data.get("RESULT", {}).get("CODE", "?")
    return svc.get("row", []), svc.get("total_count", "0"), svc.get("RESULT", {}).get("CODE", "")


def fetch_data(api_key, food_type, max_rows, log):
    base_url = find_working_base(api_key)
    norm_target = _normalize(food_type)
    proto = base_url.split("://")[0]
    log(f"🚀 {food_type} 수집 시작 (프로토콜: {proto})")

    # 마침표 인코딩 2가지 시도
    encodings = []
    if "." in food_type:
        encodings = [
            ("마침표 유지", urllib.parse.quote(food_type, safe=".")),
            ("마침표 인코딩", urllib.parse.quote(food_type, safe="")),
        ]
    else:
        encodings = [
            ("기본", urllib.parse.quote(food_type, safe=".")),
        ]

    for enc_name, encoded_type in encodings:
        log(f"🔤 인코딩 방식: {enc_name}")

        all_data = []
        start_idx = 1
        page_size = 500
        retry_count = 0

        while start_idx <= max_rows:
            end_idx = min(start_idx + page_size - 1, max_rows)

            try:
                raw_rows, total_count, code = _fetch_page(
                    base_url, api_key, encoded_type, start_idx, end_idx)

                if code == "INFO-300":
                    log("❌ 인증키 오류")
                    return []
                if code == "INFO-200" or not raw_rows:
                    log("ℹ️ 데이터 없음")
                    break
                if code != "INFO-000":
                    log(f"❌ API 오류: {code}")
                    break

                matched = [r for r in raw_rows
                           if _normalize(r.get("PRDLST_DCNM", "")) == norm_target]
                all_data.extend(matched)

                log(f"📦 {start_idx}~{end_idx} → {len(matched)}/{len(raw_rows)}건 "
                    f"(누적: {len(all_data)} / DB: {total_count})")

                if len(raw_rows) < (end_idx - start_idx + 1):
                    break
                start_idx += page_size
                time.sleep(0.2)

            except TimeoutError:
                retry_count += 1
                if retry_count > 2:
                    log("⏰ 타임아웃 3회 — 중단")
                    break
                log(f"⏰ 타임아웃 — 재시도 ({retry_count}/3)…")
                time.sleep(1)
                continue
            except Exception as e:
                log(f"⚠️ {type(e).__name__}: {e}")
                break

        if all_data:
            log(f"✅ '{enc_name}' 방식으로 {len(all_data)}건 수집 성공!")
            return all_data
        else:
            log(f"⚠️ '{enc_name}' 방식 0건 — 다음 방식 시도")

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
        st.error("❌ 수집된 데이터가 없습니다.")
        st.info("**원인 가능성:**\n"
                "1. API 키 만료 → [재발급](https://www.foodsafetykorea.go.kr/api/openApiInfo.do)\n"
                "2. 해당 유형 데이터 없음\n"
                "3. Streamlit Cloud ↔ API 서버 통신 문제")
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

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV", csv,
                       f"{food_type.replace('.','_')}_{datetime.now():%Y%m%d_%H%M}.csv",
                       "text/csv", use_container_width=True)
