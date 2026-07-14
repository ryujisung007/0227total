# -*- coding: utf-8 -*-
"""
📝 AI 교열·심의 검증 웹앱 (Claude 기반)
- 기사문/문장을 입력하면 ①사실관계 검증 ②문법·어법 판정 ③교열본 ④수정 포인트 ⑤확인 권고 순으로 회신
- '오류 단정'과 '스타일 권고'를 구분하는 심의 검증 모드 포함 ('때문' 사례처럼 사전 근거 기반 판정)
- 실행: streamlit run app.py
- 필요 secrets: ANTHROPIC_API_KEY
"""

import json
import threading
import time
import requests
import streamlit as st
import yfinance as yf

# ──────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────
st.set_page_config(page_title="두피와 기봉이의 AI 교열세상", page_icon="🐶", layout="wide")

API_URL = "https://api.anthropic.com/v1/messages"
MODEL_CANDIDATES = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]

# ──────────────────────────────────────────────
# 시스템 프롬프트 (이 워크플로의 핵심)
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한국 언론사 수준의 전문 교열기자다. 아래 원칙을 반드시 지켜 회신한다.

[작업 순서]
1. 사실관계 검증: 문장 속 고유명사(인명·국적·직책·한자·날짜·수치·순위·기록)를 먼저 점검한다.
   - 웹검색 도구가 있으면 반드시 검색해 확인하고, 없으면 지식 기반 판단에 '확인 권고' 표시를 남긴다.
   - 사실 오류가 있으면 교열보다 먼저 지적한다. (예: 한자 오기 明門→明文, 국적 오기, 호칭 오류 등)
2. 문법·어법 판정: '문법 오류'와 '스타일 권고'를 엄격히 구분한다.
   - 규범 판단은 표준국어대사전·국립국어원 답변 등 근거를 명시한다.
   - 예시: 의존명사 '때문'은 명사·대명사, 어미 '-기/-은/-는/-던' 뒤에 쓸 수 있으므로
     '어려워진 때문으로'는 문법 오류가 아니다. 다만 '-기 때문' 형태가 더 일반적이므로 스타일 권고는 가능.
     (단, '-ㄹ' 관형사형 뒤에는 '때문'이 쓰이지 않음)
3. 교열본 제시: 인용 블록(>)으로 전체 교열본을 먼저 보여준다.
4. 수정 포인트: 항목별로 [무엇을 → 무엇으로] + 이유(사실/문법/스타일 중 어느 차원인지) + 근거(사전·국어원 규정·표준 표기 등 구체적 출처)를 밝힌다.
   - "근거"는 "왠지 어색해서"처럼 막연하게 쓰지 말고, 표준국어대사전/국립국어원 답변/한글 맞춤법 조항/기사체 관례 중 무엇에 해당하는지 명시한다.
   - 원문 유지 가능(선택사항)한 항목은 그렇게 표시한다.
   - 같은 단락 내 어휘 중복(예: '탓' 반복)도 점검한다.
5. 확인 권고: 단정할 수 없는 사실은 "원출처와 대조 권고"로 분리해 안내한다.
6. 미완성 문장이 있으면 지적하고, 뒷부분을 요청한다.

[문체 규칙]
- 기사체 관례 준수: 첫 언급 시 전체 성명, 서명은 『 』 처리 제안, 수사 표기('세 번째') 등.
- 번역투 정리: '~을 통해'→'~(으)로', '진행됐다'→'열렸다' 등 간결한 우리말 우선.
- 띄어쓰기·부호 통일 점검.

[심의 의견 검증 모드]
- 입력이 "심의 의견/권고사항이 타당한가"를 묻는 경우:
  ① 근거(사전·국어원 답변)를 검증하고 ② 결론의 타당성 판정(타당/부분 타당/부당)
  ③ 규범 판정과 실무 수용 여부를 분리해 정리한다.

[교열 점수]
- 100점 만점에서 시작해 사실오류(-25~-40) · 문법오류(-10~-20) · 스타일권고(-2~-5) 항목별로 감점해 산정한다.
- 선택사항(원문 유지 가능) 항목은 감점하지 않는다.
- 감점 근거 없이 점수만 임의로 매기지 말 것 — "수정포인트"에 실제로 잡힌 항목 수·심각도에 비례해야 한다.

[출력 형식]
반드시 아래 JSON만 출력한다. 마크다운 코드펜스, 서두·말미 설명 금지.
{
  "판정": "이상없음 | 사실오류 | 문법오류 | 스타일권고 | 복합",
  "점수": 0,
  "사실검증": [{"항목": "", "판정": "정확|오류|확인필요", "근거": ""}],
  "교열본": "전체 교열된 문장",
  "수정포인트": [{"원문": "", "수정": "", "차원": "사실|문법|스타일|표기", "이유": "", "근거": "", "선택사항": true}],
  "확인권고": ["원출처 대조가 필요한 항목"],
  "총평": "2~3문장 요약"
}"""

# ──────────────────────────────────────────────
# API 호출
# ──────────────────────────────────────────────
def call_claude(text: str, mode: str, use_web: bool, api_key: str) -> dict:
    user_msg = f"[모드: {mode}]\n\n다음 글을 검토해줘.\n\n{text}"
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}] if use_web else []

    last_err = None
    for model in MODEL_CANDIDATES:
        payload = {
            "model": model,
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        }
        if tools:
            payload["tools"] = tools
        try:
            r = requests.post(
                API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            if r.status_code != 200:
                last_err = f"{model}: HTTP {r.status_code} - {r.text[:200]}"
                continue
            data = r.json()
            # 텍스트 블록만 이어붙임 (web_search 결과 블록 제외)
            full_text = "\n".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ).strip()
            clean = full_text.replace("```json", "").replace("```", "").strip()
            # JSON 본문만 추출
            s, e = clean.find("{"), clean.rfind("}")
            if s != -1 and e != -1:
                return {"ok": True, "model": model, "result": json.loads(clean[s : e + 1]), "raw": full_text}
            return {"ok": True, "model": model, "result": None, "raw": full_text}
        except Exception as ex:
            last_err = f"{model}: {ex}"
            continue
    return {"ok": False, "error": last_err}


def call_claude_chat(history: list[dict], review_context: str, api_key: str) -> str:
    """'기봉이' 챗봇 — 방금 나온 교열 결과(review_context)를 문맥으로 물음에 답한다."""
    system = (
        "너는 '기봉이', AI 교열 결과에 대해 친근하고 간결하게 답하는 보조 챗봇이다. "
        "아래 검토 결과 JSON을 근거로만 답하고, 결과에 없는 내용은 모른다고 말한다. "
        "존댓말 대신 친근한 반말 섞인 말투를 쓰되 무례하지는 않게.\n\n"
        f"[이번 검토 결과]\n{review_context}"
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    try:
        r = requests.post(
            API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": MODEL_CANDIDATES[0], "max_tokens": 1000, "system": system, "messages": messages},
            timeout=60,
        )
        if r.status_code != 200:
            return f"(API 오류 {r.status_code}: {r.text[:200]})"
        data = r.json()
        return "\n".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip() or "(빈 응답)"
    except Exception as ex:
        return f"(오류: {ex})"


# ──────────────────────────────────────────────
# 시장 현황 위젯 — 업무 리프레시용 (국장 / 미장, 종목 개인화 가능)
# ──────────────────────────────────────────────
DEFAULT_KR_TICKERS = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "글로벌텍스프리": "204620.KQ",
}
DEFAULT_US_TICKERS = {
    "S&P500": "^GSPC",
    "NASDAQ": "^IXIC",
    "다우존스": "^DJI",
}


def _init_ticker_state():
    if "kr_tickers" not in st.session_state:
        st.session_state["kr_tickers"] = dict(DEFAULT_KR_TICKERS)
    if "us_tickers" not in st.session_state:
        st.session_state["us_tickers"] = dict(DEFAULT_US_TICKERS)


@st.cache_data(ttl=600)  # 10분 캐시 — 매 rerun마다 야후 파이낸스를 두드리지 않도록
def fetch_quote(ticker: str) -> dict:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) >= 2:
            last, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]
            return {"value": float(last), "pct": float((last - prev) / prev * 100)}
        return {"error": "데이터 부족"}
    except Exception as ex:  # noqa: BLE001
        return {"error": str(ex)}


@st.cache_data(ttl=600)
def fetch_history(ticker: str, period: str = "1mo"):
    try:
        return yf.Ticker(ticker).history(period=period)
    except Exception:  # noqa: BLE001
        return None


def render_ticker_group(title: str, session_key: str):
    st.markdown(f"**{title}**")
    tickers = st.session_state[session_key]
    for name, code in list(tickers.items()):
        d = fetch_quote(code)
        row = st.columns([5, 1])
        with row[0]:
            if "pct" in d:
                up = d["pct"] >= 0
                label = "국짐" if up else "스머프"
                color = "red" if up else "blue"  # 국내 관례: 상승=빨강, 하락=파랑
                st.markdown(f"{name}  {d['value']:,.1f}  :{color}[{label} {d['pct']:+.2f}%]")
            else:
                st.markdown(f"{name}  _조회 실패_")
        with row[1]:
            if name not in DEFAULT_KR_TICKERS and name not in DEFAULT_US_TICKERS:
                if st.button("✕", key=f"rm_{session_key}_{name}", help="목록에서 제거"):
                    del st.session_state[session_key][name]
                    st.rerun()

    with st.form(key=f"add_{session_key}", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_name = c1.text_input("표시 이름", key=f"name_{session_key}", label_visibility="collapsed", placeholder="표시 이름")
        new_code = c2.text_input("티커(yfinance)", key=f"code_{session_key}", label_visibility="collapsed", placeholder="예: NVDA, 000270.KS")
        added = c3.form_submit_button("➕ 추가")
        if added and new_name.strip() and new_code.strip():
            st.session_state[session_key][new_name.strip()] = new_code.strip()
            st.rerun()


def render_market_widget():
    _init_ticker_state()
    st.caption("📈 국장 당일 · 미장 전일 마감 — 10분 캐시. 종목은 자유롭게 추가/삭제 가능")
    render_ticker_group("🇰🇷 국장", "kr_tickers")
    st.divider()
    render_ticker_group("🇺🇸 미장", "us_tickers")

    all_tickers = {**st.session_state["kr_tickers"], **st.session_state["us_tickers"]}
    st.divider()
    pick = st.selectbox("🔎 자세히 볼 종목", ["(선택 안 함)"] + list(all_tickers.keys()))
    st.session_state["market_detail_pick"] = None if pick == "(선택 안 함)" else (pick, all_tickers[pick])


def render_market_detail():
    """사이드바에서 종목을 선택하면 메인화면(우측)에 상세 정보를 보여준다."""
    pick = st.session_state.get("market_detail_pick")
    if not pick:
        return
    name, code = pick
    st.markdown(f"### 📊 {name} 상세")
    d = fetch_quote(code)
    hist = fetch_history(code)
    c1, c2 = st.columns([1, 2])
    with c1:
        if "pct" in d:
            up = d["pct"] >= 0
            label = "국짐" if up else "스머프"
            st.metric(name, f"{d['value']:,.2f}", f"{d['pct']:+.2f}% ({label})")
        else:
            st.warning(f"조회 실패: {d.get('error')}")
        if hist is not None and not hist.empty:
            st.caption(
                f"1개월 최고 {hist['High'].max():,.2f} · 최저 {hist['Low'].min():,.2f} · "
                f"평균 거래량 {hist['Volume'].mean():,.0f}"
            )
    with c2:
        if hist is not None and not hist.empty:
            st.line_chart(hist["Close"], height=220)
        else:
            st.info("차트 데이터를 불러오지 못했습니다.")
    st.divider()


# ──────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────
hero_col, title_col = st.columns([1, 3])
with hero_col:
    st.image("assets/edit_hero.png", width="stretch")
with title_col:
    st.title("🐶 두피와 기봉이의 AI 교열세상")
    st.caption("사실검증 → 문법판정(오류/스타일 구분) → 교열본 → 수정 포인트 → 확인 권고")

with st.sidebar:
    st.subheader("⚙️ 설정")
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = st.text_input("Anthropic API Key", type="password")
    mode = st.radio(
        "검토 모드",
        ["기사 교열", "심의 의견 검증", "문법 판정만"],
        help="기사 교열=전체 워크플로 / 심의 의견 검증='이 권고가 타당한가' 판정 / 문법 판정만=사실검증 생략",
    )
    use_web = st.toggle("🔍 웹검색 사실검증", value=True, help="고유명사·수치·기록을 실시간 검색으로 확인")
    st.divider()
    st.caption("판정 원칙: '문법 오류'와 '스타일 권고'를 구분하고, 규범 판단에는 사전 근거를 명시합니다.")
    st.divider()
    render_market_widget()

render_market_detail()

text = st.text_area(
    "검토할 글을 입력하세요",
    height=220,
    placeholder="예) 이 대통령은 2022년 8월 당권을 거머쥔 이후 문 전 대통령을 처음 예방한 자리에서도…",
)

if st.button("🚀 교열 판정", type="primary", width="stretch"):
    if not api_key:
        st.error("API 키를 입력하세요 (secrets의 ANTHROPIC_API_KEY 또는 사이드바 입력).")
    elif not text.strip():
        st.warning("검토할 글을 입력하세요.")
    else:
        # 실제 API 호출은 백그라운드 스레드에서 돌리고, 메인 스레드는 예상 소요시간
        # 대비 남은시간을 progress bar로 보여준다 (Claude가 진행률을 알려주진 않으므로
        # 텍스트 길이·웹검색 여부로 추정한 총 소요시간 대비 경과 비율로 근사).
        result_box = {}

        def _worker():
            result_box["res"] = call_claude(text.strip(), mode, use_web, api_key)

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()

        est_total = (25 if use_web else 12) + min(20, len(text) // 150)
        progress_bar = st.progress(0, text="AI 검토 시작…")
        t0 = time.time()
        while worker_thread.is_alive():
            elapsed = time.time() - t0
            pct = min(0.95, elapsed / est_total)
            remaining = max(0, est_total - elapsed)
            progress_bar.progress(pct, text=f"AI 검토 중… 약 {remaining:.0f}초 남음")
            time.sleep(0.2)
        worker_thread.join()
        progress_bar.progress(1.0, text="완료!")
        time.sleep(0.3)
        progress_bar.empty()

        res = result_box["res"]

        if not res["ok"]:
            st.error(f"API 호출 실패: {res['error']}")
        elif res["result"] is None:
            st.warning("구조화 파싱에 실패해 원문 응답을 표시합니다.")
            st.markdown(res["raw"])
        else:
            r = res["result"]
            verdict = r.get("판정", "-")
            color = {"이상없음": "green", "스타일권고": "blue", "사실오류": "red", "문법오류": "orange", "복합": "violet"}.get(verdict, "gray")

            score = r.get("점수")
            score_col, verdict_col = st.columns([1, 3])
            with score_col:
                if isinstance(score, (int, float)):
                    stars = round(max(0, min(100, score)) / 20)
                    st.metric("교열 점수", f"{score:.0f}점")
                    st.markdown("⭐" * stars + "☆" * (5 - stars))
            with verdict_col:
                st.markdown(f"### 판정: :{color}[{verdict}]  \n_모델: {res['model']}_")

            facts = r.get("사실검증") or []
            if facts:
                st.subheader("① 사실관계 검증")
                for f in facts:
                    icon = {"정확": "✅", "오류": "❌", "확인필요": "⚠️"}.get(f.get("판정"), "•")
                    st.markdown(f"{icon} **{f.get('항목','')}** — {f.get('판정','')}: {f.get('근거','')}")

            if r.get("교열본"):
                st.subheader("② 교열본")
                st.info(r["교열본"])
                # st.code는 마우스를 올리면 오른쪽 위에 복사 아이콘이 뜨고, height를 안 주면
                # 내용 길이에 맞춰 자동으로 늘어난다(스크롤로 잘리지 않음).
                st.code(r["교열본"], language=None, wrap_lines=True)

            points = r.get("수정포인트") or []
            if points:
                st.subheader("③ 수정 포인트")
                for p in points:
                    opt = " *(선택사항)*" if p.get("선택사항") else ""
                    basis = p.get("근거", "")
                    basis_line = f"  \n  📚 근거: {basis}" if basis else ""
                    st.markdown(
                        f"- **[{p.get('차원','')}]** '{p.get('원문','')}' → '{p.get('수정','')}'{opt}  \n"
                        f"  ↳ {p.get('이유','')}{basis_line}"
                    )

            recos = r.get("확인권고") or []
            if recos:
                st.subheader("④ 원출처 대조 권고")
                for x in recos:
                    st.markdown(f"- 🔎 {x}")

            if r.get("총평"):
                st.subheader("⑤ 총평")
                st.success(r["총평"])

            # 이번 검토 결과를 세션에 저장 — 아래 기봉이 챗봇이 참고 문맥으로 쓴다.
            # 새 검토가 끝날 때마다 문맥이 바뀌므로 채팅 기록도 초기화한다.
            st.session_state["review_context"] = json.dumps(r, ensure_ascii=False)
            st.session_state["gibong_chat"] = []

# ──────────────────────────────────────────────
# 기봉이 챗봇 — 검토 결과에 대해 궁금한 걸 물어보는 창구
# ──────────────────────────────────────────────
if st.session_state.get("review_context"):
    st.divider()
    st.subheader("🐶 기봉이한테 물어보기")
    st.caption("위 교열 결과(판정·근거·수정포인트)에 대해 편하게 물어보세요.")

    for m in st.session_state.get("gibong_chat", []):
        with st.chat_message(m["role"], avatar="🐶" if m["role"] == "assistant" else None):
            st.markdown(m["content"])

    question = st.chat_input("예) 이 수정포인트는 왜 스타일권고가 아니라 문법오류야?")
    if question:
        st.session_state["gibong_chat"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant", avatar="🐶"):
            with st.spinner("기봉이가 생각 중…"):
                answer = call_claude_chat(
                    st.session_state["gibong_chat"], st.session_state["review_context"], api_key
                )
            st.markdown(answer)
        st.session_state["gibong_chat"].append({"role": "assistant", "content": answer})
