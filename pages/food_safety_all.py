"""
식품안전나라 통합 조회 앱 v1.0
API: I1250 / C002 / I0030 / I0490 / COOKRCP01 / I2500 / I1200
로컬 실행: streamlit run food_safety_all.py
secrets.toml: FOOD_SAFETY_API_KEY = "7270692908c74bccaebc"
"""
import streamlit as st
import requests
import pandas as pd
import re
import time
from datetime import date, timedelta

st.set_page_config(
    page_title="식품안전나라 통합조회",
    page_icon="🍱",
    layout="wide",
)

# ============================================================
# 설정
# ============================================================
def get_api_key():
    try:
        for k in ("FOOD_SAFETY_API_KEY", "food_safety_api_key", "FOOD_SAFETY_KEY"):
            v = st.secrets.get(k, "")
            if v and str(v).strip():
                return str(v).strip()
        # 중첩 섹션 구조: [food_safety] API_KEY = "..."
        for sec in ("food_safety", "foodsafety"):
            try:
                for k in ("FOOD_SAFETY_API_KEY", "API_KEY", "api_key"):
                    v = st.secrets[sec].get(k, "")
                    if v and str(v).strip():
                        return str(v).strip()
            except Exception:
                pass
    except Exception:
        pass
    return ""

BASE = "http://openapi.foodsafetykorea.go.kr/api"

SVC = {
    "품목제조보고":   "I1250",
    "품목원재료":     "C002",
    "건강기능식품":   "I0030",
    "회수판매중지":   "I0490",
    "레시피":         "COOKRCP01",
    "인허가업소":     "I2500",
    "식품접객업":     "I1200",
}

# ============================================================
# 공통 유틸
# ============================================================
def _url(svc_id, p_s, p_e, params=""):
    key  = st.session_state.get("manual_api_key", "").strip() or get_api_key()
    base = f"{BASE}/{key}/{svc_id}/json/{p_s}/{p_e}"
    return f"{base}/{params}" if params else base

def _norm(s):
    return s.strip().replace("·", ".").replace(" ", "").lower()

@st.cache_data(ttl=600, show_spinner=False)
def _get(url):
    proxy = st.session_state.get("proxy_url", "").strip()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=20, proxies=proxies)
            r.raise_for_status()
            return r.json(), None
        except requests.exceptions.ConnectTimeout:
            if attempt < 2:
                time.sleep(2)
                continue
            return None, "연결 시간 초과 — 네트워크/방화벽 확인 필요"
        except requests.exceptions.ConnectionError as e:
            return None, f"연결 실패 — 방화벽/프록시 확인: {str(e)[:100]}"
        except Exception as e:
            return None, str(e)
    return None, "3회 재시도 실패"

def _rows(data, svc_id):
    """응답 JSON에서 row 리스트 추출"""
    if not data or svc_id not in data:
        return [], "서비스 키 없음"
    res  = data[svc_id]
    code = res.get("RESULT", {}).get("CODE", "")
    msg  = res.get("RESULT", {}).get("MSG", "")
    if code == "INFO-200":
        return [], "조회 결과 없음"
    if code != "INFO-000":
        return [], f"[{code}] {msg}"
    return res.get("row", []), None

def fetch_all(svc_id, params="", max_rows=500):
    """전체 페이지 순차 수집"""
    # total 확인
    data, err = _get(_url(svc_id, 1, 1, params))
    if err or not data:
        return [], err or "응답 없음"
    if svc_id not in data:
        return [], "서비스 ID 오류"
    total = int(data[svc_id].get("total_count", 0))
    if total == 0:
        return [], "결과 없음"

    collected = []
    step      = 1000
    for p_s in range(1, min(total, max_rows) + 1, step):
        p_e = min(p_s + step - 1, total, max_rows)
        d, err = _get(_url(svc_id, p_s, p_e, params))
        rows, _ = _rows(d or {}, svc_id)
        collected.extend(rows)
        if p_e >= total or len(collected) >= max_rows:
            break
        time.sleep(0.15)
    return collected[:max_rows], None

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
.hdr { background: linear-gradient(135deg,#1a237e,#283593);
       color:white; padding:14px 20px; border-radius:10px;
       font-size:22px; font-weight:800; margin-bottom:14px; }
.step-box { background:#e8eaf6; border-left:5px solid #3949ab;
            padding:10px 16px; border-radius:6px;
            font-size:16px; font-weight:700; margin:10px 0 6px; }
.warn-box { background:#ffebee; border-left:5px solid #e53935;
            padding:10px 16px; border-radius:6px;
            font-size:15px; font-weight:600; margin:8px 0; }
.ok-box   { background:#e8f5e9; border-left:5px solid #43a047;
            padding:10px 16px; border-radius:6px;
            font-size:15px; margin:8px 0; }
.metric-row { display:flex; gap:12px; flex-wrap:wrap; margin:10px 0 16px; }
.mc { flex:1; min-width:120px; padding:14px; border-radius:10px;
      text-align:center; color:white; }
.mc .n { font-size:26px; font-weight:900; }
.mc .l { font-size:12px; opacity:.9; }
.mc-blue   { background:linear-gradient(135deg,#1565c0,#1976d2); }
.mc-green  { background:linear-gradient(135deg,#2e7d32,#388e3c); }
.mc-red    { background:linear-gradient(135deg,#b71c1c,#c62828); }
.mc-amber  { background:linear-gradient(135deg,#e65100,#f57c00); }
.mc-teal   { background:linear-gradient(135deg,#00695c,#00897b); }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.markdown("### 🍱 식품안전나라 통합조회")
    st.markdown("---")

    # ── 설치 가이드 ──
    with st.expander("🛠️ 최초 설치 가이드", expanded=False):
        st.markdown("**1. 저장소 클론**")
        st.code(
            "git clone https://github.com/ryujisung007/0227total.git\n"
            "cd 0227total",
            language="bash"
        )

        st.markdown("**2. 패키지 설치**")
        st.code("pip install -r requirements.txt", language="bash")

        st.markdown("**3. API 키 설정**")
        st.code(
            "# Windows\n"
            "mkdir .streamlit\n"
            "echo FOOD_SAFETY_API_KEY = \"7270692908c74bccaebc\" > .streamlit/secrets.toml\n\n"
            "# Mac/Linux\n"
            "mkdir -p .streamlit\n"
            "echo 'FOOD_SAFETY_API_KEY = \"7270692908c74bccaebc\"' > .streamlit/secrets.toml",
            language="bash"
        )

        st.markdown("**4. 앱 실행**")
        st.code(
            "# pages 폴더 안에 있으므로 아래 명령 실행\n"
            "streamlit run pages/food_safety_all.py",
            language="bash"
        )

        st.markdown("**5. 업데이트 시**")
        st.code(
            "git pull origin main\n"
            "streamlit run pages/food_safety_all.py",
            language="bash"
        )

        st.markdown("**GitHub 주소**")
        st.markdown("[🔗 ryujisung007/0227total](https://github.com/ryujisung007/0227total)")
        st.info("💡 Python 3.9 이상 필요\nhttps://python.org")

    st.markdown("---")
    API_KEY = get_api_key()

    if not API_KEY:
        st.warning("⚠️ secrets.toml에서 키를 읽지 못했습니다.\n아래에 직접 입력하세요.")
        manual_key = st.text_input(
            "FOOD_SAFETY_API_KEY",
            type="password",
            placeholder="7270692908c74bcc...",
            key="manual_api_key"
        )
        if manual_key.strip():
            API_KEY = manual_key.strip()
            st.success(f"✅ 수동 입력: `{API_KEY[:8]}...`")
        else:
            st.info("💡 키 입력 후 Enter를 누르세요.")
            st.stop()
    else:
        st.success(f"✅ API 키: `{API_KEY[:8]}...`")
    st.markdown("---")

    # ── 네트워크 진단 ──
    with st.expander("🔌 네트워크 진단 / 프록시 설정", expanded=False):
        if st.button("🔌 연결 테스트", use_container_width=True, key="net_test"):
            test_url = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I1250/json/1/1"
            proxy = st.session_state.get("proxy_url", "").strip()
            proxies = {"http": proxy, "https": proxy} if proxy else None
            try:
                r = requests.get(test_url, timeout=10, proxies=proxies)
                if r.status_code == 200:
                    st.success("✅ API 서버 연결 정상")
                else:
                    st.warning(f"⚠️ HTTP {r.status_code}: {r.text[:100]}")
            except requests.exceptions.ConnectTimeout:
                st.error("❌ 연결 시간 초과\n방화벽/VPN 확인 필요")
            except Exception as e:
                st.error(f"❌ {str(e)[:150]}")

        st.markdown("**프록시 설정 (회사 네트워크 시)**")
        proxy_input = st.text_input(
            "프록시 주소",
            placeholder="http://proxy.company.com:8080",
            key="proxy_url",
        )
        if proxy_input:
            st.caption(f"프록시 적용: {proxy_input}")

        st.markdown("**문제 해결 체크리스트**")
        st.markdown("""
- VPN 연결 해제 후 재시도
- 회사 네트워크라면 프록시 주소 입력
- `curl http://openapi.foodsafetykorea.go.kr` 로 직접 테스트
- 식품안전나라 서버 점검 여부 확인
        """)

    st.markdown("---")

# ============================================================
# session_state 초기화
# ============================================================
for k, v in {
    "products":      [],     # I1250 검색 결과
    "selected_nos":  set(),  # 선택된 품목제조번호
    "raw_mats":      [],     # C002 원재료 결과
    "recall_df":     None,   # I0490 회수 목록
    "recall_loaded": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 탭 구성
# ============================================================
tab1, tab2 = st.tabs(["🔬 품목·원재료·회수체크", "🏢 업소·레시피·접객"])

# ╔══════════════════════════════════════════════════════════╗
# ║  TAB 1 : 품목조회 → 원재료 → 회수 교차체크              ║
# ╚══════════════════════════════════════════════════════════╝
with tab1:
    st.markdown('<div class="hdr">🔬 품목제조보고 → 원재료 → 회수·판매중지 교차체크</div>',
                unsafe_allow_html=True)

    # ── STEP 1: 검색 ──────────────────────────────────────
    st.markdown('<div class="step-box">STEP 1 · 품목제조보고 검색</div>',
                unsafe_allow_html=True)

    FOOD_TYPES_FLAT = [
        "과.채주스","과.채음료","농축과.채즙","탄산음료","탄산수",
        "두유","가공두유","인삼.홍삼음료","혼합음료","유산균음료",
        "음료베이스","커피","침출차","고형차","액상차",
        "과자","캔디류","추잉껌","빵류","떡류","초콜릿","준초콜릿",
        "아이스크림","아이스크림믹스","빙과",
        "우유","가공유","발효유","농후발효유","치즈","버터",
        "햄","소시지","어묵","어육소시지","김치","두부",
        "소스","복합조미식품","마요네즈","발효식초",
        "전지분유","탈지분유","가당분유",
        "생면","건면","유탕면","즉석섭취식품","즉석조리식품",
        "건강기능식품",
    ]

    c1, c2, c3 = st.columns([2, 3, 1])
    with c1:
        search_mode = st.radio("검색 방식", ["식품유형", "제품명"], horizontal=True,
                               key="s1_mode")
    with c2:
        if search_mode == "식품유형":
            food_type = st.selectbox("식품유형 선택", FOOD_TYPES_FLAT, key="s1_type")
            prdlst_nm = ""
        else:
            prdlst_nm  = st.text_input("제품명 입력", placeholder="예: 제로, 비타민",
                                        key="s1_nm")
            food_type  = ""
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        max_prod = st.number_input("최대 건수", 10, 2000, 200, 50, key="s1_max")

    if st.button("🔍 품목 조회", type="primary", use_container_width=True, key="s1_run"):
        import urllib.parse
        params_parts = []
        if food_type:
            params_parts.append(f"PRDLST_DCNM={urllib.parse.quote(food_type,safe='')}")
        if prdlst_nm:
            params_parts.append(f"PRDLST_NM={urllib.parse.quote(prdlst_nm,safe='')}")
        params_str = "&".join(params_parts)

        with st.spinner("품목 조회 중…"):
            rows, err = fetch_all(SVC["품목제조보고"], params_str, max_prod)

        if err and not rows:
            st.error(f"❌ {err}")
        else:
            st.session_state.products     = rows
            st.session_state.selected_nos = set()
            st.session_state.raw_mats     = []
            st.success(f"✅ {len(rows)}건 조회됨")

    # ── STEP 2: 제품 선택 ─────────────────────────────────
    if st.session_state.products:
        st.markdown("---")
        st.markdown('<div class="step-box">STEP 2 · 제품 선택 (원재료 조회할 제품 체크)</div>',
                    unsafe_allow_html=True)

        rows = st.session_state.products
        df_p = pd.DataFrame([{
            "품목제조번호": r.get("PRDLST_REPORT_NO", ""),
            "제품명":       r.get("PRDLST_NM", ""),
            "식품유형":     r.get("PRDLST_DCNM", ""),
            "제조사":       r.get("BSSH_NM", ""),
            "보고일자":     r.get("PRMS_DT", ""),
            "최종수정":     r.get("LAST_UPDT_DTM", ""),
            "포장재질":     r.get("FRMLC_MTRQLT", ""),
            "유통기한":     r.get("POG_DAYCNT", ""),
            "생산여부":     r.get("PRODUCTION", ""),
            "업종":         r.get("INDUTY_CD_NM", ""),
        } for r in rows])

        # 전체선택 / 전체해제
        ca, cb, cc = st.columns([1, 1, 6])
        with ca:
            if st.button("✅ 전체 선택", use_container_width=True, key="sel_all"):
                st.session_state.selected_nos = set(df_p["품목제조번호"].tolist())
        with cb:
            if st.button("☐ 전체 해제", use_container_width=True, key="sel_none"):
                st.session_state.selected_nos = set()
        with cc:
            st.caption(f"선택: {len(st.session_state.selected_nos)} / {len(df_p)}건")

        # 제품 목록 + 체크박스
        st.markdown("**제품 목록** (체크 후 원재료 조회)")
        for _, row in df_p.iterrows():
            rno  = row["품목제조번호"]
            chk  = rno in st.session_state.selected_nos
            cols = st.columns([0.5, 3, 2, 2, 1.5])
            new_chk = cols[0].checkbox("", value=chk, key=f"chk_{rno}",
                                       label_visibility="collapsed")
            if new_chk != chk:
                if new_chk:
                    st.session_state.selected_nos.add(rno)
                else:
                    st.session_state.selected_nos.discard(rno)
            cols[1].markdown(f"**{row['제품명'][:30]}**")
            cols[2].markdown(f"<small>{row['제조사'][:20]}</small>", unsafe_allow_html=True)
            cols[3].markdown(f"<small>{row['식품유형']}</small>", unsafe_allow_html=True)
            cols[4].markdown(f"<small>{row['보고일자']}</small>", unsafe_allow_html=True)

        st.markdown("---")
        if st.session_state.selected_nos:
            if st.button(
                f"📋 선택 제품 원재료 조회 ({len(st.session_state.selected_nos)}건)",
                type="primary", use_container_width=True, key="raw_run"
            ):
                all_raw = []
                prog = st.progress(0.0)
                nos  = list(st.session_state.selected_nos)
                for i, rno in enumerate(nos):
                    prog.progress((i+1)/len(nos), text=f"원재료 조회 중… {i+1}/{len(nos)}")
                    import urllib.parse
                    params = f"PRDLST_REPORT_NO={urllib.parse.quote(rno,safe='')}"
                    r_rows, err = fetch_all(SVC["품목원재료"], params, 200)
                    # 제품명 join
                    pname = next(
                        (r.get("PRDLST_NM","") for r in rows
                         if r.get("PRDLST_REPORT_NO","") == rno), rno
                    )
                    for rr in r_rows:
                        rr["_제품명"] = pname
                        rr["_품목제조번호"] = rno
                        all_raw.append(rr)
                    time.sleep(0.15)
                prog.empty()
                st.session_state.raw_mats = all_raw
                st.success(f"✅ 원재료 {len(all_raw)}건 수집 완료")

    # ── STEP 3: 원재료 + 회수 교차체크 ──────────────────
    if st.session_state.raw_mats:
        st.markdown('<div class="step-box">STEP 3 · 원재료 목록 + 회수·판매중지 교차체크</div>',
                    unsafe_allow_html=True)

        # 원재료 DataFrame
        raw_rows = st.session_state.raw_mats
        df_raw = pd.DataFrame([{
            "제품명":   r.get("_제품명", ""),
            # C002 필드명 우선순위로 탐색
            "원재료명": (r.get("RAWMTRL_NM")
                        or r.get("INGR_NM")
                        or r.get("RAW_MTRL_NM")
                        or r.get("MATERIAL_NM", "")),
            "함량":     (r.get("CONTENT")
                        or r.get("CNTNT")
                        or r.get("CONTENT_NM", "")),
            "원산지":   (r.get("ORIGIN_CNTRY_NM")
                        or r.get("ORIGN_CNTRY_NM")
                        or r.get("CNTRY_NM", "")),
        } for r in raw_rows])

        # 원재료명이 전부 비어있으면 실제 필드 디버그 표시
        if df_raw["원재료명"].eq("").all() and raw_rows:
            st.warning("⚠️ 원재료 필드명 자동 탐색 실패 — 실제 필드 확인 중")
            with st.expander("🔍 C002 실제 응답 필드 (개발자 확인용)"):
                st.json(raw_rows[0])
            # 전체 필드를 그대로 표시
            df_raw = pd.DataFrame(raw_rows[:50])

        # 원재료 집계 (제품별 사용 수)
        if not df_raw.empty:
            mat_count = (df_raw.groupby("원재료명")
                         .agg(사용제품수=("제품명","nunique"),
                              제품목록=("제품명", lambda x: ", ".join(set(x))))
                         .reset_index()
                         .sort_values("사용제품수", ascending=False))

            # 회수·판매중지 목록 로딩 (캐시)
            if not st.session_state.recall_loaded:
                with st.spinner("회수·판매중지 정보 로딩 중…"):
                    r_rows, err = fetch_all(SVC["회수판매중지"], "", 2000)
                    st.session_state.recall_df     = pd.DataFrame(r_rows)
                    st.session_state.recall_loaded = True

            recall_df = st.session_state.recall_df

            # 교차체크
            if recall_df is not None and not recall_df.empty:
                # 회수 제품명·원재료명 텍스트 풀
                recall_text = " ".join(
                    recall_df.get("PRDLST_NM", pd.Series()).fillna("").str.lower().tolist() +
                    recall_df.get("RAWMTRL_NM", pd.Series()).fillna("").str.lower().tolist()
                )

                def _is_recalled(mat_name):
                    nm = mat_name.lower().strip()
                    if not nm:
                        return False
                    # 2글자 이상 토큰만 검색
                    return len(nm) >= 2 and nm in recall_text

                mat_count["⚠️회수여부"] = mat_count["원재료명"].apply(
                    lambda x: "🔴 회수/중지" if _is_recalled(x) else "✅ 정상"
                )
            else:
                mat_count["⚠️회수여부"] = "확인불가"

            # 경고 표시
            warned = mat_count[mat_count["⚠️회수여부"].str.contains("🔴")]
            if not warned.empty:
                st.markdown(
                    f'<div class="warn-box">🚨 회수·판매중지 해당 원재료 '
                    f'<b>{len(warned)}종</b> 발견!</div>',
                    unsafe_allow_html=True
                )
                st.dataframe(warned[["원재료명","사용제품수","제품목록","⚠️회수여부"]],
                             use_container_width=True, hide_index=True)
            else:
                st.markdown('<div class="ok-box">✅ 회수·판매중지 해당 원재료 없음</div>',
                            unsafe_allow_html=True)

            # 전체 원재료 테이블
            with st.expander(f"📋 전체 원재료 목록 ({len(mat_count)}종)", expanded=True):
                st.dataframe(mat_count, use_container_width=True, hide_index=True)

            # 제품별 원재료 상세
            with st.expander("🔍 제품별 원재료 상세"):
                products_in = sorted(df_raw["제품명"].unique())
                sel_p = st.selectbox("제품 선택", products_in, key="raw_detail")
                st.dataframe(
                    df_raw[df_raw["제품명"]==sel_p][["원재료명","함량","원산지"]],
                    use_container_width=True, hide_index=True
                )

            # CSV 다운로드
            csv = mat_count.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 원재료 CSV", csv, "원재료목록.csv", "text/csv")

        else:
            st.warning("원재료 데이터가 없습니다. (API 필드명 확인 필요)")
            st.json(raw_rows[:2])   # 실제 필드 확인용


# ╔══════════════════════════════════════════════════════════╗
# ║  TAB 2 : 업소 · 레시피 · 접객                           ║
# ╚══════════════════════════════════════════════════════════╝
with tab2:
    st.markdown('<div class="hdr">🏢 업소·레시피·접객업 조회</div>',
                unsafe_allow_html=True)

    # ── 공통 조회 설정 ──────────────────────────────────
    st.markdown("#### 📅 공통 조회 설정")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        date_mode = st.radio("조회 방식", ["기간 지정", "최신 N건"], horizontal=True,
                             key="t2_mode")
    with cc2:
        if date_mode == "기간 지정":
            d_from = st.date_input("시작일", date.today()-timedelta(days=90), key="t2_from")
            d_to   = st.date_input("종료일", date.today(), key="t2_to")
            date_params = f"UPDT_DTM={d_from.strftime('%Y%m%d')}~{d_to.strftime('%Y%m%d')}"
        else:
            n_rows     = st.number_input("최신 N건", 10, 1000, 100, 10, key="t2_n")
            date_params = ""
    with cc3:
        st.markdown("<br>", unsafe_allow_html=True)
        kw2 = st.text_input("검색 키워드 (선택)", placeholder="업소명, 식품명 등", key="t2_kw")

    st.markdown("---")

    # ── 3개 섹션 병렬 배치 ───────────────────────────────
    s1, s2, s3 = st.columns(3)

    # ▶ 건강기능식품
    with s1:
        st.markdown("##### 💊 건강기능식품")
        max_hf = n_rows if date_mode == "최신 N건" else 500
        if st.button("조회", key="hf_run", use_container_width=True):
            import urllib.parse
            p = f"PRDLST_NM={urllib.parse.quote(kw2,safe='')}" if kw2 else ""
            with st.spinner("조회 중…"):
                rows, err = fetch_all(SVC["건강기능식품"], p, max_hf)
            if err and not rows:
                st.error(err)
            else:
                df = pd.DataFrame([{
                    "제품명": r.get("PRDLST_NM",""),
                    "제조사": r.get("BSSH_NM",""),
                    "유형":   r.get("PRDLST_DCNM",""),
                    "신고일": r.get("PRMS_DT",""),
                } for r in rows])
                st.caption(f"{len(df)}건")
                st.dataframe(df, use_container_width=True, height=300, hide_index=True)
                st.download_button(
                    "📥 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                    "건강기능식품.csv", key="hf_dl"
                )

    # ▶ 인허가업소
    with s2:
        st.markdown("##### 🏭 인허가 업소")
        max_biz = n_rows if date_mode == "최신 N건" else 500
        if st.button("조회", key="biz_run", use_container_width=True):
            import urllib.parse
            p = f"BSSH_NM={urllib.parse.quote(kw2,safe='')}" if kw2 else ""
            with st.spinner("조회 중…"):
                rows, err = fetch_all(SVC["인허가업소"], p, max_biz)
            if err and not rows:
                st.error(err)
            else:
                df = pd.DataFrame([{
                    "업소명":   r.get("BSSH_NM",""),
                    "업종":     r.get("INDUTY_NM",""),
                    "주소":     r.get("SITE_ADDR",""),
                    "인허가일": r.get("LCNS_DATE",""),
                    "상태":     r.get("BSSH_STTS_NM",""),
                } for r in rows])
                st.caption(f"{len(df)}건")
                st.dataframe(df, use_container_width=True, height=300, hide_index=True)
                st.download_button(
                    "📥 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                    "인허가업소.csv", key="biz_dl"
                )

    # ▶ 식품접객업
    with s3:
        st.markdown("##### 🍽️ 식품접객업")
        max_rest = n_rows if date_mode == "최신 N건" else 500
        if st.button("조회", key="rest_run", use_container_width=True):
            import urllib.parse
            p = f"BSSH_NM={urllib.parse.quote(kw2,safe='')}" if kw2 else ""
            with st.spinner("조회 중…"):
                rows, err = fetch_all(SVC["식품접객업"], p, max_rest)
            if err and not rows:
                st.error(err)
            else:
                df = pd.DataFrame([{
                    "업소명":   r.get("BSSH_NM",""),
                    "업종":     r.get("INDUTY_NM",""),
                    "주소":     r.get("SITE_ADDR",""),
                    "인허가일": r.get("LCNS_DATE",""),
                    "상태":     r.get("BSSH_STTS_NM",""),
                } for r in rows])
                st.caption(f"{len(df)}건")
                st.dataframe(df, use_container_width=True, height=300, hide_index=True)
                st.download_button(
                    "📥 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                    "식품접객업.csv", key="rest_dl"
                )

    st.markdown("---")

    # ▶ 레시피 DB (전체 폭)
    st.markdown("##### 🍳 조리식품 레시피 DB")
    rc1, rc2 = st.columns([4, 1])
    with rc1:
        recipe_kw = st.text_input("레시피 검색어", placeholder="예: 김치찌개, 비빔밥",
                                   key="rcp_kw")
    with rc2:
        st.markdown("<br>", unsafe_allow_html=True)
        max_rcp = n_rows if date_mode == "최신 N건" else 200

    if st.button("🍳 레시피 조회", use_container_width=True, key="rcp_run"):
        import urllib.parse
        p = f"RCP_NM={urllib.parse.quote(recipe_kw,safe='')}" if recipe_kw else ""
        with st.spinner("레시피 조회 중…"):
            rows, err = fetch_all(SVC["레시피"], p, max_rcp)
        if err and not rows:
            st.error(err)
        else:
            df = pd.DataFrame([{
                "레시피명":   r.get("RCP_NM",""),
                "종류":       r.get("RCP_PAT2",""),
                "칼로리":     r.get("INFO_ENG",""),
                "탄수화물(g)":r.get("INFO_CAR",""),
                "단백질(g)":  r.get("INFO_PRO",""),
                "지방(g)":    r.get("INFO_FAT",""),
                "나트륨(mg)": r.get("INFO_NA",""),
                "재료":       r.get("RCP_PARTS_DTLS",""),
            } for r in rows])
            st.caption(f"{len(df)}건")
            st.dataframe(df, use_container_width=True, height=350, hide_index=True)

            # 상세 보기
            if not df.empty:
                sel_rcp = st.selectbox("레시피 상세 보기", df["레시피명"].tolist(), key="rcp_sel")
                sel_row = next((r for r in rows if r.get("RCP_NM","") == sel_rcp), None)
                if sel_row:
                    c1r, c2r = st.columns(2)
                    with c1r:
                        st.markdown(f"**재료:** {sel_row.get('RCP_PARTS_DTLS','')}")
                        st.markdown(f"**만드는 법:**")
                        for i in range(1, 21):
                            step = sel_row.get(f"MANUAL0{i:02d}","").strip()
                            if step:
                                st.markdown(f"{i}. {step}")
                    with c2r:
                        img = sel_row.get("ATT_FILE_NO_MAIN","")
                        if img:
                            st.image(img, use_container_width=True)

            st.download_button(
                "📥 레시피 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                "레시피.csv", key="rcp_dl"
            )

    st.markdown("---")

    # ▶ 회수·판매중지 현황 (독립 조회)
    st.markdown("##### 🚨 회수·판매중지 현황")
    rv1, rv2 = st.columns([4, 1])
    with rv1:
        recall_kw = st.text_input("검색어 (제품명 또는 원재료명)",
                                   placeholder="예: OO음료, 식용색소",
                                   key="rec_kw")
    with rv2:
        st.markdown("<br>", unsafe_allow_html=True)
        max_rec = n_rows if date_mode == "최신 N건" else 500

    if st.button("🚨 회수·판매중지 조회", use_container_width=True, key="rec_run",
                 type="primary"):
        import urllib.parse
        p = f"PRDLST_NM={urllib.parse.quote(recall_kw,safe='')}" if recall_kw else ""
        with st.spinner("조회 중…"):
            rows, err = fetch_all(SVC["회수판매중지"], p, max_rec)
        if err and not rows:
            st.error(err)
        elif not rows:
            st.success("✅ 해당 회수·판매중지 정보 없음")
        else:
            df = pd.DataFrame([{
                "제품명":     r.get("PRDLST_NM",""),
                "제조사":     r.get("BSSH_NM",""),
                "회수사유":   r.get("RECALL_REASON",""),
                "회수일자":   r.get("RECALL_DATE","") or r.get("RTRCL_DATE",""),
                "처분유형":   r.get("DSPS_TP_NM",""),
                "처분일자":   r.get("DSPS_DATE",""),
            } for r in rows])
            st.error(f"🚨 {len(df)}건 회수·판매중지 정보 조회됨")
            st.dataframe(df, use_container_width=True, height=300, hide_index=True)
            st.download_button(
                "📥 회수목록 CSV",
                df.to_csv(index=False).encode("utf-8-sig"),
                "회수판매중지.csv", key="rec_dl"
            )
            # 세션에 저장 (Tab1 교차체크용)
            st.session_state.recall_df     = pd.DataFrame(rows)
            st.session_state.recall_loaded = True
