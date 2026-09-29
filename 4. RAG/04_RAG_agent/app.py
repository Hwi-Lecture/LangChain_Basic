import os

import streamlit as st
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

# 이 폴더의 .env 파일에서 OPENAI_API_KEY, gpt_4o_mini_BASE_URL, Embedding_BASE_URL을 불러옴
# (tools.py가 임베딩 API를 사용하므로 tools를 불러오기 전에 먼저 실행)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from tools import search_documents

SYSTEM_PROMPT = (
    "너는 반도체 공정과 산업 정책 자료를 안내하는 사내 어시스턴트다."
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
    return create_agent(model, tools=[search_documents], system_prompt=SYSTEM_PROMPT)


# ── 에이전트 실행 결과에서 검색어와 검색 결과 뽑아내기 ─────────
def extract_search_steps(messages):
    """에이전트가 search_documents를 호출할 때마다 (검색어, 검색 결과)를 순서대로 모음"""
    results = {m.tool_call_id: m.content for m in messages if m.type == "tool"}
    steps = []
    for m in messages:
        if m.type == "ai":
            for call in m.tool_calls:
                if call["name"] == "search_documents":
                    steps.append({
                        "query": call["args"].get("query", ""),
                        "result": results.get(call["id"], ""),
                    })
    return steps


def show_search_steps(steps):
    """검색어와 검색된 청크를 접었다 펼 수 있는 상자로 보여줌"""
    for i, step in enumerate(steps, start=1):
        with st.expander(f"🔍 문서 검색 {i} : {step['query']}"):
            st.text(step["result"])


# ── 화면 구성 ────────────────────────────────────────────────
st.title("반도체 공정 자료 검색 챗봇")
st.caption("반도체 8대 공정 설명 자료와 첨단패키징 보도자료에 대해 질문해 보세요.")

# 대화 기록: [{"role": "user"/"assistant", "content": 답변, "search_steps": [...]}]
if "history" not in st.session_state:
    st.session_state.history = []

# 지금까지의 대화 다시 그리기
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        show_search_steps(msg.get("search_steps", []))

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
        with st.spinner("문서를 검색하는 중..."):
            response = get_agent().invoke({"messages": input_messages})

        # 이번 질문에서 새로 생긴 메시지만 골라서 검색 과정 추출
        new_messages = response["messages"][len(input_messages):]
        answer = response["messages"][-1].content
        search_steps = extract_search_steps(new_messages)

        st.markdown(answer)
        show_search_steps(search_steps)

    st.session_state.history.append(
        {"role": "assistant", "content": answer, "search_steps": search_steps}
    )
