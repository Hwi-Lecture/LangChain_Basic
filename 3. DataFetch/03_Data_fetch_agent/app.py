import os

import streamlit as st
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from tools import run_sql

# 이 폴더의 .env 파일에서 OPENAI_API_KEY, gpt_4o_mini_BASE_URL을 불러옴
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SYSTEM_PROMPT = (
    "너는 반도체 Fab ETCH 공정 데이터를 분석하는 어시스턴트다. "
    "데이터에 대한 질문은 반드시 run_sql 도구로 DB를 조회한 결과를 근거로 답해야 한다. "
    "조회 결과로 답할 수 없는 질문에는 모른다고 답해라."
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
    return create_agent(model, tools=[run_sql], system_prompt=SYSTEM_PROMPT)


# ── 에이전트 실행 결과에서 SQL 쿼리와 조회 결과 뽑아내기 ──────
def extract_sql_steps(messages):
    """에이전트가 run_sql을 호출할 때마다 (쿼리문, 조회 결과)를 순서대로 모음"""
    results = {m.tool_call_id: m.content for m in messages if m.type == "tool"}
    steps = []
    for m in messages:
        if m.type == "ai":
            for call in m.tool_calls:
                if call["name"] == "run_sql":
                    steps.append({
                        "query": call["args"].get("query", ""),
                        "result": results.get(call["id"], ""),
                    })
    return steps


def show_sql_steps(steps):
    """SQL 쿼리문과 조회 결과를 접었다 펼 수 있는 상자로 보여줌"""
    for i, step in enumerate(steps, start=1):
        with st.expander(f"🔍 SQL 조회 {i}"):
            st.code(step["query"], language="sql")
            st.text(step["result"])


# ── 화면 구성 ────────────────────────────────────────────────
st.title("ETCH 공정 데이터 분석 챗봇")
st.caption("2026년 8월 ETCH 공정 Lot 데이터에 대해 질문해 보세요.")

# 대화 기록: [{"role": "user"/"assistant", "content": 답변, "sql_steps": [...]}]
if "history" not in st.session_state:
    st.session_state.history = []

# 지금까지의 대화 다시 그리기
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        show_sql_steps(msg.get("sql_steps", []))

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
        with st.spinner("데이터를 조회하는 중..."):
            response = get_agent().invoke({"messages": input_messages})

        # 이번 질문에서 새로 생긴 메시지만 골라서 SQL 조회 과정 추출
        new_messages = response["messages"][len(input_messages):]
        answer = response["messages"][-1].content
        sql_steps = extract_sql_steps(new_messages)

        st.markdown(answer)
        show_sql_steps(sql_steps)

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "sql_steps": sql_steps}
    )
