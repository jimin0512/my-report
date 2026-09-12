# -*- coding: utf-8 -*-
"""제안서 경영진용 PDF — A4 가로(7페이지), 임원 결재 프레젠테이션 형태.

새 PDF 엔진을 만들지 않는다: report/to_pdf.py의 Report(폰트 로딩·페이지 설정)를
그대로 상속해 방향만 가로로 바꾸고, 이 파일은 "그 위에 무엇을 그릴지"만 담당한다.

이 파일이 절대 하지 않는 것:
- 새 숫자·비용·효과·KPI·담당자·일정을 만들지 않는다.
- core/metrics.py를 다시 호출하거나 값을 재계산하지 않는다 — report/proposal.py의
  build() 결과(secs)와 load_cards() 결과(cards)에 이미 있는 값만 다른 배치로 그린다.
- 인과를 단정하는 문장을 새로 쓰지 않는다.

절 순서(요약→현황→규모/추세→제안→위험→요청)의 "내용"은 그대로 유지하되, 인쇄
페이지 배치만 경영 제안서 스토리라인(표지·요약·문제구조·해석·제안·운영안·결정)으로
재구성한다.
"""
from __future__ import annotations

from core import config as C
from report import to_pdf

INK = to_pdf.INK
MUTED = to_pdf.MUTED
LINE = to_pdf.LINE
확인_필요 = "확인 필요"


def _tint(hex_color: str, factor: float) -> tuple[int, int, int]:
    """core.config 색을 흰색 쪽으로만 옅게 섞는다 — 새 팔레트를 만들지 않는다."""
    r, g, b = to_pdf._hex(hex_color)
    return (int(r + (255 - r) * factor), int(g + (255 - g) * factor),
            int(b + (255 - b) * factor))


PRIMARY = C.BRAND["primary"]
WARN = C.COLORS["warn"]
BLOCK = C.COLORS["block"]
BG = C.BRAND["bg"]


class _ExecReport(to_pdf.Report):
    """A4 가로 + 상단 얇은 블루 라인·좌측 카테고리·우측 하단 페이지 번호.

    표지(1페이지)에는 헤더/푸터를 그리지 않는다(기존 Report와 같은 관례).
    """

    def __init__(self):
        super().__init__(orientation="L")
        self.category = ""
        self.total_pages = 7

    def header(self):
        if self.page_no() == 1:
            return
        r, g, b = to_pdf._hex(PRIMARY)
        self.set_draw_color(r, g, b)
        self.set_line_width(1.0)
        self.line(self.l_margin, 12, self.w - self.r_margin, 12)
        self.set_xy(self.l_margin, 15)
        self.set_font(self.base, "", 8.5)
        self.set_text_color(*MUTED)
        self.cell(0, 5, self.category, align="L")

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_font(self.base, "", 8.5)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"{self.page_no()} / {self.total_pages}", align="R")


# ── 그리기 도구 ───────────────────────────────────────────────────
def _box(pdf, x, y, w, h, fill=None, draw=LINE, width=0.3):
    if fill is not None:
        r, g, b = fill
        pdf.set_fill_color(r, g, b)
    r2, g2, b2 = draw
    pdf.set_draw_color(r2, g2, b2)
    pdf.set_line_width(width)
    pdf.rect(x, y, w, h, style="DF" if fill is not None else "D")


def _text(pdf, x, y, w, text, size, color, bold=False, align="L", line_h=None):
    pdf.set_xy(x, y)
    pdf.set_font(pdf.base, "B" if bold else "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(w, line_h or size * 0.5, text, align=align)


def _arrow_right(pdf, x, y, length, color=PRIMARY):
    r, g, b = to_pdf._hex(color)
    pdf.set_draw_color(r, g, b)
    pdf.set_line_width(0.7)
    pdf.line(x, y, x + length, y)
    pdf.line(x + length, y, x + length - 2.4, y - 1.8)
    pdf.line(x + length, y, x + length - 2.4, y + 1.8)


def _arrow_down(pdf, x, y, length, color=PRIMARY):
    r, g, b = to_pdf._hex(color)
    pdf.set_draw_color(r, g, b)
    pdf.set_line_width(0.7)
    pdf.line(x, y, x, y + length)
    pdf.line(x, y + length, x - 1.8, y + length - 2.4)
    pdf.line(x, y + length, x + 1.8, y + length - 2.4)


def _kpi_card(pdf, x, y, w, h, label, value, color=PRIMARY, note=""):
    _box(pdf, x, y, w, h, fill=_tint(C.BRAND["line"], 0.5))
    _text(pdf, x + 6, y + 6, w - 12, label, 10.5, MUTED, bold=True)
    r, g, b = to_pdf._hex(color)
    _text(pdf, x + 6, y + h * 0.32, w - 12, value, 30, (r, g, b), bold=True)
    if note:
        _text(pdf, x + 6, y + h - 12, w - 12, note, 8, MUTED)


def _confirm_cards(pdf, x, y, w, items: list[tuple[str, str]], title="확인이 필요한 사항"):
    """"확인이 필요한 사항" 4칸 카드 — report.proposal.confirm_items()가 이미
    계산한 (항목, 상태) 목록만 그린다. 값을 임의로 만들지 않는다.
    """
    _text(pdf, x, y, w, title, 11, INK, bold=True)
    n = len(items) or 1
    gap = 5
    card_w = (w - gap * (n - 1)) / n
    cy = y + 9
    ch = 22
    for i, (label, val) in enumerate(items):
        cx = x + i * (card_w + gap)
        _box(pdf, cx, cy, card_w, ch, fill=(255, 255, 255))
        _text(pdf, cx + 4, cy + 4, card_w - 8, label, 9, MUTED, bold=True)
        _text(pdf, cx + 4, cy + 12, card_w - 8, val, 10, INK, bold=True)


def _status_lookup(rows: list[dict] | None) -> dict[str, dict]:
    return {r.get("단계"): r for r in (rows or [])}


# ── 각 페이지 ─────────────────────────────────────────────────────
def _page_cover(pdf: _ExecReport, topic: dict | None):
    pdf.add_page()
    kicker = C.DATASET
    _text(pdf, 20, 34, 180, kicker, 10.5, MUTED, bold=True)
    _text(pdf, 20, 54, 220, "내부회계 개선조치 관리 강화 제안", 30, INK, bold=True, line_h=13)
    _text(pdf, 20, 92, 220, "개선조치 착수 이후 완료 단계의 관리 공백 해소", 14, MUTED)
    r, g, b = to_pdf._hex(PRIMARY)
    pdf.set_draw_color(r, g, b)
    pdf.set_line_width(1.2)
    pdf.line(20, 104, 100, 104)
    meta_y = 122
    for k, v in (("분석 기간", f"{C.PERIOD[0]} ~ {C.PERIOD[1]}"),
                 ("데이터셋", C.DATASET),
                 ("생성일", __import__("datetime").datetime.now().strftime("%Y-%m-%d"))):
        _text(pdf, 20, meta_y, 200, f"{k}   {v}", 10.5, MUTED)
        meta_y += 8

    # 우측 하단 추상 도형(장식) — core.config 색의 옅은 음영만 쓴다.
    bars = [(PRIMARY, 0.0, 52), (PRIMARY, 0.55, 66), (PRIMARY, 0.78, 80)]
    bx = 250
    for color, factor, bh in bars:
        _box(pdf, bx, 178 - bh, 10, bh, fill=_tint(color, factor), draw=(255, 255, 255))
        bx += 14


def _page_summary(pdf: _ExecReport, 착수, 완료, 미완료, 연간환산, scale_note: str):
    pdf.category = "핵심 요약"
    pdf.add_page()
    _text(pdf, 18, 20, 260, "결론부터 말씀드립니다", 24, INK, bold=True)

    msg = (f"개선조치 착수 {착수:,}건 중 완료는 {완료:,}건에 그쳐, 착수 이후 완료 "
           f"단계에서 {미완료:,}건의 관리 공백이 확인됩니다."
           if 착수 is not None and 완료 is not None and 미완료 is not None
           else "현재 근거로는 단계별 현황을 표시할 수 없습니다.")
    _box(pdf, 18, 38, 261, 26, fill=_tint(PRIMARY, 0.92))
    _text(pdf, 26, 44, 245, msg, 13, INK, bold=True, line_h=7)

    # KPI 카드 3개
    kx, ky, kw, kh = 18, 72, 82, 44
    gap = 8
    if 착수 is not None:
        _kpi_card(pdf, kx, ky, kw, kh, "착수", f"{착수:,}건")
        _kpi_card(pdf, kx + (kw + gap), ky, kw, kh, "완료", f"{완료:,}건")
        _kpi_card(pdf, kx + 2 * (kw + gap), ky, kw, kh, "미완료", f"{미완료:,}건", color=BLOCK)

    # 하단 결정 요청 요약 + 환산값 참고 카드
    by = 126
    _box(pdf, 18, by, 190, 56, fill=(255, 255, 255))
    _text(pdf, 26, by + 8, 174, "현재 제안", 9.5, MUTED, bold=True)
    _text(pdf, 26, by + 15, 174, "2027년 목표일 개선조치를 확인 대상에 포함", 11, INK, bold=True)
    _text(pdf, 26, by + 27, 174, "판단 방식", 9.5, MUTED, bold=True)
    _text(pdf, 26, by + 34, 174, "조건 충족 시 재평가", 11, INK)
    _text(pdf, 26, by + 44, 174, "요청 : 개선조치 관리 강화 운영안 승인", 10.5, (to_pdf._hex(PRIMARY)), bold=True)

    rx = 216
    _box(pdf, rx, by, 63, 56, fill=_tint(C.BRAND["line"], 0.6))
    _text(pdf, rx + 6, by + 8, 51, "연간 환산 참고값", 8.5, MUTED, bold=True)
    if 연간환산 is not None:
        _text(pdf, rx + 6, by + 18, 51, f"{연간환산:,.1f}건", 20, to_pdf._hex(PRIMARY), bold=True)
        _text(pdf, rx + 6, by + 40, 51, "실측값이 아닌 환산값", 7.5, MUTED)
    else:
        _text(pdf, rx + 6, by + 18, 51, "규모 근거 부족", 12, MUTED, bold=True)
        _text(pdf, rx + 6, by + 34, 51, scale_note or "", 7.5, MUTED, line_h=3.6)


def _page_problem(pdf: _ExecReport, 발생, 착수, 완료, 미완료):
    pdf.category = "문제 구조"
    pdf.add_page()
    _text(pdf, 18, 20, 260, "어디에서 관리 공백이 발생하는가", 22, INK, bold=True)

    # 프로세스 Flow(가로 3단, 전체 폭 사용)
    steps = [("미비점 발생", 발생), ("개선조치 착수", 착수), ("개선조치 완료", 완료)]
    fx, fy, fw, fh = 18, 48, 71, 34
    gap = 22
    for i, (label, n) in enumerate(steps):
        cx = fx + i * (fw + gap)
        last = i == len(steps) - 1
        fill = _tint(BLOCK, 0.85) if last else _tint(C.BRAND["line"], 0.5)
        _box(pdf, cx, fy, fw, fh, fill=fill, draw=(to_pdf._hex(BLOCK) if last else LINE))
        _text(pdf, cx + 4, fy + 8, fw - 8, label, 10.5, INK, bold=True, align="C")
        color = BLOCK if last else PRIMARY
        _text(pdf, cx + 4, fy + 18, fw - 8, f"{n:,}" if n is not None else 확인_필요,
              20, to_pdf._hex(color), bold=True, align="C")
        if not last:
            _arrow_right(pdf, cx + fw + 3, fy + fh / 2, gap - 6)
    _text(pdf, fx, fy + fh + 8, 261, "병목: 전체 과정 중 진행이 가장 많이 줄어드는 구간", 8.5, MUTED)

    # 핵심 해석(전체 폭 4칸 카드)
    _text(pdf, 18, 106, 261, "핵심 해석", 12, INK, bold=True)
    bullets = ["발생 → 착수", "착수 → 완료", "미완료", "관리 초점"]
    values = ["현재 데이터상 전 건 착수",
              f"{완료:,}건 완료" if 완료 is not None else 확인_필요,
              f"{미완료:,}건" if 미완료 is not None else 확인_필요,
              "착수 이후 완료 확인"]
    ix, iy, iw, ih, igap = 18, 116, 59, 34, 8
    for i, (b, v) in enumerate(zip(bullets, values)):
        cx = ix + i * (iw + igap)
        _box(pdf, cx, iy, iw, ih, fill=(255, 255, 255))
        _text(pdf, cx + 5, iy + 6, iw - 10, b, 9, MUTED, bold=True)
        _text(pdf, cx + 5, iy + 16, iw - 10, v, 10, INK, bold=True, line_h=4.8)

    # 하단 — 주의사항
    _box(pdf, 18, 164, 261, 26, fill=_tint(WARN, 0.9), draw=to_pdf._hex(WARN))
    _text(pdf, 26, 170, 245,
          "현재 데이터는 발생과 착수가 1:1 관계인 구조이며, 향후 데이터 구조가 "
          "달라지면 다시 검토합니다.", 9.5, INK, line_h=5.5)


def _page_interpretation(pdf: _ExecReport, 실측_txt: str, 실측_caption: str, 연간환산, scale_note: str):
    pdf.category = "데이터 해석"
    pdf.add_page()
    _text(pdf, 18, 20, 260, "숫자를 어떻게 해석해야 하는가", 22, INK, bold=True)

    _box(pdf, 18, 42, 125, 50, fill=_tint(C.BRAND["line"], 0.5))
    size = 32 if len(실측_txt) <= 6 else (20 if len(실측_txt) <= 16 else 13)
    _text(pdf, 28, 50, 105, 실측_txt, size, to_pdf._hex(PRIMARY), bold=True, line_h=size * 0.42)
    _text(pdf, 28, 76, 105, 실측_caption, 9, MUTED, line_h=4.6)

    _box(pdf, 152, 42, 127, 50, fill=(255, 255, 255))
    if 연간환산 is not None:
        _text(pdf, 162, 50, 107, f"{연간환산:,.1f}건", 26, MUTED, bold=True)
        _text(pdf, 162, 74, 107, "연간 환산 참고값 — 실측값이 아닌 단순 환산값", 9, MUTED, line_h=4.6)
    else:
        _text(pdf, 162, 50, 107, "규모 근거 부족", 16, MUTED, bold=True)
        _text(pdf, 162, 64, 107, scale_note or "", 8.5, MUTED, line_h=4.4)

    principles = [
        ("실측 우선", "실제 관측된 값과 환산값을 구분합니다"),
        ("표본 기준", "최소 표본 미달 값은 성과 판단에서 제외합니다"),
        ("관측기간", "목표일이 도래하지 않은 건은 실패로 간주하지 않습니다"),
    ]
    px, py, pw, ph, gap = 18, 108, 84, 40, 6
    for i, (t, d) in enumerate(principles):
        cx = px + i * (pw + gap)
        _box(pdf, cx, py, pw, ph, fill=(255, 255, 255))
        _text(pdf, cx + 5, py + 6, pw - 10, t, 10.5, to_pdf._hex(PRIMARY), bold=True)
        _text(pdf, cx + 5, py + 15, pw - 10, d, 8.5, INK, line_h=4.4)

    _text(pdf, 18, 168, 261,
          "※ 연간 환산은 분석 기간을 연 365일 기준으로 균등 환산한 값이며, 실제 관측치를 "
          "대체하지 않습니다.", 8, MUTED, line_h=4)


def _page_action(pdf: _ExecReport, card_titles: dict, confirm_list: list[tuple[str, str]]):
    pdf.category = "제안 내용"
    pdf.add_page()
    _text(pdf, 18, 20, 260, "무엇을 바꿀 것인가", 22, INK, bold=True)

    steps = [("1. 제외", card_titles.get("제외", ""), BLOCK),
             ("2. 재평가", card_titles.get("재평가", ""), WARN),
             ("3. 실행", card_titles.get("실행", ""), PRIMARY)]
    sx, sy, sw, sh, gap = 18, 46, 79, 46, 12
    for i, (label, title, color) in enumerate(steps):
        cx = sx + i * (sw + gap)
        _box(pdf, cx, sy, sw, sh, fill=(255, 255, 255), draw=to_pdf._hex(color))
        _text(pdf, cx + 6, sy + 7, sw - 12, label, 11, to_pdf._hex(color), bold=True)
        _text(pdf, cx + 6, sy + 18, sw - 12, title, 9.5, INK, line_h=4.8)
        if i < len(steps) - 1:
            _arrow_right(pdf, cx + sw + 2, sy + sh / 2, gap - 4)

    _confirm_cards(pdf, 18, 104, 261, confirm_list)
    _text(pdf, 18, 150, 261,
          "담당자 실명·상세 일정·구체 예산처럼 승인 이후 실행계획 단계에서 정할 사항은 "
          "이 페이지에 넣지 않았습니다.", 8, MUTED)


def _page_ops(pdf: _ExecReport, ops_rows: list[tuple[str, list[str]]]):
    pdf.category = "운영안"
    pdf.add_page()
    _text(pdf, 18, 20, 260, "승인 후 어떻게 관리할 것인가", 22, INK, bold=True)

    rows = dict(ops_rows)
    시점_후속 = rows.get("확인 시점 및 후속조치", [확인_필요, 확인_필요])
    steps = [
        ("STEP 1", "확인 대상 지정", "2027년 목표일 개선조치"),
        ("STEP 2", "목표일 도래", ""),
        ("STEP 3", "완료 여부 재확인", ""),
        ("STEP 4", "필요 시 재평가", ""),
    ]
    tx, ty, tw, th, gap = 18, 44, 55, 34, 12
    for i, (step, title, sub) in enumerate(steps):
        cx = tx + i * (tw + gap)
        _box(pdf, cx, ty, tw, th, fill=_tint(PRIMARY, 0.9))
        _text(pdf, cx + 5, ty + 5, tw - 10, step, 8.5, to_pdf._hex(PRIMARY), bold=True)
        _text(pdf, cx + 5, ty + 12, tw - 10, title, 10, INK, bold=True, line_h=4.6)
        if sub:
            _text(pdf, cx + 5, ty + 24, tw - 10, sub, 7.5, MUTED, line_h=3.6)
        if i < len(steps) - 1:
            _arrow_right(pdf, cx + tw + 2, ty + th / 2, gap - 4)

    _text(pdf, 18, 92, 261, "결재 전 최소 운영 정의", 12, INK, bold=True)
    grid = [
        ("확인 대상", (rows.get("확인 대상") or [확인_필요])[0]),
        ("확인 목적", (rows.get("확인 목적") or [확인_필요])[0]),
        ("확인 시점", 시점_후속[0].replace("확인 시점: ", "") if 시점_후속 else 확인_필요),
        ("후속조치", 시점_후속[1].replace("후속조치: ", "") if len(시점_후속) > 1 else 확인_필요),
        ("확인 주체", (rows.get("확인 주체") or [확인_필요])[0]),
        ("추가 자원", "확인 필요" if rows.get("추가 자원 필요 여부") else 확인_필요),
    ]
    gx, gy, gw, gh = 18, 104, 128, 22
    for i, (label, val) in enumerate(grid):
        col, row = i % 2, i // 2
        cx = gx + col * (gw + 5)
        cy = gy + row * (gh + 4)
        _box(pdf, cx, cy, gw, gh, fill=(255, 255, 255))
        _text(pdf, cx + 5, cy + 4, gw - 10, label, 8.5, MUTED, bold=True)
        _text(pdf, cx + 5, cy + 12, gw - 10, val, 9.5, INK, line_h=4.4)

    _text(pdf, 18, 182, 261,
          "상세 근거는 제안서 화면의 '표 보기' 또는 HTML 상세 영역에서 확인할 수 있습니다.",
          8, MUTED)


def _page_decision(pdf: _ExecReport, options: list[dict], confirm_list: list[tuple[str, str]],
                   risk_text: str, request_text: str):
    pdf.category = "결정 요청"
    pdf.add_page()
    _text(pdf, 18, 20, 260, "오늘 결정해 주실 사항", 22, INK, bold=True)

    _box(pdf, 18, 38, 261, 20, fill=_tint(PRIMARY, 0.9))
    _text(pdf, 26, 44, 245, "개선조치 관리 강화 운영안을 진행할지 결정해 주십시오.",
          12.5, to_pdf._hex(PRIMARY), bold=True)

    ox, oy, ow, oh, gap = 18, 66, 84, 40, 4.5
    for i, o in enumerate(options):
        cx = ox + i * (ow + gap)
        _box(pdf, cx, oy, ow, oh, fill=(255, 255, 255))
        _text(pdf, cx + 6, oy + 6, ow - 12, o["선택지"], 12, INK, bold=True)
        _text(pdf, cx + 6, oy + 17, ow - 12, o["의미"], 8.5, MUTED, line_h=4.2)

    ry = 114
    _text(pdf, 18, ry, 128, "판단의 한계", 10.5, INK, bold=True)
    limit = risk_text.strip() or C.PROPOSAL_WORDS["pending"]["작성 필요"]
    _box(pdf, 18, ry + 8, 128, 30, fill=_tint(C.BRAND["line"], 0.5))
    _text(pdf, 24, ry + 13, 116, limit, 9, INK, line_h=4.6)

    _confirm_cards(pdf, 151, ry, 128, confirm_list, title="결재 전 확인 필요")

    ask = request_text.strip() or C.PROPOSAL_WORDS["pending"]["작성 필요"]
    _box(pdf, 18, 164, 261, 26, fill=(255, 255, 255), draw=to_pdf._hex(PRIMARY), width=0.8)
    _text(pdf, 26, 171, 245, ask, 13, to_pdf._hex(PRIMARY), bold=True, line_h=6.5)


# ── 조립 ──────────────────────────────────────────────────────────
def build_executive_pdf(secs: list[dict], topic: dict | None, cards: dict) -> bytes:
    """7페이지(표지+6) 경영진용 A4 가로 PDF를 만든다.

    secs는 report.proposal.build()의 결과, cards는 load_cards()의 결과를 그대로
    받는다 — 여기서 core/metrics.py를 다시 호출하거나 값을 재계산하지 않는다.
    데이터는 report.proposal.exec_data() 한 곳에서만 뽑는다(같은 값을 HTML도 쓴다).
    """
    from report import proposal as P  # 순환 import 회피(proposal.py가 이 모듈을 부른다)

    d = P.exec_data(secs, cards)

    pdf = _ExecReport()
    _page_cover(pdf, topic)
    _page_summary(pdf, d["착수"], d["완료"], d["미완료"], d["연간환산"], d["scale_note"])
    _page_problem(pdf, d["발생"], d["착수"], d["완료"], d["미완료"])
    _page_interpretation(pdf, d["실측_txt"], d["실측_caption"], d["연간환산"], d["scale_note"])
    _page_action(pdf, d["card_titles"], d["confirm_list"])
    _page_ops(pdf, d["ops_rows"])
    _page_decision(pdf, d["decision_options"], d["confirm_list"], d["risk_text"], d["request_text"])

    out = pdf.output()
    return bytes(out)
