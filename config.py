"""
config.py
=========
[역할] 전체 검증 파이프라인(T1·T5)에서 공통으로 쓰는 설정 모음.
  - 입력 데이터 파일명/경로
  - 각 파일의 컬럼명 (실제 파일과 다르면 여기만 고치면 됨)
  - 분석 파라미터 (표본 기간, Granger 시차 등)
  - 로그 설정

※ "확인 필요"로 표시된 컬럼명은 공식 문서에서 이름을 확인하지 못한 것.
   04_check_inputs.py 를 먼저 실행해서 실제 컬럼명을 보고 맞춰야 함.
"""
import logging
import os
import sys
from pathlib import Path

# ------------------------------------------------------------------
# 1. 폴더 구조
#    project_root/
#      data/            ← 수집한 원자료
#      outputs_verify/  ← 이 파이프라인이 만드는 중간·결과 파일
# ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FOMC_DATA_DIR", ROOT))   # 기본: 스크립트와 같은 폴더. 다른 곳이면 FOMC_DATA_DIR로 지정
# Kalshi 일별 가격 기준 시각 (09_build_kalshi_daily_et.py 참고)
#   ""   : 기존 R 출력 daily_distributions_fed_levels.csv 사용 (UTC 기준)
#   "utc": 09가 만든 UTC 기준 파일,  "et16": 09가 만든 동부시간 오후 4시 기준 파일
#   실행 예: KALSHI_TIMING=et16 python3 run_all.py  → 결과는 outputs_verify_et16/
KALSHI_TIMING = os.environ.get("KALSHI_TIMING", "")
KALSHI_DIST_FILE = DATA_DIR / (f"daily_distributions_fed_levels_{KALSHI_TIMING}.csv" if KALSHI_TIMING
                               else "daily_distributions_fed_levels.csv")
OUT_DIR = ROOT / ("outputs_verify" + (f"_{KALSHI_TIMING}" if KALSHI_TIMING else ""))
OUT_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------------
# 2. 입력 파일명 (계획서 2장 데이터 번호와 대응)
# ------------------------------------------------------------------
FILES = {
    "kalshi":     OUT_DIR / "kalshi_fomc_moments.csv",    # #1 Kalshi 분포 모멘트 (03이 KALSHI_DIST_FILE로 생성)
    "fomc":       DATA_DIR / "fomc_dates.csv",            # #2 FOMC 회의일 (정례회의). 2021-07부터 넣어야 함:
                                                          #    pyfedwatch가 관측일 이전 '비FOMC 월'을 찾기 때문 (테스트에서 2021-12 시작 시 2022-01 관측일 실패 확인)
    "dgs2":       DATA_DIR / "DGS2.csv",                  # #3 FRED DGS2
    "move":       DATA_DIR / "MOVE.csv",                  # #4 MOVE 지수 (Yahoo ^MOVE 등)
    "vix":        DATA_DIR / "VIXCLS.csv",                # #9 (선택) FRED VIXCLS
}

# ------------------------------------------------------------------
# 3. 컬럼명 매핑 (실제 파일 컬럼명 → 코드 내부 이름)
# ------------------------------------------------------------------
# 3-1. Kalshi 모멘트 파일 — R 코드 출력 형식을 몰라서 가정한 이름. 확인 필요.
#      한 행 = (관측일, 대상 FOMC 회의) 조합
KALSHI_COLS = {
    "date": "date",              # 관측일
    "meeting": "meeting_date",   # 계약이 가리키는 FOMC 회의일
    "mean": "mean",              # 평균 (금리 %, 선택)
    "std_bp": "std_bp",          # 표준편차 (bp)
    "entropy": "entropy",        # 엔트로피
    "skew": "skewness",          # 왜도
    "kurt": "kurtosis",          # 첨도
}

# 3-2. FOMC 일정 파일
FOMC_DATE_COL = "date"

# 3-3. MOVE 파일 (Yahoo Finance 다운로드 형식 가정)
MOVE_COLS = {"date": "Date", "value": "Close"}

# ------------------------------------------------------------------
# 4. 분석 파라미터
# ------------------------------------------------------------------
SAMPLE_START = "2022-01-01"   # 계획서: Kalshi 표본 2022-01 ~ 2026-10
SAMPLE_END = "2026-10-31"
MAIN_HORIZON = 2              # A13: 주 분석은 2번째 회의
AUX_HORIZON = 1               # 보조 분석: 가장 가까운 회의
GRANGER_MAXLAG = 10           # T5: 정보기준 탐색 최대 시차
GRANGER_IC = "aic"            # T5: 시차 선택 정보기준
ALPHA = 0.05                  # 유의수준

# ------------------------------------------------------------------
# 5. 로그 설정 — 모든 스크립트가 같은 형식으로 콘솔 + 파일에 기록
# ------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:            # 중복 핸들러 방지
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s | %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(OUT_DIR / "pipeline.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger
