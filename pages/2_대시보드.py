# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
import streamlit as st

from core import config as C, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("dash")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()


@st.dialog("왜 보여주지 않나요?")
def _why_not_shown(tc: dict) -> None:
    """감춘 지표의 조건값만 보여준다. 비율·증감·비교차이는 넣지 않는다."""
    st.markdown(f"**걸린 조건**: {'최소 표본' if not tc['trusted'] else '관측기간'}")
    st.markdown(f"**실제**: {tc['actual']}건")
    st.markdown(f"**기준**: {tc['threshold']}건 이상")
    st.markdown(f"**다시 계산 조건**: 표본이 {tc['threshold']}건 이상 "
                "누적된 후 재확인")


st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '대시보드</div>', unsafe_allow_html=True)
ui.page_guide("dash")

# ── 지표 카드 ─────────────────────────────────────────────────────
# 연도 delta는 관측기간 이슈가 없는 지표에만 보여준다(6절). 미해소 미비점
# 비율·개선완료율은 metric-001·004.yaml의 "유효구간" 절에 이미 "계산
# 시점에 따라 달라질 수 있다"고 적혀 있어 연도 비교에 쓰지 않는다.
# 반복 미비점 통제 비율은 연도별 값이 아예 없다(결합 스냅샷).
DELTA_OK = {"운영 적정률"}

k = ui.guard(M.kpis, t)
if k:
    m = ui.guard(M.monthly, t)
    years_avail = sorted(t["ic_deficiency"]["year"].unique())
    prev_year = years_avail[-2] if len(years_avail) >= 2 else None
    k_prev = ui.guard(M.kpis, t, prev_year) if prev_year is not None else None

    cols = st.columns(len(k))
    has_ref = False
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            # "참고지표"(임계값 미정)와 "정상"(ok)은 다른 상태다 — 같은
            # 색으로 섞지 않는다. lv=="none"이면 참고지표 텍스트로 덮는다.
            sub = "참고지표" if lv == "none" else ""
            has_ref = has_ref or lv == "none"
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), sub, lv),
                        unsafe_allow_html=True)
            if name in DELTA_OK and k_prev and name in k_prev:
                prev_v = k_prev[name]["value"]
                st.caption(f"{prev_year}년 {prev_v:.2f}% → {v['value']:.2f}%"
                           f" ({v['value'] - prev_v:+.2f}%p)")
            # 추이가 있으면 스파크라인. 지표 이름과 열 이름이 같아야 그려진다.
            if m is not None and name in getattr(m, "columns", []):
                st.plotly_chart(
                    charts.spark(m[name], C.COLORS[lv] if lv != "ok" else None),
                    width="stretch", config={"displayModeBar": False},
                    key=f"sp_{name}")
    if has_ref:
        st.caption("임계값이 정의된 지표만 상태를 판정하며, 나머지는 "
                   "참고지표로 표시합니다.")

# ── Track B 퍼널 ──────────────────────────────────────────────────
ui.section("Track B 퍼널 — 미비점 개선 파이프라인", "그레인을 먼저 확인한다")
f = ui.guard(M.funnel, t["ic_deficiency"], t["ic_remediation"])
if f is not None:
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(charts.funnel_bars(f), width="stretch",
                        config={"displayModeBar": False})
        bn = f[f.is_bottleneck].iloc[0]
        bi = max(int(f.index[f.label == bn.label][0]), 1)
        prev = f.iloc[bi - 1]
        ui.callout(
            f"<b>병목은 {prev.label} → {bn.label}</b> 구간입니다. "
            f"{prev.n:,} 중 {bn.n:,}만 넘어가 "
            f"<b>{(1-bn.step_rate)*100:.1f}%가 이탈</b>합니다.")

    with right:
        st.caption("분해 축: 프로세스")
        i = st.selectbox(
            "구간", range(len(f) - 1),
            format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
            index=min(bi - 1, len(f) - 2))
        step_from, step_to = f.step.iloc[i], f.step.iloc[i + 1]
        RATE_LABEL = {"개선조치착수": "착수율", "개선조치완료": "개선완료율"}
        rate_label = RATE_LABEL.get(step_to, "비율")
        g_long = ui.guard(M.funnel_by, t, "process_name")
        g = None
        if g_long is not None and len(g_long):
            piv = (g_long[g_long.step.isin([step_from, step_to])]
                   .pivot(index="process_name", columns="step", values="n")
                   .rename(columns={step_from: "도달", step_to: "전환"})
                   .reset_index())
            piv = piv[piv["도달"] > 0]
            g = piv
        if g is not None and len(g):
            # 프로세스별 합계가 전체와 일치하는지 먼저 확인한다.
            # 조용히 빠지는 프로세스가 있으면 안 된다(합계 불일치로 드러난다).
            total_here = int(g["도달"].sum())
            expected = int(f.n.iloc[i])
            st.caption(f"프로세스별 합계 {total_here}건 = 전체 {expected}건 "
                       + ("일치" if total_here == expected else "⚠ 불일치(확인 필요)"))

            # 표본 확인이 비율 계산보다 먼저다 — n<20인 행은 전환율을
            # 나누지 않는다("계산해 놓고 숨기기"가 아니라 "계산하지 않기").
            trusted_g = g[g["도달"] >= C.MIN_SAMPLE].copy()
            blocked_g = g[g["도달"] < C.MIN_SAMPLE]

            if len(trusted_g) >= 2:
                trusted_g["전환율"] = trusted_g["전환"] / trusted_g["도달"]
                st.plotly_chart(charts.device_compare(trusted_g), width="stretch",
                                config={"displayModeBar": False})
                hi = trusted_g.loc[trusted_g.전환율.idxmax()]
                lo = trusted_g.loc[trusted_g.전환율.idxmin()]
                if hi[trusted_g.columns[0]] != lo[trusted_g.columns[0]]:
                    ui.callout(
                        f"<b>{lo[trusted_g.columns[0]]}</b> 프로세스의 "
                        f"{rate_label}은 <b>{lo.전환율*100:.1f}%</b>로, 표본 "
                        f"기준을 충족한 프로세스 중 가장 높은 "
                        f"<b>{hi[trusted_g.columns[0]]}</b>"
                        f"({hi.전환율*100:.1f}%)보다 "
                        f"<b>{(hi.전환율-lo.전환율)*100:.1f}%p 낮습니다.</b>")
            else:
                st.caption(f"표본 기준(최소 {C.MIN_SAMPLE}건)을 충족하는 "
                           "프로세스가 없어 프로세스별 전환율 비교는 "
                           "표시하지 않습니다.")

            if len(blocked_g):
                st.markdown(
                    f'{ui.badge("block", "판정 보류")} 아래 프로세스는 표본이 '
                    f'최소 기준({C.MIN_SAMPLE}건) 미만이라 전환율을 계산하지 '
                    '않았습니다 — 원시 건수만 표시합니다.',
                    unsafe_allow_html=True)
                st.dataframe(
                    blocked_g.rename(columns={"process_name": "프로세스"})
                             [["프로세스", "도달", "전환"]],
                    hide_index=True, width="stretch")

    # 단계별 표 — 차트와 같은 f를 그대로 표로도 보여준다(새 계산 없음).
    st.dataframe(
        f[["label", "n", "step_rate", "cum_rate"]].rename(columns={
            "label": "단계", "n": "건수", "step_rate": "전 단계 대비",
            "cum_rate": "누적 비율"}),
        hide_index=True, width="stretch",
        column_config={
            "건수": st.column_config.NumberColumn(format="%d"),
            "전 단계 대비": st.column_config.ProgressColumn(
                min_value=0, max_value=1, format="%.1f%%"),
            "누적 비율": st.column_config.ProgressColumn(
                min_value=0, max_value=1, format="%.1f%%"),
        })

# ── 유지·재발 구성 ────────────────────────────────────────────────
# "유지 10·재발 5"는 판정 모집단 15개가 반드시 순서대로 거치는 단계가
# 아니라, 상호배타적인 결과 분류다(CLAUDE.md "유지·재발은 퍼널이 아니다"
# 참고). 그래서 퍼널 차트·전환율 표현을 쓰지 않는다. 함수명
# retention_funnel()은 다른 코드 호환성 때문에 그대로 둔다.
ui.section("유지·재발 구성", "개선을 완료한 통제가 다시 미비점으로 돌아왔는가")
rf = ui.guard(M.retention_funnel, t)
if rf is not None and len(rf):
    # 판단이 계산보다 먼저다 — trusted가 False면 유지율·재발률을
    # 나누지 않는다(원시 건수는 rf에서 그대로 읽어도 된다. 5-6절 참고).
    pop_n = int(rf.loc[rf.step == "기준모집단", "n"].iloc[0])
    유지_n = int(rf.loc[rf.step == "유지", "n"].iloc[0])
    재발_n = int(rf.loc[rf.step == "재발", "n"].iloc[0])
    tc = M.trust_check("개선 후 재발 분석", pop_n)

    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.markdown(
            '<div class="card tight">'
            '<div style="font-size:13px;color:#475569;margin-bottom:10px">'
            f'판정 모집단(2025년 완료 처리된 통제) {pop_n}개의 구성 — 원시 '
            '건수</div>'
            '<div style="display:flex;gap:32px">'
            '<div><div style="font-size:11px;color:#94a3b8">유지</div>'
            f'<div style="font-size:28px;font-weight:700">{유지_n}</div></div>'
            '<div><div style="font-size:11px;color:#94a3b8">재발</div>'
            f'<div style="font-size:28px;font-weight:700;'
            f'color:{C.COLORS["block"]}">{재발_n}</div></div>'
            '</div></div>', unsafe_allow_html=True)
    with c2:
        if tc["trusted"]:
            ui.callout(
                "2025년에 개선을 완료한 통제가 2026년에 다시 미비점으로 "
                f"발생했는지 확인합니다. <b>{유지_n}개는 재발하지 않았고 "
                f"({유지_n / pop_n * 100:.2f}%), {재발_n}개는 다시 발생했습니다 "
                f"({재발_n / pop_n * 100:.2f}%).</b>", "info")
        else:
            ui.callout(
                f"표본이 최소 기준({tc['threshold']}건)에 못 미쳐 유지율· "
                "재발률은 계산하지 않습니다. 판정 모집단 원시 건수만 "
                f"참고하십시오({pop_n}개 중 유지 {유지_n}개·재발 "
                f"{재발_n}개).", "info")

        with st.status("판정 과정", expanded=False) as box:
            st.write(f"1. 표본 확인 — {'통과' if tc['trusted'] else '실패'} "
                     f"({tc['actual']}건 / 최소 {tc['threshold']}건)")
            if tc["trusted"]:
                st.write("2. 관측기간 확인 — 통과")
                st.write("3. 계산 — 계산함(유지율·재발률)")
                st.write("4. 최종 판정 — 통과")
                box.update(label="판정 과정 · 통과", state="complete")
            else:
                st.write("2. 관측기간 확인 — 계산하지 않음")
                st.write("3. 계산 — 계산하지 않음(유지율·재발률)")
                st.write("4. 최종 판정 — 판정 보류")
                box.update(label="판정 과정 · 판정 보류", state="error")

        if not tc["trusted"]:
            if st.button("왜 보여주지 않나요?", key="why_retention"):
                _why_not_shown(tc)
        with st.popover("정의"):
            st.caption("유지 = 2025년 완료 처리된 통제가 2026년 같은 "
                       "control_id에서 재발하지 않음. 재발 = 다시 발생함. "
                       "최소표본 20건은 통계적 검정력 기준이 아니라 이 "
                       "프로젝트의 운영 기준이다(my-wiki-04 analysis-005).")

    # 관측기간 한계 — 2026년 개선조치 중 target_date가 2027년인 건.
    # 표본(len(rem26))은 22건으로 최소표본을 충족하므로 값 자체는 계산해
    # 보여주되, 전년 대비 성과 비교 판정에는 쓰지 않는다(5-6절 참고).
    rem26 = t["ic_remediation"].merge(
        t["ic_deficiency"][["deficiency_id", "year"]], on="deficiency_id", how="left")
    rem26 = rem26[rem26["year"] == 2026]
    future_n = int(rem26["target_date"].astype(str).str.startswith("2027").sum())
    if future_n:
        tc2 = M.trust_check("2026년 개선조치 관측기간", len(rem26),
                            observation_issue=True,
                            detail=f"{len(rem26)}건 중 {future_n}건은 target_date가 2027년")
        st.caption(f"⚠ {tc2['message']}")

# 실험 결과 / 획득 경로 효율(채널 효율) 영역은 현재 내부회계 데이터셋에
# 해당 분석(experiments·experiment_assignments 테이블, 채널 비용 데이터)이
# 없어 화면에서 제거했다. core/metrics.py의 experiment_results·
# srm_check·channel_efficiency·EXP_STEPS 등은 그대로 보존돼 있다 —
# 실험 데이터가 생기면 이 자리에 다시 연결하면 된다.
