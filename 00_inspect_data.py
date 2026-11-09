"""
00_inspect_data.py
==================
[역할] 분석 전 사전 점검. 각 입력 파일이 있는지, 실제 컬럼명이 뭔지 출력.
       config.py 의 '확인 필요' 컬럼명을 실제 이름으로 맞추는 데 사용.
       (분석은 하지 않음)
"""
import pandas as pd

import config as C

log = C.get_logger("00_inspect")

# ------------------------------------------------------------------
# [블록 1] 파일 존재 여부 확인
# ------------------------------------------------------------------
log.info("=== STEP 00: 입력 파일 점검 시작 ===")
for key, path in C.FILES.items():
    status = "OK" if path.exists() else "없음"
    log.info(f"{key:<10} {status:<4} {path.name}")

zq_files = sorted(C.ZQ_DIR.glob("ZQ*.csv")) if C.ZQ_DIR.exists() else []
log.info(f"ZQ 월물 파일: {len(zq_files)}개 " + (f"({zq_files[0].stem} ~ {zq_files[-1].stem})" if zq_files else ""))

# ------------------------------------------------------------------
# [블록 2] CSV 파일 컬럼명·앞부분 출력
# ------------------------------------------------------------------
for key, path in C.FILES.items():
    if not path.exists() or path.suffix != ".csv":
        continue
    df = pd.read_csv(path, nrows=3)
    log.info(f"[{key}] 컬럼: {list(df.columns)}")
    log.info(f"[{key}] 첫 행: {df.iloc[0].to_dict()}")

if zq_files:
    df = pd.read_csv(zq_files[0], nrows=3)
    log.info(f"[zq 예시 {zq_files[0].name}] 컬럼: {list(df.columns)}  ← 'Date','Close' 필요")

# ------------------------------------------------------------------
# [블록 3] USMPD.xlsx 시트명·컬럼명 출력 (USMPD_SHEET, USMPD_COLS 지정용)
# ------------------------------------------------------------------
if C.FILES["usmpd"].exists():
    xl = pd.ExcelFile(C.FILES["usmpd"])
    log.info(f"[USMPD] 시트 목록: {xl.sheet_names}")
    for sh in xl.sheet_names:
        df = xl.parse(sh, nrows=3)
        log.info(f"[USMPD:{sh}] 컬럼({len(df.columns)}개): {list(df.columns)}")

log.info("=== STEP 00 완료: 위 컬럼명을 보고 config.py 수정 ===")
