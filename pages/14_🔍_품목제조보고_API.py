"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3단계 연결 시도:
 ① requests HTTP (trust_env=False)
 ② urllib HTTP
 ③ urllib HTTPS
필터 검증 + 마침표 인코딩 자동 전환
"""
import streamlit as st
import requests as req_lib
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


# ══════════════════════════════════════════════════════
#  3가지 HTTP 호출 방법
# ══════════════════════════════════════════════════════
def _call_requests_http(url):
    """① requests + HTTP + trust_env=False"""
    s = req_lib.Session()
    s.trust_env = False
    r = s.get(url, timeout=(10, 20),
              proxies={"http": None, "https": None},
              headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def _call_urllib(url):
    """② ③ urllib (HTTP 또는 HTTPS)"""
    r = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


# 사용할 메서드 목록
METHODS = [
    ("requests-http",  "http://openapi.foodsafetykorea.go.kr/api",  _call_requests_http),
    ("urllib-http",    "http://openapi.foodsafetykorea.go.kr/api",  _call_urllib),
    ("urllib-https",   "https://openapi.foodsafetykorea.go.kr/api", _call_urllib),
]


def find_working_method(api_key):
    """필터가 작동하는 방법 찾기 (최초 1회, 캐시)"""
    if "working_method" in st.session_state:
        return st.session_state["working_method"]

    test_enc = urllib.parse.quote("탄산음료")
    diag = []

    for name, base, fn in METHODS:
        url = f"{base}/{api_key}/I1250/json/1/3/PRDLST_DCNM={test_enc}"
        try:
            data = fn(url)
            svc = data.get("I1250", {})
            rows = svc.get("row", [])
            code = svc.get("RESULT", {}).get("CODE", "")
            if code == "INFO-000" and rows:
                dcnm = rows[0].get("PRDLST_DCNM", "")
                if dcnm == "탄산음료":
                    diag.append(f"✅ {name}: 필터 정상!")
                    st.session_state["working_method"] = (name, base, fn)
                    st.session_state["_diag"] = diag
                    return (name, base, fn)
                else:
                    diag.append(f"⚠️ {name}: 필터 무시 (반환: {dcnm})")
            else:
                diag.append(f"⚠️ {name}: {code or '데이터없음'}")
        except Exception as e:
            ename = type(e).__name__
            diag.append(f"❌ {name}: {ename}")

    # 아무것도 안 되면 첫 번째 (HTTP) 사용
    st.session_state["_diag"] = diag
    st.session_state["working_method"] = METHODS[0]
    return METHODS[0]


def fetch_data(api_key, food_type, max_rows, log):
    method_name, base_url, call_fn = find_working_method(api_key)
    norm_target = _normalize(food_type)

    log(f"🚀 {food_type} 수집 시작")
    log(f"📡 연결 방식: {method_name}")

    # 진단 결과 표시
    for d in st.session_state.get("_diag", []):
        log(f"   {d}")

    # 마침표가 있으면 2가지 인코딩 시도
    encodings = []
    if "." in food_type:
        encodings = [
            ("safe='.'", urllib.parse.quote(food_type, safe=".")),
            ("safe=''",  urllib.parse.quote(food_type, safe="")),
        ]
    else:
        encodings = [("기본", urllib.parse.quote(food_type))]

    for enc_name, encoded_type in encodings:
        log(f"🔤 인코딩: {enc_name}")
        all_data = []
        start = 1
        retries = 0

        while start <= max_rows:
            end = min(start + 499, max_rows)
            url = f"{base_url}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded_type}"

            try:
                data = call_fn(url)
                svc = data.get("I1250")
                if not svc:
                    code = data.get("RESULT", {}).get("CODE", "")
                    log(f"   ⚠️ {code or '응답없음'}")
                    break

                raw = svc.get("row", [])
                total = svc.get("total_count", "0")
                code = svc.get("RESULT", {}).get("CODE", "")

                if code == "INFO-300":
                    log("❌ 인증키 오류"); return []
                if code != "INFO-000" or not raw:
                    break

                matched = [r for r in raw
                           if _normalize(r.get("PRDLST_DCNM", "")) == norm_target]
                all_data.extend(matched)
                log(f"📦 {start}~{end} → {len(matched)}/{len(raw)}건 "
                    f"(누적:{len(all_data)} DB:{total})")

                if len(raw) < (end - start + 1):
                    break
                start += 500
                time.sleep(0.2)

            except (TimeoutError, req_lib.exceptions.Timeout):
                retries += 1
                if retries > 2:
                    log("⏰ 타임아웃 3회 초과"); break
                log(f"⏰ 재시도 ({retries}/3)…")
                time.sleep(1)
                continue
            except Exception as e:
                log(f"⚠️ {type(e).__name__}: {e}")
                break

        if all_data:
            log(f"✅ {len(all_data)}건 수집 완료!")
            return all_data
        log(f"⚠️ '{enc_name}' 0건 — 다음 시도")

    return []


# ══════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════
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
        for k in ["working_method", "_diag"]:
            st.session_state.pop(k, None)
        st.success("완료 — 다음 조회 시 재감지")

if not api_key:
    st.info("👈 API 키를 입력하세요 → "
            "[발급](https://www.foodsafetykorea.go.kr/api/openApiInfo.do) (I1250)")
    st.stop()

if run:
    log_box = st.empty()
    lines = []
    def log(msg):
        lines.append(msg)
        log_box.code("\n".join(lines))

    t0 = time.time()
    raw_rows = fetch_data(api_key, food_type, max_rows, log)
    elapsed = time.time() - t0

    if not raw_rows:
        st.error("❌ 데이터 없음")
        st.info("Streamlit Cloud에서 이 API 접근이 불안정할 수 있습니다.\n"
                "**대안:** [Google Colab](https://colab.research.google.com)에서 동일 스크립트로 수집 → CSV 업로드")
        st.stop()

    df = pd.DataFrame(raw_rows)
    avail = [c for c in COL_MAP if c in df.columns]
    df = df[avail].rename(columns=COL_MAP)
    if "보고일자" in df.columns:
        df = df.sort_values("보고일자", ascending=False).reset_index(drop=True)

    st.success(f"✅ {len(df)}건 ({elapsed:.1f}초)")
    c1, c2, c3 = st.columns(3)
    c1.metric("수집", f"{len(df)}건")
    if "제조사" in df.columns:
        c2.metric("제조사", f"{df['제조사'].nunique()}개소")
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
