# -*- coding: utf-8 -*-
"""검증.

검증은 **자동으로 통과시키지 않는다.** 결과를 사람 앞에 놓고 게이트에서 판단하게 한다.
경고를 앱이 마음대로 무시하면, 사람은 무엇을 승인했는지 모른 채 승인하게 된다.

판정 3종:

  ok    통과
  warn  경고 — **정상일 수도 있다. 사람이 판단한다.**
  block 차단 — 이 상태로는 분석할 수 없다.

────────────────────────────────────────────────────────────────────
차단과 경고를 가르는 것은 한 질문이다.

    이 규칙이 깨진 채로 계산하면 값이 틀리는가?
        틀린다              → block
        해석만 조심하면 된다 → warn

차단을 늘리면 안전해 보이지만, 실무 데이터는 늘 어딘가 깨져 있어서
앱이 아무것도 못 돌리게 된다. **차단은 "이대로 계산하면 확실히 틀리는 것"에만 건다.**
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import pandas as pd

from core import config as C
from core.load import to_dt


def _r(name, level, msg, detail=""):
    """검증 결과 한 줄. 그대로 쓴다."""
    return {"name": name, "level": level, "msg": msg, "detail": detail}


def profile(t: dict) -> pd.DataFrame:
    """적재 직후 개요. 게이트 1에서 사람이 보는 화면.

    **그대로 쓴다.** 어느 도메인이든 행수·컬럼·기간·결측은 먼저 본다.
    """
    rows = []
    for name, df in t.items():
        date_col = next((c for c in df.columns
                         if c.endswith("_date") or c == "year_month"), None)
        span = ""
        if date_col is not None:
            s = df[date_col].astype(str)
            span = f"{s.min()} ~ {s.max()}"
        rows.append({
            "테이블": name, "행수": len(df), "컬럼": df.shape[1],
            "기간": span,
            "결측 컬럼": int(df.isna().any().sum()),
            "메모리(MB)": round(df.memory_usage(deep=True).sum() / 1e6, 1),
        })
    return pd.DataFrame(rows)


# ── 규칙 2: 필수 컬럼 ────────────────────────────────────────────
# 기준(위키 06_metrics/metric-001~004, 02_data/schema-ic_*.md, 03_analysis/analysis-005 대조):
#   A. PK/FK 연결에 필요한 컬럼
#   B. 공식 지표(metric-001~004) 계산에 필요한 컬럼
#   C. Track B 3단계(미비점 발생 → 개선조치 착수 → 개선조치 완료) 계산에 필요한 컬럼
#   D. config.PERIOD 검증에 필요한 날짜 컬럼
# 단순 설명용 컬럼(process_name·department·control_name·owner_role 등)은
# 어느 계산에도 쓰이지 않으므로 필수로 두지 않는다.
REQUIRED_COLUMNS: dict[str, list[str]] = {
    "ic_process_master": ["process_id"],
    "ic_control_master": ["control_id", "process_id"],
    "ic_design_assessment": ["assessment_id", "control_id", "assessment_date"],
    "ic_operating_assessment": [
        "assessment_id", "control_id", "year", "assessment_result", "assessment_date"],
    "ic_deficiency": ["deficiency_id", "control_id", "year", "identified_date"],
    "ic_remediation": [
        "remediation_id", "deficiency_id", "action_status",
        "target_date", "completion_date"],
}

# ── 규칙 3: 날짜 범위 ────────────────────────────────────────────
# 실제 스키마에 존재하는, 분석에 쓰이는 날짜 컬럼만 검사한다. (테이블, 컬럼) 쌍.
PERIOD_DATE_COLUMNS: list[tuple[str, str]] = [
    ("ic_design_assessment", "assessment_date"),
    ("ic_operating_assessment", "assessment_date"),
    ("ic_deficiency", "identified_date"),
    ("ic_remediation", "target_date"),
    ("ic_remediation", "completion_date"),
]


def run_checks(t: dict) -> list[dict]:
    """정합성 검증. 결과는 게이트 1에서 사람에게 보여준다.

    규칙 3건만 구현한다. 표본 충분성(MIN_SAMPLE)·조인 orphan 등 다른 점검은
    여기서 다루지 않는다 — 이 3건 외의 새 규칙을 추가하지 않는다.

        1. 행 수      — 0행이면 차단. 그 테이블을 쓰는 조인·지표·퍼널 계산
                        자체가 성립하지 않기 때문이다. 통계적 표본 충분성
                        (MIN_SAMPLE)과는 다른 질문이라 여기서 쓰지 않는다.
        2. 필수 컬럼  — 위 REQUIRED_COLUMNS 기준. 하나라도 없으면 차단.
                        공식 지표·조인·퍼널 계산을 정확히 수행할 수 없다.
        3. 날짜 범위  — config.PERIOD 밖 값이 있으면 경고만 한다(차단하지
                        않는다). 예: 2026년 개선조치의 target_date 가 2027년인
                        것은 아직 완료되지 않은 개선조치의 미래 목표일일 수
                        있어, 그 자체로 계산을 막을 근거가 아니다. 다만
                        관측기간 밖 데이터가 있다는 사실은 사람이 알아야 한다.
                        null 날짜는 기간 밖으로 세지 않는다.

    반환: [_r(이름, 레벨, 메시지, 상세), ...]
    """
    out: list[dict] = []

    # 1. 행 수
    for name in C.TABLES:
        df = t.get(name)
        n = len(df) if df is not None else 0
        level = "block" if n < 1 else "ok"
        out.append(_r(f"행 수 - {name}", level, f"{name}: {n}행 (최소 1행)"))

    # 2. 필수 컬럼
    for name, required in REQUIRED_COLUMNS.items():
        df = t.get(name)
        cols = set(df.columns) if df is not None else set()
        missing = [c for c in required if c not in cols]
        if missing:
            out.append(_r(
                f"필수 컬럼 - {name}", "block",
                f"{name}: 필수 컬럼 {len(required)}개 중 {len(missing)}개 누락 — "
                + ", ".join(missing)))
        else:
            out.append(_r(
                f"필수 컬럼 - {name}", "ok",
                f"{name}: 필수 컬럼 {len(required)}개 확인, 누락 0개"))

    # 3. 날짜 범위
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    for name, col in PERIOD_DATE_COLUMNS:
        df = t.get(name)
        if df is None or col not in df.columns:
            continue  # 컬럼 부재는 규칙 2(필수 컬럼)가 이미 차단으로 잡는다
        dt = to_dt(df[col])
        valid = dt.dropna()
        out_of_range = valid[(valid < lo) | (valid > hi)]
        n_out, n_total = len(out_of_range), len(valid)
        level = "warn" if n_out > 0 else "ok"
        detail = (f"실제 범위 {valid.min().date()} ~ {valid.max().date()}"
                  if n_total else "유효한 날짜 값이 없습니다")
        out.append(_r(
            f"날짜 범위 - {name}.{col}", level,
            f"{col}: {n_total}건 중 {n_out}건이 기간 밖 "
            f"(기준 {C.PERIOD[0]} ~ {C.PERIOD[1]})",
            detail))

    return out


def summarize(checks: list[dict]) -> dict:
    """통과·경고·차단을 센다. 차단이 하나라도 있으면 게이트를 못 넘는다.

    **그대로 쓴다.**
    """
    n = {"ok": 0, "warn": 0, "block": 0}
    for c in checks:
        n[c["level"]] += 1
    return {**n, "total": len(checks), "can_pass": n["block"] == 0}


# ══════════════════════════════════════════════════════════════════
# 참고 — 통신사 데이터에서 쓴 검증 12건
#
# **이 함수는 호출되지 않는다.** 읽고 필요한 것만 위 run_checks() 로 옮긴다.
# 대부분은 통신사 테이블·컬럼에 묶여 있어서 그대로는 안 돌아간다.
#
# 눈여겨볼 것은 규칙 자체가 아니라 **무엇을 block 으로 두고 무엇을 warn 으로
# 뒀는가**이다.
#
#   block  기간 정합성 · 퍼널 순서 · 신규 고객 일치 · 배정 중복 ·
#          중도절단 · 참조 무결성        ← 깨지면 계산이 틀린다
#   warn   월 커버리지 · 결측률 2건 · 응답률 · 표본 수 · 배정 균형
#                                        ← 정상일 수도 있다. 사람이 판단한다
# ══════════════════════════════════════════════════════════════════
def reference_checks_telecom(t: dict) -> list[dict]:
    out = []
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    cu, se, fe = t["customers"], t["sessions"], t["funnel_events"]
    um, asg, ad = t["usage_monthly"], t["experiment_assignments"], t["ad_spend"]

    # 1. 기간 — 기간이 어긋나면 조인에 구멍이 생긴다
    bad = []
    for label, s in [("sessions", se.session_date), ("funnel_events", fe.event_date),
                     ("ad_spend", ad.spend_date)]:
        d = to_dt(s)
        if d.min() < lo or d.max() > hi:
            bad.append(f"{label} {d.min().date()}~{d.max().date()}")
    out.append(_r("기간 정합성", "block" if bad else "ok",
                  "기간을 벗어난 테이블이 있습니다" if bad else
                  f"모든 테이블이 {C.PERIOD[0]} ~ {C.PERIOD[1]} 안에 있습니다",
                  "; ".join(bad)))

    # 2. 월 커버리지 — 빠진 달이 있어도 정상일 수 있다
    m = sorted(um.year_month.astype(str).unique())
    out.append(_r("월 커버리지", "ok" if len(m) == 12 else "warn",
                  f"{m[0]} ~ {m[-1]} ({len(m)}개월)"))

    # 3. 퍼널 역행 — 앞 단계를 안 거치고 뒤 단계에 온 대상
    piv = (fe.pivot_table(index="visitor_id", columns="step_order",
                          values="event_id", aggfunc="count").fillna(0) > 0)
    cols = sorted(piv.columns)
    viol = sum(int(((~piv[a]) & piv[b]).sum()) for a, b in zip(cols, cols[1:]))
    out.append(_r("퍼널 순서", "block" if viol else "ok",
                  f"단계 역행 {viol}건" if viol else "단계 역행 없음"))

    # 4. 신규 고객 = 최종 통과자
    paid = set(fe.loc[fe.funnel_step == C.FUNNEL_STEPS[-1], "visitor_id"])
    newc = set(cu.loc[cu.visitor_id.notna(), "visitor_id"])
    out.append(_r("신규 고객 일치", "ok" if newc == paid else "block",
                  f"신규 {len(newc):,}명 / 최종 통과 {len(paid):,}명"))

    # 5. 실험 배정 중복 — 한 대상이 두 번 배정되면 결과를 못 믿는다
    dup = int(asg.duplicated(["experiment_id", "visitor_id"]).sum())
    out.append(_r("배정 중복", "block" if dup else "ok",
                  f"중복 {dup}건" if dup else "중복 없음"))

    # 6. 중도절단 — 떠난 뒤의 기록이 있으면 데이터가 잘못됐다
    ch = cu[cu.is_churned][["customer_id", "churn_date"]].copy()
    ch["cm"] = to_dt(ch.churn_date).dt.strftime("%Y-%m")
    mg = um.merge(ch, on="customer_id", how="inner")
    after = int((mg.year_month.astype(str) > mg.cm).sum())
    out.append(_r("중도절단", "block" if after else "ok",
                  f"이탈 이후 사용 기록 {after}건" if after else
                  "이탈 이후 사용 기록 없음"))

    # 7. 참조 무결성 — 끊어진 참조가 있으면 조인에서 조용히 사라진다
    fk_bad = []
    if not set(um.customer_id) <= set(cu.customer_id):
        fk_bad.append("usage_monthly")
    if not set(fe.session_id) <= set(se.session_id):
        fk_bad.append("funnel_events")
    out.append(_r("참조 무결성", "block" if fk_bad else "ok",
                  f"끊어진 참조: {', '.join(fk_bad)}" if fk_bad else "모든 참조 정상"))

    # 8. 결측 — 경고로만 낸다. **구조적 결측은 오류가 아니다.**
    nn = int(cu.visitor_id.isna().sum())
    if nn:
        out.append(_r("visitor_id 결측", "warn",
                      f"고객 {len(cu):,}명 중 {nn:,}명({nn/len(cu)*100:.0f}%)이 "
                      f"퍼널 이력이 없습니다",
                      "기존 고객은 이번 기간 퍼널을 거치지 않았으므로 정상일 수 있습니다. "
                      "다만 퍼널 테이블과 INNER JOIN하면 이 인원이 전부 사라집니다."))

    # 9. 캠페인 결측 — 자연 유입은 캠페인이 없다
    cn = int(se.campaign_id.isna().sum())
    if cn:
        out.append(_r("campaign_id 결측", "warn",
                      f"세션 {len(se):,}건 중 {cn:,}건({cn/len(se)*100:.0f}%)에 "
                      f"캠페인이 없습니다",
                      "자연 유입(검색·직접 방문)은 캠페인이 없으므로 정상일 수 있습니다."))

    # 10. 응답률 — 응답자 평균은 전체 평균이 아니다
    st_ = t["support_tickets"]
    resp = st_.satisfaction_score.notna().mean()
    if resp < 0.5:
        out.append(_r("만족도 응답률", "warn",
                      f"응답률 {resp*100:.1f}% — 응답자 평균은 전체 만족도가 아닙니다",
                      "극단적 경험을 한 쪽이 더 많이 응답하는 경향이 있습니다. "
                      "이 경고는 리포트 7장 한계로 옮깁니다."))

    # 11. 표본 크기
    small = []
    for _, e in t["experiments"].iterrows():
        n = int((asg.experiment_id == e.experiment_id).sum())
        if n < C.MIN_SAMPLE:
            small.append(f"{e.experiment_id}({n:,})")
    out.append(_r("실험 표본", "warn" if small else "ok",
                  f"표본 부족: {', '.join(small)}" if small else
                  "모든 실험이 최소 표본을 넘습니다"))

    # 12. SRM — 실험 결과를 보기 전에 반드시 확인
    from core.metrics import srm_check
    broken = []
    for _, e in t["experiments"].iterrows():
        s = srm_check(asg, e.experiment_id)
        if not s["ok"]:
            broken.append(f"{e.experiment_id} ({s['ratio'][0]*100:.1f}:"
                          f"{s['ratio'][1]*100:.1f}, p={s['p']:.1e})")
    out.append(_r("실험 배정 균형(SRM)", "warn" if broken else "ok",
                  f"배정이 깨진 실험: {', '.join(broken)}" if broken else
                  "모든 실험의 배정이 균형입니다",
                  "배정이 깨진 실험은 어떤 효과가 나와도 해석할 수 없습니다. "
                  "결과를 쓰지 말고 재실험해야 합니다." if broken else ""))

    return out
