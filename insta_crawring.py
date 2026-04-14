import streamlit as st
import pandas as pd
import instaloader
import time

st.set_page_config(page_title="AI NPD SUITE - Trend Scraper", layout="wide")

# ─────────────────────────────────────────
# Instagram 해시태그 크롤러 (instaloader 기반)
# ─────────────────────────────────────────

@st.cache_resource
def get_loader(username: str = "", password: str = ""):
    """Instaloader 인스턴스 생성 (세션 캐싱)"""
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
    )
    if username and password:
        try:
            L.login(username, password)
            st.session_state["logged_in"] = True
        except instaloader.exceptions.BadCredentialsException:
            st.session_state["logged_in"] = False
            st.error("❌ 로그인 실패: ID/PW를 확인해주세요.")
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            st.session_state["logged_in"] = False
            st.error("❌ 2단계 인증 계정은 사용 불가합니다.")
    return L


def scrape_hashtag(keyword: str, count: int, loader: instaloader.Instaloader):
    """
    해시태그 포스트 수집
    - 비로그인: 최근 50~100개 내에서 수집 가능 (Instagram 제한)
    - 로그인: 더 많은 포스트 접근 가능
    """
    results = []
    keyword_clean = keyword.lstrip("#").replace(" ", "").lower()

    try:
        hashtag = instaloader.Hashtag.from_name(loader.context, keyword_clean)
        posts = hashtag.get_posts()

        progress = st.progress(0, text=f"'{keyword_clean}' 포스트 수집 중...")

        for i, post in enumerate(posts):
            if i >= count:
                break

            results.append({
                "번호": i + 1,
                "날짜": post.date_local.strftime("%Y-%m-%d"),
                "좋아요": post.likes,
                "댓글수": post.comments,
                "본문(일부)": (post.caption[:100] + "...") if post.caption else "(캡션 없음)",
                "해시태그": ", ".join(list(post.caption_hashtags)[:8]) if post.caption_hashtags else "",
                "게시물 URL": f"https://www.instagram.com/p/{post.shortcode}/",
            })

            progress.progress((i + 1) / count, text=f"{i+1}/{count} 수집 완료")
            time.sleep(0.8)  # ← Rate limit 방지 (너무 빠르면 차단됨)

        progress.empty()

    except instaloader.exceptions.QueryReturnedNotFoundException:
        st.error(f"❌ 해시태그 `#{keyword_clean}` 를 찾을 수 없습니다.")
    except instaloader.exceptions.ConnectionException as e:
        st.error(f"❌ Instagram 연결 오류 (Rate limit 가능성): {e}")
    except Exception as e:
        st.error(f"❌ 예상치 못한 오류: {e}")

    return pd.DataFrame(results)


# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────

st.title("🍹 AI NPD SUITE — Instagram 트렌드 분석")
st.caption("인스타그램 해시태그 기반 음료 트렌드 수집기 (instaloader)")

with st.sidebar:
    st.subheader("⚙️ 설정")

    st.markdown("**🔐 Instagram 계정 (선택)**")
    st.caption("로그인하면 더 많은 데이터 수집 가능. 빈칸이면 비로그인 모드.")
    ig_user = st.text_input("Instagram ID", value="", placeholder="선택사항")
    ig_pw   = st.text_input("Instagram PW", value="", type="password", placeholder="선택사항")

    st.divider()

    st.markdown("**🔍 수집 조건**")
    target = st.text_input("분석 키워드 (해시태그)", value="저당음료")
    limit  = st.slider("수집 개수", min_value=5, max_value=50, value=15, step=5)
    st.caption("⚠️ 50개 초과 수집 시 Rate limit 위험")

    btn = st.button("🚀 분석 시작", use_container_width=True, type="primary")

# ─────────────────────────────────────────
# 실행
# ─────────────────────────────────────────

if btn:
    loader = get_loader(ig_user, ig_pw)

    with st.spinner("Instagram 접속 중..."):
        df = scrape_hashtag(target, limit, loader)

    if df is not None and not df.empty:
        st.success(f"✅ **{len(df)}개** 포스트 수집 완료")

        # 요약 지표
        col1, col2, col3 = st.columns(3)
        col1.metric("총 수집", f"{len(df)}개")
        col2.metric("평균 좋아요", f"{df['좋아요'].mean():.0f}")
        col3.metric("평균 댓글", f"{df['댓글수'].mean():.0f}")

        st.divider()

        # 해시태그 빈도 분석
        all_tags = []
        for tags in df["해시태그"].dropna():
            all_tags.extend([t.strip() for t in tags.split(",") if t.strip()])

        if all_tags:
            from collections import Counter
            tag_counts = Counter(all_tags).most_common(15)
            tag_df = pd.DataFrame(tag_counts, columns=["해시태그", "빈도"])

            st.subheader("📊 연관 해시태그 TOP 15")
            st.bar_chart(tag_df.set_index("해시태그"))

        st.subheader("📋 수집 데이터")
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "게시물 URL": st.column_config.LinkColumn("링크"),
                "좋아요": st.column_config.NumberColumn(format="%d ❤️"),
            }
        )

        # CSV 다운로드
        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ CSV 다운로드",
            data=csv,
            file_name=f"insta_{target}_{limit}posts.csv",
            mime="text/csv",
        )
    else:
        st.warning("데이터를 가져오지 못했습니다. 키워드를 확인하거나 잠시 후 재시도해주세요.")
