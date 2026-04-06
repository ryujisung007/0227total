"""
품목제조보고 조회 — HTTPS 우선 + HTTP fallback
"""
import streamlit as st
import requests
import pandas as pd
import time
import urllib.parse

BASE_URLS  = [
    "https://openapi.foodsafetykorea.go.kr/api",   # Cloud용
    "http://openapi.foodsafetykorea.go.kr/api",     # Colab/로컬용
]
SERVICE_ID = "I1250"
PAGE_SIZE  = 1000

DRINK_TYPES = [
    "과.채주스", "과.채음료", "농축과.채즙",
    "탄산음료", "탄산수",
    "두유", "가공두유", "원액두유",
    "인삼.홍삼음료", "혼합음료", "유산균음료",
    "음료베이스", "효모음료",
    "커피", "침출차", "고형차", "액상차",
]

COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형",
    "BSSH_NM": "제조사", "PRMS_DT": "보고일자",
    "RAWMTRL_NM": "주요원재료", "POG_DAYCNT": "유통기한",
    "PRODUCTION": "생산종료", "LAST_UPDT_DTM": "최종수정일",
    "PRDLST_REPORT_NO": "품목제조번호",
}


# ── 작동하는 BASE URL 찾기 (최초 1회) ──
def find_working_base(api_key):
    if "working_base" in st.session_state:
        return st.session_state["working_base"]
    for base in BASE_URLS:
        url = f"{base}/{api_key}/{SERVICE_ID}/json/1/1"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                st.session_state["working_base"] = base
                return base
        except Exception:
            continue
    return BASE_URLS[0]


# ── API 호출 — Colab 로직 그대로 ──
def fetch_data(api_key, food_type, max_rows, log):
    base = find_working_base(api_key)
    encoded_type = urllib.parse.quote(food_type, safe=".")
    all_rows = []
    start = 1

    while start <= max_rows:
        end = min(start + PAGE_SIZE - 1, max_rows)
        url = f"{base}/{api_key}/{SERVICE_ID}/json/{start}/{end}/PRDLST_DCNM={encoded_type}"

        log.write(f"📡 요청 중… {start}~{end}건 ({base.split('://')[0]}) ")

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            log.write("⏰ 타임아웃! 재시도…\n")
            time.sleep(1)
            continue
        except (requests.exceptions.RequestException, ValueError) as e:
            log.write(f"❌ 요청 실패: {e}\n")
            break

        body   = data.get(SERVICE_ID, {})
        result = body.get("RESULT", {})
        code   = result.get("CODE", "")
        msg    = result.get("MSG", "")

        if code == "INFO-300":
            log.write(f"❌ 인증키 오류: {msg}\n")
            break
        if code == "INFO-200":
            log.write(f"→ 데이터 없음 ({msg})\n")
            break
        if code != "INFO-000":
            log.write(f"→ 응답: {code} {msg}\n")
            break

        rows = body.get("row", [])
        if not rows:
            log.write("→ 빈 응답\n")
            break

        rows = [r for r in rows if r.get("PRDLST_DCNM") == food_type]
        all_rows.extend(rows)
        total = int(body.get("total_count", "0"))
        log.write(f"✅ {len(rows)}건 (전체 {total}건)\n")

        if end >= total or end >= max_rows:
            break
        start = end + 1
        time.sleep(0.2)

    return all_rows


# ── UI ──
st.title("🏭 품목제조보고 조회")

with st.sidebar:
    st.markdown("### 설정")
    api_key   = st.text_input("🔑 API 키", type="password",
                              help="식품안전나라에서 발급")
    food_type = st.selectbox("🍹 식품유형", DRINK_TYPES)
    max_rows  = st.slider("조회 건수", 10, 500, 200, step=10)
    st.markdown("---")
    run = st.button("🚀 조회 실행", type="primary", use_container_width=True)
    if st.button("🔄 연결 초기화"):
        st.session_state.pop("working_base", None)
        st.success("초기화 완료")

if not api_key:
    st.info("👈 사이드바에서 API 키를 입력하세요.\n\n"
            "🔗 [키 발급](https://www.foodsafetykorea.go.kr/api/openApiInfo.do)"
            " → 서비스: **I1250** 신청")
    st.stop()

if run:
    class Log:
        def __init__(self):
            self.lines = []
            self.box = st.empty()
        def write(self, msg):
            self.lines.append(msg)
            self.box.code("".join(self.lines))

    log = Log()
    t0 = time.time()
    rows = fetch_data(api_key, food_type, max_rows, log)
    elapsed = time.time() - t0

    if not rows:
        st.error("😢 조회 결과가 없습니다. API 키와 유형명을 확인하세요.")
        st.stop()

    df = pd.DataFrame(rows)
    use_cols = [c for c in COL_MAP if c in df.columns]
    df = df[use_cols].rename(columns=COL_MAP)
    if "최종수정일" in df.columns:
        df = df.sort_values("최종수정일", ascending=False).reset_index(drop=True)

    st.success(f"✅ **{len(df)}건** 수집 ({elapsed:.1f}초)")
    c1, c2, c3 = st.columns(3)
    c1.metric("조회 건수", f"{len(df)}건")
    if "제조사" in df.columns:
        c2.metric("제조사 수", f"{df['제조사'].nunique()}곳")
    if "보고일자" in df.columns:
        dates = df["보고일자"].dropna().astype(str)
        if len(dates):
            c3.metric("최신 보고일", dates.max())

    st.markdown("---")
    show = [c for c in ["제품명","제조사","보고일자","주요원재료","유통기한","생산종료"]
            if c in df.columns]
    st.dataframe(df[show], use_container_width=True, height=500)

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV 다운로드", csv,
                       f"{food_type}_{time.strftime('%Y%m%d')}.csv",
                       "text/csv", use_container_width=True)
