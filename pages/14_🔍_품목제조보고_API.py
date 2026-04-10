"""
🥤 식품안전나라 음료 품목제조보고 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
마침표 수동 %2E 인코딩 (urllib.parse.quote가 . 인코딩 불가)
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


def _encode_food_type(food_type):
    """식품유형명 URL 인코딩 — 마침표를 %2E로 강제 인코딩
    urllib.parse.quote는 RFC상 마침표를 안전문자로 취급하여 인코딩 불가.
    서버가 URL 경로의 . 을 구분자로 해석하므로 반드시 %2E로 변환 필요.
    """
    return urllib.parse.quote(food_type).replace(".", "%2E")


def api_get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_data(api_key, food_type, max_rows, log):
    norm_target = _normalize(food_type)
    encoded_type = _encode_food_type(food_type)
    page_size = 500

    log(f"🚀 {food_type} 수집 시작")
    log(f"🔤 인코딩: {encoded_type}")

    all_data = []
    start = 1
    retries = 0

    while start <= max_rows:
        end = min(start + page_size - 1, max_rows)
        url = f"{BASE_URL}/{api_key}/I1250/json/{start}/{end}/PRDLST_DCNM={encoded_type}"

        try:
            data = api_get(url, timeout=30)
            svc = data.get("I1250")

            if not svc:
                code = data.get("RESULT", {}).get("CODE", "")
                log(f"   API: {code} {data.get('RESULT',{}).get('MSG','')}")
                break

            code = svc.get("RESULT", {}).get("CODE", "")
            if code == "INFO-300":
                log("❌ 인증키 오류")
                return []
            if code != "INFO-000":
                log(f"   API: {code}")
                break

            raw = svc.get("row", [])
            total = svc.get("total_count", "0")

            # 식품유형 정확 일치 필터
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
                log(f"   ❌ 연결 실패 (3회): {e}")
                break
            log(f"   ⏰ 타임아웃 — 재시도 {retries}/3")
            time.sleep(2)
            continue
        except Exception as e:
            log(f"   ⚠️ {type(e).__name__}: {e}")
            break

    if all_data:
        log(f"✅ {len(all_data)}건 수집 완료!")
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

    st.markdown("---")
    if st.button("🩺 연결 테스트"):
        if api_key:
            # 탄산음료 (마침표 없음)로 테스트
            test_url = f"{BASE_URL}/{api_key}/I1250/json/1/3/PRDLST_DCNM={urllib.parse.quote('탄산음료')}"
            try:
                d = api_get(test_url, timeout=30)
                rows = d.get("I1250", {}).get("row", [])
                if rows and rows[0].get("PRDLST_DCNM") == "탄산음료":
                    st.success("✅ HTTP 정상 + 필터 작동!")
                else:
                    st.warning(f"⚠️ 연결됨, 필터 이상")
            except Exception as e:
                st.error(f"❌ HTTP 실패: {e}")

            # 과.채주스 (마침표 %2E)로 테스트
            test_url2 = f"{BASE_URL}/{api_key}/I1250/json/1/3/PRDLST_DCNM={_encode_food_type('과.채주스')}"
            try:
                d2 = api_get(test_url2, timeout=30)
                rows2 = d2.get("I1250", {}).get("row", [])
                if rows2 and rows2[0].get("PRDLST_DCNM") == "과.채주스":
                    st.success("✅ 마침표(%2E) 필터 정상!")
                else:
                    dcnm = rows2[0].get("PRDLST_DCNM", "?") if rows2 else "없음"
                    total = d2.get("I1250", {}).get("total_count", "?")
                    st.warning(f"⚠️ 과.채주스 필터 결과: {dcnm} (total: {total})")
            except Exception as e:
                st.error(f"❌ 과.채주스 테스트 실패: {e}")
        else:
            st.warning("API 키를 입력하세요")

if not api_key:
    st.info("👈 API 키를 입력하세요 → "
            "[발급](https://www.foodsafetykorea.go.kr/api/openApiInfo.do)")
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
