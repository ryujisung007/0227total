"""
Gemini API 연결 테스트 챗봇
— secrets.toml 의 GOOGLE_API_KEY 사용
— gemini-2.0-flash REST 직접 호출
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

# ── 키 상태 표시 ──
if api_key:
    st.success(f"✅ API 키 로드됨: `{api_key[:8]}...{api_key[-4:]}`")
else:
    st.error("❌ API 키 없음 — secrets.toml 에 GOOGLE_API_KEY 추가 필요")
    st.stop()

# ── 모델 선택 ──
MODEL = st.selectbox("테스트 모델", [
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro",
])

URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={api_key}"

# ── 연결 테스트 버튼 ──
if st.button("🔌 연결 테스트 (ping)", use_container_width=True):
    with st.spinner("API 호출 중..."):
        try:
            r = requests.post(URL,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "hi"}]}]},
                timeout=15,
            )
            st.code(f"HTTP 상태: {r.status_code}")
            data = r.json()
            if r.ok:
                reply = data["candidates"][0]["content"]["parts"][0]["text"]
                st.success(f"✅ 성공! 모델 응답: {reply[:100]}")
            else:
                st.error(f"❌ 실패: {data.get('error', {}).get('message', str(data))}")
        except Exception as e:
            st.error(f"❌ 예외 발생: {e}")

st.divider()

# ── 간단 채팅 ──
st.subheader("채팅 테스트")

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
