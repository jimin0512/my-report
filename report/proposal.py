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

TEMPLATE_PATH = C.ROOT / "resources" / "제안서_템플릿.html"

CARD_FIELDS = ["분류", "근거", "비용", "효과", "되돌림", "확신도"]
분류_목록 = ["하지 말 것", "다시 할 것", "할 것"]

# ★ 절 순서와 auto/human 구분은 고정이다. 바꾸지 않는다.
SECTION_ORDER = [
    "1. 한 장 요약",
    "2. 하지 말 것",
    "3. 다시 할 것",
    "4. 할 것",
    "5. 이 제안이 틀린다면",
    "6. 적용",
    "7. 부록(근거 상세)",
]
HUMAN_TITLES = {"5. 이 제안이 틀린다면", "6. 적용"}


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


# ── HTML 내보내기 ─────────────────────────────────────────────────
# resources/제안서_템플릿.html 의 구조·CSS·class 이름을 그대로 재사용한다.
# 외부 CSS/JS/이미지/CDN은 추가하지 않는다 — 템플릿의 <style>을 그대로 복사해 쓴다.
CARD_CLASS = {"하지 말 것": "stop", "다시 할 것": "redo", "할 것": "go"}
CARD_MARK = {"하지 말 것": "① 하지 말 것", "다시 할 것": "② 다시 할 것", "할 것": "③ 할 것"}
SUMMARY_PROP_ROWS = [
    ("하지 말 것", "b-block", "✕ 하지 말 것", "①"),
    ("다시 할 것", "b-warn", "▲ 다시 할 것", "②"),
    ("할 것", "b-ok", "● 할 것", "③"),
]


def _load_template(path: str | Path | None = None) -> str:
    """resources/제안서_템플릿.html을 읽는다(수정하지 않는다)."""
    p = Path(path) if path else TEMPLATE_PATH
    return p.read_text(encoding="utf-8")


def _extract_style(template_html: str) -> str:
    """템플릿의 <style>...</style> 내부를 그대로(주석 포함) 꺼낸다. 한 글자도 바꾸지 않는다."""
    m = re.search(r"<style>(.*?)</style>", template_html, flags=re.DOTALL)
    return m.group(1) if m else ""


def _esc(value) -> str:
    return html.escape(str(value), quote=False)


def _wrap_num(text: str) -> str:
    """숫자(분자/분모 포함)가 있으면 template의 .num 클래스를 붙인다. 새 비율은 계산하지 않는다."""
    esc = _esc(text)
    return f'<span class="num">{esc}</span>' if re.search(r"\d", str(text)) else esc


def _wrap_value(value) -> str:
    """카드 필드 값 하나를 HTML로. "미확인"이면 template의 .unknown 클래스를 쓴다."""
    text = str(value)
    if text.startswith("미확인"):
        rest = text[len("미확인"):].strip()
        tail = f" {_wrap_num(rest)}" if rest else ""
        return f'<span class="unknown">미확인</span>{tail}'
    return _wrap_num(text)


def _prop_card_html(card: dict, 분류: str) -> str:
    """template의 .prop.stop/.redo/.go + <dl> 구조를 그대로 써서 카드 하나를 그린다."""
    cls = CARD_CLASS.get(분류, "")
    mark = CARD_MARK.get(분류, 분류)
    title = card.get("title", "(제목 없음)")
    rows = "".join(
        f"<dt>{_esc(field)}</dt><dd>{_wrap_value(card.get(field, '미확인'))}</dd>"
        for field in ("근거", "비용", "효과", "되돌림", "확신도")
    )
    return (
        f'<div class="prop {cls}">'
        f'<div class="cls">{_esc(mark)}</div>'
        f'<h4>{_esc(title)}</h4>'
        f'<dl>{rows}</dl>'
        f'</div>'
    )


def _group_html(cards: dict, 분류: str, no: str) -> str:
    group = cards.get(분류, [])
    body = ("".join(_prop_card_html(c, 분류) for c in group)
            if group else f"<p class=\"small\">현재 '{_esc(분류)}' 카드 없음.</p>")
    return f'<h2 class="sec"><span class="no">{no}</span>{_esc(분류)}</h2>{body}'


def _summary_html(cards: dict) -> str:
    """template의 .summary 블록 — 항목 4개(발견/제안/불확실/근거)만 유지한다."""
    f = _summary_fields(cards)

    발견_html = (f'{_wrap_num(f["값"])}. 비교 대상: {_wrap_num(f["비교대상"])} '
                f'({_wrap_num(f["비중"])})')

    prop_items = []
    for 분류, badge_cls, badge_txt, n in SUMMARY_PROP_ROWS:
        title = f["by_분류"].get(분류)
        title_html = _esc(title) if title else '<span class="todo">[ 카드 없음 ]</span>'
        prop_items.append(
            f'<li><span class="n">{n}</span><span>'
            f'<span class="badge {badge_cls}">{badge_txt}</span> {title_html}</span></li>')
    제안_html = '<ul class="plist">' + "".join(prop_items) + '</ul>'

    불확실_html = _esc(f["불확실"])
    근거_html = (f'조회 일시: {_wrap_num(f["조회일시"])} · 표본: {_wrap_num(f["표본"])} '
                '· 상세는 부록 A')

    return (
        '<div class="summary"><h2>한 장 요약</h2>'
        f'<div class="srow"><div class="k">발견</div>'
        f'<div class="v"><div class="lead">{발견_html}</div></div></div>'
        f'<div class="srow"><div class="k">제안</div><div class="v">{제안_html}</div></div>'
        f'<div class="srow"><div class="k">불확실</div><div class="v">{불확실_html}</div></div>'
        f'<div class="srow"><div class="k">근거</div>'
        f'<div class="v small">{근거_html}</div></div>'
        '</div>'
    )


def _human_body_html(sec: dict) -> str:
    """사람 입력값이 있으면 그대로, 비어 있으면 template의 .todo로 빈 자리임을 표시한다.

    자동으로 문장을 채우지 않는다.
    """
    body = (sec.get("body") or "").strip()
    if not body:
        return '<p class="todo">[ 아직 작성되지 않았습니다 ]</p>'
    return "<p>" + _esc(body).replace("\n", "<br>") + "</p>"


def _apply_html(sec: dict) -> str:
    """"적용" 절 — 판단기준.md 후보(읽기 전용)와 사람이 쓴 body를 별도 영역으로 나눈다."""
    candidates = sec.get("candidates") or []
    if candidates:
        cand_html = ('<ul class="plist">' + "".join(
            f'<li><span class="n">·</span><span>{_esc(c)}</span></li>'
            for c in candidates) + '</ul>')
    else:
        cand_html = '<p class="small">판단기준.md에서 후보를 찾지 못했습니다.</p>'
    return (
        '<h3>판단기준.md 최근 결정(읽기 전용, 편집 불가)</h3>' + cand_html +
        '<h3>담당자 작성</h3>' + _human_body_html(sec)
    )


def to_html(secs: list[dict]) -> str:
    """제안서 절 7개를 resources/제안서_템플릿.html의 구조·CSS로 단일 HTML 문자열로 만든다.

    외부 CSS/JS/이미지/CDN을 추가하지 않는다(템플릿의 <style>을 그대로 복사).
    카드/발견/판단기준에 없는 값은 만들지 않고 "미확인"·읽기 전용 상태 그대로 옮긴다.
    본문 순서: 한 장 요약 → 하지 말 것 → 다시 할 것 → 할 것 →
              이 제안이 틀린다면 → 적용 → 부록(근거 상세) — secs의 순서를 그대로 따른다.
    """
    style = _extract_style(_load_template())
    cards = load_cards()
    by_title = {s["title"]: s for s in secs}

    body_parts = [
        '<div class="cover"><div class="kicker">성과 개선 제안(임시)</div>'
        '<h1><span class="todo">[ 제안 한 줄 — 카드 3장(하지 말 것·다시 할 것·할 것)의 '
        '상세는 아래를 참고 ]</span></h1></div>',
        _summary_html(cards),
        _group_html(cards, "하지 말 것", "1"),
        _group_html(cards, "다시 할 것", "2"),
        _group_html(cards, "할 것", "3"),
        '<h2 class="sec"><span class="no">4</span>이 제안이 틀린다면</h2>'
        + _human_body_html(by_title.get("5. 이 제안이 틀린다면", {})),
        '<h2 class="sec"><span class="no">5</span>적용</h2>'
        + _apply_html(by_title.get("6. 적용", {})),
    ]

    appendix_cards = "".join(
        _prop_card_html(c, 분류) for 분류 in 분류_목록 for c in cards.get(분류, []))
    body_parts.append(
        '<div class="appendix"><h2 class="sec">부록 A · 근거 상세</h2>'
        + (appendix_cards if appendix_cards else '<p class="small">카드 없음.</p>')
        + '</div>')

    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>제안서(임시)</title>\n"
        f"<style>{style}</style>\n"
        "</head>\n<body>\n"
        f'<div class="page">\n{"".join(body_parts)}\n</div>\n'
        "</body>\n</html>\n"
    )


# ── PDF 내보내기 ──────────────────────────────────────────────────
# 새 PDF 엔진·디자인 패턴을 만들지 않는다 — report/to_pdf.py의 Report·build_pdf()를
# 그대로 재사용한다(기존 리포트 PDF와 같은 표지·목차·본문 렌더링).
def _apply_pdf_body(sec: dict) -> str:
    """"적용" 절의 PDF 본문 — 판단기준.md 후보(읽기 전용)와 사람이 쓴 body를
    하나의 텍스트로 합친다.

    to_pdf.build_pdf()는 title/body만 보고 페이지를 그리므로, 새 그리기 코드
    없이 candidates를 본문 텍스트 안에 그대로 적어 넣어 기존 렌더링을 그대로 쓴다.
    human body가 비어 있으면 사람이 쓴 것처럼 채우지 않고 placeholder를 그대로 남긴다.
    """
    candidates = sec.get("candidates") or []
    cand_text = ("판단기준.md 최근 결정(읽기 전용, 편집 불가):\n"
                 + "\n".join(f"- {c}" for c in candidates)) if candidates else \
        "판단기준.md에서 후보를 찾지 못했습니다."
    human_body = (sec.get("body") or "").strip()
    human_text = human_body if human_body else f"[작성되지 않음] {sec.get('placeholder', '')}"
    return f"{cand_text}\n\n담당자 작성:\n{human_text}"


def build_pdf(secs: list[dict]) -> bytes:
    """제안서 PDF — report.to_pdf.build_pdf()를 그대로 호출한다(secs 순서 그대로 유지).

    "6. 적용"만 candidates를 본문 텍스트에 옮겨 담고, 나머지 6개 절은 secs의
    title/body/placeholder를 손대지 않고 그대로 넘긴다 — 카드에 없는 값을
    새로 만들지 않는다.
    """
    patched = []
    for s in secs:
        s = dict(s)
        if s["title"] == "6. 적용":
            s["body"] = _apply_pdf_body(s)
        patched.append(s)
    return to_pdf.build_pdf(patched, {}, title="제안서(임시)")


# ── 검사(재사용) ──────────────────────────────────────────────────
def check_all(sections: list[dict]) -> dict[str, list[str]]:
    """조립된 절 본문에 인과 표현이 섞였는지 확인한다.

    새 문장검사 로직을 만들지 않고 report.sections.check_phrasing()을 그대로 재사용한다.
    """
    hits = {}
    for s in sections:
        found = check_phrasing(s.get("body") or "")
        if found:
            hits[s["title"]] = found
    return hits


# ── 조립 ──────────────────────────────────────────────────────────
def build(cards: dict, human: dict | None = None) -> list[dict]:
    """제안카드.md 기반 절 7개를 고정 순서로 조립한다.

    순서와 auto/human 구분은 바꾸지 않는다(report.sections.build()와 같은 원칙).
    """
    human = human or {}
    sections = [
        _s1_summary(cards),
        _s_group("2. 하지 말 것", cards, "하지 말 것"),
        _s_group("3. 다시 할 것", cards, "다시 할 것"),
        _s_group("4. 할 것", cards, "할 것"),
        _s5_if_wrong(human),
        _s6_apply(human),
        _s_appendix(cards),
    ]
    assert [s["title"] for s in sections] == SECTION_ORDER
    assert all(s["kind"] == ("human" if s["title"] in HUMAN_TITLES else "auto")
               for s in sections)
    return sections
