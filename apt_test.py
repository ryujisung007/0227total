"""
Gemini API 진단 도구 v3
— 전체 HTTP 응답 raw 출력
— 모델 목록 직접 조회
"""
import streamlit as st
import requests
import json

st.set_page_config(page_title="Gemini 진단", page_icon="🔬")
st.title("🔬 Gemini API 진단 도구")

# ── API 키 ──
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
    st.error("❌ API 키 없음")
    st.stop()

st.divider()

# ── STEP 1: 모델 목록 조회 ──
st.subheader("STEP 1 — 사용 가능한 모델 목록 조회")
st.caption("어떤 모델을 쓸 수 있는지 먼저 확인합니다")

if st.button("📋 모델 목록 조회 (v1)", use_container_width=True):
    for ver in ["v1", "v1beta"]:
        with st.spinner(f"{ver} 조회 중..."):
            try:
                r = requests.get(
                    f"https://generativelanguage.googleapis.com/{ver}/models?key={api_key}",
                    timeout=10
                )
                st.markdown(f"**{ver}** — HTTP {r.status_code}")
                data = r.json()
                if r.ok:
                    models = [
                        m["name"].replace("models/", "")
                        for m in data.get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ]
                    if models:
                        st.success(f"✅ generateContent 지원 모델 {len(models)}개:")
                        for m in models:
                            st.code(m)
                    else:
                        st.warning("모델 없음")
                else:
                    st.error(f"❌ {data.get('error', {}).get('message', str(data))}")
            except Exception as e:
                st.error(f"예외: {e}")

st.divider()

# ── STEP 2: 모델 직접 호출 (raw 응답 전체 출력) ──
st.subheader("STEP 2 — 모델 직접 호출 (raw 응답)")

col1, col2 = st.columns(2)
with col1:
    ver = st.selectbox("API 버전", ["v1", "v1beta"])
with col2:
    model = st.text_input("모델명", value="gemini-1.5-flash")

if st.button("🚀 호출 테스트", use_container_width=True, type="primary"):
    url = f"https://generativelanguage.googleapis.com/{ver}/models/{model}:generateContent?key={api_key}"
    st.caption(f"호출 URL: `.../{ver}/models/{model}:generateContent?key={api_key[:8]}...`")

    with st.spinner("호출 중..."):
        try:
            r = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "안녕하세요"}]}]},
                timeout=15,
            )
            st.code(f"HTTP 상태: {r.status_code}")

            data = r.json()
            if r.ok:
                reply = data["candidates"][0]["content"]["parts"][0]["text"]
                st.success(f"✅ 성공! 응답: {reply[:200]}")
            else:
                st.error("❌ 실패 — 전체 에러 응답:")
                st.json(data)   # raw JSON 전체 출력

        except Exception as e:
            st.error(f"예외 발생: {type(e).__name__}: {e}")

st.divider()

# ── STEP 3: 간단 채팅 ──
st.subheader("STEP 3 — 채팅 테스트")
st.caption("STEP 2에서 작동한 버전/모델 조합을 입력하세요")

if "chat" not in st.session_state:
    st.session_state.chat = []

for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.write(m["content"])

prompt = st.chat_input("메시지...")
if prompt:
    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        url = f"https://generativelanguage.googleapis.com/{ver}/models/{model}:generateContent?key={api_key}"
        try:
            r = requests.post(url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            if r.ok:
                reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                st.write(reply)
                st.session_state.chat.append({"role": "assistant", "content": reply})
            else:
                err = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
                st.error(f"❌ {err}")
        except Exception as e:
            st.error(f"❌ {e}")

if st.session_state.chat:
    if st.button("초기화"):
        st.session_state.chat = []
        st.rerun()
