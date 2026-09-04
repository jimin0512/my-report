# -*- coding: utf-8 -*-
"""앱 전체 점검.

  python tests/test_app.py

렌더만 보는 것이 아니라 **조작까지** 돌린다.
게이트를 통과시키고 PDF를 만들어 봐야 실제로 동작하는지 알 수 있다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest   # noqa: E402

PAGES = ["pages/1_실행.py", "pages/2_대시보드.py",
         "pages/3_리포트.py", "pages/4_아카이브.py"]
ok = True


def check(cond, label):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    ok = ok and bool(cond)


def click(at, label):
    for b in at.button:
        if b.label == label:
            b.click().run()
            return True
    return False


print("1. 페이지 렌더")
at = AppTest.from_file("app.py", default_timeout=300).run()
check(not at.exception, "app.py")
for p in PAGES:
    at.switch_page(p).run()
    check(not at.exception, p)
    if at.exception:
        for e in at.exception:
            print(f"         {type(e.value).__name__}: {e.value}")

print("\n2. 실행 흐름과 게이트")
at.switch_page("pages/1_실행.py").run()
at.button[0].click().run()
check(not at.exception and at.session_state.run["step"] >= 1, "적재")
if at.text_input:
    at.text_input[0].set_value("기존 고객은 퍼널 이력이 없는 것이 정상").run()
check(click(at, "통과시키기") and "1" in at.session_state.run["gates"],
      "게이트1 통과 · 판단 근거 기록")
if at.text_input:
    at.text_input[-1].set_value("직전 분기와 유사").run()
check(click(at, "통과시키기") and "2" in at.session_state.run["gates"],
      "게이트2 통과")

print("\n3. 대시보드 조작")
at.switch_page("pages/2_대시보드.py").run()
at.radio[0].set_value("채널별").run()
check(not at.exception, "기기별/채널별 전환")
if at.slider:
    at.slider[0].set_value(100).run()
    check(not at.exception, "개선 효과 계산기")

print("\n4. 리포트와 PDF")
at.switch_page("pages/3_리포트.py").run()
at.radio[0].set_value("6. 해석").run()
at.text_area[0].set_value("모바일 완료율 격차가 최대 병목이다.").run()
check(click(at, "저장") and at.session_state.human, "사람 작성 저장")
check(click(at, "PDF 만들기") and "pdf" in at.session_state, "PDF 생성")
if "pdf" in at.session_state:
    print(f"         {len(at.session_state.pdf)/1024:.0f}KB")

print("\n5. 아카이브")
at.switch_page("pages/4_아카이브.py").run()
check(click(at, "지금 데이터로 재계산해 비교") and not at.exception, "재현")

print("\n6. 게이트 3은 되돌릴 수 없다")
from core import gates    # noqa: E402
r = gates.new_run()
gates.pass_gate(r, 2, "")
gates.pass_gate(r, 3, "")
check(gates.revert_gate(r, 2) is True, "게이트2는 되돌릴 수 있다")
check(gates.revert_gate(r, 3) is False, "게이트3은 되돌릴 수 없다")

print(f"\n{'모두 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
