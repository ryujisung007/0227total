"""
식품안전나라 품목제조보고 조회 v7.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• trust_env=False (Windows 시스템 프록시 우회)
• IPv4 강제 (IPv6 타임아웃 방지)
• curl fallback (UTF-8 인코딩)
• 마침표(.) 보존 인코딩 + fallback
• API 키 사이드바 직접 입력
• 연결 진단 기능
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from collections import Counter
import re, time, json, os, socket, subprocess, urllib.parse


# ══════════════════════════════════════════════════════
#  IPv4 강제 — requests가 IPv6 시도 → 타임아웃 방지
# ══════════════════════════════════════════════════════
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_only


# ══════════════════════════════════════════════════════
#  상수 & 설정
# ══════════════════════════════════════════════════════
SERVICE_ID = "I1250"
API_BASE   = "http://openapi.foodsafetykorea.go.kr/api"

FOOD_TYPES = {
    "당류 및 잼류": [
        "과당", "기타과당", "설탕", "기타설탕", "포도당",
        "올리고당", "올리고당가공품", "물엿", "기타엿", "당시럽류",
        "덱스트린", "잼", "기타잼", "당류가공품", "당절임",
    ],
    "과자.빵.초콜릿류": [
        "과자", "캔디류", "추잉껌", "빵류", "떡류",
        "만두", "만두피",
        "초콜릿", "준초콜릿", "화이트초콜릿", "밀크초콜릿",
        "초콜릿가공품", "기타 코코아가공품",
        "코코아매스", "코코아버터", "코코아분말",
    ],
    "유제품 및 빙과류": [
        "우유", "강화우유", "저지방우유", "환원유", "유당분해우유",
        "가공유", "유산균첨가우유", "농축우유", "탈지농축우유",
        "유청", "유청단백분말", "유크림", "가공유크림",
        "버터", "가공버터", "버터오일", "버터유", "발효버터유",
        "치즈", "가공치즈", "모조치즈",
        "전지분유", "탈지분유", "가당분유", "혼합분유",
        "가당연유", "가공연유", "가당탈지연유",
        "아이스크림", "아이스크림믹스", "저지방아이스크림",
        "저지방아이스크림믹스", "아이스밀크", "아이스밀크믹스",
        "샤베트", "샤베트믹스",
        "비유지방아이스크림", "비유지방아이스크림믹스",
        "빙과", "식용얼음",
    ],
    "알가공품 및 발효유": [
        "발효유", "농후발효유", "크림발효유", "농후크림발효유", "발효유분말",
        "전란액", "난황액", "난백액",
        "전란분", "난황분", "난백분",
        "알가열제품", "피단", "알함유가공품",
    ],
    "식육 및 수산가공품": [
        "햄", "생햄", "프레스햄", "혼합소시지", "소시지",
        "발효소시지", "베이컨류", "건조저장육류",
        "양념육", "갈비가공품", "분쇄가공육제품",
        "식육추출가공품", "식육함유가공품", "포장육", "식육케이싱",
        "어묵", "어육소시지", "어육살", "연육", "어육반제품",
        "조미건어포", "건어포", "가공김",
        "한천", "기타 어육가공품", "기타 건포류", "기타 수산물가공품",
    ],
    "음료 및 다류": [
        "과.채주스", "과.채음료", "농축과.채즙",
        "탄산음료", "탄산수",
        "두유", "가공두유", "원액두유",
        "인삼.홍삼음료", "혼합음료", "유산균음료",
        "음료베이스", "효모음료",
        "커피", "침출차", "고형차", "액상차",
    ],
    "식용유지": [
        "콩기름", "옥수수기름", "채종유", "미강유",
        "참기름", "추출참깨유", "들기름", "추출들깨유",
        "홍화유", "해바라기유", "올리브유", "땅콩기름",
        "팜유", "팜올레인유", "팜스테아린유", "팜핵유", "야자유",
        "식용우지", "식용돈지", "어유",
        "기타식물성유지", "기타동물성유지",
        "가공유지", "식물성크림", "마가린", "쇼트닝", "향미유",
    ],
    "조미식품 및 장류": [
        "한식간장", "양조간장", "혼합간장", "산분해간장", "효소분해간장",
        "한식된장", "된장", "고추장", "춘장", "청국장", "혼합장", "기타장류",
        "한식메주", "개량메주",
        "발효식초", "희석초산",
        "소스", "토마토케첩", "카레(커리)", "복합조미식품",
        "마요네즈", "천연향신료", "향신료조제품",
        "고춧가루", "실고추",
        "천일염", "재제소금", "정제소금", "가공소금", "태움.용융소금",
    ],
    "특수영양 및 의료식": [
        "영아용 조제유", "영아용 조제식", "성장기용 조제유", "성장기용 조제식",
        "영.유아용 이유식", "영.유아용 특수조제식품",
        "체중조절용 조제식품", "임산.수유부용 식품",
        "일반 환자용 균형영양조제식품",
        "당뇨환자용 영양조제식품", "신장질환자용 영양조제식품",
        "암환자용 영양조제식품", "고혈압환자용 영양조제식품",
        "간경변환자용 영양조제식품", "폐질환자용 영양조제식품",
        "선천성대사질환자용조제식품", "유단백가수분해식품",
    ],
    "기타 가공식품": [
        "생면", "숙면", "건면", "유탕면",
        "두부", "가공두부", "유바", "묵류",
        "신선편의식품", "즉석섭취식품", "즉석조리식품",
        "간편조리세트", "시리얼류",
        "곡류가공품", "두류가공품", "서류가공품",
        "전분가공품", "전분",
        "땅콩 또는 견과류가공품", "땅콩버터",
        "과.채가공품", "절임식품", "조림류",
        "김치", "젓갈", "조미액젓",
        "곤충가공식품",
        "벌꿀", "사양벌꿀", "로열젤리",
        "효모식품", "효소식품",
        "생식제품", "기타가공품",
    ],
    "주류": [
        "탁주", "약주", "청주", "맥주", "과실주",
        "소주", "위스키", "브랜디", "리큐르",
        "일반증류주", "주정", "기타 주류",
    ],
}

COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형", "BSSH_NM": "제조사",
    "PRMS_DT": "보고일자", "RAWMTRL_NM": "주요원재료",
    "POG_DAYCNT": "유통기한", "PRODUCTION": "생산종료",
    "INDUTY_CD_NM": "업종", "LCNS_NO": "인허가번호",
    "PRDLST_REPORT_NO": "품목제조번호", "LAST_UPDT_DTM": "최종수정일",
    "HIENG_LNTRT_DVS_NM": "고열량저영양", "CHILD_CRTFC_YN": "어린이기호식품인증",
    "DISPOS": "제품형태", "FRMLC_MTRQLT": "포장재질",
}


# ══════════════════════════════════════════════════════
#  API 키 관리
# ══════════════════════════════════════════════════════
def _secret(*keys, default=""):
    try:
        for k in keys:
            v = st.secrets.get(k, "")
            if v:
                return v
    except Exception:
        pass
    return default


def get_food_api_key():
    return (st.session_state.get("_override_food_key", "")
            or _secret("FOOD_SAFETY_API_KEY")
            or "9171f7ffd72f4ffcb62f")


def get_gemini_key():
    return _secret("GOOGLE_API_KEY", "GEMINI_API_KEY",
                   "google_api_key", "GEMINI_KEY", "gemini_api_key")


# ══════════════════════════════════════════════════════
#  HTTP 클라이언트 (trust_env=False 핵심!)
# ══════════════════════════════════════════════════════
def _http(url: str, method="GET", **kwargs):
    """프록시 완전 우회 + 브라우저 헤더 세션"""
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    })
    return s.request(method, url, timeout=(10, 30),
                     proxies={"http": None, "https": None}, **kwargs)


def _api_get(url: str):
    """API GET → (dict, None) 또는 (None, error_msg)
    ① requests(IPv4+trust_env=False) → ② curl fallback
    """
    # ── 1차: requests ──
    try:
        r = _http(url)
        if r.status_code == 200:
            raw = r.text.strip()
            if raw and raw.startswith("{"):
                return r.json(), None
            return None, f"비정상 응답: {raw[:150]}"
        return None, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        pass  # curl로 넘어감
    except Exception as e:
        pass  # curl로 넘어감

    # ── 2차: curl fallback ──
    try:
        clean_env = {k: v for k, v in os.environ.items()
                     if "proxy" not in k.lower()}
        result = subprocess.run(
            ["curl", "-s", "-m", "30", "--connect-timeout", "10",
             "--noproxy", "*", "-4",
             "-H", "Accept: application/json", url],
            capture_output=True, text=True, timeout=35,
            encoding="utf-8", errors="replace", env=clean_env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout), None
        return None, f"curl code={result.returncode}"
    except FileNotFoundError:
        return None, "curl 미설치 + requests 타임아웃"
    except Exception as e:
        return None, f"모든 방법 실패: {e}"


# ══════════════════════════════════════════════════════
#  URL 빌더
# ══════════════════════════════════════════════════════
def _norm(s: str) -> str:
    return s.strip().replace("·", ".").replace(" ", "").lower()


def _build_base():
    """API 기본 URL (키 포함)"""
    return f"{API_BASE}/{get_food_api_key()}/{SERVICE_ID}/json"


def _encode_type(food_type: str, safe="."):
    """식품유형명 인코딩 (마침표 보존이 기본)"""
    return urllib.parse.quote(food_type.strip(), safe=safe)


# ══════════════════════════════════════════════════════
#  데이터 수집
# ══════════════════════════════════════════════════════
def fetch_food_data(food_type, top_n=100, prdlst_nm="",
                    prog_bar=None, status_text=None):
    base      = _build_base()
    t0        = time.time()
    norm_type = _norm(food_type)
    collected = []
    PAGE      = 1000

    enc_type   = _encode_type(food_type)
    params_str = f"PRDLST_DCNM={enc_type}"
    if prdlst_nm.strip():
        params_str += f"&PRDLST_NM={urllib.parse.quote(prdlst_nm.strip())}"

    # ── total_count 확인 ──
    probe = f"{base}/1/1/{params_str}"
    if status_text:
        status_text.markdown(f"📡 연결 확인 중…")

    data, err = _api_get(probe)
    if err:
        return [], f"API 연결 실패: {err}", 0, 0
    if SERVICE_ID not in data:
        return [], f"API 응답 오류: {json.dumps(data, ensure_ascii=False)[:300]}", 0, 0

    total = int(data[SERVICE_ID].get("total_count", 0))

    # 마침표 유형인데 0건이면 인코딩 전환 재시도
    if total == 0 and "." in food_type:
        alt_enc    = _encode_type(food_type, safe="")
        alt_params = f"PRDLST_DCNM={alt_enc}"
        if prdlst_nm.strip():
            alt_params += f"&PRDLST_NM={urllib.parse.quote(prdlst_nm.strip())}"
        d2, e2 = _api_get(f"{base}/1/1/{alt_params}")
        if d2 and SERVICE_ID in d2:
            t2 = int(d2[SERVICE_ID].get("total_count", 0))
            if t2 > 0:
                total, params_str = t2, alt_params

    if total == 0:
        code_info = data[SERVICE_ID].get("RESULT", {})
        return [], f"'{food_type}' 0건 (응답: {code_info})", 0, 0

    if status_text:
        status_text.markdown(
            f"📡 **{food_type}** 전체 {total:,}건 → 최신 {min(top_n, total)}건 수집")

    # ── 페이지네이션 ──
    cursor, page = 1, 0
    while cursor <= total and len(collected) < top_n:
        p_s, p_e = cursor, min(cursor + PAGE - 1, total)
        url = f"{base}/{p_s}/{p_e}/{params_str}"

        pct = min(len(collected) / max(top_n, 1), 0.99)
        if prog_bar:
            prog_bar.progress(pct)
        if status_text:
            el = time.time() - t0
            bar = "█" * (int(pct * 100) // 5)
            status_text.markdown(
                f"`{bar}{'░' * (20 - len(bar))}` **{int(pct*100)}%** "
                f"📄 {page+1}p ✅ {len(collected)}건 ⏱ {el:.0f}초")

        d, e = _api_get(url)
        if e:
            cursor += PAGE; page += 1; time.sleep(0.3); continue
        if SERVICE_ID not in d:
            break

        res  = d[SERVICE_ID]
        code = res.get("RESULT", {}).get("CODE", "")
        if code == "INFO-300":
            return [], f"인증키 오류: {res['RESULT']['MSG']}", total, page
        if code != "INFO-000":
            break

        for row in res.get("row", []):
            if _norm(row.get("PRDLST_DCNM", "")) == norm_type:
                collected.append(row)

        page += 1
        if len(collected) >= top_n:
            break
        cursor += PAGE
        time.sleep(0.2)

    if not collected:
        return [], "수집된 데이터 없음", total, page

    collected.sort(
        key=lambda r: r.get("LAST_UPDT_DTM") or r.get("PRMS_DT") or "0",
        reverse=True)

    elapsed = time.time() - t0
    return collected[:top_n], f"{page}p | {elapsed:.1f}초 | 전체 {total:,}건", total, page


def fetch_multiple(types_list, per_type):
    all_rows, status = [], {}
    prog = st.progress(0.0)
    stxt = st.empty()
    for i, ft in enumerate(types_list):
        prog.progress((i + 1) / len(types_list))
        stxt.markdown(f"📡 **{ft}** 조회 중… ({i+1}/{len(types_list)})")
        rows, msg, total, _ = fetch_food_data(ft, top_n=per_type)
        status[ft] = {"msg": msg, "total": total,
                      "fetched": len(rows) if rows else 0}
        if rows:
            all_rows.extend(rows)
        time.sleep(0.2)
    prog.empty(); stxt.empty()
    return all_rows, status


def to_df(rows):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})
    if "보고일자" in df.columns:
        df["보고일자"] = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════
#  차트
# ══════════════════════════════════════════════════════
def render_charts(df, food_type):
    st.markdown("### 📊 데이터 분석")
    c1, c2 = st.columns(2)
    if "제조사" in df.columns:
        with c1:
            mc = df["제조사"].value_counts().head(15)
            fig = px.bar(x=mc.values, y=mc.index, orientation="h",
                         title="제조사별 제품 수 (상위 15)",
                         color=mc.values, color_continuous_scale="Blues",
                         labels={"x": "제품 수", "y": "제조사"})
            fig.update_layout(height=400, showlegend=False,
                              yaxis=dict(autorange="reversed"))
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)
    if "보고일자_dt" in df.columns:
        with c2:
            tmp = df.dropna(subset=["보고일자_dt"]).copy()
            if not tmp.empty:
                tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
                mo = tmp["연월"].value_counts().sort_index().tail(24)
                fig2 = px.area(x=mo.index, y=mo.values,
                               title="월별 신규 보고 건수 (최근 24개월)",
                               labels={"x": "연월", "y": "건수"})
                fig2.update_traces(fill="tozeroy", line_color="#1975BC")
                fig2.update_layout(height=400)
                st.plotly_chart(fig2, use_container_width=True)
    c3, c4 = st.columns(2)
    if "생산종료" in df.columns:
        with c3:
            pc = df["생산종료"].value_counts()
            fig3 = px.pie(values=pc.values, names=pc.index, title="생산종료 현황",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig3.update_layout(height=320)
            st.plotly_chart(fig3, use_container_width=True)
    if "제조사" in df.columns:
        with c4:
            top10  = df["제조사"].value_counts().head(10)
            others = max(0, len(df) - top10.sum())
            labels = list(top10.index) + (["기타"] if others else [])
            values = list(top10.values) + ([others] if others else [])
            fig4 = px.pie(values=values, names=labels, title="제조사 점유율 (상위 10)",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig4.update_layout(height=320)
            st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════
#  AI 분석 (Gemini)
# ══════════════════════════════════════════════════════
GEMINI_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash",
                 "gemini-1.5-pro", "gemini-1.5-flash"]


def _gemini(prompt, api_key):
    BASE = "https://generativelanguage.googleapis.com/v1/models"
    s = requests.Session()
    s.trust_env = False
    last_err = ""
    for model in GEMINI_MODELS:
        try:
            r = s.post(f"{BASE}/{model}:generateContent?key={api_key}",
                       headers={"Content-Type": "application/json"},
                       json={"contents": [{"parts": [{"text": prompt}]}]},
                       timeout=60)
            if r.status_code == 400:
                raise RuntimeError(f"프롬프트 오류: {r.json().get('error',{}).get('message','')}")
            if r.status_code in (429, 404) or "no longer available" in r.text:
                last_err = f"{model}: {r.status_code}"; continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except RuntimeError:
            raise
        except Exception as e:
            last_err = f"{model}: {e}"; continue
    raise RuntimeError(f"모든 모델 실패: {last_err}")


def _ctx(df, food_type):
    monthly = {}
    if "보고일자_dt" in df.columns:
        tmp = df.dropna(subset=["보고일자_dt"]).copy()
        if not tmp.empty:
            tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
            monthly = tmp["연월"].value_counts().sort_index().tail(12).to_dict()
    maker_top = df["제조사"].value_counts().head(5).to_dict() if "제조사" in df.columns else {}
    maker_n   = df["제조사"].nunique() if "제조사" in df.columns else "N/A"
    recent    = df[[c for c in ["제품명","보고일자"] if c in df.columns]].head(10).to_dict("records") if "제품명" in df.columns else []
    kw_freq   = dict(Counter(re.findall(r"[가-힣a-zA-Z]{2,}",
                     " ".join(df["제품명"].dropna().astype(str)))).most_common(15)) if "제품명" in df.columns else {}
    return dict(food_type=food_type, total=len(df), monthly=monthly,
                maker_top=maker_top, maker_n=maker_n, recent=recent, kw_freq=kw_freq)


def render_ai_section(df, food_type, api_key):
    st.markdown("---")
    st.markdown("## 🤖 AI 연구원 분석")
    if not api_key:
        st.warning("**Gemini API 키 없음**\n\n`.streamlit/secrets.toml`:\n```toml\nGOOGLE_API_KEY = \"AIza...\"\n```")
        return
    st.info(f"모델: **gemini-2.5-pro** 우선 | 대상: **{food_type}** {len(df)}건")
    if not st.button("🔬 AI 분석 시작", key="btn_ai", type="primary", use_container_width=True):
        return
    ctx = _ctx(df, food_type)
    prefix = (f"식품 R&D 전문가로서 아래 데이터를 분석하세요.\n"
              f"카테고리: {food_type} | 조회건수: {ctx['total']}건 | 제조사: {ctx['maker_n']}개\n"
              f"월별추이(최근12개월): {ctx['monthly']}\n주요제조사(상위5): {ctx['maker_top']}\n"
              f"최신제품(10건): {ctx['recent']}\n키워드빈도(상위15): {ctx['kw_freq']}\n\n")
    analyses = [
        ("📈 시장 트렌드 분석",    prefix + "한국어로 분석 (각 3문장):\n1. 시장 성장성\n2. 경쟁 구도\n3. 출시 패턴\n4. R&D 시사점"),
        ("🍋 플레이버 & 원료 트렌드", prefix + "한국어로 분석 (각 3문장):\n1. 주요 플레이버\n2. 기능성 원료\n3. 신흥 플레이버\n4. 포뮬레이션 방향"),
        ("🧪 추천 레시피 3종",     prefix + f"{food_type} 신제품 레시피 3종:\n- 제품명/컨셉/타겟\n- 원료 배합비(%)\n- 예상 규격(pH/Brix/칼로리)\n- 차별화 포인트"),
        ("💡 종합 R&D 인사이트",   prefix + "한국어 (각 3문장):\n1. 시장 기회\n2. 리스크\n3. 즉시 출시 컨셉(6개월)\n4. 중장기 R&D(1~3년)"),
    ]
    all_results = {}
    for title, prompt in analyses:
        st.markdown(f"#### {title}")
        box = st.empty(); box.info("분석 중…")
        try:
            text = _gemini(prompt, api_key)
            all_results[title] = text; box.markdown(text)
        except Exception as e:
            all_results[title] = f"❌ {e}"; box.error(f"❌ {e}")
    if all_results:
        full = "\n\n---\n\n".join(f"{t}\n\n{c}" for t, c in all_results.items())
        st.download_button("📥 AI 분석 다운로드 (TXT)", full.encode("utf-8"),
                           f"{food_type}_AI분석_{datetime.now():%Y%m%d_%H%M}.txt",
                           "text/plain", use_container_width=True)


# ══════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════
st.set_page_config(page_title="품목제조보고 조회", page_icon="🏭", layout="wide")
st.markdown("""<style>
[data-testid="stSidebar"]{background:#f8f9fb}
div[data-testid="stMetric"]{background:#f0f2f5;border-radius:10px;padding:12px}
</style>""", unsafe_allow_html=True)

# ── 사이드바 ──
with st.sidebar:
    st.markdown("## 🔍 조회 설정")
    st.markdown("---")
    mode = st.radio("조회 방식", ["📋 단일 유형 조회", "📊 복수 유형 비교"])
    st.markdown("---")

    if mode == "📋 단일 유형 조회":
        category  = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
        food_type = st.selectbox("식품유형", FOOD_TYPES[category])
        prdlst_nm = st.text_input("🔍 제품명 검색 (선택)",
                                  placeholder="예: 제로, 비타민, 콜라겐…")
        count = st.slider("조회 건수", 10, 300, 100, step=10)
    else:
        st.markdown("**비교할 유형 선택:**")
        selected_types = []
        for cat, types in FOOD_TYPES.items():
            with st.expander(cat, expanded=(cat == "음료 및 다류")):
                for t in types:
                    if st.checkbox(t, key=f"cb_{t}",
                                   value=t in ["혼합음료", "과.채주스", "탄산음료"]):
                        selected_types.append(t)
        per_type = st.slider("유형별 조회 건수", 10, 50, 20, step=5)

    st.markdown("---")
    st.markdown("### 🔑 식품안전나라 API")
    _fk = get_food_api_key()
    if _secret("FOOD_SAFETY_API_KEY"):
        st.success(f"API 키 연결됨: `{_fk[:6]}…`", icon="✅")
    else:
        st.warning("기본 키 사용 중 (만료 가능)", icon="⚠️")
        st.caption("[식품안전나라](https://www.foodsafetykorea.go.kr/api/openApiInfo.do)에서 발급")
        _ik = st.text_input("API 키 직접 입력", type="password",
                            key="food_api_input", placeholder="발급받은 키 붙여넣기")
        if _ik.strip():
            st.session_state["_override_food_key"] = _ik.strip()
            st.session_state.pop("working_base_url", None)
            st.success("키 적용됨!")

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### 🤖 Gemini 설정")
    if get_gemini_key():
        st.success("API 키 연결됨", icon="✅")
    else:
        st.warning("GOOGLE_API_KEY 없음", icon="⚠️")
        st.caption('secrets.toml: GOOGLE_API_KEY = "AIza..."')
    gemini_key = get_gemini_key()

    st.markdown("---")
    _c1, _c2 = st.columns(2)
    with _c1:
        if st.button("🔄 캐시 초기화", use_container_width=True):
            st.cache_data.clear()
            st.session_state.pop("working_base_url", None)
            st.success("완료")
    with _c2:
        if st.button("🩺 연결 테스트", use_container_width=True):
            st.session_state.pop("working_base_url", None)
            test_url = f"{API_BASE}/{get_food_api_key()}/{SERVICE_ID}/json/1/1"
            d, e = _api_get(test_url)
            if d and SERVICE_ID in d:
                st.success(f"✅ 성공 (total={d[SERVICE_ID].get('total_count','?')})")
            else:
                st.error(f"❌ {e}")
            prx = {k: v for k, v in os.environ.items() if "proxy" in k.lower()}
            if prx:
                st.warning(f"프록시 감지: {prx}")

    st.caption("📡 식품안전나라 I1250 · v7.0")


# ── 세션 초기화 ──
for _k, _v in {"result_df": None, "result_label": "", "result_total": 0,
               "result_src": "", "result_mode": "", "status_msgs": {}}.items():
    st.session_state.setdefault(_k, _v)


# ── 메인 ──
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("---")

if run:
    if mode == "📋 단일 유형 조회":
        t0 = time.time()
        label = f"**{food_type}**" + (f" / 제품명: **{prdlst_nm}**" if prdlst_nm.strip() else "")
        st.info(f"📡 {label} 조회 중…")
        prog = st.progress(0.0); stxt = st.empty()
        rows, src, total, _ = fetch_food_data(
            food_type, top_n=count, prdlst_nm=prdlst_nm,
            prog_bar=prog, status_text=stxt)
        elapsed = time.time() - t0
        prog.empty(); stxt.empty()
        if not rows:
            st.error(f"❌ 조회 실패: {src}")
        else:
            df = to_df(rows)
            rl = food_type + (f" [{prdlst_nm}]" if prdlst_nm.strip() else "")
            st.session_state.update(
                result_df=df, result_label=rl, result_total=total,
                result_src=f"✅ **{len(df)}건** | {elapsed:.1f}초 | {src}",
                result_mode="single", status_msgs={})
    else:
        if not selected_types:
            st.warning("⚠️ 유형을 1개 이상 선택하세요.")
        else:
            t0 = time.time()
            all_rows, status = fetch_multiple(selected_types, per_type)
            elapsed = time.time() - t0
            df = to_df(all_rows)
            label = ", ".join(selected_types[:3]) + ("…" if len(selected_types) > 3 else "")
            st.session_state.update(
                result_df=df, result_label=label, result_total=0,
                result_src=f"✅ {len(selected_types)}개 유형 | {elapsed:.1f}초 | {len(df)}건",
                result_mode="multi", status_msgs=status)

df     = st.session_state["result_df"]
r_mode = st.session_state["result_mode"]
r_lbl  = st.session_state["result_label"]
r_tot  = st.session_state["result_total"]
r_src  = st.session_state["result_src"]
smsgs  = st.session_state["status_msgs"]

if df is None:
    st.info("👈 사이드바에서 식품유형을 선택하고 **[조회 실행]**을 누르세요.")
elif df.empty:
    st.warning(f"⚠️ **'{r_lbl}'** 결과 없음")
    if smsgs:
        st.markdown("**📋 유형별 상세:**")
        for ft, info in smsgs.items():
            st.code(f"{ft}: {info.get('msg','')} (수집={info['fetched']}, 전체={info['total']})")
    _k = get_food_api_key()
    st.info(f"🔑 현재 키: `{_k[:6]}…{_k[-4:]}` — "
            f"만료 시 [식품안전나라](https://www.foodsafetykorea.go.kr/api/openApiInfo.do)에서 재발급")
else:
    st.success(r_src)
    if smsgs:
        cols = st.columns(min(len(smsgs), 6))
        for i, (ft, info) in enumerate(smsgs.items()):
            with cols[i % len(cols)]:
                st.metric(ft, f"{info['fetched']}건", f"전체 {info['total']:,}건")
        st.markdown("---")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("조회 결과", f"{len(df)}건")
    if r_mode == "single":
        m2.metric("전체 DB", f"{r_tot:,}건")
        m3.metric("식품유형", r_lbl)
    else:
        m2.metric("유형 수", f"{df['식품유형'].nunique()}개" if "식품유형" in df.columns else "-")
        m3.metric("카테고리", r_lbl)
    if "제조사" in df.columns:
        m4.metric("제조사 수", f"{df['제조사'].nunique()}개")

    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

    with tab1:
        ca, cb = st.columns(2)
        with ca:
            kw = st.text_input("🔎 검색", placeholder="제품명·제조사·원재료", key="kw")
        with cb:
            makers = (["전체"] + sorted(df["제조사"].dropna().unique().tolist())
                      if "제조사" in df.columns else ["전체"])
            sel_mk = st.selectbox("제조사 필터", makers, key="mk")
        fdf = df.copy()
        if kw:
            fdf = fdf[fdf.apply(lambda r: kw.lower() in str(r).lower(), axis=1)]
        if "제조사" in df.columns and sel_mk != "전체":
            fdf = fdf[fdf["제조사"] == sel_mk]
        show = [c for c in ["제품명","식품유형","제조사","보고일자",
                             "주요원재료","유통기한","생산종료"] if c in fdf.columns]
        st.dataframe(fdf[show].reset_index(drop=True),
                     use_container_width=True, height=480)
        st.caption(f"총 {len(fdf)}건")

    with tab2:
        render_charts(df, r_lbl)

    with tab3:
        st.dataframe(df, use_container_width=True, height=480)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 CSV 다운로드", csv,
                           f"{r_lbl}_{datetime.now():%Y%m%d}.csv",
                           "text/csv", use_container_width=True)

    render_ai_section(df, r_lbl, gemini_key)
