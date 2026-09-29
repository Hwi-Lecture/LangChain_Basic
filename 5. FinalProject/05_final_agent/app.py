import os

import streamlit as st
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

# 이 폴더의 .env 파일에서 OPENAI_API_KEY, gpt_4o_mini_BASE_URL, Embedding_BASE_URL을 불러옴
# (doc_tools.py가 임베딩 API를 사용하므로 도구를 불러오기 전에 먼저 실행)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── 부품 가져오기 ────────────────────────────────────────────
# 3단계에서 sql_tools.py, doc_tools.py의 도구를 불러오도록 작성합니다.


# 4단계에서 작성합니다.
SYSTEM_PROMPT = (
    "너는 반도체 Fab ETCH 파트의 업무를 돕는 어시스턴트다."
)


# ── 에이전트 만들기 ──────────────────────────────────────────
# 화면이 새로고침될 때마다 다시 만들지 않도록 한 번만 생성해서 재사용
@st.cache_resource
def get_agent():
    model = ChatOpenAI(
        model="gpt-4o-mini",
        base_url=os.getenv("gpt_4o_mini_BASE_URL"),
        temperature=0,
    )
    # 3단계에서 에이전트가 사용할 도구를 tools에 넣습니다.
    return create_agent(model, tools=[], system_prompt=SYSTEM_PROMPT)


# ── 에이전트 실행 결과에서 도구 호출 과정 뽑아내기 ────────────
def extract_tool_steps(messages):
    """에이전트가 도구를 호출할 때마다 (도구 이름, 입력, 결과)를 호출한 순서대로 모음"""
    results = {m.tool_call_id: m.content for m in messages if m.type == "tool"}
    steps = []
    for m in messages:
        if m.type == "ai":
            for call in m.tool_calls:
                steps.append({
                    "name": call["name"],
                    "query": call["args"].get("query", str(call["args"])),
                    "result": results.get(call["id"], ""),
                })
    return steps


def show_tool_steps(steps):
    """도구 호출 과정을 순서대로 번호를 붙여 접었다 펼 수 있는 상자로 보여줌"""
    for i, step in enumerate(steps, start=1):
        if step["name"] == "run_sql":
            with st.expander(f"🗄️ {i}. SQL 조회"):
                st.code(step["query"], language="sql")
                st.text(step["result"])
        elif step["name"] == "search_documents":
            with st.expander(f"📄 {i}. 문서 검색 : {step['query']}"):
                st.text(step["result"])
        else:
            with st.expander(f"🔧 {i}. {step['name']}"):
                st.text(step["query"])
                st.text(step["result"])


# ── 화면 구성 ────────────────────────────────────────────────
st.title("ETCH 파트 업무 에이전트")
st.caption("8월 ETCH 공정 데이터와 설비 이력, 교대 인수인계 메모를 함께 찾아봅니다.")

# 대화 기록: [{"role": "user"/"assistant", "content": 답변, "tool_steps": [...]}]
if "history" not in st.session_state:
    st.session_state.history = []

# 지금까지의 대화 다시 그리기
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        show_tool_steps(msg.get("tool_steps", []))

# 새 질문 입력
if question := st.chat_input("질문을 입력하세요"):
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.history.append({"role": "user", "content": question})

    # 이전 대화도 함께 넘겨서 앞 질문의 맥락을 이어가도록 함
    input_messages = [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.history
    ]

    with st.chat_message("assistant"):
        with st.spinner("데이터와 문서를 찾는 중..."):
            response = get_agent().invoke({"messages": input_messages})

        # 이번 질문에서 새로 생긴 메시지만 골라서 도구 호출 과정 추출
        new_messages = response["messages"][len(input_messages):]
        answer = response["messages"][-1].content
        tool_steps = extract_tool_steps(new_messages)

        st.markdown(answer)
        show_tool_steps(tool_steps)

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "tool_steps": tool_steps}
    )
