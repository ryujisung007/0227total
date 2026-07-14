"""
식품안전나라 품목제조보고 자동수집 - Playwright 스크래퍼 v4
============================================================
v4 핵심 개선:
- 상세 페이지를 [새 탭]에서 열기 → 메인 페이지 검색 상태 100% 보존
- 상세 페이지의 모든 th-td 쌍을 그대로 수집 → 라벨 자동 발견
- 페이지 사이즈 dropdown custom 처리 강화
- 페이지네이션 단순 텍스트 매칭
"""
from __future__ import annotations

SCRAPER_VERSION = "v5.0 (2026-05)"

import argparse
import json
import os
import re
import sys
import time
from typing import Any

from playwright.sync_api import (
    Locator,
    Page,
    BrowserContext,
    TimeoutError as PWTimeout,
    sync_playwright,
)

SEARCH_URL = (
    "https://www.foodsafetykorea.go.kr/portal/specialinfo/"
    "searchInfoProduct.do?menu_grp=MENU_NEW04&menu_no=2815#page1"
)
BASE_URL = "https://www.foodsafetykorea.go.kr"


# ============================================================
# 환경 + Chromium launch
# ============================================================
def _is_container_env() -> bool:
    if sys.platform in ("win32", "darwin"):
        return False
    return (
        os.environ.get("DISPLAY") is None
        or os.path.exists("/home/appuser")
        or os.environ.get("HOME", "").startswith("/home/appuser")
        or os.path.exists("/.dockerenv")
    )


def _launch_chromium(p, headless_request: bool):
    in_container = _is_container_env()
    actual_headless = True if in_container else headless_request
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--no-zygote",
    ]
    if in_container:
        args.append("--single-process")
    return p.chromium.launch(headless=actual_headless, args=args)


# ============================================================
# IPC
# ============================================================
def emit(kind: str, *parts: Any) -> None:
    msg = "|".join(str(p).replace("|", "/") for p in (kind, *parts))
    print(msg, file=sys.stderr, flush=True)


def log(msg: str) -> None:
    emit("LOG", msg)


def progress(current: int, total: int, message: str = "") -> None:
    emit("PROGRESS", current, total, message)


# ============================================================
# 견고한 navigation
# ============================================================
def _robust_goto(page: Page, url: str, timeout: int = 60000) -> None:
    last_err: Exception | None = None
    for strategy in ("domcontentloaded", "commit"):
        try:
            page.goto(url, wait_until=strategy, timeout=timeout)
            return
        except PWTimeout as e:
            last_err = e
            log(f"  네비게이션 타임아웃 ({strategy}) → 다음 전략")
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err


# ============================================================
# 결과 테이블 헬퍼
# ============================================================
def _find_result_table(page: Page) -> Locator | None:
    for tbl in page.locator("table").all():
        try:
            header_text = ""
            thead = tbl.locator("thead")
            if thead.count():
                header_text = thead.first.inner_text()
            if not header_text:
                first_tr = tbl.locator("tr").first
                if first_tr.count():
                    header_text = first_tr.inner_text()
            if "품목보고번호" in header_text and "제품명" in header_text:
                return tbl
        except Exception:
            continue
    return None


def _table_headers(table: Locator) -> list[str]:
    headers: list[str] = []
    thead = table.locator("thead")
    if thead.count():
        for th in thead.first.locator("th, td").all():
            headers.append(th.inner_text().strip())
    if not headers:
        first_tr = table.locator("tr").first
        for th in first_tr.locator("th").all():
            headers.append(th.inner_text().strip())
    return headers


def _extract_table_rows(page: Page) -> list[dict]:
    table = _find_result_table(page)
    if table is None:
        return []
    headers = _table_headers(table)
    if not headers:
        return []
    rows = []
    for tr in table.locator("tbody tr").all():
        cells = tr.locator("td").all()
        if not cells:
            continue
        row_data = {}
        for i, cell in enumerate(cells):
            if i < len(headers):
                row_data[headers[i]] = re.sub(
                    r"\s+", " ", cell.inner_text()
                ).strip()
        rows.append(row_data)
    return rows


# ============================================================
# 정렬 / 페이지 사이즈 / 페이지네이션
# ============================================================
def _click_recent_sort(page: Page, delay: float) -> bool:
    for sel in [
        "button:has-text('최근등록순')",
        "a:has-text('최근등록순')",
        "*[role='button']:has-text('최근등록순')",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_visible():
                btn.click()
                page.wait_for_load_state(
                    "domcontentloaded", timeout=15000
                )
                time.sleep(delay)
                return True
        except Exception:
            continue
    return False


def _select_page_size(
    page: Page, page_size: int, delay: float, debug: bool = True
) -> bool:
    """페이지당 N개로 변경. 표준 select / custom dropdown 모두 처리."""
    target_label = f"{page_size}개씩"

    # ---- 1) 표준 <select> ----
    selects = page.locator("select").all()
    if debug:
        log(f"  발견된 select 요소: {len(selects)}개")
    for sel in selects:
        try:
            opts = sel.evaluate(
                "el => Array.from(el.options).map(o => o.text).join('|')"
            )
            if debug and opts:
                log(f"    select 옵션: {opts[:200]}")
            if "10개씩" in opts or "20개씩" in opts or "개씩" in opts:
                try:
                    sel.select_option(label=target_label)
                except Exception:
                    try:
                        sel.select_option(value=str(page_size))
                    except Exception:
                        sel.evaluate(
                            f"el => {{el.value='{page_size}'; "
                            f"el.dispatchEvent(new Event('change'));}}"
                        )
                page.wait_for_load_state(
                    "domcontentloaded", timeout=15000
                )
                time.sleep(delay)
                return True
        except Exception:
            continue

    # ---- 2) custom dropdown ----
    # 트리거 후보: "10개씩"이 텍스트로 보이는 클릭 가능 요소
    triggers = []
    for sel in [
        "button:has-text('10개씩')",
        "a:has-text('10개씩')",
        ".dropdown:has-text('10개씩')",
        "div[class*='select']:has-text('10개씩')",
        "[role='combobox']:has-text('10개씩')",
        "*:has-text('10개씩')",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                triggers.append((sel, loc))
        except Exception:
            continue

    if debug:
        log(f"  발견된 dropdown 트리거 후보: {len(triggers)}개")
        for s, _ in triggers[:3]:
            log(f"    트리거: {s}")

    for sel, trig in triggers:
        try:
            trig.click()
            time.sleep(0.5)
            opt_candidates = [
                f"li:has-text('{target_label}')",
                f"a:has-text('{target_label}')",
                f"button:has-text('{target_label}')",
                f"[role='option']:has-text('{target_label}')",
                f"*[class*='option']:has-text('{target_label}')",
            ]
            for opt_sel in opt_candidates:
                try:
                    opt = page.locator(opt_sel).first
                    if opt.count() and opt.is_visible():
                        opt.click()
                        page.wait_for_load_state(
                            "domcontentloaded", timeout=15000
                        )
                        time.sleep(delay)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _go_next_page(page: Page, current_page: int, delay: float) -> bool:
    """다음 페이지로 이동 + 실제 이동 검증.

    전략:
      1) 페이지네이션 컨테이너 내부의 a 태그 중 텍스트 == next_n
      2) URL #page{N} 해시 변경
      3) ▶ / 다음 버튼
    각 전략 후 첫 행 텍스트 비교로 실제 이동 검증.
    """
    next_n = current_page + 1

    # 이동 전: 첫 행 텍스트 캡처 (이동 검증용)
    before_first_row = ""
    try:
        before_table = _find_result_table(page)
        if before_table:
            before_rows = before_table.locator("tbody tr").all()
            if before_rows:
                before_first_row = (
                    before_rows[0].inner_text() or ""
                )[:100].strip()
    except Exception:
        pass

    clicked = False
    strategy_used = ""

    # --- 전략 1: 페이지네이션 컨테이너 내부에서만 ---
    container_selectors = [
        ".paging", ".pagination",
        "div[class*='pag']", "ul[class*='pag']",
        "nav.paging", "nav.pagination",
        "[class*='page_nav']", "[class*='pageNav']",
    ]
    for c_sel in container_selectors:
        try:
            for container in page.locator(c_sel).all():
                if not container.is_visible():
                    continue
                for a in container.locator("a").all():
                    try:
                        txt = (a.inner_text() or "").strip()
                        if txt == str(next_n):
                            a.click()
                            clicked = True
                            strategy_used = (
                                f"페이지네이션 컨테이너({c_sel})에서 "
                                f"'{next_n}' 클릭"
                            )
                            break
                    except Exception:
                        continue
                if clicked:
                    break
            if clicked:
                break
        except Exception:
            continue

    # --- 전략 2: URL #pageN 해시 변경 ---
    if not clicked:
        try:
            current_url = page.url
            if "#page" in current_url:
                new_url = re.sub(
                    r"#page\d+", f"#page{next_n}", current_url
                )
                page.goto(
                    new_url, wait_until="domcontentloaded", timeout=15000
                )
                clicked = True
                strategy_used = f"URL 해시 → #page{next_n}"
        except Exception:
            pass

    # --- 전략 3: ▶ / 다음 ---
    if not clicked:
        for sel in [
            "a[title*='다음']",
            "a:has-text('▶')",
            "a:has-text('다음')",
            ".pagination a.next:not(.disabled)",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    cls = (loc.get_attribute("class") or "").lower()
                    if "disabled" in cls:
                        continue
                    loc.click()
                    clicked = True
                    strategy_used = f"▶ 버튼 ({sel})"
                    break
            except Exception:
                continue

    if not clicked:
        log("  ⚠️ 다음 페이지 클릭 가능한 요소를 찾지 못함")
        return False

    # 클릭 후 대기
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    time.sleep(delay)

    # --- 이동 검증: 첫 행이 바뀌었는지 ---
    after_first_row = ""
    try:
        after_table = _find_result_table(page)
        if after_table:
            after_rows = after_table.locator("tbody tr").all()
            if after_rows:
                after_first_row = (
                    after_rows[0].inner_text() or ""
                )[:100].strip()
    except Exception:
        pass

    if not after_first_row:
        # AJAX 지연 가능성 - 한 번 더 대기 후 재확인
        time.sleep(delay * 2)
        try:
            after_table = _find_result_table(page)
            if after_table:
                after_rows = after_table.locator("tbody tr").all()
                if after_rows:
                    after_first_row = (
                        after_rows[0].inner_text() or ""
                    )[:100].strip()
        except Exception:
            pass

    if not after_first_row:
        log(f"  ⚠️ 이동 시도({strategy_used}) 후 결과 테이블 없음")
        return False

    if before_first_row and after_first_row == before_first_row:
        log(
            f"  ⚠️ 이동 시도({strategy_used}) 했으나 첫 행이 동일 - "
            "실제로는 이동 안 됨"
        )
        return False

    log(f"  ✅ 페이지 이동 성공 ({strategy_used})")
    return True


# ============================================================
# 상세 페이지 추출
# ============================================================
def _extract_ingredients(page: Page) -> list[str]:
    """'성분 및 원료' 표 추출."""
    for tbl in page.locator("table").all():
        try:
            ths = tbl.locator("th").all()
            th_texts = [t.inner_text().strip() for t in ths]
            col_idx = -1
            for i, t in enumerate(th_texts):
                if "성분" in t and "원료" in t:
                    col_idx = i
                    break
            if col_idx == -1:
                continue
            tbody_rows = tbl.locator("tbody tr").all()
            target_rows = (
                tbody_rows if tbody_rows else tbl.locator("tr").all()[1:]
            )
            ingredients = []
            for tr in target_rows:
                tds = tr.locator("td").all()
                if col_idx < len(tds):
                    name = re.sub(
                        r"\s+", " ", tds[col_idx].inner_text()
                    ).strip()
                    if name and not re.fullmatch(r"\d+", name):
                        ingredients.append(name)
            if ingredients:
                return ingredients
        except Exception:
            continue
    return []


def _extract_all_detail_pairs(page: Page) -> dict:
    """상세 페이지의 모든 th-td 라벨/값 쌍을 dict로. 라벨 매핑 안 함."""
    pairs: dict = {}
    for tr in page.locator("table tr").all():
        try:
            ths = tr.locator("th").all()
            tds = tr.locator("td").all()
            if len(ths) == 1 and len(tds) == 1:
                label = ths[0].inner_text().strip()
                value = re.sub(
                    r"\s+", " ", tds[0].inner_text()
                ).strip()
                if label and value and label not in pairs:
                    pairs[label] = value
            elif len(ths) > 1 and len(ths) == len(tds):
                for th, td in zip(ths, tds):
                    label = th.inner_text().strip()
                    value = re.sub(
                        r"\s+", " ", td.inner_text()
                    ).strip()
                    if label and value and label not in pairs:
                        pairs[label] = value
        except Exception:
            continue
    return pairs


def _open_detail_in_new_tab(
    context: BrowserContext,
    page: Page,
    link: Locator,
    delay: float,
) -> dict:
    """링크를 새 탭에서 열어 상세 추출. 메인 페이지는 건드리지 않음.

    전략:
      1) Ctrl+클릭 - 이벤트 popup
      2) href 직접 navigate
      3) onclick 코드를 새 탭에서 실행
    """
    new_tab: Page | None = None

    # ---- 전략 1: Ctrl+클릭 ----
    try:
        with context.expect_page(timeout=2500) as popup_info:
            link.click(modifiers=["Control"])
        new_tab = popup_info.value
    except PWTimeout:
        pass
    except Exception:
        pass

    # ---- 전략 2: href ----
    if not new_tab:
        try:
            href = link.get_attribute("href") or ""
            if (
                href
                and not href.startswith("javascript")
                and href not in ("#", "")
            ):
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = BASE_URL + href
                else:
                    full_url = BASE_URL + "/" + href
                new_tab = context.new_page()
                _robust_goto(new_tab, full_url, timeout=20000)
        except Exception as e:
            log(f"    href navigate 실패: {e}")
            if new_tab:
                try:
                    new_tab.close()
                except Exception:
                    pass
                new_tab = None

    # ---- 전략 3: onclick ----
    if not new_tab:
        try:
            onclick = link.get_attribute("onclick") or ""
            if onclick:
                new_tab = context.new_page()
                _robust_goto(new_tab, SEARCH_URL, timeout=20000)
                time.sleep(delay)
                try:
                    new_tab.evaluate(onclick)
                    new_tab.wait_for_load_state(
                        "domcontentloaded", timeout=15000
                    )
                except Exception as e:
                    log(f"    onclick 실행 실패: {e}")
                    new_tab.close()
                    new_tab = None
        except Exception:
            if new_tab:
                try:
                    new_tab.close()
                except Exception:
                    pass
                new_tab = None

    if not new_tab:
        log("    ⚠️ 새 탭 열기 실패 (모든 전략)")
        return {}

    detail: dict = {}
    try:
        time.sleep(delay)
        all_pairs = _extract_all_detail_pairs(new_tab)
        # 모든 라벨-값 쌍을 그대로 detail에
        detail.update(all_pairs)
        # 성분 별도 처리
        ingredients = _extract_ingredients(new_tab)
        if ingredients:
            detail["성분및원료"] = ", ".join(ingredients)
            detail["성분개수"] = len(ingredients)
    except Exception as e:
        log(f"    상세 추출 오류: {e}")
    finally:
        try:
            new_tab.close()
        except Exception:
            pass

    return detail


# ============================================================
# 폼 입력 헬퍼 (food_type / product_name 공용)
# ============================================================
def _fill_search_field(
    page: Page,
    value: str,
    label_texts: list[str],
    selectors: list[str],
    field_label: str,
    required: bool = True,
) -> bool:
    """검색 폼 필드에 값 입력. label/selector 후보를 순차 시도.

    찾지 못했고 required=True면 진단 정보 덤프 후 RuntimeError.
    required=False면 경고 로그 후 False 반환 (선택적 필드).
    """
    # 1) get_by_label
    for label_text in label_texts:
        try:
            loc = page.get_by_label(label_text, exact=False).first
            if loc.count():
                loc.fill(value)
                log(f"  → {field_label}: get_by_label('{label_text}') 사용")
                return True
        except Exception:
            continue

    # 2) 셀렉터 후보
    for sel in selectors:
        try:
            inp = page.locator(sel).first
            if inp.count() and inp.is_visible():
                inp.fill(value)
                log(f"  → {field_label}: {sel} 사용")
                return True
        except Exception:
            continue

    # 못 찾음
    if not required:
        log(f"  ⚠️ {field_label} 입력 필드 못 찾음 (선택 필드라 계속 진행)")
        return False

    # required: 진단 + 예외
    log(f"⚠️ {field_label} 입력 필드 못 찾음 - 진단 덤프:")
    try:
        import tempfile
        debug_dir = tempfile.gettempdir()
        html_path = os.path.join(debug_dir, "food_safety_debug.html")
        png_path = os.path.join(debug_dir, "food_safety_debug.png")
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            log(f"  📄 HTML 저장: {html_path}")
        except Exception:
            pass
        try:
            page.screenshot(path=png_path, full_page=True)
            log(f"  🖼️ 스크린샷 저장: {png_path}")
        except Exception:
            pass
        for inp in page.locator("input:visible").all()[:25]:
            try:
                info = {
                    "type": inp.get_attribute("type"),
                    "name": inp.get_attribute("name"),
                    "id": inp.get_attribute("id"),
                    "placeholder": inp.get_attribute("placeholder"),
                }
                log(f"    {dict((k, v) for k, v in info.items() if v)}")
            except Exception:
                continue
    except Exception:
        pass

    raise RuntimeError(
        f"{field_label} 입력 필드를 찾을 수 없습니다. "
        f"저장된 HTML/스크린샷을 확인해주세요."
    )


# ============================================================
# 식품유형 목록 추출 (Streamlit dropdown 채우기용)
# ============================================================
def list_food_types(headless: bool = True) -> list[str]:
    """검색 페이지의 품목유형 자동완성 드롭다운에서 가능한 모든 식품유형 추출.

    동작 방식:
    1. 검색 페이지 진입
    2. 품목유형 input에 한글 자모를 하나씩 입력 → 자동완성 옵션 캡처
    3. 옵션들 합쳐서 정렬 후 반환

    이 사이트는 select 박스가 아니라 자동완성 input이라
    한글 자모 단위로 prefix 검색해야 모든 항목 발견 가능.
    """
    types: set[str] = set()
    syllable_starts = list("가나다라마바사아자차카타파하")

    with sync_playwright() as p:
        browser = _launch_chromium(p, headless)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            _robust_goto(
                page, "https://www.foodsafetykorea.go.kr/", timeout=30000
            )
            time.sleep(1.5)
            search_url_no_hash = SEARCH_URL.split("#")[0]
            _robust_goto(page, search_url_no_hash, timeout=60000)
            time.sleep(2)
        except Exception as e:
            log(f"⚠️ 페이지 진입 실패: {e}")
            browser.close()
            return []

        # 품목유형 input 찾기
        input_loc = None
        for sel in [
            "input[name='prdlstNm']",
            "input[name='prdlstDcnm']",
            "input[id*='prdlst']",
            "label:has-text('품목유형') ~ input",
            "th:has-text('품목유형') ~ td input",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    input_loc = loc
                    break
            except Exception:
                continue

        if input_loc is None:
            log("⚠️ 품목유형 입력 필드 못 찾음 - 식품유형 목록 추출 불가")
            browser.close()
            return []

        # 각 자모로 prefix 입력 → 자동완성 옵션 수집
        for ch in syllable_starts:
            try:
                input_loc.click()
                input_loc.fill("")
                time.sleep(0.2)
                input_loc.type(ch, delay=80)
                time.sleep(0.8)  # 자동완성 ajax 응답 대기

                # 자동완성 옵션 셀렉터 후보
                option_selectors = [
                    "ul.ui-autocomplete li",
                    ".autocomplete-result li",
                    "[role='listbox'] [role='option']",
                    "ul.search_list li",
                    ".dropdown-menu li",
                ]
                found_any = False
                for opt_sel in option_selectors:
                    try:
                        opts = page.locator(opt_sel).all()
                        if not opts:
                            continue
                        for opt in opts:
                            try:
                                if not opt.is_visible():
                                    continue
                                txt = (opt.inner_text() or "").strip()
                                if txt and 2 <= len(txt) <= 30:
                                    types.add(txt)
                                    found_any = True
                            except Exception:
                                continue
                        if found_any:
                            break
                    except Exception:
                        continue

                # ESC로 자동완성 닫기
                page.keyboard.press("Escape")
                time.sleep(0.2)
            except Exception as e:
                log(f"  '{ch}' 시도 중 오류: {e}")
                continue

        browser.close()

    result = sorted(types)
    log(f"✅ 식품유형 {len(result)}개 추출")
    return result


# ============================================================
# 진단 모드
# ============================================================
def inspect_site(headless: bool = False) -> None:
    with sync_playwright() as p:
        browser = _launch_chromium(p, headless)
        page = browser.new_page(locale="ko-KR")
        log(f"진단 모드: {SEARCH_URL}")
        _robust_goto(page, SEARCH_URL)
        time.sleep(2)

        report: dict = {
            "url": page.url,
            "title": page.title(),
            "labels_with_for": [],
            "buttons": [],
            "selects": [],
            "tables": [],
        }
        for el in page.locator("label").all()[:30]:
            txt = (el.inner_text() or "").strip()
            if txt:
                report["labels_with_for"].append({
                    "label": txt[:30],
                    "for": el.get_attribute("for"),
                })
        for btn in page.locator(
            "button:visible, a.btn:visible, a[role='button']:visible"
        ).all()[:40]:
            txt = (btn.inner_text() or "").strip()
            if txt:
                report["buttons"].append({
                    "text": txt[:30],
                    "class": btn.get_attribute("class"),
                })
        for sel in page.locator("select:visible").all()[:15]:
            try:
                opts = sel.evaluate(
                    "el => Array.from(el.options).map(o => o.text)"
                )
            except Exception:
                opts = []
            report["selects"].append({
                "name": sel.get_attribute("name"),
                "id": sel.get_attribute("id"),
                "options": opts[:10],
            })
        for tbl in page.locator("table:visible").all()[:8]:
            try:
                hdr = (
                    tbl.locator("thead").first.inner_text()
                    if tbl.locator("thead").count()
                    else ""
                )
                rows = tbl.locator("tbody tr").count()
                report["tables"].append({
                    "class": tbl.get_attribute("class"),
                    "header": hdr[:200],
                    "row_count": rows,
                })
            except Exception:
                continue
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


# ============================================================
# 메인 스크래핑
# ============================================================
def scrape(
    food_type: str,
    product_name: str = "",
    max_items: int | None = None,
    max_pages: int | None = None,
    page_size: int = 50,
    headless: bool = True,
    delay: float = 1.0,
) -> list[dict]:
    results: list[dict] = []

    with sync_playwright() as p:
        if _is_container_env():
            log("컨테이너 환경 감지 → headless + 안정성 플래그 적용")
        browser = _launch_chromium(p, headless)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
        )
        # 자동화 탐지 우회
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', "
            "{get: () => undefined});"
        )
        page = context.new_page()

        # 1-a. 메인 페이지 방문 (세션 쿠키 획득)
        log("메인 페이지 방문 (세션 초기화)")
        try:
            _robust_goto(
                page, "https://www.foodsafetykorea.go.kr/",
                timeout=30000,
            )
            time.sleep(2)
        except Exception as e:
            log(f"  메인 페이지 실패 (계속 진행): {e}")

        # 1-b. 검색 페이지 진입 (해시 제거 - hash는 폼 로드를 막을 수 있음)
        search_url_no_hash = SEARCH_URL.split("#")[0]
        log(f"검색 페이지 진입: {search_url_no_hash}")
        _robust_goto(page, search_url_no_hash, timeout=60000)

        # 1-c. 검색 폼이 실제로 렌더링될 때까지 대기 (특정 요소 기준)
        log("  검색 폼 렌더링 대기")
        form_loaded = False
        for wait_sel in [
            "input[name='prdlstNm']",
            "input[name='prdlstDcnm']",
            "label:has-text('품목유형')",
            "th:has-text('품목유형')",
            "input[id*='prdlst']",
        ]:
            try:
                page.wait_for_selector(
                    wait_sel, state="attached", timeout=10000,
                )
                form_loaded = True
                log(f"  ✅ 검색 폼 감지 ({wait_sel})")
                break
            except Exception:
                continue
        if not form_loaded:
            log("  ⚠️ 검색 폼 셀렉터 미감지 - 추가 5초 대기")
            time.sleep(5)
        time.sleep(max(delay, 1.5))
        log(f"  현재 URL: {page.url}")
        log(f"  페이지 제목: {page.title()[:60]}")

        # 2. 품목유형 입력 (빈 문자열이면 건너뜀)
        if food_type and food_type.strip():
            _fill_search_field(
                page, food_type.strip(),
                label_texts=["품목유형", "품목 유형"],
                selectors=[
                    "input[name='prdlstNm']",
                    "input[name='prdlstDcnm']",
                    "input[name='PRDLST_NM']",
                    "input[id*='prdlst']",
                    "input[id*='Prdlst']",
                    "input[placeholder*='품목유형']",
                    "input[title*='품목유형']",
                    "label:has-text('품목유형') ~ input",
                    "th:has-text('품목유형') ~ td input",
                    "th:has-text('품목유형') + td input",
                    "td:has-text('품목유형') + td input",
                ],
                field_label="품목유형",
                required=not (product_name and product_name.strip()),
            )
        else:
            log("품목유형 입력 생략 (전체 검색 모드)")

        # 2-c. 제품명 입력 (선택)
        if product_name and product_name.strip():
            log(f"제품명 입력: '{product_name}'")
            _fill_search_field(
                page, product_name.strip(),
                label_texts=["제품명", "품목명"],
                selectors=[
                    "input[name='prductNm']",
                    "input[name='productNm']",
                    "input[name='PRDUCT_NM']",
                    "input[id*='prduct']",
                    "input[id*='product']",
                    "input[placeholder*='제품명']",
                    "input[title*='제품명']",
                    "label:has-text('제품명') ~ input",
                    "th:has-text('제품명') ~ td input",
                    "th:has-text('제품명') + td input",
                    "td:has-text('제품명') + td input",
                ],
                field_label="제품명",
                required=False,
            )

        # 3. 검색
        log("검색 실행")
        clicked = False
        for sel in [
            "button:has-text('검색')",
            "a.btn:has-text('검색')",
            "a:has-text('검색')",
            "input[type='submit'][value*='검색']",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_visible():
                    btn.click()
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            page.keyboard.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        time.sleep(delay)

        # 검색 결과 총 건수
        total_estimate = None
        try:
            body_text = page.locator("body").inner_text()
            m = re.search(r"총\s*([\d,]+)\s*건", body_text)
            if m:
                total_estimate = int(m.group(1).replace(",", ""))
                log(f"검색 결과: 총 {total_estimate:,}건")
        except Exception:
            pass

        # 4. 최근등록순
        if _click_recent_sort(page, delay):
            log("✅ 최근등록순 정렬 적용")
        else:
            log("⚠️ 최근등록순 버튼 못 찾음")

        # 5. 페이지 사이즈
        if _select_page_size(page, page_size, delay, debug=True):
            log(f"✅ 페이지당 {page_size}개씩 적용")
            # 적용 후 행 수 검증
            rows_check = _extract_table_rows(page)
            log(f"   현재 페이지 행 수: {len(rows_check)}")
        else:
            log(f"⚠️ 페이지 사이즈 변경 실패 (기본 사이즈로 진행)")

        # 6. 페이지 순회
        page_num = 1
        items_collected = 0

        if max_items:
            progress_total = max_items
        elif max_pages:
            progress_total = max_pages * page_size
        elif total_estimate:
            progress_total = min(total_estimate, 99999)
        else:
            progress_total = 100

        while True:
            log(f"=== 페이지 {page_num} 처리 시작 ===")
            rows_data = _extract_table_rows(page)
            if not rows_data:
                log("⚠️ 결과 행 없음 - 종료")
                break
            log(f"  페이지에 {len(rows_data)}개 행")

            # 메인 테이블의 row locators (새 탭 방식이라 그대로 유지됨)
            main_table = _find_result_table(page)
            row_locs = (
                main_table.locator("tbody tr").all() if main_table else []
            )

            for row_idx, row_data in enumerate(rows_data):
                if max_items is not None and items_collected >= max_items:
                    break
                items_collected += 1
                product_name = (
                    row_data.get("제품명")
                    or row_data.get("품목명")
                    or ""
                )
                progress(
                    items_collected, progress_total, product_name[:30]
                )
                log(
                    f"  [{items_collected}/{progress_total}] "
                    f"{product_name[:50]}"
                )

                detail: dict = {}
                if row_idx < len(row_locs):
                    link = row_locs[row_idx].locator("a").first
                    if link.count():
                        detail = _open_detail_in_new_tab(
                            context, page, link, delay
                        )
                    else:
                        log("    ⚠️ 행에 링크 없음")

                merged = {
                    "수집순번": items_collected,
                    "페이지": page_num,
                    **row_data,
                    **detail,
                }
                results.append(merged)

            if max_items is not None and items_collected >= max_items:
                break
            if max_pages is not None and page_num >= max_pages:
                log(f"max_pages 도달 ({max_pages})")
                break

            if not _go_next_page(page, page_num, delay):
                log(f"마지막 페이지 도달 (총 {page_num}페이지)")
                break
            page_num += 1

        browser.close()

    progress(items_collected, items_collected, "완료")
    log(f"✅ 총 {len(results)}건 수집")
    return results


# ============================================================
# CLI
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--food-type", default="",
        help="품목유형 (예: 혼합음료). 비워두면 제품명만으로 검색.",
    )
    parser.add_argument(
        "--product-name", default="",
        help="제품명 검색어 (선택)",
    )
    parser.add_argument(
        "--max-items", "--max", type=int, default=None, dest="max_items",
    )
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument(
        "--list-food-types", action="store_true",
        help="식품유형 목록만 추출 (UI dropdown용)",
    )
    parser.add_argument(
        "--output-file",
        help="결과 JSON을 쓸 파일 경로 (지정 시 stdout 대신 사용)",
    )
    args = parser.parse_args()

    emit("LOG", f"=== 스크래퍼 {SCRAPER_VERSION} 시작 ===")

    try:
        if args.inspect:
            inspect_site(headless=args.headless)
            return 0

        if args.list_food_types:
            types = list_food_types(headless=args.headless)
            payload = json.dumps(types, ensure_ascii=False)
            if args.output_file:
                with open(args.output_file, "w", encoding="utf-8") as f:
                    f.write(payload)
                emit("LOG", f"식품유형 {len(types)}개 저장: {args.output_file}")
            else:
                print(payload)
            return 0

        if not args.food_type and not args.product_name:
            emit("ERROR", "--food-type 또는 --product-name 중 하나 이상 필수")
            return 2

        results = scrape(
            food_type=args.food_type,
            product_name=args.product_name,
            max_items=args.max_items,
            max_pages=args.max_pages,
            page_size=args.page_size,
            headless=args.headless,
            delay=args.delay,
        )
        if args.output_file:
            try:
                with open(args.output_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False)
                emit("LOG", f"결과 저장 완료: {args.output_file} ({len(results)}건)")
            except Exception as e:
                emit("ERROR", f"파일 쓰기 실패: {e}")
                return 1
        else:
            print(json.dumps(results, ensure_ascii=False))
        return 0
    except Exception as e:
        import traceback
        emit("ERROR", str(e))
        emit("LOG", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
