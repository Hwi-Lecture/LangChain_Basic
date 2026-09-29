from pathlib import Path
from langchain.tools import tool

DOCS_DIR = Path("./docs")


# 아래 함수들을 continue의 도움을 받아 완성하고 에이전트를 실행합니다.

# 1) docs 폴더의 문서를 불러와서 청크로 나누기
def load_chunks():
    pass


# 2) 청크로 검색기(retriever) 만들기
def build_retriever(chunks):
    pass


# 3) 에이전트가 사용할 문서 검색 도구
@tool
def search_documents(query: str) -> str:
    pass
