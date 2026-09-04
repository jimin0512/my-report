# -*- coding: utf-8 -*-
"""PDF 생성 (fpdf2).

한글 폰트는 Noto Sans KR(OFL)을 쓴다. 맑은 고딕은 재배포가 불가능하므로
앱에 동봉할 수 없다 — 라이선스는 배포 단계에서 실제로 문제가 된다.

fpdf2는 상태 저장형이다. set_font / set_text_color를 바꾸면 이후 계속 유지되므로
블록마다 명시적으로 지정한다.
"""
from __future__ import annotations

import io
from datetime import datetime

from fpdf import FPDF

from core import config as C

FONT_DIR = C.ROOT / "fonts"
INK = (15, 23, 42)
MUTED = (100, 116, 139)
LINE = (226, 232, 240)


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Report(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(True, margin=20)
        self.has_kr = False
        reg, bold = FONT_DIR / "NotoSansKR-Regular.ttf", FONT_DIR / "NotoSansKR-Bold.ttf"
        if reg.exists():
            self.add_font("Noto", "", str(reg))
            self.add_font("Noto", "B", str(bold) if bold.exists() else str(reg))
            self.has_kr = True
        self.base = "Noto" if self.has_kr else "Helvetica"

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self.base, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"{C.DATASET}  ·  {C.PERIOD[0]} ~ {C.PERIOD[1]}",
                  align="L")
        self.ln(8)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font(self.base, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, str(self.page_no()), align="C")


def build_pdf(sections: list[dict], charts: dict[str, bytes],
              title: str = "성장 성과 분석") -> bytes:
    pdf = Report()

    # ── 표지 ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.ln(64)
    pdf.set_font(pdf.base, "B", 26)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 12, title, align="L")
    pdf.ln(3)
    pdf.set_font(pdf.base, "", 12)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 8, f"{C.PERIOD[0]} ~ {C.PERIOD[1]}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"데이터셋 {C.DATASET}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_draw_color(*_hex(C.BRAND["primary"]))
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 40, pdf.get_y())
    pdf.ln(14)
    pdf.set_font(pdf.base, "", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"생성 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # ── 목차 ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font(pdf.base, "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(0, 10, "목차", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    for s in sections:
        pdf.set_font(pdf.base, "", 11)
        pdf.set_text_color(*INK)
        mark = "" if s["kind"] == "auto" else "  (사람 작성)"
        pdf.cell(0, 8, s["title"] + mark, new_x="LMARGIN", new_y="NEXT")

    # ── 본문 ──────────────────────────────────────────────────────
    for s in sections:
        pdf.add_page()
        pdf.set_font(pdf.base, "B", 15)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 9, s["title"])
        pdf.ln(1)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(6)

        body = (s.get("body") or "").strip()
        if not body:
            pdf.set_font(pdf.base, "", 10)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(0, 6, f"[작성되지 않음] {s.get('placeholder','')}")
            continue

        pdf.set_font(pdf.base, "", 10.5)
        pdf.set_text_color(*INK)
        for para in body.split("\n\n"):
            pdf.multi_cell(0, 6.2, para.strip())
            pdf.ln(3)

        for key in s.get("charts", []):
            png = charts.get(key)
            if not png:
                continue
            if pdf.get_y() > 200:
                pdf.add_page()
            pdf.ln(2)
            pdf.image(io.BytesIO(png), w=pdf.w - pdf.l_margin - pdf.r_margin)
            pdf.ln(4)

    out = pdf.output()
    return bytes(out)
