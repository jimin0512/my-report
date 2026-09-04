# -*- coding: utf-8 -*-
"""지표 계산.

**지표의 정의는 위키가 원본이다.** 이 파일은 위키에 적힌 정의를 코드로 옮긴 것일 뿐,
여기서 정의를 새로 만들지 않는다. 정의가 바뀌면 위키를 먼저 고친다.

────────────────────────────────────────────────────────────────────
★ 이 파일에는 통신사 컬럼명이 박혀 있다.

  billing_amount · is_churned · acquisition_channel · visitor_id ...

config.py 를 다 바꿔도 여기서 깨진다. **깨지는 것이 정상이다.**
컬럼명을 하나씩 내 것으로 맞추는 것이 이식 작업의 절반이다. → DESIGN.md §4-6
────────────────────────────────────────────────────────────────────

계산은 전부 pandas로 한다. 어디서 읽어왔든 입력은 동일한 DataFrame이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from core import config as C
from core.load import to_dt
from core.todo import todo


# ── 퍼널 ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def funnel(defi: pd.DataFrame, rem: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Track B(미비점 개선 파이프라인) 단계별 도달 건수와 전환율.

    그레인: 미비점 사건 1건(deficiency_id). my-wiki-04 raw 데이터는 미비점
    1건당 개선조치가 정확히 1건(1:1)이므로 nunique 가 아니라 그대로 센다(len).

    단계 정의(my-wiki-04/나의_성장퍼널.md ②, 03_analysis/analysis-005 확정):
        미비점발생    ic_deficiency.deficiency_id
        개선조치착수  ic_remediation.deficiency_id 존재
        개선조치완료  ic_remediation.action_status == '완료'

    year 를 주면 ic_deficiency.year 로 먼저 필터링해 해당 연도만 계산한다.
    생략하면(None) 보유한 전체 연도를 합쳐 계산한다.

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]

        step           config.FUNNEL_STEPS 의 값
        label          config.FUNNEL_LABELS 의 값 (화면 표시용)
        n              그 단계에 도달한 수
        step_rate      전 단계 대비 비율 (첫 단계는 NaN)
        cum_rate       첫 단계 대비 비율
        drop           전 단계에서 빠진 수
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True
    """
    d = defi if year is None else defi[defi["year"] == year]
    dids = set(d["deficiency_id"])
    r = rem[rem["deficiency_id"].isin(dids)]

    counts = {
        "미비점발생": len(d),
        "개선조치착수": len(r),
        "개선조치완료": int((r["action_status"] == "완료").sum()),
    }

    rows, prev, first = [], None, None
    for step in C.FUNNEL_STEPS:
        n = counts[step]
        if first is None:
            first = n
        step_rate = np.nan if prev is None else (n / prev if prev else np.nan)
        cum_rate = np.nan if not first else n / first
        drop = 0 if prev is None else prev - n
        rows.append({"step": step, "label": C.FUNNEL_LABELS[step], "n": n,
                     "step_rate": step_rate, "cum_rate": cum_rate, "drop": drop})
        prev = n

    out = pd.DataFrame(rows)
    out["is_bottleneck"] = False
    valid = out["step_rate"].notna()
    if valid.any():
        out.loc[out.loc[valid, "step_rate"].idxmin(), "is_bottleneck"] = True
    return out


@st.cache_data(show_spinner=False)
def funnel_by(t: dict, dim: str = "process_name") -> pd.DataFrame:
    """Track B 퍼널을 분해 축(기본: process_name)별로 쪼갠다.

    쪼개는 기준은 이것이다: 그 축으로 나눴을 때 **손을 쓸 수 있는가.**
    나눠서 격차가 보여도 우리가 못 바꾸는 것이면 분해할 이유가 적다.
    이 도메인에서는 프로세스 담당 조직이 실제로 조치를 취할 수 있는
    단위라 process_name을 우선 축으로 쓴다(my-wiki-04 analysis-002와
    동일한 세그먼트 기준).

    조인: ic_deficiency.control_id -> ic_control_master.control_id
          -> ic_control_master.process_id -> ic_process_master.process_id

    funnel()과 같은 그레인(deficiency_id 1건 = 1행)을 process_name별로
    나눠 다시 센다 — 새 계산식이 아니라 funnel()의 3단계 카운트 로직을
    process 단위로 반복 적용한 것이다. 그래서 각 process_name의 합계는
    반드시 전체 funnel()의 값과 같아야 한다(발생 52·착수 52·완료 24,
    my-wiki-04/analysis-005 확정치).

    반환: DataFrame[<dim>, step, label, n, step_rate, cum_rate, drop,
                    is_bottleneck] — funnel()과 같은 컬럼에 <dim> 컬럼만
          추가된 형태(세그먼트별 병목은 세그먼트마다 따로 판정한다).
    """
    defi, rem = t["ic_deficiency"], t["ic_remediation"]
    cm, pm = t["ic_control_master"], t["ic_process_master"]

    ctrl_to_seg = (cm[["control_id", "process_id"]]
                   .merge(pm[["process_id", "process_name"]], on="process_id", how="left")
                   .set_index("control_id")[dim if dim in pm.columns else "process_name"])

    d = defi.assign(**{dim: defi["control_id"].map(ctrl_to_seg)})
    dids = set(d["deficiency_id"])
    r = (rem[rem["deficiency_id"].isin(dids)]
         .merge(defi[["deficiency_id", "control_id"]], on="deficiency_id", how="left"))
    r[dim] = r["control_id"].map(ctrl_to_seg)

    rows = []
    for seg, d_seg in d.groupby(dim, observed=True):
        r_seg = r[r[dim] == seg]
        counts = {
            "미비점발생": len(d_seg),
            "개선조치착수": len(r_seg),
            "개선조치완료": int((r_seg["action_status"] == "완료").sum()),
        }
        prev, first = None, None
        for step in C.FUNNEL_STEPS:
            n = counts[step]
            if first is None:
                first = n
            step_rate = np.nan if prev is None else (n / prev if prev else np.nan)
            cum_rate = np.nan if not first else (n / first if first else np.nan)
            drop = 0 if prev is None else prev - n
            rows.append({dim: seg, "step": step, "label": C.FUNNEL_LABELS[step],
                         "n": n, "step_rate": step_rate, "cum_rate": cum_rate,
                         "drop": drop})
            prev = n

    out = pd.DataFrame(rows)
    out["is_bottleneck"] = False
    for seg in out[dim].unique():
        mask = out[dim] == seg
        valid = mask & out["step_rate"].notna()
        if valid.any():
            out.loc[out.loc[valid, "step_rate"].idxmin(), "is_bottleneck"] = True
    return out


# ── 유지 퍼널 ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """개선 후 재발(이탈) — my-wiki-04 최종 확정 정의(후보 B, analysis-005·006).

    config.RETENTION_STEPS 를 쓰지 않는다. 유지/재발의 정의 자체가 이미
    my-wiki-04에서 확정돼 있어 도메인마다 값이 달라지는 설정이 아니다.

        기준 모집단  2025년에 미비점이 발생했고, 그 통제(control_id)의
                    2025년 미비점에 대한 개선조치가 전부(all)
                    action_status == '완료'로 처리된 control_id
        유지        기준 모집단 중 2026년에 같은 control_id 에서
                    새 미비점이 발생하지 않은 통제
        재발        기준 모집단 중 2026년에 같은 control_id 에서
                    미비점이 다시 발생한 통제
                    (analysis-005 "개선 후 재발(C)" 집합과 동일)

    **metric-003(반복 미비점 통제, 11개)과는 다른 집합이다.** metric-003은
    완료 여부와 무관하게 두 연도 모두 미비점이 발생한 control_id 를 전부
    세지만, 여기서는 "2025년에 완료 처리됐다가 2026년에 다시 발생한" 것만
    센다 — 2025년에 아예 완료되지 않은 채 2026년까지 남은 통제(analysis-006
    "반복 미비점과의 차이"의 B-C 6개)는 기준 모집단에 들지 않아 재발로
    세지 않는다.

    그레인: 통제(control_id) 1개. 행(미비점) 수가 아니라 control_id 집합
    연산으로 판정하므로 같은 control_id 를 두 번 세지 않는다.

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]
        step="기준모집단"/"유지"/"재발" 3행. "유지"의 step_rate·cum_rate가
        곧 유지율이다. 유지+재발=기준모집단(배타적 분류)이며 재발이 유지의
        다음 단계로 이어지는 것은 아니다 — 기존 funnel_bars() 차트로
        그대로 표시하기 위해 같은 표 형식을 쓴다.
        rf.attrs["재발_control_id"] 에 재발 control_id 목록을 담아 둔다.
    """
    defi, rem = t["ic_deficiency"], t["ic_remediation"]

    d25 = defi[defi["year"] == 2025]
    r25 = rem[rem["deficiency_id"].isin(set(d25["deficiency_id"]))]
    merged = d25[["deficiency_id", "control_id"]].merge(
        r25[["deficiency_id", "action_status"]], on="deficiency_id", how="left")
    done_by_control = merged.groupby("control_id")["action_status"].apply(
        lambda s: bool((s == "완료").all()))
    population = set(done_by_control[done_by_control].index)

    d26_controls = set(defi.loc[defi["year"] == 2026, "control_id"])
    재발 = population & d26_controls
    유지 = population - d26_controls

    counts = {"기준모집단": len(population), "유지": len(유지), "재발": len(재발)}
    labels = {"기준모집단": "기준 모집단", "유지": "유지", "재발": "재발"}

    rows, prev, first = [], None, None
    for step in ["기준모집단", "유지", "재발"]:
        n = counts[step]
        if first is None:
            first = n
        step_rate = np.nan if prev is None else (n / prev if prev else np.nan)
        cum_rate = np.nan if not first else n / first
        drop = 0 if prev is None else prev - n
        rows.append({"step": step, "label": labels[step], "n": n,
                     "step_rate": step_rate, "cum_rate": cum_rate, "drop": drop})
        prev = n

    out = pd.DataFrame(rows)
    out["is_bottleneck"] = False
    valid = out["step_rate"].notna()
    if valid.any():
        out.loc[out.loc[valid, "step_rate"].idxmin(), "is_bottleneck"] = True
    out.attrs["재발_control_id"] = sorted(재발)
    return out


# ── KPI ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def kpis(t: dict, year: int | None = None) -> dict:
    """지표 카드 — 공식 지표 metric-001~004(my-wiki-04/06_metrics)를 그대로 계산한다.

    카드 값은 기본적으로 보유한 연도 중 **최근 연도**(현재 데이터는 2026)
    기준이다. year 를 주면 그 연도로 같은 정의를 그대로 재계산한다 —
    funnel(defi, rem, year=None)의 연도 파라미터와 같은 패턴이다(새 정의가
    아니라 같은 공식을 다른 연도에 적용하는 것뿐이다). KPI 카드 delta
    표시에 이전 연도 값이 필요할 때 이 파라미터로 재사용한다.
    metric-003(반복 미비점 통제 비율)만 연도별 값이 없고 보유 연도 전체를
    결합한 단일 스냅샷이다(공식 정의서에 이미 그렇게 확정돼 있다) —
    year 를 줘도 이 값은 바뀌지 않는다.

        metric-001 미해소 미비점 비율 = 미완료(action_status!='완료') 건수
            / 해당 연도 전체 미비점 건수 * 100        (낮을수록 좋음)
        metric-002 운영 적정률       = 적정 건수 / 해당 연도 전체 운영평가
            건수 * 100                                (높을수록 좋음)
        metric-003 반복 미비점 통제 비율 = 서로 다른 연도 2개 이상에서 미비점이
            발생한 control_id 수 / 미비점이 1건 이상 발생한 control_id 수 * 100
            (낮을수록 좋음, 연도 결합 스냅샷)
        metric-004 개선완료율        = 완료(action_status=='완료') 건수
            / 해당 연도 개선조치 착수 건수(=발생 건수) * 100  (높을수록 좋음)

    반환: {"지표이름": {"value": float, "unit": str, "fmt": str,
                       "분자": int, "분모": int, "방향성": str, "기준연도": str}}
          value·unit·fmt 는 기존 화면(kpi_card·status_of·스파크라인)이 그대로
          쓰는 키다. 분자·분모·방향성·기준연도는 추적용으로 덧붙인 키다.
    """
    defi, rem = t["ic_deficiency"], t["ic_remediation"]
    oa = t["ic_operating_assessment"]

    years = sorted(defi["year"].unique())
    latest = year if year is not None else years[-1]

    d = defi[defi["year"] == latest]
    dids = set(d["deficiency_id"])
    r = rem[rem["deficiency_id"].isin(dids)]
    발생 = len(d)
    완료 = int((r["action_status"] == "완료").sum())

    oa_y = oa[oa["year"] == latest]
    운영분모 = len(oa_y)
    운영적정 = int((oa_y["assessment_result"] == "적정").sum())

    g = defi.groupby("control_id")["year"].nunique()
    반복분모 = int((g >= 1).sum())
    반복분자 = int((g >= 2).sum())

    return {
        "미해소 미비점 비율": {
            "value": (발생 - 완료) / 발생 * 100 if 발생 else float("nan"),
            "unit": "%", "fmt": "{:.2f}%",
            "분자": 발생 - 완료, "분모": 발생, "방향성": "낮을수록 좋음",
            "기준연도": str(latest),
        },
        "운영 적정률": {
            "value": 운영적정 / 운영분모 * 100 if 운영분모 else float("nan"),
            "unit": "%", "fmt": "{:.2f}%",
            "분자": 운영적정, "분모": 운영분모, "방향성": "높을수록 좋음",
            "기준연도": str(latest),
        },
        "반복 미비점 통제 비율": {
            "value": 반복분자 / 반복분모 * 100 if 반복분모 else float("nan"),
            "unit": "%", "fmt": "{:.2f}%",
            "분자": 반복분자, "분모": 반복분모, "방향성": "낮을수록 좋음",
            "기준연도": f"{years[0]}~{years[-1]}",
        },
        "개선완료율": {
            "value": 완료 / 발생 * 100 if 발생 else float("nan"),
            "unit": "%", "fmt": "{:.2f}%",
            "분자": 완료, "분모": 발생, "방향성": "높을수록 좋음",
            "기준연도": str(latest),
        },
    }


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """월별 추이 — 미비점 발생 건수·개선완료 건수.

    새 지표를 만들지 않고, 이미 확정된 이벤트(미비점 발생·개선조치 완료)를
    월 단위로 센다. 완료 판정은 공식 정의(metric-004)와 동일하게
    action_status == '완료' 하나만 쓴다.

        미비점 발생  ic_deficiency.identified_date 기준
        개선완료     ic_remediation.completion_date 기준
                     (action_status == '완료' 인 행만 포함)

    범위는 config.PERIOD(2025-01~2026-12)를 그대로 쓰고, 발생·완료가 없는
    달도 0으로 채운다(빠뜨리지 않는다).

    반환: 인덱스가 월("YYYY-MM"), 열이 "미비점 발생"·"개선완료"인 DataFrame
    """
    defi, rem = t["ic_deficiency"], t["ic_remediation"]

    months = pd.period_range(
        pd.Timestamp(C.PERIOD[0]).to_period("M"),
        pd.Timestamp(C.PERIOD[1]).to_period("M"),
        freq="M",
    )

    occurred = to_dt(defi["identified_date"]).dt.to_period("M").value_counts()
    done = rem[rem["action_status"] == "완료"]
    completed = to_dt(done["completion_date"]).dt.to_period("M").value_counts()

    out = pd.DataFrame({
        "미비점 발생": [int(occurred.get(p, 0)) for p in months],
        "개선완료": [int(completed.get(p, 0)) for p in months],
    }, index=[str(p) for p in months])
    return out


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.
    이름이 config.THRESHOLDS 에 없으면 "none"을 돌려준다 — **"ok"가
    아니다.** 임계값이 아직 없다는 것과 정상 범위라는 것은 다른 말이다.
    "none"은 화면에서 "참고지표"로 표시된다(신뢰성 판정 보류의 "block"과는
    다른, 별도의 중립 상태다 — CLAUDE.md "참고지표 vs 판정 보류" 참고).
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "none"
    # ★ 높을수록 나쁜 지표. 내 지표 이름을 넣는다.
    higher_is_worse = {"이탈률", "이탈율", "해지율", "불량률", "반품률",
                       "미해소 미비점 비율"}
    if name in higher_is_worse:
        # metric-001 확정 경계는 이상/미만 포함이다(63.64 이상은 이미 경고).
        return ("block" if value >= th["위험"]
                else "warn" if value >= th["경고"] else "ok")
    return ("block" if value < th["위험"]
            else "warn" if value < th["경고"] else "ok")


# ── 실험 ──────────────────────────────────────────────────────────
# ★ 실험별로 어느 구간을 보는지. 도메인이 바뀌면 이 표를 갈아끼운다.
#   실험이 없는 도메인이면 비워 둔다.
EXP_STEPS: dict[str, tuple[str, str]] = {
    "EXP-001": ("랜딩방문", "요금제조회"),
    "EXP-002": ("요금제조회", "신청시작"),
    "EXP-003": ("신청시작", "신청완료"),
    "EXP-004": ("요금제조회", "신청시작"),
    "EXP-005": ("요금제조회", "신청시작"),
}


def _two_prop(sc, nc, stt, nt):
    """두 비율 비교. 차이·신뢰구간·p값을 함께 돌려준다.

    **그대로 쓴다.** 통계 계산은 도메인이 바뀌어도 같다.

    p값만 보면 '유의하지만 실질 효과가 없는' 경우를 놓친다.
    그래서 신뢰구간을 항상 함께 계산해 화면에 그린다.
    """
    rc, rt = sc / nc, stt / nt
    se = np.sqrt(rc * (1 - rc) / nc + rt * (1 - rt) / nt)
    if se == 0:
        return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=0, lo=0, hi=0, p=1.0, lift=0)
    z = (rt - rc) / se
    return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=rt - rc,
                lo=(rt - rc) - 1.96 * se, hi=(rt - rc) + 1.96 * se,
                p=2 * (1 - stats.norm.cdf(abs(z))),
                lift=(rt / rc - 1) if rc else 0)


def srm_check(asg: pd.DataFrame, exp_id: str) -> dict:
    """SRM(Sample Ratio Mismatch). 배정이 50:50인지 검정한다.

    **그대로 쓴다.** 7주차에 손으로 해본 그 계산이다.

    배정이 50:50이 아니면 배정 로직에 버그가 있다는 뜻이고,
    그 경우 어떤 효과가 나오든 해석할 수 없다.
    """
    a = asg[asg.experiment_id == exp_id]
    c = int((a.variant == "control").sum())
    t = int((a.variant == "treatment").sum())
    if c + t == 0:
        return {"ok": False, "c": 0, "t": 0, "p": 1.0, "ratio": (0.0, 0.0)}
    p = stats.chisquare([c, t]).pvalue
    return {"ok": p >= 0.001, "c": c, "t": t, "p": float(p),
            "ratio": (c / (c + t), t / (c + t))}


def trust_check(name: str, n: int, min_sample: int | None = None,
                observation_issue: bool = False, detail: str = "") -> dict:
    """계산보다 먼저 신뢰 여부를 판정한다. 호출자는 이 결과를 보고서야 비율을 계산한다.

    ★ Day3 실습 C. 원래 골격은 실험(SRM·배정) 게이트였지만, 이 데이터에는
    experiments·experiment_assignments 테이블 자체가 없어 SRM 개념이
    적용되지 않는다(config.TABLES 6종 중 실험 관련 테이블 없음). 대신
    my-wiki-04가 이미 확정한 신뢰도 기준 둘만 그대로 옮긴다.

    **판정이 계산보다 먼저다.** "계산해 놓고 화면에서 숨기는" 것이 아니라
    "못 믿으면 비율 자체를 계산하지 않는" 구조를 만들기 위한 판정 지점이다.
    호출자는 `trusted`가 False면 유지율·재발률·프로세스별 전환율 같은 비율을
    나누는 코드를 아예 실행하지 않고, 원시 건수와 `reason`만 보여준다.

        표본 부족  n < min_sample(생략하면 config.MIN_SAMPLE=20) 이면
                  trusted=False, level="block". **통계적 검정력을 보장하는
                  기준이 아니다** — 지금 프로젝트가 세부 분석을 해석할 때
                  쓰는 운영 기준일 뿐이다(my-wiki-04/03_analysis/
                  analysis-005 "최소 표본" 확정).
        관측기간  observation_issue=True 이면(표본은 충분해도) level="warn".
                  값 자체는 계산해 보여주되, 전년 대비 성과가 좋아졌다/
                  나빠졌다는 비교 판정에는 쓰지 않는다. 예) 2026년
                  개선조치의 target_date 가 2027년인 것은 아직 완료되지
                  않은 개선조치의 미래 목표일일 수 있다(analysis-005
                  "관측 기간 문제").

    반환: {"name", "n", "level"("ok"/"warn"/"block"), "message", "detail",
           "trusted": bool, "reason": str, "actual": int, "threshold": int,
           "observation_issue": bool}
          message 는 reason 의 별칭이다(기존 호출부 호환 — 새 필드가 늘었을
          뿐 이 두 키의 뜻은 바뀌지 않았다).
    """
    threshold = C.MIN_SAMPLE if min_sample is None else min_sample
    trusted = n >= threshold

    if not trusted:
        reason = f"표본 {n}건 (최소 {threshold}건)"
        level = "block"
    elif observation_issue:
        reason = ("관측기간 미성숙 — 전년 대비 성과 판정 보류"
                  + (f" ({detail})" if detail else ""))
        level = "warn"
    else:
        reason = f"표본 {n}건 (최소 {threshold}건 이상 충족)"
        level = "ok"

    return {
        "name": name, "n": n, "level": level, "message": reason, "detail": detail,
        "trusted": trusted, "reason": reason, "actual": n, "threshold": threshold,
        "observation_issue": observation_issue,
    }


@st.cache_data(show_spinner=False)
def experiment_results(t: dict) -> list[dict]:
    """실험 결과와 판정.

    **판정 순서가 이 함수의 전부다.** 믿을 수 있는지 먼저 묻고,
    믿을 수 있을 때만 계산한다.

    좋은 결과를 먼저 보면 경고를 무시하고 싶어진다. 그래서 사람의 규율에
    맡기지 않고 **코드로 순서를 박는다.**

    실험이 없는 도메인이면 이 함수는 빈 목록을 돌려준다. 대신 전후 비교
    카드를 만들되 **"인과 주장 불가"를 카드에 박아 둔다.** → DESIGN.md §4-4
    """
    if "experiments" not in t or "experiment_assignments" not in t:
        return []
    ex, asg, fe = t["experiments"], t["experiment_assignments"], t["funnel_events"]
    reach = {s: set(fe.loc[fe.funnel_step == s, "visitor_id"]) for s in C.FUNNEL_STEPS}
    out = []
    for _, e in ex.iterrows():
        eid = e.experiment_id
        srm = srm_check(asg, eid)
        n_total = int((asg.experiment_id == eid).sum())
        row = {
            "id": eid, "name": e.experiment_name, "hypothesis": e.hypothesis,
            "primary": e.primary_metric, "guardrail": e.guardrail_metric,
            "start": e.start_date, "end": e.end_date, "srm": srm,
        }

        # ★ 판정이 계산보다 먼저다. 못 믿으면 여기서 끝난다.
        reason = trust_check(srm, n_total)
        if reason:
            row["verdict"] = "무효"
            row["color"] = "block"
            row["reason"] = reason
            out.append(row)
            continue        # 지표를 계산하지 않는다. 숨기는 것이 아니다.

        # ── 여기부터 계산 ─────────────────────────────────────────
        if eid not in EXP_STEPS:
            row.update(verdict="데이터 없음", color="none",
                       reason="EXP_STEPS 에 이 실험의 구간이 없습니다.")
            out.append(row)
            continue
        sf, stp = EXP_STEPS[eid]
        a = asg[asg.experiment_id == eid][["visitor_id", "variant", "assigned_at"]]
        a = a[a.visitor_id.isin(reach[sf])]
        a = a.assign(conv=a.visitor_id.isin(reach[stp]).astype(int))
        g = a.groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(g) < 2:
            row.update(verdict="데이터 없음", color="none")
            out.append(row)
            continue
        r = _two_prop(g.loc["control", "sum"], g.loc["control", "count"],
                      g.loc["treatment", "sum"], g.loc["treatment", "count"])
        row.update(r, step_from=sf, step_to=stp, assignments=a)

        # 가드레일 — 주지표를 올리려 할 때 희생될 수 있는 것
        # ★ 아래는 통신사 컬럼(is_churned)이다. 내 가드레일 지표로 바꾼다.
        row["guard"] = None
        if "유지율" in str(e.guardrail_metric) and "customers" in t:
            cu = t["customers"]
            m = cu.merge(a[["visitor_id", "variant"]], on="visitor_id", how="inner")
            if len(m) and m.variant.nunique() == 2:
                ret = m.groupby("variant", observed=True).is_churned.mean()
                row["guard"] = {
                    "name": e.guardrail_metric,
                    "control": float(1 - ret["control"]),
                    "treatment": float(1 - ret["treatment"]),
                    "delta": float((1 - ret["treatment"]) - (1 - ret["control"])),
                }

        # 판정 — ★ 3%p 는 예시다. 내 가드레일 기준으로 바꾼다.
        sig = r["p"] < 0.05
        guard_bad = row["guard"] is not None and row["guard"]["delta"] < -0.03
        if guard_bad:
            # 주지표가 좋아져도 가드레일이 무너지면 성공이 아니다
            row.update(verdict="주의 필요", color="warn",
                       reason="주지표는 개선됐으나 가드레일이 악화됐습니다.")
        elif sig and r["lift"] > 0:
            row.update(verdict="성공", color="ok", reason="")
        elif sig:
            row.update(verdict="악화", color="block", reason="")
        else:
            row.update(verdict="효과 없음", color="none",
                       reason="통계적으로 유의한 차이가 없습니다.")
        out.append(row)
    return out


def peeking_curve(res: dict, start: str, cuts=(7, 14, 30, 60, 92)) -> pd.DataFrame:
    """관측 시점별 누적 결과. '그때 멈췄다면 무엇을 봤을까'를 재현한다.

    **그대로 쓴다.** 7주차에 겪은 조기 중단이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["d"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days
    rows = []
    for c in cuts:
        s = a[a.d <= c].groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(s) < 2 or s["count"].min() < 30:
            continue
        r = _two_prop(s.loc["control", "sum"], s.loc["control", "count"],
                      s.loc["treatment", "sum"], s.loc["treatment", "count"])
        rows.append({"cut": c, "lift": r["lift"], "p": r["p"], "sig": r["p"] < 0.05})
    return pd.DataFrame(rows)


def weekly_effect(res: dict, start: str, bucket_days: int = 14) -> pd.DataFrame:
    """기간을 쪼개 효과 추이를 본다. 신규성 효과는 전체 평균에 가려진다.

    **그대로 쓴다.** 7주차에 겪은 그것이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["b"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days // bucket_days
    g = (a[a.b >= 0].groupby(["b", "variant"], observed=True).conv
         .mean().unstack().dropna())
    if g.empty:
        return pd.DataFrame()
    g["lift"] = g.treatment / g.control - 1
    g = g.reset_index()
    g["label"] = g.b.apply(lambda i: f"{int(i)*2+1}~{int(i)*2+2}주")
    return g


# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def channel_efficiency(t: dict) -> pd.DataFrame:
    """비용만 보면 순위가 뒤집힌다. 유지율까지 반영한 유효 비용을 함께 낸다.

    ★ Day3 선택 과제입니다. 안 만들어도 나머지가 돕니다.

    획득 비용이 싼 경로가 실제로 싼 것이 아니다 —
    데려온 대상이 남지 않으면 같은 자리를 다시 채워야 한다.

        유효 비용 = 획득 비용 / 유지율

    비용 개념이 없으면 **투입 공수(인시)**로 해도 된다.
    획득 경로 구분이 없으면 이 함수를 지운다.

    ★ 여기 쓰이는 CHANNEL_CAC 는 **가정값**이다. 광고비 실측 테이블에서
      유도하지 않는다 — 광고비는 개인 단위로 추적되지 않아 가입과 이을 수 없다.
      리포트에 이 값이 들어가면 "가정값 기반"을 문장에 남긴다. → DESIGN.md §4-3

    반환: DataFrame[채널, 방문, 가입, 전환율, CAC, 유지율, 유효CAC, 역전]
    """
    todo("Day3 선택 과제", "채널 효율",
         "내 도메인에 획득 경로 구분이 있습니까? 비용이 없으면 투입 공수로 바꾸십시오.",
         "core/metrics.py  channel_efficiency()")
