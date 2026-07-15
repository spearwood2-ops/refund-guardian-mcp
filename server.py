# -*- coding: utf-8 -*-
"""환불 지킴이 v2.7 — MCP 서버 (무인증, Streamable HTTP).

환불 권리와 대응 절차를 확인하도록 돕는다(회수 보장 아님).
checker P0 반영: 결론(조건부) 우선 출력·간결(≈500자)·내부 라벨 미노출·
사실 부족 시 '추가 확인 필요'·수신인별 문서 분리.
"""
import os
import re
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from refund_rules import (  # noqa: E501
    classify,
    KNOWLEDGE,
    installment_defense,
    InstallmentGroundCode,
    InstallmentGroundFact,
)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
_allowed = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
_ts = (TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                 allowed_hosts=[h.strip() for h in _allowed.split(",")],
                                 allowed_origins=["*"])
       if _allowed else TransportSecuritySettings(enable_dns_rebinding_protection=False))

mcp = FastMCP("refund-guardian", host=HOST, port=PORT, transport_security=_ts)

_NOTE = "참고 정보이며 법률 자문이 아닙니다. 1372 소비자상담센터(상담료 없음, 통화료 발신자 부담, 평일 9-18시·점심 12-13시 제외)에서 확인하세요."
_OUTPUT_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")

# PlayMCP 공개 description은 1,024자 이내로 유지한다. 긴 함수 docstring은
# 개발자용 상세 규칙으로 보존하고, 아래 문구만 tools/list에 노출한다.
_CHECK_REFUND_RIGHT_DESCRIPTION = (
    "환불 지킴이 (Refund Guardian)가 소비자 상황의 환불 가능성, 적용 법령·기한, "
    "확인할 사실과 다음 행동을 조건부로 안내합니다. 온라인·오프라인 구매, 방문판매, "
    "구독, 헬스장·필라테스·학원, 상조, 폐업·잠적 등 환불 상황을 한국어로 입력하세요. "
    "핵심 사실이 부족하면 권리를 추정하거나 결과를 보장하지 않고 한 가지 확인 질문을 "
    "반환합니다. 일반 정보이며 법률 자문이 아닙니다."
)
_CHECK_INSTALLMENT_DESCRIPTION = (
    "환불 지킴이 (Refund Guardian)가 할부항변권의 수량 요건(총액·기간·잔여금)과 "
    "법정 사유 후보를 점검합니다. has_remaining_balance는 사용자에게 "
    "확인하고 추정하지 마세요. ground_code는 입력 스키마의 6개 값 중 하나입니다. "
    "ground_confirmed=True는 같은 할부계약에서 이미 발생한 완전한 사유와 "
    "필수 ground_facts가 모두 확인될 때만 사용하세요. 필수 사실은 "
    "contract_invalid=installment_contract_scope+contract_invalid_confirmed, "
    "contract_ended=installment_contract_scope+contract_ended_confirmed, "
    "supply_not_completed=installment_contract_scope+supply_time_reached+actual_non_supply, "
    "warranty_unfulfilled=installment_contract_scope+warranty_duty_exists+"
    "warranty_duty_unfulfilled, purpose_failed_by_breach=installment_contract_scope+"
    "seller_breach_confirmed+contract_purpose_unattainable, lawful_withdrawal="
    "installment_contract_scope+withdrawal_legally_available+withdrawal_exercised입니다. "
    "폐업·하자·채무불이행·청약철회 언급만으로 확정하지 말고 부정·질문·전언·가능성·"
    "희망·미래·요청 표현도 확정하지 마세요. 결과는 자동 권리 확정이 아닌 미충족 또는 "
    "공식 검토 필요입니다. 일반 정보이며 법률 자문이 아닙니다."
)
_GENERATE_LETTER_DESCRIPTION = (
    "환불 지킴이 (Refund Guardian)가 판매자용 환불 요구서 초안을 만들거나 카드 분쟁의 "
    "공식 확인 경로를 안내합니다. recipient는 판매자 또는 카드사이며 업체명·계약 내용·"
    "금액·상황이 필요합니다. 판매자 분기만 사용자가 검토할 [초안]을 생성합니다. 카드사 "
    "분기는 결제 총액·할부기간·잔여할부금과 구조화된 법정 사유를 먼저 점검하되 지급거절 "
    "행사문을 자동 생성하지 않고 카드사 공식 양식·증빙 검토로 연결합니다. 카드사 입력의 "
    "ground_code, ground_confirmed, ground_facts에는 check_installment_defense와 같은 "
    "엄격한 사유 규칙을 적용하세요. 같은 할부계약에서 법정 사유 전체가 이미 발생했고 "
    "정확한 ground_facts가 모두 있을 때만 confirmed를 사용하세요. 폐업·하자·"
    "채무불이행·청약철회 언급만으로 사유를 "
    "확정하지 말고 부정·질문·전언·가능성·희망·미래·요청 표현에서도 추정하지 마세요. "
    "일반 정보이며 법률 자문이나 환불 결과 보장이 아닙니다."
)
_REFUND_CHANNELS_DESCRIPTION = (
    "환불 지킴이 (Refund Guardian)가 사건 유형에 맞는 1372, 한국소비자원, 카드사·"
    "금융감독원, 홈택스, 소액사건심판 등 공식 소비자 구제 채널을 우선순위대로 안내합니다. "
    "외부 기관에 자동 접수·전송하지 않으며 법률 자문이나 해결 보장이 아닙니다."
)


def _document_text(value) -> str:
    """사용자 사실은 보존하되 공식 문서 출력 표준에 맞게 이모지·중복 공백만 제거."""
    return " ".join(_OUTPUT_EMOJI.sub("", str(value)).split())


def _read_only_annotations(title: str) -> ToolAnnotations:
    """이 서버의 조회·텍스트 생성 도구에 공통으로 쓰는 MCP 안전 힌트."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


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


@mcp.tool(
    description=_CHECK_REFUND_RIGHT_DESCRIPTION,
    annotations=_read_only_annotations("환불 지킴이 - 환불 권리 확인"),
)
def check_refund_right(situation: str) -> str:
    """환불 지킴이가 소비자 상황에서 적용 가능한 환불 권리와 다음 단계를 조건부로 안내합니다.

    Describe the situation in Korean (헬스장 폐업/중도해지, 학원, 온라인 환불 거부,
    오프라인 구매, 방문판매, 구독, 상조, 업체 잠적 등). Returns: the applicable law
    and conditions, what facts to confirm, and next steps. If key facts are missing,
    it asks ONE clarifying question instead of guessing.
    """
    cid, label, clarify = classify(situation)
    return _render(KNOWLEDGE[cid], clarify)


@mcp.tool(
    description=_CHECK_INSTALLMENT_DESCRIPTION,
    annotations=_read_only_annotations("환불 지킴이 - 할부항변권 확인"),
)
def check_installment_defense(
    amount_won: int,
    installment_months: int,
    has_remaining_balance: Optional[bool] = None,
    reason: str = "",
    ground_code: Optional[InstallmentGroundCode] = None,
    ground_confirmed: Optional[bool] = None,
    ground_facts: Optional[List[InstallmentGroundFact]] = None,
) -> str:
    """환불 지킴이가 할부항변권의 수량 요건과 법정 사유 후보를 점검합니다.

    amount_won: total price. installment_months: card installment period.
    has_remaining_balance: whether unpaid installments remain — REQUIRED (ask the user;
    do not guess). reason: the user's factual description. ground_code: used to select
    the statutory ground to review; choose one of contract_invalid, contract_ended,
    supply_not_completed, warranty_unfulfilled, purpose_failed_by_breach,
    lawful_withdrawal. These mean the FULL statutory ground: closure alone is not
    supply_not_completed; a defect alone is not warranty_unfulfilled; breach alone is
    not purpose_failed_by_breach; mentioning withdrawal is not lawful_withdrawal.
    ground_confirmed: set true ONLY when the user states the full ground as an already
    occurred fact, never for a negation, question, hearsay, possibility, future plan,
    or request. ground_facts must contain exactly the required set for the selected code:
    contract_invalid=[installment_contract_scope,contract_invalid_confirmed];
    contract_ended=[installment_contract_scope,contract_ended_confirmed];
    supply_not_completed=[installment_contract_scope,supply_time_reached,actual_non_supply];
    warranty_unfulfilled=[installment_contract_scope,warranty_duty_exists,warranty_duty_unfulfilled];
    purpose_failed_by_breach=[installment_contract_scope,seller_breach_confirmed,contract_purpose_unattainable];
    lawful_withdrawal=[installment_contract_scope,withdrawal_legally_available,withdrawal_exercised].
    Returns not met / needs review. Even apparently complete facts are routed to the
    card issuer's official form because this tool cannot independently verify evidence,
    same-contract scope, or legal applicability.
    """
    if has_remaining_balance is None:
        return "아직 내지 않은 할부금(잔여 할부금)이 남아 있나요? 항변권은 남은 할부금에만 행사할 수 있어 이 확인이 필요합니다.\n\n" + _NOTE
    status, reasons, steps = installment_defense(
        amount_won,
        installment_months,
        has_remaining_balance,
        reason,
        ground_code=ground_code,
        ground_confirmed=ground_confirmed,
        ground_facts=ground_facts,
    )
    heads = {
        "not_met": "확인 결과: 항변권 요건에는 해당하기 어려워 보입니다. 다른 환불 경로를 함께 확인해 보세요",
        "review": "많이 답답하셨을 텐데, 지금 단계에서 권리를 단정하지 않겠습니다. 불리한 안내가 되지 않도록 공식 확인 경로까지 이어드릴게요",
        "need_info": "정확한 안내를 위해 정보가 조금 더 필요합니다",
    }
    # 알 수 없는 상태가 추가돼도 법률 긍정 문구 대신 review 안내로 안전하게 강등한다.
    out = [heads.get(status, heads["review"]), ""]
    out += ["- " + r for r in reasons]
    if steps:
        out += ["", "다음 단계"] + steps
    out += ["", _NOTE]
    return "\n".join(out)


@mcp.tool(
    description=_GENERATE_LETTER_DESCRIPTION,
    annotations=_read_only_annotations("환불 지킴이 - 환불 요구서 작성"),
)
def generate_refund_letter(
    recipient: str,
    business_name: str = "",
    item: str = "",
    amount: str = "",
    situation: str = "",
    amount_won: int = 0,
    installment_months: int = 0,
    has_remaining_balance: Optional[bool] = None,
    ground_code: Optional[InstallmentGroundCode] = None,
    ground_confirmed: Optional[bool] = None,
    ground_facts: Optional[List[InstallmentGroundFact]] = None,
) -> str:
    """환불 지킴이가 판매자 환불 요구서 초안을 만들거나 카드 분쟁의 공식 확인 경로를 안내합니다.

    recipient must be "판매자" or "카드사". All facts (business_name, item,
    amount, situation) are required. For "카드사",
    amount_won, installment_months, has_remaining_balance, ground_code AND
    ground_confirmed=True and the exact required ground_facts for that code are required:
    contract_invalid/ended need installment_contract_scope plus their confirmed fact;
    all codes need installment_contract_scope; supply additionally needs
    supply_time_reached+actual_non_supply; warranty needs warranty_duty_exists+
    warranty_duty_unfulfilled; purpose failure needs seller_breach_confirmed+
    contract_purpose_unattainable; withdrawal needs withdrawal_legally_available+
    withdrawal_exercised.
    The situation must state the FULL statutory ground, not merely closure, defect,
    breach, or a withdrawal request. Never confirm a ground from a negation, question,
    hearsay, possibility, future plan, or request. The same statutory gate is checked
    before guidance. The card branch never writes a payment-refusal exercise notice;
    it connects the user to the issuer's official form and evidence review. Only the
    seller branch outputs a DRAFT that the user must review.
    """
    missing = [n for n, v in (("업체명", business_name), ("계약 내용", item), ("금액", amount), ("상황", situation)) if not str(v).strip()]
    if recipient not in ("판매자", "카드사"):
        return "수신인을 알려주세요: 업체(판매자)에게 보내는 요구서인가요, 카드사에 내는 할부항변 통지인가요?"
    if missing:
        return "초안 작성에 다음 정보가 필요합니다: %s. 하나씩 알려주세요." % ", ".join(missing)
    if sum(len(str(v)) for v in (business_name, item, amount, situation)) > 160:
        return "초안을 읽기 편하게 만들 수 있도록 업체명·계약 내용·금액·상황을 합쳐 160자 이내로 줄여주세요. 계약일, 결제액, 문제 발생일, 원하는 조치 순서면 충분합니다."

    business_name, item, amount, situation = (
        _document_text(v) for v in (business_name, item, amount, situation)
    )

    if recipient == "카드사":
        # 카드사 지급거절 행사문은 자동 생성하지 않는다. 같은 상위 입력이 만든
        # 구조값은 증빙의 진위·동일 계약 관련성·법 적용을 독립 확인하지 못한다.
        if not amount_won or not installment_months:
            return "카드사 할부항변 통지는 요건 확인이 먼저 필요합니다. 결제 총액(원)과 할부 개월수를 알려주세요."
        if has_remaining_balance is None:
            return "아직 내지 않은 할부금(잔여 할부금)이 남아 있나요? 항변권은 남은 할부금에만 행사할 수 있어 먼저 확인이 필요합니다."
        digits = re.sub(r"[^\d]", "", amount)
        if digits and int(digits) != amount_won:
            return "표시 금액(%s)과 판정에 쓴 금액(%s원)이 다릅니다. 실제 결제 총액을 다시 알려주세요." % (amount, format(amount_won, ","))
        status, reasons, _steps = installment_defense(
            amount_won,
            installment_months,
            has_remaining_balance,
            situation,
            ground_code=ground_code,
            ground_confirmed=ground_confirmed,
            ground_facts=ground_facts,
        )
        if status == "not_met":
            return "\n".join([
                "많이 답답하셨을 텐데, 확인된 정보로는 할부항변권 수량 요건에 해당하기 어려워 카드사 행사문을 만들지 않았습니다.",
                "",
                "다음 행동",
                "1. 판매자에게 환불 요구서를 보내고 1372에서 다른 구제 절차를 확인하세요.",
                "2. 카드 결제 분쟁은 카드사 고객센터에 별도로 접수하세요.",
                "",
                _NOTE,
            ])
        return "\n".join([
            "당황스러우셨을 텐데, 불리한 문구가 남지 않도록 카드사 지급거절 행사문은 자동으로 만들지 않겠습니다.",
            "사실·증빙의 진위와 같은 계약 관련성, 법 적용은 카드사의 공식 확인이 필요합니다.",
            "",
            "다음 행동",
            "1. 카드사 고객센터에 할부항변권 담당 부서와 공식 서면 양식을 요청하세요.",
            "2. 계약서·결제내역·미공급 또는 하자 대응 증빙을 제출하고 적용 여부를 서면으로 확인하세요.",
            "3. 해결되지 않으면 금융감독원 1332 또는 1372에서 도움을 받으세요.",
            "",
            _NOTE,
        ])

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


@mcp.tool(
    description=_REFUND_CHANNELS_DESCRIPTION,
    annotations=_read_only_annotations("환불 지킴이 - 구제 채널 안내"),
)
def refund_channels(case_type: str = "일반") -> str:
    """환불 지킴이가 사건 유형에 맞는 공식 소비자 구제 채널을 안내합니다."""
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
