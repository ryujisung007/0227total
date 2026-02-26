"""🏷️ 표시사항 검토"""
import streamlit as st
import pandas as pd
PAGE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGE_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.common import *

# page_config set in main app.py
st.markdown("# 🏷️ 표시사항 검토 & 식품등의 표시기준")
st.markdown("식품등의 표시기준 PDF 학습 → 표시사항 작성 → 적합성 비교 분석")
st.markdown("---")

if "label_pdf_text" not in st.session_state:
    st.session_state.label_pdf_text = ""
if "label_analysis" not in st.session_state:
    st.session_state.label_analysis = None

# ━━━ 기본 표시기준 데이터 (식품등의 표시기준 주요 항목) ━━━
LABEL_REQUIREMENTS = {
    "필수 표시사항": [
        {"항목": "제품명", "기준": "식품유형에 맞는 제품명 사용", "관련조항": "제4조", "필수": True},
        {"항목": "식품유형", "기준": "식품공전상 분류명 기재", "관련조항": "제4조", "필수": True},
        {"항목": "업소명 및 소재지", "기준": "제조업소명과 주소 기재", "관련조항": "제4조", "필수": True},
        {"항목": "유통기한(소비기한)", "기준": "년월일 또는 년월 표시, 2023.1.1부터 소비기한 전환", "관련조항": "제5조", "필수": True},
        {"항목": "내용량", "기준": "g, ml, 개수 등으로 표시", "관련조항": "제4조", "필수": True},
        {"항목": "원재료명", "기준": "함량 높은 순, 5가지 이상은 %표시", "관련조항": "제6조", "필수": True},
        {"항목": "영양성분 표시", "기준": "열량, 탄수화물, 당류, 단백질, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨 9가지", "관련조항": "제7조", "필수": True},
        {"항목": "알레르기 유발물질", "기준": "난류, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지, 복숭아, 토마토, 호두, 닭, 쇠고기, 오징어, 조개 등 22종", "관련조항": "제8조", "필수": True},
        {"항목": "보관방법", "기준": "보관온도, 방법 등 구체적 기재", "관련조항": "제4조", "필수": True},
        {"항목": "주의사항", "기준": "섭취 시 주의사항 등", "관련조항": "제10조", "필수": True},
    ],
    "음료류 추가 표시사항": [
        {"항목": "과즙함량", "기준": "과채음료 10% 이상 시 함량 표시", "관련조항": "제11조", "필수": True},
        {"항목": "카페인 함량", "기준": "카페인 1ml당 0.15mg 이상 시 '고카페인' 표시, 총카페인 함량", "관련조항": "제11조", "필수": True},
        {"항목": "인공감미료 사용", "기준": "대체감미료 사용 시 명칭 표시", "관련조항": "제6조", "필수": False},
        {"항목": "살균/멸균 표시", "기준": "살균 또는 멸균 제품 해당 표시", "관련조항": "제4조", "필수": False},
    ],
}

# ━━━ 사이드바: PDF 업로드 ━━━
with st.sidebar:
    st.markdown("### 📄 식품등의 표시기준 PDF")
    st.caption("식약처 고시 PDF를 업로드하세요")

    label_pdf = st.file_uploader("PDF 업로드", type=["pdf"], key="label_pdf_upload")
    if label_pdf and not st.session_state.label_pdf_text:
        with st.spinner("📄 PDF 텍스트 추출 중..."):
            result = extract_pdf_text(label_pdf)
            if isinstance(result, tuple):
                text, msg = result
            else:
                text, msg = result, ""
            if text:
                st.session_state.label_pdf_text = text
                st.success(f"✅ {label_pdf.name} ({len(text):,}자) — {msg}")
            else:
                st.error(f"❌ {msg}")

    if st.session_state.label_pdf_text:
        st.markdown("---")
        st.markdown(f"**학습된 문서:** {len(st.session_state.label_pdf_text):,}자")

    st.markdown("---")
    st.link_button("📖 식품등의 표시기준 원문", "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000231887", use_container_width=True)
    st.link_button("🔗 식품안전나라", "https://www.foodsafetykorea.go.kr", use_container_width=True)

# ━━━ 탭 ━━━
tab1, tab2, tab3, tab4 = st.tabs(["✍️ 표시사항 작성", "📊 적합성 비교표", "📄 기준 원문 검색", "🤖 AI 검토"])

# ━━━ TAB 1: 표시사항 작성 ━━━
with tab1:
    st.markdown("### ✍️ 표시사항 작성")

    form = st.session_state.get("ai_formulation")

    with st.form("label_form"):
        c1, c2 = st.columns(2)

        with c1:
            product_name = st.text_input("제품명", value=form.get("productName", "") if form else "")
            food_type = st.selectbox("식품유형", ["혼합음료", "탄산음료", "과채음료", "과채주스", "유산균음료", "커피", "에너지음료", "두유류", "기타"])
            company = st.text_input("업소명", placeholder="주식회사 OO식품")
            address = st.text_input("소재지", placeholder="서울시 OO구 OO로 123")
            shelf_life = st.text_input("소비기한", value=form.get("shelfLife", "") if form else "", placeholder="제조일로부터 12개월")
            volume = st.text_input("내용량", value=form.get("totalVolume", "500ml") if form else "500ml")

        with c2:
            ingredients_text = st.text_area("원재료명 (함량순)",
                value=", ".join(i["name"] for i in form.get("ingredients", [])) if form else "",
                height=80)
            nutrition = st.text_area("영양성분 (1회 제공량 기준)",
                value=f"열량 {form.get('calories', '-')}kcal" if form else "",
                placeholder="열량 45kcal, 탄수화물 11g, 당류 10g, 단백질 0g, 지방 0g, 나트륨 15mg",
                height=80)
            allergens = st.multiselect("알레르기 유발물질",
                ["난류","우유","메밀","땅콩","대두","밀","고등어","게","새우","돼지고기",
                 "복숭아","토마토","호두","닭고기","쇠고기","오징어","조개류(굴,전복,홍합)"],
                default=[])
            storage = st.text_input("보관방법", value="직사광선을 피하고 서늘한 곳에 보관")
            caution = st.text_area("주의사항", value="개봉 후 냉장보관, 어린이 과다섭취 주의", height=60)
            caffeine = st.text_input("카페인 함량 (해당 시)", placeholder="총카페인 함량 80mg")

        submitted = st.form_submit_button("📋 표시사항 저장", type="primary", use_container_width=True)

    if submitted:
        st.session_state.label_data = {
            "제품명": product_name, "식품유형": food_type, "업소명": company,
            "소재지": address, "소비기한": shelf_life, "내용량": volume,
            "원재료명": ingredients_text, "영양성분": nutrition,
            "알레르기": ", ".join(allergens) if allergens else "해당없음",
            "보관방법": storage, "주의사항": caution, "카페인": caffeine,
        }
        st.success("✅ 표시사항이 저장되었습니다!")

    # 미리보기
    if st.session_state.get("label_data"):
        st.markdown("---")
        st.markdown("### 📋 표시사항 미리보기")
        ld = st.session_state.label_data
        label_df = pd.DataFrame(list(ld.items()), columns=["항목", "내용"])
        st.dataframe(label_df, use_container_width=True, hide_index=True)

        csv_dl = label_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 표시사항 CSV", csv_dl, "표시사항.csv", "text/csv")


# ━━━ TAB 2: 적합성 비교표 ━━━
with tab2:
    st.markdown("### 📊 표시기준 적합성 비교 분석표")

    ld = st.session_state.get("label_data", {})

    for section_name, items in LABEL_REQUIREMENTS.items():
        st.markdown(f"#### {section_name}")
        rows = []
        for item in items:
            # 작성 여부 체크
            field_map = {
                "제품명": "제품명", "식품유형": "식품유형", "업소명 및 소재지": "업소명",
                "유통기한(소비기한)": "소비기한", "내용량": "내용량",
                "원재료명": "원재료명", "영양성분 표시": "영양성분",
                "알레르기 유발물질": "알레르기", "보관방법": "보관방법",
                "주의사항": "주의사항", "카페인 함량": "카페인",
                "과즙함량": "원재료명",
            }
            mapped_field = field_map.get(item["항목"], "")
            my_value = ld.get(mapped_field, "") if mapped_field else ""
            filled = bool(my_value and my_value.strip() and my_value.strip() != "해당없음" and my_value.strip() != "-")

            status = "✅ 작성됨" if filled else ("⚠️ 미작성" if item["필수"] else "ℹ️ 선택사항")
            if not ld:
                status = "— (표시사항 미작성)"

            row = {
                "표시항목": item["항목"],
                "기준": item["기준"],
                "조항": item["관련조항"],
                "필수": "✅필수" if item["필수"] else "선택",
                "작성 내용": my_value[:50] if my_value else "-",
                "적합 판정": status,
            }

            # PDF 근거 찾기
            if st.session_state.label_pdf_text:
                keyword = item["항목"].replace("(", "").replace(")", "").split("/")[0]
                if keyword in st.session_state.label_pdf_text:
                    row["PDF 근거"] = "📄 있음"
                else:
                    row["PDF 근거"] = "—"
            else:
                row["PDF 근거"] = "—"

            rows.append(row)

        compare_df = pd.DataFrame(rows)
        st.dataframe(compare_df, use_container_width=True, hide_index=True)

    # 종합 판정
    if ld:
        all_required = [item for items in LABEL_REQUIREMENTS.values() for item in items if item["필수"]]
        filled_count = 0
        for item in all_required:
            mapped = {"제품명":"제품명","식품유형":"식품유형","업소명 및 소재지":"업소명",
                      "유통기한(소비기한)":"소비기한","내용량":"내용량","원재료명":"원재료명",
                      "영양성분 표시":"영양성분","알레르기 유발물질":"알레르기","보관방법":"보관방법",
                      "주의사항":"주의사항"}.get(item["항목"], "")
            if mapped and ld.get(mapped, "").strip():
                filled_count += 1

        rate = filled_count / len(all_required) * 100 if all_required else 0
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        c1.metric("필수항목 충족률", f"{rate:.0f}%")
        c2.metric("작성/필수", f"{filled_count}/{len(all_required)}")
        c3.metric("종합", "✅ 적합" if rate >= 90 else "⚠️ 보완필요")


# ━━━ TAB 3: 기준 원문 검색 ━━━
with tab3:
    st.markdown("### 📄 식품등의 표시기준 원문 검색")

    if not st.session_state.label_pdf_text:
        st.info("""
        📤 **사이드바에서 '식품등의 표시기준' PDF를 업로드하세요.**

        PDF 다운로드 링크:
        - [법제처 국가법령정보센터](https://www.law.go.kr)에서 '식품등의 표시기준' 검색
        - [식품안전나라](https://www.foodsafetykorea.go.kr)에서 다운로드 가능
        """)
    else:
        search_kw = st.text_input("🔍 키워드 검색", placeholder="예: 유통기한, 영양성분, 원재료, 알레르기")

        if search_kw:
            text = st.session_state.label_pdf_text
            lines = text.split("\n")
            matched = []
            for i, line in enumerate(lines):
                if search_kw.lower() in line.lower():
                    # 앞뒤 2줄 포함
                    context = lines[max(0,i-1):min(len(lines),i+3)]
                    matched.append("\n".join(context))

            st.markdown(f"**'{search_kw}' 검색 결과: {len(matched)}건**")
            for j, m in enumerate(matched[:20]):
                with st.expander(f"결과 {j+1}", expanded=j < 3):
                    st.text(m)
        else:
            st.text_area("전문 (상위 5,000자)", st.session_state.label_pdf_text[:5000], height=400)


# ━━━ TAB 4: AI 검토 ━━━
with tab4:
    st.markdown("### 🤖 AI 표시사항 적합성 검토")

    ld = st.session_state.get("label_data", {})
    if not ld:
        st.warning("먼저 [✍️ 표시사항 작성] 탭에서 표시사항을 입력하세요")
    else:
        if st.button("🤖 AI 적합성 검토 실행", type="primary", use_container_width=True):
            with st.spinner("AI가 표시기준을 확인하고 있습니다..."):
                label_info = "\n".join(f"- {k}: {v}" for k, v in ld.items())
                pdf_ref = st.session_state.label_pdf_text[:2000] if st.session_state.label_pdf_text else "(PDF 없음)"

                prompt = f"""당신은 식품표시 전문가입니다. 아래 표시사항이 '식품등의 표시기준'에 적합한지 검토하세요.

[작성된 표시사항]
{label_info}

[식품등의 표시기준 참고]
{pdf_ref}

다음을 분석해주세요:
1. 필수 표시항목 누락 여부
2. 각 항목별 기준 충족 여부 (구체적)
3. 영양성분 표시 적정성
4. 알레르기 표시 적정성
5. 개선 필요 사항
6. 종합 판정 (적합/부적합/조건부적합)

한국어로 전문적으로 작성하세요."""

                try:
                    api_key = get_api_key()
                    if not api_key:
                        raise Exception("API 키 없음")
                    resp = __import__("requests").post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                        },
                        json={"model":"gpt-4o-mini","max_tokens":2000,
                              "messages":[
                                  {"role":"system","content":"당신은 식품표시 전문가입니다. 한국어로 전문적으로 답변하세요."},
                                  {"role":"user","content":prompt},
                              ]},
                        timeout=60,
                    )
                    if resp.status_code == 401:
                        raise Exception("API 키 유효하지 않음")
                    data = resp.json()
                    result = data["choices"][0]["message"]["content"]
                except:
                    result = f"""## 표시사항 적합성 검토 결과

### 1. 필수 표시항목 점검
- 제품명: {'✅' if ld.get('제품명') else '❌ 누락'}
- 식품유형: {'✅' if ld.get('식품유형') else '❌ 누락'}
- 업소명: {'✅' if ld.get('업소명') else '❌ 누락'}
- 소비기한: {'✅' if ld.get('소비기한') else '❌ 누락'}
- 내용량: {'✅' if ld.get('내용량') else '❌ 누락'}
- 원재료명: {'✅' if ld.get('원재료명') else '❌ 누락'}
- 영양성분: {'✅' if ld.get('영양성분') else '❌ 누락'}
- 알레르기: {'✅' if ld.get('알레르기') else '⚠️ 확인필요'}
- 보관방법: {'✅' if ld.get('보관방법') else '❌ 누락'}

### 2. 개선 필요 사항
- 영양성분 9가지 항목 전부 기재 여부 확인 필요
- 원재료명 함량순 배열 확인 필요
- {'카페인 함량 표시 확인 필요' if ld.get('카페인') else '카페인 해당 여부 확인'}

### 3. 종합
기본 항목은 {'대부분 작성됨' if sum(1 for v in ld.values() if v.strip()) > 7 else '보완 필요'}. 세부 기준 충족 여부는 전문가 최종 확인 권장.

⚠️ *AI 참고용 분석이며, 최종 판단은 식약처 기준을 따르세요.*"""

                st.session_state.label_analysis = result
                st.markdown(result)

        elif st.session_state.label_analysis:
            st.markdown(st.session_state.label_analysis)

# ━━━ 챗봇 ━━━
render_chatbot("표시사항",
    page_context="식품등의 표시기준 PDF 학습 → 표시사항 작성 → 적합성 비교표 페이지.",
    system_extra="식품 표시기준, 영양성분, 알레르기, 원재료 표시 관련 질문에 답변하세요.")
