"""품목제조보고 간편 조회 — 심플 버전"""
import streamlit as st
import requests
import pandas as pd
import socket
import time

# IPv4 강제
_orig = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: _orig(a[0], a[1], socket.AF_INET, *a[3:], **k)

st.set_page_config("품목제조보고", "🏭", layout="wide")
st.title("🏭 품목제조보고 간편 조회")

# ── 설정 ──
TYPES = [
    "과.채주스", "과.채음료", "농축과.채즙", "탄산음료", "탄산수",
    "두유", "가공두유", "혼합음료", "유산균음료", "커피",
    "침출차", "액상차", "인삼.홍삼음료", "음료베이스",
    "아이스크림", "빙과", "소스", "과자", "빵류", "즉석조리식품",
]

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    api_key = st.text_input("🔑 API 키", value="9171f7ffd72f4ffcb62f",
                            help="식품안전나라에서 발급")
with c2:
    food_type = st.selectbox("식품유형", TYPES)
with c3:
    count = st.selectbox("건수", [20, 50, 100, 200], index=1)

if st.button("🚀 조회", type="primary", use_container_width=True):
    import urllib.parse
    enc = urllib.parse.quote(food_type, safe=".")
    url = f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I1250/json/1/{count}/PRDLST_DCNM={enc}"

    with st.spinner(f"📡 {food_type} 조회 중…"):
        try:
            s = requests.Session()
            s.trust_env = False
            r = s.get(url, timeout=(10, 30),
                      proxies={"http": None, "https": None},
                      headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
        except Exception as e:
            st.error(f"❌ 연결 실패: {e}")
            st.stop()

    body = data.get("I1250", {})
    code = body.get("RESULT", {}).get("CODE", "")
    total = body.get("total_count", "0")

    if code != "INFO-000":
        st.error(f"❌ API 오류: {body.get('RESULT', {})}")
        st.stop()

    rows = body.get("row", [])
    if not rows:
        st.warning("조회 결과 없음")
        st.stop()

    # DataFrame
    COL = {"PRDLST_NM": "제품명", "BSSH_NM": "제조사", "PRDLST_DCNM": "식품유형",
           "PRMS_DT": "보고일자", "RAWMTRL_NM": "원재료", "POG_DAYCNT": "유통기한",
           "PRODUCTION": "생산종료", "LAST_UPDT_DTM": "최종수정"}
    df = pd.DataFrame(rows)
    df = df.rename(columns={k: v for k, v in COL.items() if k in df.columns})

    if "최종수정" in df.columns:
        df = df.sort_values("최종수정", ascending=False)

    st.success(f"✅ **{len(df)}건** 조회 완료 (전체 DB: {total}건)")

    show = [c for c in ["제품명", "제조사", "보고일자", "유통기한", "원재료", "생산종료"] if c in df.columns]
    st.dataframe(df[show].reset_index(drop=True), use_container_width=True, height=500)

    # CSV
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV 다운로드", csv,
                       f"{food_type}_{time.strftime('%Y%m%d')}.csv",
                       "text/csv", use_container_width=True)
