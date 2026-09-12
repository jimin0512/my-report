# -*- coding: utf-8 -*-
"""제안서 — 독립 페이지.

데이터 흐름은 정확히 다음 순서로만 간다(화면에서 별도 계산·재필터링 없음):

    load.load_all() → M.proposal_topics(t) → (사용자가 topic 선택)
    → M.topic_evidence(t, topic) → P.load_cards() → P.build(topic, evidence, cards, human)

거르는 책임(표본 미달·관측기간 등으로 후보 자체를 안 만드는 것)은
core/metrics.py의 proposal_topics()/topic_evidence()에만 있다 — 이 화면은
그 결과를 읽어 보여주기만 한다.
"""
import streamlit as st

from core import config as C, metrics as M, load
from report import proposal as P
from viz import ui

_WORDS = C.PROPOSAL_WORDS

st.set_page_config(page_title="제안서", page_icon="🧭", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("proposal")

if "run" not in st.session_state:
    st.session_state.run = None
if "proposal_human_new" not in st.session_state:
    st.session_state.proposal_human_new = {}

ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '제안서</div>', unsafe_allow_html=True)
st.caption("core.metrics.proposal_topics()·topic_evidence()와 report.proposal.build()를 "
           "그대로 호출한 결과만 보여줍니다 — 이 화면에서 새로 계산하거나 후보를 "
           "다시 거르지 않습니다.")

topics = M.proposal_topics(t)


def _topic_label(tp: dict) -> str:
    """규모_연간건수/기각사유는 있는 그대로 라벨에만 반영한다(새 판단 없음)."""
    제목 = tp.get("제목") or tp.get("키", "(제목 없음)")
    규모 = tp.get("규모_연간건수")
    size_txt = f"연 {규모:,.1f}건" if 규모 is not None else _WORDS["status_terms"]["규모 산정 불가"]
    label = f"{제목} · {size_txt}"
    if tp.get("기각사유"):
        label += " (차이 없음)"
    return label


options = [("전체", None)] + [(_topic_label(tp), tp) for tp in topics]
labels = [o[0] for o in options]
label_to_topic = dict(options)

picked_label = st.selectbox("주제 선택", labels, label_visibility="collapsed")
picked_topic = label_to_topic[picked_label]

st.divider()

if picked_topic is None:
    # ── 전체 ─────────────────────────────────────────────────────
    # proposal_topics(t)의 결과를 읽기 전용으로만 보여준다 — 특정 topic의
    # build()를 강제로 만들지 않는다.
    ui.section("전체 후보", "proposal_topics(t) 결과 그대로")
    if not topics:
        st.caption("현재 신뢰 가능한 후보가 없습니다.")
    for tp in topics:
        규모 = tp.get("규모_연간건수")
        규모_txt = (f"연 {규모:,.1f}건" if 규모 is not None
                   else _WORDS["status_terms"]["규모 산정 불가"])
        기각 = tp.get("기각사유")
        st.markdown(
            f'<div class="card tight" style="margin-bottom:10px">'
            f'<div style="font-weight:700;font-size:15px">{tp.get("제목", tp.get("키"))}</div>'
            f'<div style="font-size:13px;color:#475569;margin:6px 0">{tp.get("한줄", "")}</div>'
            f'<div style="font-size:12.5px;color:#64748b">규모: {규모_txt}'
            + (f' · {_WORDS["status_terms"]["기각사유"]}: {기각}' if 기각 else '')
            + '</div></div>', unsafe_allow_html=True)

else:
    # ── 특정 topic ───────────────────────────────────────────────
    evidence = M.topic_evidence(t, picked_topic)
    cards = P.load_cards()

    # A. 근거 요약 — topic에 실제 있는 값만(없는 키는 건너뜀)
    ui.section("근거 요약")
    규모 = picked_topic.get("규모_연간건수")
    tc = picked_topic.get("신뢰판정") or {}
    summary_bits = []
    if picked_topic.get("한줄"):
        summary_bits.append(picked_topic["한줄"])
    summary_bits.append(
        f"규모: {'연 ' + format(규모, ',.1f') + '건' if 규모 is not None else _WORDS['status_terms']['규모 산정 불가']}")
    if tc.get("reason"):
        summary_bits.append(f"{_WORDS['status_terms']['신뢰 가능']}: {tc['reason']}")
    if picked_topic.get("기각사유"):
        summary_bits.append(f"{_WORDS['status_terms']['기각사유']}: {picked_topic['기각사유']}")
    if picked_topic.get("관측기간_주의"):
        summary_bits.append(f"{_WORDS['status_terms']['관측기간 주의']}: {picked_topic['관측기간_주의']}")
    st.markdown(
        '<div class="card tight">' +
        "<br>".join(summary_bits) +
        '</div>', unsafe_allow_html=True)

    # B. 절별 미리보기 — build() 결과 순서 그대로
    secs = P.build(picked_topic, evidence, cards, st.session_state.proposal_human_new)

    st.divider()
    ui.section("절별 미리보기", "build() 결과를 순서 그대로 표시")

    for s in secs:
        kind_txt = _WORDS["kind"].get(s["kind"], s["kind"])
        lvl = "ok" if s["kind"] == "auto" else ("ok" if (s.get("문장") or "").strip() else "warn")
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin-top:22px">'
            f'<div style="font-size:17px;font-weight:700">{s["제목"]}</div>'
            f'{ui.badge(lvl, kind_txt)}</div>'
            f'<div style="font-size:12px;color:#94a3b8;margin-bottom:8px">{s.get("질문", "")}</div>',
            unsafe_allow_html=True)

        if s["kind"] == "auto":
            # auto 절 — 읽기 전용. text_area·수정 버튼 없음.
            문장 = s.get("문장") or ""
            if 문장:
                st.markdown(
                    f'<div class="card"><div style="white-space:pre-line;'
                    f'font-size:14px;line-height:1.7">{문장}</div></div>',
                    unsafe_allow_html=True)
            if s.get("차트"):
                st.markdown(s["차트"], unsafe_allow_html=True)
            if s.get("표") is not None:
                with st.expander("표 보기"):
                    st.json(s["표"])
        else:
            key = f"prop2_{s['키']}"
            is_request = s["키"] == "request"

            if is_request:
                # 결정 요청 절의 자동 영역(A) — 규모/보류 시 규모/선택지/확인 필요는
                # build()가 이미 만들어 둔 값을 그대로 읽기 전용으로만 보여준다.
                규모정보 = s.get("규모정보") or {}
                연간 = 규모정보.get("연간환산")
                if 연간 is not None:
                    st.markdown(f"규모: 연 {연간:,.1f}건(환산값)")
                else:
                    label = _WORDS["status_terms"]["규모 산정 불가"]
                    사유 = 규모정보.get("계산불가사유")
                    st.markdown(f"규모: {label}" + (f" — {사유}" if 사유 else ""))
                if s.get("보류시규모"):
                    st.caption(s["보류시규모"])
                options = s.get("결정선택지") or []
                if options:
                    st.markdown("**결정 선택지**")
                    for o in options:
                        st.markdown(f"- **{o['선택지']}**: {o['의미']}")
                pending = s.get("확인필요") or []
                if pending:
                    with st.expander(f"확인 필요 항목 ({len(pending)}건)"):
                        for p in pending:
                            st.markdown(f"- {p['무엇']} · {p['확인방법']} · {p['확인전결정']}")
                placeholder = ("승인·결정·판단 중 하나의 결정 동사를 포함해, "
                               "무엇을 결정해 달라는 것인지 작성하십시오.")
            else:
                placeholder = s["질문"]

            txt = st.text_area(
                s["제목"], value=st.session_state.proposal_human_new.get(s["제목"], ""),
                height=180, key=key, label_visibility="collapsed",
                placeholder=placeholder)

            if is_request and txt.strip() and not P.has_decision_verb(txt):
                st.warning("결정 요청 문장에 승인·결정·판단 중 하나의 결정 동사를 포함해 주세요.")

            if st.button("저장", key=f"save_{key}"):
                st.session_state.proposal_human_new[s["제목"]] = txt
                st.rerun()

    st.divider()
    ui.section("내보내기")

    # HTML — report.proposal.to_html()이 새 6절 구조를 실제로 처리할 수
    # 있는지 먼저 호출해 확인한 뒤에만 다운로드 버튼을 연결한다.
    try:
        proposal_html = P.to_html(secs)
        st.download_button(
            "제안서 HTML 내려받기",
            proposal_html,
            file_name="제안서.html",
            mime="text/html",
            key="dl_proposal_html_new")
    except Exception as e:
        st.error(f"HTML 생성 중 오류: {type(e).__name__}: {e}")

    # PDF — report.proposal.build_pdf()가 새 6절 구조를 실제로 처리할 수 있는지
    # 먼저 호출해 확인한 뒤에만 다운로드 버튼을 연결한다(HTML과 같은 패턴).
    try:
        proposal_pdf = P.build_pdf(secs)
        st.download_button(
            "제안서 PDF 내려받기",
            proposal_pdf,
            file_name="제안서.pdf",
            mime="application/pdf",
            key="dl_proposal_pdf_new")
    except Exception as e:
        st.error(f"PDF 생성 중 오류: {type(e).__name__}: {e}")
