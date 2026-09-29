import sqlite3
import pandas as pd
from langchain.tools import tool

DB_PATH = "./db/fab_etch.db"
MAX_ROWS = 100  # 에이전트에게 돌려줄 최대 행 수

# 아래 함수를 continue의 도움을 받아 완성하고 에이전트를 실행합니다.
@tool
def run_sql(query: str) -> str:
    pass
