import csv
import os
import re
from pathlib import Path

from kiwipiepy import Kiwi
from langchain.tools import tool
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

DOCS_DIR = Path("./docs")
TOP_K = 8  # 한 번 검색할 때 가져올 청크 수


# 1) docs 폴더의 문서를 불러와서 청크로 나누기
def load_chunks():
    """설비 이력(csv)은 한 행을 한 청크로, 인수인계 메모(txt)는 교대 1회(■ 단위)를 한 청크로 나눔"""
    chunks = []

    for path in sorted(DOCS_DIR.glob("*.csv")):
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                # 행만 떼어 놓아도 뜻을 알 수 있도록 컬럼 이름을 함께 붙임
                text = "[설비 이력] " + " | ".join(f"{k}: {v}" for k, v in row.items() if v)
                chunks.append(Document(page_content=text, metadata={"source": path.name}))

    for path in sorted(DOCS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        # 맨 앞의 문서 설명 부분은 건너뛰고 ■ 로 시작하는 교대 기록만 사용
        for entry in text.split("■ ")[1:]:
            chunks.append(Document(
                page_content="[교대 인수인계] " + entry.strip(),
                metadata={"source": path.name},
            ))

    return chunks


# 2) 청크로 검색기(retriever) 만들기
kiwi = Kiwi()

# 문서와 검색어마다 날짜 형식이 달라서('2026-08-16', '08/16', '8월 16일') 모두 '0816'으로 맞춤
DATE_PATTERNS = [r"(?:\d{4}-)?(\d{1,2})[-/](\d{1,2})(?!\d)", r"(\d{1,2})월\s*(\d{1,2})일"]


def tokenize(text):
    """날짜는 월일 4자리로 바꾸고, 나머지는 명사, 영어, 숫자만 남기는 한국어 토큰화 (BM25용)"""
    dates = []
    for pattern in DATE_PATTERNS:
        dates += [f"{int(m):02d}{int(d):02d}" for m, d in re.findall(pattern, text)]
        text = re.sub(pattern, " ", text)
    words = [t.form for t in kiwi.tokenize(text) if t.tag.startswith(("NN", "SL", "SN"))]
    return words + dates


def build_retriever(chunks):
    """BM25(키워드)와 Dense(의미) 검색을 반씩 섞은 Hybrid 검색기"""
    bm25 = BM25Retriever.from_documents(chunks, preprocess_func=tokenize, k=TOP_K)
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        base_url=os.getenv("Embedding_BASE_URL"),
    )
    dense = FAISS.from_documents(chunks, embeddings).as_retriever(search_kwargs={"k": TOP_K})
    return EnsembleRetriever(retrievers=[bm25, dense], weights=[0.5, 0.5])


# 앱이 시작될 때 한 번만 만들어 둠
retriever = build_retriever(load_chunks())


# 3) 에이전트가 사용할 문서 검색 도구
@tool
def search_documents(query: str) -> str:
    """ETCH 파트의 2026년 8월 설비 이력과 교대 인수인계 메모에서 검색어와 관련된 기록을 찾는다.

    - 설비 이력(ETCH_설비이력_202608.csv): 설비·챔버별 정기PM, 점검, 알람조치, 변경점(레시피 변경 등) 기록.
      일시는 '2026-08-16 23:48' 형식이다.
    - 교대 인수인계(ETCH_교대인수인계_202608.txt): 교대(주간/오후/야간)마다 엔지니어가 남긴 메모.
      날짜는 '08/16(일) 야간' 형식이고, 설비·챔버를 '03호기', '03B'(ETCH_03 CH_B)처럼 줄여 쓴다.

    공정 데이터(압력, 불량률 등의 수치)는 들어 있지 않다.
    검색어에는 설비 ID, 챔버, 날짜, 알람이나 작업 이름 같은 구체적인 단어를 넣는다.
    """
    docs = retriever.invoke(query)[:TOP_K]
    return "\n\n".join(f"[{d.metadata['source']}]\n{d.page_content}" for d in docs)
