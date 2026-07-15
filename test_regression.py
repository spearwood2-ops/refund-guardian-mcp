# -*- coding: utf-8 -*-
"""회귀 테스트 — checker 검증보고(2026-07-14)의 적대 10문장 + 항변권 경계값 + 출력 길이.

실행: python test_regression.py  (전부 PASS 여야 심사요청 게이트 통과)
"""
import asyncio
import io
import inspect
import sys
from importlib.metadata import version
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
from refund_rules import GROUND_REQUIRED_FACTS, INSTALLMENT_GROUNDS, classify, installment_defense
import server

FAILS = []
CHECK_COUNT = 0


def check(name, cond, detail=""):
    global CHECK_COUNT
    CHECK_COUNT += 1
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAILS.append(name)


def facts_for(ground_code):
    return sorted(GROUND_REQUIRED_FACTS[ground_code])


def card_result(situation, ground_code=None, ground_confirmed=None, ground_facts=None):
    """카드사 행동문서 게이트를 같은 고정 입력으로 검증한다."""
    return server.generate_refund_letter(
        "카드사",
        "OO서비스",
        "6개월 이용권",
        "900,000원",
        situation,
        amount_won=900000,
        installment_months=6,
        has_remaining_balance=True,
        ground_code=ground_code,
        ground_confirmed=ground_confirmed,
        ground_facts=ground_facts,
    )


requirements = Path(__file__).with_name("requirements.txt").read_text(encoding="utf-8").splitlines()
check("배포 의존성: 검증한 MCP SDK 1.28.0 고정", "mcp==1.28.0" in requirements)
check("배포 의존성: 실행 MCP SDK도 1.28.0", version("mcp") == "1.28.0")


# 1) checker 적대 10문장 (기대 = 확인해야 할 우선 유형; 정답 집합 허용)
ADV = [
    ("필라테스가 폐업해서 남은 6개월 이용권 환불받고 싶어요.", {"gym_close"}),
    ("폐업한 필라테스에서 90만원 6개월 할부금을 환불받고 싶어요.", {"gym_close"}),
    ("헬스장은 폐업하지 않았고 정상 영업 중인데, 개인 사정으로 중도해지하고 싶어요.", {"gym_quit"}),
    ("쇼핑몰에서 산 옷 사이즈가 안 맞아 반품하려는데 판매자가 거부해요.", {"online_refuse"}),
    ("판매자가 환불을 거부한 인터넷 쇼핑몰입니다.", {"online_refuse"}),
    ("전화권유로 가입한 정기결제를 3일 만에 취소하고 싶어요.", {"door_sale"}),
    ("전화권유를 받았지만 계약하지 않았고, 기존 구독만 해지하려고요.", {"subscribe"}),
    ("오프라인 매장에서 산 신발이 사이즈가 안 맞아 반품하고 싶어요.", {"offline_purchase"}),  # 전자상거래법 미적용 (오라클 단일 고정)
    ("학원 원장이 잠적해서 남은 수강료를 환불받고 싶어요.", {"academy"}),  # 학원법 분리 (오라클 단일 고정)
    ("상조는 아니고 장례식장 계약금 환불 문제예요.", {"general"}),
    ("온라인은 아니고 매장에서 직접 샀는데 환불 되나요?", {"offline_purchase"}),  # 채널 부정문
    ("학원은 아니고 헬스장 환불 문제예요.", {"gym_quit"}),  # 업종 부정문 (단일 오라클)
    ("온라인으로 주문하고 매장에서 수령했는데 환불 되나요?", {"general"}),  # 혼합 채널 → 단정 금지
    ("학원 수업은 아니고 헬스 PT 환불 문제예요.", {"gym_quit"}),  # 조사·수식어 낀 업종 부정
    ("온라인 거래가 아닌데, 매장에서 산 물건 환불 되나요?", {"offline_purchase"}),  # 조사 낀 채널 부정
]
for i, (txt, expected) in enumerate(ADV, 1):
    cid, label, clarify = classify(txt)
    check("분류#%d" % i, cid in expected, "→ %s (기대 %s)" % (cid, "/".join(expected)))

# 2) 할부항변권 — 사유 없는 '충족' 반환 금지 (checker 재현 케이스)
st, _, _ = installment_defense(900000, 6, True, "단순 변심이고 업체가 약속대로 정상 제공 중")
check("항변권: 변심+정상제공 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "")
check("항변권: 사유 미제공 → 판정보류(review)", st == "review", "→ %s" % st)
st, _, _ = installment_defense(
    900000, 6, True, "업체가 폐업해서 남은 서비스를 못 받아요",
    ground_code="supply_not_completed", ground_confirmed=True,
    ground_facts=facts_for("supply_not_completed"),
)
check("항변권: 폐업+수량충족 → 공식 확인(review)", st == "review", "→ %s" % st)
st, _, _ = installment_defense(150000, 6, True, "폐업")
check("항변권: 20만원 미만 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(900000, 1, True, "폐업")
check("항변권: 일시불 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, False, "폐업")
check("항변권: 완납 → 불성립", st == "not_met", "→ %s" % st)

# 2-1) checker 재검증 지적: 부정문·희망형 사유, 정확 경계값
st, _, _ = installment_defense(900000, 6, True, "폐업하지 않았어요")
check("항변권: 사유 부정문 → possible 금지", st in ("review", "not_met"), "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "그냥 취소하고 싶어요")
check("항변권: 희망형 취소 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "계약이 무효라고 생각합니다")
check("항변권: 무효라고 생각 → 확정 사실 아님(review)", st == "review", "→ %s" % st)
st, _, _ = installment_defense(199999, 6, True, "폐업")
check("항변권: 199,999원 경계 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(
    200000, 6, True, "업체가 폐업해 남은 서비스를 받지 못했습니다",
    ground_code="supply_not_completed", ground_confirmed=True,
    ground_facts=facts_for("supply_not_completed"),
)
check("항변권: 200,000원 경계 → 공식 확인(review)", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 2, True, "폐업")
check("항변권: 2개월 경계 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(
    900000, 3, True, "업체가 폐업해 남은 서비스를 받지 못했습니다",
    ground_code="supply_not_completed", ground_confirmed=True,
    ground_facts=facts_for("supply_not_completed"),
)
check("항변권: 3개월 경계 → 공식 확인(review)", st == "review", "→ %s" % st)

# 2-2) v2.1 재검증 지적: 불확실·변형 부정·희망형 잔존 경로 (정확 상태 오라클)
st, _, _ = installment_defense(900000, 6, True, "폐업인 것 같아요")
check("항변권: 불확실(것 같다) → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "취소를 하고 싶습니다")
check("항변권: 희망형(를 하고 싶다) → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "안 망했어요, 잘 다니고 있어요")
check("항변권: 앞선 부정(안 망했) → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "폐업했다고 들었어요")
check("항변권: 전언(들었다) → review", st == "review", "→ %s" % st)

# 2-3) v2.2 재검증 지적: 의심·희망 표현, no-ground 반전, 잔여금 기본값
st, _, _ = installment_defense(900000, 6, True, "폐업이 의심됩니다")
check("항변권: 의심 표현 → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "계약 해지를 희망합니다")
check("항변권: 희망합니다 → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(
    900000, 6, True, "정상 영업 중이 아니에요, 문을 닫아 남은 서비스를 못 받아요",
    ground_code="supply_not_completed", ground_confirmed=True,
    ground_facts=facts_for("supply_not_completed"),
)
check("항변권: 부정된 no-ground(영업중 아님)+폐업 → review", st == "review", "→ %s" % st)
r = server.check_installment_defense(900000, 6)
check("공개 판정 도구: 잔여금 미입력 → 질문(기본값 금지)", "남아 있나요" in r)

# 2-4) v2.3 재검증 지적: 명시적 부정 활용형·질문형·전언·과거 반전
st, _, _ = installment_defense(900000, 6, True, "폐업 아님")
check("항변권: '폐업 아님' → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "하자는 아냐, 그냥 문의")
check("항변권: '하자는 아냐' → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "폐업 가능성이 있다고 합니다")
check("항변권: 가능성+전언 → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "청약철회가 가능한지 궁금합니다")
check("항변권: 질문형(궁금) → review", st == "review", "→ %s" % st)
st, _, _ = installment_defense(
    900000, 6, True, "예전에는 정상 영업 중이었는데 지금은 폐업했고 남은 서비스를 받지 못했어요",
    ground_code="supply_not_completed", ground_confirmed=True,
    ground_facts=facts_for("supply_not_completed"),
)
check("항변권: 과거 정상→현재 폐업 → review", st == "review", "→ %s" % st)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "폐업 아님", amount_won=900000, installment_months=6, has_remaining_balance=True)
check("카드사 통지: '폐업 아님' → 초안 미생성", "[초안]" not in r)
cid, _, _ = classify("전화권유로 가입하지 않았는데 앱 구독 해지하고 싶어요")
check("분류: 비계약 전화권유+구독 → subscribe", cid == "subscribe", "→ %s" % cid)

# 2-5) v2.4 재검증 지적: '아닙니다' 활용형 + 코어 3곳 배선 검증
st, _, _ = installment_defense(900000, 6, True, "폐업 아닙니다")
check("항변권: '폐업 아닙니다' → review", st == "review", "→ %s" % st)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "폐업 아닙니다", amount_won=900000, installment_months=6, has_remaining_balance=True)
check("카드사 통지: '폐업 아닙니다' → 초안 미생성", "[초안]" not in r)
st, _, _ = installment_defense(900000, 6, True, "하자 아닙니다, 문의만요")
check("항변권: '하자 아닙니다' → review", st == "review", "→ %s" % st)
from refund_rules import _NEG_CORE, _NOUN_NEG, _negated, _NEG_WIDE  # noqa: E402
import re as _re2
check("배선: _NEG_WIDE가 코어 포함", _NEG_CORE in _NEG_WIDE.pattern)
check("배선: _NOUN_NEG가 코어 포함", any(_NEG_CORE in p for p in _NOUN_NEG))
check("배선: _negated 기본값이 코어 포함", _NEG_CORE in _negated.__defaults__[0])
check("코어: 아닙(니다) 활용형 포함", bool(_re2.search(_NEG_CORE, "아닙니다")))

# 2-6) v2.6 P0 구조 수정: 대화 입력만으로 권리 확정·카드사 행동문서를 열지 않음
EXPECTED_GROUND_CODES = {
    "contract_invalid",
    "contract_ended",
    "supply_not_completed",
    "warranty_unfulfilled",
    "purpose_failed_by_breach",
    "lawful_withdrawal",
}
EXPECTED_GROUND_FACTS = set().union(*GROUND_REQUIRED_FACTS.values())
check("구조 게이트: 법정 사유 코드 6개 고정", set(INSTALLMENT_GROUNDS) == EXPECTED_GROUND_CODES)
check("구조 게이트: 코드별 필수 사실 2~3개",
      set(GROUND_REQUIRED_FACTS) == EXPECTED_GROUND_CODES
      and all(len(v) in (2, 3) for v in GROUND_REQUIRED_FACTS.values()))
for fn in (server.check_installment_defense, server.generate_refund_letter):
    sig = inspect.signature(fn)
    check("공개 서명: %s ground_code 존재·기본 None" % fn.__name__,
          "ground_code" in sig.parameters and sig.parameters["ground_code"].default is None)
    check("공개 서명: %s ground_confirmed 존재·기본 None" % fn.__name__,
          "ground_confirmed" in sig.parameters and sig.parameters["ground_confirmed"].default is None)
    check("공개 서명: %s ground_facts 존재·기본 None" % fn.__name__,
          "ground_facts" in sig.parameters and sig.parameters["ground_facts"].default is None)

published_tools = {t.name: t.parameters for t in server.mcp._tool_manager.list_tools()}
for tool_name in ("check_installment_defense", "generate_refund_letter"):
    props = published_tools[tool_name]["properties"]
    enum_values = set(props["ground_code"]["anyOf"][0]["enum"])
    check("MCP 스키마: %s ground_code 6개 enum" % tool_name,
          enum_values == EXPECTED_GROUND_CODES)
    check("MCP 스키마: %s ground_code 기본 null" % tool_name,
          props["ground_code"].get("default", "missing") is None)
    check("MCP 스키마: %s ground_confirmed 기본 null" % tool_name,
          props["ground_confirmed"].get("default", "missing") is None)
    fact_enum = set(props["ground_facts"]["anyOf"][0]["items"]["enum"])
    check("MCP 스키마: %s ground_facts 11개 enum" % tool_name,
          fact_enum == EXPECTED_GROUND_FACTS)
    check("MCP 스키마: %s ground_facts 기본 null" % tool_name,
          props["ground_facts"].get("default", "missing") is None)

# 2-6-1) PlayMCP 접수 메타데이터: 실제 tools/list 응답의 description·annotations 검증
EXPECTED_TOOL_TITLES = {
    "check_refund_right": "환불 지킴이 - 환불 권리 확인",
    "check_installment_defense": "환불 지킴이 - 할부항변권 확인",
    "generate_refund_letter": "환불 지킴이 - 환불 요구서 작성",
    "refund_channels": "환불 지킴이 - 구제 채널 안내",
}
wire_tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
check("MCP 메타데이터: 공개 툴 4개 이름 고정", set(wire_tools) == set(EXPECTED_TOOL_TITLES))
for tool_name, expected_title in EXPECTED_TOOL_TITLES.items():
    tool = wire_tools[tool_name]
    annotations = tool.annotations
    description = tool.description or ""
    check("MCP description: %s 국·영문 서비스명 포함" % tool_name,
          "환불 지킴이 (Refund Guardian)" in description)
    check("MCP description: %s 1,024자 이하" % tool_name,
          0 < len(description) <= 1024)
    check("MCP annotations: %s 정의" % tool_name, annotations is not None)
    check("MCP annotations: %s title 고정" % tool_name,
          annotations.title == expected_title)
    check("MCP annotations: %s 안전 힌트" % tool_name,
          annotations.readOnlyHint is True
          and annotations.destructiveHint is False
          and annotations.idempotentHint is True
          and annotations.openWorldHint is False)

check("MCP description: 할부항변권 자동 확정 금지 유지",
      "자동 권리 확정" in wire_tools["check_installment_defense"].description)
check("MCP description: 카드사 지급거절 행사문 자동 생성 금지 유지",
      "지급거절 행사문을 자동 생성하지 않고" in wire_tools["generate_refund_letter"].description)
check("MCP description: 할부 동일 계약 범위 유지",
      "같은 할부계약" in wire_tools["check_installment_defense"].description
      and "같은 할부계약" in wire_tools["generate_refund_letter"].description)
check("MCP description: 구제 채널 자동 접수·전송 아님",
      "자동 접수·전송하지 않으며" in wire_tools["refund_channels"].description)

OMISSION_CASES = [
    ("자유문장만", {}, "review"),
    ("코드만", {"ground_code": "supply_not_completed"}, "review"),
    ("확인값만", {"ground_confirmed": True}, "review"),
    ("명시적 미확인", {"ground_code": "supply_not_completed", "ground_confirmed": False}, "review"),
    ("잘못된 코드", {"ground_code": "not_a_ground", "ground_confirmed": True}, "review"),
    ("필수 사실 누락", {"ground_code": "supply_not_completed", "ground_confirmed": True}, "review"),
    ("필수 사실 1개", {"ground_code": "supply_not_completed", "ground_confirmed": True,
                    "ground_facts": ["actual_non_supply"]}, "review"),
    ("다른 사유 사실 혼합", {"ground_code": "supply_not_completed", "ground_confirmed": True,
                       "ground_facts": facts_for("warranty_unfulfilled")}, "review"),
    ("문장·코드 불일치", {"ground_code": "warranty_unfulfilled", "ground_confirmed": True,
                    "ground_facts": facts_for("warranty_unfulfilled")}, "review"),
]
for label, kwargs, expected_status in OMISSION_CASES:
    st, _, _ = installment_defense(900000, 6, True, "업체가 폐업해 서비스가 중단됐습니다", **kwargs)
    check("구조 게이트: %s → %s" % (label, expected_status), st == expected_status, "→ %s" % st)
    r = card_result("업체가 폐업해 서비스가 중단됐습니다", **kwargs)
    check("행동문서: %s → 초안 차단" % label, "[초안]" not in r)

NONFACT_CASES = [
    ("폐업 안 해요", "supply_not_completed"),
    ("폐업 안 함", "supply_not_completed"),
    ("폐업하지는 않아요", "supply_not_completed"),
    ("폐업했나요?", "supply_not_completed"),
    ("폐업이라고 들었습니다", "supply_not_completed"),
    ("폐업일 수 있습니다", "supply_not_completed"),
    ("다음 달 폐업 예정입니다", "supply_not_completed"),
    ("폐업은커녕 정상 영업합니다", "supply_not_completed"),
    ("폐업 사실은 사실무근입니다", "supply_not_completed"),
    ("하자가 있다고 보기는 어렵습니다", "warranty_unfulfilled"),
    ("계약 해지 부탁드립니다", "contract_ended"),
    ("청약철회 문의드립니다", "lawful_withdrawal"),
]
for text, code in NONFACT_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("비확정 차단: %s → review" % text, st == "review", "→ %s" % st)
    r = card_result(text, code, True, facts_for(code))
    check("비확정 문서 차단: %s" % text, "[초안]" not in r)

CONFIRMED_CASES = [
    ("업체가 오늘 폐업해 남은 서비스를 받지 못했습니다", "supply_not_completed"),
    ("약정한 서비스 공급이 중단되어 이용하지 못했습니다", "supply_not_completed"),
    ("판매자와 연락이 두절되어 약정한 서비스를 받지 못했습니다", "supply_not_completed"),
    ("제품 하자가 확인됐고 판매자가 수리를 거부했습니다", "warranty_unfulfilled"),
    ("할부계약이 적법하게 해지됐습니다", "contract_ended"),
    ("할부계약이 무효로 확인됐습니다", "contract_invalid"),
    ("판매자의 채무불이행으로 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("전자상거래법상 기간 안에 청약철회를 이미 행사했습니다", "lawful_withdrawal"),
    ("업체가 폐업해서 남은 서비스를 못 받아 환불받고 싶어요", "supply_not_completed"),
    ("업체가 폐업했고 남은 서비스를 받지 못했습니다. 이제 어떻게 해야 하나요?", "supply_not_completed"),
]
for text, code in CONFIRMED_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("확정 사유도 공식 확인: %s" % text, st == "review", "→ %s" % st)
    r = card_result(text, code, True, facts_for(code))
    check("확정 사유 카드 행사문 차단: %s" % text,
          "[초안]" not in r and "공식 서면 양식" in r)

# 2-7) 테스트 밖 독립 적대 78문장 + 조문 전체 요건 오라클
# 단어가 있어도 부정·질문·전언·추정·미래·요청·가정이면 review여야 한다.
WIDE_NONFACT_CASES = [
    ("폐업을 안 했습니다", "supply_not_completed"),
    ("폐업은 전혀 사실이 아닙니다", "supply_not_completed"),
    ("폐업이라는 건 틀린 말입니다", "supply_not_completed"),
    ("하자가 난 것은 아닙니다", "warranty_unfulfilled"),
    ("하자라고 단정하기 어렵습니다", "warranty_unfulfilled"),
    ("계약이 무효라는 주장은 사실이 아닙니다", "contract_invalid"),
    ("서비스 중단으로 볼 수는 없습니다", "supply_not_completed"),
    ("연락 두절은 사실이 아닙니다", "supply_not_completed"),
    ("폐업입니까?", "supply_not_completed"),
    ("폐업인가?", "supply_not_completed"),
    ("폐업했는지요", "supply_not_completed"),
    ("하자 맞나요?", "warranty_unfulfilled"),
    ("서비스가 중단됐습니까?", "supply_not_completed"),
    ("계약이 무효입니까?", "contract_invalid"),
    ("청약철회할 수 있습니까?", "lawful_withdrawal"),
    ("계약 해지가 된 걸까요?", "contract_ended"),
    ("폐업이라고 전해졌습니다", "supply_not_completed"),
    ("폐업이라는 소식을 접했습니다", "supply_not_completed"),
    ("폐업으로 알고 있습니다", "supply_not_completed"),
    ("업체가 문을 닫았대요", "supply_not_completed"),
    ("폐업했다고 하네요", "supply_not_completed"),
    ("하자라네요", "warranty_unfulfilled"),
    ("계약이 무효라는 얘기가 있습니다", "contract_invalid"),
    ("서비스 중단 통보를 받았다고 해요", "supply_not_completed"),
    ("폐업일 가능도 있습니다", "supply_not_completed"),
    ("폐업일지 모릅니다", "supply_not_completed"),
    ("폐업 같네요", "supply_not_completed"),
    ("폐업으로 보입니다", "supply_not_completed"),
    ("폐업일 법합니다", "supply_not_completed"),
    ("폐업인지 애매합니다", "supply_not_completed"),
    ("하자일 개연성이 있습니다", "warranty_unfulfilled"),
    ("무효라고 짐작합니다", "contract_invalid"),
    ("서비스 중단일 확률이 높습니다", "supply_not_completed"),
    ("해지된 모양입니다", "contract_ended"),
    ("내일 폐업합니다", "supply_not_completed"),
    ("폐업하게 될 겁니다", "supply_not_completed"),
    ("폐업할 전망입니다", "supply_not_completed"),
    ("서비스 중단이 임박했습니다", "supply_not_completed"),
    ("다음 주 문 닫습니다", "supply_not_completed"),
    ("곧 계약을 해지합니다", "contract_ended"),
    ("청약철회할 생각입니다", "lawful_withdrawal"),
    ("조만간 연락 두절이 될 겁니다", "supply_not_completed"),
    ("계약 해지 바랍니다", "contract_ended"),
    ("청약철회를 신청합니다", "lawful_withdrawal"),
    ("해지 원함", "contract_ended"),
    ("철회 바랍니다", "lawful_withdrawal"),
    ("계약 취소 처리 바랍니다", "contract_ended"),
    ("무효로 해 주세요", "contract_invalid"),
    ("폐업하는 경우에는 어떻게 하나요", "supply_not_completed"),
    ("폐업이라면 항변할 수 있나요", "supply_not_completed"),
    ("폐업한다고 치면 어떻게 되나요", "supply_not_completed"),
    ("서비스 중단 시 항변하고 싶습니다", "supply_not_completed"),
    ("무효일 때는 어떻게 하나요", "contract_invalid"),
    ("하자라면 환불되나요", "warranty_unfulfilled"),
    ("고장일 때 항변권이 있나요", "warranty_unfulfilled"),
    ("연락 두절 상황을 상정합니다", "supply_not_completed"),
    ("서비스 공급이 중단됐습니다?", "supply_not_completed"),
    ("하자담보책임을 이행하지 않았습니다?", "warranty_unfulfilled"),
    ("계약이 무효로 확정됐습니다?", "contract_invalid"),
    ("계약 해지가 완료됐습니다?", "contract_ended"),
    ("전자상거래법상 청약철회를 행사했습니다?", "lawful_withdrawal"),
    ("판매자 채무불이행으로 계약 목적 달성이 불가능합니다?", "purpose_failed_by_breach"),
    ("서비스 공급이 중단됐습니다 맞나요", "supply_not_completed"),
    ("하자담보책임을 이행하지 않았습니다 맞나요", "warranty_unfulfilled"),
    ("계약이 무효로 확정됐습니다 맞나요", "contract_invalid"),
    ("계약 해지가 완료됐습니다 맞나요", "contract_ended"),
    ("전자상거래법상 청약철회를 행사했습니다 맞나요", "lawful_withdrawal"),
    ("판매자 채무불이행으로 계약 목적 달성이 불가능합니다 맞나요", "purpose_failed_by_breach"),
    ("할부계약이 무효로 확정됐습니다, 다만 저는 판결문을 직접 확인하지 못한 상태이고 이 내용은 법무사에게 전해 들었습니다", "contract_invalid"),
    ("할부계약 해지가 완료됐습니다, 아직 확인서를 받지는 못했고 이 말은 상담센터 직원에게 들었습니다", "contract_ended"),
    ("서비스가 중단됐습니다, 저는 현장을 찾아가 직접 확인하지 않았고 주변 상인에게 전해 들었습니다", "supply_not_completed"),
    ("하자담보책임을 이행하지 않았습니다, 수리 내역은 제가 확인하지 못했고 지인의 설명을 들었습니다", "warranty_unfulfilled"),
    ("판매자 채무불이행으로 계약 목적을 달성할 수 없습니다, 계약서를 직접 보지는 않았고 동료에게 들었습니다", "purpose_failed_by_breach"),
    ("전자상거래법상 청약철회를 행사했습니다, 발송증명은 확인하지 못했으며 상담원에게 들었습니다", "lawful_withdrawal"),
    ("할부계약이 무효로 확정됐습니다: 이 내용은 법무사에게 전해 들었습니다", "contract_invalid"),
    ("할부계약 해지가 완료됐습니다 — 이 판단이 맞습니까?", "contract_ended"),
    ("약정한 서비스 제공이 중단되어 이용하지 못했습니다 하지만 사실인지는 모르겠습니다", "supply_not_completed"),
    ("하자담보책임을 이행하지 않았습니다 이 문장은 다음 달 상황을 가정한 표현입니다", "warranty_unfulfilled"),
    ("판매자 채무불이행으로 계약 목적을 달성할 수 없습니다 이 문구를 예시 통지서에 넣어 달라는 요청입니다", "purpose_failed_by_breach"),
    ("전자상거래법상 기간 안에 청약철회를 행사했습니다: 이 내용은 판매자에게 전해 들었습니다", "lawful_withdrawal"),
    ("할부계약이 무효로 확정됐습니다. 아마 그럴 겁니다.", "contract_invalid"),
    ("할부계약 해지가 완료됐습니다. 확실하지는 않습니다.", "contract_ended"),
    ("약정한 서비스가 중단되어 이용하지 못했습니다. 그런 것 같습니다.", "supply_not_completed"),
    ("하자담보책임을 이행하지 않았습니다. 정확한지는 모르겠습니다.", "warranty_unfulfilled"),
    ("판매자 채무불이행으로 계약 목적을 달성할 수 없습니다. 제 추측입니다.", "purpose_failed_by_breach"),
    ("전자상거래법상 기간 안에 청약철회를 행사했습니다. 발송 여부는 확실하지 않습니다.", "lawful_withdrawal"),
]
for text, code in WIDE_NONFACT_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("광역 비확정 차단: %s" % text, st == "review", "→ %s" % st)
    check("광역 비확정 문서 차단: %s" % text,
          "[초안]" not in card_result(text, code, True, facts_for(code)))

# 법정 사유보다 좁게 판정: 폐업·하자·연락두절 같은 단어만으로는 부족하다.
INCOMPLETE_GROUND_CASES = [
    ("홈택스 조회 결과 업체가 폐업한 사실을 확인했습니다", "supply_not_completed"),
    ("판매자가 잠적했습니다", "supply_not_completed"),
    ("판매자와 연락이 두절됐습니다", "supply_not_completed"),
    ("제품 불량이 검사에서 확인됐습니다", "warranty_unfulfilled"),
    ("제품이 고장 난 상태로 인도됐습니다", "warranty_unfulfilled"),
    ("판매자의 채무불이행이 확인됐습니다", "purpose_failed_by_breach"),
    ("정상 운영 중이었지만 오늘 업체가 폐업했습니다", "supply_not_completed"),
    ("폐업 가능성을 확인한 뒤 홈택스에서 실제 폐업 상태를 확인했습니다", "supply_not_completed"),
    ("혹시 몰라 조회했더니 업체가 실제로 폐업했습니다", "supply_not_completed"),
    ("업체 공지에 따라 오늘부로 영업을 중단했습니다", "supply_not_completed"),
    ("폐업 예정 공지 후 오늘 실제로 영업이 중단됐습니다", "supply_not_completed"),
]
for text, code in INCOMPLETE_GROUND_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("법정 요건 미완성: %s → review" % text, st == "review", "→ %s" % st)
    check("법정 요건 미완성 문서 차단: %s" % text,
          "[초안]" not in card_result(text, code, True, facts_for(code)))

CONTRADICTORY_GROUND_CASES = [
    ("제품에 하자가 있지만 판매자가 즉시 무상수리 중입니다", "warranty_unfulfilled"),
    ("업체는 폐업했지만 승계 업체가 서비스를 정상 제공하고 있습니다", "supply_not_completed"),
    ("약속과 일부 다르지만 정상 이용 중이고 계약 목적은 달성했습니다", "purpose_failed_by_breach"),
    ("청약철회 기간이 지나 판매자가 적법하게 거절했습니다", "lawful_withdrawal"),
    ("해지 접수만 했고 계약은 아직 유지 중입니다", "contract_ended"),
    ("공급 예정일은 다음 달이고 아직 기한 전이지만 상품 배송을 받지 못했습니다", "supply_not_completed"),
    ("보증기간이 끝난 제품이라 업체가 유상 수리를 거부했습니다", "warranty_unfulfilled"),
    ("판매자 잘못은 없고 계약 위반은 소비자 책임이어서 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("전자상거래법 적용 대상이 아닌 거래지만 청약철회를 행사했습니다", "lawful_withdrawal"),
    ("본 할부계약은 정상적으로 계속 유지되고 있습니다. 별도 무료 부가서비스 계약 해지가 완료됐습니다", "contract_ended"),
    ("할부계약은 유효하지만 별도 보증계약이 무효로 확인됐습니다", "contract_invalid"),
    ("할부계약은 유효하며 별도 보증계약이 무효로 확인됐습니다", "contract_invalid"),
    ("할부계약은 종료되지 않았습니다. 사은품 계약 해지가 완료됐습니다", "contract_ended"),
    ("6개월 서비스는 모두 정상 이용했고 약정 만료로 중단됐습니다", "supply_not_completed"),
    ("본 계약 서비스는 완료됐고 다른 계약의 서비스가 중단됐습니다", "supply_not_completed"),
    ("제품에는 하자가 없지만 업체가 디자인 변경 수리를 거부했어요", "warranty_unfulfilled"),
    ("판매자의 하자담보책임은 없고 업체가 수리를 거부했어요", "warranty_unfulfilled"),
    ("계약 위반은 제3자 책임이지만 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("배송업체의 계약 위반으로 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("전자상거래법상 주문제작 예외 상품이지만 청약철회를 행사했습니다", "lawful_withdrawal"),
    ("전자상거래법 요건을 충족하지 못했지만 청약철회를 행사했습니다", "lawful_withdrawal"),
    ("정식 공급 개시일은 아직 오지 않았지만 무료 체험 서비스 제공이 중단됐습니다", "supply_not_completed"),
    ("수강생의 일시정지 요청으로 서비스 제공이 중단됐습니다", "supply_not_completed"),
    ("보증 적용 대상이 아닌 중고품이라 판매자가 무상 수리를 거부했습니다", "warranty_unfulfilled"),
    ("계약 위반 주체는 구매자였고 그 결과 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("전자상거래법 적용 여부는 확인하지 않았지만 청약철회를 행사했습니다", "lawful_withdrawal"),
    ("법정 기간을 지켰는지는 알 수 없지만 방문판매법상 청약철회를 행사했습니다", "lawful_withdrawal"),
]
for text, code in CONTRADICTORY_GROUND_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("반대 사실 차단: %s" % text, st == "review", "→ %s" % st)
    check("반대 사실 문서 차단: %s" % text,
          "[초안]" not in card_result(text, code, True, facts_for(code)))

FULL_STATUTORY_GROUND_CASES = [
    ("업체가 문을 닫아 남은 수업을 받지 못했습니다", "supply_not_completed"),
    ("하자담보책임을 이행하지 않았습니다", "warranty_unfulfilled"),
    ("할부계약이 무효로 확정됐습니다", "contract_invalid"),
    ("할부계약이 성립하지 않았습니다", "contract_invalid"),
    ("할부계약을 이미 취소했습니다", "contract_ended"),
    ("판매자와 합의해 할부계약을 해제했습니다", "contract_ended"),
    ("할부계약 해지가 완료됐습니다", "contract_ended"),
    ("판매자 계약 위반으로 계약 목적 달성이 불가능합니다", "purpose_failed_by_breach"),
    ("판매자가 약속과 다른 서비스를 제공해 계약 목적을 달성하지 못했습니다", "purpose_failed_by_breach"),
    ("전자상거래법상 기간 내 요건을 충족해 청약철회를 이미 행사했습니다", "lawful_withdrawal"),
    ("적법한 철회 통지를 어제 발송했습니다", "lawful_withdrawal"),
    ("남은 수업을 못 받았어요", "supply_not_completed"),
    ("판매자가 하자 수리를 안 해줘요", "warranty_unfulfilled"),
    ("할부계약이 성립 안 됐어요", "contract_invalid"),
    ("할부계약 해지 완료했어요", "contract_ended"),
    ("판매자 계약 위반으로 계약 목적을 못 달성했어요", "purpose_failed_by_breach"),
    ("전자상거래법 기간 안에 철회 통지를 보냈어요", "lawful_withdrawal"),
    ("배송 예정일이 지났고 상품을 받지 못했습니다", "supply_not_completed"),
]
for text, code in FULL_STATUTORY_GROUND_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("조문 전체 사유도 공식 확인: %s" % text, st == "review", "→ %s" % st)
    check("조문 전체 사유 카드 행사문 차단: %s" % text,
          "[초안]" not in card_result(text, code, True, facts_for(code)))

# 2-8) 최종 안전 불변식: 구조값이 모두 채워져도 대화 입력은 독립 증빙이 아니다.
# 선행·후행 비확정, 별도 계약, 귀책·기한·예외 변형도 review이며 카드 행사문은 없다.
FINAL_FAIL_CLOSED_CASES = [
    ("아마 할부계약이 무효로 확정됐습니다", "contract_invalid"),
    ("제 추측으로는 할부계약 해지가 완료됐습니다", "contract_ended"),
    ("가정하면 약정한 남은 수업을 받지 못했습니다", "supply_not_completed"),
    ("소문으로는 제품 하자를 업체가 수리 거부했습니다", "warranty_unfulfilled"),
    ("들리는 말로는 판매자 계약 위반으로 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("예시로 전자상거래법상 기간 안에 청약철회를 행사했습니다", "lawful_withdrawal"),
    ("할부계약이 무효로 확정됐습니다. 다만 진위는 검증되지 않았습니다", "contract_invalid"),
    ("할부계약 해지가 완료됐습니다. 이 문구를 카드사 서류에 써 주세요", "contract_ended"),
    ("남은 수업을 못 받았습니다. 실제로는 제가 결석한 탓입니다", "supply_not_completed"),
    ("계약한 서비스는 다음 달 시작이라 아직 받지 못했습니다", "supply_not_completed"),
    ("제품이 소비자 과실로 고장났고 업체가 수리를 거부했습니다", "warranty_unfulfilled"),
    ("판매자와 무관한 설치 업체 위반으로 계약 목적을 달성할 수 없습니다", "purpose_failed_by_breach"),
    ("법정 기간 내는 아니지만 청약철회를 행사했습니다", "lawful_withdrawal"),
    ("할부계약이 무효로 확정됐습니다. 이는 별도 계약이고 현재 계약은 유효합니다", "contract_invalid"),
    ("할부계약 해지가 완료됐습니다. 위 문장은 다른 사례이고 현재 계약은 유지 중입니다", "contract_ended"),
    ("확인되지 않았지만 남은 서비스 공급이 중단됐습니다", "supply_not_completed"),
    ("그런 것 같지만 하자담보책임을 이행하지 않았습니다", "warranty_unfulfilled"),
    ("가능성으로는 판매자 위반 때문에 계약 목적 달성이 불가능합니다", "purpose_failed_by_breach"),
    ("요건을 충족한 것은 아니지만 청약철회를 행사했습니다", "lawful_withdrawal"),
]
for text, code in FINAL_FAIL_CLOSED_CASES:
    st, _, _ = installment_defense(
        900000, 6, True, text, ground_code=code, ground_confirmed=True,
        ground_facts=facts_for(code),
    )
    check("최종 fail-closed 상태: %s" % text, st == "review", "→ %s" % st)
    r = card_result(text, code, True, facts_for(code))
    check("최종 fail-closed 행동문서 없음: %s" % text,
          "[초안]" not in r and "지급 거절 의사를 통지" not in r)

# 내부 판정이 나중에 실수로 possible을 반환해도 공개 카드 도구는 행사문을 만들지 않는다.
_original_installment_defense = server.installment_defense
try:
    server.installment_defense = lambda *args, **kwargs: ("possible", ["강제 상태"], [])
    r = card_result(
        "업체가 폐업해 남은 서비스를 받지 못했습니다",
        "supply_not_completed", True, facts_for("supply_not_completed"),
    )
    forced_check = server.check_installment_defense(
        900000, 6, True, "업체가 폐업해 남은 서비스를 받지 못했습니다",
        ground_code="supply_not_completed", ground_confirmed=True,
        ground_facts=facts_for("supply_not_completed"),
    )
finally:
    server.installment_defense = _original_installment_defense
check("서버 불변식: 내부 possible 강제에도 카드 행사문 없음",
      "공식 서면 양식" in r and "[초안]" not in r and "지급 거절 의사를 통지" not in r)
check("서버 불변식: 미지 상태도 권리 긍정 대신 review로 강등",
      "권리를 단정하지 않겠습니다" in forced_check and "행사 가능성이 있습니다" not in forced_check)

_letter_source = inspect.getsource(server.generate_refund_letter)
check("서버 구조: 카드 행사문 제목 제거", "[초안] 할부항변권 행사 통지" not in _letter_source)
check("서버 구조: 지급거절 단정 문구 제거", "지급 거절 의사를 통지합니다" not in _letter_source)

# 3) 출력 길이(첫 응답 ≈500자, 여유 550) + 이모지 0
import re as _re
_EMOJI = _re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")
samples = [
    server.check_refund_right("필라테스가 폐업해서 남은 6개월 이용권 환불받고 싶어요."),
    server.check_refund_right("쇼핑몰에서 산 옷 환불 거부당했어요."),
    server.check_refund_right("헬스장 중도해지하고 싶어요."),
    server.check_installment_defense(
        900000, 6, True, "업체가 폐업해 남은 서비스를 받지 못했습니다",
        ground_code="supply_not_completed", ground_confirmed=True,
        ground_facts=facts_for("supply_not_completed"),
    ),
    server.refund_channels("폐업"),
]
for i, s in enumerate(samples, 1):
    check("길이#%d<=550" % i, len(s) <= 550, "(%d자)" % len(s))
    check("이모지#%d=0" % i, not _EMOJI.search(s))

# 4) 내용증명 — 필수 입력 없으면 생성 대신 질문
r = server.generate_refund_letter("판매자")
check("내용증명: 정보 없으면 질문", "필요합니다" in r)
r = server.generate_refund_letter(
    "판매자", "OO필라테스", "6개월 이용권", "900,000원", "남은 수업을 받지 못했습니다",
)
check("내용증명: 판매자 대상 환불 요구 초안은 유지", "[초안] 환불 요구 통지" in r)
r = server.generate_refund_letter(
    "판매자", "OO필라테스", "이용권", "900,000원", "상황 " + ("가" * 700),
)
check("내용증명: 긴 사용자 입력은 짧은 재작성 요청", len(r) <= 550 and "160자 이내" in r)
r = server.generate_refund_letter(
    "판매자", "OO필라테스", "이용권", "900,000원", "남은 수업을 못 받았어요 😢",
)
check("내용증명: 사용자 입력 이모지도 문서에서 제거", not _EMOJI.search(r))
r = server.generate_refund_letter("몰라요")
check("내용증명: 수신인 불명 → 질문", "수신인" in r)
r = server.generate_refund_letter(
    "카드사", "OO필라테스", "6개월 이용권", "900,000원", "폐업으로 남은 서비스를 받지 못했습니다",
    amount_won=900000, installment_months=6, has_remaining_balance=True,
    ground_code="supply_not_completed", ground_confirmed=True,
    ground_facts=facts_for("supply_not_completed"),
)
check("카드사: 요건 충족처럼 보여도 공식 양식 연결·행사문 없음",
      "공식 서면 양식" in r and "[초안]" not in r and "지급 거절 의사를 통지" not in r)

# 4-1) checker 재검증 지적: 카드사 통지서 게이트 우회 차단
r = server.generate_refund_letter("카드사", "OO필라테스", "이용권", "10만원", "폐업")
check("카드사 통지: 금액·개월 미제공 → 질문", "할부 개월수" in r or "알려주세요" in r, )
r = server.generate_refund_letter("카드사", "OO필라테스", "이용권", "100,000원", "폐업", amount_won=100000, installment_months=6, has_remaining_balance=True)
check("카드사 통지: 10만원(요건 미달) → 생성 거부", "만들지 않았습니다" in r)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "단순 변심이고 정상 영업 중", amount_won=900000, installment_months=6, has_remaining_balance=True)
check("카드사 통지: 변심·정상제공 → 생성 거부 + 초안 없음", "만들지 않았습니다" in r and "[초안]" not in r)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "폐업이 의심됩니다", amount_won=900000, installment_months=6, has_remaining_balance=True)
check("카드사 통지: 의심 사유 → 초안 미생성(사실 확인 요구)", "[초안]" not in r)

# 4-2) v2.1 재검증 지적: 잔여할부금 하드코딩·금액 불일치
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "폐업", amount_won=900000, installment_months=6)
check("카드사 통지: 잔여할부금 미확인 → 질문", "잔여 할부금" in r or "남아 있나요" in r)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "폐업", amount_won=900000, installment_months=6, has_remaining_balance=False)
check("카드사 통지: 완납 → 생성 거부", "만들지 않았습니다" in r)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "1,000,000원", "폐업", amount_won=900000, installment_months=6, has_remaining_balance=True)
check("카드사 통지: 표시·판정 금액 불일치 → 질문", "다릅니다" in r)

print()
if FAILS:
    print("결과: FAIL %d건 — %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("결과: 전체 PASS (%d검사)" % CHECK_COUNT)
