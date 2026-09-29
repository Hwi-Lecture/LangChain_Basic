import sqlite3
import pandas as pd
from langchain.tools import tool

DB_PATH = "./db/fab_etch.db"
MAX_ROWS = 100  # 에이전트에게 돌려줄 최대 행 수


def _query(sql, params=()):
    """읽기 전용으로 DB에 연결해서 쿼리 결과를 DataFrame으로 돌려줌"""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


# ── 자유 SQL 도구 (03 실습과 같은 방식) ─────────────────────────
@tool
def run_sql(query: str) -> str:
    """가상 Fab ETCH 공정 DB(SQLite)에 SELECT 쿼리를 실행하고 결과를 표 형태의 문자열로 돌려준다.

    테이블: etch_lot
    - 한 행은 웨이퍼 50장으로 이뤄진 Lot 1건을 ETCH 공정에서 한 번 처리한 기록이다.
    - 기간: 2026-08-01 ~ 2026-08-31, 행 수: 11,160건

    컬럼:
    - timestamp (TEXT): 공정 완료 시각, 'YYYY-MM-DD HH:MM:SS'
    - lot_id (TEXT): Lot 식별자
    - product_id (TEXT): 제품군 코드 (PROD_A12, PROD_B07, PROD_C03, PROD_D09)
    - equipment_id (TEXT): 설비 ID (ETCH_01, ETCH_02, ETCH_03)
    - chamber_id (TEXT): 설비 내 챔버 ID (CH_A, CH_B, CH_C)
    - recipe_id (TEXT): 공정 레시피 ID (RCP_A12, RCP_B07, RCP_C03, RCP_D09)
    - wafer_count (INTEGER): Lot 내 처리 웨이퍼 수(개)
    - pressure_kpa (REAL): 압력 센서 기록값(kPa)
    - temperature_c (REAL): 공정 온도 기록값(°C)
    - rf_power_w (REAL): RF Power 기록값(W)
    - gas_flow_sccm (REAL): 가스 유량 기록값(sccm)
    - process_time_s (REAL): 공정 시간(초)
    - defect_count (INTEGER): 검사에서 집계된 불량 웨이퍼 수(개)
    - defect_rate (REAL): defect_count / wafer_count, 비율(0~1)
    - yield_rate (REAL): 1 - defect_rate, 비율(0~1)

    불량률을 집계할 때는 SUM(defect_count) * 1.0 / SUM(wafer_count)로 계산한다.
    (SQLite는 정수끼리 나누면 소수점을 버리므로 * 1.0을 꼭 붙인다.)
    조회만 가능하며, 결과는 최대 100행까지만 돌려준다.
    """
    try:
        df = _query(query)
    except Exception as e:
        return f"쿼리 실행 오류: {e}"

    if len(df) > MAX_ROWS:
        return f"(전체 {len(df)}행 중 앞 {MAX_ROWS}행만 표시)\n" + df.head(MAX_ROWS).to_string(index=False)
    return df.to_string(index=False)


# ── 정해진 쿼리 도구 ─────────────────────────────────────────
# 자주 쓰는 분석은 쿼리를 미리 정해 두고, 에이전트는 값(기간, 설비, 챔버)만 넣게 함
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
