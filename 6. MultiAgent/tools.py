"""06 멀티에이전트 노트북에서 사용하는 도구 모음

- 데이터 도구 : 05 최종 프로젝트(시연_구조개선/sql_tools.py)와 같은 도구
- 문서 도구 : 임베딩 없이 동작하도록 단순 키워드 검색으로 바꾼 버전
  (04 실습의 Hybrid 검색기로 바꿔 끼워도 됩니다.)
"""
import csv
import re
import sqlite3
from pathlib import Path

import pandas as pd
from langchain.tools import tool

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "db" / "fab_etch.db"
DOCS_DIR = BASE_DIR / "docs"
MAX_ROWS = 100  # 에이전트에게 돌려줄 최대 행 수
TOP_K = 8  # 문서 검색 한 번에 돌려줄 기록 수


# ── 데이터 도구 ──────────────────────────────────────────────
def _query(sql, params=()):
    """읽기 전용으로 DB에 연결해서 쿼리 결과를 DataFrame으로 돌려줌"""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


@tool
def run_sql(query: str) -> str:
    """가상 Fab ETCH 공정 DB(SQLite)에 SELECT 쿼리를 실행하고 결과를 표 형태의 문자열로 돌려준다.

    테이블: etch_lot (2026-08-01 ~ 2026-08-31, 11,160건, 한 행은 Lot 1건의 ETCH 공정 기록)
    컬럼: timestamp('YYYY-MM-DD HH:MM:SS'), lot_id, product_id, equipment_id(ETCH_01~03),
    chamber_id(CH_A~C), recipe_id, wafer_count, pressure_kpa, temperature_c, rf_power_w,
    gas_flow_sccm, process_time_s, defect_count, defect_rate, yield_rate

    불량률을 집계할 때는 SUM(defect_count) * 1.0 / SUM(wafer_count)로 계산한다.
    조회만 가능하며, 결과는 최대 100행까지만 돌려준다.
    """
    try:
        df = _query(query)
    except Exception as e:
        return f"쿼리 실행 오류: {e}"

    if len(df) > MAX_ROWS:
        return f"(전체 {len(df)}행 중 앞 {MAX_ROWS}행만 표시)\n" + df.head(MAX_ROWS).to_string(index=False)
    return df.to_string(index=False)


SUMMARY_COLUMNS = """
    COUNT(*) AS lot_수,
    ROUND(SUM(defect_count) * 100.0 / SUM(wafer_count), 2) AS 불량률_pct,
    ROUND(AVG(pressure_kpa), 2) AS 평균압력_kpa,
    ROUND(AVG(temperature_c), 1) AS 평균온도_c,
    ROUND(AVG(rf_power_w), 0) AS 평균RF_w,
    ROUND(AVG(gas_flow_sccm), 1) AS 평균가스유량_sccm
"""


@tool
def chamber_summary(start_date: str = "2026-08-01", end_date: str = "2026-08-31") -> str:
    """기간 안에서 설비·챔버별(9개) lot 수, 불량률(%), 평균 압력·온도·RF Power·가스 유량을 비교한다.

    불량률이 오른 원인을 찾을 때 가장 먼저 사용해서, 다른 챔버와 다른 설비·챔버를 찾는다.
    날짜는 'YYYY-MM-DD' 형식이고, 시작일과 종료일을 모두 포함한다.
    """
    sql = f"""
        SELECT equipment_id, chamber_id, {SUMMARY_COLUMNS}
        FROM etch_lot
        WHERE date(timestamp) BETWEEN ? AND ?
        GROUP BY equipment_id, chamber_id
        ORDER BY 불량률_pct DESC
    """
    return _query(sql, (start_date, end_date)).to_string(index=False)


@tool
def daily_trend(equipment_id: str, chamber_id: str) -> str:
    """설비·챔버 하나의 8월 날짜별(31일) 불량률(%)과 평균 압력·온도·RF Power·가스 유량을 보여준다.

    chamber_summary로 찾은 설비·챔버에서 불량률과 공정 변수가 바뀌기 시작한 날짜를 찾을 때 사용한다.
    equipment_id는 ETCH_01~03, chamber_id는 CH_A~C 중 하나다.
    """
    sql = f"""
        SELECT date(timestamp) AS 날짜, {SUMMARY_COLUMNS}
        FROM etch_lot
        WHERE equipment_id = ? AND chamber_id = ?
        GROUP BY 날짜
        ORDER BY 날짜
    """
    return _query(sql, (equipment_id, chamber_id)).to_string(index=False)


# ── 문서 도구 (키워드 검색) ───────────────────────────────────
def load_chunks():
    """설비 이력(csv)은 한 행을, 인수인계 메모(txt)는 교대 1회(■ 단위)를 한 기록으로 나눔"""
    chunks = []
    for path in sorted(DOCS_DIR.glob("*.csv")):
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                chunks.append("[설비 이력] " + " | ".join(f"{k}: {v}" for k, v in row.items() if v))
    for path in sorted(DOCS_DIR.glob("*.txt")):
        for entry in path.read_text(encoding="utf-8").split("■ ")[1:]:
            chunks.append("[교대 인수인계] " + entry.strip())
    return chunks


# 날짜 표기('2026-08-16', '08/16', '8월 16일')를 모두 '0816'으로 맞춤
DATE_PATTERNS = [r"(?:\d{4}-)?(\d{1,2})[-/](\d{1,2})(?!\d)", r"(\d{1,2})월\s*(\d{1,2})일"]


def tokenize(text):
    """검색용 단어 목록. 날짜와 설비 줄임말('03호기', '03B')을 DB와 같은 표기로 바꿔서 함께 넣음"""
    words = []
    for pattern in DATE_PATTERNS:
        words += [f"{int(m):02d}{int(d):02d}" for m, d in re.findall(pattern, text)]
        text = re.sub(pattern, " ", text)
    for num, ch in re.findall(r"(?<![\w])0([1-3])([ABC])(?![\w])", text):
        words += [f"etch_0{num}", f"ch_{ch.lower()}"]
    for num in re.findall(r"0([1-3])호기", text):
        words.append(f"etch_0{num}")
    words += re.findall(r"[0-9a-z가-힣_]+", text.lower())
    return set(words)


CHUNKS = load_chunks()
CHUNK_TOKENS = [tokenize(c) for c in CHUNKS]


@tool
def search_documents(query: str) -> str:
    """ETCH 파트의 2026년 8월 설비 이력과 교대 인수인계 메모에서 검색어와 관련된 기록을 찾는다.

    - 설비 이력: 설비·챔버별 정기PM, 점검, 알람조치, 변경점 기록. 일시는 '2026-08-16 23:48' 형식이다.
    - 교대 인수인계: 교대(주간/오후/야간)마다 남긴 메모. 날짜는 '08/16(일) 야간' 형식이고,
      설비·챔버를 '03호기', '03B'(ETCH_03 CH_B)처럼 줄여 쓴다.

    공정 데이터(압력, 불량률 등의 수치)는 들어 있지 않다.
    검색어에는 설비 ID, 챔버, 날짜, 알람이나 작업 이름 같은 구체적인 단어를 넣는다.
    """
    query_tokens = tokenize(query)
    scored = [(len(query_tokens & tokens), i) for i, tokens in enumerate(CHUNK_TOKENS)]
    scored = sorted((s for s in scored if s[0] > 0), key=lambda s: -s[0])[:TOP_K]
    if not scored:
        return "검색 결과 없음. 설비 ID, 챔버, 날짜 등 다른 검색어로 다시 검색하세요."
    return "\n\n".join(CHUNKS[i] for _, i in scored)
