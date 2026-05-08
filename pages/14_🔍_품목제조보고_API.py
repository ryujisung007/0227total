"""
🔍 품목제조보고 통합 조회 페이지
============================================================
- 📡 API 조회 (기존): I1250 공식 API. 음료 17종 카테고리. 빠르고 안정적.
- 🌐 웹 수집 (신규): Playwright. 모든 식품유형 + 성분/원료 등 상세정보.

상위 디렉토리(repo root)의 food_safety_scraper.py를 subprocess로 호출.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# 페이지 설정 (멀티페이지 앱에서 페이지별 설정 가능)
st.set_page_config(
    page_title="품목제조보고 조회",
    page_icon="🔍",
    layout="wide",
)

# repo root에 있는 스크래퍼 CLI 경로
SCRAPER_PATH = Path(__file__).parent.parent / "food_safety_scraper.py"


# ============================================================
# 헤더 + 모드 선택
# ============================================================
st.title("🔍 품목제조보고 조회")

mode = st.radio(
    "조회 방식",
    ["📡 API 조회 (빠름·음료 한정)", "🌐 웹 수집 (상세·전체 식품유형)"],
    horizontal=True,
    label_visibility="collapsed",
    key="_pmr_mode",
)
st.divider()


# ============================================================
# ============== 📡 API 조회 모드 (기존 코드) ================
# ============================================================
DRINK_TYPES = [
    "과.채주스", "과.채음료", "농축과.채즙", "탄산음료", "탄산수",
    "두유", "가공두유", "원액두유", "인삼.홍삼음료", "혼합음료",
    "유산균음료", "음료베이스", "효모음료", "커피", "침출차",
    "고형차", "액상차",
]

SEARCH_TERMS = {
    "과.채주스":     ["채주스"],
    "과.채음료":     ["채음료"],
    "농축과.채즙":   ["농축", "채즙"],
    "인삼.홍삼음료": ["홍삼음료", "홍삼"],
}

COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형",
    "BSSH_NM": "제조사", "PRMS_DT": "보고일자",
    "RAWMTRL_NM": "주요원재료", "POG_DAYCNT": "유통기한",
    "PRODUCTION": "생산종료", "LAST_UPDT_DTM": "최종수정일",
    "PRDLST_REPORT_NO": "품목제조번호",
}

BASE_URLS = [
    "https://openapi.foodsafetykorea.go.kr/api",
    "http://openapi.foodsafetykorea.go.kr/api",
]


def _normalize(s: str) -> str:
    return s.strip().replace("·", ".").replace("‧", ".").replace(" ", "")


def _api_get(url: str, timeout: int = 60, retries: int = 3, log=None):
    """API GET with retry. 타임아웃/네트워크 오류 시 백오프 재시도.

    Streamlit Cloud 미국 서버 ↔ 한국 정부 API 국제 구간이 느릴 수 있어
    충분한 timeout과 자동 재시도가 필수.
    """
    import urllib.error
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                wait = 1.5 * (2 ** attempt)  # 1.5, 3, 6초
                if log:
                    log(
                        f"  ⏰ 네트워크 오류 - {wait:.0f}초 후 재시도 "
                        f"({attempt + 2}/{retries})"
                    )
                time.sleep(wait)
    raise last_err


def _find_working_base(api_key: str, log=None) -> str:
    if "_pmr_api_base" in st.session_state:
        return st.session_state["_pmr_api_base"]
    for base in BASE_URLS:
        try:
            data = _api_get(
                f"{base}/{api_key}/I1250/json/1/1",
                timeout=30, retries=2, log=log,
            )
            if data.get("I1250", {}).get(
                "RESULT", {}
            ).get("CODE") == "INFO-000":
                st.session_state["_pmr_api_base"] = base
                return base
        except Exception:
            continue
    st.session_state["_pmr_api_base"] = BASE_URLS[0]
    return BASE_URLS[0]


def _get_search_terms(food_type: str) -> list:
    if food_type in SEARCH_TERMS:
        return SEARCH_TERMS[food_type]
    if "." in food_type:
        return [
            food_type.split(".")[-1],
            food_type.replace(".", ""),
        ]
    return [food_type]


def _fetch_with_term(
    base_url, api_key, search_term, food_type, max_rows,
    log, product_name="", min_prms_dt="",
    use_exact_match=True, candidate_multiplier=5,
):
    """
    I1250 API는 정렬 파라미터 / 날짜범위 파라미터를 지원 안 함.
    → 안전한 전략:
       1. 충분한 후보 가져오기 (max_rows × candidate_multiplier)
       2. 클라이언트 측에서 식품유형 정확 매칭 + 신고일 컷
       3. PRMS_DT 내림차순 재정렬 후 상위 N건 반환

    Args:
        search_term: PRDLST_DCNM 검색어 (정확명 또는 변형)
        food_type: 정확 매칭 기준 원본명 (전체검색 시 빈 문자열)
        product_name: PRDLST_NM 추가 필터 (선택)
        min_prms_dt: "YYYYMMDD" - 이보다 옛날은 클라이언트에서 폐기
        candidate_multiplier: 후보 배수 (기본 5)
    """
    encoded_type = (
        urllib.parse.quote(search_term) if search_term else ""
    )
    encoded_name = (
        urllib.parse.quote(product_name) if product_name else ""
    )
    norm_target = _normalize(food_type) if food_type else ""

    # API 파라미터 (검증된 것만)
    params_list = []
    if encoded_type:
        params_list.append(f"PRDLST_DCNM={encoded_type}")
    if encoded_name:
        params_list.append(f"PRDLST_NM={encoded_name}")
    params = "&".join(params_list) if params_list else ""

    # 후보 확보량
    if use_exact_match and food_type:
        target_candidates = max_rows * candidate_multiplier
    else:
        target_candidates = max_rows * 2
    target_candidates = min(target_candidates, 5000)

    all_data = []
    start = 1
    page_size = 200
    consec_fails = 0
    skipped_old = 0
    skipped_type = 0

    while (
        start <= target_candidates
        and len(all_data) < target_candidates
    ):
        end = min(start + page_size - 1, target_candidates)
        url = f"{base_url}/{api_key}/I1250/json/{start}/{end}"
        if params:
            url += f"/{params}"

        try:
            data = _api_get(url, timeout=60, retries=3, log=log)
            svc = data.get("I1250", {})
            code = svc.get("RESULT", {}).get("CODE", "")

            if code == "INFO-300":
                log("❌ 인증키 오류")
                return []
            if code != "INFO-000" or not svc.get("row"):
                break

            rows = svc.get("row", [])
            total = svc.get("total_count", "0")

            page_matched = []
            for r in rows:
                # 1) 식품유형 정확 매칭
                if use_exact_match and norm_target:
                    if _normalize(
                        r.get("PRDLST_DCNM", "")
                    ) != norm_target:
                        skipped_type += 1
                        continue
                # 2) 신고일 컷 (클라이언트 측)
                if min_prms_dt:
                    prms = (
                        (r.get("PRMS_DT", "") or "")
                        .replace("-", "").replace(".", "")[:8]
                    )
                    if prms and prms < min_prms_dt:
                        skipped_old += 1
                        continue
                page_matched.append(r)

            all_data.extend(page_matched)
            log(
                f"📦 {start}~{end} → 매칭 {len(page_matched)}/{len(rows)} "
                f"(누적: {len(all_data)}, 유형불일치: {skipped_type}, "
                f"날짜컷: {skipped_old}, DB총: {total})"
            )

            if len(rows) < page_size:
                log("  ▣ 더 이상 데이터 없음")
                break
            start += page_size
            time.sleep(0.3)
            consec_fails = 0

        except Exception as e:
            consec_fails += 1
            log(f"⚠️ {type(e).__name__}: {e}")
            if consec_fails >= 2 and base_url.startswith("https://"):
                http_base = base_url.replace(
                    "https://", "http://", 1
                )
                log("🔄 HTTPS 연속 실패 → HTTP 전환")
                base_url = http_base
                st.session_state["_pmr_api_base"] = http_base
                consec_fails = 0
                continue
            if consec_fails >= 3:
                log("⛔ 3회 연속 실패 - 중단")
                break

    # PRMS_DT 내림차순 정렬
    def _prms_key(r):
        d = (r.get("PRMS_DT", "") or "")
        return d.replace("-", "").replace(".", "")[:8]

    all_data.sort(key=_prms_key, reverse=True)
    log(
        f"🔢 후보 {len(all_data)}건 PRMS_DT 내림차순 정렬 → "
        f"상위 {min(max_rows, len(all_data))}건"
    )
    return all_data[:max_rows]


def _fetch_data(
    api_key, food_type, max_rows, log,
    product_name="", min_prms_dt="",
):
    base_url = _find_working_base(api_key, log=log)
    proto = base_url.split("://")[0]

    # 식품유형이 비어있으면 (전체 검색) - 제품명만으로 검색
    if not food_type:
        log(f"🚀 전체 식품유형 + 제품명='{product_name}' 검색 ({proto})")
        return _fetch_with_term(
            base_url, api_key, "", "", max_rows, log,
            product_name=product_name,
            min_prms_dt=min_prms_dt,
            use_exact_match=False,
        )

    # 식품유형 지정된 경우 - 검색어 변형 시도
    terms = _get_search_terms(food_type)
    for term in terms:
        if term != food_type:
            log(f"🚀 {food_type} → '{term}'로 검색 ({proto})")
        else:
            log(f"🚀 {food_type} 수집 시작 ({proto})")
        if product_name:
            log(f"   + 제품명 필터: '{product_name}'")
        if min_prms_dt:
            log(f"   + 신고일 컷: {min_prms_dt} 이후")

        result = _fetch_with_term(
            base_url, api_key, term, food_type, max_rows, log,
            product_name=product_name,
            min_prms_dt=min_prms_dt,
            use_exact_match=True,
        )
        if result:
            log(f"✅ '{term}' 검색으로 {len(result)}건 수집!")
            return result
        else:
            log(f"⚠️ '{term}' 검색 0건 — 다음 검색어 시도")

    return []


def _render_api_mode():
    st.subheader("📡 API 조회")
    st.caption(
        "I1250 공식 API. 빠르고 안정적이며 IP 차단 위험 없음. "
        "음료·과자·빵 등 모든 식품유형 검색 가능."
    )

    # 컨테이너 환경에서는 한미 국제 구간 지연 안내
    if _is_container():
        st.info(
            "ℹ️ Streamlit Cloud(미국 서버) → 한국 정부 API 국제 구간이 "
            "느려서 종종 타임아웃이 발생할 수 있습니다. "
            "자동 재시도(3회) + HTTPS↔HTTP fallback이 적용되어 있어 "
            "**대부분 결국 성공**하지만, 시간이 더 걸립니다.\n\n"
            "🚀 더 빠르고 안정적인 사용은 **로컬 PC 실행** 권장."
        )

    # 전체 식품유형 옵션 (음료 17종 + 추가 카테고리)
    # 정확한 식품안전나라 분류명을 따라야 PRDLST_DCNM 매칭됨
    ALL_FOOD_TYPES = [
        # 음료
        "과.채주스", "과.채음료", "농축과.채즙",
        "탄산음료", "탄산수",
        "두유", "가공두유", "원액두유",
        "인삼.홍삼음료", "혼합음료", "유산균음료",
        "음료베이스", "효모음료",
        "커피", "침출차", "고형차", "액상차",
        # 과자/빵/캔디
        "과자", "캔디류", "츄잉껌", "초콜릿류",
        "빵류", "떡류",
        # 빙과/유제품
        "빙과류", "아이스크림류", "아이스크림믹스류",
        "우유류", "가공유류", "산양유", "발효유류",
        "치즈류", "버터류", "분유류", "조제유류",
        # 식육/수산
        "식육가공품", "햄류", "소시지류", "베이컨류",
        "건조저장육류", "수산물가공품", "어육가공품",
        "젓갈류", "건포류",
        # 면/즉석/조미
        "면류", "즉석조리식품", "즉석섭취식품",
        "즉석조리식품류", "조미식품",
        "장류", "고추장", "된장", "혼합장", "춘장", "청국장", "간장",
        "복합조미식품", "마요네즈", "토마토케첩",
        "드레싱", "소스류",
        # 절임/조림
        "조림식품", "절임식품", "김치류", "절임류",
        # 건강/특수
        "건강기능식품",
        "특수영양식품", "특수의료용도식품",
        # 기타
        "농산가공식품류", "기타가공품", "엿류", "당류가공품",
        "주류",
    ]

    with st.sidebar:
        st.markdown("### 🔑 API 키")
        api_key = st.text_input(
            "식품안전나라 API 키",
            type="password",
            key="_pmr_api_key",
        )

        st.markdown("### 🔍 검색 조건")

        # 식품유형 - 드롭다운 + (전체) 옵션 + 직접 입력
        food_type_options = (
            ["(전체 - 제품명만 검색)"] + ALL_FOOD_TYPES
        )
        default_idx = (
            food_type_options.index("혼합음료")
            if "혼합음료" in food_type_options else 0
        )
        food_type_sel = st.selectbox(
            "식품유형",
            options=food_type_options,
            index=default_idx,
            help=(
                "원하는 식품유형 선택. '(전체)' 선택 시 "
                "제품명을 반드시 입력해야 함."
            ),
            key="_pmr_api_food_type",
        )
        food_type = (
            ""
            if food_type_sel.startswith("(전체")
            else food_type_sel
        )

        # 직접 입력 (목록에 없는 유형용)
        with st.expander("📝 직접 입력 (목록에 없는 유형)"):
            food_type_custom = st.text_input(
                "식품유형 직접 입력",
                value="",
                placeholder="예: 가공밥",
                help=(
                    "위 드롭다운 대신 사용할 정확한 분류명. "
                    "마침표(.) 포함 그대로."
                ),
                key="_pmr_api_food_custom",
            )
            if food_type_custom.strip():
                food_type = food_type_custom.strip()
                st.caption(f"💡 직접 입력 사용: '{food_type}'")

        # 제품명 (선택)
        product_name = st.text_input(
            "제품명 (선택)",
            value="",
            placeholder="예: 콜라겐, 아메리카노",
            help=(
                "제품명 키워드로 좁히고 싶을 때만 입력. "
                "비워두면 식품유형 전체."
            ),
            key="_pmr_api_product",
        )

        # 입력 검증
        if not food_type and not product_name.strip():
            st.warning(
                "⚠️ 식품유형 '전체' 시에는 "
                "**제품명 필수**."
            )

        st.markdown("### 📅 신고일 필터 (옵션)")
        st.caption(
            "옛날 데이터 제외하고 최근 신고만 보고 싶을 때 사용. "
            "I1250 API는 신고일 정렬을 지원하지 않아, 클라이언트 측에서 "
            "**충분한 후보를 가져온 뒤 필터링·재정렬**합니다."
        )
        date_filter_mode = st.radio(
            "기간 제한",
            ["제한 없음", "최근 6개월", "최근 1년", "최근 2년", "직접 지정"],
            index=2,  # 최근 1년 기본
            key="_pmr_api_date_filter",
            label_visibility="collapsed",
        )
        min_prms_dt = ""
        from datetime import datetime as _dt, timedelta as _td
        if date_filter_mode == "최근 6개월":
            min_prms_dt = (_dt.now() - _td(days=180)).strftime("%Y%m%d")
        elif date_filter_mode == "최근 1년":
            min_prms_dt = (_dt.now() - _td(days=365)).strftime("%Y%m%d")
        elif date_filter_mode == "최근 2년":
            min_prms_dt = (_dt.now() - _td(days=730)).strftime("%Y%m%d")
        elif date_filter_mode == "직접 지정":
            from_date = st.date_input(
                "이 날짜 이후 신고 건만",
                value=_dt.now() - _td(days=365),
                key="_pmr_api_from_date",
            )
            min_prms_dt = from_date.strftime("%Y%m%d")
        if min_prms_dt:
            st.caption(f"📅 신고일 컷: **{min_prms_dt}** 이후")

        st.markdown("### 📊 수집 범위")
        max_rows = st.slider(
            "최대 수집 건수",
            min_value=10, max_value=2000,
            value=200, step=10,
            key="_pmr_api_max",
            help=(
                "API는 식품유형 정확 매칭을 위해 내부적으로 "
                "이 값의 3배 후보를 가져온 뒤 정렬·추리므로 "
                "큰 값은 시간이 더 걸립니다."
            ),
        )

        st.markdown("---")
        run = st.button(
            "🚀 조회 시작",
            type="primary",
            use_container_width=True,
            key="_pmr_api_run",
        )
        if st.button("🔄 연결 초기화", key="_pmr_api_reset"):
            st.session_state.pop("_pmr_api_base", None)
            st.success("완료")

    if not api_key:
        st.info(
            "👈 사이드바에서 API 키를 입력하세요.\n\n"
            "[키 발급]"
            "(https://www.foodsafetykorea.go.kr/api/openApiInfo.do) → "
            "I1250 신청"
        )
        return

    if not run:
        return

    if not food_type and not product_name.strip():
        st.error(
            "❌ 식품유형 '(전체)' 선택 시에는 "
            "**제품명을 반드시 입력**해야 합니다."
        )
        return

    log_box = st.empty()
    log_lines = []

    def log(msg):
        log_lines.append(msg)
        log_box.code("\n".join(log_lines))

    t0 = time.time()
    raw_rows = _fetch_data(
        api_key, food_type, max_rows, log,
        product_name=product_name.strip(),
        min_prms_dt=min_prms_dt,
    )
    elapsed = time.time() - t0

    if not raw_rows:
        st.error(
            "❌ 수집된 데이터가 없습니다. "
            "검색 조건을 완화하거나 API 키를 확인해주세요."
        )
        return

    df = pd.DataFrame(raw_rows)
    avail = [c for c in COL_MAP if c in df.columns]
    df = df[avail].rename(columns=COL_MAP)
    if "보고일자" in df.columns:
        df = df.sort_values(
            "보고일자", ascending=False
        ).reset_index(drop=True)

    st.success(f"✅ {len(df)}건 수집 ({elapsed:.1f}초)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("수집 건수", f"{len(df)}건")
    if "제조사" in df.columns:
        c2.metric("제조사 수", f"{df['제조사'].nunique()}개소")
    if "보고일자" in df.columns:
        c3.metric("최근 보고일", df["보고일자"].max())
        c4.metric("가장 오래된", df["보고일자"].min())

    st.markdown("---")
    show = [
        c for c in [
            "식품유형", "제품명", "보고일자", "제조사",
            "주요원재료", "유통기한", "생산종료",
        ] if c in df.columns
    ]
    st.dataframe(df[show], use_container_width=True, height=500)
    st.caption(f"총 {len(df)}건")

    # 파일명 구성
    parts = []
    if food_type:
        parts.append(food_type.replace(".", "_"))
    if product_name.strip():
        parts.append(product_name.strip())
    if not parts:
        parts.append("전체")
    name_prefix = "_".join(parts)

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 CSV 다운로드",
        csv,
        f"{name_prefix}_{datetime.now():%Y%m%d_%H%M}.csv",
        "text/csv",
        use_container_width=True,
        key="_pmr_api_dl",
    )


# ============================================================
# ============== 🌐 웹 수집 모드 (신규) ======================
# ============================================================
def _is_container():
    """Streamlit Cloud / Docker / 컨테이너 환경 감지."""
    if sys.platform in ("win32", "darwin"):
        return False
    return (
        os.environ.get("DISPLAY") is None
        or os.path.exists("/home/appuser")
        or os.environ.get("HOME", "").startswith("/home/appuser")
        or os.path.exists("/.dockerenv")
    )


def _render_local_execution_guide():
    """모드 선택 즉시 환경 안내. True 반환 시 호출자는 더 진행 안 함."""
    in_container = _is_container()

    if in_container:
        st.error(
            "🚨 **현재 Streamlit Cloud 서버에서 실행 중입니다 — "
            "웹 수집은 로컬 PC 실행이 필요합니다.**"
        )

        st.markdown(
            "### ⚡ 원클릭 로컬 실행\n"
            "PowerShell을 열고 아래 한 줄을 복사-붙여넣기 → 엔터:"
        )
        st.code(
            "iwr https://raw.githubusercontent.com/ryujisung007/"
            "0227total/main/install.ps1 | iex",
            language="powershell",
        )
        st.caption(
            "이 한 줄이 자동으로: GitHub에서 최신 코드 다운로드 → "
            "Python 패키지 설치 → Chromium 설치 → Streamlit 앱 실행 → "
            "브라우저 자동 오픈."
        )

        with st.expander("❓ 왜 클라우드에서는 안 되나요?", expanded=False):
            st.markdown(
                """
**기술적 이유 3가지**

1. **IP 미스매치**: 모바일 핫스팟에 접속하셔도 화면 표시만 핫스팟 IP일 뿐,
   실제 식품안전나라 사이트 요청은 **Streamlit Cloud의 미국 AWS IP**에서 나갑니다.
   한국 정부 사이트와 자주 충돌.

2. **메모리 제약**: Streamlit Cloud 무료 티어 1GB는 Chromium 안정 동작에 빠듯
   (`Target page, context or browser has been closed` 에러).

3. **시스템 라이브러리**: 컨테이너에 Chromium 의존성(`libnss3` 등) 누락 가능.

**브라우저는 사용자 PC에 직접 명령어 실행 권한이 없습니다** — 이건 표준 웹 보안 모델이라
어떤 사이트도 우회 못 합니다. 그래서 위의 PowerShell 한 줄 패턴이 유일한 방법.
                """
            )

        with st.expander(
            "🛠️ Python이 아직 설치 안 되어 있다면 (1회만)",
            expanded=False,
        ):
            st.markdown(
                """
**Python 설치** (다음 중 하나, 평생 1회):

**방법 1) python.org 직접 다운로드 (가장 안전)**
- https://www.python.org/downloads/
- 설치 시 **"Add python.exe to PATH"** 반드시 체크

**방법 2) winget (Windows 10/11):**
```cmd
winget install Python.Python.3.12
```

**방법 3) Microsoft Store에서 'Python' 검색**

설치 후 **PowerShell 재시작** → 위 원라이너 명령어 실행.
                """
            )

        with st.expander(
            "📋 원라이너 대신 수동 설치 (참고)", expanded=False
        ):
            st.markdown(
                """
```cmd
:: 1. repo 다운로드 - GitHub Code → Download ZIP, 압축 해제

:: 2. CMD/PowerShell을 그 폴더에서 열고
python -m pip install -r requirements.txt
python -m playwright install chromium

:: 3. 실행
python -m streamlit run app.py
```
                """
            )
        return True  # 컨테이너 → 호출자가 더 진행 안 하도록 신호

    # 로컬 환경 - 간단한 안내만
    st.info(
        "💡 로컬 환경에서 실행 중입니다. 모바일 핫스팟에 PC를 연결하면 "
        "한국 통신사 IP로 요청이 나가서 IP 차단 회피에 유리합니다."
    )
    return False


@st.cache_resource(show_spinner=False)
def _ensure_playwright_browser():
    cache_dir = os.path.expanduser("~/.cache/ms-playwright")
    has_chromium = (
        os.path.isdir(cache_dir)
        and any(
            d.startswith(("chromium", "chrome-"))
            for d in os.listdir(cache_dir)
        )
    )
    if has_chromium:
        return True
    placeholder = st.empty()
    placeholder.info(
        "🌐 Playwright Chromium 설치 중... (최초 1회, 약 1~2분)"
    )
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "playwright",
                "install", "chromium",
            ],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            placeholder.error(
                "❌ Chromium 설치 실패\n\n```\n"
                + (result.stderr or result.stdout)[:1500]
                + "\n```"
            )
            return False
        placeholder.success("✅ Chromium 설치 완료")
    except subprocess.TimeoutExpired:
        placeholder.error("❌ 설치 시간 초과")
        return False
    except Exception as e:
        placeholder.error(f"❌ 설치 오류: {e}")
        return False
    return True


def _check_scraper_available():
    """scraper.py 파일과 playwright 패키지 존재 확인."""
    if not SCRAPER_PATH.exists():
        st.error(
            f"❌ 스크래퍼 파일을 찾을 수 없습니다:\n`{SCRAPER_PATH}`\n\n"
            "repo root에 `food_safety_scraper.py`가 있는지 확인하세요."
        )
        return False
    try:
        import playwright  # noqa: F401
    except ImportError:
        st.error(
            "❌ Playwright 패키지가 설치되지 않았습니다.\n\n"
            "터미널에서:\n"
            "```\n"
            "python -m pip install playwright openpyxl\n"
            "python -m playwright install chromium\n"
            "```"
        )
        return False
    return True


# ============================================================
# 식품유형 dropdown용 캐시
# ============================================================
# Fallback 식품유형 목록 - 사이트 추출 실패 시 즉시 사용 가능한 주요 유형
# (식품안전나라에서 자주 검색되는 유형들 수동 큐레이션)
_FALLBACK_FOOD_TYPES = [
    # 음료
    "혼합음료", "과채음료", "과채주스", "농축과채즙",
    "탄산음료", "탄산수", "두유", "가공두유", "원액두유",
    "인삼홍삼음료", "유산균음료", "음료베이스", "효모음료",
    "커피", "침출차", "고형차", "액상차",
    # 과자/빵
    "과자", "캔디류", "츄잉껌", "초콜릿류", "빵류", "떡류",
    # 빙과/유제품
    "빙과", "아이스크림류", "아이스크림믹스류",
    "우유", "가공유", "산양유", "발효유",
    "치즈류", "버터류", "분유", "조제유류",
    # 식육/수산
    "식육가공품", "햄류", "소시지류", "베이컨류", "건조저장육류",
    "수산물가공품", "어육가공품", "젓갈류",
    # 면/즉석/조미
    "면류", "즉석조리식품", "즉석섭취식품",
    "장류", "고추장", "된장", "간장", "조미식품",
    "드레싱", "마요네즈", "케첩",
    # 기타
    "조림식품", "절임식품", "젓갈류", "김치류",
    "건강기능식품", "특수의료용도식품",
    "농산가공식품류", "기타가공품",
]


@st.cache_data(ttl=86400, show_spinner=False)  # 24시간 캐시
def _get_food_types_cached() -> list:
    """사이트에서 식품유형 목록을 한 번만 가져와 캐시.

    실패하면 빈 리스트 반환 → 호출자가 fallback 처리.
    """
    try:
        result_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        )
        result_file.close()

        cmd = [
            sys.executable, str(SCRAPER_PATH),
            "--list-food-types", "--headless",
            "--output-file", result_file.name,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", timeout=120,  # 180 → 120초로 단축
        )
        if proc.returncode != 0:
            return []
        try:
            with open(result_file.name, "r", encoding="utf-8") as f:
                return json.load(f)
        finally:
            try:
                os.unlink(result_file.name)
            except Exception:
                pass
    except Exception:
        return []


def _clear_food_types_cache():
    _get_food_types_cached.clear()


def _render_scraper_mode():
    # 헤더 (먼저 표시)
    st.subheader("🌐 웹 수집 (전체 식품유형 + 상세정보)")
    st.caption(
        "Playwright 자동화. 품목유형 → 최근등록순 → 50개씩 → "
        "각 제품 클릭 → **성분 및 원료 + 신고일자** → 엑셀 다운로드"
    )

    # 환경 진단 + 로컬 실행 가이드 (체크 전에 보여줌)
    # 컨테이너 환경이면 가이드만 표시하고 더 진행 안 함
    if _render_local_execution_guide():
        return
    st.divider()

    # 환경 체크 (로컬에서만)
    if not _check_scraper_available():
        return
    if not _ensure_playwright_browser():
        return

    with st.sidebar:
        st.markdown("### ⚙️ 수집 설정")

        # ────────── 식품유형 선택 ──────────
        # 기본은 폴백 목록 (즉시 사용). 사용자가 명시적으로
        # "사이트에서 받기" 누른 경우에만 실제 추출 실행.
        if st.session_state.get("_pmr_scr_types_loaded") == "fetched":
            food_types = _get_food_types_cached() or _FALLBACK_FOOD_TYPES
            loaded_label = (
                "📋 사이트 추출"
                if food_types != _FALLBACK_FOOD_TYPES
                else "📋 기본 목록 (사이트 추출 실패)"
            )
        else:
            food_types = _FALLBACK_FOOD_TYPES
            loaded_label = "📋 기본 목록"

        st.caption(f"{loaded_label} ({len(food_types)}종)")

        options = ["(전체 - 제품명만 검색)"] + sorted(set(food_types))
        default_index = (
            options.index("혼합음료") if "혼합음료" in options else 0
        )
        selected = st.selectbox(
            "품목유형",
            options=options,
            index=default_index,
            help=(
                "원하는 식품유형 선택. '전체' 선택 시에는 "
                "제품명을 반드시 입력해야 함."
            ),
            key="_pmr_scr_food",
        )
        food_type_value = (
            "" if selected.startswith("(전체") else selected
        )

        # 식품유형 목록 새로고침 (사이트에서 직접 추출)
        with st.expander("🔄 식품유형 목록 갱신 (선택)", expanded=False):
            st.caption(
                "기본 목록에 없는 유형이 필요하면 "
                "사이트에서 직접 추출하세요 (1~2분 소요)."
            )
            if st.button(
                "🌐 사이트에서 최신 목록 가져오기",
                key="_pmr_scr_fetch_types",
                use_container_width=True,
            ):
                with st.spinner(
                    "사이트에서 식품유형 추출 중... (최대 2분)"
                ):
                    _clear_food_types_cache()
                    fetched = _get_food_types_cached()
                if fetched:
                    st.session_state["_pmr_scr_types_loaded"] = "fetched"
                    st.success(f"✅ {len(fetched)}개 추출")
                    st.rerun()
                else:
                    st.warning(
                        "사이트 추출 실패 - 기본 목록 그대로 사용"
                    )

            # 직접 입력 옵션 (목록에 없는 유형)
            custom_type = st.text_input(
                "직접 입력 (위 목록에 없는 경우)",
                value="",
                placeholder="예: 가공두유",
                help="입력하면 위 드롭다운 선택을 무시하고 이 값을 사용",
                key="_pmr_scr_food_custom",
            )
            if custom_type.strip():
                food_type_value = custom_type.strip()
                st.caption(f"💡 직접 입력 사용: '{food_type_value}'")

        # ────────── 제품명 검색 ──────────
        product_name = st.text_input(
            "제품명 (선택)",
            value="",
            placeholder="예: 콜라겐, 아메리카노",
            help=(
                "특정 제품명 키워드로 좁히고 싶을 때만 입력. "
                "비워두면 선택된 식품유형 전체 검색."
            ),
            key="_pmr_scr_product",
        )

        # 입력 검증
        if not food_type_value and not product_name.strip():
            st.warning(
                "⚠️ 품목유형 '전체' 선택 시에는 "
                "**제품명을 반드시 입력**해주세요."
            )

        st.markdown("---")
        st.markdown("**수집 범위**")
        limit_mode = st.radio(
            "범위",
            ["건수로 제한", "페이지 수로 제한", "전체 (주의)"],
            index=0,
            label_visibility="collapsed",
            key="_pmr_scr_limit",
        )
        max_items = None
        max_pages = None
        if limit_mode == "건수로 제한":
            max_items = st.number_input(
                "최대 수집 건수",
                min_value=5, max_value=10000,
                value=50, step=10,
                key="_pmr_scr_max_items",
            )
        elif limit_mode == "페이지 수로 제한":
            max_pages = st.number_input(
                "최대 페이지 수",
                min_value=1, max_value=500,
                value=5, step=1,
                key="_pmr_scr_max_pages",
            )
        else:
            st.warning(
                "⚠️ 전체 수집은 수천 건 + IP 차단 위험."
            )

        page_size = st.selectbox(
            "페이지당 항목 수",
            options=[10, 20, 50, 100],
            index=2,
            key="_pmr_scr_page_size",
        )
        headless = st.checkbox(
            "백그라운드 실행", value=True,
            key="_pmr_scr_headless",
        )
        delay = st.slider(
            "페이지 간 대기 (초)",
            min_value=0.5, max_value=5.0,
            value=2.0, step=0.5,
            help="2초 이상 권장 (IP 차단 방지)",
            key="_pmr_scr_delay",
        )
        st.markdown("---")
        inspect_mode = st.button(
            "🔧 사이트 구조 진단",
            use_container_width=True,
            key="_pmr_scr_inspect",
        )

    if inspect_mode:
        _render_scraper_inspect(headless)
        return

    col_run, _ = st.columns([1, 4])
    run = col_run.button(
        "🚀 수집 시작", type="primary",
        use_container_width=True,
        key="_pmr_scr_run",
    )

    if not run:
        st.info(
            "**사용 가이드**\n"
            "1. 좌측 **품목유형** 입력 (예: `혼합음료`, `과자`)\n"
            "2. **수집 범위** 선택\n"
            "3. **수집 시작** 클릭\n\n"
            "**⚠️ IP 차단 주의**: delay 2초 이상, "
            "처음엔 5~10건으로 검증 후 점진적 확장."
        )
        return

    if not food_type_value and not product_name.strip():
        st.error("품목유형을 선택하거나 제품명을 입력해주세요.")
        return

    _run_scraper_subprocess(
        food_type=food_type_value,
        product_name=product_name.strip(),
        max_items=max_items,
        max_pages=max_pages,
        page_size=page_size,
        headless=headless,
        delay=delay,
    )


def _render_scraper_inspect(headless):
    st.subheader("🔍 사이트 구조 진단 결과")
    with st.spinner("사이트 분석 중..."):
        cmd = [
            sys.executable, str(SCRAPER_PATH),
            "--inspect", "--headless",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                report = json.loads(result.stdout)
                st.success(f"분석 완료: {report.get('title', '')}")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**📝 라벨**")
                    st.json(
                        report.get("labels_with_for", []),
                        expanded=False,
                    )
                    st.markdown("**📋 셀렉트**")
                    st.json(report.get("selects", []), expanded=False)
                with col2:
                    st.markdown("**🔘 버튼**")
                    st.json(report.get("buttons", []), expanded=False)
                    st.markdown("**📊 테이블**")
                    st.json(report.get("tables", []), expanded=False)
            else:
                st.error("진단 실패")
                st.code(result.stderr or "출력 없음")
        except subprocess.TimeoutExpired:
            st.error("진단 시간 초과")
        except json.JSONDecodeError:
            st.error("결과 파싱 실패")
            st.code(result.stdout[:2000])
        except Exception as e:
            st.error(f"오류: {e}")


def _run_scraper_subprocess(
    food_type, product_name, max_items, max_pages,
    page_size, headless, delay,
):
    result_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    )
    result_file.close()

    cmd = [
        sys.executable, str(SCRAPER_PATH),
        "--food-type", food_type,
        "--product-name", product_name,
        "--page-size", str(int(page_size)),
        "--delay", str(delay),
        "--output-file", result_file.name,
    ]
    if max_items is not None:
        cmd += ["--max-items", str(int(max_items))]
    if max_pages is not None:
        cmd += ["--max-pages", str(int(max_pages))]
    if headless:
        cmd.append("--headless")

    progress_bar = st.progress(0.0, text="시작 중...")
    log_box = st.empty()
    logs = []

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )

        while True:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("PROGRESS|"):
                parts = line.split("|", 4)
                try:
                    _, current, total, message = (
                        parts[0], int(parts[1]), int(parts[2]),
                        parts[3] if len(parts) > 3 else "",
                    )
                    pct = current / total if total > 0 else 0
                    progress_bar.progress(
                        min(pct, 1.0),
                        text=f"[{current}/{total}] {message}",
                    )
                except (ValueError, IndexError):
                    pass
            elif line.startswith("LOG|"):
                ts = datetime.now().strftime("%H:%M:%S")
                logs.append(f"[{ts}] {line[4:]}")
                log_box.code("\n".join(logs[-30:]))
            elif line.startswith("ERROR|"):
                st.error(f"스크래퍼 오류: {line[6:]}")
                logs.append(f"❌ {line[6:]}")
                log_box.code("\n".join(logs[-30:]))

        proc.wait(timeout=30)

        if proc.returncode != 0:
            st.error(
                f"스크래퍼가 비정상 종료되었습니다 "
                f"(exit code {proc.returncode})"
            )
            return

        try:
            with open(result_file.name, "r", encoding="utf-8") as f:
                results_json = f.read()
        except Exception as e:
            st.error(f"결과 파일 읽기 실패: {e}")
            return
        finally:
            try:
                os.unlink(result_file.name)
            except Exception:
                pass

        if not results_json.strip():
            st.warning("수집된 데이터가 없습니다.")
            return

        try:
            results = json.loads(results_json)
        except json.JSONDecodeError as e:
            st.error(f"결과 파싱 실패: {e}")
            st.code(results_json[:2000])
            return

        if not results:
            st.warning("수집된 항목이 없습니다.")
            return

        # 결과 파일명용 라벨 만들기 (식품유형 + 제품명 조합)
        if food_type and product_name:
            query_label = f"{food_type}_{product_name}"
        elif food_type:
            query_label = food_type
        elif product_name:
            query_label = product_name
        else:
            query_label = "검색"

        _render_scraper_results(results, query_label)

    except subprocess.TimeoutExpired:
        st.error("실행 시간 초과")
        if proc:
            proc.kill()
    except Exception as e:
        import traceback
        st.error(f"실행 오류: {e}")
        st.code(traceback.format_exc())


def _render_scraper_results(results, food_type):
    df = pd.DataFrame(results)
    front_cols = [
        "수집순번", "페이지", "번호",
        "품목보고번호", "업체명", "품목유형", "제품명",
        "분류", "소비기한", "성분개수", "성분및원료",
    ]
    cols = [c for c in front_cols if c in df.columns] + [
        c for c in df.columns if c not in front_cols
    ]
    df = df[cols]

    st.success(f"✅ 총 {len(df):,}건 수집 완료")
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("총 수집 건수", f"{len(df):,}")
    if "페이지" in df.columns:
        col_m2.metric("페이지 수", df["페이지"].nunique())
    if "성분개수" in df.columns:
        avg_ing = pd.to_numeric(
            df["성분개수"], errors="coerce"
        ).dropna().mean()
        if not pd.isna(avg_ing):
            col_m3.metric("평균 성분 수", f"{avg_ing:.1f}")
    if "업체명" in df.columns:
        col_m4.metric("제조업체 수", df["업체명"].nunique())

    st.subheader("📋 결과 미리보기")
    st.dataframe(df, use_container_width=True, height=500)

    try:
        from openpyxl.utils import get_column_letter
        df_excel = df.copy()
        clean_cols = {
            c: str(c).replace("\n", " ").replace("\r", " ")[:200]
            for c in df_excel.columns
        }
        df_excel = df_excel.rename(columns=clean_cols).fillna("")

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_excel.to_excel(
                writer, sheet_name="품목제조보고", index=False,
            )
            ws = writer.sheets["품목제조보고"]
            for i, col in enumerate(df_excel.columns, start=1):
                try:
                    series_str = df_excel[col].astype(str)
                    max_len = max(
                        series_str.map(len).max() if len(df_excel) else 0,
                        len(str(col)),
                    )
                    ws.column_dimensions[
                        get_column_letter(i)
                    ].width = min(int(max_len) + 2, 60)
                except Exception:
                    continue
        excel_bytes = buf.getvalue()
    except Exception as e:
        import traceback
        st.error(f"❌ 엑셀 생성 실패: {e}")
        st.code(traceback.format_exc())
        csv_bytes = df.to_csv(
            index=False, encoding="utf-8-sig",
        ).encode("utf-8-sig")
        st.download_button(
            "📥 CSV 다운로드 (fallback)",
            data=csv_bytes,
            file_name=(
                f"품목제조보고_{food_type}_"
                f"{datetime.now():%Y%m%d_%H%M}.csv"
            ),
            mime="text/csv",
            type="primary",
            key="_pmr_scr_csv",
        )
        return

    filename = (
        f"품목제조보고_{food_type}_"
        f"{datetime.now():%Y%m%d_%H%M}.xlsx"
    )
    col_dl, _ = st.columns([1, 4])
    col_dl.download_button(
        "📥 엑셀 다운로드",
        data=excel_bytes,
        file_name=filename,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        type="primary",
        use_container_width=True,
        key="_pmr_scr_xlsx",
    )


# ============================================================
# 모드 분기 실행
# ============================================================
if mode.startswith("📡"):
    _render_api_mode()
else:
    _render_scraper_mode()
