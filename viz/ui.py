# -*- coding: utf-8 -*-
"""공용 UI — 디자인 시스템과 재사용 컴포넌트.

색·간격·타이포를 여기서만 정의한다. 페이지마다 스타일을 흩뿌리면
나중에 한 곳을 고쳐도 다른 곳이 안 따라온다.
"""
from __future__ import annotations

import streamlit as st

from core import config as C

STATUS_MARK = {"ok": "●", "warn": "▲", "block": "✕", "none": "○"}
STATUS_TEXT = {"ok": "정상", "warn": "주의", "block": "차단", "none": "없음"}


def css() -> None:
    st.markdown(f"""<style>
:root {{
  --ok:{C.COLORS['ok']}; --warn:{C.COLORS['warn']};
  --block:{C.COLORS['block']}; --none:{C.COLORS['none']};
  --primary:{C.BRAND['primary']}; --ink:{C.BRAND['ink']};
  --muted:{C.BRAND['muted']}; --line:{C.BRAND['line']};
  --bg:{C.BRAND['bg']}; --surface:{C.BRAND['surface']};
}}
html, body, [class*="css"] {{
  font-family: Pretendard, -apple-system, 'Malgun Gothic', sans-serif;
}}
.stApp {{ background: var(--bg); }}
.block-container {{ padding: 1.2rem 2.2rem 3rem; max-width: 1320px; }}
/* 툴바의 메뉴·배포 버튼만 숨긴다.
   header 나 stToolbar 를 통째로 숨기면 안 된다 — 사이드바를 다시 여는
   stExpandSidebarButton 이 그 안에 들어 있어서, 한 번 접으면
   되돌릴 방법이 사라진다. */
[data-testid="stMainMenu"],
[data-testid="stAppDeployButton"],
[data-testid="stStatusWidget"] {{ display: none; }}
footer {{ visibility: hidden; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stExpandSidebarButton"] {{ visibility: visible !important; }}

/* pages/ 에서 자동 생성되는 목차는 감춘다. sidebar_nav() 가 대신 그린다 */
[data-testid="stSidebarNav"] {{ display: none; }}

/* 숫자는 고정폭이라야 자릿수가 흔들리지 않는다 */
.num {{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }}

/* 상단 컨텍스트 바 — 지금 보는 숫자가 어느 데이터의 것인지 잃지 않게 한다 */
.ctx {{
  display:flex; align-items:center; gap:18px; flex-wrap:wrap;
  background:var(--surface); border:1px solid var(--line);
  border-radius:12px; padding:12px 18px; margin-bottom:20px;
}}
.ctx .k {{ font-size:11px; color:var(--muted); letter-spacing:.04em; }}
.ctx .v {{ font-size:14px; font-weight:600; color:var(--ink); }}
.ctx .sep {{ width:1px; height:26px; background:var(--line); }}

.card {{
  background:var(--surface); border:1px solid var(--line);
  border-radius:14px; padding:22px 24px; height:100%;
}}
.card.tight {{ padding:16px 18px; }}

/* 지표 카드 */
.kpi .label {{ font-size:12px; color:var(--muted); font-weight:600;
  letter-spacing:.03em; }}
.kpi .value {{ font-size:32px; font-weight:700; color:var(--ink);
  line-height:1.15; margin:4px 0 2px;
  font-variant-numeric:tabular-nums; }}
.kpi .sub {{ font-size:12px; color:var(--muted); }}

/* 상태 배지 */
.badge {{
  display:inline-flex; align-items:center; gap:5px;
  font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px;
  letter-spacing:.02em;
}}
.b-ok    {{ background:rgba(16,185,129,.12);  color:var(--ok); }}
.b-warn  {{ background:rgba(245,158,11,.14);  color:#b45309; }}
.b-block {{ background:rgba(244,63,94,.12);   color:var(--block); }}
.b-none  {{ background:rgba(100,116,139,.12); color:var(--none); }}

/* 실험 카드 — 왼쪽 굵은 선이 곧 판정이다 */
.exp {{
  background:var(--surface); border:1px solid var(--line);
  border-left:5px solid var(--line); border-radius:12px;
  padding:18px 22px; margin-bottom:14px;
}}
.exp.ok    {{ border-left-color:var(--ok); }}
.exp.warn  {{ border-left-color:var(--warn); background:#fffdf7; }}
.exp.block {{ border-left-color:var(--block); background:#fff8f9; }}
.exp.none  {{ border-left-color:var(--none); }}
.exp .id {{ font-size:11px; font-weight:700; color:var(--muted);
  letter-spacing:.06em; }}
.exp .nm {{ font-size:16px; font-weight:700; color:var(--ink); margin-top:2px; }}
.exp .hy {{ font-size:12px; color:var(--muted); margin-top:4px; }}
.exp .mv {{ font-size:22px; font-weight:700; color:var(--ink);
  font-variant-numeric:tabular-nums; }}
.exp .guard {{
  margin-top:12px; padding-top:12px; border-top:1px dashed var(--line);
  font-size:13px;
}}
.exp .note {{ font-size:12.5px; color:#92400e; margin-top:6px; }}
.exp .blocked {{
  font-size:13px; color:var(--block); background:rgba(244,63,94,.06);
  border-radius:8px; padding:12px 14px; margin-top:10px;
}}

/* 게이트 */
.gate {{
  border:1.5px solid var(--line); border-radius:14px;
  padding:20px 24px; background:var(--surface);
}}
.gate.final {{ border-color:var(--block); background:#fff8f9; }}
.gate .q {{ font-size:16px; font-weight:700; color:var(--ink); }}
.gate .warnbox {{
  background:rgba(245,158,11,.08); border-radius:8px;
  padding:12px 14px; margin:12px 0; font-size:13px; color:#92400e;
}}

/* 스테퍼 */
.stepper {{ display:flex; align-items:flex-start; gap:0; margin:6px 0 22px; }}
.stepper .s {{ flex:1; text-align:center; position:relative; }}
.stepper .dot {{
  width:26px; height:26px; border-radius:50%; margin:0 auto 7px;
  display:flex; align-items:center; justify-content:center;
  font-size:11px; font-weight:700;
  background:var(--surface); border:2px solid var(--line); color:var(--muted);
}}
.stepper .s.done .dot {{ background:var(--ok); border-color:var(--ok); color:#fff; }}
.stepper .s.now .dot  {{ background:var(--primary); border-color:var(--primary);
  color:#fff; box-shadow:0 0 0 4px rgba(79,70,229,.16); }}
.stepper .s .t {{ font-size:11px; color:var(--muted); }}
.stepper .s.now .t {{ color:var(--primary); font-weight:700; }}
.stepper .s:not(:last-child):after {{
  content:""; position:absolute; top:13px; left:50%; width:100%;
  height:2px; background:var(--line); z-index:-1;
}}
.stepper .s.done:not(:last-child):after {{ background:var(--ok); }}

/* 로그 */
.log {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px;
  background:#0f172a; color:#cbd5e1; border-radius:10px; padding:14px 16px;
  max-height:220px; overflow-y:auto; }}
.log .t {{ color:#64748b; margin-right:10px; }}
.log .warn {{ color:#fbbf24; }}
.log .block {{ color:#fb7185; }}

.sec {{ font-size:18px; font-weight:700; color:var(--ink); margin:26px 0 12px; }}
.sec .hint {{ font-size:12px; font-weight:400; color:var(--muted);
  margin-left:10px; }}
.callout {{
  border-left:3px solid var(--warn); background:rgba(245,158,11,.07);
  padding:12px 16px; border-radius:0 8px 8px 0; font-size:13.5px;
  color:#78350f; margin-top:12px;
}}
.callout.info {{ border-left-color:var(--primary);
  background:rgba(79,70,229,.05); color:#3730a3; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric:tabular-nums; }}
</style>""", unsafe_allow_html=True)


def badge(level: str, text: str | None = None) -> str:
    return (f'<span class="badge b-{level}">{STATUS_MARK[level]} '
            f'{text or STATUS_TEXT[level]}</span>')


def context_bar(run: dict | None, extra: dict | None = None) -> None:
    items = [("데이터셋", C.DATASET),
             ("기간", f"{C.PERIOD[0]} ~ {C.PERIOD[1]}")]
    if run:
        items.append(("마지막 실행", run.get("started_at", "-").replace("T", " ")))
    for k, v in (extra or {}).items():
        items.append((k, v))
    html = '<div class="ctx">'
    for i, (k, v) in enumerate(items):
        if i:
            html += '<div class="sep"></div>'
        html += f'<div><div class="k">{k}</div><div class="v num">{v}</div></div>'
    if run:
        lv = {"진행중": "warn", "완료": "ok", "차단": "block"}.get(
            run.get("status", ""), "none")
        html += ('<div style="margin-left:auto">'
                 + badge(lv, run.get("status", "")) + "</div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def section(title: str, hint: str = "") -> None:
    h = f'<span class="hint">{hint}</span>' if hint else ""
    st.markdown(f'<div class="sec">{title}{h}</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", level: str = "ok") -> str:
    return (f'<div class="card kpi tight"><div class="label">{label}</div>'
            f'<div class="value">{value}</div>'
            f'<div class="sub">{badge(level, sub or None)}</div></div>')


def callout(text: str, kind: str = "warn") -> None:
    cls = "callout info" if kind == "info" else "callout"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


def stepper(steps: list[str], current: int) -> None:
    html = '<div class="stepper">'
    for i, s in enumerate(steps):
        cls = "done" if i < current else ("now" if i == current else "")
        mark = "✓" if i < current else str(i + 1)
        html += f'<div class="s {cls}"><div class="dot">{mark}</div><div class="t">{s}</div></div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def logbox(entries: list[dict]) -> None:
    if not entries:
        st.caption("아직 기록이 없습니다.")
        return
    rows = "".join(
        f'<div><span class="t">{e["at"]}</span>'
        f'<span class="{e["level"] if e["level"] != "ok" else ""}">{e["msg"]}</span></div>'
        for e in entries[-40:])
    st.markdown(f'<div class="log">{rows}</div>', unsafe_allow_html=True)


def sidebar_nav(active: str) -> None:
    with st.sidebar:
        st.markdown(
            f'<div style="padding:6px 0 14px">'
            f'<div style="font-size:17px;font-weight:800;color:{C.BRAND["ink"]}">'
            f'성장 리포트</div>'
            f'<div style="font-size:11px;color:{C.BRAND["muted"]}">'
            f'{C.DATASET}</div></div>', unsafe_allow_html=True)
        st.page_link("app.py", label="홈", icon="🏠")
        st.page_link("pages/1_실행.py", label="실행", icon="▶️")
        st.page_link("pages/2_대시보드.py", label="대시보드", icon="📊")
        st.page_link("pages/3_리포트.py", label="리포트", icon="📄")
        st.page_link("pages/4_아카이브.py", label="아카이브", icon="🗂️")
        st.divider()
        st.caption("발송은 초안까지만 만듭니다.\n실제 메일은 나가지 않습니다.")


def todo_card(e) -> None:
    """아직 채우지 않은 자리에 안내를 그린다.

    **골격 전용이다.** 전부 채우고 나면 이 함수와 core/todo.py를 지워도 된다.
    """
    st.markdown(
        f'<div style="border:1.5px dashed #94a3b8;border-radius:14px;'
        f'padding:20px 24px;background:{C.BRAND["surface"]};margin:8px 0 18px">'
        f'<div style="font-size:11px;font-weight:700;color:{C.BRAND["primary"]};'
        f'letter-spacing:.06em">★ {e.day}</div>'
        f'<div style="font-size:16px;font-weight:700;color:{C.BRAND["ink"]};'
        f'margin:6px 0 4px">{e.task}</div>'
        + (f'<div style="font-size:13px;color:#475569;line-height:1.6">'
           f'{e.hint}</div>' if e.hint else "")
        + (f'<div style="font-size:12px;color:{C.BRAND["muted"]};margin-top:10px;'
           f'font-family:ui-monospace,Consolas,monospace">{e.where}</div>'
           if e.where else "")
        + '</div>', unsafe_allow_html=True)


def guard(fn, *args, **kwargs):
    """아직 안 채운 함수를 호출하면 안내 카드를 그리고 None을 돌려준다.

    **골격 전용이다.** 덕분에 빈 골격도 화면이 뜨고, 채운 자리부터 살아난다.

        f = ui.guard(M.funnel, t["funnel_events"])
        if f is None:
            st.stop()
    """
    from core.todo import NotYet
    try:
        return fn(*args, **kwargs)
    except NotYet as e:
        todo_card(e)
        return None
