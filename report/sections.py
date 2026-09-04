# -*- coding: utf-8 -*-
"""리포트 8장 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 장과 사람이 쓰는 장이 나뉜다. 가르는 질문은 하나다.

    이 문장이 틀렸을 때 누가 책임지는가?
        사람이 진다        → 사람이 쓴다   (2 배경 · 6 해석 · 8 제안)
        사실이 틀린 것뿐   → 자동으로 쓴다 (1 요약 · 3 방법 · 4 결과 · 5 개선·재발 · 7 한계)

**해석과 제안을 자동화하는 순간 책임이 사라진다.** 그것이 이 수업의 결론이다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime

from core import config as C, metrics as M, validate as V
from core.todo import todo

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#   내 도메인에만 있는 단정 표현이 있으면 여기에 더한다.
BANNED = ["때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히",
          "원인이다", "유발했다", "영향을 미쳤다", "기여했다", "창출했다"]


def check_phrasing(text: str) -> list[str]:
    """자동 생성 문장에 인과 단정 표현이 섞였는지 스스로 검사한다.

    **그대로 쓴다.** 사람이 쓴 장에도 걸어라 — 사람이 더 자주 쓴다.
    """
    return [w for w in BANNED if w in text]


# ★ 신뢰성 기준(trust_check)으로 감춘 파생 비율. 값이 바뀌면 이 목록도
#   갱신한다(BANNED와 같은 방식 — 도메인이 바뀌면 사람이 고친다).
HIDDEN_RATIOS = ["66.67%", "33.33%", "28.57%", "46.67%", "18.10%",
                 "71.43%", "8.57%p"]


def find_hidden_leaks(secs: list[dict]) -> list[str]:
    """신뢰성 기준으로 감춘 파생 비율이 리포트 본문에 다시 나타났는지 확인한다.

    게이트 3 최종 점검에서 쓴다. 8장 전체(자동+사람) body를 합쳐서 검사한다.
    """
    all_text = " ".join((s.get("body") or "") for s in secs)
    return [r for r in HIDDEN_RATIOS if r in all_text]


def _fmt(n, unit=""):
    return f"{n:,.0f}{unit}"


# ── 자동으로 쓰는 장 ──────────────────────────────────────────────
def _s1_summary(t: dict) -> dict:
    """1. 요약 — 지표 4종 + Track B + 개선 후 재발 헤드라인.

    수치만 나열하고 원인은 쓰지 않는다. 원인 해석은 6장, 대응은 8장에서
    사람이 쓴다.
    """
    k = M.kpis(t)
    f = M.funnel(t["ic_deficiency"], t["ic_remediation"])
    rf = M.retention_funnel(t)

    미해소, 운영, 반복, 완료율 = (k["미해소 미비점 비율"], k["운영 적정률"],
                              k["반복 미비점 통제 비율"], k["개선완료율"])
    발생, 착수, 완료 = f["n"].tolist()
    모집단, 유지, 재발 = rf["n"].tolist()

    body = (
        f"{미해소['기준연도']}년 기준 미해소 미비점 비율은 "
        f"{미해소['value']:.2f}%({미해소['분자']}/{미해소['분모']})이고, "
        f"개선완료율은 {완료율['value']:.2f}%({완료율['분자']}/{완료율['분모']})다. "
        f"운영 적정률은 {운영['value']:.2f}%({운영['분자']}/{운영['분모']})이고, "
        f"반복 미비점 통제 비율은 {반복['기준연도']} 결합 기준 "
        f"{반복['value']:.2f}%({반복['분자']}/{반복['분모']})다.\n\n"

        f"Track B(미비점 개선 파이프라인)는 미비점 발생 {_fmt(발생)}건 → "
        f"개선조치 착수 {_fmt(착수)}건 → 개선조치 완료 {_fmt(완료)}건으로 "
        f"이어진다. 착수 대비 완료 비율은 {완료 / 착수 * 100:.2f}%다.\n\n"

        f"개선 후 재발 분석(2025년 미비점의 개선조치가 전부 완료 처리된 "
        f"통제 {_fmt(모집단)}개 기준)에서는 유지 {_fmt(유지)}개, 재발 "
        f"{_fmt(재발)}개로 나뉜다. 이 판정 모집단({_fmt(모집단)}개)은 "
        f"최소표본 기준({C.MIN_SAMPLE}개)에 못 미친다.\n\n"

        "위 수치는 결과 나열이며, 원인 해석과 대응 방향은 6장(해석)과 "
        "8장(제안)에서 사람이 판단한다."
    )
    return {"title": "1. 요약", "kind": "auto", "body": body}


def _s3_method(t: dict) -> dict:
    """3. 방법 — 분석 단위(그레인)와 포함·제외 조건을 밝힌다.

    지표 정의는 my-wiki-04/06_metrics(metric-001~004)가 원본이다.
    여기서 새로 정의하지 않는다.
    """
    years = sorted(t["ic_deficiency"]["year"].unique())
    body = (
        f"분석 대상 기간은 {years[0]}~{years[-1]}년, 대상 데이터는 "
        f"{C.DATASET} raw 테이블 6종(ic_process_master·ic_control_master·"
        "ic_design_assessment·ic_operating_assessment·ic_deficiency·"
        "ic_remediation)이다. 지표 정의는 my-wiki-04/06_metrics의 "
        "metric-001~004(.yaml)를 그대로 따르며, 이 리포트는 새 정의를 "
        "만들지 않는다.\n\n"

        "그레인(분석 단위)은 지표마다 다르다. 미해소 미비점 비율· "
        "개선완료율·Track B 퍼널은 미비점 1건(deficiency_id) 단위로 "
        "센다. 반복 미비점 통제 비율은 통제(control_id) 단위로, 서로 "
        "다른 연도 2개 이상에서 미비점이 발생했는지를 센다. 개선 후 "
        "재발 분석도 통제(control_id) 단위이며, 미비점 발생 건수가 "
        "아니라 통제 수로 판정한다.\n\n"

        "포함·제외 조건은 위키 정의서와 동일하게 적용했다. 미해소 "
        "미비점 비율·개선완료율·반복 미비점 통제 비율은 "
        "deficiency_type(운영미비·설계미비) 구분 없이 전체를 포함하며, "
        "별도로 제외한 행은 없다. 개선 후 재발 분석은 2025년 미비점이 "
        "있었던 통제 중 그 개선조치가 전부(all) 완료 처리된 통제만 "
        "판정 모집단으로 삼는다 — 2025년에 완료되지 않은 채 남은 통제는 "
        "유지·재발 어느 쪽으로도 세지 않는다.\n\n"

        "결측·중복은 my-wiki-04에서 이미 재검증됐다(계산에 쓰는 컬럼에 "
        "결측 없음, deficiency_id·remediation_id 1:1). 이 리포트는 이 "
        "재검증 결과를 그대로 신뢰하고 별도의 결측 처리 로직을 추가하지 "
        "않았다.\n\n"

        "가설 검정이나 실험 설계는 쓰지 않았다. 무작위 배정 데이터가 "
        "없어 관찰 데이터 비교만 가능하며, 이 리포트의 모든 수치는 "
        "기술 통계(descriptive statistics)다."
    )
    return {"title": "3. 방법", "kind": "auto", "body": body}


def _s4_results(t: dict) -> dict:
    """4. 결과 — 숫자만 나열한다. 해석은 6장.

    charts 키에 차트 이름을 넣으면 화면·PDF에 함께 그려진다.
    """
    k = M.kpis(t)
    f_all = M.funnel(t["ic_deficiency"], t["ic_remediation"])
    f25 = M.funnel(t["ic_deficiency"], t["ic_remediation"], year=2025)
    f26 = M.funnel(t["ic_deficiency"], t["ic_remediation"], year=2026)
    rf = M.retention_funnel(t)
    g_long = M.funnel_by(t, "process_name")

    미해소, 운영, 반복, 완료율 = (k["미해소 미비점 비율"], k["운영 적정률"],
                              k["반복 미비점 통제 비율"], k["개선완료율"])
    발생, 착수, 완료 = f_all["n"].tolist()
    bn = f_all.loc[f_all.is_bottleneck, "label"].iloc[0]
    모집단, 유지, 재발 = rf["n"].tolist()

    # 판단이 계산보다 먼저다 — trusted가 아니면 비율을 나누지 않는다.
    tc_retention = M.trust_check("개선 후 재발 분석", 모집단)
    if tc_retention["trusted"]:
        retention_line = (
            f"유지 {_fmt(유지)}개({유지 / 모집단 * 100:.2f}%), 재발 "
            f"{_fmt(재발)}개({재발 / 모집단 * 100:.2f}%)다.")
    else:
        retention_line = (
            f"유지 {_fmt(유지)}개, 재발 {_fmt(재발)}개다(원시 건수). "
            f"{tc_retention['reason']}으로 유지율·재발률 비율 판정은 "
            "보류한다.")

    # 프로세스별 발생 건수(원시) — funnel_by()가 이미 계산한 값을 그대로
    # 옮긴다. 최소표본(20건) 미만인 프로세스는 전환율을 계산하지 않는다.
    발생by = (g_long[g_long.step == "미비점발생"]
              .set_index("process_name")["n"].sort_index())
    합계확인 = int(발생by.sum())
    프로세스목록 = "·".join(f"{p} {n}건" for p, n in 발생by.items())
    process_line = (
        f"프로세스별 발생 건수: {프로세스목록}(합계 {합계확인}건 = 전체 "
        f"{발생}건 {'일치' if 합계확인 == 발생 else '불일치(확인 필요)'}). "
        f"모든 프로세스가 최소표본({C.MIN_SAMPLE}건) 미만이라 프로세스별 "
        "전환율 비교는 판정 보류하며 아래 차트는 표시되지 않는다."
    )

    tc_stock = M.trust_check("재고 프로세스 운영 적정률(2026)", 7)
    tc_key = M.trust_check("Key통제 개선완료율(2026)", 7)

    body = (
        f"지표 카드 4종({미해소['기준연도']}년 기준, 반복 미비점 통제 "
        f"비율은 {반복['기준연도']} 결합 기준): 미해소 미비점 비율 "
        f"{미해소['value']:.2f}%({미해소['분자']}/{미해소['분모']}), "
        f"운영 적정률 {운영['value']:.2f}%({운영['분자']}/{운영['분모']}), "
        f"반복 미비점 통제 비율 {반복['value']:.2f}%({반복['분자']}/"
        f"{반복['분모']}), 개선완료율 {완료율['value']:.2f}%"
        f"({완료율['분자']}/{완료율['분모']}).\n\n"

        f"Track B 퍼널(전체 {_fmt(발생)}건 결합): 미비점 발생 "
        f"{_fmt(발생)}건 → 개선조치 착수 {_fmt(착수)}건 → 개선조치 완료 "
        f"{_fmt(완료)}건. 연도별로 나누면 2025년 "
        f"{_fmt(f25['n'].iloc[0])}→{_fmt(f25['n'].iloc[1])}→"
        f"{_fmt(f25['n'].iloc[2])}건(완료 "
        f"{f25['n'].iloc[2] / f25['n'].iloc[0] * 100:.2f}%), 2026년 "
        f"{_fmt(f26['n'].iloc[0])}→{_fmt(f26['n'].iloc[1])}→"
        f"{_fmt(f26['n'].iloc[2])}건(완료 "
        f"{f26['n'].iloc[2] / f26['n'].iloc[0] * 100:.2f}%)이다. 전환율이 "
        f"가장 낮게 계산된 구간은 '{bn}' 단계다(아래 차트 참고).\n\n"

        f"{process_line}\n\n"

        f"개선 후 재발 분석: 판정 모집단 {_fmt(모집단)}개(2025년 미비점이 "
        f"발생하고 그 개선조치가 전부 완료 처리된 통제) 중 {retention_line}\n\n"

        "세그먼트 판정 보류(참고 — my-wiki-04 analysis-002·insight-001에서 "
        "이미 확인된 원시 건수이며, 이 화면의 데이터로 새로 계산한 값이 "
        f"아니다): 재고 프로세스 운영 적정률은 {tc_stock['reason']}으로 "
        "전체 평균과의 비교 판정을 보류한다(운영 적정 5건/통제 7건, 원시 "
        f"건수만 표시). Key통제 개선완료율도 {tc_key['reason']}으로 "
        "Non-Key와의 비교 판정을 보류한다(완료 2건/통제 7건, 원시 건수만 "
        "표시)."
    )
    return {"title": "4. 결과", "kind": "auto", "body": body,
            "charts": ["funnel", "device"]}


def _s5_recurrence(t: dict) -> dict:
    """5. 개선·재발 분석 — 기존 '5. 실험' 자리.

    이 도메인에는 experiments·experiment_assignments 테이블이 없어
    실험 판정(옛 _s5_experiments의 골격)을 적용할 수 없다. 대신
    my-wiki-04가 이미 확정한 "개선 후 재발"(analysis-005·006, 후보 B)
    분석을 담는다. core.metrics.experiment_results()·srm_check()·
    EXP_STEPS·channel_efficiency()는 실험 데이터가 생기면 다시 쓸 수
    있도록 그대로 둔다 — 이 함수는 그것들을 지우거나 대체하지 않는다.
    """
    rf = M.retention_funnel(t)
    모집단, 유지, 재발 = rf["n"].tolist()
    재발_목록 = rf.attrs.get("재발_control_id", [])
    tc = M.trust_check("개선 후 재발 분석", 모집단)

    k = M.kpis(t)
    반복 = k["반복 미비점 통제 비율"]

    if tc["trusted"]:
        판정문 = (f"유지 {_fmt(유지)}개({유지 / 모집단 * 100:.2f}%), "
                 f"재발 {_fmt(재발)}개({재발 / 모집단 * 100:.2f}%)다.")
    else:
        판정문 = (f"유지 {_fmt(유지)}개, 재발 {_fmt(재발)}개다(원시 건수 — "
                 f"{tc['reason']}으로 유지율·재발률 비율 판정은 보류한다).")

    body = (
        "정의: 2025년에 미비점이 발생하고 그 개선조치가 전부(all) "
        "'완료'로 처리된 통제(판정 모집단)만 대상으로, 2026년 같은 "
        f"control_id에서 미비점이 다시 발생했는지를 본다. 판정 모집단 "
        f"{_fmt(모집단)}개 중 {판정문} 재발 통제 "
        f"목록: {', '.join(재발_목록)}.\n\n"

        f"{tc['message']}\n\n"

        "이 정의('재발', 통제 수 기준 판정 모집단 안에서만 계산)는 반복 "
        f"미비점 통제 비율(metric-003, {반복['기준연도']} 결합 기준 "
        f"{반복['value']:.2f}%, {반복['분자']}/{반복['분모']})과 같은 "
        "개념이 아니다. metric-003은 완료 여부와 무관하게 두 연도 모두 "
        f"미비점이 발생한 통제 {반복['분자']}개를 전부 센다. 이 중 재발로 "
        f"세는 {_fmt(재발)}개를 뺀 나머지(my-wiki-04 analysis-006 확인: "
        "CTRL-004·015·024·039·050·060, 6개)는 2025년 미비점이 애초에 "
        f"완료 처리되지 않은 채 2026년까지 남아 있던 통제이며, 이 장의 "
        f"'재발' {_fmt(재발)}개에는 포함하지 않았다.\n\n"

        "관측기간 미성숙 — 전년 대비 성과 판정 보류(my-wiki-04 "
        "analysis-005 확인): 2026년 개선조치 22건 중 12건(54.55%)의 "
        "target_date가 2027년이다. 2026년 완료율이 2025년보다 낮게 "
        "계산된 것을 처리 속도 저하로 단정할 근거는 이 표에 없다 — "
        "2026년 코호트는 아직 완료할 기간이 더 남아 있을 수 있다.\n\n"

        "재발의 원인(개선조치가 형식적이었는지, 근본원인이 같은지 "
        "다른지)은 이 표에 없다. root_cause 컬럼을 2025·2026 미비점 "
        "간에 직접 대조하지 않았다."
    )
    return {"title": "5. 개선·재발 분석", "kind": "auto", "body": body}


def _s7_limits(t: dict) -> dict:
    """7. 한계 — 소표본·관측기간 경고를 그대로 옮긴다.

    한계는 세 곳에서 온다: 검증 경고 · 판단하지 않은 것 · 계산할 수
    없었던 것. 사람이 매번 새로 쓰지 않고 이미 확인된 경고를 옮긴다.
    """
    # 검증 경고 — 하드코딩하지 않고 core.validate.run_checks()의 실제
    # 결과(level=="warn")를 그대로 옮긴다. 새 검증 규칙은 만들지 않는다.
    checks = V.run_checks(t)
    warns = [c for c in checks if c["level"] == "warn"]
    if warns:
        검증경고 = " ".join(f"{w['name']}: {w['msg']}" +
                          (f"({w['detail']})" if w["detail"] else "")
                          for w in warns)
    else:
        검증경고 = "검증 경고 없음(현재 데이터 기준)."

    tc_retention = M.trust_check("개선 후 재발 분석", 15)
    tc_key = M.trust_check("Key통제 개선완료율(2026)", 7)
    tc_stock = M.trust_check("재고 프로세스 운영 적정률(2026)", 7)
    tc_obs = M.trust_check("2026년 개선조치 관측기간", 22, observation_issue=True,
                           detail="22건 중 12건(54.55%)은 target_date가 2027년")

    # 프로세스별 전환율 판정 보류 — funnel_by()가 이미 계산한 건수 중
    # 최댓값을 그대로 인용한다(새 계산 없음).
    g_long = M.funnel_by(t, "process_name")
    발생by = g_long[g_long.step == "미비점발생"].set_index("process_name")["n"]
    최대프로세스 = 발생by.idxmax()
    tc_process = M.trust_check(f"프로세스별 전환율({최대프로세스}, 최대)",
                               int(발생by.max()))

    # 문구에 나열하는 항목 수를 하드코딩하지 않고 이 리스트의 길이로 뽑는다.
    판정보류_목록 = [tc_retention, tc_key, tc_stock, tc_process]

    body = (
        "이 리포트는 기계적으로 판정 가능한 것만 계산했다. 혼입 변수 "
        "층화, 역인과 검토, 사전 정의된 가설 검정은 수행하지 않았다 — "
        "판단이 필요한 영역이며 2장(배경)·6장(해석)·8장(제안)에서 사람이 "
        "다룬다. 이 리포트는 관측 데이터만 다루므로 인과를 주장하지 "
        "않는다.\n\n"

        f"검증 경고(core.validate.run_checks 결과 그대로): {검증경고}\n\n"

        f"판정 보류(표본 미달) {len(판정보류_목록)}건: {tc_retention['reason']}(개선 후 "
        f"재발 분석 — 유지율·재발률 미표시, 원시 건수 15/10/5만 표시). "
        f"{tc_key['reason']}(Key통제 개선완료율 — 비율·Non-Key 대비 차이 "
        f"미표시). {tc_stock['reason']}(재고 프로세스 운영 적정률 — 전체 "
        f"평균 대비 차이 미표시). {tc_process['reason']}(프로세스별 "
        "전환율 — 7개 프로세스 전부 최소표본 미달로 판정 보류, 발생 "
        "건수만 표시).\n\n"

        f"{tc_obs['message']}: 2026년 개선조치 22건 중 12건(54.55%)의 "
        "target_date가 2027년이다(my-wiki-04 analysis-005 확인). "
        "2025년 완료율(50.00%)과 2026년 완료율(40.91%)은 같은 조건에서 "
        "측정된 값이 아니므로, 이 리포트는 두 값의 차이를 전년 대비 "
        "성과 악화로 쓰지 않는다.\n\n"

        "누적값 비교 제한: 반복 미비점 통제 비율(metric-003, 27.50%, "
        "11/40)은 2025~2026 결합 스냅샷이다. 관측 연도가 늘어날수록 "
        "분자가 단조 증가하는 구조라, 향후 연도가 추가된 결합값과 이번 "
        "값을 직접 비교해 늘었다거나 줄었다고 말할 수 없다"
        "(metric-003.yaml 유효구간 절). 분석기간 자체도 2025~2026년 "
        "2개 연도뿐이라, 그보다 긴 주기(3개 연도 이상)에 걸친 추세나 "
        "반복 여부는 이 리포트로 확인할 수 없다.\n\n"

        "임계값 적용 상태: my-wiki-04는 미해소 미비점 비율(metric-001) "
        "기준 임계값 B안(정상 63.64% 미만·경고 63.64~68.18%·위험 68.18% "
        "이상)과 최소표본 n=20을 확정했고, 이 앱의 config.THRESHOLDS에는 "
        "metric-001만 반영돼 있다(현재값 59.09%는 정상 범위). 운영 "
        "적정률·반복 미비점 통제 비율·개선완료율(metric-002~004)은 "
        "공식 임계값이 아직 확정되지 않아 화면에서 '참고지표'로 표시되며, "
        "정상·경고·위험 판정을 임의로 만들지 않는다.\n\n"

        "이 리포트에는 가정값이 들어간 문장이 없다.\n\n"

        "찾았지만 없었던 것: root_cause 기준 재발 원인 대조, 3개 연도 "
        "이상에서 반복되는 '장기 고질' 통제 여부, 개선조치 처리 경과일 "
        "— 전부 현재 데이터(2개 연도, root_cause 미대조)로는 계산할 수 "
        "없다."
    )
    return {"title": "7. 한계", "kind": "auto", "body": body}


# ── 사람이 쓰는 장 (제공) ─────────────────────────────────────────
# hint 는 입력 가이드일 뿐이다. body 를 대신 채우지 않는다. 현재 데이터·
# 분석 결과 기반으로 조립하되(M.kpis·M.trust_check·V.run_checks 재사용,
# 새 계산 없음), "무엇을 써야 하는지"만 안내하고 완성 문장을 만들지 않는다.
# pages/3_리포트.py가 hint 앞에 "※ 작성 가이드라인" 단서를 항상 붙인다.
def _s2_background(t: dict, human: dict) -> dict:
    years = sorted(t["ic_deficiency"]["year"].unique())
    hint = (
        "이번 보고서에서 설명하면 좋은 내용<br>"
        f"· 왜 {years[0]}~{years[-1]}년 {C.DATASET} 운영·개선 상태를 "
        "점검하는지<br>"
        "· 어떤 업무 판단이나 관리 우선순위를 위해 보는지<br>"
        "· 미해소 미비점·반복 미비점·개선완료 상태·개선 후 유지·재발을 "
        "함께 보는 이유<br>"
        f"· 표본이 최소표본({C.MIN_SAMPLE}건) 미달이거나 관측기간이 짧은 "
        "항목을 왜 따로 판정을 미루는지<br><br>"
        "담당자가 직접 결정할 내용<br>"
        "· 실제 보고 대상<br>"
        "· 실제 업무 목적<br>"
        "· 이번 보고서를 통해 결정하려는 사항"
    )
    return {
        "title": "2. 배경", "kind": "human",
        "body": human.get("2. 배경", ""),
        "placeholder": "이 분석을 왜 했는지, 어떤 의사결정을 앞두고 있는지 적으십시오.",
        "hint": hint,
    }


def _s6_interpretation(t: dict, human: dict) -> dict:
    k = M.kpis(t)
    years_avail = sorted(t["ic_deficiency"]["year"].unique())
    prev_year = years_avail[-2] if len(years_avail) >= 2 else None
    운영 = k["운영 적정률"]
    완료율 = k["개선완료율"]
    rf = M.retention_funnel(t)
    모집단 = int(rf.loc[rf.step == "기준모집단", "n"].iloc[0])
    tc_retention = M.trust_check("개선 후 재발 분석", 모집단)
    tc_key = M.trust_check("Key통제 개선완료율(2026)", 7)

    사실 = []
    if prev_year is not None:
        운영_prev = M.kpis(t, year=prev_year)["운영 적정률"]
        사실.append(
            f"· 운영 적정률: {prev_year} {운영_prev['value']:.2f}% → "
            f"{운영['기준연도']} {운영['value']:.2f}% "
            f"({운영['value'] - 운영_prev['value']:+.2f}%p)")
    사실.append(
        f"· 개선완료율: {완료율['기준연도']} {완료율['value']:.2f}% — 해당 "
        "연도 개선조치 일부는 목표일이 다음 연도 이후라 관측기간이 아직 "
        "다 차지 않음")
    사실.append(
        f"· 개선 후 유지·재발: 판정 모집단 {모집단}건 — "
        f"{tc_retention['reason']}로 비율 판정을 미룸")
    사실.append("· 프로세스별 비교: 전체 프로세스가 최소표본 미달로 비교 판정을 미룸")
    사실.append(f"· Key통제 개선완료율: {tc_key['reason']}로 비교 판정을 미룸")

    hint = (
        "현재 사실(참고)<br>" + "<br>".join(사실) + "<br><br>"
        "해석에서 설명하면 좋은 내용<br>"
        "· 실제로 관찰된 변화가 무엇인지<br>"
        "· 비교할 수 있는 값과 비교하면 안 되는 값을 구분<br>"
        "· 관측기간이 충분하지 않은 지표를 어떻게 볼지<br>"
        "· 표본이 부족해 판정을 미룬 항목을 어떻게 설명할지<br>"
        "· 현재 데이터로는 콕 집어 말할 수 없는 부분<br><br>"
        "결과와 원인을 하나로 못박는 표현은 쓰지 않습니다(예: 특정 요인 "
        "하나가 결과를 만들었다고 단정하는 문장)<br><br>"
        "담당자가 직접 판단할 내용<br>"
        "· 숫자가 실제 업무에서 무엇을 의미하는지<br>"
        "· 추가로 확인이 필요한 후보<br>"
        "· 현업 상황과 함께 봤을 때의 의미"
    )
    return {
        "title": "6. 해석", "kind": "human",
        "body": human.get("6. 해석", ""),
        "placeholder": ("숫자가 무엇을 뜻하는지 적으십시오. "
                        "자동으로 쓰지 않습니다 — 해석은 사람의 책임입니다."),
        "hint": hint,
    }


def _s8_proposal(t: dict, human: dict) -> dict:
    rf = M.retention_funnel(t)
    재발_n = int(rf.loc[rf.step == "재발", "n"].iloc[0])
    tc_obs = M.trust_check("2026년 개선조치 관측기간", 22, observation_issue=True,
                           detail="22건 중 12건(54.55%)은 target_date가 2027년")

    hint = (
        "현재 데이터 기반 참고사항<br>"
        "· 미해소 미비점이 존재함(0건 아님)<br>"
        "· 개선조치 목표일(target_date) 관리가 필요함<br>"
        f"· 개선 후 다시 미비점이 발생한 통제 {재발_n}건 존재<br>"
        "· 프로세스별·Key통제 분석은 표본 부족으로 비교 판정을 미룬 상태<br>"
        f"· {tc_obs['message']}<br>"
        "· 표본이 부족한 지표는 그 자체로 제도 변경의 근거로 바로 쓰지 "
        "않음<br><br>"
        "제안에서 검토하면 좋은 내용<br>"
        "· 어떤 미비점이나 개선조치를 먼저 살펴볼지<br>"
        "· 개선 후 다시 미비점이 발생한 통제를 어떻게 점검할지<br>"
        "· 표본이 부족한 항목은 언제 다시 평가할지<br>"
        "· 목표일이 다음 연도 이후인 건을 언제 다시 확인할지<br>"
        "· 지금 당장 하지 않을 조치는 무엇인지<br><br>"
        "담당자가 직접 결정할 내용<br>"
        "· 실제 담당 부서<br>"
        "· 일정<br>"
        "· 우선순위<br>"
        "· 통제 재설계 여부<br>"
        "· 경영진 보고 또는 후속조치 수준"
    )
    return {
        "title": "8. 제안", "kind": "human",
        "body": human.get("8. 제안", ""),
        "placeholder": ("무엇을 할 것인지, 무엇을 하지 않을 것인지 적으십시오. "
                        "선택하지 않으면 제안이 아니라 보고입니다."),
        "hint": hint,
    }


# ── 조립 ──────────────────────────────────────────────────────────
def _safe(title: str, fn, *args) -> dict:
    """아직 안 채운 장은 "todo" 종류로 돌려준다. 골격 전용."""
    from core.todo import NotYet
    try:
        return fn(*args)
    except NotYet as e:
        return {"title": title, "kind": "todo", "body": "", "todo": e}


def build(t: dict, human: dict | None = None) -> list[dict]:
    """8장을 조립한다. human 은 사람이 쓴 장의 본문 딕셔너리.

    **순서와 자동/사람 구분은 바꾸지 않는다.** 장 개수는 도메인에 맞게 줄여도 되지만,
    해석과 제안을 자동으로 돌리는 것만은 하지 않는다.
    """
    human = human or {}
    return [
        _safe("1. 요약", _s1_summary, t),
        _s2_background(t, human),
        _safe("3. 방법", _s3_method, t),
        _safe("4. 결과", _s4_results, t),
        _safe("5. 개선·재발 분석", _s5_recurrence, t),
        _s6_interpretation(t, human),
        _safe("7. 한계", _s7_limits, t),
        _s8_proposal(t, human),
    ]


def email_draft(t: dict, sections: list[dict]) -> dict:
    """이메일 초안. **실제로 보내지 않는다.**

    그대로 쓴다. 이메일 HTML은 인라인 스타일과 표 레이아웃만 쓴다 —
    외부 CSS·자바스크립트·이미지는 대부분의 메일 클라이언트가 막는다.

    받을 사람이 없으면 초안까지만 만들고, 게이트 3은 "보냈다고 치고" 기록만 남긴다.
    """
    summary = next((s["body"] for s in sections if s["title"].startswith("1.")), "")
    subject = f"[성장 리포트] {C.PERIOD[0][:7]}~{C.PERIOD[1][:7]}"
    html = (
        f'<div style="font-family:sans-serif;color:#0f172a;max-width:640px">'
        f'<h2 style="font-size:18px">{subject}</h2>'
        f'<p style="font-size:14px;line-height:1.7;white-space:pre-line">'
        f'{summary}</p>'
        f'<p style="font-size:12px;color:#64748b;margin-top:20px">'
        f'자동 생성 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p></div>')
    return {"to": C.EMAIL_TO_EXAMPLE, "subject": subject, "html": html}
