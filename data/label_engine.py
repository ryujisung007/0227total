"""
핵심 엔진: PDF 지식베이스 구축 · 적부 판정 · 법령 참조
"""
import pandas as pd
import os, json, re, io
from datetime import datetime

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_THIS_DIR)
KB_DIR = os.path.join(_APP_DIR, "knowledge")
os.makedirs(KB_DIR, exist_ok=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. PDF 텍스트 추출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_pdf(uploaded_file):
    """PDF → 텍스트 (다중 라이브러리 폴백)"""
    try:
        uploaded_file.seek(0)
    except:
        pass
    try:
        raw = uploaded_file.read()
    except:
        return None, "파일 읽기 실패"
    if not raw or len(raw) < 100:
        return None, "파일이 비어있거나 손상됨"

    for lib_name, extractor in [
        ("pypdf", _extract_pypdf),
        ("pdfplumber", _extract_pdfplumber),
    ]:
        try:
            text = extractor(raw)
            if text and len(text.strip()) > 50:
                return text, f"{lib_name}로 추출 완료 ({len(text):,}자)"
        except:
            continue
    return None, "텍스트 추출 실패 — 스캔 PDF이거나 보안 설정된 파일"

def _extract_pypdf(raw):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(p.extract_text() or "" for p in reader.pages)

def _extract_pdfplumber(raw):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 지식베이스 구축 (PDF → 조항별 청크)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 3개 법령의 핵심 검토 항목
REGULATION_SCHEMA = {
    "식품등의_표시기준": {
        "법령명": "식품등의 표시기준",
        "약칭": "표시기준",
        "검토항목": [
            {"id": "LBL-01", "항목": "제품명", "설명": "제품명이 식품유형에 맞게 표시되었는지", "관련조항": "제3조, 제4조", "필수": True},
            {"id": "LBL-02", "항목": "식품유형", "설명": "식품공전상 분류에 맞는 식품유형 기재", "관련조항": "제4조", "필수": True},
            {"id": "LBL-03", "항목": "업소명 및 소재지", "설명": "제조업소명(상호)과 소재지 기재", "관련조항": "제4조", "필수": True},
            {"id": "LBL-04", "항목": "소비기한(유통기한)", "설명": "소비기한 또는 품질유지기한 표시 (2023.1.1부터 소비기한 전환)", "관련조항": "제5조", "필수": True},
            {"id": "LBL-05", "항목": "내용량", "설명": "g, ml, 개수 등 단위와 함께 표시", "관련조항": "제4조", "필수": True},
            {"id": "LBL-06", "항목": "원재료명", "설명": "함량 높은 순으로 표시, 복합원재료 괄호 처리, 2% 미만 순서무관", "관련조항": "제6조", "필수": True},
            {"id": "LBL-07", "항목": "성분함량 표시", "설명": "주표시면에 특정 원재료명 강조 시 그 함량(%) 표시", "관련조항": "제6조의2", "필수": True},
            {"id": "LBL-08", "항목": "영양성분", "설명": "열량, 탄수화물, 당류, 단백질, 지방, 포화지방, 트랜스지방, 콜레스테롤, 나트륨 9종 필수", "관련조항": "제7조", "필수": True},
            {"id": "LBL-09", "항목": "알레르기 유발물질", "설명": "22종 알레르기 유발물질 함유 시 별도 표시 (난류, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기, 복숭아, 토마토, 호두, 닭고기, 쇠고기, 오징어, 조개류, 잣, 아황산류 등)", "관련조항": "제8조", "필수": True},
            {"id": "LBL-10", "항목": "보관방법/주의사항", "설명": "보관온도·방법, 섭취 시 주의사항", "관련조항": "제4조, 제10조", "필수": True},
            {"id": "LBL-11", "항목": "카페인 함량", "설명": "카페인 1ml당 0.15mg 이상 시 '고카페인 함유' 및 총카페인 함량 표시", "관련조항": "제11조", "필수": False},
            {"id": "LBL-12", "항목": "과즙함량", "설명": "과채음료에서 과즙함량 10% 이상 시 함량 표시", "관련조항": "제11조", "필수": False},
            {"id": "LBL-13", "항목": "나트륨 함량 비교표시", "설명": "나트륨 저감 강조 시 비교대상 제품 및 저감률 표시", "관련조항": "제7조", "필수": False},
            {"id": "LBL-14", "항목": "글자크기", "설명": "주표시면 및 정보표시면의 글자 크기 기준 충족", "관련조항": "제3조", "필수": True},
            {"id": "LBL-15", "항목": "부당한 표시·광고", "설명": "의약품으로 오인할 표현, 허위·과대 표시·광고 금지", "관련조항": "제12조", "필수": True},
        ],
    },
    "원산지_표시요령": {
        "법령명": "농수산물의 원산지 표시 등에 관한 법률 시행령/요령",
        "약칭": "원산지",
        "검토항목": [
            {"id": "ORI-01", "항목": "원산지 표시 대상", "설명": "원산지 표시 대상 원재료인지 확인 (농산물, 수산물, 축산물 등)", "관련조항": "시행령 제3조", "필수": True},
            {"id": "ORI-02", "항목": "원산지 표시방법", "설명": "국가명(수입품) 또는 시·도명(국산) 표시", "관련조항": "시행령 제4조", "필수": True},
            {"id": "ORI-03", "항목": "배합비율 순 표시", "설명": "2가지 이상 원산지 혼합 시 배합비율 높은 순으로 표시", "관련조항": "시행령 제4조", "필수": True},
            {"id": "ORI-04", "항목": "원산지 위치·크기", "설명": "소비자가 쉽게 알아볼 수 있는 위치에 읽기 쉬운 크기로 표시", "관련조항": "표시요령 제5조", "필수": True},
            {"id": "ORI-05", "항목": "가공식품 원산지", "설명": "사용된 원료 중 배합비율 1·2순위 원료의 원산지 표시", "관련조항": "표시요령 제6조", "필수": True},
            {"id": "ORI-06", "항목": "원산지 변경 시", "설명": "원산지 변경 시 기존 재고 소진기간 내 변경 표시", "관련조항": "표시요령 제7조", "필수": False},
        ],
    },
    "기구용기_규격": {
        "법령명": "기구 및 용기·포장의 기준 및 규격",
        "약칭": "용기규격",
        "검토항목": [
            {"id": "PKG-01", "항목": "재질 표시", "설명": "용기·포장 재질 종류 표시 (PET, PP, PE, 유리 등)", "관련조항": "제2조", "필수": True},
            {"id": "PKG-02", "항목": "용출·침출시험", "설명": "식품과 접촉하는 면의 용출·침출 시험 적합 여부", "관련조항": "제3조", "필수": True},
            {"id": "PKG-03", "항목": "중금속 기준", "설명": "납, 카드뮴, 수은 등 중금속 용출 기준 이내", "관련조항": "제3조, 별표", "필수": True},
            {"id": "PKG-04", "항목": "재활용 표시", "설명": "분리배출 표시(재질·구조 등급 표시)", "관련조항": "자원재활용법", "필수": True},
            {"id": "PKG-05", "항목": "내열온도 적합", "설명": "충전·살균 온도에 적합한 내열성 보유", "관련조항": "제4조", "필수": True},
            {"id": "PKG-06", "항목": "차광성", "설명": "빛에 의한 품질변화 방지를 위한 차광성 (해당 시)", "관련조항": "제4조", "필수": False},
            {"id": "PKG-07", "항목": "가스차단성", "설명": "탄산가스 유지를 위한 가스차단성 (탄산음료 해당)", "관련조항": "제4조", "필수": False},
        ],
    },
}

# 22종 알레르기 유발물질
ALLERGENS_22 = [
    "난류(가금류)","우유","메밀","땅콩","대두","밀","고등어","게","새우","돼지고기",
    "복숭아","토마토","호두","닭고기","쇠고기","오징어","조개류(굴,전복,홍합포함)",
    "잣","아황산류","참깨","아몬드","잔새우(크릴)"
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSV 템플릿 (사용자가 이 양식으로 업로드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CSV_TEMPLATE = """항목,내용
제품명,예) 스파클링 레몬에이드
식품유형,예) 탄산음료
업소명,예) 주식회사 OO식품
소재지,예) 서울특별시 강남구 OO로 123
소비기한,예) 제조일로부터 12개월
내용량,예) 500ml
원재료명,"예) 정제수, 과당포도당액(국산), 구연산, 이산화탄소, 레몬농축액(이탈리아산)3%, 비타민C, 천연향료"
영양성분,"예) 1회 제공량 250ml 기준 / 열량 45kcal / 탄수화물 11g / 당류 10g / 단백질 0g / 지방 0g / 포화지방 0g / 트랜스지방 0g / 콜레스테롤 0mg / 나트륨 15mg"
알레르기,예) 해당없음
보관방법,예) 직사광선을 피하고 서늘한 곳에 보관
주의사항,예) 개봉 후 냉장보관하고 빠른 시일 내 드세요
카페인함량,예) 해당없음
과즙함량,예) 레몬과즙 3%
원산지(주원료1),예) 정제수(국산)
원산지(주원료2),예) 과당포도당액(국산)
용기재질,예) PET
용기용출시험,예) 적합
재활용표시,예) PET 1등급
"""

SAMPLE_LABELS = {
    "탄산음료 (정상)": {
        "제품명": "스파클링 레몬에이드",
        "식품유형": "탄산음료",
        "업소명": "주식회사 프레시음료",
        "소재지": "경기도 이천시 마장면 산업단지로 55",
        "소비기한": "제조일로부터 12개월",
        "내용량": "500ml",
        "원재료명": "정제수, 과당포도당액(국산), 구연산, 이산화탄소, 레몬농축과즙(이탈리아산)3%, 비타민C, 천연향료",
        "영양성분": "1회 제공량 250ml / 열량 45kcal, 탄수화물 11g, 당류 10g, 단백질 0g, 지방 0g, 포화지방 0g, 트랜스지방 0g, 콜레스테롤 0mg, 나트륨 15mg",
        "알레르기": "해당없음",
        "보관방법": "직사광선을 피하고 서늘한 곳에 보관",
        "주의사항": "개봉 후 냉장보관, 어린이 과다섭취 주의",
        "카페인함량": "해당없음",
        "과즙함량": "레몬과즙 3%",
        "원산지(주원료1)": "정제수(국산)",
        "원산지(주원료2)": "과당포도당액(국산)",
        "용기재질": "PET",
        "용기용출시험": "적합",
        "재활용표시": "PET 1등급",
    },
    "에너지음료 (부적합 예시)": {
        "제품명": "울트라 에너지부스트",
        "식품유형": "",  # 누락
        "업소명": "OO에너지",
        "소재지": "",  # 누락
        "소비기한": "2025.12",
        "내용량": "250ml",
        "원재료명": "정제수, 포도당, 타우린, 카페인, 구연산, 합성향료, 비타민B군",
        "영양성분": "열량 46kcal, 당류 10g",  # 불완전
        "알레르기": "",  # 누락
        "보관방법": "",  # 누락
        "주의사항": "",  # 누락
        "카페인함량": "",  # 고카페인인데 미표시
        "과즙함량": "",
        "원산지(주원료1)": "",  # 누락
        "원산지(주원료2)": "",
        "용기재질": "알루미늄캔",
        "용기용출시험": "",  # 미확인
        "재활용표시": "",  # 누락
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 지식베이스 저장/로드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_knowledge(doc_key, text, filename):
    """추출된 PDF 텍스트를 지식베이스에 저장"""
    filepath = os.path.join(KB_DIR, f"{doc_key}.json")
    # 조항별 청크 분리
    chunks = _chunk_legal_text(text)
    data = {
        "doc_key": doc_key,
        "filename": filename,
        "full_text_length": len(text),
        "chunks": chunks,
        "updated": datetime.now().isoformat(),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(chunks)

def load_knowledge(doc_key):
    """저장된 지식베이스 로드"""
    filepath = os.path.join(KB_DIR, f"{doc_key}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def load_all_knowledge():
    """전체 지식베이스 로드"""
    result = {}
    for doc_key in REGULATION_SCHEMA.keys():
        kb = load_knowledge(doc_key)
        if kb:
            result[doc_key] = kb
    return result

def _chunk_legal_text(text):
    """법령 텍스트를 조항 단위로 분리"""
    chunks = []
    # 제N조, 제N항, 별표 등 패턴
    patterns = [
        r'(제\d+조(?:의\d+)?[\s\(].*?)(?=제\d+조|$)',
        r'(별표\s*\d+.*?)(?=별표\s*\d+|$)',
        r'(부칙.*?)(?=부칙|$)',
    ]
    # 기본: 500자 단위 청크
    if len(text) < 200:
        return [{"idx": 0, "text": text}]

    # 조항 패턴 매칭
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.DOTALL):
            found.append(m.group(1).strip())

    if found:
        for i, chunk in enumerate(found):
            if len(chunk) > 50:
                chunks.append({"idx": i, "text": chunk[:2000]})
    else:
        # 패턴 없으면 고정 길이 청크
        for i in range(0, len(text), 800):
            chunk = text[i:i+800].strip()
            if chunk:
                chunks.append({"idx": len(chunks), "text": chunk})

    return chunks if chunks else [{"idx": 0, "text": text[:2000]}]


def search_knowledge(doc_key, keyword):
    """지식베이스에서 키워드 검색"""
    kb = load_knowledge(doc_key)
    if not kb:
        return []
    results = []
    for chunk in kb.get("chunks", []):
        if keyword.lower() in chunk["text"].lower():
            results.append(chunk["text"])
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 적부 판정 엔진 (규칙 기반)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_compliance(label_data):
    """
    표시사항 데이터 → 적부 판정
    label_data: dict {"제품명": "...", "식품유형": "...", ...}
    returns: list of dicts
    """
    results = []

    # ─── 식품등의 표시기준 ───
    results += _check_labeling(label_data)

    # ─── 원산지 표시요령 ───
    results += _check_origin(label_data)

    # ─── 기구용기 규격 ───
    results += _check_packaging(label_data)

    return results


def _val(label_data, key):
    """안전하게 값 가져오기"""
    v = label_data.get(key, "")
    return v.strip() if isinstance(v, str) else str(v).strip()


def _check_labeling(ld):
    """식품등의 표시기준 검토"""
    results = []

    # LBL-01 제품명
    v = _val(ld, "제품명")
    results.append({
        "id": "LBL-01", "법령": "표시기준", "항목": "제품명",
        "입력값": v,
        "판정": "적합" if v else "부적합",
        "사유": "제품명 기재됨" if v else "제품명 누락 — 제4조 위반",
        "조항": "제3조, 제4조",
    })

    # LBL-02 식품유형
    v = _val(ld, "식품유형")
    results.append({
        "id": "LBL-02", "법령": "표시기준", "항목": "식품유형",
        "입력값": v,
        "판정": "적합" if v else "부적합",
        "사유": "식품유형 기재됨" if v else "식품유형 누락 — 식품공전상 분류명 필수 기재",
        "조항": "제4조",
    })

    # LBL-03 업소명/소재지
    v1 = _val(ld, "업소명")
    v2 = _val(ld, "소재지")
    ok = bool(v1 and v2)
    results.append({
        "id": "LBL-03", "법령": "표시기준", "항목": "업소명·소재지",
        "입력값": f"{v1} / {v2}",
        "판정": "적합" if ok else "부적합",
        "사유": "업소명·소재지 기재됨" if ok else f"{'업소명' if not v1 else ''} {'소재지' if not v2 else ''} 누락",
        "조항": "제4조",
    })

    # LBL-04 소비기한
    v = _val(ld, "소비기한")
    has_date = bool(v)
    is_expiry = "소비" in v or "제조일로부터" in v or "까지" in v
    is_old = "유통기한" in v
    results.append({
        "id": "LBL-04", "법령": "표시기준", "항목": "소비기한",
        "입력값": v,
        "판정": "적합" if has_date else "부적합",
        "사유": ("소비기한 표시됨" + (" (⚠️ '유통기한' 용어 → 2023.1.1부터 '소비기한'으로 변경 필요)" if is_old else "")) if has_date else "소비기한 누락",
        "조항": "제5조",
    })

    # LBL-05 내용량
    v = _val(ld, "내용량")
    has_unit = bool(re.search(r'\d+\s*(ml|g|kg|L|개|매|EA)', v, re.I))
    results.append({
        "id": "LBL-05", "법령": "표시기준", "항목": "내용량",
        "입력값": v,
        "판정": "적합" if has_unit else ("주의" if v else "부적합"),
        "사유": "내용량 단위 포함 표시됨" if has_unit else ("단위(ml, g 등) 확인 필요" if v else "내용량 누락"),
        "조항": "제4조",
    })

    # LBL-06 원재료명
    v = _val(ld, "원재료명")
    ingr_count = len([x for x in v.split(",") if x.strip()]) if v else 0
    results.append({
        "id": "LBL-06", "법령": "표시기준", "항목": "원재료명",
        "입력값": v[:80] + "..." if len(v) > 80 else v,
        "판정": "적합" if ingr_count >= 2 else "부적합",
        "사유": f"원재료 {ingr_count}종 표시 (함량순 배열 여부 확인 필요)" if ingr_count >= 2 else "원재료명 누락 또는 부족",
        "조항": "제6조",
    })

    # LBL-08 영양성분
    v = _val(ld, "영양성분")
    required_9 = ["열량", "탄수화물", "당류", "단백질", "지방", "포화지방", "트랜스지방", "콜레스테롤", "나트륨"]
    found = [n for n in required_9 if n in v]
    missing = [n for n in required_9 if n not in v]
    results.append({
        "id": "LBL-08", "법령": "표시기준", "항목": "영양성분",
        "입력값": v[:80] + "..." if len(v) > 80 else v,
        "판정": "적합" if len(found) >= 9 else ("주의" if len(found) >= 5 else "부적합"),
        "사유": f"9종 중 {len(found)}종 표시" + (f" — 누락: {', '.join(missing)}" if missing else " (전체 충족)"),
        "조항": "제7조",
    })

    # LBL-09 알레르기
    v = _val(ld, "알레르기")
    results.append({
        "id": "LBL-09", "법령": "표시기준", "항목": "알레르기 유발물질",
        "입력값": v,
        "판정": "적합" if v else "부적합",
        "사유": "알레르기 표시됨 (원재료 대비 정확성 확인 필요)" if v else "알레르기 유발물질 표시 누락 — 해당없음이라도 기재 권장",
        "조항": "제8조",
    })

    # LBL-10 보관/주의
    v1 = _val(ld, "보관방법")
    v2 = _val(ld, "주의사항")
    results.append({
        "id": "LBL-10", "법령": "표시기준", "항목": "보관방법·주의사항",
        "입력값": f"{v1} / {v2}",
        "판정": "적합" if v1 and v2 else ("주의" if v1 or v2 else "부적합"),
        "사유": "보관방법·주의사항 기재됨" if v1 and v2 else f"{'보관방법' if not v1 else ''} {'주의사항' if not v2 else ''} 누락",
        "조항": "제4조, 제10조",
    })

    # LBL-11 카페인
    raw_ingr = _val(ld, "원재료명").lower()
    has_caffeine_ingr = any(k in raw_ingr for k in ["카페인", "커피", "과라나", "녹차추출"])
    v = _val(ld, "카페인함량")
    if has_caffeine_ingr:
        results.append({
            "id": "LBL-11", "법령": "표시기준", "항목": "카페인 함량",
            "입력값": v,
            "판정": "적합" if v and "해당없음" not in v else "부적합",
            "사유": "카페인 함량 표시됨" if v and "해당없음" not in v else "카페인 함유 원료 사용 → 고카페인 표시 및 총카페인 함량 기재 필요",
            "조항": "제11조",
        })

    return results


def _check_origin(ld):
    """원산지 표시요령 검토"""
    results = []
    v1 = _val(ld, "원산지(주원료1)")
    v2 = _val(ld, "원산지(주원료2)")

    # ORI-01 표시대상
    results.append({
        "id": "ORI-01", "법령": "원산지", "항목": "원산지 표시",
        "입력값": f"1순위: {v1} / 2순위: {v2}",
        "판정": "적합" if v1 else "부적합",
        "사유": "주원료 원산지 표시됨" if v1 else "주원료 원산지 미표시 — 배합비율 1순위 이상 원료의 원산지 표시 필수",
        "조항": "시행령 제3조, 제4조",
    })

    # 국산/수입 표기 확인
    if v1:
        has_origin = any(k in v1 for k in ["국산","수입","산)","국내산","외국산"])
        results.append({
            "id": "ORI-02", "법령": "원산지", "항목": "원산지 표시방법",
            "입력값": v1,
            "판정": "적합" if has_origin else "주의",
            "사유": "국가명/국산 표기 확인됨" if has_origin else "원산지 국가명 또는 '국산' 표기가 명확하지 않음",
            "조항": "시행령 제4조",
        })

    # 원재료명 내 원산지 괄호 표기 확인
    ingr = _val(ld, "원재료명")
    origin_in_ingr = bool(re.search(r'\(.*?산\)', ingr))
    results.append({
        "id": "ORI-05", "법령": "원산지", "항목": "원재료명 내 원산지",
        "입력값": ingr[:60] + "..." if len(ingr) > 60 else ingr,
        "판정": "적합" if origin_in_ingr else "주의",
        "사유": "원재료명에 원산지 괄호 표기 확인됨" if origin_in_ingr else "원재료명에 원산지(국산, OO산) 표기 확인 필요",
        "조항": "표시요령 제6조",
    })

    return results


def _check_packaging(ld):
    """기구용기 규격 검토"""
    results = []

    v = _val(ld, "용기재질")
    known_materials = ["PET","PP","PE","HDPE","LDPE","PS","유리","알루미늄","캔","종이팩","테트라팩"]
    is_known = any(m.lower() in v.lower() for m in known_materials) if v else False
    results.append({
        "id": "PKG-01", "법령": "용기규격", "항목": "용기 재질",
        "입력값": v,
        "판정": "적합" if is_known else ("주의" if v else "부적합"),
        "사유": f"재질 '{v}' 확인됨" if is_known else ("재질 표기 확인 필요" if v else "용기 재질 미기재"),
        "조항": "제2조",
    })

    v = _val(ld, "용기용출시험")
    results.append({
        "id": "PKG-02", "법령": "용기규격", "항목": "용출시험",
        "입력값": v,
        "판정": "적합" if "적합" in v else ("주의" if v else "미확인"),
        "사유": "용출시험 적합 확인됨" if "적합" in v else ("시험 결과 확인 필요" if v else "용출시험 결과 미기재 — 식품접촉 재질의 용출·침출시험 성적서 필요"),
        "조항": "제3조",
    })

    v = _val(ld, "재활용표시")
    results.append({
        "id": "PKG-04", "법령": "용기규격", "항목": "재활용 표시",
        "입력값": v,
        "판정": "적합" if v else "부적합",
        "사유": "재활용(분리배출) 표시 확인됨" if v else "재활용 표시 누락 — 분리배출 표시(재질·구조 등급) 필수",
        "조항": "자원재활용법",
    })

    return results


def get_summary(results):
    """판정 결과 요약"""
    total = len(results)
    ok = sum(1 for r in results if r["판정"] == "적합")
    warn = sum(1 for r in results if r["판정"] == "주의")
    fail = sum(1 for r in results if r["판정"] == "부적합")
    unk = sum(1 for r in results if r["판정"] == "미확인")
    rate = ok / total * 100 if total > 0 else 0
    overall = "✅ 적합" if fail == 0 and unk == 0 else ("⚠️ 조건부" if fail <= 2 else "❌ 부적합")
    return {
        "total": total, "ok": ok, "warn": warn, "fail": fail, "unknown": unk,
        "rate": rate, "overall": overall,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. OpenAI API 호출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_api_key():
    import streamlit as st
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key: return key
    except: pass
    key = os.environ.get("OPENAI_API_KEY", "")
    if key: return key
    return st.session_state.get("api_key", "")

def call_openai(system_prompt, user_prompt, max_tokens=2000):
    """OpenAI API 호출"""
    import requests
    api_key = get_api_key()
    if not api_key:
        return None, "API 키 미설정"
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"], None
        elif resp.status_code == 401:
            return None, "API 키가 유효하지 않습니다"
        else:
            return None, f"API 오류 ({resp.status_code})"
    except Exception as e:
        return None, str(e)


def render_api_key_input():
    import streamlit as st
    key = get_api_key()
    if not key:
        with st.sidebar:
            st.markdown("---")
            st.markdown("### 🔑 OpenAI API 키")
            input_key = st.text_input("API Key", type="password",
                                       key="api_key_input", placeholder="sk-proj-...")
            if input_key:
                st.session_state.api_key = input_key
                st.rerun()
            st.markdown("[🔗 키 발급](https://platform.openai.com/api-keys)")
    return bool(get_api_key())


def render_chatbot(page_key, page_context=""):
    """페이지 하단 챗봇"""
    import streamlit as st
    st.markdown("---")
    st.markdown("### 💬 AI 규제 전문가 챗봇")

    chat_key = f"chat_{page_key}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(f"질문하세요 ({page_key})", key=f"ci_{page_key}")
    if user_input:
        st.session_state[chat_key].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("🤖 생각 중..."):
                # 지식베이스 컨텍스트 구성
                kb_context = ""
                for doc_key in REGULATION_SCHEMA:
                    matches = search_knowledge(doc_key, user_input[:20])
                    if matches:
                        kb_context += f"\n[{REGULATION_SCHEMA[doc_key]['법령명']}]\n" + "\n".join(matches[:2])

                sys_prompt = f"""당신은 한국 식품 규제 전문가입니다.
식품등의 표시기준, 원산지 표시요령, 기구용기 규격에 대해 전문적으로 답변합니다.
항상 관련 조항(제X조)을 인용하며, 한국어로 답변하세요.

{page_context}

참조 법령 내용:
{kb_context if kb_context else '(업로드된 법령 없음)'}"""

                answer, err = call_openai(sys_prompt, user_input, 1000)
                if not answer:
                    answer = f"⚠️ {err or 'API 키를 설정하면 AI 답변을 받을 수 있습니다.'}"
            st.markdown(answer)

        st.session_state[chat_key].append({"role": "assistant", "content": answer})
