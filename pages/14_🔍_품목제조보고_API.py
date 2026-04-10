"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HTTP 우선 (필터 정상) → HTTPS fallback (대량수집+클라이언트필터)
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


def _normalize(s):
    return s.strip().replace("·", ".").replace("‧", ".").replace(" ", "")


def api_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def detect_mode(api_key):
    """HTTP(필터정상) vs HTTPS(필터무시) 감지"""
    if "api_mode" in st.session_state:
        return st.session_state["api_mode"]

    test_enc = urllib.parse.quote("탄산음료")

    # 1차: HTTP (Colab과 동일, 필터 정상 작동)
    try:
        url = f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I1250/json/1/3/PRDLST_DCNM={test_enc}"
        data = api_get(url, timeout=15)
        rows = data.get("I1250", {}).get("row", [])
        if rows and rows[0].get("PRDLST_DCNM") == "탄산음료":
            st.session_state["api_mode"] = "http_filtered"
            return "http_filtered"
    except Exception:
        pass

    # 2차: HTTPS (필터 안 먹히지만 연결은 됨)
    try:
        url = f"https://openapi.foodsafetykorea.go.kr/api/{api_key}/I1250/json/1/3/PRDLST_DCNM={test_enc}"
        data = api_get(url, timeout=15)
        if data.get("I1250", {}).get("row"):
            st.session_state["api_mode"] = "https_unfiltered"
            return "https_unfiltered"
    except Exception:
        pass

    st.session_state["api_mode"] = "failed"
    return "failed"


def fetch_http_filtered(api_key, food_type, max_rows, log):
    """HTTP 모드: 서버 필터 작동 → 효율적"""
    base = "http://openapi.foodsafetykorea.go.kr/api"
    encoded_type = urllib.parse.quote(food_type, safe=".")
    norm = _normalize(food_type)
    all_data = []
    start = 1

    while start <= max_rows:
        end = min(start + 499, max_rows)
        url = f"{base}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded_type}"
        try:
            data = api_get(url, timeout=20)
            svc = data.get("I1250", {})
            if svc.get("RESULT", {}).get("CODE") != "INFO-000":
                break
            rows = svc.get("row", [])
            matched = [r for r in rows if _normalize(r.get("PRDLST_DCNM", "")) == norm]
            all_data.extend(matched)
            total = svc.get("total_count", "0")
            log(f"📦 {start}~{end} → {len(matched)}건 (누적: {len(all_data)} / DB: {total})")
            if len(rows) < (end - start + 1):
                break
            start += 500
            time.sleep(0.2)
        except Exception as e:
            log(f"⚠️ {e}")
            break
    return all_data


def fetch_https_unfiltered(api_key, food_type, max_rows, log):
    """HTTPS 모드: 서버 필터 무시 → 대량수집 + 클라이언트 필터"""
    base = "https://openapi.foodsafetykorea.go.kr/api"
    encoded_type = urllib.parse.quote(food_type, safe=".")
    norm = _normalize(food_type)
    all_data = []
    start = 1
    page_size = 1000  # 대량으로 가져와서 필터
    max_fetch = max_rows * 20  # 최대 탐색 범위 (20배)
    scanned = 0

    while len(all_data) < max_rows and start <= max_fetch:
        end = min(start + page_size - 1, max_fetch)
        url = f"{base}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded_type}"
        try:
            data = api_get(url, timeout=20)
            svc = data.get("I1250", {})
            if svc.get("RESULT", {}).get("CODE") != "INFO-000":
                break
            rows = svc.get("row", [])
            if not rows:
                break
            matched = [r for r in rows if _normalize(r.get("PRDLST_DCNM", "")) == norm]
            all_data.extend(matched)
            scanned += len(rows)
            total = svc.get("total_count", "0")
            log(f"📦 {start}~{end} → {len(matched)}건 일치 / {len(rows)}건 스캔 "
                f"(누적: {len(all_data)} / 스캔: {scanned})")
            if len(rows) < page_size:
                break
            start += page_size
            time.sleep(0.3)
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
    max_rows  = st.slider("최대 수집 건수", 10, 500, 200, step=10)
    st.markdown("---")
    run = st.button("🚀 조회 시작", type="primary", use_container_width=True)
    if st.button("🔄 연결 초기화"):
        st.session_state.pop("api_mode", None)
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

    mode = detect_mode(api_key)

    if mode == "http_filtered":
        log("🌐 HTTP 모드 (서버 필터 정상)")
        t0 = time.time()
        raw_rows = fetch_http_filtered(api_key, food_type, max_rows, log)
    elif mode == "https_unfiltered":
        log("🔒 HTTPS 모드 (클라이언트 필터링 — 시간이 더 걸릴 수 있습니다)")
        t0 = time.time()
        raw_rows = fetch_https_unfiltered(api_key, food_type, max_rows, log)
    else:
        st.error("❌ API 서버에 연결할 수 없습니다.\n\n"
                 "Google Colab에서 데이터를 수집한 뒤 CSV로 업로드하세요.")
        st.stop()

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
