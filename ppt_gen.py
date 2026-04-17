"""
PPT 생성 모듈 — BCG/Deloitte 컨설팅 스타일
배경: #1E3A5F (네이비), 강조: #00B4D8 (시안), 텍스트: #FFFFFF
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import io, datetime

# ── 컬러 상수
NAVY   = RGBColor(0x1E, 0x3A, 0x5F)
CYAN   = RGBColor(0x00, 0xB4, 0xD8)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
LGRAY  = RGBColor(0xB0, 0xC4, 0xD8)
DGRAY  = RGBColor(0x0F, 0x1F, 0x35)
CYAN2  = RGBColor(0x00, 0x8B, 0xAA)

W = Inches(13.33)   # 와이드 슬라이드 너비
H = Inches(7.5)     # 높이

def _prs():
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H
    return prs

def _bg(slide, color=NAVY):
    """슬라이드 배경색 설정"""
    from pptx.oxml.ns import qn
    from lxml import etree
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def _box(slide, x, y, w, h, text, size=14, bold=False, color=WHITE,
         align=PP_ALIGN.LEFT, bg=None, alpha=None):
    """텍스트 박스 추가"""
    txBox = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"
    if bg:
        fill = txBox.fill
        fill.solid()
        fill.fore_color.rgb = bg
    return txBox

def _rect(slide, x, y, w, h, color, alpha_str=None):
    """색상 사각형 추가"""
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape

def _line(slide, x1, y1, x2, y2, color=CYAN, width_pt=2):
    """라인 추가"""
    from pptx.util import Pt as Pt2
    connector = slide.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    connector.line.color.rgb = color
    connector.line.width = Pt2(width_pt)

def _header_bar(slide, title, subtitle=""):
    """공통 헤더 바 (좌측 시안 라인 + 타이틀)"""
    _rect(slide, 0, 0, 13.33, 1.1, DGRAY)
    _rect(slide, 0, 0, 0.08, 1.1, CYAN)
    _box(slide, 0.2, 0.12, 9, 0.55, title, size=26, bold=True, color=WHITE)
    if subtitle:
        _box(slide, 0.2, 0.65, 9, 0.38, subtitle, size=13, color=LGRAY)
    # 우측 날짜
    today = datetime.date.today().strftime("%Y.%m.%d")
    _box(slide, 10.5, 0.35, 2.5, 0.4, today, size=11, color=LGRAY, align=PP_ALIGN.RIGHT)

def _footer(slide, text="AI NPD SUITE — 네이버 음료 트렌드 분석"):
    _rect(slide, 0, 7.1, 13.33, 0.4, DGRAY)
    _line(slide, 0, 7.1, 13.33, 7.1, CYAN, 1)
    _box(slide, 0.3, 7.12, 8, 0.3, text, size=9, color=LGRAY)
    _box(slide, 10, 7.12, 3, 0.3, "CONFIDENTIAL", size=9, color=LGRAY, align=PP_ALIGN.RIGHT)

def slide_title(prs, keywords, total_blog, total_shop, date_range):
    """슬라이드 1 — 타이틀"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, NAVY)

    # 배경 장식 사각형
    _rect(slide, 0, 0, 0.5, 7.5, DGRAY)
    _rect(slide, 0.5, 5.5, 12.83, 2.0, DGRAY)
    _rect(slide, 0.5, 5.48, 12.83, 0.06, CYAN)

    # 메인 타이틀
    _box(slide, 1.2, 1.5, 11, 0.8,
         "🍹  AI NPD SUITE", size=20, color=CYAN, bold=True)
    _box(slide, 1.2, 2.2, 11, 1.2,
         "네이버 음료 트렌드 분석 리포트", size=38, bold=True, color=WHITE)
    _box(slide, 1.2, 3.4, 11, 0.5,
         f"분석 키워드: {keywords}", size=15, color=LGRAY)
    _box(slide, 1.2, 3.9, 11, 0.5,
         f"분석 기간: {date_range}", size=15, color=LGRAY)

    # 하단 메트릭 3개
    for i, (label, val) in enumerate([
        ("블로그 수집", f"{total_blog:,}건"),
        ("쇼핑 수집",   f"{total_shop:,}개"),
        ("분석 일자",   datetime.date.today().strftime("%Y년 %m월 %d일")),
    ]):
        x = 1.2 + i * 4.0
        _rect(slide, x, 5.7, 3.5, 1.2, DGRAY)
        _rect(slide, x, 5.7, 3.5, 0.06, CYAN)
        _box(slide, x+0.15, 5.8, 3.2, 0.4, label, size=11, color=LGRAY)
        _box(slide, x+0.15, 6.15, 3.2, 0.55, val, size=22, bold=True, color=WHITE)

def slide_blog_score(prs, score_data):
    """슬라이드 2 — 블로그 관련성 점수"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, NAVY)
    _header_bar(slide, "블로그 트렌드 — 관련성 점수 분석",
                "음료 관련 블로그 게시글 필터링 및 키워드별 품질 평가")

    # 좌측: 점수 바차트 (텍스트 기반)
    _box(slide, 0.3, 1.3, 6, 0.4, "키워드별 평균 관련성 점수", size=13, bold=True, color=CYAN)
    max_score = max(v for _, v, _ in score_data) if score_data else 100
    for i, (kw, score, cnt) in enumerate(score_data[:8]):
        y = 1.75 + i * 0.58
        bar_w = (score / max(max_score, 1)) * 5.5
        _rect(slide, 0.3,   y+0.12, 5.8, 0.32, DGRAY)
        _rect(slide, 0.3,   y+0.12, max(bar_w, 0.05), 0.32, CYAN2)
        _box(slide,  0.35,  y, 3.5, 0.28, kw, size=11, color=WHITE)
        _box(slide,  4.5,   y, 1.5, 0.28, f"{score:.1f}점 ({cnt}건)",
             size=11, color=CYAN, align=PP_ALIGN.RIGHT)

    # 우측: 콘텐츠 유형 설명 카드
    _box(slide, 7.0, 1.3, 5.8, 0.4, "콘텐츠 유형 가이드", size=13, bold=True, color=CYAN)
    types = [
        ("🆕 신제품/출시",  "+30점", "브랜드 신제품 관련 글"),
        ("☕ 카페메뉴",     "+25점", "카페 시그니처 음료 소개"),
        ("📈 소비트렌드",   "+20점", "인기·핫·트렌드 언급"),
        ("💬 구매후기",     "+20점", "실구매 경험 공유"),
        ("🔬 성분분석",     "+15점", "칼로리·성분·영양 정보"),
        ("🛒 구매채널",     "+15점", "편의점·마트·쿠팡 등"),
    ]
    for i, (typ, pt, desc) in enumerate(types):
        y = 1.75 + i * 0.73
        _rect(slide, 7.0, y, 6.0, 0.62, DGRAY)
        _rect(slide, 7.0, y, 0.06, 0.62, CYAN)
        _box(slide, 7.15, y+0.04, 3.2, 0.28, typ,  size=12, bold=True, color=WHITE)
        _box(slide, 7.15, y+0.30, 3.2, 0.25, desc, size=10, color=LGRAY)
        _box(slide, 10.2, y+0.12, 1.6, 0.35, pt,   size=14, bold=True,
             color=CYAN, align=PP_ALIGN.RIGHT)

    _footer(slide)

def slide_top_posts(prs, top_posts):
    """슬라이드 3 — TOP 블로그 게시글"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, NAVY)
    _header_bar(slide, "블로그 TOP 10 — 고관련성 게시글",
                "관련성 점수 기준 상위 10개 음료 관련 게시글")

    headers = ["순위","점수","유형","키워드","제목"]
    col_x   = [0.2, 1.1, 2.0, 3.4, 5.1]
    col_w   = [0.8, 0.8, 1.3, 1.6, 7.8]

    # 헤더 행
    _rect(slide, 0.2, 1.2, 12.9, 0.42, DGRAY)
    _rect(slide, 0.2, 1.2, 12.9, 0.05, CYAN)
    for j, h in enumerate(headers):
        _box(slide, col_x[j]+0.05, 1.23, col_w[j], 0.35,
             h, size=11, bold=True, color=CYAN)

    # 데이터 행
    medals = ["🥇","🥈","🥉","④","⑤","⑥","⑦","⑧","⑨","⑩"]
    for i, row in enumerate(top_posts[:10]):
        y = 1.65 + i * 0.49
        bg_c = RGBColor(0x12, 0x25, 0x40) if i % 2 == 0 else DGRAY
        _rect(slide, 0.2, y, 12.9, 0.47, bg_c)
        vals = [
            medals[i] if i < len(medals) else str(i+1),
            f"{row.get('관련성점수',0):.0f}",
            str(row.get('콘텐츠유형',''))[:8],
            str(row.get('키워드',''))[:10],
            str(row.get('제목',''))[:45],
        ]
        for j, val in enumerate(vals):
            col = CYAN if j == 1 else WHITE
            _box(slide, col_x[j]+0.05, y+0.06, col_w[j]-0.1, 0.36,
                 val, size=10, color=col)
    _footer(slide)

def slide_shop_overview(prs, type_data, price_data):
    """슬라이드 4 — 쇼핑 트렌드 개요"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, NAVY)
    _header_bar(slide, "쇼핑 트렌드 — 상품 유형 & 가격 분석",
                "RTD음료 중심 가격 구조 및 시장 분포")

    # 좌측: 상품유형 분포
    _box(slide, 0.3, 1.3, 5.8, 0.4, "상품 유형 분포", size=13, bold=True, color=CYAN)
    total = sum(v for _, v in type_data) if type_data else 1
    for i, (typ, cnt) in enumerate(type_data[:5]):
        y = 1.78 + i * 0.9
        pct = cnt / total * 100
        bar_w = pct / 100 * 5.5
        _rect(slide, 0.3, y+0.32, 5.5, 0.3, DGRAY)
        _rect(slide, 0.3, y+0.32, max(bar_w,0.05), 0.3, CYAN2)
        _box(slide, 0.3, y+0.02, 4.0, 0.28, typ, size=12, bold=True, color=WHITE)
        _box(slide, 4.8, y+0.02, 1.2, 0.28,
             f"{pct:.0f}%", size=14, bold=True, color=CYAN, align=PP_ALIGN.RIGHT)
        _box(slide, 0.3, y+0.65, 4.0, 0.22,
             f"{cnt}개", size=10, color=LGRAY)

    # 우측: 가격 분석 테이블
    _box(slide, 7.0, 1.3, 5.8, 0.4, "키워드별 가격 분석 (RTD 기준)", size=13, bold=True, color=CYAN)
    _rect(slide, 7.0, 1.75, 6.0, 0.4, DGRAY)
    _rect(slide, 7.0, 1.75, 6.0, 0.05, CYAN)
    for j, h in enumerate(["키워드","평균 개당","100ml당"]):
        _box(slide, 7.05 + j*2.0, 1.78, 1.9, 0.32,
             h, size=10, bold=True, color=CYAN)
    for i, (kw, unit_p, ml_p) in enumerate(price_data[:7]):
        y = 2.18 + i * 0.58
        bg_c = RGBColor(0x12,0x25,0x40) if i%2==0 else DGRAY
        _rect(slide, 7.0, y, 6.0, 0.55, bg_c)
        _box(slide, 7.05, y+0.1, 1.9, 0.35, str(kw)[:10], size=11, color=WHITE)
        _box(slide, 9.05, y+0.1, 1.9, 0.35,
             f"{unit_p:,.0f}원" if unit_p else "-", size=11, color=CYAN)
        _box(slide, 11.05, y+0.1, 1.9, 0.35,
             f"{ml_p:,.0f}원" if ml_p else "-", size=11, color=WHITE)

    _footer(slide)

def slide_npd_ideas(prs, ideas):
    """슬라이드 5 — NPD 아이디어"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, NAVY)
    _header_bar(slide, "NPD 인사이트 — 신제품 아이디어 제언",
                "블로그·쇼핑 데이터 기반 Claude AI 분석 결과")

    card_colors = [CYAN2, RGBColor(0x00,0x7A,0x8A), RGBColor(0x00,0x5F,0x6E)]
    for i, idea in enumerate(ideas[:3]):
        x = 0.4 + i * 4.3
        # 카드 배경
        _rect(slide, x, 1.3, 4.0, 5.5, DGRAY)
        _rect(slide, x, 1.3, 4.0, 0.08, card_colors[i % 3])

        # 번호 뱃지
        _rect(slide, x+0.15, 1.45, 0.45, 0.45, card_colors[i % 3])
        _box(slide, x+0.15, 1.45, 0.45, 0.45,
             str(i+1), size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

        _box(slide, x+0.7, 1.48, 3.1, 0.45,
             str(idea.get('idea',''))[:20], size=14, bold=True, color=WHITE)
        _line(slide, x+0.15, 2.05, x+3.85, 2.05, LGRAY, 0.5)

        labels = [
            ("🍹 플레이버", idea.get('flavor','-')),
            ("🏷️ 컨셉",    idea.get('concept','-')),
            ("💰 가격대",   idea.get('price_range','-')),
        ]
        for j, (lbl, val) in enumerate(labels):
            y = 2.2 + j * 0.75
            _box(slide, x+0.15, y,      3.7, 0.3, lbl, size=10, color=LGRAY)
            _box(slide, x+0.15, y+0.28, 3.7, 0.38, str(val)[:18],
                 size=13, bold=True, color=CYAN)

        _line(slide, x+0.15, 4.6, x+3.85, 4.6, LGRAY, 0.5)
        _box(slide, x+0.15, 4.68, 3.7, 0.3,
             "근거", size=10, color=LGRAY)
        _box(slide, x+0.15, 4.95, 3.7, 1.5,
             str(idea.get('reason',''))[:80], size=11, color=WHITE)

    _footer(slide)

def slide_closing(prs):
    """슬라이드 6 — 마무리"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, NAVY)
    _rect(slide, 0, 0, 0.5, 7.5, DGRAY)
    _rect(slide, 0.5, 3.2, 12.83, 0.06, CYAN)
    _box(slide, 1.5, 2.2, 10, 0.8, "AI NPD SUITE", size=18, color=CYAN, bold=True)
    _box(slide, 1.5, 2.9, 10, 1.0,
         "데이터 기반 음료 트렌드 분석 완료", size=34, bold=True, color=WHITE)
    _box(slide, 1.5, 3.9, 10, 0.5,
         "Powered by Naver API · Google Gemini · Anthropic Claude",
         size=13, color=LGRAY)
    today = datetime.date.today().strftime("%Y년 %m월 %d일")
    _box(slide, 1.5, 4.4, 10, 0.4, today, size=13, color=LGRAY)
    _footer(slide)


def build_ppt(blog_df, shop_df, claude_result=None):
    """
    전체 PPT 빌드 → bytes 반환
    """
    import pandas as pd
    prs = _prs()

    # ── 슬라이드 1: 타이틀
    keywords = ", ".join(blog_df["키워드"].unique()[:5]) if not blog_df.empty else "-"
    today = datetime.date.today()
    six_ago = today.replace(month=today.month-6 if today.month > 6 else today.month+6,
                            year=today.year if today.month > 6 else today.year-1)
    date_range = f"{six_ago.strftime('%Y.%m')} ~ {today.strftime('%Y.%m')}"
    slide_title(prs, keywords, len(blog_df), len(shop_df), date_range)

    # ── 슬라이드 2: 블로그 점수
    if not blog_df.empty:
        score_data = blog_df.groupby("키워드")["관련성점수"].agg(
            score="mean", cnt="count"
        ).reset_index().sort_values("score", ascending=False)
        score_list = [(r["키워드"], r["score"], int(r["cnt"]))
                      for _, r in score_data.iterrows()]
        slide_blog_score(prs, score_list)

        # ── 슬라이드 3: TOP 게시글
        top = blog_df.nlargest(10, "관련성점수")[
            ["관련성점수","콘텐츠유형","키워드","제목"]
        ].to_dict("records")
        slide_top_posts(prs, top)

    # ── 슬라이드 4: 쇼핑
    if not shop_df.empty:
        type_data = [(r["상품유형"], r["수"])
                     for _, r in shop_df["상품유형"].value_counts().reset_index()
                     .rename(columns={"count":"수"}).iterrows()]
        rtd = shop_df[shop_df["상품유형"]=="RTD음료"]
        price_data = []
        for kw in shop_df["키워드"].unique():
            sub = rtd[rtd["키워드"]==kw]
            u = sub["개당가격(원)"].mean() if not sub.empty else None
            m = sub["100ml당가격(원)"].dropna()
            m = m.mean() if not m.empty else None
            price_data.append((kw, u, m))
        slide_shop_overview(prs, type_data, price_data)

    # ── 슬라이드 5: NPD 아이디어
    if claude_result and "npd_ideas" in claude_result:
        slide_npd_ideas(prs, claude_result["npd_ideas"])

    # ── 슬라이드 6: 마무리
    slide_closing(prs)

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()
