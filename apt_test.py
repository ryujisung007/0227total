"""
Gemini API 연결 테스트 챗봇 v2
— 작동하는 모델 자동 탐색
— secrets.toml 의 GOOGLE_API_KEY 사용
"""
import streamlit as st
import requests

st.set_page_config(page_title="Gemini API 테스트", page_icon="🤖")
st.title("🤖 Gemini API 연결 테스트")

# ── API 키 로드 ──
def get_key():
    try:
        for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "google_api_key"):
            v = st.secrets.get(k, "")
            if v:
                return v
    except Exception:
        pass
    return ""

api_key = get_key()

if api_key:
    st.success(f"✅ API 키 로드됨: `{api_key[:8]}...{api_key[-4:]}`")
else:
    st.error("❌ API 키 없음 — secrets.toml 에 GOOGLE_API_KEY 추가 필요")
    st.stop()

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# ── 사용 가능한 모델 목록 자동 조회 ──
@st.cache_data(ttl=3600)
def get_models(key):
    try:
        r = requests.get(f"{BASE}?key={key}", timeout=10)
        if r.ok:
            return [
                m["name"].replace("models/", "")
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
                and "embedding" not in m["name"]
            ]
    except Exception:
        pass
    return []

with st.spinner("사용 가능한 모델 조회 중..."):
    available = get_models(api_key)

# 우선순위 후보 목록 (최신 → 구버전 순)
CANDIDATES = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-preview-03-25",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro",
]

if available:
    st.info(f"📋 사용 가능한 모델 {len(available)}개 조회됨")
    model_options = available
else:
    st.warning("모델 목록 자동 조회 실패 — 후보 목록에서 선택")
    model_options = CANDIDATES

MODEL = st.selectbox("테스트할 모델 선택", model_options)
URL = f"{BASE}/{MODEL}:generateContent?key={api_key}"

# ── 자동 탐색 버튼 ──
if st.button("🔍 작동하는 모델 자동 탐색", use_container_width=True):
    found = None
    prog = st.progress(0)
    for i, m in enumerate(CANDIDATES):
        prog.progress((i+1)/len(CANDIDATES), text=f"테스트 중: {m}")
        try:
            r = requests.post(
                f"{BASE}/{m}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "hi"}]}]},
                timeout=10,
            )
            if r.ok:
                st.success(f"✅ 작동 확인: **{m}**")
                found = m
                break
            else:
                err = r.json().get("error", {}).get("message", "")[:60]
                st.warning(f"❌ {m}: {err}")
        except Exception as e:
            st.warning(f"❌ {m}: {e}")
    prog.empty()
    if not found:
        st.error("모든 후보 모델 실패 — API 키 권한을 확인하세요")
    else:
        st.info(f"이 모델명을 main 앱 코드에 사용하세요: `{found}`")

st.divider()

# ── 단순 ping 테스트 ──
if st.button("🔌 선택 모델 연결 테스트", use_container_width=True):
    with st.spinner(f"{MODEL} 호출 중..."):
        try:
            r = requests.post(URL,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "안녕"}]}]},
                timeout=15,
            )
            st.code(f"HTTP {r.status_code}")
            data = r.json()
            if r.ok:
                reply = data["candidates"][0]["content"]["parts"][0]["text"]
                st.success(f"✅ 성공: {reply[:120]}")
            else:
                st.error(f"❌ {data.get('error', {}).get('message', str(data))}")
        except Exception as e:
            st.error(f"❌ {e}")

st.divider()

# ── 채팅 ──
st.subheader("💬 채팅 테스트")
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.write(m["content"])

prompt = st.chat_input("메시지 입력...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("응답 중..."):
            try:
                r = requests.post(URL,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=30,
                )
                if r.ok:
                    reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    st.write(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                else:
                    err = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
                    st.error(f"❌ {err}")
            except Exception as e:
                st.error(f"❌ {e}")

if st.session_state.messages:
    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.rerun()
