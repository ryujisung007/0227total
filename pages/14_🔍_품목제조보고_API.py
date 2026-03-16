"""
식품안전나라 품목제조보고 조회 v5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
조회 전략: 병렬 스캔 폐기 → 단일 필터 요청 1회
  URL: /api/KEY/I1250/json/1/N/PRDLST_DCNM=유형명
  서버가 필터링해서 반환 → 전체 DB 순회 불필요
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from collections import Counter
import re
import time

import json

GENAI_AVAILABLE = True  # REST API 직접 호출 — SDK 불필요


# ══════════════════════════════════════════════════════
#  설정 — Lazy loading (앱 시작 후 secrets 접근)
# ══════════════════════════════════════════════════════
def _secret(*keys, default=""):
    """st.secrets를 lazy하게 읽음 (모듈 최상단에서 호출 금지)"""
    try:
        for k in keys:
            v = st.secrets.get(k, "")
            if v:
                return v
    except Exception:
        pass
    return default

def get_food_api_key():
    return _secret("FOOD_SAFETY_API_KEY", default="9171f7ffd72f4ffcb62f")

def get_gemini_key():
    return _secret("GOOGLE_API_KEY", "GEMINI_API_KEY", "google_api_key",
                   "GEMINI_KEY", "gemini_api_key")

SERVICE_ID = "I1250"

def get_base_url():
    return f"http://openapi.foodsafetykorea.go.kr/api/{get_food_api_key()}/{SERVICE_ID}/json"

GEMINI_MODELS = ["gemini-2.0-flash-001"]  # REST API 정식 모델명

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
TYPE_TO_CAT = {t: c for c, ts in FOOD_TYPES.items() for t in ts}

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
#  조회 — API 명세 기반 (PRDLST_DCNM + CHNG_DT 파라미터)
# ══════════════════════════════════════════════════════
def _norm(s: str) -> str:
    return s.strip().replace("·", ".").replace(" ", "").lower()


def _safe_get(url: str):
    """GET 요청 → (dict | None, error_msg | None)"""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        return None, "응답 시간 초과 (30초)"
    except requests.exceptions.ConnectionError:
        return None, "서버 연결 실패"
    except Exception as e:
        return None, f"HTTP 오류: {e}"
    raw = r.text.strip()
    if not raw:
        return None, f"빈 응답 (HTTP {r.status_code})"
    try:
        return r.json(), None
    except Exception:
        return None, f"JSON 파싱 실패: {raw[:200]}"


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_with_params(base_url: str, p_s: int, p_e: int, params_str: str):
    """파라미터 포함 페이지 단위 캐시"""
    url = f"{base_url}/{p_s}/{p_e}"
    if params_str:
        url += f"/{params_str}"
    return _safe_get(url)


def fetch_food_data(food_type: str, top_n: int = 100, max_pages: int = 50,
                    chng_dt: str = "",
                    prog_bar=None, status_text=None):
    """
    API 명세 기반 조회 전략:
      1순위: PRDLST_DCNM + CHNG_DT 파라미터 → 서버 필터링 (빠름)
      2순위: PRDLST_DCNM만 → 서버 필터링
      3순위: 전체 스캔 + 클라이언트 필터 (fallback)

    URL 형식 (API 명세):
      /api/KEY/I1250/json/1/100/PRDLST_DCNM=혼합음료&CHNG_DT=20230101
    """
    import urllib.parse
    base_url  = get_base_url()
    t_start   = time.time()
    norm_type = _norm(food_type)
    page_size = 1000

    # ── 파라미터 문자열 구성 ──
    # API 명세: 추가인자는 URL 경로에 변수명=값&변수명=값 형식
    encoded_type = urllib.parse.quote(food_type.strip(), safe="")
    param_variants = []

    if chng_dt:
        param_variants.append(
            f"PRDLST_DCNM={encoded_type}&CHNG_DT={chng_dt}"
        )
    param_variants.append(f"PRDLST_DCNM={encoded_type}")
    param_variants.append("")   # fallback: 전체 스캔

    for params_str in param_variants:
        label = ("서버필터+날짜" if "CHNG_DT" in params_str
                 else "서버필터" if "PRDLST_DCNM" in params_str
                 else "전체스캔")

        if status_text:
            status_text.markdown(f"📡 **{label}** 방식으로 조회 중…")

        # total_count 파악
        url_probe = f"{base_url}/1/1"
        if params_str:
            url_probe += f"/{params_str}"
        data, err = _safe_get(url_probe)
        if err or SERVICE_ID not in data:
            continue

        total = int(data[SERVICE_ID].get("total_count", 0))
        if total == 0:
            continue

        # 서버필터가 작동하는지 검증 (첫 페이지 샘플)
        if params_str:
            d_check, _ = _fetch_with_params(base_url, 1, 5, params_str)
            if d_check and SERVICE_ID in d_check:
                rows_check = d_check[SERVICE_ID].get("row", [])
                if rows_check:
                    matched = [r for r in rows_check
                               if _norm(r.get("PRDLST_DCNM","")) == norm_type]
                    match_rate = len(matched) / len(rows_check)
                    if match_rate < 0.5:
                        # 서버필터 미작동 → 다음 방식 시도
                        if "PRDLST_DCNM" in params_str:
                            continue

        # 페이지네이션으로 top_n건 수집
        collected  = []
        pages_done = 0
        cursor     = 1

        while cursor <= total and pages_done < max_pages:
            p_s = cursor
            p_e = min(cursor + page_size - 1, total)

            elapsed = time.time() - t_start
            pct     = min(pages_done / max(max_pages, 1), 0.99)
            if prog_bar:
                prog_bar.progress(pct)
            if status_text:
                status_text.markdown(
                    f"📡 **{label}** | 페이지 {pages_done+1} | "
                    f"수집 {len(collected)}건 | {elapsed:.0f}초"
                )

            d, err = _fetch_with_params(base_url, p_s, p_e, params_str)
            if err:
                cursor += page_size
                pages_done += 1
                time.sleep(0.2)
                continue

            if SERVICE_ID not in d:
                cursor += page_size
                pages_done += 1
                continue

            res  = d[SERVICE_ID]
            code = res.get("RESULT", {}).get("CODE", "")
            if code == "INFO-200":
                break
            if code != "INFO-000":
                break

            rows = res.get("row", [])
            for row in rows:
                if not params_str:
                    # 전체스캔: 클라이언트 필터
                    if _norm(row.get("PRDLST_DCNM","")) == norm_type:
                        collected.append(row)
                else:
                    # 서버필터: 검증만
                    if _norm(row.get("PRDLST_DCNM","")) == norm_type:
                        collected.append(row)

            if len(collected) >= top_n:
                break

            cursor     += page_size
            pages_done += 1
            time.sleep(0.15)

        if collected:
            # LAST_UPDT_DTM → PRMS_DT 순으로 최신순 정렬
            collected.sort(
                key=lambda r: (r.get("LAST_UPDT_DTM","") or
                               r.get("PRMS_DT","") or "0"),
                reverse=True
            )
            elapsed = time.time() - t_start
            src_msg = (f"{label} | {pages_done}페이지 | "
                       f"전체 {total:,}건 | {elapsed:.1f}초")
            return collected[:top_n], src_msg, total, pages_done

    return [], "조회 결과 없음 — 식품유형명 확인 필요", 0, 0


def fetch_multiple(types_list: list, per_type: int, max_pages: int,
                   chng_dt: str = ""):
    """복수 유형 순차 조회"""
    all_rows, status = [], {}
    prog        = st.progress(0.0)
    status_text = st.empty()
    for i, ft in enumerate(types_list):
        pct = (i + 1) / len(types_list)
        prog.progress(pct)
        status_text.markdown(f"📡 **{ft}** 조회 중… ({i+1}/{len(types_list)})")
        rows, msg, total, _ = fetch_food_data(
            ft, top_n=per_type, max_pages=max_pages, chng_dt=chng_dt
        )
        status[ft] = {
            "msg":     msg or "",
            "total":   total,
            "fetched": len(rows) if rows else 0,
        }
        if rows:
            all_rows.extend(rows)
        time.sleep(0.2)
    prog.empty()
    status_text.empty()
    return all_rows, status


def to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {k: v for k, v in COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    if "보고일자" in df.columns:
        df["보고일자"] = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════
#  차트
# ══════════════════════════════════════════════════════
def render_charts(df: pd.DataFrame, food_type: str):
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
            fig3 = px.pie(values=pc.values, names=pc.index,
                          title="생산종료 현황",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig3.update_layout(height=320)
            st.plotly_chart(fig3, use_container_width=True)

    if "제조사" in df.columns:
        with c4:
            top10  = df["제조사"].value_counts().head(10)
            others = max(0, len(df) - top10.sum())
            labels = list(top10.index) + (["기타"] if others > 0 else [])
            values = list(top10.values) + ([others] if others > 0 else [])
            fig4 = px.pie(values=values, names=labels,
                          title="제조사 점유율 (상위 10)",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig4.update_layout(height=320)
            st.plotly_chart(fig4, use_container_width=True)


# ══════════════════════════════════════════════════════
#  AI 분석
# ══════════════════════════════════════════════════════
GEMINI_CANDIDATES = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

def _gemini(prompt: str, api_key: str) -> str:
    """작동하는 모델 순서대로 시도. 400은 프롬프트 문제이므로 즉시 중단."""
    BASE = "https://generativelanguage.googleapis.com/v1/models"
    last_err = ""
    for model in GEMINI_CANDIDATES:
        try:
            r = requests.post(
                f"{BASE}/{model}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60,
            )
            # 400 = 프롬프트 문제 → 모델 바꿔도 동일, 즉시 에러 메시지 반환
            if r.status_code == 400:
                msg = r.json().get("error", {}).get("message", "Bad Request")
                raise RuntimeError(f"프롬프트 오류 (400): {msg}")
            if r.status_code == 404 or "no longer available" in r.text:
                last_err = f"{model}: deprecated"
                continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except RuntimeError:
            raise
        except requests.exceptions.HTTPError as e:
            last_err = f"{model}: {e}"
            continue
        except Exception as e:
            last_err = f"{model}: {e}"
            continue
    raise RuntimeError(f"모든 모델 실패. 마지막 오류: {last_err}")


def _ctx(df: pd.DataFrame, food_type: str) -> dict:
    """프롬프트용 데이터 — 토큰 절약을 위해 최소화"""
    monthly = {}
    if "보고일자_dt" in df.columns:
        tmp = df.dropna(subset=["보고일자_dt"]).copy()
        if not tmp.empty:
            tmp["연월"] = tmp["보고일자_dt"].dt.to_period("M").astype(str)
            # 최근 12개월만
            monthly = tmp["연월"].value_counts().sort_index().tail(12).to_dict()

    # 상위 5개 제조사만
    maker_top = df["제조사"].value_counts().head(5).to_dict() if "제조사" in df.columns else {}
    maker_n   = df["제조사"].nunique() if "제조사" in df.columns else "N/A"

    # 최신 10건만, 제품명과 보고일자만
    recent = []
    if "제품명" in df.columns:
        cols  = [c for c in ["제품명", "보고일자"] if c in df.columns]
        recent = df[cols].head(10).to_dict(orient="records")

    # 키워드 상위 15개만
    kw_freq = {}
    if "제품명" in df.columns:
        words   = re.findall(r"[가-힣a-zA-Z]{2,}",
                             " ".join(df["제품명"].dropna().astype(str)))
        kw_freq = dict(Counter(words).most_common(15))

    return dict(food_type=food_type, total=len(df),
                monthly=monthly, maker_top=maker_top,
                maker_n=maker_n, recent=recent, kw_freq=kw_freq)


def render_ai_section(df: pd.DataFrame, food_type: str, api_key: str):
    st.markdown("---")
    st.markdown("## 🤖 AI 연구원 분석")

    if not api_key:
        st.warning("**Gemini API 키 없음**\n\n`.streamlit/secrets.toml`:\n```toml\nGOOGLE_API_KEY = \"AIza...\"\n```")
        return

    st.info(f"모델: **gemini-2.5-pro 우선** | 대상: **{food_type}** {len(df)}건")

    if not st.button("🔬 AI 분석 시작", key="btn_ai", type="primary",
                     use_container_width=True):
        return

    ctx = _ctx(df, food_type)

    # ── 공통 prefix (간결하게) ──
    prefix = (
        f"식품 R&D 전문가로서 아래 데이터를 분석하세요.\n"
        f"카테고리: {food_type} | 조회건수: {ctx['total']}건 | 제조사: {ctx['maker_n']}개\n"
        f"월별추이(최근12개월): {ctx['monthly']}\n"
        f"주요제조사(상위5): {ctx['maker_top']}\n"
        f"최신제품(10건): {ctx['recent']}\n"
        f"키워드빈도(상위15): {ctx['kw_freq']}\n\n"
    )

    analyses = [
        {
            "title": "📈 시장 트렌드 분석",
            "prompt": prefix + (
                "위 데이터를 바탕으로 한국어로 분석하세요 (각 항목 3문장):\n"
                "1. 시장 성장성\n2. 경쟁 구도\n3. 출시 패턴\n4. R&D 시사점"
            ),
        },
        {
            "title": "🍋 플레이버 & 원료 트렌드",
            "prompt": prefix + (
                "위 제품명 키워드를 바탕으로 한국어로 분석하세요 (각 항목 3문장):\n"
                "1. 주요 플레이버 트렌드\n2. 기능성 원료 트렌드\n"
                "3. 신흥 플레이버\n4. 포뮬레이션 방향 제언"
            ),
        },
        {
            "title": "🧪 추천 레시피 3종",
            "prompt": prefix + (
                f"위 트렌드를 반영한 {food_type} 신제품 레시피 3종을 제안하세요.\n"
                "각 레시피:\n"
                "- 제품명 / 컨셉 / 타겟\n"
                "- 주요 원료 및 배합비(%) — 합계 100%\n"
                "- 예상 규격(pH/Brix/칼로리)\n"
                "- 차별화 포인트"
            ),
        },
        {
            "title": "💡 종합 R&D 인사이트",
            "prompt": prefix + (
                "위 데이터를 바탕으로 한국어로 작성하세요 (각 항목 3문장):\n"
                "1. 시장 기회(틈새)\n2. 리스크 요인\n"
                "3. 즉시 출시 추천 컨셉(6개월 내)\n4. 중장기 R&D 방향(1~3년)"
            ),
        },
    ]

    all_results = {}
    for item in analyses:
        st.markdown(f"#### {item['title']}")
        box = st.empty()
        box.info("분석 중…")
        try:
            text = _gemini(item["prompt"], api_key)
            all_results[item["title"]] = text
            box.markdown(text)
        except Exception as e:
            msg = f"❌ {e}"
            all_results[item["title"]] = msg
            box.error(msg)
        st.markdown("")

    if all_results:
        full = "\n\n---\n\n".join(f"{t}\n\n{c}" for t, c in all_results.items())
        st.download_button(
            "📥 AI 분석 전체 다운로드 (TXT)",
            full.encode("utf-8"),
            f"{food_type}_AI분석_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            "text/plain", use_container_width=True,
        )


# ══════════════════════════════════════════════════════
#  스타일
# ══════════════════════════════════════════════════════
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #f8f9fb; }
div[data-testid="stMetric"] { background: #f0f2f5; border-radius: 10px; padding: 12px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  사이드바
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🔍 조회 설정")
    st.markdown("---")

    mode = st.radio("조회 방식", ["📋 단일 유형 조회", "📊 복수 유형 비교"])
    st.markdown("---")

    if mode == "📋 단일 유형 조회":
        category  = st.selectbox("카테고리", list(FOOD_TYPES.keys()))
        food_type = st.selectbox("식품유형", FOOD_TYPES[category])
        custom    = st.text_input("직접 입력 (DB 표기 그대로)",
                                  placeholder="예: 과.채주스")
        if custom.strip():
            food_type = custom.strip()
        count = st.slider("조회 건수", 10, 300, 100, step=10)

    else:
        st.markdown("**비교할 유형 선택:**")
        selected_types = []
        for cat, types in FOOD_TYPES.items():
            with st.expander(cat, expanded=(cat == "음료류")):
                for t in types:
                    if st.checkbox(t, key=f"cb_{t}",
                                   value=t in ["혼합음료", "과.채주스", "탄산음료"]):
                        selected_types.append(t)
        per_type = st.slider("유형별 조회 건수", 10, 50, 20, step=5)

    st.markdown("---")
    st.markdown("#### 🔭 조회 설정")
    max_pages = st.slider(
        "최대 페이지 (fallback용)", 10, 200, 30, step=10,
        help="서버 필터가 작동하면 1~3페이지만 사용. 실패 시 이 값만큼 전체 스캔",
    )
    st.markdown("#### 📅 변경일자 필터 (CHNG_DT)")
    use_chng = st.checkbox("변경일자 이후만 조회", value=True,
                           help="API 명세: 지정일 이후 변경된 데이터만 반환 → 빠름")
    if use_chng:
        from datetime import date, timedelta
        default_dt = date.today() - timedelta(days=365*2)  # 기본 2년
        chng_date  = st.date_input("변경일자 기준", value=default_dt)
        chng_dt    = chng_date.strftime("%Y%m%d")
        st.caption(f"CHNG_DT = {chng_dt} 이후 데이터만 조회")
    else:
        chng_dt = ""

    st.markdown("---")
    run = st.button("🚀 조회 실행", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("### 🤖 Gemini 설정")
    if get_gemini_key():
        st.success("API 키 연결됨", icon="✅")
    else:
        st.warning("GOOGLE_API_KEY 없음", icon="⚠️")
        st.caption("secrets.toml: GOOGLE_API_KEY = \"AIza...\"")
    gemini_model = get_gemini_key()
    st.caption("모델: 자동 선택 (2.5-flash → 2.0-flash-lite → 1.5-flash 순)")

    st.markdown("---")
    if st.button("🔄 캐시 초기화", use_container_width=True):
        st.cache_data.clear()
        st.success("완료")
    st.caption("📡 식품안전나라 I1250")
    st.caption("⚠️ 일일 2,000회 호출 제한")


# ══════════════════════════════════════════════════════
#  session_state 초기화
# ══════════════════════════════════════════════════════
for _k, _v in {
    "result_df":    None,   # 조회 결과 DataFrame
    "result_label": "",     # 식품유형명
    "result_total": 0,      # 전체 DB 건수
    "result_src":   "",     # 조회 방식 메시지
    "result_mode":  "",     # single / multi
    "status_msgs":  {},     # 복수 유형 상태
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════
st.markdown("# 🏭 식품안전나라 품목제조보고 조회")
st.markdown("---")

# ── 조회 실행 (run 버튼 눌렸을 때만 API 호출) ──
if run:
    if mode == "📋 단일 유형 조회":
        t0          = time.time()
        prog_bar    = st.progress(0.0)
        status_text = st.empty()

        rows, src, total, _ = fetch_food_data(
            food_type, top_n=count, max_pages=max_pages,
            chng_dt=chng_dt,
            prog_bar=prog_bar, status_text=status_text,
        )
        elapsed = time.time() - t0
        prog_bar.empty()
        status_text.empty()

        if rows is None:
            st.error(f"❌ 조회 실패: {src}")
        else:
            df = to_df(rows)
            st.session_state.update({
                "result_df":    df,
                "result_label": food_type,
                "result_total": total,
                "result_src":   f"✅ **{len(df)}건** | {elapsed:.1f}초 | {src} | 전체: {total:,}건",
                "result_mode":  "single",
                "status_msgs":  {},
            })

    else:  # 복수 유형
        if not selected_types:
            st.warning("⚠️ 유형을 1개 이상 선택하세요.")
        else:
            t0 = time.time()
            all_rows, status = fetch_multiple(selected_types, per_type, max_pages,
                                              chng_dt=chng_dt)
            elapsed = time.time() - t0
            df = to_df(all_rows)
            label = ", ".join(selected_types[:3]) + ("…" if len(selected_types) > 3 else "")
            st.session_state.update({
                "result_df":    df,
                "result_label": label,
                "result_total": 0,
                "result_src":   f"✅ {len(selected_types)}개 유형 완료 | {elapsed:.1f}초 | {len(df)}건",
                "result_mode":  "multi",
                "status_msgs":  status,
            })

# ── 결과 렌더링 (session_state 기반 → 버튼 눌러도 유지) ──
df     = st.session_state["result_df"]
r_mode = st.session_state["result_mode"]
r_lbl  = st.session_state["result_label"]
r_tot  = st.session_state["result_total"]
r_src  = st.session_state["result_src"]
smsgs  = st.session_state["status_msgs"]

if df is None:
    st.info("👈 사이드바에서 식품유형을 선택하고 **[조회 실행]**을 누르세요.")

elif df.empty:
    st.warning(f"⚠️ **'{r_lbl}'** 결과 없음 — 스캔 범위를 늘리거나 유형명을 확인하세요.")

else:
    st.success(r_src)

    # 복수 유형 요약 메트릭
    if smsgs:
        cols = st.columns(min(len(smsgs), 6))
        for i, (ft, info) in enumerate(smsgs.items()):
            with cols[i % len(cols)]:
                st.metric(ft, f"{info['fetched']}건", f"전체 {info['total']:,}건")
        st.markdown("---")

    # 상단 메트릭
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("조회 결과", f"{len(df)}건")
    if r_mode == "single":
        m2.metric("전체 DB",   f"{r_tot:,}건")
        m3.metric("식품유형",   r_lbl)
    else:
        m2.metric("유형 수",    f"{df['식품유형'].nunique()}개" if "식품유형" in df.columns else "-")
        m3.metric("카테고리",   r_lbl)
    if "제조사" in df.columns:
        m4.metric("제조사 수",  f"{df['제조사'].nunique()}개")

    st.markdown("---")

    # ── 탭 ──
    tab1, tab2, tab3 = st.tabs(["📋 제품 목록", "📊 분석 차트", "📥 원시 데이터"])

    with tab1:
        ca, cb = st.columns(2)
        with ca:
            kw = st.text_input("🔎 검색", placeholder="제품명·제조사·원재료", key="kw_input")
        with cb:
            makers = (["전체"] + sorted(df["제조사"].dropna().unique().tolist())
                      if "제조사" in df.columns else ["전체"])
            sel_mk = st.selectbox("제조사 필터", makers, key="maker_sel")

        fdf = df.copy()
        if kw:
            fdf = fdf[fdf.apply(lambda r: kw.lower() in str(r).lower(), axis=1)]
        if "제조사" in df.columns and sel_mk != "전체":
            fdf = fdf[fdf["제조사"] == sel_mk]

        sc = [c for c in ["제품명", "식품유형", "제조사", "보고일자",
                           "주요원재료", "유통기한", "생산종료"]
              if c in fdf.columns]
        st.dataframe(fdf[sc].reset_index(drop=True),
                     use_container_width=True, height=480)
        st.caption(f"총 {len(fdf)}건 표시")

    with tab2:
        render_charts(df, r_lbl)

    with tab3:
        st.dataframe(df, use_container_width=True, height=480)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 CSV 다운로드", csv,
            f"{r_lbl}_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv", use_container_width=True,
        )

    # ── AI 분석 (탭 밖 → session_state df 사용) ──
    render_ai_section(df, r_lbl, gemini_model)
