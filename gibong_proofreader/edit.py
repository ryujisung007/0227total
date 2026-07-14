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
import datetime as dt
from zoneinfo import ZoneInfo
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
    "삼성전자우": "005935.KS",
    "SK하이닉스": "000660.KS",
    "대우건설": "047040.KS",
    "삼성전기": "009150.KS",
    "글로벌텍스프리": "204620.KQ",
    "펌텍코리아": "251970.KQ",
    "LG화학": "051910.KS",
    "현대차": "005380.KS",
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


@st.cache_data(ttl=60)  # 1분 캐시 — "실시간"에 가깝게, 그래도 매 rerun마다 두드리진 않게
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


KR_TZ = ZoneInfo("Asia/Seoul")
US_TZ = ZoneInfo("America/New_York")


def market_phase(market: str) -> tuple[str, dt.datetime]:
    """market: 'KR' 또는 'US'. 반환: (프리장/장중/애프터장/휴장, 해당 시장 기준 현재시각)."""
    if market == "KR":
        now = dt.datetime.now(KR_TZ)
        open_t, close_t = dt.time(9, 0), dt.time(15, 30)
    else:
        now = dt.datetime.now(US_TZ)
        open_t, close_t = dt.time(9, 30), dt.time(16, 0)

    if now.weekday() >= 5:
        return "휴장", now
    t = now.time()
    if t < open_t:
        return "프리장", now
    if t > close_t:
        return "애프터장", now
    return "장중", now


PHASE_BADGE = {
    "프리장": ("🌅", "#94a3b8"),
    "장중": ("🟢", "#16a34a"),
    "애프터장": ("🌙", "#64748b"),
    "휴장": ("💤", "#94a3b8"),
}


def phase_banner_html(market: str) -> str:
    """국장/미장 섹션 맨 위에 한 번만 — 지금이 프리장/장중/애프터장인지 시간과 함께 큼직하게."""
    phase, now = market_phase(market)
    icon, color = PHASE_BADGE[phase]
    tz_label = "한국시간" if market == "KR" else "미국동부시간"
    return (
        f'<div style="display:inline-block;padding:4px 12px;border-radius:999px;'
        f'background:{color}1a;color:{color};font-weight:700;font-size:14px;margin-bottom:6px;">'
        f'{icon} {phase} · {now.strftime("%H:%M")} ({tz_label})'
        f"</div>"
    )


@st.cache_data(ttl=300)
def _intraday_shape(ticker: str):
    """오늘 5분봉으로 전반부/후반부 흐름을 대략 분류한다. 데이터 부족하면 None."""
    try:
        h = yf.Ticker(ticker).history(period="1d", interval="5m")
        if len(h) < 6:
            return None
        closes = h["Close"]
        open_px = closes.iloc[0]
        mid_px = closes.iloc[len(closes) // 2]
        now_px = closes.iloc[-1]
        return float(mid_px - open_px), float(now_px - mid_px)
    except Exception:  # noqa: BLE001
        return None


def market_comment(code: str, market: str, pct: float) -> str:
    """카드 안에 넣을 한 줄 — 장중일 때만 흐름(전강후약 등) + 장난스러운 한마디.
    지금이 프리장/장중/애프터장인지는 섹션 상단 phase_banner_html에서 한 번만 보여준다."""
    phase, _ = market_phase(market)

    if phase == "장중":
        shape = _intraday_shape(code)
        if abs(pct) < 0.2:
            trend = "약보합"
        elif shape is None:
            trend = "강세" if pct > 0 else "약세"
        else:
            first_half, second_half = shape
            if first_half > 0 and second_half < 0:
                trend = "전강후약"
            elif first_half < 0 and second_half > 0:
                trend = "후강전약"
            elif first_half > 0 and second_half > 0:
                trend = "상승세 지속"
            elif first_half < 0 and second_half < 0:
                trend = "하락세 지속"
            else:
                trend = "약보합"
        prefix = f"{trend} · "
    else:
        prefix = ""

    joke = "오늘도 스머프 예정 ㅜㅜ" if pct < 0 else "오늘은 국짐 가나!?"
    return f"{prefix}{joke}"


def _card_html(name: str, d: dict, market: str = "KR", code: str = "") -> str:
    if "pct" not in d:
        return (
            f'<div style="border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;'
            f'margin-bottom:10px;background:#fafafa;">'
            f'<div style="font-size:13px;color:#64748b;">{name}</div>'
            f'<div style="font-size:14px;color:#94a3b8;">조회 실패</div></div>'
        )
    up = d["pct"] >= 0
    label = "국짐" if up else "스머프"
    color = "#b91c1c" if up else "#1d4ed8"  # 국내 관례: 상승=빨강, 하락=파랑
    arrow = "▲" if up else "▼"
    comment = market_comment(code, market, d["pct"]) if code else ""
    comment_html = f'<div style="font-size:12px;color:#94a3b8;margin-top:4px;">{comment}</div>' if comment else ""
    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;
                margin-bottom:10px;background:#ffffff;box-shadow:0 1px 2px rgba(0,0,0,.04);">
      <div style="font-size:13px;color:#64748b;">{name}</div>
      <div style="font-size:24px;font-weight:700;color:#0f172a;">{d['value']:,.1f}</div>
      <div style="font-size:14px;font-weight:600;color:{color};">
        {arrow} {d['pct']:+.2f}% <span style="font-weight:400;">· {label}</span>
      </div>
      {comment_html}
    </div>
    """


def _stock_row_html(name: str, d: dict) -> str:
    """개별 종목 — 지수 카드보다 작고 한 줄로 압축된 형태."""
    if "pct" not in d:
        return f'<div style="font-size:13px;color:#94a3b8;padding:4px 0;">{name} · 조회 실패</div>'
    up = d["pct"] >= 0
    label = "국짐" if up else "스머프"
    color = "#b91c1c" if up else "#1d4ed8"
    arrow = "▲" if up else "▼"
    return (
        f'<div style="display:flex;justify-content:space-between;padding:5px 2px;'
        f'border-bottom:1px solid #f1f5f9;font-size:13px;">'
        f'<span style="color:#334155;">{name}</span>'
        f'<span style="color:#0f172a;">{d["value"]:,.1f}</span>'
        f'<span style="font-weight:600;color:{color};">{arrow} {d["pct"]:+.2f}% · {label}</span>'
        f"</div>"
    )


def _biggest_mover(all_stock_quotes: dict, want_gainer: bool):
    """all_stock_quotes: {name: quote_dict}. 가장 크게 오른/내린 종목 하나를 찾는다."""
    candidates = [(name, d["pct"]) for name, d in all_stock_quotes.items() if "pct" in d]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1]) if want_gainer else min(candidates, key=lambda x: x[1])


def render_market_briefing():
    """메인화면 맨 아래 — 작게 접혀있는 참고용 시장 브리핑. 교열이 메인, 이건 부가 기능."""
    _init_ticker_state()
    with st.expander("📊 오늘의 시장 브리핑 (참고용, 클릭해서 펼치기)", expanded=False):
        cap_col, refresh_col = st.columns([5, 1])
        cap_col.caption(
            "🐶 두피 관심종목(국장) · 미장 — 1분 캐시로 최대한 실시간에 가깝게. "
            "무료 데이터 특성상 실거래가와 몇 분 차이날 수 있어요. 종목 추가/삭제는 왼쪽 사이드바에서."
        )
        if refresh_col.button("🔄 새로고침"):
            fetch_quote.clear()
            st.rerun()

        all_stock_quotes = {}  # 떡상/떡락 집계용 (지수 제외, 개별 종목만)

        for label, key, market in [("🐶 두피 관심종목 (국장)", "kr_tickers", "KR"), ("🇺🇸 미장", "us_tickers", "US")]:
            tickers = st.session_state[key]
            if not tickers:
                continue
            index_items = {n: c for n, c in tickers.items() if c.startswith("^")}
            stock_items = {n: c for n, c in tickers.items() if not c.startswith("^")}

            with st.container(border=True):
                head_col, badge_col = st.columns([1, 2])
                head_col.markdown(f"**{label}**")
                badge_col.markdown(phase_banner_html(market), unsafe_allow_html=True)

                if index_items:
                    cols = st.columns(len(index_items))
                    for col, (name, code) in zip(cols, index_items.items()):
                        with col:
                            st.markdown(
                                _card_html(name, fetch_quote(code), market=market, code=code),
                                unsafe_allow_html=True,
                            )
                if stock_items:
                    for name, code in stock_items.items():
                        d = fetch_quote(code)
                        all_stock_quotes[name] = d
                        st.markdown(_stock_row_html(name, d), unsafe_allow_html=True)

        gainer = _biggest_mover(all_stock_quotes, want_gainer=True)
        loser = _biggest_mover(all_stock_quotes, want_gainer=False)
        if gainer or loser:
            st.markdown("**오늘의 떡상 · 떡락** _(추적 중인 개별 종목 기준)_")
            mc1, mc2 = st.columns(2)
            if gainer:
                mc1.markdown(f"🚀 떡상: **{gainer[0]}** :red[+{gainer[1]:.2f}%]")
            if loser:
                mc2.markdown(f"💀 떡락: **{loser[0]}** :blue[{loser[1]:.2f}%]")

    render_market_detail()
    st.divider()


def render_ticker_manage(title: str, session_key: str):
    """사이드바 — 종목 추가/삭제 관리 (수치는 메인화면 브리핑 카드에서 확인)."""
    st.markdown(f"**{title}**")
    tickers = st.session_state[session_key]
    for name in list(tickers.keys()):
        row = st.columns([4, 1])
        row[0].caption(name)
        if name not in DEFAULT_KR_TICKERS and name not in DEFAULT_US_TICKERS:
            if row[1].button("✕", key=f"rm_{session_key}_{name}", help="목록에서 제거"):
                del st.session_state[session_key][name]
                st.rerun()

    with st.form(key=f"add_{session_key}", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_name = c1.text_input("표시 이름", key=f"name_{session_key}", label_visibility="collapsed", placeholder="표시 이름")
        new_code = c2.text_input("티커(yfinance)", key=f"code_{session_key}", label_visibility="collapsed", placeholder="예: NVDA, 000270.KS")
        added = c3.form_submit_button("➕")
        if added and new_name.strip() and new_code.strip():
            st.session_state[session_key][new_name.strip()] = new_code.strip()
            st.toast(f"'{new_name.strip()}' 추가됨 — 메인화면 브리핑에서 확인하세요.", icon="✅")
            st.rerun()


def render_market_widget():
    """사이드바 — 종목 관리 + 상세보기 선택. 실제 브리핑 카드는 메인화면에 표시된다."""
    _init_ticker_state()
    render_ticker_manage("🇰🇷 국장", "kr_tickers")
    st.divider()
    render_ticker_manage("🇺🇸 미장", "us_tickers")

    all_tickers = {**st.session_state["kr_tickers"], **st.session_state["us_tickers"]}
    st.divider()
    pick = st.selectbox("🔎 자세히 볼 종목", ["(선택 안 함)"] + list(all_tickers.keys()))
    st.session_state["market_detail_pick"] = None if pick == "(선택 안 함)" else (pick, all_tickers[pick])


def render_market_detail():
    """종목을 선택하면 브리핑 카드 아래에 상세(가격·1개월 차트)를 보여준다."""
    pick = st.session_state.get("market_detail_pick")
    if not pick:
        return
    name, code = pick
    st.markdown(f"#### 🔎 {name} 상세")
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


# ──────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────
hero_col, title_col = st.columns([1, 3])
with hero_col:
    try:
        st.image("assets/edit_hero.png", width="stretch")
    except Exception:
        pass  # 헤더 이미지가 없거나 로드 실패해도 앱 전체가 죽으면 안 된다
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

# 교열 도구가 첫 화면의 주인공 — 시장 브리핑은 항상 맨 아래, 별도 섹션으로 분리
st.divider()
render_market_briefing()
