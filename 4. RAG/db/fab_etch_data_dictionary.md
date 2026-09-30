# 가상 Fab ETCH 데이터 — 데이터 사전

## 데이터 개요
- 파일: `fab_etch.db`
- 관측 단위: Lot 1건의 ETCH 공정 결과
- 기간: 2026-08-01 ~ 2026-08-31
- 행 수: 11,160건

## 용어설명
* 제품(product) : 반도체 제품의 종류
* 웨이퍼(Wafer) : 반도체 칩을 여러 개 만들기 위해 사용하는 얇고 둥근 판. 제품을 만드는 재료판
* 로트(Lot) : 함께 관리하고 공정을 진행하는 웨이퍼 묶음. csv의 한 행은 웨이퍼 50장으로 이뤄진 Lot을 한 번 처리한 기록.
* 설비(Equipment) : 공정 작업을 하는 큰 기계.
* 챔버(Chamber) : 설비 안에서 실제로 웨이퍼를 넣고 작업하는 공간. 큰 설비 안에 여러 작업 공간이 있다고 생각하면 된다.
* 레시피(Recipe) : 웨이퍼를 어떻게 처리할지 정해둔 작업 설정 묶음

## 컬럼
| 컬럼 | 설명 | 단위/형식 |
|---|---|---|
| `timestamp` | 공정 완료 시각 | YYYY-MM-DD HH:MM:SS |
| `lot_id` | Lot 식별자 | 문자열 |
| `product_id` | 제품군 코드 | 범주형 |
| `equipment_id` | 설비 ID | ETCH_01~03 |
| `chamber_id` | 설비 내 챔버 ID | CH_A~C |
| `recipe_id` | 공정 Recipe ID | 4종 |
| `wafer_count` | Lot 내 처리 Wafer 수 | 개 |
| `pressure_kpa` | 압력 센서 기록값 | kPa |
| `temperature_c` | 공정 온도 기록값 | °C |
| `rf_power_w` | RF Power 기록값 | W |
| `gas_flow_sccm` | 가스 유량 기록값 | sccm |
| `process_time_s` | 공정 시간 | 초 |
| `defect_count` | 검사에서 집계된 불량 Wafer 수 | 개 |
| `defect_rate` | `defect_count / wafer_count` | 비율(0~1) |
| `yield_rate` | `1 - defect_rate` | 비율(0~1) |