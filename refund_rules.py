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


def _norm(t):
    return re.sub(r"\s+", " ", t.strip())


def _negated(text, m_start, patterns=(r"하지\s*않", r"않았", r"안\s*했", r"아(니|닌|님|냐|닐)", r"없")):
    """매치 지점 뒤 12자 내 부정어가 있으면 그 신호를 무효화."""
    tail = text[m_start:m_start + 16]
    return any(re.search(p, tail) for p in patterns)


# 명사(업종·채널) 부정: "학원은 아니고", "학원 수업은 아니고", "온라인 거래가 아닌데" — 동사 부정(하지 않)과 구분
_NOUN_NEG = (r"^\s*[가-힣]{0,4}\s*(은|는|이|가)?\s*(아니|아닌|아님|아냐|말고)",)


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

# ---------- 할부항변권 (v2.1: 법정 사유 — 부정문·희망형 오판 차단) ----------
_GROUND_PATTERNS = [
    ("계약 무효·불성립", r"(무효|불성립|성립.{0,6}(안|않))"),
    ("미공급·이행중단", r"(폐업|문\s*을?\s*닫|먹튀|잠적|연락\s*두절|영업\s*중단|공급.{0,6}(안|못)|이행.{0,6}(안|못|중단)|서비스.{0,8}(중단|못\s*받))"),
    ("하자·불이행", r"(하자|불량|고장|약속.{0,8}(다르|어김|불이행)|계약.{0,8}(다르|위반))"),
    ("계약 취소·해제·해지", r"(취소|해제|해지)"),
    ("적법한 청약철회", r"(청약\s*철회|철회)"),
]
_NO_GROUND = re.compile(r"(단순\s*변심|그냥\s*(환불|취소|해지)|마음이\s*바뀌|정상\s*(제공|영업|운영)\s*중|문제.{0,4}없)")
# 부정·불확실 어휘 통합(음절 활용형 포함) — 여러 정규식에 흩어지며 일부만 고쳐지는 사고 방지
_NEG_CORE = r"아(니|닌|님|냐|닐)"  # 아니/아닌/아님/아냐/아닐 전 활용형
_DESIRE = re.compile(r"(하고\s*싶|싶습니다|싶어요|하려|할래|할까|하면\s*좋|했으면|희망|원해|원합니다|바랍니다)")  # 희망형 = 사실 아님
_UNCERTAIN = re.compile(r"(것\s*같|듯\s*하|듯한|모르겠|인지\s*모| 카더라|들었어|들은\s*것|의심|의문|추정|아닐까|가능성|가능한지|궁금|일지도|다고\s*(합니다|해요|함|하더|해서))")  # 불확실·전언·질문형 = 판정보류
_NEG_WIDE = re.compile(r"(하지\s*않|않았|안\s*(했|됐|당했|한)|(는|이|가)?\s*" + _NEG_CORE + r"|같지\s*않|없)")
_PAST_FLIP = re.compile(r"(이었|였는데|었는데|았는데|였다가|었다가|더니)")  # 과거형 = 현재는 뒤집혔을 수 있음


def _find_ground(reason_text):
    """법정 항변 사유 탐지 v3.

    반환: 라벨(str) | None(사유 미확인) | False(사유 아님 확정) | "UNCERTAIN"(불확실).
    부정문("폐업하지 않았"/"안 망했"), 희망형("취소를 하고 싶다"), 불확실("폐업인 것 같다")은
    사실로 취급하지 않는다 — possible 판정 금지.
    """
    rt = reason_text or ""
    m_ng = _NO_GROUND.search(rt)
    if m_ng:
        ng_tail = rt[m_ng.end():m_ng.end() + 12]
        # "정상 영업 중" = 사유 아님. 단 부정("~이 아니다")이나 과거형("~이었는데")이면 뒤집지 않음
        if not (_NEG_WIDE.search(ng_tail) or _PAST_FLIP.search(ng_tail)):
            return False
    for label, rx in _GROUND_PATTERNS:
        m = re.search(rx, rt)
        if not m:
            continue
        pre = rt[max(0, m.start() - 4):m.start()]
        post = rt[m.end():m.end() + 20]
        if re.search(r"안\s*$", pre) or _NEG_WIDE.search(post):
            continue  # 앞선/뒤따르는 부정 — 사실 아님
        if _DESIRE.search(post[:12]):
            continue  # 희망이지 발생 사실 아님
        if _UNCERTAIN.search(post):
            return "UNCERTAIN"  # 사실 여부 불확실 — 되물음
        return label
    return None


def installment_defense(amount_won, months, has_remaining, reason_text=""):
    """할부항변권 판정 v2.

    반환 (status, reasons, steps): status ∈ {"possible","not_met","review","need_info"}
    - 수량 요건(20만원·3개월·잔여금)과 '법정 항변 사유'가 모두 있어야 possible.
    - 사유가 없거나 불명확하면 review(추가 확인)로. 단정 금지.
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

    ground = _find_ground(reason_text)

    if not quant_ok:
        return "not_met", reasons, [
            "항변권 요건이 안 되어도 방법이 있습니다:",
            "- 1372 상담 → 한국소비자원 피해구제",
            "- 소액이면 지급명령·소액사건심판(3,000만원 이하 금전 청구) 검토",
        ]
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
    if ground is None:
        reasons.append("법정 항변 사유(미공급·폐업으로 인한 불이행·하자·계약 해제 등) 해당 여부가 확인되지 않았습니다")
        return "review", reasons, [
            "무슨 문제가 있었는지(폐업·미공급·하자·계약해지 등)를 알려주시면 사유 해당 여부까지 판정해 드립니다",
        ]
    reasons.append("항변 사유 후보: %s — 증빙으로 뒷받침 필요" % ground)
    return "possible", reasons, [
        "1. 카드사 콜센터에 '할부항변권 행사'를 문의하고 서면 양식 요청",
        "2. 증빙(계약서·결제내역·폐업 조회·이행중단 증거) 첨부해 서면 제출 (서면 발송일에 효력)",
        "3. 다음 결제일에 잔여 할부금 청구 중단 여부 확인",
        "4. 카드사가 거부하면 금융감독원 1332",
    ]
