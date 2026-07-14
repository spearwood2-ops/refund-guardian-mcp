# -*- coding: utf-8 -*-
"""환불 지킴이 v2 — 소비자 환불 권리 지식베이스 + 판정 엔진.

checker 검증(2026-07-14) P0 반영:
  - 할부항변권: 법정 사유 확인 없이는 '충족' 반환 금지 (REVIEW 상태 도입)
  - 분류: 첫매치 정규식 → 신호 추출 + 부정어 처리 + 점수/가드. 낮은 확신 = 확인 질문
  - 학원/체육시설 분리(학원법 별도 산식), 온라인/오프라인 분리, 다단계 분리
  - 단정 문구 제거(조건부 표현), 방해 종료 후 7일·방문판매 기산점·순선수금 50% 교정

원칙: 사실이 부족하면 '가능/불가능' 대신 '추가 확인 필요'. 최종 확인은 1372.
"""
import re
from typing import List, Literal, Optional


def _norm(t):
    return re.sub(r"\s+", " ", t.strip())


# ★ 부정 어휘의 단일 정의 지점(SSOT). '아니-' 전 활용형은 음절 단위라 반드시 여기에만 추가한다.
#   (아니/아닌/아님/아냐/아닐/아닙(니다)) — 아래 _negated/_NOUN_NEG/_NEG_WIDE 전부 이걸 참조.
_NEG_CORE = r"아(니|닌|님|냐|닐|닙)"


def _negated(text, m_start, patterns=(r"하지\s*않", r"않았", r"안\s*했", _NEG_CORE, r"없")):
    """매치 지점 뒤 12자 내 부정어가 있으면 그 신호를 무효화."""
    tail = text[m_start:m_start + 16]
    return any(re.search(p, tail) for p in patterns)


# 명사(업종·채널) 부정: "학원은 아니고", "학원 수업은 아니고", "온라인 거래가 아닌데" — 동사 부정(하지 않)과 구분
_NOUN_NEG = (r"^\s*[가-힣]{0,4}\s*(은|는|이|가)?\s*(" + _NEG_CORE + r"|말고)",)


def _has(text, rx, neg_aware=False, neg_patterns=None):
    m = re.search(rx, text)
    if not m:
        return False
    if neg_aware:
        if neg_patterns:
            tail = text[m.end():m.end() + 12]
            if any(re.search(p, tail) for p in neg_patterns):
                return False
        elif _negated(text, m.end()):
            return False
    return True


def extract_signals(text):
    t = _norm(text)
    return {
        "online": _has(t, r"(쇼핑몰|온라인|인터넷|오픈마켓|스토어|앱에서|배송|택배|주문)", neg_aware=True, neg_patterns=_NOUN_NEG),
        "offline": _has(t, r"(오프라인|매장에서|가게에서|백화점에서|직접\s*(가서|방문))", neg_aware=True, neg_patterns=_NOUN_NEG),
        "gym": _has(t, r"(헬스|피트니스|필라테스|요가|피티|PT|수영장|골프연습장|크로스핏)", neg_aware=True, neg_patterns=_NOUN_NEG),
        "academy": _has(t, r"(학원|어학원|과외|교습소|수강료|인강|강의)", neg_aware=True, neg_patterns=_NOUN_NEG),
        "closed": _has(t, r"(폐업|문\s*을?\s*닫|먹튀|잠적|연락\s*(두절|안\s*됨|끊)|망했)", neg_aware=True),
        "quit": _has(t, r"(중도\s*해지|해지|그만\s*다니|환불받|남은\s*(기간|돈|횟수|수강))"),
        "refuse": _has(t, r"(거부|거절|안\s*(해줘|해준)|못\s*받|무시)"),
        "change_mind": _has(t, r"(단순\s*변심|사이즈|색상|맘에\s*안|잘못\s*샀|안\s*맞)"),
        "door": _has(t, r"(방문\s*판매|길거리|전화\s*권유|홍보관|설명회)", neg_aware=True, neg_patterns=_NOUN_NEG) and not _has(t, r"((계약|가입)(하지|은)\s*않|(계약|가입)\s*안\s*했|(계약|가입)한\s*적\s*없)"),
        "multilevel": _has(t, r"(다단계|판매원으로|하위\s*판매)", neg_aware=True, neg_patterns=_NOUN_NEG),
        "subscribe": _has(t, r"(구독|정기\s*결제|멤버십|자동\s*결제)", neg_aware=True, neg_patterns=_NOUN_NEG),
        "sangjo": _has(t, r"(상조|선불식)", neg_aware=True, neg_patterns=_NOUN_NEG),
        "installment": _has(t, r"(할부)"),
        "purchase": _has(t, r"(샀|구매|주문|결제|산\s)"),
    }


def classify(text):
    """(case_id, label, clarify) 반환. 확신 낮으면 clarify에 확인 질문."""
    s = extract_signals(text)

    if s["multilevel"]:
        return "multilevel", "다단계판매 관련", None
    if s["sangjo"]:
        return "sangjo", "상조(선불식 할부거래)", None
    if s["academy"]:
        # 학원은 폐업이든 해지든 학원법 별도 기준 — 체육시설과 분리
        return "academy", "학원·교습소 환불", None
    if s["gym"]:
        if s["closed"]:
            return "gym_close", "체육시설 폐업·연락두절", None
        if s["quit"]:
            return "gym_quit", "체육시설 중도해지", None
        return "gym_quit", "체육시설 환불", "폐업인가요, 아니면 다니는 중 해지인가요?"
    if s["closed"]:
        return "biz_close", "업체 폐업·연락두절", None
    if s["door"]:
        return "door_sale", "방문·전화권유 판매", None
    if s["subscribe"]:
        return "subscribe", "구독·정기결제 해지", None
    if s["online"] and s["offline"]:
        # 온라인 주문 + 매장 수령 등 혼합 채널 — 주문 경로에 따라 적용 법이 다르므로 단정 금지
        return "general", "구매 채널 확인", "주문을 온라인(앱·인터넷)으로 하셨나요, 매장에서 직접 계약하셨나요? 주문 경로에 따라 적용 법이 달라집니다."
    if s["offline"]:
        return "offline_purchase", "오프라인 매장 구매", None
    if s["online"]:
        if s["refuse"]:
            return "online_refuse", "온라인 구매 환불 거부", None
        if s["change_mind"]:
            return "online_change", "온라인 구매 단순변심 반품", None
        if s["purchase"] or s["quit"]:
            return "online_change", "온라인 구매 반품", "판매자가 반품을 거부했나요?"
    if (s["refuse"] or s["change_mind"]) and s["purchase"]:
        # 채널 미상 — 온라인/오프라인에 따라 적용법이 다르므로 단정하지 않음
        return "general", "환불 분쟁", "온라인(인터넷·앱) 구매인가요, 매장에서 직접 구매인가요?"
    return "general", "환불 상담", "무엇을 어디서(온라인/매장/방문판매) 어떻게 결제하셨는지 알려주시면 정확히 짚어드립니다."


# ---------- 유형별 지식 (조건부 표현·간결) ----------
KNOWLEDGE = {
    "online_change": {
        "verdict": "받은 날부터 7일 이내이고 예외 사유가 없다면 단순변심이어도 청약철회(반품)가 가능할 수 있습니다(전자상거래법 제17조).",
        "checks": [
            "받은 날부터 7일이 지났는지 (사업자 방해로 철회를 못 했다면 방해가 끝난 날부터 다시 7일)",
            "예외 해당 여부: 사용·훼손으로 가치 감소, 복제 가능 상품 개봉, 시간 경과로 재판매 곤란, 주문제작(사전 고지+서면 동의가 있었던 경우) 등",
            "단순변심 반품비는 소비자 부담",
        ],
        "steps": [
            "기록이 남는 방법으로 판매자에게 철회 의사 통보",
            "거부 시 통보 기록을 갖고 1372 상담",
        ],
    },
    "online_refuse": {
        "verdict": "기간 내이고 예외 사유가 없다면 판매자가 임의로 환불을 거부하기 어렵습니다. '환불 불가' 고지만으로 법정 철회권이 없어지지 않습니다.",
        "checks": [
            "받은 날부터 7일 이내인지, 상품을 사용·훼손하지 않았는지",
            "상품이 표시·광고와 다르면 7일이 지나도 공급일부터 3개월(안 날부터 30일) 내 철회 가능 + 반품비 판매자 부담",
            "환급은 재화 반환일부터 3영업일 내(미공급 용역 등은 철회일 기준)",
        ],
        "steps": [
            "환불 요구·거부 답변 캡처 보존",
            "1372 상담 → 한국소비자원 피해구제",
            "카드 결제면 카드사 이의제기 병행",
        ],
    },
    "offline_purchase": {
        "verdict": "매장 직접 구매는 전자상거래법 청약철회(7일) 적용 대상이 아닙니다. 단순변심 반품은 판매자 약정·교환 정책에 따르고, 하자가 있다면 민법·소비자분쟁해결기준에 따라 수리·교환·환불을 요구할 수 있습니다.",
        "checks": [
            "하자·불량인지 단순변심인지",
            "영수증·구매 증빙 보유 여부",
        ],
        "steps": [
            "하자면 구매처에 교환·환불 요구(증빙 지참)",
            "분쟁 시 1372 상담",
        ],
    },
    "gym_quit": {
        "verdict": "헬스장 등 '계속거래'(1개월 이상 계속 공급 + 해지 시 환급 제한·위약금 약정이 있는 거래)는 계약기간 중 해지를 요구할 수 있는 경우가 많습니다(방문판매법 제31조). '환불 불가' 특약이 있어도 그대로 인정되지 않을 수 있습니다.",
        "checks": [
            "소비자 사정 해지(기간제): 개시 전 = 총이용금액의 10% 공제, 개시 후 = 경과 기간 이용금액 + 10% 공제(횟수제는 사용 횟수 비율)",
            "사업자 잘못(시설 폐쇄 등)이면 반대로 사용분 공제 후 환급 + 총이용금액 10% 배상 방향",
            "계약 형태별 정확한 산식은 1372에서 확인",
        ],
        "steps": [
            "기록이 남는 방법으로 해지 의사 통보(통보일 기준 정산)",
            "과다 공제 시 계약서·결제내역 갖고 1372 상담",
            "카드 3개월 이상 할부였다면 할부항변권 검토",
        ],
    },
    "gym_close": {
        "verdict": "폐업이라도 결제 수단에 따라 회수 방법이 있습니다. 카드 3개월 이상 할부였다면 남은 할부금 지급을 거절할 수 있는 할부항변권(할부거래법 제16조)을 검토할 수 있습니다.",
        "checks": [
            "결제 수단: 카드 할부(20만원 이상·3개월 이상)인지, 일시불·현금인지",
            "폐업 여부: 홈택스 '사업자등록상태 조회'로 확인(로그인 불필요. 세법상 등록 상태 기준)",
            "폐업으로 서비스를 못 받는 것은 항변 사유인 '미공급·채무불이행'에 해당할 수 있음",
        ],
        "steps": [
            "할부면: 카드사에 항변권 행사 문의 + 서면 통지(증빙 첨부)",
            "일시불·현금이면: 1372 상담 + 내용증명 + 소액사건심판(3,000만원 이하 금전 청구) 검토",
            "증거 보존(계약서·결제내역·폐업 공지)",
        ],
    },
    "academy": {
        "verdict": "학원·교습소 환불은 학원법(시행령 별표의 교습비 반환 기준)이 별도로 적용됩니다. 체육시설과 산식이 다르니 혼동하지 마세요.",
        "checks": [
            "교습 개시 전 해지: 전액 반환이 원칙",
            "개시 후: 남은 기간 비율 기준 반환(월 단위 등 별표 산식) — 교육청·1372에서 정확 산식 확인",
            "원장 잠적·폐원이면 결제 수단 확인(카드 할부면 항변권 검토)",
        ],
        "steps": [
            "기록이 남는 방법으로 환불 요구",
            "관할 교육청 학원 민원 또는 1372 상담",
        ],
    },
    "door_sale": {
        "verdict": "방문판매·전화권유판매는 계약서를 받은 날부터 14일 이내 청약철회가 가능할 수 있습니다(방문판매법 제8조).",
        "checks": [
            "기산점: 계약서 받은 날부터 14일 (재화 공급이 계약서 교부보다 늦으면 공급받은 날부터)",
            "계약서를 못 받았거나 철회 안내가 없었다면 기산점이 더 늦춰질 수 있음(안 날 기준)",
        ],
        "steps": [
            "14일 내 서면(내용증명 권장)으로 철회 통보",
            "거부 시 1372 상담",
        ],
    },
    "multilevel": {
        "verdict": "다단계판매는 일반 소비자와 판매원의 철회 기간이 다릅니다. 소비자는 14일, 다단계판매원의 재화 구매는 원칙적으로 계약일부터 3개월 등 별도 규정(방문판매법 제17조)이 적용됩니다.",
        "checks": ["본인이 소비자로 구매했는지, 판매원 자격으로 구매했는지"],
        "steps": ["지위(소비자/판매원)를 확인한 뒤 1372 상담으로 정확한 철회 기간 확인"],
    },
    "subscribe": {
        "verdict": "구독·정기결제는 해지 시 잔여분 환불을 요구할 수 있는 경우가 많습니다. 해지를 어렵게 만드는 구조는 전자상거래법 위반 소지가 있습니다.",
        "checks": ["결제 경로(앱스토어/자체 결제)에 따라 환불 절차가 다름", "이용분 공제 후 잔액 환불이 기본 방향"],
        "steps": ["결제 경로의 공식 해지·환불 절차 진행(기록 보존)", "거부 시 1372 상담 + 카드사 이의제기"],
    },
    "sangjo": {
        "verdict": "상조(선불식)는 법정 보전 제도가 있습니다. 다만 보전 대상은 원칙적으로 '선수금에서 이미 제공받은 재화·용역 가액을 뺀 금액의 50%'이고, 실제 지급액은 개인별 등록 보전액에 따라 다릅니다(할부거래법 제27조).",
        "checks": [
            "공정위 '내상조 찾아줘'(mysangjo.or.kr)에서 내 가입·보전기관·보전액 확인",
            "정상 영업 중 해지는 해약환급금 기준(공정위 고시) 적용",
        ],
        "steps": ["보전기관 등록 내역 확인 후 피해보상금 신청", "분쟁 시 1372 상담"],
    },
    "biz_close": {
        "verdict": "업체가 폐업·잠적해도 결제 수단에 따라 구제 경로가 있습니다.",
        "checks": [
            "카드 할부(20만원 이상·3개월 이상) 여부 — 해당하면 할부항변권 검토",
            "홈택스 '사업자등록상태 조회'로 폐업 확인(세법상 등록 상태 기준)",
        ],
        "steps": ["할부면 카드사에 항변권 행사 문의(서면)", "일시불·현금이면 1372 상담 + 지급명령·소액사건 검토", "증거 보존"],
    },
    "general": {
        "verdict": "상황에 따라 적용되는 법(전자상거래 7일 / 방문판매 14일 / 계속거래 해지 / 할부항변권)이 다릅니다.",
        "checks": ["무엇을(상품/서비스), 어디서(온라인/매장/방문판매), 어떻게 결제(일시불/할부)했는지가 판단 기준"],
        "steps": ["위 정보를 알려주시면 해당 권리를 짚어드립니다", "공통: 증거 보존 + 1372 상담"],
    },
}

# ---------- 할부항변권 (v2.6: 구조화 확정 사유만 positive gate 통과) ----------
InstallmentGroundCode = Literal[
    "contract_invalid",
    "contract_ended",
    "supply_not_completed",
    "warranty_unfulfilled",
    "purpose_failed_by_breach",
    "lawful_withdrawal",
]
InstallmentGroundFact = Literal[
    "installment_contract_scope",
    "contract_invalid_confirmed",
    "contract_ended_confirmed",
    "supply_time_reached",
    "actual_non_supply",
    "warranty_duty_exists",
    "warranty_duty_unfulfilled",
    "seller_breach_confirmed",
    "contract_purpose_unattainable",
    "withdrawal_legally_available",
    "withdrawal_exercised",
]

GROUND_REQUIRED_FACTS = {
    "contract_invalid": frozenset(("installment_contract_scope", "contract_invalid_confirmed")),
    "contract_ended": frozenset(("installment_contract_scope", "contract_ended_confirmed")),
    "supply_not_completed": frozenset(("installment_contract_scope", "supply_time_reached", "actual_non_supply")),
    "warranty_unfulfilled": frozenset(("installment_contract_scope", "warranty_duty_exists", "warranty_duty_unfulfilled")),
    "purpose_failed_by_breach": frozenset(("installment_contract_scope", "seller_breach_confirmed", "contract_purpose_unattainable")),
    "lawful_withdrawal": frozenset(("installment_contract_scope", "withdrawal_legally_available", "withdrawal_exercised")),
}

# 할부거래법 제16조 제1항 1~6호와 일대일 대응한다. 자유문장은 이 코드의 후보를
# 되물을 법정 사유 후보를 찾는 데만 쓴다. 이 입력만으로 권리를 확정하지 않는다.
INSTALLMENT_GROUNDS = {
    "contract_invalid": {
        "label": "할부계약 불성립·무효",
        "pattern": r"(무효|불성립|성립.{0,6}(안|않))",
        "confirm": "할부계약이 실제로 성립하지 않았거나 무효로 확정됐나요?",
    },
    "contract_ended": {
        "label": "할부계약 취소·해제·해지",
        "pattern": r"(취소|해제|해지)",
        "confirm": "계약의 취소·해제·해지가 접수 단계가 아니라 실제로 완료됐나요?",
    },
    "supply_not_completed": {
        "label": "정해진 시기까지 재화·용역 전부 또는 일부 미공급",
        "pattern": r"(폐업|문\s*을?\s*닫|먹튀|잠적|연락\s*두절|영업\s*중단|공급.{0,6}(안|못)|이행.{0,6}(안|못|중단)|서비스.{0,8}(중단|못\s*받))",
        "confirm": "폐업·연락두절 사실 외에, 약정한 재화나 남은 서비스가 정해진 때까지 실제로 제공되지 않았나요?",
    },
    "warranty_unfulfilled": {
        "label": "하자담보책임 미이행",
        "pattern": r"(하자\s*담보.{0,10}(불이행|이행.{0,5}(안|않|못))|하자|불량|고장)",
        "confirm": "하자 자체뿐 아니라 판매자가 수리·교환 등 하자담보책임을 실제로 이행하지 않았나요?",
    },
    "purpose_failed_by_breach": {
        "label": "판매자 채무불이행으로 할부계약 목적 달성 불가",
        "pattern": r"(채무\s*불이행|계약\s*목적.{0,10}(달성.{0,4}(못|불가)|불가능)|약속.{0,8}(다르|어김|불이행)|계약.{0,8}(다르|위반))",
        "confirm": "판매자의 채무불이행 때문에 할부계약의 목적을 실제로 달성할 수 없게 됐나요?",
    },
    "lawful_withdrawal": {
        "label": "다른 법률에 따라 정당하게 행사한 청약철회",
        "pattern": r"(청약\s*철회|철회)",
        "confirm": "다른 법률의 요건·기간을 지켜 청약철회 의사를 실제로 통지했나요?",
    },
}
_GROUND_PATTERNS = [(code, spec["pattern"]) for code, spec in INSTALLMENT_GROUNDS.items()]

# 행동문서를 열 수 있는 '완전한 법정 사유'의 보수적 화이트리스트.
# 위 pattern은 되물음을 위한 후보 탐지이고, 아래 패턴도 공식 확인에 보낼 후보를 좁히는 용도다.
_FULL_GROUND_PATTERNS = {
    "contract_invalid": (
        re.compile(
            r"할부\s*계약(?:이|은|자체가)?\s*(?:"
            r"성립하지\s*않았(?:습니다|어요)|성립\s*안\s*됐(?:습니다|어요)|"
            r"불성립(?:으로|임이|이)?\s*(?:확인됐습니다|확인됐어요|확정됐습니다|확정됐어요|판정됐습니다|확인되었습니다|확정되었습니다|입니다)|"
            r"무효(?:로|임이|라고)?\s*(?:확인됐습니다|확인됐어요|확정됐습니다|확정됐어요|판정됐습니다|결정됐습니다|확인되었습니다|확정되었습니다|입니다)"
            r")"
        ),
    ),
    "contract_ended": (
        re.compile(
            r"할부\s*계약(?:이|은|을|를|의)?\s*(?:이미\s*)?(?:적법하게\s*)?(?:취소|해제|해지)(?:가|를|을)?\s*(?:이미\s*)?(?:"
            r"완료(?:됐습니다|됐어요|되었습니다|했습니다|했어요)|"
            r"확정(?:됐습니다|됐어요|되었습니다)|"
            r"됐습니다|됐어요|되었습니다|했습니다|했어요|하였습니다|한\s*상태입니다"
            r")"
        ),
    ),
    "supply_not_completed": (
        re.compile(
            r"(?:남은|약정한|계약한|제공받기로\s*한).{0,14}(?:서비스|용역|수업|강의|이용권).{0,24}(?:"
            r"제공(?:이|을)?\s*(?:되지\s*않았습니다|받지\s*못했습니다)|"
            r"공급(?:이|을)?\s*(?:되지\s*않았습니다|받지\s*못했습니다)|"
            r"받지\s*못(?:했습니다|했어요|하고\s*있습니다)|"
            r"못\s*받(?:았습니다|았어요|고\s*있습니다|아요|아(?=\s|$))|"
            r"중단.{0,12}(?:이용하지\s*못|받지\s*못)|"
            r"미공급(?:됐습니다|되었습니다|입니다)|미이행(?:됐습니다|되었습니다|입니다)"
            r")"
        ),
    ),
    "warranty_unfulfilled": (
        re.compile(
            r"(?:하자\s*담보\s*책임|보증\s*의무).{0,24}(?:"
            r"이행하지\s*않았(?:습니다|어요)|이행\s*안\s*했(?:습니다|어요)|이행되지\s*않았습니다|미이행(?:됐습니다|되었습니다|입니다)|"
            r"불이행(?:이\s*확인됐습니다|입니다)|거부(?:됐습니다|당했습니다|했습니다)"
            r")"
        ),
        re.compile(
            r"(?:제품|상품|물품).{0,18}(?:하자|불량|고장).{0,24}(?:판매자|업체|사업자).{0,20}(?:수리|교환|하자\s*처리|보증).{0,16}(?:"
            r"거부했(?:습니다|어요)|안\s*해(?:줘요|줍니다)|해주지\s*않았(?:습니다|어요)|"
            r"이행하지\s*않았(?:습니다|어요)|처리하지\s*않았(?:습니다|어요)|미이행(?:했습니다|상태입니다))"
        ),
        re.compile(
            r"(?:판매자|업체|사업자).{0,18}(?:하자|불량|고장).{0,16}(?:수리|교환|하자\s*처리|보증).{0,16}(?:"
            r"거부했(?:습니다|어요)|안\s*해(?:줘요|줍니다)|해주지\s*않았(?:습니다|어요))"
        ),
    ),
    "purpose_failed_by_breach": (
        re.compile(
            r"(?<![가-힣])(?:판매자|할부거래업자|업체).{0,20}(?:채무\s*불이행|계약\s*위반|약속(?:과|이)\s*(?:다른|달라|어긋)|약정(?:과|이)\s*(?:다른|달라|어긋)).{0,42}"
            r"(?:계약\s*)?목적.{0,18}(?:달성(?:할\s*수\s*없(?:습니다|어요)|하지\s*못했(?:습니다|어요)|이\s*불가합니다)|"
            r"못\s*달성했(?:습니다|어요)|불가능(?:합니다|해졌어요))"
        ),
    ),
}
_LAWFUL_WITHDRAWAL_CONTEXT = re.compile(
    r"(적법|정당(?:하게|한)|요건(?:을|이)?\s*충족|법정\s*기간|기간\s*(?:안|내))"
)
_WITHDRAWAL_EXERCISED = re.compile(
    r"(?:청약\s*철회|철회\s*통지).{0,24}(?:"
    r"행사(?:했습니다|했어요)|발송(?:했습니다|했어요)|보냈(?:습니다|어요)|"
    r"도달(?:했습니다|했어요)|완료(?:됐습니다|되었습니다))"
)
_SUPPLY_TIME_REACHED = re.compile(
    r"(?:(?:배송|공급|제공)\s*)?(?:예정일|기한|시기|약속한\s*(?:날|날짜)).{0,20}"
    r"(?:지났|도과|넘었|경과)|(?:지났|도과|넘었|경과).{0,16}(?:예정일|기한|시기|약속한\s*(?:날|날짜))"
)
_GOODS_NOT_SUPPLIED = re.compile(
    r"(?:재화|상품|제품|물품|배송).{0,28}(?:받지\s*못했(?:습니다|어요)|"
    r"못\s*받았(?:습니다|어요)|배송되지\s*않았(?:습니다|어요)|"
    r"미배송(?:입니다|됐습니다)|미공급(?:입니다|됐습니다))"
)
_COMMON_REFUTATION = re.compile(
    r"(사실(?:이|은)?\s*(?:아니|아닙)|틀린\s*말|거짓|사실무근|오보|"
    r"단정(?:하|하기).{0,6}어렵|볼\s*수(?:는|도)?\s*없)"
)
_ASSERTION_TAIL_VETO = re.compile(
    r"^\s*(?:[?？]|맞(?:나요|습니까)|인가요|건가요|일까요|인지|"
    r"[\"'”’]?\s*(?:라고|라는|라며)|(?:가|이)?\s*아니(?:라|고|며)|"
    r"[,，.。;；]\s*.*(?:말(?:했|했다|합니다|씀)|안내(?:했|했다|받)|"
    r"알려(?:줬|주었|졌)|들었|전해|이야기|얘기|소문|확인하지\s*못|"
    r"(?:판결문|확인서|내역|계약서|발송증명).{0,16}(?:받지|보지)\s*못))"
)
_POST_ASSERTION_VETO = re.compile(
    r"(전해\s*들|들었습니다|들었어요|말(?:했|했다|합니다|씀)|"
    r"안내(?:했|했다|받)|알려(?:줬|주었|졌)|소문|아마|확실하지|확실한지|"
    r"정확한지|사실인지|그런\s*것\s*같|것\s*같습니다|제\s*추측|추정|모르|"
    r"여부.{0,10}(?:미확인|불확실)|판단.{0,8}맞(?:습니까|나요)|"
    r"(?:다음|향후).{0,10}(?:상황|가정)|가정한\s*표현|상정|"
    r"(?:예시\s*통지서|문구).{0,20}(?:넣어|작성|요청)|넣어\s*달)"
)
_GROUND_CONTRADICTIONS = {
    "contract_invalid": (
        re.compile(r"할부\s*계약.{0,24}(?:유효(?:합니다|하지만|하며|하고|함|한\s*상태)|정상적으로\s*성립)"),
    ),
    "contract_ended": (
        re.compile(r"할부\s*계약.{0,28}(?:아직\s*)?(?:계속\s*)?(?:유지(?:\s*중|되고\s*있|됩니다)|유효(?:합니다|한\s*상태))"),
        re.compile(r"(?:취소|해제|해지).{0,14}(?:접수만|신청만|예정|계획|의향|원함)"),
        re.compile(r"할부\s*계약.{0,22}(?:종료|취소|해제|해지).{0,10}(?:되지\s*않|안\s*됐|아니)"),
    ),
    "supply_not_completed": (
        re.compile(
            r"정상\s*(?:제공|이행|운영|영업|이용)(?:하고\s*있|\s*중(?:입니다|이에요|이고|이며|인데|입니다만|$))"
        ),
        re.compile(r"승계.{0,24}정상\s*(?:제공|이행|운영|이용)"),
        re.compile(r"(?:공급|배송|제공)?\s*(?:예정일|기한|시기).{0,18}(?:다음|아직|도래\s*전)|아직.{0,12}(?:기한|예정일|시기)\s*전"),
        re.compile(r"(?:모두|전부).{0,14}(?:정상\s*이용|정상\s*제공|이용\s*완료|제공\s*완료)|(?:약정|계약).{0,12}(?:만료|완료)"),
        re.compile(r"(?:무료\s*체험|체험\s*서비스)|(?:소비자|수강생|구매자).{0,14}(?:일시\s*정지|중단\s*요청|정지\s*요청)"),
    ),
    "warranty_unfulfilled": (
        re.compile(r"(?:무상\s*)?(?:수리|교환|보증|하자\s*처리).{0,16}(?:진행\s*중|이행\s*중|완료됐|완료되었습니다)"),
        re.compile(r"(?:보증|담보)\s*기간.{0,16}(?:끝|만료|지났|경과)|유상\s*수리"),
        re.compile(r"(?:하자|불량|고장).{0,12}(?:없|아니)|(?:하자\s*담보\s*책임|보증\s*의무).{0,14}(?:없|아니)|보증.{0,12}대상.{0,8}아(?:니|닌|님)"),
    ),
    "purpose_failed_by_breach": (
        re.compile(r"계약\s*목적.{0,16}(?:달성했습니다|달성됐습니다|달성\s*가능|달성할\s*수\s*있)"),
        re.compile(r"정상\s*이용\s*중"),
        re.compile(r"판매자.{0,12}(?:잘못|책임|귀책).{0,8}(?:없|아니)|소비자.{0,12}(?:책임|귀책)"),
        re.compile(r"(?:제3자|배송\s*업체|배송업체|구매자|소비자).{0,16}(?:책임|귀책|계약\s*위반)"),
    ),
    "lawful_withdrawal": (
        re.compile(r"(?:청약\s*)?철회.{0,16}(?:기간\s*(?:경과|도과)|불가|무효|적법하게\s*거절)"),
        re.compile(r"기간.{0,12}(?:지났|경과했|도과했)"),
        re.compile(r"(?:전자상거래법|방문판매법|다른\s*법률).{0,20}(?:적용\s*대상.{0,6}아(?:니|닌|님|냐|닐|닙)|적용되지\s*않|미적용)"),
        re.compile(r"(?:주문\s*제작|맞춤\s*제작).{0,12}(?:예외|철회\s*제한)|요건.{0,12}충족하지\s*못|(?:적용|기간|요건).{0,12}(?:미확인|확인하지\s*않|알\s*수\s*없)"),
    ),
}


def _has_direct_match(regexes, reason_text):
    """확정형 문구 뒤에 물음표·전언·즉시 반전이 붙으면 사실 진술로 보지 않는다."""
    for rx in regexes:
        for match in rx.finditer(reason_text):
            tail = reason_text[match.end():]
            if not (_ASSERTION_TAIL_VETO.search(tail) or _POST_ASSERTION_VETO.search(tail)):
                return True
    return False


def _matches_full_ground(reason_text, ground_code):
    """법 제16조 제1항의 선택된 사유 전체가 확정 사실로 표현됐는지 확인한다."""
    rt = _norm(reason_text or "")
    if _COMMON_REFUTATION.search(rt):
        return False
    if ground_code == "supply_not_completed":
        service_stopped = _has_direct_match(_FULL_GROUND_PATTERNS[ground_code], rt)
        goods_overdue = bool(
            _SUPPLY_TIME_REACHED.search(rt)
            and _has_direct_match((_GOODS_NOT_SUPPLIED,), rt)
        )
        return service_stopped or goods_overdue
    if ground_code == "lawful_withdrawal":
        return bool(
            _LAWFUL_WITHDRAWAL_CONTEXT.search(rt)
            and _has_direct_match((_WITHDRAWAL_EXERCISED,), rt)
        )
    return _has_direct_match(_FULL_GROUND_PATTERNS.get(ground_code, ()), rt)


def _contradicts_full_ground(reason_text, ground_code):
    """확정 사유 뒤에 정상 이행·계약 유지·기간 경과 등 반대 사실이 있으면 차단한다."""
    rt = _norm(reason_text or "")
    if _COMMON_REFUTATION.search(rt):
        return True
    return any(rx.search(rt) for rx in _GROUND_CONTRADICTIONS.get(ground_code, ()))


_NO_GROUND = re.compile(r"(단순\s*변심|그냥\s*(환불|취소|해지)|마음이\s*바뀌|정상\s*(제공|영업|운영)\s*중|문제.{0,4}없)")
# 불확실·희망 어휘 (부정 코어는 파일 상단 _NEG_CORE 단일 정의를 참조)
_UNCERTAIN = re.compile(r"(아마|혹시|것\s*같|같(?:아요|습니다|다)|듯\s*하|듯한|모르|인지\s*모|카더라|의심|의문|추정|생각|아닐까|가능성|가능한지|궁금|일\s*수|일지도|여부)")
_NEG_WIDE = re.compile(r"(하지\s*않|않았|안\s*(했|됐|당했|한)|(는|이|가)?\s*" + _NEG_CORE + r"|같지\s*않|없)")
_PAST_FLIP = re.compile(r"(이었|였는데|었는데|았는데|였다가|었다가|더니)")  # 과거형 = 현재는 뒤집혔을 수 있음

_GROUND_EVENT = r"(?:폐업|문\s*을?\s*닫|잠적|연락\s*두절|영업\s*중단|하자|불량|고장|무효|불성립|취소|해제|해지|청약\s*철회|철회)"
_NEGATED_GROUND = re.compile(
    _GROUND_EVENT
    + r"\s*(?:(?:은|는|이|가|도|만)\s*)?"
      r"(?:(?:한|된)\s*(?:것|건)\s*(?:은|이|도)?\s*)?"
      r"(?:전혀\s*)?"
      r"(?:안\s*(?:해|함|하|할|했|된|됐)|"
      r"(?:하|되)?지(?:는|도|만|조차)?\s*않|"
    + _NEG_CORE
    + r"|없|커녕|(?:라고\s*)?(?:보|볼)\s*수\s*없|"
      r"(?:라고\s*)?보기\s*어렵|(?:이라고\s*)?단정할\s*수\s*없)"
)
_GROUND_DENIAL = re.compile(
    _GROUND_EVENT
    + r".{0,16}(사실무근|오보|(?:라고|이라고)?\s*(?:보|볼)\s*수\s*없|"
      r"(?:라고|이라고)?\s*보기(?:는|도)?\s*어렵|(?:이라고)?\s*단정할\s*수\s*없)"
)
_GROUND_QUESTION = re.compile(
    r"(혹시|" + _GROUND_EVENT
    + r".{0,8}(했나요|한가요|인가요|건가요|있나요|가능한가요|일까요|인지\s*(확인|궁금|모르)))"
)
_HEARSAY = re.compile(r"(소문|카더라|들었|전해\s*들|라던데|(?:라고|다고)\s*(합니다|해요|함))")
_FUTURE_OR_HYPOTHETICAL = re.compile(
    r"(예정|계획|가정|만약|대비|" + _GROUND_EVENT
    + r".{0,8}(하면|이면|한다면|있다면|생기면|될\s*경우|할\s*경우|했을\s*때))"
)
_GROUND_REQUEST = re.compile(
    r"(?:취소|해제|해지|청약\s*철회|철회).{0,10}"
    r"(?:부탁|요청|문의|해\s*주|하고\s*싶|원해|원합니다|희망)"
)


def _has_nonfact_signal(reason_text):
    """확정 사실이 아닌 부정·질문·전언·불확실·미래·요청 표현을 문장 전체에서 찾는다."""
    rt = _norm(reason_text or "")
    return any(rx.search(rt) for rx in (
        _NEGATED_GROUND,
        _GROUND_DENIAL,
        _GROUND_QUESTION,
        _HEARSAY,
        _UNCERTAIN,
        _FUTURE_OR_HYPOTHETICAL,
        _GROUND_REQUEST,
    ))


def _find_ground(reason_text):
    """법정 항변 사유 후보 탐지 v4.

    반환: 사유 코드(str) | None(사유 미확인) | False(사유 아님 확정) |
    "UNCERTAIN"(비확정). 이 함수는 후보·차단만 담당하며 권리를 확정하지 않는다.
    """
    rt = reason_text or ""
    m_ng = _NO_GROUND.search(rt)
    if m_ng:
        ng_tail = rt[m_ng.end():m_ng.end() + 12]
        # "정상 영업 중" = 사유 아님. 단 부정("~이 아니다")이나 과거형("~이었는데")이면 뒤집지 않음
        if not (_NEG_WIDE.search(ng_tail) or _PAST_FLIP.search(ng_tail)):
            return False
    if _has_nonfact_signal(rt):
        return "UNCERTAIN"
    for code, rx in _GROUND_PATTERNS:
        m = re.search(rx, rt)
        if not m:
            continue
        pre = rt[max(0, m.start() - 4):m.start()]
        post = rt[m.end():m.end() + 20]
        # 제16조 제1항 제5호 자체가 '계약 목적을 달성할 수 없음'을 요건으로 하므로,
        # 이 코드의 '없음/불가'를 사유 부정으로 뒤집지 않는다.
        post_is_negation = _NEG_WIDE.search(post) and code != "purpose_failed_by_breach"
        if re.search(r"안\s*$", pre) or post_is_negation:
            continue  # 앞선/뒤따르는 부정 — 사실 아님
        return code
    return None


def installment_defense(
    amount_won,
    months,
    has_remaining,
    reason_text="",
    *,
    ground_code: Optional[InstallmentGroundCode] = None,
    ground_confirmed: Optional[bool] = None,
    ground_facts: Optional[List[InstallmentGroundFact]] = None,
):
    """할부항변권 안내 v4 — 자동 확정 없이 공식 확인 경로로 연결.

    반환 (status, reasons, steps): status ∈ {"not_met","review","need_info"}
    - 수량 요건 + 유효한 ground_code + ground_confirmed is True + 해당 사유의
      필수 ground_facts(같은 할부계약 범위 포함) + 문장 일치가 모두 필요.
    - 모두 충족해 보여도 증빙 진위·동일 계약 관련성·법 적용을 독립 확인할 수 없으므로
      자동 확정하지 않고 review와 카드사 공식 양식·상담 경로를 반환한다.
    """
    if amount_won is None or months is None:
        return "need_info", ["결제 총액과 할부 개월수를 알려주시면 판정해 드립니다"], []

    reasons, quant_ok = [], True
    if amount_won >= 200000:
        reasons.append("결제 총액 %s원 — 20만원 이상 충족 (신용카드 기준)" % format(amount_won, ","))
    else:
        reasons.append("결제 총액 %s원 — 신용카드 기준 20만원 미만" % format(amount_won, ","))
        quant_ok = False
    if months >= 3:
        reasons.append("%d개월 할부 — 3회 이상 분할(2개월 이상) 요건에 해당" % months)
    else:
        reasons.append("%d개월 — 일시불·2개월은 할부거래법상 할부계약이 아닐 수 있음" % months)
        quant_ok = False
    if has_remaining:
        reasons.append("남은 할부금 있음 — 항변권은 '앞으로 낼 잔여 할부금'의 지급 거절 권리")
    else:
        reasons.append("남은 할부금 없음(완납) — 항변권 대상이 아니며 별도 환불 절차 필요")
        quant_ok = False

    if not quant_ok:
        return "not_met", reasons, [
            "항변권 요건이 안 되어도 방법이 있습니다:",
            "- 1372 상담 → 한국소비자원 피해구제",
            "- 소액이면 지급명령·소액사건심판(3,000만원 이하 금전 청구) 검토",
        ]

    # 구조화 값이 없으면 자유문장은 되물음·명백한 불성립 판정에만 사용한다.
    # 어떤 긍정형 자유문장이나 구조값도 자동 권리 확정을 열 수 없다.
    if ground_confirmed is not True:
        ground = _find_ground(reason_text)
        if ground is False:
            reasons.append("사유: 단순변심·정상 제공 중이면 법정 항변 사유(미공급·하자·해지 등)에 해당하지 않습니다")
            return "not_met", reasons, [
                "항변권은 업체의 미공급·불이행 등이 있어야 합니다. 단순변심 해지는 위의 중도해지·청약철회 경로로 진행하세요 (1372 확인)",
            ]
        if ground == "UNCERTAIN":
            reasons.append("항변 사유로 보이는 정황이 있으나 사실 여부가 불확실합니다(추측·전언 표현)")
            return "review", reasons, [
                "사실 확인이 먼저입니다: 홈택스 사업자등록상태 조회, 업체 공지·연락 기록 등으로 확인한 뒤 다시 알려주세요",
            ]
        reasons.append("항변 사유가 실제로 발생한 사실인지 확인이 필요합니다")
        return "review", reasons, [
            "업체 공지·계약서·서비스 중단 기록 등으로 확인된 사실과 실제 미이행 내용을 알려주세요",
        ]
    if ground_code not in INSTALLMENT_GROUNDS:
        reasons.append("법정 항변 사유의 종류가 확정되지 않았습니다")
        return "review", reasons, [
            "확인된 사실이 계약 무효·해지·미공급·하자담보 미이행·채무불이행·적법 철회 중 무엇인지 확인해 주세요",
        ]
    required_facts = GROUND_REQUIRED_FACTS[ground_code]
    provided_facts = frozenset(ground_facts or ())
    if provided_facts != required_facts:
        reasons.append("선택한 법정 사유의 필수 사실과 이 할부계약의 관련성이 모두 확인되지 않았습니다")
        return "review", reasons, [
            INSTALLMENT_GROUNDS[ground_code]["confirm"],
        ]
    if _contradicts_full_ground(reason_text, ground_code):
        reasons.append("입력 문장에 선택한 항변 사유와 반대되는 사실이 함께 있어 판정을 확정할 수 없습니다")
        return "review", reasons, [
            "현재 실제 상태(정상 제공 여부·계약 유지 여부·철회 기간 등)를 다시 확인해 주세요",
        ]
    if not _matches_full_ground(reason_text, ground_code):
        reasons.append("입력 문장만으로는 선택한 법정 항변 사유의 전체 요건이 확인되지 않습니다")
        return "review", reasons, [
            INSTALLMENT_GROUNDS[ground_code]["confirm"],
        ]
    ground_label = INSTALLMENT_GROUNDS[ground_code]["label"]
    reasons.append("법정 사유 후보: %s" % ground_label)
    reasons.append("증빙의 진위·동일 계약 관련성·법 적용은 이 도구가 독립 확인할 수 없어 자동 확정하지 않습니다")
    return "review", reasons, [
        "1. 카드사 콜센터에 할부항변권 담당 부서와 공식 서면 양식을 요청하세요",
        "2. 계약서·결제내역과 해당 사유 증빙을 제출하고 적용 가능 여부를 서면으로 확인하세요",
        "3. 해결되지 않으면 금융감독원 1332 또는 1372에서 확인하세요",
    ]
