import sqlite3
import pandas as pd
from langchain.tools import tool

DB_PATH = "../db/fab_etch.db"
MAX_ROWS = 100  # 에이전트에게 돌려줄 최대 행 수

@tool
def run_sql(query: str) -> str:
    """가상 Fab ETCH 공정 DB(fab_etch.db, SQLite)에 SQL 쿼리를 실행하고 결과를 표 형태의 문자열로 돌려줍니다.
    조회(SELECT)만 가능하며, 결과는 최대 100행까지만 반환되므로 많은 데이터는 GROUP BY 등으로 집계해서 조회하세요.

    테이블: etch_lot
    - 한 행 = Lot 1건의 ETCH 공정 결과
    - 기간: 2026-08-01 ~ 2026-08-31, 총 11,160행

    컬럼 (이름 | 설명 | 단위/형식):
    - timestamp      | 공정 완료 시각               | 문자열 'YYYY-MM-DD HH:MM:SS' (날짜 비교는 date(timestamp) 등 SQLite 함수 사용)
    - lot_id         | Lot 식별자                   | 문자열
    - product_id     | 제품군 코드                  | PROD_A12, PROD_B07, PROD_C03, PROD_D09
    - equipment_id   | 설비 ID                      | ETCH_01, ETCH_02, ETCH_03
    - chamber_id     | 설비 내 챔버 ID              | CH_A, CH_B, CH_C
    - recipe_id      | 공정 Recipe ID               | RCP_A12, RCP_B07, RCP_C03, RCP_D09
    - wafer_count    | Lot 내 처리 Wafer 수         | 개
    - pressure_kpa   | 압력 센서 기록값             | kPa
    - temperature_c  | 공정 온도 기록값             | °C
    - rf_power_w     | RF Power 기록값              | W
    - gas_flow_sccm  | 가스 유량 기록값             | sccm
    - process_time_s | 공정 시간                    | 초
    - defect_count   | 검사에서 집계된 불량 Wafer 수 | 개
    - defect_rate    | defect_count / wafer_count   | 비율(0~1)
    - yield_rate     | 1 - defect_rate              | 비율(0~1)
    """
    # 읽기 전용 모드로 연결: 데이터를 수정하거나 삭제하는 쿼리는 실행되지 않습니다.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        df = pd.read_sql(query, conn)
    except Exception as e:
        # 에러를 에이전트에게 돌려주면, 에이전트가 보고 쿼리를 고쳐서 다시 시도할 수 있습니다.
        return f"쿼리 실행 오류: {e}"
    finally:
        conn.close()

    # 결과가 너무 많으면 앞부분만 돌려줍니다.
    if len(df) > MAX_ROWS:
        return f"결과가 {len(df)}행이라 앞의 {MAX_ROWS}행만 보여줍니다.\n" + df.head(MAX_ROWS).to_string(index=False)
    return df.to_string(index=False)
