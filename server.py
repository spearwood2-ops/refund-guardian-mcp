# -*- coding: utf-8 -*-
"""환불 지킴이 — MCP 서버 (무인증, Streamable HTTP).

목적: 포기했던 환불 — 법이 보장한 내 돈을 돌려받게 한다.
근거: 헬스장 등 선결제 피해구제 3년 14,857건, 온라인 환불 거부 분쟁 상시.
청약철회·중도해지·할부항변권은 명문 규정 — 몰라서 못 쓰는 권리를 대화로 찾아준다.

판정은 참고 정보(법률 자문 아님). 최종 확인 1372. 출력: 이모지 금지·중요도순·간결.
"""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from refund_rules import classify, KNOWLEDGE, installment_defense

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
_allowed = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
_ts = (TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                 allowed_hosts=[h.strip() for h in _allowed.split(",")],
                                 allowed_origins=["*"])
       if _allowed else TransportSecuritySettings(enable_dns_rebinding_protection=False))

mcp = FastMCP("refund-guardian", host=HOST, port=PORT, transport_security=_ts)

_DISCLAIMER = ("본 안내는 법령·소비자분쟁해결기준에 근거한 참고 정보이며 법률 자문이 아닙니다. "
               "정확한 판단은 1372 소비자상담센터(국번없이 1372)에서 무료로 확인하세요.")


@mcp.tool()
def check_refund_right(situation: str) -> str:
    """Identify the user's legal refund rights for a Korean consumer dispute.

    THE core tool. Describe any refund situation in Korean (헬스장 폐업/중도해지,
    온라인쇼핑 환불 거부, 단순변심 반품, 방문판매, 구독 해지, 상조, 업체 잠적 등)
    and get: which law applies (전자상거래법 7일 청약철회, 방문판매법 14일,
    계속거래 중도해지, 할부항변권), the exact conditions/deadlines, and next steps.
    """
    cid, label = classify(situation)
    k = KNOWLEDGE[cid]
    out = ["상황 분류: %s" % label, "", "내 권리", k["right"], ""]
    out.append("요건·기준")
    out += ["- " + c for c in k["conditions"]]
    out += ["", "지금 할 일"]
    out += ["%d. %s" % (i + 1, s) if not s.startswith("-") else s for i, s in enumerate(k["steps"])]
    out += ["", _DISCLAIMER]
    return "\n".join(out)


@mcp.tool()
def check_installment_defense(amount_won: int, installment_months: int, has_remaining_balance: bool = True, reason: str = "") -> str:
    """Determine whether 할부항변권 (Installment Defense Right, 할부거래법 제16조) applies.

    For paid-in-advance services that closed down (헬스장 먹튀 등) or undelivered goods,
    paid by credit-card installment. Requirements are statutory: total >= 200,000 KRW
    AND installment period >= 3 months AND remaining balance exists. Returns a clear
    성립/불성립 verdict with reasons and the exact card-company procedure.
    """
    ok, reasons, steps = installment_defense(amount_won, installment_months, has_remaining_balance, reason)
    if ok is None:
        head = "판정 불가 — 정보가 더 필요합니다"
    elif ok:
        head = "판정: 할부항변권 행사 요건 충족 (할부거래법 제16조)"
    else:
        head = "판정: 할부항변권 요건 미충족 — 다른 구제 수단 안내"
    out = [head, ""]
    out += ["- " + r for r in reasons]
    if steps:
        out += ["", "지금 할 일"] + steps
    out += ["", _DISCLAIMER]
    return "\n".join(out)


@mcp.tool()
def generate_refund_letter(business_name: str, item: str, amount: str, situation: str, request: str = "환불") -> str:
    """Draft a formal Korean demand letter (내용증명) or card-company installment-defense notice.

    Provide business name, what was purchased, amount, what happened, and what you demand.
    Returns a ready-to-send draft the user can adapt and send via 우체국 내용증명
    (or submit to their card company for 할부항변).
    """
    body = [
        "제목: %s 청구의 건" % request,
        "",
        "수신: %s" % business_name,
        "발신: (성명·연락처·주소 기재)",
        "",
        "1. 본인은 귀사와 아래와 같이 계약을 체결하였습니다.",
        "   - 계약 내용: %s" % item,
        "   - 결제 금액: %s" % amount,
        "",
        "2. 그러나 다음과 같은 사유가 발생하였습니다.",
        "   - %s" % situation.strip(),
        "",
        "3. 이에 본인은 관련 법령(전자상거래법·방문판매법·할부거래법 및 소비자분쟁해결기준)에 따라",
        "   %s을(를) 요청하며, 본 통지 수령일로부터 14일 이내에 처리해 주시기 바랍니다." % request,
        "",
        "4. 기한 내 처리되지 않을 경우 한국소비자원 피해구제 신청 및 관련 법적 절차를",
        "   진행할 예정임을 알려드립니다.",
        "",
        "20    년    월    일",
        "발신인:            (서명)",
    ]
    guide = [
        "발송 방법",
        "- 우체국 방문 또는 인터넷우체국(epost.go.kr)에서 '내용증명'으로 발송 (사본 3부: 발송용·보관용·우체국 보관)",
        "- 카드 할부 건이면 이 초안을 '할부항변권 행사 통지서' 제목으로 바꿔 카드사에 제출할 수 있습니다",
        "- 계약서·결제내역·대화 캡처를 함께 보관하세요",
    ]
    return "\n".join(["내용증명 초안", "=" * 24] + body + ["", ""] + guide + ["", _DISCLAIMER])


@mcp.tool()
def refund_channels(case_type: str = "일반") -> str:
    """List official Korean consumer-remedy channels and how to check if a business closed.

    Returns: 1372 hotline, 한국소비자원 procedures, 홈택스 business-status lookup,
    금감원, small-claims court — ordered by what to do first.
    """
    out = [
        "환불 분쟁 구제 채널 (순서대로)",
        "",
        "1. 1372 소비자상담센터 — 국번없이 1372, 평일 9~18시. 무료 상담으로 내 사건의 정확한 절차 확인",
        "2. 한국소비자원 피해구제 — kca.go.kr 온라인 신청. 합의 권고 → 분쟁조정까지 무료",
        "3. 업체 폐업 확인 — 홈택스(hometax.go.kr) '사업자등록상태 조회'에 사업자번호 입력 (무료)",
        "4. 카드 결제 분쟁 — 카드사 민원 → 해결 안 되면 금융감독원 1332",
        "5. 소액 민사 — 3,000만원 이하는 소액사건심판(변호사 없이 가능), 지급명령 신청도 검토",
        "",
        "상조 가입자: 공정위 '내상조 찾아줘'(mysangjo.or.kr)에서 예치기관 확인",
        "",
        _DISCLAIMER,
    ]
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
