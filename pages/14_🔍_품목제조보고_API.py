"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HTTP 전용 (HTTPS는 이 API에서 필터 미지원)
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

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"


def _normalize(s):
    return s.strip().replace("·", ".").replace("‧", ".").replace(" ", "")


def api_get(url, timeout=30):
    """urllib로 HTTP API 호출"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; FoodSafetyBot/1.0)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_data(api_key, food_type, max_rows, log):
    norm_target = _normalize(food_type)
    page_size = 500

    # 마침표 인코딩: safe="." 먼저, 실패 시 safe="" (%2E)
    if "." in food_type:
        enc_list = [
            (".", urllib.parse.quote(food_type, safe=".")),
            ("%2E", urllib.parse.quote(food_type, safe="")),
        ]
    else:
        enc_list = [("기본", urllib.parse.quote(food_type))]

    for enc_label, encoded_type in enc_list:
        all_data = []
        start = 1
        retries = 0
        log(f"🔤 인코딩: {enc_label} → {encoded_type}")

        while start <= max_rows:
            end = min(start + page_size - 1, max_rows)
            url = f"{BASE_URL}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded_type}"

            try:
                data = api_get(url, timeout=30)
                svc = data.get("I1250")

                if not svc:
                    code = data.get("RESULT", {}).get("CODE", "")
                    log(f"   API 응답: {code} {data.get('RESULT',{}).get('MSG','')}")
                    break

                code = svc.get("RESULT", {}).get("CODE", "")
                if code == "INFO-300":
                    log("❌ 인증키 오류 — 키를 확인하세요")
                    return []
                if code != "INFO-000":
                    break

                raw = svc.get("row", [])
                total = svc.get("total_count", "0")

                matched = [r for r in raw
                           if _normalize(r.get("PRDLST_DCNM", "")) == norm_target]
                all_data.extend(matched)

                log(f"   📦 {start}~{end} → {len(matched)}/{len(raw)}건 "
                    f"(누적 {len(all_data)} / DB {total})")

                if len(raw) < (end - start + 1):
                    break
                start += page_size
                retries = 0
                time.sleep(0.2)

            except (TimeoutError, urllib.error.URLError) as e:
                retries += 1
                if retries > 3:
                    log(f"   ❌ 연결 실패 (3회 재시도 후 중단): {e}")
                    break
                log(f"   ⏰ 타임아웃 — 재시도 {retries}/3")
                time.sleep(2)
                continue
            except Exception as e:
                log(f"   ⚠️ {type(e).__name__}: {e}")
                break

        if all_data:
            log(f"✅ {len(all_data)}건 수집 성공!")
            return all_data

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

    # 연결 진단
    st.markdown("---")
    if st.button("🩺 연결 테스트"):
        if api_key:
            st.markdown("**HTTP 연결 테스트 중…**")
            test_url = f"{BASE_URL}/{api_key}/I1250/json/1/3/PRDLST_DCNM=%ED%83%84%EC%82%B0%EC%9D%8C%EB%A3%8C"
            try:
                t0 = time.time()
                d = api_get(test_url, timeout=30)
                ms = int((time.time() - t0) * 1000)
                svc = d.get("I1250", {})
                rows = svc.get("row", [])
                if rows and rows[0].get("PRDLST_DCNM") == "탄산음료":
                    st.success(f"✅ HTTP 정상 ({ms}ms)\n\n필터 작동 확인!")
                else:
                    dcnm = rows[0].get("PRDLST_DCNM", "?") if rows else "없음"
                    st.warning(f"⚠️ 연결됨 ({ms}ms) but 필터 이상\n\n반환된 유형: {dcnm}")
            except Exception as e:
                st.error(f"❌ HTTP 연결 실패\n\n{type(e).__name__}: {e}\n\n"
                         "Streamlit Cloud에서 이 API 서버(HTTP)에 접근할 수 없습니다.\n"
                         "**대안:** Colab에서 데이터를 수집하세요.")
        else:
            st.warning("API 키를 먼저 입력하세요")

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

    log("🚀 조회 시작…")
    t0 = time.time()
    raw_rows = fetch_data(api_key, food_type, max_rows, log)
    elapsed = time.time() - t0

    if not raw_rows:
        st.error("❌ 수집된 데이터가 없습니다.")
        st.info("사이드바의 **🩺 연결 테스트**를 눌러 HTTP 접속 가능 여부를 확인하세요.")
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
