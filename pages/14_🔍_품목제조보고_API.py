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


def _api_get(url: str, timeout: int = 20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _find_working_base(api_key: str) -> str:
    if "_pmr_api_base" in st.session_state:
        return st.session_state["_pmr_api_base"]
    for base in BASE_URLS:
        try:
            data = _api_get(
                f"{base}/{api_key}/I1250/json/1/1", timeout=15
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
    base_url, api_key, search_term, food_type, max_rows, log
):
    encoded = urllib.parse.quote(search_term)
    norm_target = _normalize(food_type)
    all_data = []
    start = 1
    page_size = 500
    retries = 0

    while start <= max_rows and len(all_data) < max_rows:
        end = min(start + page_size - 1, max_rows)
        url = (
            f"{base_url}/{api_key}/I1250/json/{start}/{end}/"
            f"PRDLST_DCNM={encoded}"
        )
        try:
            data = _api_get(url, timeout=20)
            svc = data.get("I1250", {})
            code = svc.get("RESULT", {}).get("CODE", "")

            if code == "INFO-300":
                log("❌ 인증키 오류")
                return []
            if code != "INFO-000" or not svc.get("row"):
                break

            rows = svc.get("row", [])
            total = svc.get("total_count", "0")
            matched = [
                r for r in rows
                if _normalize(r.get("PRDLST_DCNM", "")) == norm_target
            ]
            all_data.extend(matched)

            log(
                f"📦 {start}~{end} → {len(matched)}/{len(rows)}건 "
                f"(누적: {len(all_data)} / DB: {total})"
            )

            if len(rows) < page_size:
                break
            start += page_size
            time.sleep(0.2)
            retries = 0

        except TimeoutError:
            retries += 1
            if retries > 2:
                log("⏰ 타임아웃 3회 — 중단")
                break
            log(f"⏰ 타임아웃 — 재시도 ({retries}/3)")
            time.sleep(1)
            continue
        except Exception as e:
            log(f"⚠️ {e}")
            break

    return all_data[:max_rows]


def _fetch_data(api_key, food_type, max_rows, log):
    base_url = _find_working_base(api_key)
    proto = base_url.split("://")[0]
    terms = _get_search_terms(food_type)

    for term in terms:
        if term != food_type:
            log(f"🚀 {food_type} → '{term}'로 검색 ({proto})")
        else:
            log(f"🚀 {food_type} 수집 시작 ({proto})")

        result = _fetch_with_term(
            base_url, api_key, term, food_type, max_rows, log
        )
        if result:
            log(f"✅ '{term}' 검색으로 {len(result)}건 수집 성공!")
            return result
        else:
            log(f"⚠️ '{term}' 검색 0건 — 다음 검색어 시도")

    return []


def _render_api_mode():
    st.subheader("📡 API 조회 (음료 카테고리)")
    st.caption(
        "I1250 공식 API. 음료 17종 카테고리 한정. "
        "빠르고 안정적이며 IP 차단 위험 없음."
    )

    with st.sidebar:
        st.markdown("### 🔑 API 키")
        api_key = st.text_input(
            "식품안전나라 API 키",
            type="password",
            key="_pmr_api_key",
        )
        st.markdown("### 🍹 조회 설정")
        food_type = st.selectbox(
            "식품유형", DRINK_TYPES, key="_pmr_api_food_type"
        )
        max_rows = st.slider(
            "최대 수집 건수", 10, 1000, 200, step=10,
            key="_pmr_api_max",
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

    log_box = st.empty()
    log_lines = []

    def log(msg):
        log_lines.append(msg)
        log_box.code("\n".join(log_lines))

    t0 = time.time()
    raw_rows = _fetch_data(api_key, food_type, max_rows, log)
    elapsed = time.time() - t0

    if not raw_rows:
        st.error("❌ 수집된 데이터가 없습니다. API 키를 확인하세요.")
        return

    df = pd.DataFrame(raw_rows)
    avail = [c for c in COL_MAP if c in df.columns]
    df = df[avail].rename(columns=COL_MAP)
    if "보고일자" in df.columns:
        df = df.sort_values(
            "보고일자", ascending=False
        ).reset_index(drop=True)

    st.success(f"✅ {len(df)}건 수집 ({elapsed:.1f}초)")
    c1, c2, c3 = st.columns(3)
    c1.metric("수집 건수", f"{len(df)}건")
    if "제조사" in df.columns:
        c2.metric("제조사 수", f"{df['제조사'].nunique()}개소")
    if "보고일자" in df.columns:
        c3.metric("최근 보고일", df["보고일자"].max())

    st.markdown("---")
    show = [
        c for c in [
            "식품유형", "제품명", "보고일자", "제조사",
            "주요원재료", "유통기한", "생산종료",
        ] if c in df.columns
    ]
    st.dataframe(df[show], use_container_width=True, height=500)
    st.caption(f"총 {len(df)}건")

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 CSV 다운로드",
        csv,
        f"{food_type.replace('.', '_')}_"
        f"{datetime.now():%Y%m%d_%H%M}.csv",
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
        food_type = st.text_input(
            "품목유형",
            value="혼합음료",
            help="예: 혼합음료, 과채음료, 과자, 빵류, 빙과, 액상차",
            key="_pmr_scr_food",
        )
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

    if not food_type.strip():
        st.error("품목유형을 입력해주세요.")
        return

    _run_scraper_subprocess(
        food_type=food_type.strip(),
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
    food_type, max_items, max_pages, page_size, headless, delay,
):
    result_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    )
    result_file.close()

    cmd = [
        sys.executable, str(SCRAPER_PATH),
        "--food-type", food_type,
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

        _render_scraper_results(results, food_type)

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
