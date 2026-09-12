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


# ── 제안서 후보 주제 ────────────────────────────────────────────────
# ★ 판정이 계산보다 먼저다(trust_check()와 같은 원칙). 표본 미달·관측기간
#   미도래·임계값 미정의 등으로 못 믿는 비교는 후보 자체를 만들지 않는다 —
#   "비교는 가능하지만 우선순위를 낮출 근거가 있다"(후보로 남기고 기각사유를
#   채운다)와 "애초에 비교할 수 없다"(후보를 만들지 않는다)를 섞지 않는다.
#   우선순위를 낮출 공식 기준(config·판단기준)이 아직 없으므로, 지금은
#   신뢰 가능한 비교를 임의로 기각하지 않고 전부 후보로 남긴다.


def _annual_factor() -> float | None:
    """config.PERIOD(고정 범위)만으로 연간 환산 배수를 구한다. datetime.now/today는 쓰지 않는다."""
    start, end = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    days = (end - start).days + 1
    return 365.0 / days if days > 0 else None


def _funnel_bottleneck_candidate(defi: pd.DataFrame, rem: pd.DataFrame,
                                 annual_factor: float | None):
    """Track B(funnel()) 중 가장 낮은 전환율 구간과 그다음으로 낮은 구간의 격차.

    funnel()이 이미 계산한 값을 그대로 읽기만 한다(새 계산 없음). 유효한
    step_rate가 2개 미만이면(비교 대상 자체가 없으면) 후보를 만들지 않는다.
    """
    f = funnel(defi, rem, year=None)
    valid = f[f["step_rate"].notna()]
    if len(valid) < 2:
        return None, [{"근거축": "Track B 단계", "사유": "비교 가능한 단계 전환율이 2개 미만"}]

    srt = valid.sort_values("step_rate")
    lowest, second = srt.iloc[0], srt.iloc[1]
    idx = int(f.index[f["step"] == lowest["step"]][0])
    prev_n, cur_n = int(f["n"].iloc[idx - 1]), int(f["n"].iloc[idx])
    tc = trust_check(f"Track B {f['label'].iloc[idx - 1]}→{lowest['label']}", prev_n)
    if not tc["trusted"]:
        return None, [{"근거축": "Track B 단계", "사유": tc["reason"]}]

    gap = float(second["step_rate"] - lowest["step_rate"])
    loss_n = prev_n - cur_n
    규모 = round(loss_n * annual_factor, 1) if annual_factor is not None else None
    developing = _observation_caveat(defi, rem)
    topic = {
        "키": "funnel_bottleneck",
        "제목": f"Track B 병목 구간 — {f['label'].iloc[idx - 1]} → {lowest['label']}",
        "한줄": (f"{f['label'].iloc[idx - 1]} → {lowest['label']} 전환율이 "
                f"{lowest['step_rate'] * 100:.2f}%로 가장 낮다"
                f"({second['label']} 구간 {second['step_rate'] * 100:.2f}% 대비 "
                f"{gap * 100:.2f}%p 낮음)."),
        "규모_연간건수": 규모,
        "근거축": "Track B 단계(funnel(), 전체 연도 결합)",
        "구간": f"{C.PERIOD[0]}~{C.PERIOD[1]}(결합)",
        "기각사유": None,
        "표본": prev_n,
        "신뢰판정": tc,
        "격차_pp": round(gap * 100, 2),
    }
    if developing:
        topic["관측기간_주의"] = developing
    return topic, []


def _observation_caveat(defi: pd.DataFrame, rem: pd.DataFrame) -> str | None:
    """전체 결합 Track B 값에 관측기간이 덜 찬 코호트가 섞여 있으면 주의 문구를 만든다.

    새 판정을 만들지 않고, 이미 있는 trust_check(observation_issue=...) 문구를
    그대로 재사용한다. 관측기간 문제가 없으면 None.
    """
    years = sorted(defi["year"].unique())
    if not years:
        return None
    latest = years[-1]
    d_latest = defi[defi["year"] == latest]
    r_latest = rem[rem["deficiency_id"].isin(set(d_latest["deficiency_id"]))]
    future = int((r_latest["target_date"].astype(str).str[:4] > str(latest)).sum())
    if not future:
        return None
    tc = trust_check(f"{latest}년 코호트 관측기간", len(r_latest),
                     observation_issue=True,
                     detail=f"{len(r_latest)}건 중 {future}건은 target_date가 {latest}년 이후")
    return tc["reason"]


def _segment_candidates(t: dict, annual_factor: float | None):
    """config.FUNNEL_DIMS에 정의된 분해 축을 순회해 최고/최저 셀을 비교한다.

    funnel_by()가 실제로 바르게 지원하는 축은 process_name(및 동일 파티션인
    process_id)뿐이다 — 다른 dim은 에러를 내거나 process_name으로 조용히
    대체되므로(별도 확인됨) 여기서 새로 시도하지 않는다. 이 프로젝트
    config.py에는 FUNNEL_DIMS 자체가 없어 실제로 쓰이는 process_name으로
    대신한다(새 config 값을 만들지 않는다).
    """
    dims = getattr(C, "FUNNEL_DIMS", None) or ["process_name"]
    candidates, excluded = [], []
    last_step = C.FUNNEL_STEPS[-1]
    first_step = C.FUNNEL_STEPS[0]

    for dim in dims:
        if dim not in ("process_name", "process_id"):
            excluded.append({"근거축": dim,
                             "사유": "funnel_by()가 이 축을 정상 지원하지 않음(process_name/process_id만 지원)"})
            continue

        g = funnel_by(t, dim)
        trusted_cells = []
        for _, row in g[g["step"] == last_step].iterrows():
            발생n = int(g.loc[(g[dim] == row[dim]) & (g["step"] == first_step), "n"].iloc[0])
            tc = trust_check(f"{dim}={row[dim]} 전환율", 발생n)
            if tc["trusted"]:
                trusted_cells.append((row[dim], float(row["step_rate"]), 발생n))
            else:
                excluded.append({"근거축": f"{dim}={row[dim]}", "사유": tc["reason"]})

        if len(trusted_cells) < 2:
            continue  # 신뢰 가능한 셀이 2개 미만이면 비교 자체가 성립하지 않는다

        trusted_cells.sort(key=lambda c: c[1])
        worst, best = trusted_cells[0], trusted_cells[-1]
        gap = best[1] - worst[1]
        total_n = int(g[g["step"] == first_step]["n"].sum())
        비중 = worst[2] / total_n if total_n else None
        규모 = (round(gap * 비중 * total_n * annual_factor, 1)
               if (비중 is not None and annual_factor is not None) else None)
        candidates.append({
            "키": f"segment_{dim}",
            "제목": f"{dim}별 개선조치 완료 전환율 격차",
            "한줄": (f"{dim}={worst[0]}의 완료 전환율이 {worst[1] * 100:.2f}%로 "
                    f"가장 낮고, {dim}={best[0]}({best[1] * 100:.2f}%)와 "
                    f"{gap * 100:.2f}%p 차이(신뢰 가능한 셀 {len(trusted_cells)}개 기준)."),
            "규모_연간건수": 규모,
            "근거축": dim,
            "구간": f"{C.PERIOD[0]}~{C.PERIOD[1]}(결합)",
            "기각사유": None,
            "표본": {"최저": worst, "최고": best},
            "신뢰판정": {"trusted_cells": len(trusted_cells)},
        })
    return candidates, excluded


def _threshold_candidates(t: dict, annual_factor: float | None):
    """config.THRESHOLDS에 이미 등록된 임계값만 확인한다. 새 경고/위험선을 만들지 않는다."""
    candidates, checked = [], []
    years = sorted(t["ic_deficiency"]["year"].unique())
    for th_name, th in C.THRESHOLDS.items():
        for yr in years:
            k = kpis(t, year=yr)
            v = k.get(th_name)
            if not v:
                continue
            val = v["value"]
            state = status_of(th_name, val)
            checked.append({"지표": th_name, "연도": yr, "값": val, "상태": state})
            if state not in ("warn", "block"):
                continue  # 실제로 임계값을 벗어난 경우에만 후보로 검토한다
            tc = trust_check(f"{th_name}({yr})", v["분모"])
            if not tc["trusted"]:
                continue  # 표본 미달이면 감춘 값을 되살리지 않는다(후보로 만들지 않음)
            선 = th["위험"] if state == "block" else th["경고"]
            격차 = val - 선
            규모 = (round(v["분모"] * annual_factor, 1)
                   if annual_factor is not None else None)
            candidates.append({
                "키": f"threshold_{th_name}_{yr}",
                "제목": f"{th_name}({yr}) 임계값 이탈",
                "한줄": (f"{yr}년 {th_name}이 {val:.2f}%로 "
                        f"{'위험선' if state == 'block' else '경고선'}"
                        f"({선:.2f}%)을 {'상회' if th_name in ('미해소 미비점 비율',) else '이탈'}했다."),
                "규모_연간건수": 규모,
                "근거축": f"{th_name}(config.THRESHOLDS)",
                "구간": str(yr),
                "기각사유": None,
                "표본": v["분모"],
                "신뢰판정": tc,
                "상태": state,
                "격차_pp": round(격차, 2),
            })
    return candidates, checked


def _trend_candidates(t: dict):
    """monthly()의 연도별 합계로 최근 구간과 직전 구간을 비교한다.

    비교 구간은 config.PERIOD 안의 연도 경계로만 정한다(현재 시각 사용 안 함).
    완료 여부가 걸린 지표(개선완료)는 관측기간이 덜 찬 코호트를 포함하므로
    추세 후보로 만들지 않는다 — 발생 건수(identified_date 기준)만 다룬다.
    """
    m = monthly(t)
    years = sorted({idx[:4] for idx in m.index})
    candidates, excluded = [], []
    if len(years) < 2:
        return candidates, [{"근거축": "monthly 추세", "사유": "비교 가능한 연도가 2개 미만"}]

    직전연도, 최근연도 = years[-2], years[-1]
    for col, blocked_by_observation in (("미비점 발생", False), ("개선완료", True)):
        직전값 = int(m.loc[[i for i in m.index if i.startswith(직전연도)], col].sum())
        최근값 = int(m.loc[[i for i in m.index if i.startswith(최근연도)], col].sum())
        총n = 직전값 + 최근값
        tc = trust_check(f"{col} 추세({직전연도}→{최근연도})", 총n)
        if not tc["trusted"]:
            excluded.append({"근거축": f"{col} 추세", "사유": tc["reason"]})
            continue
        if blocked_by_observation:
            excluded.append({"근거축": f"{col} 추세",
                             "사유": ("완료 여부는 target_date 미도래 코호트를 포함해 "
                                     "관측기간이 덜 찼다 — 추세 비교 후보로 만들지 않는다")})
            continue

        격차 = 최근값 - 직전값
        # 격차 크기로 기각할 공식 기준(config·판단기준)이 아직 없다 — 임의로
        # "작다"고 판단해 기각하지 않고, 신뢰 가능한 비교는 그대로 후보로 남긴다.
        기각사유 = None
        candidates.append({
            "키": f"trend_{col}",
            "제목": f"{col} 추세 — {직전연도}년 대비 {최근연도}년",
            "한줄": (f"{col}이 {직전연도}년 {직전값}건에서 {최근연도}년 {최근값}건으로 "
                    f"{abs(격차)}건 {'감소' if 격차 < 0 else '증가'}했다."),
            "규모_연간건수": None,
            "근거축": "monthly() 연도별 집계(identified_date 기준)",
            "구간": f"{직전연도}(전체) vs {최근연도}(전체)",
            "기각사유": 기각사유,
            "표본": {직전연도: 직전값, 최근연도: 최근값},
            "신뢰판정": tc,
            "규모_계산_불가_사유": ("비중(상위 모집단 대비 비율) 개념이 없는 단일 전체 "
                              "집계 차이라 격차×비중×연간건수 공식을 적용할 근거가 없음"),
        })
    return candidates, excluded


def _topic_sort_key(topic: dict):
    """규모가 계산된 비기각 후보 우선(규모 큰 순) → 규모 None인 비기각 후보 →
    기각된 후보는 항상 뒤(그 안에서는 원래 순서 유지, 삭제하지 않는다)."""
    rejected = 1 if topic.get("기각사유") else 0
    규모 = topic.get("규모_연간건수")
    has_size = 0 if 규모 is not None else 1
    return (rejected, has_size, -규모 if 규모 is not None else 0)


@st.cache_data(show_spinner=False)
def proposal_topics(t: dict) -> list[dict]:
    """제안서용 주제 후보 여러 개를 만든다. Track B 병목(A)·분해 축(B)·
    임계값 이탈(C)·추세(D) 네 경로를 확인하고, 신뢰 가능한 비교만 후보로
    남긴다("계산해서 숨기기"가 아니라 "못 믿으면 후보 자체를 만들지 않기").

    "비교할 수 없음"(표본 미달·관측기간 미도래·축 미지원 등 — 후보 자체를
    만들지 않음)과 "비교는 가능하지만 우선순위가 낮음"(후보는 남기고
    기각사유를 채움)을 구분한다. 기각된 후보를 지우지 않는다. 우선순위를
    낮출 공식 기준이 아직 없으면 임의로 기각하지 않는다. 후보 5개를
    채우려고 신뢰 기준을 완화하지 않는다 — 표본 부족이면 후보 수가 적어도
    그대로 둔다.

    기존 계산 함수(funnel·funnel_by·kpis·monthly·trust_check·status_of)의
    결과만 읽으며, 새 지표·새 임계값을 만들지 않는다. datetime.now()/today()는
    쓰지 않고 config.PERIOD 고정 범위만으로 기간을 정한다.
    """
    defi, rem = t["ic_deficiency"], t["ic_remediation"]
    af = _annual_factor()

    topics: list[dict] = []

    bottleneck, _ = _funnel_bottleneck_candidate(defi, rem, af)
    if bottleneck:
        topics.append(bottleneck)

    seg_topics, _ = _segment_candidates(t, af)
    topics.extend(seg_topics)

    th_topics, _ = _threshold_candidates(t, af)
    topics.extend(th_topics)

    trend_topics, _ = _trend_candidates(t)
    topics.extend(trend_topics)

    topics.sort(key=_topic_sort_key)
    return topics


# ── 주제 근거 ────────────────────────────────────────────────────────
# ★ topic_evidence()는 조회·구조화만 한다. 문장(보고서·제안 문장)을 만들지
#   않고, 인과 해석·우선순위 판단·새 임계값도 만들지 않는다 — 그 일은
#   report/proposal.py 쪽 사람 절의 몫이다.
def _evidence_status(defi: pd.DataFrame, rem: pd.DataFrame) -> dict:
    """현황 — Track B 퍼널 전체를 funnel() 결과 그대로 재구성한다(새 계산 없음)."""
    f = funnel(defi, rem, year=None)
    rows = [{
        "단계": r["label"],
        "도달": int(r["n"]),
        "전환율": None if pd.isna(r["step_rate"]) else round(float(r["step_rate"]), 4),
        "병목여부": bool(r["is_bottleneck"]),
    } for _, r in f.iterrows()]
    return {"값": rows, "사유": None}


def _evidence_cause(t: dict, topic: dict) -> dict:
    """원인 — 신뢰 가능한 분해축 근거가 있을 때만 반환한다.

    현재 프로젝트는 process_name 세그먼트가 전부 최소표본 미달이라(이미
    trust_check()로 확인됨) 대부분의 주제는 여기서 값=None을 돌려준다.
    trust_check를 통과하지 못한 칸은 이 함수 안에서도 절대 만들지 않는다
    (감춰진 세그먼트 비율을 다시 노출하지 않는다).
    """
    key = topic.get("키", "")
    if not key.startswith("segment_"):
        return {"값": None,
               "사유": ("이 주제는 분해축(세그먼트) 비교에서 나온 것이 아니다 — "
                        "process_name 세그먼트는 전부 최소표본 미달(n=3~12 < "
                        f"{C.MIN_SAMPLE})로 판정 보류 상태라 별도 원인 분해 근거가 없다.")}

    dim = key[len("segment_"):]
    if dim not in ("process_name", "process_id"):
        return {"값": None, "사유": f"funnel_by()가 '{dim}' 축을 정상 지원하지 않는다."}

    g = funnel_by(t, dim)
    last_step, first_step = C.FUNNEL_STEPS[-1], C.FUNNEL_STEPS[0]
    cells = []
    for _, row in g[g["step"] == last_step].iterrows():
        발생n = int(g.loc[(g[dim] == row[dim]) & (g["step"] == first_step), "n"].iloc[0])
        tc = trust_check(f"{dim}={row[dim]} 전환율", 발생n)
        if tc["trusted"]:  # 신뢰 실패 칸은 여기 리스트에 아예 들어오지 않는다
            cells.append({"칸": row[dim], "도달": 발생n, "전환": int(row["n"]),
                          "전환율": round(float(row["step_rate"]), 4)})

    if len(cells) < 2:
        return {"값": None,
               "사유": (f"'{dim}' 세그먼트는 신뢰 가능한(n≥{C.MIN_SAMPLE}) 칸이 "
                        f"{len(cells)}개뿐이라 최고/최저 비교가 성립하지 않는다.")}

    total = sum(c["도달"] for c in cells)
    for c in cells:
        c["비중"] = round(c["도달"] / total, 4) if total else None
    cells.sort(key=lambda c: c["전환율"])
    cells[0]["최저"], cells[-1]["최고"] = True, True
    return {"값": cells, "사유": None}


def _evidence_scale(t: dict, topic: dict) -> dict:
    """규모 — 실측값과 연간 환산값을 분리해서 돌려준다. proposal_topics()가 이미
    계산한 값을 우선 재사용하고, Track B 병목만 실측(손실 건수)을 별도로
    다시 조회한다(새 비율은 만들지 않는다 — funnel()이 이미 낸 n을 뺄 뿐이다).
    """
    key = topic.get("키", "")
    af = _annual_factor()

    if key == "funnel_bottleneck":
        defi, rem = t["ic_deficiency"], t["ic_remediation"]
        f = funnel(defi, rem, year=None)
        bott_idx = int(f.index[f["is_bottleneck"]][0])
        if bott_idx == 0:
            return {"실측": None, "연간환산": None, "가정": [],
                    "계산불가사유": "병목 구간에 이전 단계가 없다"}
        prev_n, cur_n = int(f["n"].iloc[bott_idx - 1]), int(f["n"].iloc[bott_idx])
        손실 = prev_n - cur_n
        if af is None:
            return {"실측": 손실, "연간환산": None, "가정": [],
                    "계산불가사유": "config.PERIOD로 연간 환산 배수를 계산할 수 없다"}
        가정 = [
            f"config.PERIOD({C.PERIOD[0]}~{C.PERIOD[1]}) 전체 기간을 연 365일 기준으로 "
            f"균등 환산했다(배수 {af:.4f}).",
            "Track B는 발생=착수(1:1, 현재 데이터)라 병목 구간 손실을 전체 모집단 대비 "
            "비중 1.0으로 취급했다.",
        ]
        return {"실측": 손실, "연간환산": round(손실 * af, 1), "가정": 가정, "계산불가사유": None}

    if key.startswith("trend_"):
        return {"실측": topic.get("표본"), "연간환산": None, "가정": [],
                "계산불가사유": topic.get(
                    "규모_계산_불가_사유",
                    "비중(상위 모집단 대비 비율) 개념이 없어 격차×비중×연간건수 공식을 "
                    "적용할 근거가 없다")}

    # segment_*/threshold_* — proposal_topics()가 이미 계산해 둔 값을 그대로 옮긴다
    규모 = topic.get("규모_연간건수")
    if 규모 is None:
        return {"실측": topic.get("표본"), "연간환산": None, "가정": [],
                "계산불가사유": "이 주제는 규모_연간건수를 계산하지 못했다(비중 또는 "
                              "연간 환산 배수 근거 부족)"}
    return {"실측": topic.get("표본"), "연간환산": 규모,
            "가정": ["config.PERIOD 전체 기간을 연 365일 기준으로 균등 환산했다."],
            "계산불가사유": None}


def _evidence_trend(t: dict, topic: dict) -> dict:
    """추세 — monthly()의 최근 12개월(config.PERIOD 안, datetime 미사용)을 돌려준다.

    완료 여부가 걸린 월별 지표(개선완료)는 target_date 미도래 코호트를 포함해
    관측기간이 덜 찼으므로 추세 근거로 만들지 않는다(발생 건수만 허용).
    """
    key = topic.get("키", "")
    if key.startswith("trend_"):
        col = key[len("trend_"):]
    elif key == "funnel_bottleneck":
        col = "개선완료"  # Track B 완료 단계와 가장 가까운 monthly() 컬럼
    else:
        col = None

    if col not in ("미비점 발생", "개선완료"):
        return {"값": None, "사유": "이 주제와 안전하게 연결할 monthly() 지표가 없다"}

    if col == "개선완료":
        return {"값": None,
               "사유": ("개선완료 월별 추이는 target_date 미도래 코호트를 포함해 관측기간이 "
                        "덜 찼다 — 추세 근거로 안전하게 쓸 수 없다")}

    m = monthly(t)  # 이미 config.PERIOD 범위·결측월 0채움이 반영된 결과 — monthly()는 바꾸지 않는다
    last12 = m[col].iloc[-12:]

    # monthly()는 결측월도 0으로 채운다(다른 화면이 이 규약에 기대므로 monthly()
    # 자체는 그대로 둔다). 다만 "실제로 0건 관측"과 "원본에 그 달 레코드 자체가
    # 없어 구분 불가"는 다른 상태다 — 여기서만 원본 날짜 컬럼(identified_date)을
    # 다시 확인해, 레코드가 전혀 없는 달은 0으로 단정하지 않고 제외한다.
    present_months = set(
        to_dt(t["ic_deficiency"]["identified_date"]).dt.strftime("%Y-%m").dropna())

    rows = [{"월": ym, "값": int(v)} for ym, v in last12.items() if ym in present_months]
    if not rows:
        return {"값": None, "사유": "최근 12개월 안에 원본(identified_date) 레코드가 있는 달이 없다"}
    return {"값": rows, "사유": None}


def topic_evidence(t: dict, topic: dict) -> dict:
    """proposal_topics()가 고른 주제 하나의 근거(현황·원인·규모·추세)를 한 번에 모은다.

    조회·구조화만 한다 — 보고서/제안 문장을 만들지 않고, 인과 해석·우선순위
    판단·새 임계값도 만들지 않는다. 근거가 없으면 값=None과 구체적 사유를
    함께 돌려준다(추정·생성 금지). 기존 funnel/funnel_by/kpis/monthly/
    trust_check/proposal_topics()는 호출만 하고 수정하지 않는다.
    """
    defi, rem = t["ic_deficiency"], t["ic_remediation"]
    return {
        "현황": _evidence_status(defi, rem),
        "원인": _evidence_cause(t, topic),
        "규모": _evidence_scale(t, topic),
        "추세": _evidence_trend(t, topic),
        "메타": {"키": topic.get("키"), "제목": topic.get("제목"),
                "근거축": topic.get("근거축"), "구간": topic.get("구간")},
    }


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
