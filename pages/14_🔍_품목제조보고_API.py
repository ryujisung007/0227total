"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Colab 스크립트 → Streamlit 전환 (API 로직 동일)
HTTPS 우선 → HTTP fallback 자동 감지
"""
import streamlit as st
import requests
import pandas as pd
import time
import urllib.parse
from datetime import datetime

# ── 상수 (Colab 원본과 동일) ──
DRINK_TYPES = [
    "과.채주스", "과.채음료", "농축과.채즙", "탄산음료", "탄산수",
    "두유", "가공두유", "원액두유", "인삼.홍삼음료", "혼합음료",
    "유산균음료", "음료베이스", "효모음료", "커피", "침출차", "고형차", "액상차",
]

COL_MAP = {
    "PRDLST_NM": "제품명",
    "PRDLST_DCNM": "식품유형",
    "BSSH_NM": "제조사",
    "PRMS_DT": "보고일자",
    "RAWMTRL_NM": "주요원재료",
    "POG_DAYCNT": "유통기한",
    "PRODUCTION": "생산종료",
    "LAST_UPDT_DTM": "최종수정일",
    "PRDLST_REPORT_NO": "품목제조번호",
}

# HTTPS 우선 (Streamlit Cloud), HTTP fallback (Colab/로컬)
BASE_URLS = [
    "https://openapi.foodsafetykorea.go.kr/api",
    "http://openapi.foodsafetykorea.go.kr/api",
]


# ── 작동하는 프로토콜 자동 감지 (최초 1회) ──
def find_working_base(api_key):
    if "working_base" in st.session_state:
        return st.session_state["working_base"]
    for base in BASE_URLS:
        test_url = f"{base}/{api_key}/I1250/json/1/1"
        try:
            r = requests.get(test_url, timeout=10)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                st.session_state["working_base"] = base
                return base
        except Exception:
            continue
    # 기본값
    st.session_state["working_base"] = BASE_URLS[0]
    return BASE_URLS[0]


# ── 데이터 수집 (Colab 원본 fetch_food_safety_data 그대로) ──
def fetch_food_safety_data(api_key, food_type, max_rows, log):
    base_url = find_working_base(api_key)
    all_data = []
    start_idx = 1
    page_size = 500  # 원본과 동일: 안정적 수집 위해 500건씩

    # 한글 유형명 인코딩 (마침표는 안전하게 처리)
    encoded_type = urllib.parse.quote(food_type, safe=".")

    proto = base_url.split("://")[0]
    log(f"🚀 {food_type} 데이터 수집 시작… (프로토콜: {proto})")

    while start_idx <= max_rows:
        end_idx = min(start_idx + page_size - 1, max_rows)

        url = f"{base_url}/{api_key}/I1250/json/{start_idx}/{end_idx}/PRDLST_DCNM={encoded_type}"

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            # 응답 결과 확인
            service_data = data.get("I1250")
            if not service_data:
                res_code = data.get("RESULT", {}).get("CODE")
                if res_code == "INFO-200":
                    log("ℹ️ 해당 조건의 데이터가 더 이상 없습니다.")
                else:
                    log(f"❌ API 서버 오류: {data.get('RESULT', {}).get('MSG')}")
                break

            rows = service_data.get("row", [])
            all_data.extend(rows)

            total_count = service_data.get("total_count", "0")
            log(f"📦 {start_idx}~{end_idx} 수집 완료 (누적: {len(all_data)} / 전체: {total_count})")

            if len(rows) < (end_idx - start_idx + 1):
                break  # 마지막 페이지 도달

            start_idx += page_size
            time.sleep(0.2)  # 서버 부하 방지

        except requests.exceptions.Timeout:
            log(f"⏰ {start_idx}~{end_idx} 타임아웃 — 재시도…")
            time.sleep(1)
            continue
        except Exception as e:
            log(f"⚠️ 요청 중 오류: {e}")
            break

    return all_data


# ══════════════════════════════════════════════════════
#  Streamlit UI
# ══════════════════════════════════════════════════════
st.title("🥤 음료 품목제조보고 조회")

with st.sidebar:
    st.markdown("### 🔑 API 키")
    api_key = st.text_input(
        "식품안전나라 API 키", type="password",
        help="https://www.foodsafetykorea.go.kr/api/openApiInfo.do → I1250 신청")

    st.markdown("### 🍹 조회 설정")
    food_type = st.selectbox("식품유형", DRINK_TYPES)
    max_rows  = st.slider("최대 수집 건수", 10, 1000, 200, step=10)

    st.markdown("---")
    run = st.button("🚀 조회 시작", type="primary", use_container_width=True)

    if st.button("🔄 연결 초기화"):
        st.session_state.pop("working_base", None)
        st.success("프로토콜 캐시 초기화 완료")

if not api_key:
    st.info(
        "👈 사이드바에서 **API 키**를 입력하세요.\n\n"
        "**발급 방법:**\n"
        "1. [식품안전나라](https://www.foodsafetykorea.go.kr/api/openApiInfo.do) 접속\n"
        "2. 서비스: **품목제조보고(심사) [I1250]** 신청\n"
        "3. 발급받은 키를 왼쪽에 입력"
    )
    st.stop()

if run:
    # 로그 영역
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

    # ── DataFrame 처리 (Colab 원본과 동일) ──
    df = pd.DataFrame(raw_rows)

    # 컬럼 선별 및 한글화
    avail = [c for c in COL_MAP if c in df.columns]
    df = df[avail].rename(columns=COL_MAP)

    # 보고일자 기준 내림차순 정렬 (최신순)
    if "보고일자" in df.columns:
        df = df.sort_values(by="보고일자", ascending=False).reset_index(drop=True)

    # ── 결과 출력 ──
    st.success(f"✅ 데이터 수집 완료! ({elapsed:.1f}초)")

    c1, c2, c3 = st.columns(3)
    c1.metric("📊 총 수집 건수", f"{len(df)}건")
    if "제조사" in df.columns:
        c2.metric("🏢 제조사 수", f"{df['제조사'].nunique()}개소")
    if "보고일자" in df.columns:
        c3.metric("📅 최근 보고일", df["보고일자"].max())

    # 미리보기 (상위 10건)
    st.markdown("---")
    st.markdown("### 📋 상위 10건 미리보기")
    preview = [c for c in ["제품명", "제조사", "보고일자", "주요원재료"] if c in df.columns]
    st.dataframe(df[preview].head(10), use_container_width=True)

    # 전체 데이터
    st.markdown("### 📊 전체 데이터")
    show = [c for c in ["제품명","식품유형","제조사","보고일자","주요원재료","유통기한","생산종료"]
            if c in df.columns]
    st.dataframe(df[show], use_container_width=True, height=500)
    st.caption(f"총 {len(df)}건")

    # CSV 다운로드
    file_name = f"{food_type.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV 다운로드", csv, file_name,
                       "text/csv", use_container_width=True)
