import os

import streamlit as st
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

# 이 폴더의 .env 파일에서 OPENAI_API_KEY, gpt_4o_mini_BASE_URL, Embedding_BASE_URL을 불러옴
# (doc_tools.py가 임베딩 API를 사용하므로 도구를 불러오기 전에 먼저 실행)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from doc_tools import search_documents
from middleware import CHECK_NAME, MIDDLEWARE
from sql_tools import chamber_summary, daily_trend, run_sql

SYSTEM_PROMPT = """너는 반도체 Fab ETCH 파트의 업무를 돕는 어시스턴트다.
불량률이나 공정 이상의 원인을 물으면 아래 순서대로 도구를 사용한다.
1. 데이터 조회 도구로 설비·챔버별 불량률과 공정 변수를 비교해서, 다른 챔버와 다른 설비·챔버를 찾는다.
2. 1에서 찾은 설비·챔버의 날짜별 추이를 조회해서, 불량률과 공정 변수가 바뀌기 시작한 날짜를 찾는다.
3. 찾은 설비, 챔버와 시작 날짜, 그 전날을 검색어에 넣어서 search_documents로 설비 이력과 인수인계 메모를 검색한다.
4. 문서 기록의 시각·설비·챔버가 데이터에서 찾은 이상과 맞는지 비교해서 연결 근거를 쓴다.
   날짜만 같고 설비나 챔버가 다른 기록은 원인으로 보지 않는다.
5. 문서로 확인되지 않은 내용은 단정하지 말고 '확인 필요'로 쓴다.
6. 관련 기록을 쓸 때는 이력번호(EH-2608-xxx)나 인수인계 날짜·교대(예: 08/16(일) 야간)를 함께 적는다.
보고서 양식: 1) 현상 2) 관련 기록 3) 추정 원인과 근거 4) 원인에서 제외한 것 5) 확인 필요 사항"""


# ── 에이전트 만들기 ──────────────────────────────────────────
# 사이드바 설정 조합마다 한 번만 만들어서 재사용
@st.cache_resource
def get_agent(use_fixed_tools, use_middleware):
    model = ChatOpenAI(
        model="gpt-4o-mini",
        base_url=os.getenv("gpt_4o_mini_BASE_URL"),
        temperature=0,
    )
    tools = [run_sql, search_documents]
    if use_fixed_tools:
        tools = [chamber_summary, daily_trend, run_sql, search_documents]
    middleware = MIDDLEWARE if use_middleware else []
    return create_agent(model, tools=tools, system_prompt=SYSTEM_PROMPT, middleware=middleware)


# ── 에이전트 실행 결과에서 도구 호출과 미들웨어 개입 과정 뽑아내기 ──
def extract_steps(messages):
    """도구 호출과 미들웨어의 보고서 검사를 일어난 순서대로 모음"""
    results = {m.tool_call_id: m.content for m in messages if m.type == "tool"}
    steps = []
    for i, m in enumerate(messages):
        if m.type == "ai":
            for call in m.tool_calls:
                steps.append({
                    "name": call["name"],
                    "args": call["args"],
                    "result": results.get(call["id"], ""),
                })
        elif m.type == "human" and m.name == CHECK_NAME:
            # 보고서 검사에 걸린 직전 답변(수정 전)과 미들웨어가 보낸 지적 사항
            steps.append({"name": CHECK_NAME, "draft": messages[i - 1].content, "result": m.content})
    return steps


TOOL_LABELS = {
    "run_sql": "🗄️ SQL 조회",
    "chamber_summary": "📊 챔버별 비교",
    "daily_trend": "📈 날짜별 추이",
    "search_documents": "📄 문서 검색",
}


def show_steps(steps):
    """도구 호출과 미들웨어 개입을 순서대로 번호를 붙여 접었다 펼 수 있는 상자로 보여줌"""
    for i, step in enumerate(steps, start=1):
        if step["name"] == CHECK_NAME:
            with st.expander(f"🛡️ {i}. 미들웨어 보고서 검사 → 다시 작성"):
                st.text(step["result"])
                st.caption("수정 전 답변")
                st.markdown(step["draft"])
            continue

        icon, label = TOOL_LABELS.get(step["name"], f"🔧 {step['name']}").split(" ", 1)
        # require_data_first가 막은 호출, ToolCallLimitMiddleware가 막은 호출
        if step["result"].startswith(("[미들웨어 차단]", "Tool call limit exceeded")):
            icon, label = "🛡️", f"{label} 차단"
        args = step["args"]
        detail = args.get("query", ", ".join(str(v) for v in args.values()))
        with st.expander(f"{icon} {i}. {label} : {detail}"[:120]):
            if step["name"] == "run_sql":
                st.code(args.get("query", ""), language="sql")
            st.text(step["result"])


# ── 화면 구성 ────────────────────────────────────────────────
st.title("ETCH 파트 업무 에이전트 (구조 개선 시연)")
st.caption("8월 ETCH 공정 데이터와 설비 이력, 교대 인수인계 메모를 함께 찾아봅니다.")

with st.sidebar:
    st.header("구조 개선 설정")
    use_fixed_tools = st.toggle("① 정해진 쿼리 도구", help="chamber_summary, daily_trend 도구를 추가합니다.")
    use_middleware = st.toggle("② 미들웨어", help="검색 순서 강제, 보고서 검사(인용·원인 설비), 검색 횟수 제한을 적용합니다.")
    if st.button("대화 지우기"):
        st.session_state.history = []

# 대화 기록: [{"role": "user"/"assistant", "content": 답변, "steps": [...]}]
if "history" not in st.session_state:
    st.session_state.history = []

# 지금까지의 대화 다시 그리기
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        if msg.get("setting"):
            st.caption(msg["setting"])
        st.markdown(msg["content"])
        show_steps(msg.get("steps", []))

# 새 질문 입력
if question := st.chat_input("질문을 입력하세요"):
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.history.append({"role": "user", "content": question})

    # 이전 대화도 함께 넘겨서 앞 질문의 맥락을 이어가도록 함
    input_messages = [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.history
    ]
    setting = f"설정 : 정해진 쿼리 도구 {'ON' if use_fixed_tools else 'OFF'} / 미들웨어 {'ON' if use_middleware else 'OFF'}"

    with st.chat_message("assistant"):
        st.caption(setting)
        with st.spinner("데이터와 문서를 찾는 중..."):
            agent = get_agent(use_fixed_tools, use_middleware)
            response = agent.invoke({"messages": input_messages})

        # 이번 질문에서 새로 생긴 메시지만 골라서 도구 호출 과정 추출
        new_messages = response["messages"][len(input_messages):]
        answer = response["messages"][-1].content
        steps = extract_steps(new_messages)

        st.markdown(answer)
        show_steps(steps)

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "steps": steps, "setting": setting}
    )
