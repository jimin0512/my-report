# -*- coding: utf-8 -*-
"""아카이브 — 지난 실행을 찾고 비교한다.

재현이 핵심이다. 같은 입력이면 같은 결과가 나와야 하고,
그것을 확인할 수 없으면 자동화를 신뢰할 수 없다.
"""
import pandas as pd
import streamlit as st

from core import config as C, gates, load, metrics as M
from report import archive
from viz import charts, ui

st.set_page_config(page_title="아카이브", page_icon="🗂️", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("archive")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '아카이브</div>', unsafe_allow_html=True)

runs = gates.load_all()

ui.section("실행 이력")
if not runs:
    st.info("아직 저장된 실행이 없습니다. 실행 화면에서 게이트 2까지 통과하면 "
            "여기에 기록됩니다.")
else:
    for r in runs[:20]:
        lv = {"완료": "ok", "진행중": "warn", "차단": "block"}.get(
            r.get("status", ""), "none")
        gl = r.get("gates", {})
        passed = "".join(
            f'<span style="margin-right:8px">게이트{n} '
            f'{"✓" if str(n) in gl else "—"}</span>' for n in (1, 2, 3))
        notes = " / ".join(g.get("note", "") for g in gl.values() if g.get("note"))
        st.markdown(
            f'<div class="card tight" style="margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="font-weight:700" class="num">{r["run_id"]}</div>'
            f'<div style="font-size:12px;color:#64748b">{r.get("dataset","")}</div>'
            f'<div style="margin-left:auto">{ui.badge(lv, r.get("status",""))}</div>'
            f'</div>'
            f'<div style="font-size:12px;color:#64748b;margin-top:8px">{passed}</div>'
            + (f'<div style="font-size:12px;color:#94a3b8;margin-top:6px">'
               f'판단 근거 — {notes}</div>' if notes else "")
            + '</div>', unsafe_allow_html=True)

# ── 확정된 리포트 ─────────────────────────────────────────────────
ui.section("확정된 리포트", "사람 작성 3장 저장 + 게이트 3 통과 시점의 스냅샷")
archives = archive.load_all()
if not archives:
    st.info("아직 확정된 리포트가 없습니다. 리포트 화면에서 사람 작성 3장을 "
            "모두 저장하고 게이트 3(발송)을 통과시키면 여기에 기록됩니다.")
else:
    for a in archives:
        st.markdown(
            f'<div class="card tight" style="margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="font-weight:700" class="num">{a["archive_id"]}</div>'
            f'<div style="font-size:12px;color:#64748b">{a["dataset"]} · '
            f'{a["period"]["start"]} ~ {a["period"]["end"]}</div>'
            f'<div style="margin-left:auto">'
            f'{ui.badge("ok" if a.get("confirmed") else "none", "확정" if a.get("confirmed") else "미확정")}'
            f'</div></div></div>', unsafe_allow_html=True)
        pdf_bytes = archive.read_pdf(a["archive_id"])
        if pdf_bytes:
            st.download_button(
                "PDF 다운로드", pdf_bytes, file_name=f"{a['archive_id']}.pdf",
                mime="application/pdf", key=f"dl_{a['archive_id']}")

# ── 기간 비교 ─────────────────────────────────────────────────────
ui.section("기간 비교", "수준이 아니라 변화를 본다")
t = ui.guard(load.load_all)
if t is None:
    st.stop()
m = ui.guard(M.monthly, t)

if m is not None and len(m) >= 2:
    months = list(m.index)
    metric_cols = [c for c in m.columns]

    c1, c2 = st.columns(2)
    with c1:
        a = st.selectbox("기준 기간", months, index=len(months) - 2)
    with c2:
        b = st.selectbox("비교 기간", months, index=len(months) - 1)

    # ★ 높을수록 나쁜 지표. metrics.status_of() 와 같은 목록을 쓴다.
    HIGHER_IS_WORSE = {"이탈", "이탈률", "이탈율", "해지율", "불량률", "반품률"}

    rows = []
    for col in metric_cols:
        va, vb = m.loc[a, col], m.loc[b, col]
        pct = (vb / va - 1) * 100 if va else 0
        good = (vb <= va) if col in HIGHER_IS_WORSE else (vb >= va)
        rows.append({"지표": col, str(a): f"{va:,.2f}", str(b): f"{vb:,.2f}",
                     "변화": f"{pct:+.1f}%", "판정": "정상" if good else "주의"})

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 column_config={"판정": st.column_config.TextColumn(width="small")})

    ui.section("추이")
    col = st.selectbox("지표", metric_cols)
    st.plotly_chart(charts.trend(m, col), width="stretch",
                    config={"displayModeBar": False})

# ── 재현 ──────────────────────────────────────────────────────────
ui.section("재현", "같은 입력이면 같은 결과가 나와야 한다")
if st.button("지금 데이터로 재계산해 비교"):
    f = ui.guard(M.funnel, t["funnel_events"])
    k = ui.guard(M.kpis, t)
    if f is not None and k is not None:
        rows = [{"항목": f"{r.label} 도달", "값": f"{r.n:,}"}
                for r in f.itertuples()]
        rows += [{"항목": name, "값": v["fmt"].format(v["value"])}
                 for name, v in k.items()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.success("계산에 현재 시각을 쓰지 않으므로 "
                   "몇 번을 돌려도 같은 값이 나옵니다.")
