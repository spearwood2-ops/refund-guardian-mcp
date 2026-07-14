# -*- coding: utf-8 -*-
"""회귀 테스트 — checker 검증보고(2026-07-14)의 적대 10문장 + 항변권 경계값 + 출력 길이.

실행: python test_regression.py  (전부 PASS 여야 심사요청 게이트 통과)
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
from refund_rules import classify, installment_defense
import server

FAILS = []


def check(name, cond, detail=""):
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAILS.append(name)


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
]
for i, (txt, expected) in enumerate(ADV, 1):
    cid, label, clarify = classify(txt)
    check("분류#%d" % i, cid in expected, "→ %s (기대 %s)" % (cid, "/".join(expected)))

# 2) 할부항변권 — 사유 없는 '충족' 반환 금지 (checker 재현 케이스)
st, _, _ = installment_defense(900000, 6, True, "단순 변심이고 업체가 약속대로 정상 제공 중")
check("항변권: 변심+정상제공 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "")
check("항변권: 사유 미제공 → 판정보류(review)", st == "review", "→ %s" % st)
st, _, _ = installment_defense(900000, 6, True, "업체가 폐업해서 서비스를 못 받아요")
check("항변권: 폐업+수량충족 → 가능성(possible)", st == "possible", "→ %s" % st)
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
check("항변권: 무효 주장 → 사유 인정", st == "possible", "→ %s" % st)
st, _, _ = installment_defense(199999, 6, True, "폐업")
check("항변권: 199,999원 경계 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(200000, 6, True, "폐업")
check("항변권: 200,000원 경계 → 가능성", st == "possible", "→ %s" % st)
st, _, _ = installment_defense(900000, 2, True, "폐업")
check("항변권: 2개월 경계 → 불성립", st == "not_met", "→ %s" % st)
st, _, _ = installment_defense(900000, 3, True, "폐업")
check("항변권: 3개월 경계 → 가능성", st == "possible", "→ %s" % st)

# 3) 출력 길이(첫 응답 ≈500자, 여유 550) + 이모지 0
import re as _re
_EMOJI = _re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")
samples = [
    server.check_refund_right("필라테스가 폐업해서 남은 6개월 이용권 환불받고 싶어요."),
    server.check_refund_right("쇼핑몰에서 산 옷 환불 거부당했어요."),
    server.check_refund_right("헬스장 중도해지하고 싶어요."),
    server.check_installment_defense(900000, 6, True, "폐업"),
    server.refund_channels("폐업"),
]
for i, s in enumerate(samples, 1):
    check("길이#%d<=550" % i, len(s) <= 550, "(%d자)" % len(s))
    check("이모지#%d=0" % i, not _EMOJI.search(s))

# 4) 내용증명 — 필수 입력 없으면 생성 대신 질문
r = server.generate_refund_letter("판매자")
check("내용증명: 정보 없으면 질문", "필요합니다" in r)
r = server.generate_refund_letter("몰라요")
check("내용증명: 수신인 불명 → 질문", "수신인" in r)
r = server.generate_refund_letter("카드사", "OO필라테스", "6개월 이용권", "900,000원", "폐업으로 서비스 중단", amount_won=900000, installment_months=6)
check("내용증명: 카드사(요건 충족) → 항변 통지·초안 표기", "할부항변권" in r and "초안" in r)

# 4-1) checker 재검증 지적: 카드사 통지서 게이트 우회 차단
r = server.generate_refund_letter("카드사", "OO필라테스", "이용권", "10만원", "폐업")
check("카드사 통지: 금액·개월 미제공 → 질문", "할부 개월수" in r or "알려주세요" in r, )
r = server.generate_refund_letter("카드사", "OO필라테스", "이용권", "100,000원", "폐업", amount_won=100000, installment_months=6)
check("카드사 통지: 10만원(요건 미달) → 생성 거부", "만들지 않았습니다" in r)
r = server.generate_refund_letter("카드사", "OO헬스", "이용권", "900,000원", "단순 변심이고 정상 영업 중", amount_won=900000, installment_months=6)
check("카드사 통지: 변심·정상제공 → 생성 거부", "만들지 않았습니다" in r)

print()
if FAILS:
    print("결과: FAIL %d건 — %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("결과: 전체 PASS")
