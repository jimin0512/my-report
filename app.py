# -*- coding: utf-8 -*-
"""성장 리포트 — 진입 화면.

실행 · 대시보드 · 리포트 · 아카이브 4개 화면으로 나뉜다.
성격이 다른 것을 한 화면에 넣지 않는다는 것이 이 앱의 구조 원칙이다.
"""
import streamlit as st

from core import config as C, gates, load
from viz import ui

st.set_page_config(page_title="성장 리포트", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("home")

if "run" not in st.session_state:
    st.session_state.run = None

ui.context_bar(st.session_state.run)

st.markdown(
    '<div style="font-size:26px;font-weight:800;margin-bottom:2px">'
    '성장 퍼널 분석과 자동 리포트</div>'
    '<div style="color:#64748b;font-size:14px;margin-bottom:22px">'
    '데이터를 넣으면 검증 · 계산 · 대시보드 · 리포트까지 이어집니다. '
    '사람은 게이트 세 곳에서만 판단합니다.</div>',
    unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
cards = [
    ("▶️ 실행", "새 데이터를 넣고 8단계를 돌립니다.", "pages/1_실행.py", "한 번 쓰고 끝"),
    ("📊 대시보드", "퍼널 · 실험 · 채널 효율을 봅니다.", "pages/2_대시보드.py", "반복해서 봄"),
    ("📄 리포트", "8장 문서와 PDF를 만듭니다.", "pages/3_리포트.py", "만들어 공유"),
    ("🗂️ 아카이브", "지난 실행을 찾고 비교합니다.", "pages/4_아카이브.py", "가끔"),
]
for col, (t, d, p, when) in zip([c1, c2, c3, c4], cards):
    with col:
        st.markdown(
            f'<div class="card tight" style="min-height:132px">'
            f'<div style="font-size:15px;font-weight:700">{t}</div>'
            f'<div style="font-size:12.5px;color:#64748b;margin:8px 0 10px;'
            f'line-height:1.5">{d}</div>'
            f'<div style="font-size:11px;color:#94a3b8">{when}</div></div>',
            unsafe_allow_html=True)
        st.page_link(p, label="열기 →")

ui.section("이 앱이 하지 않는 것")
st.markdown("""
- **지표를 스스로 정의하지 않습니다.** 정의는 위키가 원본이고 앱은 읽어 쓸 뿐입니다.
- **게이트를 대신 통과시키지 않습니다.** 판단할 재료만 놓고 결정은 사람이 합니다.
- **원본 데이터를 고치지 않습니다.** 읽기만 합니다.
- **메일을 실제로 보내지 않습니다.** 초안까지만 만듭니다.
""")

with st.expander("데이터 상태 확인", expanded=True):
    t = ui.guard(load.load_all)
    if t is not None:
        st.success(f"{len(t)}개 테이블 적재 완료 · 메모리 {load.memory_mb(t):.0f}MB "
                   f"(Streamlit 무료 한도 1,024MB)")
        st.dataframe(
            __import__("core.validate", fromlist=["profile"]).profile(t),
            width="stretch", hide_index=True)
