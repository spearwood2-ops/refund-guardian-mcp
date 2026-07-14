# -*- coding: utf-8 -*-
"""환불 지킴이 v2 — MCP 서버 (무인증, Streamable HTTP).

환불 권리와 대응 절차를 확인하도록 돕는다(회수 보장 아님).
checker P0 반영: 결론(조건부) 우선 출력·간결(≈500자)·내부 라벨 미노출·
사실 부족 시 '추가 확인 필요'·수신인별 문서 분리.
"""
import os
import re
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from refund_rules import classify, KNOWLEDGE, installment_defense  # noqa: E501

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
_allowed = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
_ts = (TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                 allowed_hosts=[h.strip() for h in _allowed.split(",")],
                                 allowed_origins=["*"])
       if _allowed else TransportSecuritySettings(enable_dns_rebinding_protection=False))

mcp = FastMCP("refund-guardian", host=HOST, port=PORT, transport_security=_ts)

_NOTE = "참고 정보이며 법률 자문이 아닙니다. 1372 소비자상담센터(상담료 없음, 통화료 발신자 부담, 평일 9-18시·점심 12-13시 제외)에서 확인하세요."


def _render(k, clarify=None, max_checks=3, max_steps=3):
    out = [k["verdict"], ""]
    if clarify:
        out += ["확인 필요: " + clarify, ""]
    out.append("확인할 것")
    out += ["- " + c for c in k["checks"][:max_checks]]
    out += ["", "지금 할 일"]
    out += ["%d. %s" % (i + 1, s) for i, s in enumerate(k["steps"][:max_steps])]
    out += ["", _NOTE]
    return "\n".join(out)


@mcp.tool()
def check_refund_right(situation: str) -> str:
    """Identify likely legal refund rights for a Korean consumer dispute (conditional, never absolute).

    Describe the situation in Korean (헬스장 폐업/중도해지, 학원, 온라인 환불 거부,
    오프라인 구매, 방문판매, 구독, 상조, 업체 잠적 등). Returns: the applicable law
    and conditions, what facts to confirm, and next steps. If key facts are missing,
    it asks ONE clarifying question instead of guessing.
    """
    cid, label, clarify = classify(situation)
    return _render(KNOWLEDGE[cid], clarify)


@mcp.tool()
def check_installment_defense(amount_won: int, installment_months: int, has_remaining_balance: Optional[bool] = None, reason: str = "") -> str:
    """Assess 할부항변권 (할부거래법 제16조) — requires quantity conditions AND a statutory ground.

    amount_won: total price. installment_months: card installment period.
    has_remaining_balance: whether unpaid installments remain — REQUIRED (ask the user;
    do not guess). reason: WHAT went wrong (폐업/미공급/하자/계약해지 등 — required
    for a positive assessment). Returns possible / not met / needs review.
    """
    if has_remaining_balance is None:
        return "아직 내지 않은 할부금(잔여 할부금)이 남아 있나요? 항변권은 남은 할부금에만 행사할 수 있어 이 확인이 필요합니다.\n\n" + _NOTE
    status, reasons, steps = installment_defense(amount_won, installment_months, has_remaining_balance, reason)
    heads = {
        "possible": "판단: 항변권 행사 가능성이 있습니다 (미지급 잔여 할부금 대상, 카드사 서면 통지 필요)",
        "not_met": "판단: 항변권 요건에 해당하지 않는 것으로 보입니다",
        "review": "판단 보류: 법정 항변 사유 확인이 더 필요합니다",
        "need_info": "정보가 더 필요합니다",
    }
    out = [heads[status], ""]
    out += ["- " + r for r in reasons]
    if steps:
        out += ["", "다음 단계"] + steps
    out += ["", _NOTE]
    return "\n".join(out)


@mcp.tool()
def generate_refund_letter(recipient: str, business_name: str = "", item: str = "", amount: str = "", situation: str = "", amount_won: int = 0, installment_months: int = 0, has_remaining_balance: Optional[bool] = None) -> str:
    """Draft (초안) a formal notice — recipient must be "판매자" (demand letter / 내용증명) or "카드사" (할부항변 통지).

    All facts (business_name, item, amount, situation) are required. For "카드사",
    amount_won, installment_months AND has_remaining_balance are also required; the
    statutory installment-defense conditions are checked first and the notice is
    generated only when the defense is plausible. Output is a DRAFT the user must review.
    """
    missing = [n for n, v in (("업체명", business_name), ("계약 내용", item), ("금액", amount), ("상황", situation)) if not str(v).strip()]
    if recipient not in ("판매자", "카드사"):
        return "수신인을 알려주세요: 업체(판매자)에게 보내는 요구서인가요, 카드사에 내는 할부항변 통지인가요?"
    if missing:
        return "초안 작성에 다음 정보가 필요합니다: %s. 하나씩 알려주세요." % ", ".join(missing)

    if recipient == "카드사":
        # 항변권 게이트: 요건 판정을 통과해야만 통지서 생성 (우회 금지)
        if not amount_won or not installment_months:
            return "카드사 할부항변 통지는 요건 확인이 먼저 필요합니다. 결제 총액(원)과 할부 개월수를 알려주세요."
        if has_remaining_balance is None:
            return "아직 내지 않은 할부금(잔여 할부금)이 남아 있나요? 항변권은 남은 할부금에만 행사할 수 있어 먼저 확인이 필요합니다."
        digits = re.sub(r"[^\d]", "", amount)
        if digits and int(digits) != amount_won:
            return "표시 금액(%s)과 판정에 쓴 금액(%s원)이 다릅니다. 실제 결제 총액을 다시 알려주세요." % (amount, format(amount_won, ","))
        status, reasons, _steps = installment_defense(amount_won, installment_months, has_remaining_balance, situation)
        if status != "possible":
            if status == "review":
                return "\n".join(["항변 사유 확인이 먼저 필요합니다. 무슨 문제가 있었는지(폐업·미공급·하자·계약해지 등) 사실 위주로 알려주세요.", "", _NOTE])
            return "\n".join(["할부항변권 요건에 해당하지 않아 카드사 통지서를 만들지 않았습니다.", ""]
                             + ["- " + r for r in reasons]
                             + ["", "대신 판매자 대상 환불 요구(내용증명)나 1372 상담 경로를 이용하세요.", "", _NOTE])
        body = [
            "[초안] 할부항변권 행사 통지 (할부거래법 제16조)",
            "",
            "수신: (카드사명) 귀중",
            "발신: (성명·생년월일·연락처)",
            "",
            "1. 본인은 %s와 아래 계약을 체결하고 귀사 신용카드 할부로 결제하였습니다." % business_name,
            "   - 계약 내용: %s / 결제 총액: %s원 (%d개월 할부)" % (item, format(amount_won, ","), installment_months),
            "2. 발생한 문제: %s" % situation.strip(),
            "3. 위 사유로 할부거래법 제16조에 따라 잔여 할부금 지급 거절 의사를 통지합니다.",
            "   증빙(계약서·결제내역·사업자등록상태 조회 등)을 첨부합니다.",
            "",
            "(작성일·서명. 카드번호 등은 카드사 양식에 따라 기재)",
            "",
            "안내: 카드사 자체 양식이 있는 경우가 많으니 콜센터에 먼저 문의하세요. 서면 발송일에 효력이 생깁니다.",
        ]
    else:
        body = [
            "[초안] 환불 요구 통지 (내용증명용)",
            "",
            "수신: %s" % business_name,
            "발신: (성명·연락처·주소)",
            "",
            "1. 계약 내용: %s / 결제 금액: %s" % (item, amount),
            "2. 발생한 문제: %s" % situation.strip(),
            "3. 이에 관련 법령 및 소비자분쟁해결기준에 따른 환불을 요청합니다.",
            "   회신 기한: 수령일부터 14일 (기한 도과 시 한국소비자원 피해구제 등 절차 진행 예정)",
            "",
            "(작성일·서명)",
            "",
            "발송: 우체국 또는 인터넷우체국(epost.go.kr) 내용증명. 계약서·결제내역 사본 보관.",
        ]
    body += ["", "이 문서는 초안입니다. 사실관계를 확인·수정한 뒤 발송하세요. " + _NOTE]
    return "\n".join(body)


@mcp.tool()
def refund_channels(case_type: str = "일반") -> str:
    """Official Korean consumer-remedy channels, filtered by case (폐업/카드/상조/일반)."""
    base = ["1. 1372 소비자상담센터 — 국번없이 1372. 내 사건의 정확한 절차 확인(상담료 없음·통화료 발신자 부담)",
            "2. 한국소비자원 피해구제 — kca.go.kr 온라인 신청(무료)"]
    t = case_type
    extra = []
    if any(k in t for k in ("폐업", "잠적", "먹튀")):
        extra = ["3. 홈택스 '사업자등록상태 조회' — 사업자번호로 폐업 확인(무료·로그인 불필요, 세법상 등록 상태 기준)",
                 "4. 소액사건심판·지급명령 — 3,000만원 이하 금전 청구, 변호사 없이 가능"]
    elif any(k in t for k in ("카드", "할부")):
        extra = ["3. 카드사 민원 접수(할부항변·이의제기)", "4. 해결 안 되면 금융감독원 1332"]
    elif "상조" in t:
        extra = ["3. 공정위 '내상조 찾아줘'(mysangjo.or.kr) — 가입·보전기관·보전액 확인"]
    else:
        extra = ["3. 카드 결제 분쟁은 카드사 민원 → 금융감독원 1332", "4. 소액이면 소액사건심판(3,000만원 이하) 검토"]
    return "\n".join(["환불 분쟁 구제 채널 (순서대로)", ""] + base + extra + ["", _NOTE])


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
