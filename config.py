"""
config.py
=========
[역할] 전체 검증 파이프라인(T0~T5)에서 공통으로 쓰는 설정 모음.
  - 입력 데이터 파일명/경로
  - 각 파일의 컬럼명 (실제 파일과 다르면 여기만 고치면 됨)
  - 분석 파라미터 (표본 기간, 실현변동성 창 길이 등)
  - 로그 설정

※ "확인 필요"로 표시된 컬럼명은 공식 문서에서 이름을 확인하지 못한 것.
   00_inspect_data.py 를 먼저 실행해서 실제 컬럼명을 보고 맞춰야 함.
"""
import logging
import sys
from pathlib import Path

# ------------------------------------------------------------------
# 1. 폴더 구조
#    project_root/
#      data/            ← 수집한 원자료
#      data/zq/         ← 연방기금선물 월물별 CSV (ZQZ25.csv 등)
#      outputs_verify/  ← 이 파이프라인이 만드는 중간·결과 파일
# ------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path("/Users/hyowon/Desktop/2.2test/mfed")
ZQ_DIR = DATA_DIR / "zq"
OUT_DIR = ROOT / "outputs_verify"
OUT_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------------
# 2. 입력 파일명 (계획서 2장 데이터 번호와 대응)
# ------------------------------------------------------------------
FILES = {
    "kalshi":     DATA_DIR / "kalshi_fomc_moments.csv",   # #1 Kalshi 분포 모멘트 (R 코드 outputs/ 결과를 합친 파일)
    "fomc":       DATA_DIR / "fomc_dates.csv",            # #2 FOMC 회의일 (정례회의). 2021-07부터 넣어야 함:
                                                          #    pyfedwatch가 관측일 이전 '비FOMC 월'을 찾기 때문 (테스트에서 2021-12 시작 시 2022-01 관측일 실패 확인)
    "dgs2":       DATA_DIR / "DGS2.csv",                  # #3 FRED DGS2
    "move":       DATA_DIR / "MOVE.csv",                  # #4 MOVE 지수 (Yahoo ^MOVE 등)
    "usmpd":      DATA_DIR / "USMPD.xlsx",                # #5 SF Fed USMPD
    # #6 ZQ 월물: data/zq/ZQ{월코드}{YY}.csv  (예: ZQZ25.csv) — 파일 1개 = 월물 1개
    "dfedtarl":   DATA_DIR / "DFEDTARL.csv",              # #7 FRED 목표범위 하단
    "dfedtaru":   DATA_DIR / "DFEDTARU.csv",              # #7 FRED 목표범위 상단
    "cme_fw":     DATA_DIR / "cme_fedwatch_official.csv", # #8 CME FedWatch 공식 확률 (최근 1년)
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

# 3-4. USMPD.xlsx — 시트명·컬럼명 확인 필요 (SF Fed 페이지에 컬럼 목록이 공개돼 있지 않음)
#      SF Fed 페이지에서 확인된 변수명: MP1, MP2, ED1~ED4, UST2Y, UST10Y
#      DKW(2026) Table 5는 'MP Statement Shock', 'MP Press Conference Shock' 두 충격을 사용
USMPD_SHEET = "Monetary Events"    # 시트: README / Statements / Press Conferences / Monetary Events / Minutes
USMPD_COLS = {
    "date": "Date",
    "event_type": None,            # 시트가 이미 이벤트 종류별로 나뉘어 있어서 필요 없음
    "y2": "UST2Y",
}
USMPD_EVENT_FILTER = None
USMPD_SHOCK_COLS = ["MP1"]

# 3-5. CME FedWatch 공식 확률 파일 — 긴(long) 형식 가정. 확인 필요
#      한 행 = (관측일, 회의일, 목표범위 하단, 확률)
CME_FW_COLS = {
    "watch_date": "watch_date",
    "meeting": "meeting_date",
    "range_low": "range_low",      # 목표범위 하단 (%, 예: 3.75)
    "prob": "prob",                # 확률 (0~1 또는 0~100, 자동 판별)
}

# ------------------------------------------------------------------
# 4. 분석 파라미터
# ------------------------------------------------------------------
USE_FEDWATCH = False          # ZQ 월물 데이터 미확보 → FedWatch 통제 제외 (계획서 6장: v1으로 복귀)
                              # True로 바꾸면 01·02단계 실행 + T2·T3·T5에 FedWatch 변수 포함
SAMPLE_START = "2022-01-01"   # 계획서: Kalshi 표본 2022-01 ~ 2026-10
SAMPLE_END = "2026-10-31"
RV_WINDOW = 21                # T2: 향후 21거래일 실현변동성 (A7)
ANNUALIZE = True              # RV를 연율화(×√(252/21))할지. 스케일만 바뀌고 t값은 동일
FEDWATCH_NUM_UPCOMING = 3     # pyfedwatch 계산할 앞으로의 회의 수 (2~3개 회의 앞까지)
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
