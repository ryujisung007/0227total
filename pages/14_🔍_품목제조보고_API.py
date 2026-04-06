"""
품목제조보고 조회 v8
━━━━━━━━━━━━━━━━━━
Cloud(requests) + 로컬(curl fallback) 자동 전환
"""
import streamlit as st
import pandas as pd
import json, os, time, subprocess, urllib.parse

st.set_page_config("품목제조보고", "🏭", layout="wide")

SERVICE  = "I1250"
API_BASE = "http://openapi.foodsafetykorea.go.kr/api"

FOOD_TYPES = {
    "음료 및 다류": [
        "과.채주스", "과.채음료", "농축과.채즙",
        "탄산음료", "탄산수",
        "두유", "가공두유", "원액두유",
        "인삼.홍삼음료", "혼합음료", "유산균음료",
        "음료베이스", "효모음료",
        "커피", "침출차", "고형차", "액상차",
    ],
    "유제품 및 빙과류": [
        "아이스크림", "아이스크림믹스", "저지방아이스크림",
        "아이스밀크", "빙과", "샤베트",
        "우유", "발효유", "농후발효유", "치즈", "버터",
    ],
    "과자.빵.초콜릿류": [
        "과자", "캔디류", "빵류", "떡류", "만두",
        "초콜릿", "초콜릿가공품",
    ],
    "조미식품 및 장류": [
        "소스", "토마토케첩", "마요네즈", "고추장", "된장",
        "한식간장", "양조간장", "복합조미식품",
    ],
    "기타 가공식품": [
        "즉석조리식품", "즉석섭취식품", "신선편의식품",
        "간편조리세트", "김치", "생면", "유탕면",
    ],
}

COL = {
    "PRDLST_NM": "제품명", "BSSH_NM": "제조사", "PRDLST_DCNM": "식품유형",
    "PRMS_DT": "보고일자", "RAWMTRL_NM": "원재료", "POG_DAYCNT": "유통기한",
    "PRODUCTION": "생산종료", "LAST_UPDT_DTM": "최종수정",
    "PRDLST_REPORT_NO": "품목제조번호",
}


# ══════════════════════════════════════════════════════
#  API 호출 — requests 우선, curl fallback
# ══════════════════════════════════════════════════════
def _try_requests(url):
    """Streamlit Cloud / Colab 등 클라우드 환경용"""
    import requests as req
    s = req.Session()
    s.trust_env = False
    r = s.get(url, timeout=(10, 30),
              proxies={"http": None, "https": None},
              headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def _try_curl(url):
    """로컬 PC용 — Windows/Mac/Linux curl"""
    env = {k: v for k, v in os.environ.items()
           if "proxy" not in k.lower()}
    if os.name == "nt":
        env.setdefault("SYSTEMROOT", r"C:\Windows")
    r = subprocess.run(
        ["curl", "-s", "-m", "60", "--connect-timeout", "15",
         "--noproxy", "*", "-4", url],
        capture_output=True, timeout=65, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"curl code {r.returncode}")
    raw = r.stdout.decode("utf-8", errors="replace").strip()
    return json.loads(raw)


def api_get(url):
    """requests → curl 자동 전환"""
    # 1차: requests
    try:
        return _try_requests(url)
    except Exception:
        pass
    # 2차: curl
    try:
        return _try_curl(url)
    except Exception as e:
        raise RuntimeError(f"API 연결 실패 (requests+curl 모두): {e}")


def fetch(api_key, food_type, count):
    """데이터 수집 — 1회 호출"""
    enc = urllib.parse.quote(food_type.strip(), safe=".")
    url = f"{API_BASE}/{api_key}/{SERVICE}/json/1/{count}/PRDLST_DCNM={enc}"
    data = api_get(url)
    body = data.get(SERVICE, {})
    code = body.get("RESULT", {}).get("CODE", "")
    if code == "INFO-300":
        raise RuntimeError("인증키 오류 — API 키를 확인하세요")
    if code != "INFO-000":
        raise RuntimeError(f"API 오류: {body.get('RESULT', {})}")
    rows  = body.get("row", [])
    total = body.get("total_count", "0")
    # 식품유형 일치 검증
    norm = food_type.strip().replace("·", ".").lower()
    rows = [r for r in rows
            if r.get("PRDLST_DCNM", "").strip().replace("·", ".").lower() == norm]
    return rows, total


# ══════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════
st.title("🏭 품목제조보고 조회")

# 사이드바
with st.sidebar:
    st.markdown("### 설정")
    api_key = st.text_input("🔑 API 키", value="9171f7ffd72f4ffcb62f", type="password")
    category = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
    food_type = st.selectbox("식품유형", FOOD_TYPES[category])
    count = st.slider("조회 건수", 10, 500, 100, step=10)
    st.markdown("---")
    run = st.button("🚀 조회", type="primary", use_container_width=True)
    st.caption("📡 식품안전나라 I1250 · v8")

if run:
    with st.spinner(f"📡 {food_type} 조회 중…"):
        t0 = time.time()
        try:
            rows, total = fetch(api_key, food_type, count)
        except Exception as e:
            st.error(f"❌ {e}")
            st.stop()
        elapsed = time.time() - t0

    if not rows:
        st.warning("조회 결과 없음")
        st.stop()

    df = pd.DataFrame(rows)
    df = df.rename(columns={k: v for k, v in COL.items() if k in df.columns})
    if "최종수정" in df.columns:
        df = df.sort_values("최종수정", ascending=False).reset_index(drop=True)

    # 요약
    st.success(f"✅ **{len(df)}건** | {elapsed:.1f}초 | 전체 DB {total}건")
    c1, c2, c3 = st.columns(3)
    c1.metric("조회 건수", f"{len(df)}건")
    c2.metric("제조사 수", f"{df['제조사'].nunique()}개" if "제조사" in df.columns else "-")
    c3.metric("전체 DB", f"{int(total):,}건")

    # 테이블
    st.markdown("---")
    kw = st.text_input("🔎 검색", placeholder="제품명·제조사·원재료")
    show_cols = [c for c in ["제품명","제조사","보고일자","유통기한","원재료","생산종료"]
                 if c in df.columns]
    fdf = df.copy()
    if kw:
        fdf = fdf[fdf.apply(lambda r: kw.lower() in str(r).lower(), axis=1)]
    st.dataframe(fdf[show_cols].reset_index(drop=True),
                 use_container_width=True, height=500)
    st.caption(f"총 {len(fdf)}건")

    # 차트
    if "제조사" in df.columns:
        import plotly.express as px
        st.markdown("### 📊 제조사별 제품 수")
        mc = df["제조사"].value_counts().head(15)
        fig = px.bar(x=mc.values, y=mc.index, orientation="h",
                     color=mc.values, color_continuous_scale="Blues",
                     labels={"x": "제품 수", "y": "제조사"})
        fig.update_layout(height=400, showlegend=False,
                          yaxis=dict(autorange="reversed"))
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    # CSV
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV 다운로드", csv,
                       f"{food_type}_{time.strftime('%Y%m%d')}.csv",
                       "text/csv", use_container_width=True)

    # 세션 저장 (다른 탭에서 활용 가능)
    st.session_state["last_df"] = df
    st.session_state["last_type"] = food_type
