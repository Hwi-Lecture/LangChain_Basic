import sqlite3
import pandas as pd
from langchain.tools import tool

DB_PATH = "./db/fab_etch.db"

# 아래 함수를 continue의 도움을 받아 완성하고 에이전트를 실행합니다.
@tool
def run_sql(query: str) -> str:
    pass
