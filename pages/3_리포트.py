# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
import streamlit as st

from core import config as C, gates, load, metrics as M, validate as V
from report import archive, sections as S, to_pdf
from viz import pdf_charts, ui

st.set_page_config(page_title="리포트", page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("report")

if "run" not in st.session_state:
    st.session_state.run = None
if "human" not in st.session_state:
    st.session_state.human = {}

# 이 세션에 활성 run이 없으면(예: 리포트 페이지를 별도 세션/탭에서 열었거나
# 서버가 재시작돼 세션이 새로 시작된 경우) runs/에 이미 저장된 최신 run을
# 읽어온다. 세션에 이미 run이 있으면 그것을 그대로 쓴다 — 진행 중인 다른
# run을 덮어쓰지 않는다. 게이트 1·2 기록은 여기서 새로 만들거나 고치지
# 않고, 디스크에 있는 것을 읽기만 한다.
if st.session_state.run is None:
    _saved_runs = gates.load_all()
    if _saved_runs:
        st.session_state.run = _saved_runs[0]

ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()
secs = S.build(t, st.session_state.human)

# 리포트 차트에 쓸 분해 축 — pages/2_대시보드.py와 동일하게 process_name을 쓴다.
DIM = "process_name"


def _process_compare(t: dict, f, bi: int):
    """funnel_by()의 process별 결과를, 병목 구간(step_from→step_to)의
    도달/전환/전환율 표로 재구성한다. 새 계산이 아니라 이미 구현된
    M.funnel_by()의 결과를 차트용으로 pivot만 한다
    (pages/2_대시보드.py의 process별 비교와 동일한 방식).

    표본이 최소 기준(config.MIN_SAMPLE) 미만인 프로세스는 전환율을
    나누지 않는다 — 판정이 계산보다 먼저다. 표본 기준을 충족하는
    프로세스가 2개 미만이면(비교 자체가 성립하지 않으면) None을 돌려준다.
    """
    step_from, step_to = f.step.iloc[bi - 1], f.step.iloc[bi]
    g_long = M.funnel_by(t, DIM)
    piv = (g_long[g_long.step.isin([step_from, step_to])]
           .pivot(index=DIM, columns="step", values="n")
           .rename(columns={step_from: "도달", step_to: "전환"})
           .reset_index())
    piv = piv[piv["도달"] >= C.MIN_SAMPLE]
    if len(piv) < 2:
        return None
    piv["전환율"] = piv["전환"] / piv["도달"]
    return piv


def _final_checks(t: dict, secs: list[dict]) -> dict:
    """게이트 3(최종 확정) 직전 마지막 점검. 판단은 하지 않고 사실만 모은다.

    입력 중 경고·저장·PDF 미리보기는 이 함수와 무관하게 그대로 된다 —
    여기서 나온 결과는 오직 게이트 3 "확정" 버튼의 활성 여부에만 쓴다.
    """
    phrasing_fail = [(s["title"], bad) for s in secs
                     if (bad := S.check_phrasing(s.get("body") or ""))]

    checks = V.run_checks(t)
    warns = [c for c in checks if c["level"] == "warn"]
    lim_body = next((s.get("body") or "" for s in secs
                     if s["title"] == "7. 한계"), "")
    warn_missing = [w["name"] for w in warns if w["name"] not in lim_body]

    leaks = S.find_hidden_leaks(secs)

    try:
        to_pdf.build_pdf(secs, {})
        pdf_ok = True
    except Exception:
        pdf_ok = False

    ok = not phrasing_fail and not warn_missing and not leaks and pdf_ok
    return {"phrasing_fail": phrasing_fail, "warns": warns,
            "warn_missing": warn_missing, "leaks": leaks,
            "pdf_ok": pdf_ok, "ok": ok}


st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '리포트</div>', unsafe_allow_html=True)
ui.page_guide("report")

nav, body = st.columns([1, 3.4])

with nav:
    titles = [s["title"] for s in secs]
    pick = st.radio("목차", titles, label_visibility="collapsed")
    st.divider()
    done = sum(1 for s in secs if s["kind"] == "human" and s["body"].strip())
    need = sum(1 for s in secs if s["kind"] == "human")
    left = sum(1 for s in secs if s["kind"] == "todo")
    st.caption(f"사람 작성 {done}/{need}장")
    st.progress(done / need if need else 0)
    if left:
        st.caption(f"아직 안 만든 장 {left}개")

sec = next(s for s in secs if s["title"] == pick)

with body:
    kind = {"auto": "자동 생성", "human": "사람 작성",
            "todo": "아직 안 만듦"}[sec["kind"]]
    lvl = {"auto": "ok", "todo": "none"}.get(
        sec["kind"], "ok" if sec["body"].strip() else "warn")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
        f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

    if sec["kind"] == "todo":
        ui.todo_card(sec["todo"])
    elif sec["kind"] == "auto":
        st.markdown(
            f'<div class="card"><div style="white-space:pre-line;'
            f'font-size:14px;line-height:1.75">{sec["body"]}</div></div>',
            unsafe_allow_html=True)
        bad = S.check_phrasing(sec["body"])
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>. 관측 데이터로는 인과를 "
                       f"주장할 수 없습니다.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")

        if "funnel" in sec.get("charts", []):
            f = M.funnel(t["ic_deficiency"], t["ic_remediation"])
            st.image(pdf_charts.funnel_png(f), width="stretch")
        if "device" in sec.get("charts", []):
            f = M.funnel(t["ic_deficiency"], t["ic_remediation"])
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            g = _process_compare(t, f, bi)
            if g is not None:
                st.image(pdf_charts.device_png(g), width="stretch")
        # 실험 결과 차트는 현재 내부회계 데이터셋에 experiments·
        # experiment_assignments 테이블이 없어 표시하지 않는다.
        # core.metrics.experiment_results()·pdf_charts.experiments_png()는
        # 그대로 보존돼 있다 — 실험 데이터가 생기면 다시 연결하면 된다.
    else:
        st.caption(sec["placeholder"])
        if sec.get("hint"):
            # 가이드라인은 참고용이다 — text_area 기본값·저장 대상이
            # 아니며, 이 단서를 항상 같이 보여준다.
            st.caption("※ 아래 내용은 현재 데이터와 분석 결과를 바탕으로 "
                       "제공되는 작성 가이드라인입니다. 실제 보고 문구는 "
                       "담당자가 검토·수정한 후 최종 확정해야 합니다.")
            ui.callout(sec["hint"], "info")
        txt = st.text_area("본문", value=sec["body"], height=280,
                           key=f"h_{sec['title']}", label_visibility="collapsed")
        # 사람이 쓴 장에도 반드시 검사한다(S.check_phrasing 자체 문서화 —
        # "사람이 더 자주 쓴다"). 저장 전 입력 중인 내용을 바로 검사한다.
        bad_human = S.check_phrasing(txt)
        if bad_human:
            ui.callout(f"인과 단정 표현이 발견되었습니다: "
                       f"<b>{', '.join(bad_human)}</b>. 관측 데이터로는 "
                       f"인과를 주장할 수 없습니다.")
        elif txt.strip():
            st.caption("✓ 인과 단정 표현 검사 통과")
        if st.button("작성내용 저장", type="primary", key=f"save_{sec['title']}"):
            if txt.strip():
                st.session_state.human[sec["title"]] = txt
                st.session_state[f"msg_{sec['title']}"] = ("success", "저장되었습니다.")
            else:
                st.session_state[f"msg_{sec['title']}"] = (
                    "warn", "내용을 입력한 뒤 저장해 주세요.")
            st.rerun()
        _msg = st.session_state.pop(f"msg_{sec['title']}", None)
        if _msg:
            (st.success if _msg[0] == "success" else st.warning)(_msg[1])

# ── 내보내기 ──────────────────────────────────────────────────────
st.divider()
ui.section("내보내기")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
    if st.button("PDF 만들기", type="primary"):
        with st.spinner("차트를 그리고 PDF를 조립하는 중..."):
            f = M.funnel(t["ic_deficiency"], t["ic_remediation"])
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            g = _process_compare(t, f, bi)
            charts = {"funnel": pdf_charts.funnel_png(f)}
            if g is not None:
                charts["device"] = pdf_charts.device_png(g)
            pdf = to_pdf.build_pdf(secs, charts)
        st.session_state.pdf = pdf
        st.success(f"생성 완료 · {len(pdf)/1024:.0f}KB")
    if st.session_state.get("pdf"):
        st.download_button("PDF 내려받기", st.session_state.pdf,
                           file_name=f"성장리포트_{C.PERIOD[0][:7]}.pdf",
                           mime="application/pdf")

with c2:
    st.markdown("**이메일 초안** — 실제로 보내지 않습니다")
    draft = S.email_draft(t, secs)
    st.text_input("받는 사람", draft["to"], disabled=True)
    st.text_input("제목", draft["subject"], disabled=True)
    with st.expander("본문 미리보기"):
        st.markdown(draft["html"], unsafe_allow_html=True)

    run = st.session_state.run
    gate2_ok = bool(run and gates.is_passed(run, 2))
    human_ready = need > 0 and done == need
    if gate2_ok and human_ready:
        st.markdown('<div class="gate final" style="margin-top:12px">'
                    '<div class="q">게이트 3 · 발송</div>'
                    '<div style="font-size:12.5px;color:#9f1239;margin-top:6px">'
                    '<b>되돌릴 수 없습니다.</b> 통과시키면 이 실행(run)의 '
                    '보고서 상태는 되돌릴 수 없고 발송 기록이 남습니다.</div>'
                    '</div>', unsafe_allow_html=True)

        # 최종 점검 — 문장 작성/수정·PDF 미리보기는 이 결과와 무관하게
        # 그대로 된다. 오직 "확정" 버튼의 활성 여부에만 쓴다.
        fc = _final_checks(t, secs)
        st.markdown("**최종 점검**")
        st.write(f"{'✅' if human_ready else '❌'} 사람 작성: {done}/{need} 완료")
        st.write(f"{'✅' if not fc['phrasing_fail'] else '❌'} 인과 표현: "
                 f"{'통과' if not fc['phrasing_fail'] else '실패'}")
        for title, words in fc["phrasing_fail"]:
            st.caption(f"- {title}: 인과 단정 표현 '{', '.join(words)}' 발견")
        st.write(f"{'✅' if not fc['warn_missing'] else '❌'} 검증 warning → "
                 f"한계 반영: {'통과' if not fc['warn_missing'] else '실패'}"
                 f"({len(fc['warns'])}건 중 {len(fc['warns']) - len(fc['warn_missing'])}건 반영)")
        for name in fc["warn_missing"]:
            st.caption(f"- 한계에 반영 안 됨: {name}")
        st.write(f"{'✅' if not fc['leaks'] else '❌'} 감춘 수치 재노출: "
                 f"{'없음' if not fc['leaks'] else '발견 — ' + ', '.join(fc['leaks'])}")
        st.write(f"{'✅' if fc['pdf_ok'] else '❌'} PDF: "
                 f"{'정상' if fc['pdf_ok'] else '문제'}")
        if not fc["ok"]:
            reasons = []
            for title, words in fc["phrasing_fail"]:
                reasons.append(f"- {title}: 인과 단정 표현 '{', '.join(words)}' 발견")
            if fc["warn_missing"]:
                reasons.append("- 검증 warning 중 한계 절에 반영되지 않은 "
                               f"항목 {len(fc['warn_missing'])}건")
            if fc["leaks"]:
                reasons.append(f"- 감춘 수치 재노출: {', '.join(fc['leaks'])}")
            if not fc["pdf_ok"]:
                reasons.append("- PDF 생성 중 문제 발생")
            st.error("**게이트 3 통과 불가**\n" + "\n".join(reasons))

        if gates.is_passed(run, 3):
            st.success("게이트 3 통과 기록됨 · 실제 발송은 하지 않았습니다.")
            _amsg = st.session_state.pop("msg_archive", None)
            if _amsg:
                (st.success if _amsg[0] == "success" else st.info)(_amsg[1])
            if run.get("archive"):
                pdf_saved = archive.read_pdf(run["archive"]["archive_id"])
                if pdf_saved:
                    st.download_button(
                        "저장된 PDF 다운로드", pdf_saved,
                        file_name=f"{run['archive']['archive_id']}.pdf",
                        mime="application/pdf", key="dl_archived_pdf")
        else:
            ok = st.text_input('확인 문구로 "발송"을 입력하십시오', key="g3")
            if st.button("확정", disabled=(ok != "발송") or not fc["ok"]):
                if run.get("archive"):
                    st.session_state["msg_archive"] = (
                        "info", "이미 저장된 보고서입니다.")
                else:
                    gates.pass_gate(run, 3, "초안 확정 (실제 발송 없음)")
                    f = M.funnel(t["ic_deficiency"], t["ic_remediation"])
                    bi = max(int(f.index[f.is_bottleneck][0]), 1)
                    g = _process_compare(t, f, bi)
                    archive_charts = {"funnel": pdf_charts.funnel_png(f)}
                    if g is not None:
                        archive_charts["device"] = pdf_charts.device_png(g)
                    archive_pdf = to_pdf.build_pdf(secs, archive_charts)
                    meta = archive.save_archive(run, t, secs, archive_pdf)
                    run["archive"] = {"archive_id": meta["archive_id"]}
                    st.session_state["msg_archive"] = (
                        "success", "아카이브 저장 완료")
                gates.save(run)
                st.rerun()
    elif not gate2_ok:
        st.caption("게이트 2를 통과해야 발송 확정 단계가 열립니다.")
    else:
        st.caption(f"사람 작성 {done}/{need}장 — 2·6·8장을 모두 저장해야 "
                   "발송 확정 단계가 열립니다.")
