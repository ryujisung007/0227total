"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
프로토콜 자동 감지: 필터 작동 여부까지 검증
HTTP 우선 (Colab과 동일) → HTTPS fallback
"""
import streamlit as st
import requests
import pandas as pd
import time
import urllib.parse
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

# HTTP 먼저 (Colab과 동일하게 작동), HTTPS fallback
BASE_URLS = [
    "http://openapi.foodsafetykorea.go.kr/api",
    "https://openapi.foodsafetykorea.go.kr/api",
]


def _normalize(s):
    return s.strip().replace("·", ".").replace("‧", ".").replace(" ", "")


def find_working_base(api_key):
    """필터가 실제로 작동하는 프로토콜 찾기"""
    if "working_base" in st.session_state:
        return st.session_state["working_base"]

    # "탄산음료"로 테스트 (마침표 없는 확실한 유형)
    test_type = urllib.parse.quote("탄산음료")

    for base in BASE_URLS:
        url = f"{base}/{api_key}/I1250/json/1/3/PRDLST_DCNM={test_type}"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            svc = data.get("I1250", {})
            if svc.get("RESULT", {}).get("CODE") != "INFO-000":
                continue
            # 핵심: 반환된 데이터가 실제로 "탄산음료"인지 확인
            rows = svc.get("row", [])
            if rows and rows[0].get("PRDLST_DCNM") == "탄산음료":
                st.session_state["working_base"] = base
                return base
        except Exception:
            continue

    # 둘 다 안 되면 HTTP (Colab 기본)
    st.session_state["working_base"] = BASE_URLS[0]
    return BASE_URLS[0]


def fetch_food_safety_data(api_key, food_type, max_rows, log):
    base_url = find_working_base(api_key)
    all_data = []
    start_idx = 1
    page_size = 500
    encoded_type = urllib.parse.quote(food_type, safe=".")
    norm_target = _normalize(food_type)

    proto = base_url.split("://")[0]
    log(f"🚀 {food_type} 수집 시작 (프로토콜: {proto})")

    while start_idx <= max_rows:
        end_idx = min(start_idx + page_size - 1, max_rows)
        url = f"{base_url}/{api_key}/I1250/json/{start_idx}/{end_idx}/PRDLST_DCNM={encoded_type}"

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            service_data = data.get("I1250")
            if not service_data:
                res_code = data.get("RESULT", {}).get("CODE")
                if res_code == "INFO-200":
                    log("ℹ️ 데이터 없음")
                else:
                    log(f"❌ API 오류: {data.get('RESULT', {}).get('MSG')}")
                break

            raw_rows = service_data.get("row", [])
            total_count = service_data.get("total_count", "0")

            # 식품유형 정규화 매칭
            matched = [r for r in raw_rows
                       if _normalize(r.get("PRDLST_DCNM", "")) == norm_target]
            all_data.extend(matched)

            log(f"📦 {start_idx}~{end_idx} → {len(matched)}/{len(raw_rows)}건 일치 "
                f"(누적: {len(all_data)} / DB: {total_count})")

            if len(raw_rows) < (end_idx - start_idx + 1):
                break

            start_idx += page_size
            time.sleep(0.2)

        except requests.exceptions.Timeout:
            log(f"⏰ 타임아웃 — 재시도…")
            time.sleep(1)
            continue
        except Exception as e:
            log(f"⚠️ 오류: {e}")
            break

    return all_data


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
        st.success("완료 — 다시 조회하면 프로토콜 재감지합니다")

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
    raw_rows = fetch_food_safety_data(api_key, food_type, max_rows, log)
    elapsed = time.time() - t0

    if not raw_rows:
        st.error("❌ 수집된 데이터가 없습니다. API 키와 식품유형을 확인하세요.")
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
