# ============================================================
#  식품안전나라 품목제조보고(I1250) — Google Colab 간단 조회
#  사용법: 셀 실행 → API 키 입력 → 식품유형 선택 → CSV 자동 저장
# ============================================================

import requests
import pandas as pd
import time
from datetime import datetime

# ── API 키 입력 ──
API_KEY = input("🔑 식품안전나라 API 키를 입력하세요: ").strip()
if not API_KEY:
    raise ValueError(
        "❌ API 키가 필요합니다!\n"
        "👉 https://www.foodsafetykorea.go.kr/api/openApiInfo.do 에서 발급하세요.\n"
        "👉 서비스: 품목제조보고(심사) [I1250] 신청"
    )
print(f"✅ API 키 설정 완료")

# ── 설정 ──
SERVICE_ID = "I1250"
BASE_URL   = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/{SERVICE_ID}/json"

# ── 식품유형 사전 (11개 대분류) ──
FOOD_TYPES = {
    "당류 및 잼류": [
        "과당","기타과당","설탕","기타설탕","포도당","올리고당","올리고당가공품",
        "물엿","기타엿","당시럽류","덱스트린","잼","기타잼","당류가공품","당절임",
    ],
    "과자.빵.초콜릿류": [
        "과자","캔디류","추잉껌","빵류","떡류","만두","만두피",
        "초콜릿","준초콜릿","화이트초콜릿","밀크초콜릿",
        "초콜릿가공품","기타 코코아가공품","코코아매스","코코아버터","코코아분말",
    ],
    "유제품 및 빙과류": [
        "우유","강화우유","저지방우유","환원유","유당분해우유",
        "가공유","유산균첨가우유","농축우유","탈지농축우유",
        "유청","유청단백분말","유크림","가공유크림",
        "버터","가공버터","버터오일","버터유","발효버터유",
        "치즈","가공치즈","모조치즈",
        "전지분유","탈지분유","가당분유","혼합분유",
        "가당연유","가공연유","가당탈지연유",
        "아이스크림","아이스크림믹스","저지방아이스크림",
        "저지방아이스크림믹스","아이스밀크","아이스밀크믹스",
        "샤베트","샤베트믹스","비유지방아이스크림","비유지방아이스크림믹스",
        "빙과","식용얼음",
    ],
    "알가공품 및 발효유": [
        "발효유","농후발효유","크림발효유","농후크림발효유","발효유분말",
        "전란액","난황액","난백액","전란분","난황분","난백분",
        "알가열제품","피단","알함유가공품",
    ],
    "식육 및 수산가공품": [
        "햄","생햄","프레스햄","혼합소시지","소시지",
        "발효소시지","베이컨류","건조저장육류",
        "양념육","갈비가공품","분쇄가공육제품",
        "식육추출가공품","식육함유가공품","포장육","식육케이싱",
        "어묵","어육소시지","어육살","연육","어육반제품",
        "조미건어포","건어포","가공김",
        "한천","기타 어육가공품","기타 건포류","기타 수산물가공품",
    ],
    "음료 및 다류": [
        "과.채주스","과.채음료","농축과.채즙",
        "탄산음료","탄산수",
        "두유","가공두유","원액두유",
        "인삼.홍삼음료","혼합음료","유산균음료",
        "음료베이스","효모음료",
        "커피","침출차","고형차","액상차",
    ],
    "식용유지": [
        "콩기름","옥수수기름","채종유","미강유",
        "참기름","추출참깨유","들기름","추출들깨유",
        "홍화유","해바라기유","올리브유","땅콩기름",
        "팜유","팜올레인유","팜스테아린유","팜핵유","야자유",
        "식용우지","식용돈지","어유",
        "기타식물성유지","기타동물성유지",
        "가공유지","식물성크림","마가린","쇼트닝","향미유",
    ],
    "조미식품 및 장류": [
        "한식간장","양조간장","혼합간장","산분해간장","효소분해간장",
        "한식된장","된장","고추장","춘장","청국장","혼합장","기타장류",
        "한식메주","개량메주",
        "발효식초","희석초산",
        "소스","토마토케첩","카레(커리)","복합조미식품",
        "마요네즈","천연향신료","향신료조제품",
        "고춧가루","실고추",
        "천일염","재제소금","정제소금","가공소금","태움.용융소금",
    ],
    "특수영양 및 의료식": [
        "영아용 조제유","영아용 조제식","성장기용 조제유","성장기용 조제식",
        "영.유아용 이유식","영.유아용 특수조제식품",
        "체중조절용 조제식품","임산.수유부용 식품",
        "일반 환자용 균형영양조제식품",
        "당뇨환자용 영양조제식품","신장질환자용 영양조제식품",
        "암환자용 영양조제식품","고혈압환자용 영양조제식품",
        "간경변환자용 영양조제식품","폐질환자용 영양조제식품",
        "선천성대사질환자용조제식품","유단백가수분해식품",
    ],
    "기타 가공식품": [
        "생면","숙면","건면","유탕면",
        "두부","가공두부","유바","묵류",
        "신선편의식품","즉석섭취식품","즉석조리식품",
        "간편조리세트","시리얼류",
        "곡류가공품","두류가공품","서류가공품",
        "전분가공품","전분",
        "땅콩 또는 견과류가공품","땅콩버터",
        "과.채가공품","절임식품","조림류",
        "김치","젓갈","조미액젓",
        "곤충가공식품",
        "벌꿀","사양벌꿀","로열젤리",
        "효모식품","효소식품",
        "생식제품","기타가공품",
    ],
    "주류": [
        "탁주","약주","청주","맥주","과실주",
        "소주","위스키","브랜디","리큐르",
        "일반증류주","주정","기타 주류",
    ],
}

# 컬럼 한글 매핑
COL_MAP = {
    "PRDLST_NM": "제품명", "PRDLST_DCNM": "식품유형", "BSSH_NM": "제조사",
    "PRMS_DT": "보고일자", "RAWMTRL_NM": "주요원재료",
    "POG_DAYCNT": "유통기한", "PRODUCTION": "생산종료",
    "INDUTY_CD_NM": "업종", "LCNS_NO": "인허가번호",
    "PRDLST_REPORT_NO": "품목제조번호", "LAST_UPDT_DTM": "최종수정일",
    "DISPOS": "제품형태", "FRMLC_MTRQLT": "포장재질",
}


# ============================================================
#  핵심 함수
# ============================================================
def fetch_food_data(food_type: str, max_count: int = 500) -> pd.DataFrame:
    """
    식품유형명으로 API 조회 → 최신순 정렬 → DataFrame 반환
    - 서버 파라미터 PRDLST_DCNM 사용 (서버 필터링)
    - 1000건씩 페이지네이션, max_count까지 수집
    """
    import urllib.parse
    encoded_type = urllib.parse.quote(food_type.strip(), safe="")
    page_size = 1000
    collected = []
    norm_type = food_type.strip().replace("·", ".").replace(" ", "").lower()

    # 1) total_count 확인
    probe_url = f"{BASE_URL}/1/1/PRDLST_DCNM={encoded_type}"
    try:
        r = requests.get(probe_url, timeout=30)
        data = r.json()
        total = int(data[SERVICE_ID].get("total_count", 0))
    except Exception as e:
        print(f"❌ API 연결 실패: {e}")
        return pd.DataFrame()

    if total == 0:
        print(f"⚠️ '{food_type}' 조회 결과 0건")
        return pd.DataFrame()

    print(f"📡 '{food_type}' 전체 {total:,}건 발견 → 최신 {min(max_count, total)}건 수집 시작")

    # 2) 페이지네이션 수집
    cursor = 1
    page = 0
    while cursor <= total and len(collected) < max_count:
        p_s = cursor
        p_e = min(cursor + page_size - 1, total)
        url = f"{BASE_URL}/{p_s}/{p_e}/PRDLST_DCNM={encoded_type}"

        try:
            r = requests.get(url, timeout=30)
            data = r.json()
        except Exception as e:
            print(f"  ⚠️ 페이지 {page+1} 실패: {e}")
            cursor += page_size
            page += 1
            time.sleep(0.3)
            continue

        if SERVICE_ID not in data:
            break

        res = data[SERVICE_ID]
        code = res.get("RESULT", {}).get("CODE", "")
        if code not in ("INFO-000",):
            break

        rows = res.get("row", [])
        for row in rows:
            # 서버 필터 검증
            row_type = row.get("PRDLST_DCNM", "").strip().replace("·", ".").replace(" ", "").lower()
            if row_type == norm_type:
                collected.append(row)

        page += 1
        print(f"  📄 {page}페이지 완료 | 수집: {len(collected)}건")

        if len(collected) >= max_count:
            break

        cursor += page_size
        time.sleep(0.2)

    if not collected:
        print("⚠️ 수집된 데이터 없음")
        return pd.DataFrame()

    # 3) DataFrame 변환 + 최신순 정렬
    df = pd.DataFrame(collected[:max_count])
    rename = {k: v for k, v in COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    if "보고일자" in df.columns:
        df["보고일자"] = df["보고일자"].astype(str)
        df["보고일자_dt"] = pd.to_datetime(df["보고일자"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("보고일자_dt", ascending=False).reset_index(drop=True)

    print(f"✅ 완료: {len(df)}건 수집 (전체 DB {total:,}건)")
    return df


def show_menu():
    """대분류 → 소분류 선택 메뉴"""
    categories = list(FOOD_TYPES.keys())
    print("\n" + "="*50)
    print("  식품안전나라 품목제조보고 조회 (Colab)")
    print("="*50)

    print("\n📁 대분류 선택:")
    for i, cat in enumerate(categories, 1):
        print(f"  {i:2d}. {cat} ({len(FOOD_TYPES[cat])}개 유형)")

    cat_idx = int(input("\n번호 입력: ")) - 1
    category = categories[cat_idx]

    types = FOOD_TYPES[category]
    print(f"\n📋 [{category}] 식품유형 선택:")
    for i, t in enumerate(types, 1):
        print(f"  {i:2d}. {t}")

    type_idx = int(input("\n번호 입력: ")) - 1
    food_type = types[type_idx]

    max_count = int(input("\n조회 건수 (최대 500, 기본 100): ") or "100")
    max_count = min(max(max_count, 10), 500)

    return food_type, max_count


# ============================================================
#  실행
# ============================================================
food_type, max_count = show_menu()

print(f"\n{'─'*50}")
df = fetch_food_data(food_type, max_count)

if df.empty:
    print("데이터 없음. 종료.")
else:
    # 주요 컬럼만 표시
    show_cols = [c for c in ["제품명","식품유형","제조사","보고일자","주요원재료","유통기한","생산종료"]
                 if c in df.columns]
    print(f"\n📊 미리보기 (상위 10건):")
    print(df[show_cols].head(10).to_string(index=False))

    # CSV 저장
    filename = f"{food_type}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"\n💾 CSV 저장 완료: {filename}")
    print(f"   → {len(df)}건, 컬럼 {len(df.columns)}개")

    # Colab에서 다운로드
    try:
        from google.colab import files
        files.download(filename)
        print("📥 다운로드 시작됨")
    except ImportError:
        print(f"(로컬 환경: {filename} 파일 확인)")
