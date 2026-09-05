# -*- coding: utf-8 -*-
"""실행 — 데이터를 넣고 8단계를 돌린다.

사람이 개입하는 곳은 게이트 세 곳뿐이다.
게이트는 앱이 판단하지 않는다. 판단할 재료를 놓고 사람이 누른다.
누가 언제 무엇을 보고 통과시켰는지 run 기록에 남는다.
"""
import pandas as pd
import streamlit as st

from core import config as C, gates, load, metrics as M, validate as V
from viz import ui

st.set_page_config(page_title="실행", page_icon="▶️", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("run")

if "run" not in st.session_state:
    st.session_state.run = None
run = st.session_state.run

ui.context_bar(run)
st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:18px">'
            '실행</div>', unsafe_allow_html=True)

# ── 1. 데이터 선택 ────────────────────────────────────────────────
ui.section("1. 데이터 선택")
src = st.radio("원본", ["등록된 데이터셋", "파일 업로드"],
               horizontal=True, label_visibility="collapsed")

tables = None
if src == "등록된 데이터셋":
    st.selectbox("데이터셋", [C.DATASET], label_visibility="collapsed")
    if st.button("적재 시작", type="primary"):
        st.session_state.run = gates.new_run()
        run = st.session_state.run
        with st.spinner("적재 중..."):
            tables = ui.guard(load.load_all)
        if tables is None:
            st.session_state.run = None
            st.stop()
        gates.log(run, f"적재 완료 · {len(tables)}개 테이블 "
                       f"{sum(len(d) for d in tables.values()):,}행")
        gates.advance(run, "적재")
        st.session_state.loaded = True
        st.rerun()
else:
    up = st.file_uploader("데이터 파일 (**파일명이 테이블명**이어야 합니다)",
                          type=["csv", "parquet", "xlsx", "xls"],
                          accept_multiple_files=True)
    st.caption("배포본에서는 파일당 20MB로 제한됩니다. "
               "큰 데이터는 parquet 으로 바꿔 넣으십시오.")
    if up and st.button("적재 시작", type="primary"):
        st.session_state.run = gates.new_run("업로드")
        run = st.session_state.run
        tables = load.load_uploaded(up)
        gates.log(run, f"업로드 {len(tables)}개 테이블 적재")
        gates.advance(run, "적재")
        st.session_state.loaded = True
        st.rerun()

if not run:
    st.info("데이터를 적재하면 진행 상태가 표시됩니다.")
    st.stop()

if tables is None:
    tables = ui.guard(load.load_all)
    if tables is None:
        st.stop()

# ── 진행 스테퍼 ───────────────────────────────────────────────────
ui.section("진행")
ui.stepper(gates.STEPS, run["step"])

# ── 2. 프로파일 ───────────────────────────────────────────────────
if run["step"] >= 1:
    ui.section("2. 프로파일", "적재된 데이터가 무엇인지 먼저 본다")
    prof = V.profile(tables)
    st.dataframe(prof, width="stretch", hide_index=True)
    gates.advance(run, "프로파일")

# ── 3. 검증 ───────────────────────────────────────────────────────
if run["step"] >= 2:
    ui.section("3. 검증", "통과·경고·차단을 나눠 사람 앞에 놓는다")
    checks = ui.guard(V.run_checks, tables)
    if checks is None:
        st.stop()
    s = V.summarize(checks)
    gates.advance(run, "검증")

    c1, c2, c3 = st.columns(3)
    for col, k, label in [(c1, "ok", "통과"), (c2, "warn", "경고"),
                          (c3, "block", "차단")]:
        with col:
            st.markdown(ui.kpi_card(label, f"{s[k]}건", "", k),
                        unsafe_allow_html=True)

    st.write("")
    for c in checks:
        with st.container():
            st.markdown(
                f'<div class="card tight" style="margin-bottom:8px">'
                f'{ui.badge(c["level"])} <b>{c["name"]}</b><br>'
                f'<span style="font-size:13px;color:#475569">{c["msg"]}</span>'
                + (f'<div style="font-size:12px;color:#94a3b8;margin-top:6px">'
                   f'{c["detail"]}</div>' if c["detail"] else "")
                + '</div>', unsafe_allow_html=True)

# ── 게이트 1 ──────────────────────────────────────────────────────
if run["step"] >= 3 and not gates.is_passed(run, 1):
    ui.section("게이트 1 · 입구")
    warns = [c for c in checks if c["level"] == "warn"]
    body = (f'<div class="gate"><div class="q">{gates.GATES[1]["question"]}</div>')
    if warns:
        body += ('<div class="warnbox"><b>경고 '
                 f'{len(warns)}건을 확인하십시오.</b><br>'
                 + "<br>".join(f"· {w['name']} — {w['msg']}" for w in warns)
                 + "</div>")
    body += ('<div style="font-size:12.5px;color:#64748b">'
             '되돌릴 수 있는 게이트입니다.</div></div>')
    st.markdown(body, unsafe_allow_html=True)

    note = st.text_input("판단 근거 (기록에 남습니다)",
                         placeholder="예: target_date 기간 외 19건은 향후 개선 예정 건이므로 진행")
    a, b = st.columns([1, 1])
    with a:
        if st.button("되돌리기"):
            st.session_state.run = None
            st.rerun()
    with b:
        if st.button("통과시키기", type="primary", disabled=not s["can_pass"]):
            gates.pass_gate(run, 1, note)
            gates.advance(run, "게이트1")
            st.rerun()
    if not s["can_pass"]:
        st.error("차단 항목이 있어 통과할 수 없습니다.")

# ── 4. 계산 ───────────────────────────────────────────────────────
if gates.is_passed(run, 1):
    ui.section("4. 계산")
    f = ui.guard(M.funnel, tables["ic_deficiency"], tables["ic_remediation"])
    k = ui.guard(M.kpis, tables)
    if f is None or k is None:
        st.stop()
    res = ui.guard(M.experiment_results, tables) or []
    gates.advance(run, "계산")
    if "계산 완료" not in [l["msg"][:5] for l in run["log"]]:
        gates.log(run, f"계산 완료 · 퍼널 {len(f)}단계 · 실험 {len(res)}건")

    cols = st.columns(4)
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            # 대시보드와 같은 뜻이다 — 임계값 미정("none")은 "정상"이
            # 아니라 "참고지표"다. ui.kpi_card·ui.badge를 그대로 재사용한다.
            sub = "참고지표" if lv == "none" else ""
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), sub, lv),
                        unsafe_allow_html=True)

    st.write("")
    # 표시용으로만 NaN을 "-"로 바꾼다. f(funnel() 반환값) 자체는 그대로 둔다.
    step_disp = f[["label", "n", "step_rate", "cum_rate"]].rename(columns={
        "label": "단계", "n": "도달", "step_rate": "단계 전환율",
        "cum_rate": "누적 전환율"}).copy()
    for col_name in ("단계 전환율", "누적 전환율"):
        step_disp[col_name] = step_disp[col_name].apply(
            lambda v: "-" if pd.isna(v) else f"{v:.2%}")
    st.dataframe(
        step_disp.style.format({"도달": "{:,}"}),
        width="stretch", hide_index=True)

# ── 게이트 2 ──────────────────────────────────────────────────────
if gates.is_passed(run, 1) and not gates.is_passed(run, 2):
    ui.section("게이트 2 · 출구")

    # 게이트 2 참고자료 — 판단은 자동으로 하지 않는다. 근거를 사람이
    # 입력해 통과하는 아래 절차는 그대로 두고, 판정 재료만 미리 모은다.
    rf = M.retention_funnel(tables)
    pop_n = int(rf.loc[rf.step == "기준모집단", "n"].iloc[0])
    보류항목 = [tc for tc in (
        M.trust_check("개선 후 재발 분석", pop_n),
        M.trust_check("재고 프로세스 운영 적정률(2026)", 7),
        M.trust_check("Key통제 개선완료율(2026)", 7),
    ) if not tc["trusted"]]

    g_long = M.funnel_by(tables, "process_name")
    process_sum = int(g_long.loc[g_long.step == "미비점발생", "n"].sum())
    합계일치 = process_sum == int(f.n.iloc[0])

    rem26 = tables["ic_remediation"].merge(
        tables["ic_deficiency"][["deficiency_id", "year"]],
        on="deficiency_id", how="left")
    rem26 = rem26[rem26["year"] == 2026]
    future_n = int(rem26["target_date"].astype(str).str.startswith("2027").sum())

    st.markdown(
        '<div class="card tight" style="margin-bottom:10px">'
        '<div style="font-size:13px;font-weight:700;margin-bottom:6px">'
        '게이트 2 참고자료 — 신뢰성 판정 요약</div>'
        '<div style="font-size:12.5px;color:#475569;line-height:1.8">'
        f'· 판정 보류 항목 {len(보류항목)}건: '
        + (", ".join(f"{tc['name']}({tc['reason']})" for tc in 보류항목)
           or "없음")
        + '<br>· 프로세스 분해 합계 = 전체 합계: '
        + ("일치" if 합계일치 else "⚠ 불일치(확인 필요)")
        + f'<br>· 관측기간 이슈: 2026년 개선조치 {len(rem26)}건 중 '
          f'{future_n}건({future_n / len(rem26) * 100:.2f}%)의 '
          'target_date가 2027년'
        '</div></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="gate"><div class="q">'
                f'{gates.GATES[2]["question"]}</div>'
                f'<div style="font-size:12.5px;color:#64748b;margin-top:8px">'
                f'계산 결과가 상식에 맞는지, 이전 기간과 크게 다르지 않은지 '
                f'확인하십시오. 되돌릴 수 있습니다.</div></div>',
                unsafe_allow_html=True)
    note2 = st.text_input("판단 근거", key="g2",
                          placeholder="예: 전환율 3.72%는 직전 분기와 유사")
    a, b = st.columns([1, 1])
    with a:
        if st.button("되돌리기", key="r2"):
            gates.revert_gate(run, 2) or gates.revert_gate(run, 1)
            st.rerun()
    with b:
        if st.button("통과시키기", type="primary", key="p2"):
            gates.pass_gate(run, 2, note2)
            gates.advance(run, "대시보드")
            gates.save(run)
            st.rerun()

if gates.is_passed(run, 2):
    gates.advance(run, "리포트")
    run["status"] = "완료"
    gates.save(run)
    st.success("계산과 검증이 끝났습니다. 대시보드와 리포트로 넘어가십시오.")
    a, b = st.columns(2)
    with a:
        st.page_link("pages/2_대시보드.py", label="📊 대시보드 열기 →")
    with b:
        st.page_link("pages/3_리포트.py", label="📄 리포트 열기 →")

# ── 로그 ──────────────────────────────────────────────────────────
ui.section("로그")
ui.logbox(run["log"])
