# -*- coding: utf-8 -*-
"""제안카드.md를 절 구조로 조립한다.

데이터와 카드에서 그대로 재현되는 절은 auto로, 사람의 판단이 필요한 절은 human으로 만들며,
카드에 없는 값은 새로 생성하지 않고 "미확인"(카드에 이미 있는 값) 또는 빈 문자열/placeholder
(사람 절)로 그대로 남긴다.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from core import config as C
from report import to_pdf  # PDF 엔진은 새로 만들지 않고 기존 report/to_pdf.py를 그대로 재사용한다
from report.sections import BANNED, check_phrasing  # 문장검사 로직은 여기서 새로 만들지 않고 그대로 재사용한다
from viz.proposal_charts import funnel_svg, trend_svg  # 차트도 새로 만들지 않고 그대로 재사용한다

CARD_FIELDS = ["분류", "근거", "비용", "효과", "되돌림", "확신도"]
분류_목록 = ["하지 말 것", "다시 할 것", "할 것"]


# ── 카드 파싱 ────────────────────────────────────────────────────
def parse_cards(text: str) -> dict:
    """제안카드.md 본문을 분류(하지 말 것/다시 할 것/할 것)별 카드 목록으로 나눈다.

    파일에 적힌 텍스트를 그대로 옮기기만 한다 — 새 값을 계산하거나 채우지 않는다.
    """
    cards: dict[str, list[dict]] = {k: [] for k in 분류_목록}
    blocks = re.split(r"^## 카드 \d+ — ", text, flags=re.MULTILINE)[1:]
    for block in blocks:
        title, _, body = block.partition("\n")
        card = {"title": title.strip()}
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            key, _, value = line[2:].partition(":")
            key = key.strip()
            if key in CARD_FIELDS:
                card[key] = value.strip()
        분류 = card.get("분류", "")
        if 분류 in cards:
            cards[분류].append(card)
    return cards


def load_cards(path: str | Path | None = None) -> dict:
    """제안카드.md 파일을 읽어 parse_cards()로 구조화한다."""
    p = Path(path) if path else C.ROOT / "제안카드.md"
    return parse_cards(p.read_text(encoding="utf-8"))


# ── 발견 파싱(요약 절에만 쓴다) ────────────────────────────────────
def parse_findings(text: str) -> dict:
    """발견.md에서 "한 장 요약"에 쓸 최소 정보만 뽑는다.

    새 값을 계산하지 않고 파일에 적힌 조회 일시와 "발견 1" 표의 텍스트를 그대로 옮긴다.
    """
    조회일시 = ""
    m = re.search(r"^조회 일시:\s*(.+)$", text, flags=re.MULTILINE)
    if m:
        조회일시 = m.group(1).strip()

    발견1: dict[str, str] = {}
    m = re.search(r"^## 발견 1.*?\n(.*?)(?=\n##|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if m:
        for row in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
                                m.group(1), flags=re.MULTILINE):
            key, value = row.group(1).strip(), row.group(2).strip()
            if key not in ("항목", "---"):
                발견1[key] = value

    return {"조회일시": 조회일시, "발견1": 발견1}


def load_findings(path: str | Path | None = None) -> dict:
    """발견.md 파일을 읽어 parse_findings()로 구조화한다."""
    p = Path(path) if path else C.ROOT / "발견.md"
    return parse_findings(p.read_text(encoding="utf-8"))


# ── 판단기준 파싱("적용" 절의 읽기 전용 후보에만 쓴다) ──────────────
def parse_recent_decisions(text: str) -> list[str]:
    """판단기준.md의 가장 최근 날짜 항목에서 "오늘 실제로 내린 결정" 문장만 그대로 뽑는다.

    새 문장을 만들지 않고 파일에 있는 불릿만 그대로 옮긴다. 못 찾으면 빈 목록.
    """
    date_blocks = list(re.finditer(
        r"^## (\d{4}-\d{2}-\d{2})\n(.*?)(?=\n## |\Z)", text,
        flags=re.MULTILINE | re.DOTALL))
    if not date_blocks:
        return []
    latest = max(date_blocks, key=lambda m: m.group(1))
    m = re.search(r"\[오늘 실제로 내린 결정\]\s*\n(.*?)(?=\n\[|\Z)",
                  latest.group(2), flags=re.DOTALL)
    if not m:
        return []
    return [line.strip()[2:].strip() for line in m.group(1).splitlines()
            if line.strip().startswith("- ")]


def load_recent_decisions(path: str | Path | None = None) -> list[str]:
    """판단기준.md 파일을 읽어 parse_recent_decisions()로 최근 결정 문장만 뽑는다."""
    p = Path(path) if path else C.ROOT / "판단기준.md"
    return parse_recent_decisions(p.read_text(encoding="utf-8"))


def _card_body(card: dict) -> str:
    lines = [f"### {card.get('title', '(제목 없음)')}"]
    for key in CARD_FIELDS:
        lines.append(f"- {key}: {card.get(key, '미확인')}")
    return "\n".join(lines)


# ── auto 절 ──────────────────────────────────────────────────────
def _summary_fields(cards: dict) -> dict:
    """[발견]·[제안]·[불확실]·[근거] 4항목의 원재료를 한 곳에서 뽑는다.

    _s1_summary(텍스트 요약)와 to_html(HTML 요약)이 같은 값을 서로 다른 형식으로만
    보여주도록 필드 추출을 한 번만 한다 — 계산을 늘리지 않는다.
    """
    findings = load_findings()
    발견1 = findings.get("발견1", {})
    조회일시 = findings.get("조회일시") or "미확인"
    값 = 발견1.get("값", "미확인")
    비교대상 = 발견1.get("비교 대상", "미확인")
    비중 = 발견1.get("비중", "미확인")
    표본 = 발견1.get("표본", "미확인")

    titles = [c["title"] for k in 분류_목록 for c in cards.get(k, [])]
    by_분류 = {k: (cards[k][0]["title"] if cards.get(k) else None) for k in 분류_목록}

    # [불확실] — 비용/효과/되돌림/확신도가 "미확인"인 카드가 여럿이면 임의로 하나를 고르지 않는다
    uncertain = [
        c["title"] for k in 분류_목록 for c in cards.get(k, [])
        if any(str(c.get(f, "")).startswith("미확인")
               for f in ("비용", "효과", "되돌림", "확신도"))
    ]
    불확실 = uncertain[0] + " — 미확인 항목 존재" if len(uncertain) == 1 else "미확인 항목 존재"

    return {
        "값": 값, "비교대상": 비교대상, "비중": 비중, "표본": 표본,
        "조회일시": 조회일시, "titles": titles, "by_분류": by_분류,
        "불확실": 불확실,
    }


def _s1_summary(cards: dict) -> dict:
    """[발견]·[제안]·[불확실]·[근거] 4항목만으로 구성한다 — 그 이상 늘리지 않는다.

    발견.md·제안카드.md에 있는 텍스트만 옮긴다. 새 숫자·새 문장을 만들지 않고,
    없는 값은 "미확인"으로 남긴다.
    """
    f = _summary_fields(cards)

    # [발견] — target_date 관측기간 발견 1개, 분자/분모(비중) 포함
    발견_line = f"{f['값']}. 비교 대상: {f['비교대상']} ({f['비중']})."

    # [제안] — 하지 말 것 → 다시 할 것 → 할 것 순서로 제목만
    제안_line = " → ".join(f'"{t}"' for t in f["titles"]) if f["titles"] else "미확인"

    # [근거] — 조회 일시·표본·"상세는 부록" 3요소만
    근거_line = f"조회 일시: {f['조회일시']} · 표본: {f['표본']} · 상세는 부록"

    body = (
        f"[발견] {발견_line}\n"
        f"[제안] {제안_line}\n"
        f"[불확실] {f['불확실']}\n"
        f"[근거] {근거_line}"
    )
    return {"title": "1. 한 장 요약", "kind": "auto", "body": body}


def _s_group(title: str, cards: dict, 분류: str) -> dict:
    group = cards.get(분류, [])
    body = ("\n\n".join(_card_body(c) for c in group)
            if group else f"현재 '{분류}' 카드 없음.")
    return {"title": title, "kind": "auto", "body": body}


def _s_appendix(cards: dict) -> dict:
    all_cards = [c for k in 분류_목록 for c in cards.get(k, [])]
    body = "\n\n".join(_card_body(c) for c in all_cards) if all_cards else "카드 없음."
    return {"title": "7. 부록(근거 상세)", "kind": "auto", "body": body}


# ── human 절 ─────────────────────────────────────────────────────
def _human_section(title: str, human: dict, placeholder: str, hint: str) -> dict:
    return {
        "title": title, "kind": "human",
        "body": human.get(title, ""),
        "placeholder": placeholder,
        "hint": hint,
    }


def _s5_if_wrong(human: dict) -> dict:
    """"이 제안이 틀린다면" — 문서 전체에 이 절 하나만 존재한다(카드마다 반복 생성하지 않는다).

    body는 사람 입력값이 없으면 빈 문자열 그대로 둔다(자동 완성 금지).
    """
    return _human_section(
        "5. 이 제안이 틀린다면", human,
        "이 제안이 틀렸다면 무엇 때문인지, 확인하려면 무엇을 보면 되는지 적으십시오.",
        "카드의 근거·표본·관측기간 조건 중 무엇이 바뀌면 이 제안이 성립하지 않는지 "
        "담당자가 직접 판단해 적는 절입니다. 자동으로 채우지 않습니다.")


def _s6_apply(human: dict) -> dict:
    """"적용" — 판단기준.md의 최근 "오늘 실제로 내린 결정" 문장을 읽기 전용 후보로 붙이고,
    그 아래에 사람이 "다음에 무엇을 볼 것인가"를 직접 쓰게 한다.

    후보는 candidates 키에 별도로 담는다(hint와 구분) — 사람이 편집하는 body와
    섞이지 않도록, 화면에서도 candidates는 위젯 없이 읽기 전용으로만 그린다.
    """
    sec = _human_section(
        "6. 적용", human,
        "위 후보를 참고해 다음에 무엇을 볼 것인지 적으십시오.",
        "카드에는 비용·효과·되돌림이 대부분 '미확인'으로 남아 있습니다 — 이 절에서 "
        "임의로 채우지 말고, 실제 적용 여부·시점·담당은 담당자가 직접 결정해 적습니다.")
    sec["candidates"] = load_recent_decisions()
    return sec


# ── HTML 내보내기(새 6절 구조) ────────────────────────────────────
# resources/제안서_템플릿.html은 읽지도 재사용하지도 않는다 — 이 함수가
# 인쇄(A4)용 HTML을 직접 만든다. 외부 CSS/JS/이미지/CDN·웹폰트 없음.
# 색은 core.config의 기존 색만 재사용한다(강조=primary, 위험=block,
# 본문=ink, 보조=muted — 새 팔레트를 만들지 않는다).
def _esc(value) -> str:
    return html.escape(str(value), quote=False)


_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)(%p|%|건)?")


def _wrap_numbers(text: str) -> str:
    """문장·표 안의 숫자만 굵게(tabular-nums)로 감싸고 단위는 한 단계 작게 표시한다.

    새 숫자를 계산하지 않는다 — 이미 있는 텍스트 안의 숫자 표기만 스타일을 입힌다.
    """
    esc = _esc(text)

    def _sub(m: re.Match) -> str:
        num, unit = m.group(1), m.group(2) or ""
        out = f'<span class="num">{num}</span>'
        if unit:
            out += f'<span class="unit">{unit}</span>'
        return out

    return _NUM_RE.sub(_sub, esc)


def _html_style() -> str:
    """A4 인쇄 기준 CSS. core.config의 기존 색(최대 4색)만 쓴다."""
    ink, muted = C.BRAND["ink"], C.BRAND["muted"]
    primary, block = C.BRAND["primary"], C.COLORS["block"]
    mr, mg, mb = to_pdf._hex(muted)  # 머리행 옅은 배경 — 새 색이 아니라 muted의 옅은 음영
    return f"""
@page {{ size: A4; margin: 18mm 16mm; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  font-family: 'Malgun Gothic', sans-serif;
  font-size: 10.5pt; line-height: 1.7; color: {ink};
}}
.doc {{ max-width: 720px; margin: 0 auto; padding: 20px; }}
h2 {{
  font-size: 14.5pt; font-weight: 700; margin: 20px 0 4px;
  display: flex; align-items: center; gap: 10px;
  page-break-after: avoid; break-after: avoid-page;
}}
.q {{ font-size: 9.5pt; color: {muted}; margin: 0 0 8px; }}
.badge {{
  font-size: 8pt; font-weight: 700; padding: 2px 9px; border-radius: 999px;
  color: #fff; letter-spacing: .02em;
}}
.b-auto {{ background: {primary}; }}
.b-human {{ background: {block}; }}
p.body {{ margin: 6px 0 10px; }}
p.todo {{ color: {muted}; font-style: italic; }}
.num {{ font-variant-numeric: tabular-nums; font-weight: 700; }}
.unit {{ font-size: .8em; font-weight: 400; margin-left: 1px; }}
.summary-box {{
  border: 1.5px solid {primary}; border-radius: 10px;
  padding: 14px 18px; margin-bottom: 18px;
  break-inside: avoid; page-break-inside: avoid;
}}
.summary-label {{ font-size: 10pt; font-weight: 700; color: {primary}; margin-bottom: 6px; }}
.chart {{ margin: 8px 0; break-inside: avoid; page-break-inside: avoid; }}
.chart svg {{ max-width: 100%; height: auto; display: block; }}
table {{
  border-collapse: collapse; width: 100%; font-size: 9.5pt;
  margin: 8px 0 14px; break-inside: avoid; page-break-inside: avoid;
}}
th, td {{ border: none; border-bottom: 1px solid rgba({mr},{mg},{mb},.25);
  padding: 6px 8px; text-align: left; }}
th {{ background: rgba({mr},{mg},{mb},.08); font-weight: 700; }}
section.sec {{ break-inside: avoid; page-break-inside: avoid; margin-bottom: 10px; }}
"""


def _table_status(rows: list[dict]) -> str:
    body = []
    for r in rows:
        rate = r.get("전환율")
        rate_txt = f"{rate * 100:.2f}%" if rate is not None else "—"
        mark = "●" if r.get("병목여부") else ""
        도달_txt = f"{r.get('도달', 0):,}"
        body.append(
            f"<tr><td>{_esc(r.get('단계', ''))}</td>"
            f"<td>{_wrap_numbers(도달_txt)}</td>"
            f"<td>{_wrap_numbers(rate_txt)}</td>"
            f"<td>{mark}</td></tr>")
    return ("<table><thead><tr><th>단계</th><th>도달</th><th>전환율</th>"
            "<th>병목</th></tr></thead><tbody>" + "".join(body) + "</tbody></table>")


def _status_rows_text(rows: list[dict]) -> str:
    """PDF(줄글) 전용 — _table_status()와 같은 값을 텍스트로만 나열한다(새 값 없음).

    병목 표시는 HTML의 "●" 대신 "병목"이라는 낱말을 쓴다 — 내장 한글 폰트
    (Noto Sans KR)에 "●" 글리프가 없어 PDF에서 빈칸으로 보이기 때문이며,
    판정 값 자체(병목여부)는 그대로다.
    """
    lines = ["[단계별 현황] 단계 | 도달 | 전환율 | 병목"]
    for r in rows:
        rate = r.get("전환율")
        rate_txt = f"{rate * 100:.2f}%" if rate is not None else "—"
        mark = "병목" if r.get("병목여부") else ""
        lines.append(f"{r.get('단계', '')} | {r.get('도달', 0):,} | {rate_txt} | {mark}")
    return "\n".join(lines)


def _scale_trend_rows_text(표: dict) -> str:
    """PDF(줄글) 전용 — _table_scale_trend()와 같은 값을 텍스트로만 나열한다(새 값 없음)."""
    lines = []
    scale = 표.get("규모")
    if scale:
        if scale.get("실측") is not None:
            lines.append(f"실측: {_fmt_measured(scale['실측'])}")
        if scale.get("연간환산") is not None:
            lines.append(f"연간 환산: {scale['연간환산']:,}건")
        if scale.get("계산불가사유"):
            lines.append(f"규모 계산: {_display(scale['계산불가사유'])}")
    trend = 표.get("추세")
    if trend:
        listing = ", ".join(f"{r['월']} {r['값']:,}건" for r in trend)
        lines.append(f"월별 관측: {listing}")
    return "\n".join(lines)


def _table_scale_trend(표: dict) -> str:
    rows: list[tuple[str, str]] = []
    scale = 표.get("규모")
    if scale:
        if scale.get("실측") is not None:
            rows.append(("실측", _fmt_measured(scale["실측"])))
        if scale.get("연간환산") is not None:
            rows.append(("연간 환산", f"{scale['연간환산']:,}건"))
        if scale.get("계산불가사유"):
            rows.append(("규모 계산", _display(scale["계산불가사유"])))
    trend = 표.get("추세")
    if trend:
        listing = ", ".join(f"{r['월']} {r['값']:,}건" for r in trend)
        rows.append(("월별 관측", listing))
    if not rows:
        return ""
    body = "".join(f"<tr><td>{_esc(k)}</td><td>{_wrap_numbers(v)}</td></tr>" for k, v in rows)
    return f"<table><tbody>{body}</tbody></table>"


def _card_rows(cards: dict) -> list[tuple[str, str, str]]:
    """제안카드.md 카드를 (분류 표시어, 항목, 내용) 3열 행 목록으로만 뽑는다.

    분류 내부 키는 조회에만 쓰고 반환값에는 _classification_label()로 바꿔 넣는다.
    "미확인"인 필드값은 _pending_term()으로만 표시를 바꾸고 카드 원본은 그대로 둔다.
    HTML(_table_cards)·PDF(_card_rows_text) 양쪽이 이 값 하나만 서로 다른
    형식으로 그린다 — 조회·판단 로직을 두 곳에 반복해서 만들지 않는다.
    """
    rows: list[tuple[str, str, str]] = []
    for 분류 in 분류_목록:
        for c in (cards.get(분류) or []):
            분류_disp = _classification_label(분류)
            title = c.get("title", "")
            rows.append((분류_disp, "제목", _display(title)))
            # 외부 독자 지적("2027년 개선조치를 지금 확인 대상에 포함해야 하는
            # 이유")의 답은 "확인 대상"을 제안하는 카드(분류="할 것")의 기존
            # "근거" 필드에 이미 있다 — 배열 순서가 아니라 이 카드 내용으로
            # 식별해, 그 카드 하나에만 근거를 표에 노출한다(다른 카드까지
            # 전부 노출하지 않는다). 새 근거를 만들지 않고 제안카드.md에
            # 이미 있는 문자열을 표시용 변환(_display)만 거쳐 그대로 옮긴다.
            if 분류 == "할 것" and "확인 대상" in title:
                근거 = c.get("근거", "")
                if 근거:
                    rows.append((분류_disp, "근거", _display(근거)))
            for field in ("비용", "효과", "되돌림", "확신도"):
                값 = _display(_pending_term(str(c.get(field, "미확인"))))
                rows.append((분류_disp, field, 값))
    return rows


def _card_rows_text(cards: dict) -> str:
    """PDF(줄글) 전용 — _card_rows()와 같은 값을 텍스트로만 나열한다(새 값 없음)."""
    rows = _card_rows(cards)
    if not rows:
        return ""
    lines = ["[제안 카드]"] + [f"{a} · {b}: {v}" for a, b, v in rows]
    return "\n".join(lines)


def _table_cards(cards: dict) -> str:
    """제안카드.md 카드를 (분류 표시어, 항목, 내용) 3열 표로 평탄화한다."""
    rows = _card_rows(cards)
    if not rows:
        return ""
    body = "".join(
        f"<tr><td>{_esc(a)}</td><td>{_esc(b)}</td><td>{_wrap_numbers(v)}</td></tr>"
        for a, b, v in rows)
    cards_table = (f"<table><thead><tr><th>분류</th><th>항목</th><th>내용</th></tr></thead>"
                   f"<tbody>{body}</tbody></table>")
    return cards_table + _table_ops_definition(cards)


def _join_lines(lines: list[str]) -> str:
    """각 줄만 이스케이프하고 <br>로 잇는다 — 태그 자체가 다시 이스케이프되지 않게 한다."""
    return "<br>".join(_esc(line) for line in lines)


def _ops_definition_rows(cards: dict) -> list[tuple[str, list[str]]]:
    """"확인 대상/목적/주체/시점 및 후속조치/추가 자원 필요 여부" 5행의 값만 뽑는다.

    "확인 대상"을 제안하는 카드(할 것)와 "재평가" 카드(다시 할 것)의 기존
    제목·근거에서 직접 확인되는 내용만 옮긴다. 새 분석·새 숫자·새 날짜·
    담당자 실명·비용 금액·KPI 수치를 만들지 않는다 — 카드 원문이 뒷받침하지
    않는 항목은 전부 "확인 필요"로만 남긴다. HTML(_table_ops_definition)·
    PDF(_ops_definition_text) 양쪽이 이 값 하나만 서로 다른 형식으로 그린다.
    """
    확인_필요 = "확인 필요"
    카드1 = next((c for c in (cards.get("할 것") or [])
                 if "확인 대상" in c.get("title", "")), None)
    카드2_목록 = cards.get("다시 할 것") or []
    카드2 = 카드2_목록[0] if 카드2_목록 else None
    카드2_근거 = (카드2.get("근거", "") if 카드2 else "")

    # A. 확인 대상 — 카드 1 제목 그대로(새 대상·숫자 추가 없음)
    확인_대상 = [_display(카드1["title"])] if 카드1 else [확인_필요]

    # B. 확인 목적 — 카드1(확인 대상 지정)과 카드2(도래 시점 재확인)를 함께
    #    읽었을 때만 직접 확인되는 좁은 취지. 카드 원문에 없는 "조기 위험
    #    탐지"·"지연 예방"·"완료율 향상"·"성과 개선"·"독촉"·"일정 재조정" 같은
    #    말은 절대 만들지 않는다.
    if 카드1 and "도래" in 카드2_근거:
        확인_목적 = ["목표일 도래 시 완료 여부를 다시 확인하기 위한 관리 대상 지정"]
    else:
        확인_목적 = [확인_필요]

    # C. 확인 주체 — 카드 어디에도 역할 주체가 없다. 추측하지 않는다.
    확인_주체 = [확인_필요]

    # D. 확인 시점 및 후속조치 — 카드2 근거의 "도래 시점"·"다시 확인한다"
    #    취지만 재사용한다. 구체 날짜·일정표는 만들지 않는다.
    if "도래" in 카드2_근거:
        시점_후속 = ["확인 시점: 개선조치 목표일 도래 시점",
                    "후속조치: 완료 여부 재확인 및 재평가"]
    else:
        시점_후속 = [확인_필요]

    # E. 추가 자원 필요 여부 — 카드에 근거가 없으므로 Yes/No를 임의로 만들지 않는다.
    자원_여부 = [f"추가 시스템: {확인_필요}", f"외부비용: {확인_필요}", f"추가 인력: {확인_필요}"]

    return [
        ("확인 대상", 확인_대상), ("확인 목적", 확인_목적), ("확인 주체", 확인_주체),
        ("확인 시점 및 후속조치", 시점_후속), ("추가 자원 필요 여부", 자원_여부),
    ]


def _ops_definition_text(cards: dict) -> str:
    """PDF(줄글) 전용 — _ops_definition_rows()와 같은 값을 텍스트로만 나열한다(새 값 없음)."""
    op_rows = _ops_definition_rows(cards)
    lines = ["[결재 전 최소 운영 정의]"] + [f"{k}: {' / '.join(v)}" for k, v in op_rows]
    return "\n".join(lines)


def _table_ops_definition(cards: dict) -> str:
    """"제안 내용" 절에 카드 표와 별도로 작은 표 하나만 더 붙인다 — 새 절이 아니다."""
    op_rows = _ops_definition_rows(cards)
    body = "".join(f"<tr><td>{_esc(k)}</td><td>{_join_lines(v)}</td></tr>" for k, v in op_rows)
    caption = (f'<div style="font-size:10pt;font-weight:700;color:{C.BRAND["muted"]};'
               f'margin:10px 0 4px">결재 전 최소 운영 정의</div>')
    return (caption + f"<table><thead><tr><th>항목</th><th>현재 정의</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def _table_html(표) -> str:
    """표 데이터의 실제 모양(현황/규모·추세/카드)에 맞춰 평탄화한 표만 만든다.

    내부 dict key를 그대로 노출하지 않고, 표시용 변환(_display)을 그대로 재사용한다.
    """
    if isinstance(표, list) and 표 and isinstance(표[0], dict) and "단계" in 표[0]:
        return _table_status(표)
    if isinstance(표, dict) and ("규모" in 표 or "추세" in 표):
        return _table_scale_trend(표)
    if isinstance(표, dict):
        return _table_cards(표)
    return ""


def _decision_options_html(options: list[dict]) -> str:
    if not options:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(o['선택지'])}</td><td>{_esc(o['의미'])}</td></tr>"
        for o in options)
    return (f"<table><thead><tr><th>결정 선택지</th><th>의미</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def _decision_options_text(options: list[dict]) -> str:
    """PDF(줄글) 전용 — _decision_options_html()과 같은 값을 텍스트로만 나열한다."""
    if not options:
        return ""
    lines = ["[결정 선택지]"] + [f"- {o['선택지']}: {o['의미']}" for o in options]
    return "\n".join(lines)


def _pending_items_text(items: list[dict]) -> str:
    """PDF(줄글) 전용 — _pending_items_html()과 같은 값을 텍스트로만 나열한다."""
    if not items:
        return ""
    lines = ["[확인 필요 항목]"] + [
        f"- {i['무엇']} / 확인 방법: {i['확인방법']} / 확인 전에도 가능한 결정: {i['확인전결정']}"
        for i in items]
    return "\n".join(lines)


def _pending_items_html(items: list[dict]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<tr><td>{_wrap_numbers(i['무엇'])}</td><td>{_esc(i['확인방법'])}</td>"
        f"<td>{_esc(i['확인전결정'])}</td></tr>"
        for i in items)
    return (f"<table><thead><tr><th>무엇이 확인되지 않았는가</th>"
            f"<th>확인 방법</th><th>확인 전에도 가능한 결정</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def _summary_box_html(s: dict) -> str:
    문장 = (s.get("문장") or "").strip()
    if not 문장:
        return ""
    return (f'<div class="summary-box"><div class="summary-label">'
            f'{_esc(s.get("제목", ""))}</div>'
            f'<div class="summary-body">{_wrap_numbers(문장)}</div></div>')


def _section_html(s: dict) -> str:
    kind = s.get("kind")
    문장 = (s.get("문장") or "").strip()
    차트 = s.get("차트")
    표 = s.get("표")

    # 빈 자동 절은 아예 출력하지 않는다(문장·차트·표가 전부 없을 때만).
    if kind == "auto" and not 문장 and not 차트 and not 표:
        return ""

    badge_cls = "b-auto" if kind == "auto" else "b-human"
    badge_txt = C.PROPOSAL_WORDS["kind"].get(kind, kind)
    is_request = s.get("키") == "request"

    parts = [
        '<section class="sec">',
        f'<h2>{_esc(s.get("제목", ""))}<span class="badge {badge_cls}">{badge_txt}</span></h2>',
    ]
    if s.get("질문"):
        parts.append(f'<div class="q">{_esc(s["질문"])}</div>')

    if is_request:
        # 결정 요청 절의 자동 영역(A) — 규모/보류 시 규모/선택지/확인 필요는 항상
        # 사람 문장(B)보다 먼저 그린다. 마지막 실질 문장이 사람이 쓴 요청 문장이
        # 되도록, 이 블록 뒤에는 사람 문장(또는 미작성 상태) 외에 아무것도 붙이지 않는다.
        parts.append(f'<p class="body">{_wrap_numbers(_scale_info_text(s.get("규모정보") or {}))}</p>')
        if s.get("보류시규모"):
            parts.append(f'<p class="body">{_wrap_numbers(s["보류시규모"])}</p>')
        opts_html = _decision_options_html(s.get("결정선택지") or [])
        if opts_html:
            parts.append(opts_html)
        pending_html = _pending_items_html(s.get("확인필요") or [])
        if pending_html:
            parts.append(pending_html)

    if kind == "human" and not 문장:
        # 사람이 아직 안 썼다고 새 판단 문장을 만들지 않는다 — 상태만 표시.
        parts.append(f'<p class="todo">{_esc(C.PROPOSAL_WORDS["pending"]["작성 필요"])}</p>')
    elif 문장:
        parts.append(f'<p class="body">{_wrap_numbers(문장)}</p>')

    if 차트:
        # viz/proposal_charts.py는 이번 단계에서 수정하지 않는다 — 그 SVG가
        # 이미 담고 있는 캡션(예: "deficiency_id 기준")도 다른 자동 문장과
        # 똑같이 _display() 표시용 변환을 거쳐 내부 컬럼명이 그대로 보이지
        # 않게 한다(SVG 파일 자체를 고치는 것이 아니라 문자열만 바꾼다).
        parts.append(f'<div class="chart">{_display(차트)}</div>')

    if 표 is not None:
        table = _table_html(표)
        if table:
            parts.append(table)

    parts.append("</section>")
    return "".join(parts)


def to_html(secs: list[dict]) -> str:
    """제안서 6절(build() 결과)을 A4 인쇄 기준 단일 HTML 문자열로 만든다.

    resources/제안서_템플릿.html은 읽지 않는다 — 이 함수가 직접 <style>을 만든다.
    "한눈에 무엇을 알아야 합니까?" 절은 build() 결과에 실제로 있을 때만 맨 위
    요약 박스로 보여주고, 나머지 절은 build()가 돌려준 순서를 그대로 따른다.
    빈 자동 절은 출력하지 않고, human 절은 비어 있으면 "작성 필요"만 표시한다
    (새 문장·새 숫자를 만들지 않는다).
    """
    summary_html = ""
    body_secs = []
    for s in secs:
        if s.get("키") == "summary":
            summary_html = _summary_box_html(s)
            continue
        body_secs.append(s)

    section_htmls = [h for h in (_section_html(s) for s in body_secs) if h]

    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>제안서</title>\n"
        f"<style>{_html_style()}</style>\n"
        "</head>\n<body>\n"
        '<div class="doc">\n'
        + summary_html
        + "".join(section_htmls)
        + "\n</div>\n</body>\n</html>\n"
    )


# ── PDF 내보내기(새 6절 구조) ─────────────────────────────────────
# 새 PDF 엔진·디자인 패턴을 만들지 않는다 — report/to_pdf.py의 Report·build_pdf()를
# 그대로 재사용한다(기존 리포트 PDF와 같은 표지·목차·본문 렌더링). 이 파일이
# 하는 일은 새 6절 구조(제목/질문/kind/문장/차트/표)를 to_pdf.build_pdf()가
# 원래 기대하는 옛 모양(title/kind/body/placeholder/charts)으로 값만 옮기는
# 것뿐이다 — 여기서 새 문장·새 숫자·새 판단을 만들지 않는다.
#
# 차트(SVG)는 이미지로 넣지 않는다: 이 프로젝트 SVG는 반응형 크기
# (width="100%" height="auto")와 한글 <text>를 쓰는데, fpdf2 내장 SVG
# 렌더러는 퍼센트/auto 길이를 파싱하지 못하고(ValueError) 한글 텍스트에서도
# 폰트를 찾지 못해(KeyError) 그대로는 임베드할 수 없다 — viz/proposal_charts.py는
# 이번 작업에서 수정하지 않으므로, 차트를 그리는 대신 그 차트가 근거로 삼는
# 표(단계별 현황·규모/추세)를 HTML과 같은 값으로 줄글로 옮긴다.
def _pdf_sections(secs: list[dict]) -> list[dict]:
    """새 6절 구조를 to_pdf.build_pdf()가 기대하는 옛 모양으로 변환한다.

    to_html()의 _section_html()과 같은 순서 규칙을 따른다 — "결정 요청" 절은
    자동 영역(규모/보류 시 규모/선택지/확인 필요)을 먼저 쓰고 사람 문장(또는
    미작성 상태)을 마지막 문단으로 둔다. 사람이 안 쓴 human 절은 문장을
    만들어 채우지 않는다: "위험" 절처럼 표·자동 정보가 없는 human 절은 본문을
    비워 to_pdf.py의 기존 "[작성되지 않음] {placeholder}" 처리를 그대로 쓴다.
    """
    out = []
    for s in secs:
        kind = s.get("kind")
        키 = s.get("키")
        문장 = (s.get("문장") or "").strip()
        표 = s.get("표")
        parts: list[str] = []

        if 키 == "request":
            parts.append(_scale_info_text(s.get("규모정보") or {}))
            if s.get("보류시규모"):
                parts.append(s["보류시규모"])
            opts_text = _decision_options_text(s.get("결정선택지") or [])
            if opts_text:
                parts.append(opts_text)
            pending_text = _pending_items_text(s.get("확인필요") or [])
            if pending_text:
                parts.append(pending_text)
            parts.append(문장 if 문장 else C.PROPOSAL_WORDS["pending"]["작성 필요"])
        elif 문장:
            parts.append(문장)

        if 표 is not None:
            if isinstance(표, list) and 표 and isinstance(표[0], dict) and "단계" in 표[0]:
                parts.append(_status_rows_text(표))
            elif isinstance(표, dict) and ("규모" in 표 or "추세" in 표):
                parts.append(_scale_trend_rows_text(표))
            elif isinstance(표, dict):
                parts.append(_card_rows_text(표))
                parts.append(_ops_definition_text(표))

        body = "\n\n".join(p for p in parts if p)
        out.append({
            "title": s.get("제목", ""), "kind": kind, "body": body,
            "placeholder": s.get("질문", ""), "charts": [],
        })
    return out


def build_pdf(secs: list[dict]) -> bytes:
    """제안서 PDF — report.to_pdf.build_pdf()를 그대로 재사용한다(새 PDF 엔진 없음).

    _pdf_sections()로 값만 옛 모양으로 옮겨서 넘긴다 — secs 순서 그대로 유지하고
    카드/근거에 없는 값을 새로 만들지 않는다.
    """
    patched = _pdf_sections(secs)
    return to_pdf.build_pdf(patched, {}, title="제안서")


# ── 검사(재사용) ──────────────────────────────────────────────────
def check_all(sections: list[dict]) -> dict[str, list[str]]:
    """조립된 절 본문에 인과 표현이 섞였는지 확인한다.

    새 문장검사 로직을 만들지 않고 report.sections.check_phrasing()을 그대로 재사용한다.
    옛 절 모양("title"/"body")과 새 절 모양("제목"/"문장")을 둘 다 받는다 —
    build_pdf()·to_html() 쪽(옛 모양)과 새 build()(새 모양) 양쪽에서 재사용하기 위함이다.
    """
    hits = {}
    for s in sections:
        text = s.get("문장") if "문장" in s else s.get("body")
        found = check_phrasing(text or "")
        if found:
            key = s.get("제목", s.get("title"))
            hits[key] = found
    return hits


# ══════════════════════════════════════════════════════════════════
# ── 새 6절 구조 조립 (CLAUDE.md "제안서 절 구조 기준표") ─────────────
# ══════════════════════════════════════════════════════════════════
# 절 제목/질문·표시 용어는 core.config.PROPOSAL_WORDS 한 곳에서만 관리한다
# (코드 여러 곳에 반복해서 박지 않는다). 내부 키(아래 "키"·kind, 분류_목록의
# "하지 말 것"/"다시 할 것"/"할 것")는 여기서 바꾸지 않는다 — build()의
# 계산·조회는 이 내부 키로 그대로 하고, 화면/문서에 보일 때만
# PROPOSAL_WORDS를 거친다.
_SECTION_KIND: list[tuple[str, str]] = [
    ("summary", "auto"), ("status", "auto"), ("scale_trend", "auto"),
    ("proposal", "auto"), ("risk", "human"), ("request", "human"),
]
SECTION_SPECS: list[dict] = [
    {"키": key, "제목": C.PROPOSAL_WORDS["sections"][key]["title"],
     "질문": C.PROPOSAL_WORDS["sections"][key]["question"], "kind": kind}
    for key, kind in _SECTION_KIND
]


def _spec(key: str) -> dict:
    return next(s for s in SECTION_SPECS if s["키"] == key)


def _classification_label(분류: str) -> str:
    """제안카드.md의 내부 분류 키는 그대로 두고, 표시할 때만 명사형으로 바꾼다."""
    return C.PROPOSAL_WORDS["classification"].get(분류, 분류)


def _status_term(key: str) -> str:
    """판정/상태 라벨의 표시용 변환. core/metrics.py의 판정 로직·반환값은 바꾸지 않는다."""
    return C.PROPOSAL_WORDS["status_terms"].get(key, key)


def _pending_term(text: str) -> str:
    """"미확인"으로 시작하는 카드 값을 표시용 문구로 바꾼다. 원본 카드 값은 바꾸지 않는다."""
    term = C.PROPOSAL_WORDS["pending"]["미확인"]
    if text.startswith("미확인"):
        rest = text[len("미확인"):].strip()
        return f"{term}{(' ' + rest) if rest else ''}"
    return text


def _display(text: str) -> str:
    """자동 문장에서 내부 코드 용어를 한국어 표시어로 바꾼다(값 변경이 아니라 표시 변환)."""
    if not text:
        return text
    for k, v in C.PROPOSAL_WORDS["display_terms"].items():
        text = text.replace(k, v)
    return text


_DECISION_VERBS = ("승인", "결정", "판단")


def has_decision_verb(text: str) -> bool:
    """"결정 요청" 사람 입력에 결정 동사(승인/결정/판단) 중 하나가 있는지만 확인한다.

    report.sections.check_phrasing()·BANNED와는 별개의 검사다 — 자동 절 문장검사에는
    섞지 않고, 저장을 막지 않으며 경고 표시 여부 판단에만 쓴다.
    """
    return any(v in (text or "") for v in _DECISION_VERBS)


def _fmt_measured(v) -> str:
    """규모["실측"]은 topic 종류에 따라 int(손실 건수)이거나 dict({"2025":30,...})다.
    새 계산 없이 있는 그대로 문자열로만 나열한다.
    """
    if isinstance(v, dict):
        return ", ".join(f"{k} {vv:,}건" for k, vv in v.items())
    if isinstance(v, (int, float)):
        return f"{v:,}건"
    return str(v)


# ── 절별 문장 생성 (절 하나당 최대 3문장) ────────────────────────────
def _sentences_status(status: dict, topic: dict | None) -> list[str]:
    """2번 절 — 1문장(관측: 분모 중 결과값) + 2문장(비교: 실제 근거가 있을 때만).

    비교 격차는 새로 계산하지 않고 topic["격차_pp"](core/metrics.py가 이미
    계산해 둔 값)가 있을 때만 쓴다 — 없으면 비교 문장을 만들지 않는다.
    """
    rows = status.get("값") if status else None
    if not rows:
        return []
    idx = next((i for i, r in enumerate(rows) if r.get("병목여부")), None)
    if idx is None:
        return []
    b = rows[idx]
    prev = rows[idx - 1] if idx > 0 else None
    out: list[str] = []

    if prev is not None:
        s1 = f"{prev['단계']} {prev['도달']:,}건 중 {b['단계']} {b['도달']:,}건"
        if b.get("전환율") is not None:
            s1 += f"({b['전환율'] * 100:.2f}%)"
        s1 += "으로 전환율이 가장 낮다."
        out.append(s1)

    gap_pp = (topic or {}).get("격차_pp")
    if prev is not None and gap_pp is not None and prev.get("전환율") is not None:
        out.append(f"{prev['단계']} 구간({prev['전환율'] * 100:.2f}%)보다 "
                   f"{gap_pp:.2f}%p 낮다.")

    return out[:3]


def _sentences_scale_trend(scale: dict | None, trend: dict | None) -> list[str]:
    """3번 절 — 실측/연간환산/가정을 분리하고, 연간환산이 없으면 추세(관측 차이)만 쓴다.

    실측과 환산을 한 문장에 섞지 않는다. 값이 없는 부분은 문장을 만들지 않는다.
    """
    out: list[str] = []
    if scale:
        if scale.get("실측") is not None:
            out.append(f"실측값은 {_fmt_measured(scale['실측'])}이다.")
        if scale.get("연간환산") is not None:
            가정 = [_display(a) for a in (scale.get("가정") or [])]
            tail = f"({'; '.join(가정)})" if 가정 else ""
            out.append(f"연간 환산 규모는 {scale['연간환산']:,}건이다{tail}.")
    if trend and trend.get("값"):
        listing = ", ".join(f"{r['월']} {r['값']:,}건" for r in trend["값"])
        out.append(f"실제 관측된 달은 {listing}이다.")
    return out[:3]


def _sentences_proposal(cards: dict) -> list[str]:
    """4번 절 — 분류별 카드 제목 하나씩(최대 3개). 표시용 용어 변환만 적용한다.

    분류 내부 키("하지 말 것" 등)는 그대로 조회하고, 문장에 보일 때만
    _classification_label()로 바꾼다(내부 키 자체는 바꾸지 않는다).
    """
    out = []
    for 분류 in 분류_목록:
        group = cards.get(분류) or []
        if group:
            out.append(f"{_classification_label(분류)}: {_display(group[0]['title'])}")
    return out[:3]


def _section_human(key: str, human: dict) -> dict:
    """5번 절(위험·철회 기준) — 항상 만든다. 사람이 안 썼으면 빈 문자열 그대로 둔다(자동 완성 금지)."""
    spec = _spec(key)
    return {**spec, "문장": human.get(spec["제목"], ""), "차트": None, "표": None}


# ── 6번 절(결정 요청) 전용 — 자동 영역(A) + 사람 문장(B) ────────────────
def _decision_options() -> list[dict]:
    """승인/조건부 승인/보류 3개 선택지. 예산·담당자·일정 등 없는 값은 만들지 않고
    선택의 취지만 한 줄로 고정해 둔다(카드/근거에 따라 달라지지 않는 구조적 설명).
    """
    return [
        {"선택지": "승인", "의미": "현재 근거와 조건으로 제안을 진행하는 선택입니다."},
        {"선택지": "조건부 승인", "의미": "추가 확인 조건을 두고 진행 여부를 결정하는 선택입니다."},
        {"선택지": "보류", "의미": "추가 근거가 확보될 때까지 결정을 미루는 선택입니다."},
    ]


def _request_scale(topic: dict | None, evidence: dict | None) -> dict:
    """topic["규모_연간건수"]가 있으면 그 값을, 없으면 evidence["규모"]["계산불가사유"]만
    그대로 옮긴다 — 새 규모 계산을 하지 않는다.
    """
    규모_연간 = (topic or {}).get("규모_연간건수")
    if 규모_연간 is not None:
        return {"연간환산": 규모_연간, "계산불가사유": None}
    scale_evi = (evidence or {}).get("규모") or {}
    사유 = scale_evi.get("계산불가사유")
    return {"연간환산": None, "계산불가사유": _display(사유) if 사유 else None}


def _defer_scale(규모정보: dict) -> str | None:
    """규모_연간건수가 있을 때만, 그 값을 그대로 재사용해 "1년 미룰 경우" 문장을 만든다.

    새 계산 기준을 만들지 않는다 — 연간 환산 가정 자체가 이미 "연 단위로 균등하게
    쌓인다"는 가정이므로, 1년을 더 미루면 같은 연간환산값만큼 더 쌓인다고 재사용한다.
    실측처럼 단정하지 않도록 "동일한 환산 가정"·"환산값"을 문장에 명시한다.
    """
    연간 = 규모정보.get("연간환산")
    if 연간 is None:
        return None
    return (f"결정을 1년 미룰 경우 동일한 환산 가정에서는 약 {연간:,.1f}건이 "
            f"추가로 누적될 수 있습니다(환산값이며 실측이 아닙니다).")


def _scale_info_text(규모정보: dict) -> str:
    연간 = 규모정보.get("연간환산")
    if 연간 is not None:
        return f"규모: 연 {연간:,.1f}건(환산값)."
    label = C.PROPOSAL_WORDS["status_terms"]["규모 산정 불가"]
    사유 = 규모정보.get("계산불가사유")
    return f"규모: {label}" + (f" — {사유}" if 사유 else "") + "."


def _pending_items(cards: dict) -> list[dict]:
    """카드 필드 중 "미확인"으로 남은 항목을 확인 필요 3요소로 구조화한다.

    확인 주체·기한·구체적 확인 절차는 카드/근거 어디에도 없으므로 지어내지 않고
    "확인 필요" 상태만 남긴다. "확인 전에도 가능한 결정"은 항상 존재하는 구조적
    선택지(조건부 승인)를 가리킬 뿐, 카드마다 새 사실을 만들지 않는다.
    """
    items: list[dict] = []
    for 분류 in 분류_목록:
        for c in (cards.get(분류) or []):
            for field in ("비용", "효과", "되돌림", "확신도"):
                raw = str(c.get(field, "미확인"))
                if raw.startswith("미확인"):
                    items.append({
                        "무엇": f"{_classification_label(분류)} · {_display(c.get('title', ''))} "
                                f"· {field}: {_pending_term(raw)}",
                        "확인방법": "확인 필요",
                        "확인전결정": "조건부 승인으로 조건을 지정해 진행 여부를 결정할 수 있습니다.",
                    })
    return items


def _section_request(topic: dict | None, evidence: dict | None, cards: dict, human: dict) -> dict:
    """6번 절(결정 요청) — 자동 영역(규모/선택지/확인 필요)과 사람 문장을 함께 담는다.

    "문장"은 오직 사람이 쓴 값만 들어간다(자동 생성 금지) — 그 외 보조 키
    (결정선택지/규모정보/보류시규모/확인필요)는 화면·HTML이 자동 영역을 사람 문장과
    구분해서 그리는 데만 쓴다.
    """
    spec = _spec("request")
    규모정보 = _request_scale(topic, evidence)
    return {
        **spec,
        "문장": human.get(spec["제목"], ""),
        "차트": None,
        "표": None,
        "결정선택지": _decision_options(),
        "규모정보": 규모정보,
        "보류시규모": _defer_scale(규모정보),
        "확인필요": _pending_items(cards),
    }


def build(topic: dict, evidence: dict, cards: dict, human: dict | None = None) -> list[dict]:
    """CLAUDE.md "제안서 절 구조 기준표"의 6절을 조립한다(자동 4 + 사람 2).

    근거(evidence/cards)가 없는 자동 절은 아예 만들지 않는다 — 빈 자동 절을
    남겨 두지 않는다. 사람 절(위험·철회 기준 / 요청) 2개는 항상 만들되
    자동으로 문장을 채우지 않는다. 절 순서(요약→현황→규모/추세→제안→
    위험→요청)는 바꾸지 않는다. 자동 절은 절당 최대 3문장으로 제한한다.
    """
    human = human or {}
    evidence = evidence or {}
    cards = cards or {}

    status_evi = evidence.get("현황") or {}
    scale = evidence.get("규모")
    trend = evidence.get("추세")

    status_sents = _sentences_status(status_evi, topic)
    scale_trend_sents = _sentences_scale_trend(scale, trend)
    proposal_sents = _sentences_proposal(cards)

    auto_sections = []
    if status_sents:
        spec = _spec("status")
        auto_sections.append({**spec, "문장": " ".join(status_sents),
                              "차트": funnel_svg(status_evi),
                              "표": status_evi.get("값")})
    if scale_trend_sents:
        spec = _spec("scale_trend")
        차트 = trend_svg(trend) if trend and trend.get("값") else None
        표: dict = {}
        if scale:
            표["규모"] = scale
        if trend and trend.get("값"):
            표["추세"] = trend["값"]
        auto_sections.append({**spec, "문장": " ".join(scale_trend_sents),
                              "차트": 차트, "표": 표 or None})
    if proposal_sents:
        spec = _spec("proposal")
        auto_sections.append({**spec, "문장": " ".join(proposal_sents),
                              "차트": None, "표": cards})

    # 1번 절 — 2~4번 각 절의 첫 문장만 압축한다(핵심 관측 / 규모 또는 추세 / 제안).
    # 새 사실을 추가하지 않고 이미 만든 문장 중 첫 문장만 재사용한다.
    summary_parts = [s[0] for s in (status_sents, scale_trend_sents, proposal_sents) if s][:3]

    sections = []
    if summary_parts:
        spec = _spec("summary")
        sections.append({**spec, "문장": " ".join(summary_parts),
                         "차트": None, "표": None})
    sections.extend(auto_sections)
    sections.append(_section_human("risk", human))
    sections.append(_section_request(topic, evidence, cards, human))
    return sections
