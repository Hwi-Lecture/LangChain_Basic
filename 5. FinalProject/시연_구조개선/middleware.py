import re

from langchain.agents.middleware import ToolCallLimitMiddleware, after_model, wrap_tool_call
from langchain_core.messages import HumanMessage, ToolMessage

DATA_TOOLS = {"run_sql", "chamber_summary", "daily_trend"}
CHECK_NAME = "report_check"  # 보고서 검사 미들웨어가 넣는 메시지 이름
MAX_RETRY = 2  # 보고서 검사로 다시 쓰게 하는 최대 횟수


def current_turn(messages):
    """마지막 사용자 질문부터 지금까지의 메시지 (보고서 검사 메시지는 사용자 질문으로 치지 않음)"""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.type == "human" and m.name != CHECK_NAME:
            return messages[i:]
    return messages


# ── 미들웨어 1: 데이터를 조회하기 전에는 문서 검색을 막음 ────────
@wrap_tool_call
def require_data_first(request, handler):
    if request.tool_call["name"] == "search_documents":
        turn = current_turn(request.state["messages"])
        called = {c["name"] for m in turn if m.type == "ai" for c in m.tool_calls}
        if not called & DATA_TOOLS:
            return ToolMessage(
                content="[미들웨어 차단] 데이터 조회 도구로 이상이 생긴 설비·챔버·날짜를 먼저 찾은 다음, "
                        "그 설비·챔버·날짜를 검색어에 넣어서 다시 검색하세요.",
                tool_call_id=request.tool_call["id"],
                name="search_documents",
            )
    return handler(request)


# ── 미들웨어 2: 보고서 검사 ─────────────────────────────────
# (1) 답변에 인용한 기록이 실제 검색 결과에 있는지 검사
def find_citation_problems(answer, tool_text, searched):
    problems = []
    for eh_id in sorted(set(re.findall(r"EH-2608-\d{3}", answer))):
        row = next((line for line in tool_text.splitlines() if eh_id in line), None)
        if row is None:
            problems.append(f"{eh_id} : 검색 결과에 없는 이력번호입니다.")
            continue
        # 이력번호와 같은 줄에 적은 설비가 실제 기록의 설비와 다르면 잘못 연결한 것
        row_eq = re.search(r"설비: (ETCH_0\d)", row)
        if row_eq is None:
            continue
        for line in answer.splitlines():
            eqs = list(re.finditer(r"ETCH_0\d", line))
            if eh_id not in line or not eqs:
                continue
            # 한 줄에 설비가 여러 개 나오면 이력번호와 가장 가까운 설비만 비교
            pos = line.index(eh_id)
            nearest = min(eqs, key=lambda m: abs(m.start() - pos)).group()
            if nearest != row_eq.group(1):
                problems.append(f"{eh_id} : 실제 기록은 {row_eq.group(1)}인데 {nearest}로 적었습니다.")

    headers = re.findall(r"\d{2}/\d{2}\([월화수목금토일]\) (?:주간|오후|야간)", answer)
    for h in sorted(set(headers)):
        if h not in tool_text:
            problems.append(f"{h} : 검색 결과에 없는 인수인계 기록입니다.")

    if searched and not re.search(r"EH-2608-\d{3}", answer) and not headers:
        problems.append("관련 기록에 이력번호(EH-2608-xxx)나 인수인계 날짜·교대(예: 08/16(일) 야간)를 적지 않았습니다.")
    return problems


# (2) 추정 원인에 이상이 확인된 설비와 다른 설비의 기록이 들어갔는지 검사
def find_cause_problems(answer, turn, tool_text):
    # 에이전트가 데이터를 조회한 설비 = 이상이 확인된 설비
    checked = set()
    for m in turn:
        if m.type != "ai":
            continue
        for call in m.tool_calls:
            if call["name"] == "daily_trend":
                checked.add(call["args"].get("equipment_id"))
            elif call["name"] == "run_sql":
                checked |= set(re.findall(r"equipment_id\s*=\s*'(ETCH_0\d)'", call["args"].get("query", "")))
    if len(checked) != 1:  # 여러 설비를 조회했으면 어느 설비가 이상인지 판단하지 않음
        return []

    section = re.search(r"추정 원인(.*?)원인에서 제외", answer, re.S)
    if section is None:
        return []
    section = section.group(1)
    target = next(iter(checked))

    # 추정 원인에 적은 설비와, 추정 원인에 인용한 이력번호의 실제 설비를 모두 모음
    others = set(re.findall(r"ETCH_0\d", section))
    for eh_id in set(re.findall(r"EH-2608-\d{3}", section)):
        row = next((line for line in tool_text.splitlines() if eh_id in line), "")
        others |= set(re.findall(r"설비: (ETCH_0\d)", row))
    others = sorted(others - checked)

    problems = []
    if others:
        problems.append(
            f"추정 원인에 {', '.join(others)}의 기록이 들어 있지만, 데이터로 이상이 확인된 설비는 {target}입니다. "
            f"설비가 다른 기록은 '원인에서 제외한 것'으로 옮기세요."
        )
    # 근거 기록 없이 쓴 추정 원인은 어느 설비의 기록인지 검사할 수 없으므로 인용을 요구
    bullets = [line for line in section.splitlines() if re.match(r"\s*[-*]\s", line)]
    if any(not re.search(r"EH-2608-\d{3}|\d{2}/\d{2}\(.\) (?:주간|오후|야간)", b) for b in bullets):
        problems.append("추정 원인마다 근거가 되는 이력번호나 인수인계 날짜·교대를 적으세요.")
    return problems


@after_model(can_jump_to=["model"])
def check_report(state, runtime):
    last = state["messages"][-1]
    # 최종 답변일 때만 검사 (도구를 쓰는 중이거나 다른 미들웨어가 메시지를 붙인 경우는 제외)
    if last.type != "ai" or last.tool_calls:
        return None

    turn = current_turn(state["messages"])
    if sum(1 for m in turn if m.type == "human" and m.name == CHECK_NAME) >= MAX_RETRY:
        return None

    tool_text = "\n".join(m.content for m in turn if m.type == "tool")
    searched = any(m.type == "tool" and m.name == "search_documents" for m in turn)
    problems = find_citation_problems(last.content, tool_text, searched)
    problems += find_cause_problems(last.content, turn, tool_text)
    if not problems:
        return None

    feedback = "[미들웨어 보고서 검사] 아래 문제를 고쳐서 답변을 다시 작성하세요. 검색 결과에 있는 기록만 인용합니다.\n- "
    return {
        "messages": [HumanMessage(content=feedback + "\n- ".join(problems), name=CHECK_NAME)],
        "jump_to": "model",
    }


# ── 미들웨어 3: 문서 검색 횟수 제한 (langchain 기본 제공) ────────
search_limit = ToolCallLimitMiddleware(tool_name="search_documents", run_limit=4)

MIDDLEWARE = [require_data_first, check_report, search_limit]
