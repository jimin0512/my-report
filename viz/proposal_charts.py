# -*- coding: utf-8 -*-
"""제안서용 인라인 SVG 차트 3종.

제안서(HTML/PDF)에 그대로 삽입할 수 있는 <svg> 문자열만 만든다. 외부
이미지·CDN·웹폰트·JS를 쓰지 않고, core/metrics.py의 topic_evidence()가 이미
계산한 값만 그린다 — 새 계산·새 임계값을 여기서 만들지 않는다. 값을 그릴 수
없으면 빈 SVG 대신 None을 돌려준다(report/proposal.py 원칙과 같다 — 근거에
없는 값을 화면에서 새로 만들지 않는다).

색은 3개를 넘지 않는다(viz/charts.py·viz/pdf_charts.py와 같은 관례):
    강조   config.COLORS["block"]   (병목 구간 · 최고/최저 셀)
    기본   config.BRAND["primary"]  (일반 막대·선)
    회색   config.BRAND["muted"]    (축·눈금·비강조 요소·캡션)
"""
from __future__ import annotations

import html

from core import config as C

FONT = "'Malgun Gothic', sans-serif"  # 시스템 폰트만 쓴다 — 웹폰트 없음
COLOR_EMPHASIS = C.COLORS["block"]
COLOR_BASE = C.BRAND["primary"]
COLOR_MUTED = C.BRAND["muted"]

# Track B(funnel())는 이 앱에 하나뿐인 퍼널이다 — 그레인은 core/metrics.py
# funnel()·CLAUDE.md "계산 그레인" 표에 이미 적힌 정의를 그대로 옮긴 것이지
# 여기서 새로 지어낸 것이 아니다.
GRAIN_FUNNEL = "그레인: 미비점 1건(deficiency_id 기준)"
GRAIN_GAP = "그레인: 신뢰 가능한(최소표본 충족) 세그먼트 칸만 표시"
GRAIN_TREND = "그레인: 월별 집계 — 원본 레코드가 있는 달만 표시(결측월 제외)"


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _svg_open(width: int, height: int, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="100%" height="auto" role="img" aria-label="{_esc(title)}" '
            f'style="font-family:{FONT}">')


def funnel_svg(data: dict | None) -> str | None:
    """현황 — Track B 단계별 도달 막대. 병목 구간 하나만 강조색.

    입력: topic_evidence(t, topic)["현황"]
        {"값": [{"단계","도달","전환율","병목여부"}, ...], "사유": None}
    값을 그릴 수 없으면(값 없음·전부 0건) None을 돌려준다.
    """
    if not data or not data.get("값"):
        return None
    rows = data["값"]
    if not rows:
        return None
    max_n = max(r["도달"] for r in rows)
    if max_n <= 0:
        return None

    top, row_h, axis_h, caption_h = 16, 56, 36, 26
    label_w, right_pad = 150, 70
    W = 640
    H = top + len(rows) * row_h + axis_h + caption_h
    bar_x = label_w + 10
    bar_max_w = W - bar_x - right_pad

    parts = [_svg_open(W, H, "Track B 단계별 도달 건수, 병목 구간 강조")]

    for i, r in enumerate(rows):
        y = top + i * row_h
        bw = (r["도달"] / max_n) * bar_max_w
        color = COLOR_EMPHASIS if r.get("병목여부") else COLOR_BASE
        parts.append(f'<text x="{label_w}" y="{y + 20}" font-size="13" '
                     f'fill="{COLOR_MUTED}" text-anchor="end">{_esc(r["단계"])}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{bw:.1f}" height="28" '
                     f'rx="3" fill="{color}"/>')
        parts.append(f'<text x="{bar_x + bw + 8:.1f}" y="{y + 19}" font-size="13" '
                     f'font-weight="700" fill="{COLOR_MUTED}">{r["도달"]:,}</text>')

    axis_y = top + len(rows) * row_h + 12
    parts.append(f'<line x1="{bar_x}" y1="{axis_y}" x2="{bar_x + bar_max_w}" '
                 f'y2="{axis_y}" stroke="{COLOR_MUTED}" stroke-width="1"/>')
    for frac in (0.0, 0.5, 1.0):
        tx = bar_x + bar_max_w * frac
        tick_v = round(max_n * frac)
        parts.append(f'<line x1="{tx:.1f}" y1="{axis_y}" x2="{tx:.1f}" '
                     f'y2="{axis_y + 5}" stroke="{COLOR_MUTED}" stroke-width="1"/>')
        parts.append(f'<text x="{tx:.1f}" y="{axis_y + 18}" font-size="11" '
                     f'fill="{COLOR_MUTED}" text-anchor="middle">{tick_v:,}</text>')

    parts.append(f'<text x="0" y="{H - 6}" font-size="11" fill="{COLOR_MUTED}">'
                 f'{_esc(GRAIN_FUNNEL)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def gap_svg(data: dict | None) -> str | None:
    """원인 — 신뢰 가능한 분해축 칸만 가로 막대로 비교한다. 최고/최저만 강조.

    입력: topic_evidence(t, topic)["원인"]
        {"값": [{"칸","도달","전환","전환율","비중","최고"?,"최저"?}, ...] | None, "사유": str | None}

    표본 미달로 topic_evidence()가 애초에 담지 않은 칸은 여기서도 그릴 수
    없다 — "값"이 None이거나 비교 가능한 칸이 2개 미만이면 None을 돌려준다
    (표본 미달 비율을 다시 노출하지 않는다).
    """
    if not data or not data.get("값"):
        return None
    cells = data["값"]
    if len(cells) < 2:
        return None
    max_rate = max(c["전환율"] for c in cells)
    if max_rate <= 0:
        return None

    top, row_h, axis_h, caption_h = 16, 44, 26, 26
    label_w, right_pad = 150, 90
    W = 640
    H = top + len(cells) * row_h + axis_h + caption_h
    bar_x = label_w + 10
    bar_max_w = W - bar_x - right_pad

    parts = [_svg_open(W, H, "분해축별 전환율, 최고/최저 강조")]

    for i, c in enumerate(cells):
        y = top + i * row_h
        bw = (c["전환율"] / max_rate) * bar_max_w
        emph = bool(c.get("최고")) or bool(c.get("최저"))
        color = COLOR_EMPHASIS if emph else COLOR_MUTED
        parts.append(f'<text x="{label_w}" y="{y + 18}" font-size="13" '
                     f'fill="{COLOR_MUTED}" text-anchor="end">{_esc(c["칸"])}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y + 2}" width="{bw:.1f}" height="24" '
                     f'rx="3" fill="{color}"/>')
        parts.append(f'<text x="{bar_x + bw + 8:.1f}" y="{y + 18}" font-size="12" '
                     f'fill="{COLOR_MUTED}">{c["전환율"] * 100:.2f}%</text>')

    axis_y = top + len(cells) * row_h + 8
    parts.append(f'<line x1="{bar_x}" y1="{axis_y}" x2="{bar_x + bar_max_w}" '
                 f'y2="{axis_y}" stroke="{COLOR_MUTED}" stroke-width="1"/>')

    parts.append(f'<text x="0" y="{H - 6}" font-size="11" fill="{COLOR_MUTED}">'
                 f'{_esc(GRAIN_GAP)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def trend_svg(data: dict | None) -> str | None:
    """추세 — 실제 관측된 월만 꺾은선으로 잇는다. 결측월은 그리지 않는다.

    입력: topic_evidence(t, topic)["추세"]
        {"값": [{"월","값"}, ...] | None, "사유": str | None}
    값이 없거나(None) 점이 2개 미만이면(선을 그릴 수 없으면) None을 돌려준다.

    임계선: 이 입력에는 어떤 지표의 추세인지 이름 정보가 없다({"월","값"}만
    있음) — config.THRESHOLDS와 지표명을 직접 대조할 근거가 없으므로 새
    임계값을 만들지 않고 임계선 자체를 그리지 않는다.
    """
    if not data or not data.get("값"):
        return None
    rows = data["값"]
    if len(rows) < 2:
        return None

    values = [r["값"] for r in rows]
    max_v, min_v = max(values), min(values)

    W, H = 640, 220
    left, right_pad, top, bottom_axis, caption_h = 44, 20, 24, 36, 26
    plot_w = W - left - right_pad
    plot_h = H - top - bottom_axis - caption_h
    n = len(rows)
    step_x = plot_w / (n - 1) if n > 1 else 0

    def x_at(i):
        return left + step_x * i

    def y_at(v):
        if max_v == min_v:
            return top + plot_h / 2
        return top + plot_h * (1 - (v - min_v) / (max_v - min_v))

    parts = [_svg_open(W, H, "최근 관측 월 추세")]

    axis_y0 = top + plot_h
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{axis_y0}" '
                 f'stroke="{COLOR_MUTED}" stroke-width="1"/>')
    parts.append(f'<line x1="{left}" y1="{axis_y0}" x2="{left + plot_w}" '
                 f'y2="{axis_y0}" stroke="{COLOR_MUTED}" stroke-width="1"/>')
    parts.append(f'<text x="{left - 6}" y="{top + 4}" font-size="10" '
                 f'fill="{COLOR_MUTED}" text-anchor="end">{max_v:,}</text>')
    parts.append(f'<text x="{left - 6}" y="{axis_y0}" font-size="10" '
                 f'fill="{COLOR_MUTED}" text-anchor="end">{min_v:,}</text>')

    points = [(x_at(i), y_at(v)) for i, v in enumerate(values)]
    path_d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    parts.append(f'<path d="{path_d}" fill="none" stroke="{COLOR_BASE}" '
                 f'stroke-width="2.5"/>')

    for (x, y), r in zip(points, rows):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLOR_BASE}"/>')
        parts.append(f'<text x="{x:.1f}" y="{max(y - 10, 10):.1f}" font-size="11" '
                     f'fill="{COLOR_MUTED}" text-anchor="middle">{r["값"]:,}</text>')
        parts.append(f'<text x="{x:.1f}" y="{axis_y0 + 16}" font-size="10" '
                     f'fill="{COLOR_MUTED}" text-anchor="middle">{_esc(r["월"])}</text>')

    parts.append(f'<text x="0" y="{H - 6}" font-size="11" fill="{COLOR_MUTED}">'
                 f'{_esc(GRAIN_TREND)}</text>')
    parts.append('</svg>')
    return "".join(parts)
