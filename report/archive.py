# -*- coding: utf-8 -*-
"""최종 확정 리포트 아카이브.

새 계산을 하지 않는다. core.metrics 가 이미 계산한 결과(kpis·funnel)와
report.to_pdf 가 이미 만든 PDF 바이트를 그대로 파일로 옮겨 담을 뿐이다.

저장 방식은 core/gates.py의 실행 이력 저장(run_id 폴더 없이 JSON 1개)과
같은 원칙을 쓴다 — 새 DB를 두지 않고, run_id 대신 archive_id 폴더 아래에
PDF와 metadata.json을 나란히 둔다.
"""
from __future__ import annotations

import json
from datetime import datetime

from core import config as C, metrics as M

ARCHIVE_DIR = C.ROOT / "archives"


def save_archive(run: dict, t: dict, secs: list[dict], pdf_bytes: bytes) -> dict:
    """확정 시점의 리포트를 archives/<archive_id>/ 아래에 저장하고 metadata를 돌려준다.

    화면·리포트에서 신뢰성 기준 미달로 감춘 파생 비율(유지율·재발률·
    세그먼트 비교 등)은 여기에도 다시 저장하지 않는다. 대신 trust 절에
    "무엇을 왜 판정 보류했는지"(trusted·reason·actual·threshold)만 남긴다
    — 원천 건수·데이터 품질 정보는 남기되, 감춘 비율 자체는 남기지 않는다.
    """
    k = M.kpis(t)
    f = M.funnel(t["ic_deficiency"], t["ic_remediation"])
    rf = M.retention_funnel(t)
    pop_n = int(rf.loc[rf.step == "기준모집단", "n"].iloc[0])
    trust = {
        "개선 후 재발 분석": M.trust_check("개선 후 재발 분석", pop_n),
        "재고 프로세스 운영 적정률(2026)": M.trust_check(
            "재고 프로세스 운영 적정률(2026)", 7),
        "Key통제 개선완료율(2026)": M.trust_check(
            "Key통제 개선완료율(2026)", 7),
    }

    archive_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ARCHIVE_DIR / archive_id
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = out_dir / "report.pdf"
    pdf_path.write_bytes(pdf_bytes)

    human_sections = {s["title"]: s["body"] for s in secs if s["kind"] == "human"}

    metadata = {
        "archive_id": archive_id,
        "run_id": run.get("run_id"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": C.DATASET,
        "period": {"start": C.PERIOD[0], "end": C.PERIOD[1]},
        "kpis": {
            name: {"value": v["value"], "unit": v["unit"],
                   "분자": v["분자"], "분모": v["분모"], "기준연도": v["기준연도"]}
            for name, v in k.items()
        },
        "funnel": {"label": f["label"].tolist(), "n": f["n"].tolist()},
        "retention": {"label": rf["label"].tolist(), "n": rf["n"].tolist()},
        "trust": {
            name: {"trusted": tc["trusted"], "reason": tc["reason"],
                   "actual": tc["actual"], "threshold": tc["threshold"]}
            for name, tc in trust.items()
        },
        "human_sections": human_sections,
        "confirmed": True,
        "pdf_path": str(pdf_path.relative_to(C.ROOT)),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def load_all() -> list[dict]:
    """저장된 아카이브 metadata를 최신순으로 돌려준다."""
    if not ARCHIVE_DIR.exists():
        return []
    out = []
    for p in sorted(ARCHIVE_DIR.glob("*/metadata.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def read_pdf(archive_id: str) -> bytes | None:
    p = ARCHIVE_DIR / archive_id / "report.pdf"
    return p.read_bytes() if p.exists() else None
