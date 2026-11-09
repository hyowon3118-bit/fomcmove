"""
03_build_kalshi_moments.py
==========================
[역할] 연준 R 코드 출력(daily_distributions_fed_levels.csv, 확률분포)을
       분석용 모멘트 파일(kalshi_fomc_moments.csv)로 변환.
  입력: data/daily_distributions_fed_levels.csv, data/fomc_dates.csv
  출력: data/kalshi_fomc_moments.csv
        (한 행 = 관측일 × 대상 회의, 컬럼: date, meeting_date, mean, std_bp, entropy, skewness, kurtosis)

입력 파일 구조 (실제 파일에서 확인):
  - contract_preamble: 회의별 계약 이름 (FED-22MAR, KXFED-26JAN …)
  - strike: 금리 수준(%), 0.25 간격
  - probability: 확률(%) — (계약, 관측일)마다 합이 100
  - expiry_date: 최근 계약은 회의일이 아닌 데이터 마지막 날이 찍혀 있음 → 회의일로 쓰지 않음
"""
import numpy as np
import pandas as pd

import config as C
import utils as U

log = C.get_logger("03_kalshi")
log.info("=== STEP 03: Kalshi 확률분포 → 모멘트 변환 시작 ===")

SRC = C.KALSHI_DIST_FILE                 # config.KALSHI_TIMING에 따라 기존 R 출력 / utc / et16
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# ------------------------------------------------------------------
# [블록 1] 원자료 읽기 + 확률(%) → 0~1
# ------------------------------------------------------------------
raw = pd.read_csv(SRC, parse_dates=["date"])
raw["p"] = raw["probability"] / 100
log.info(f"입력 {SRC.name}")
log.info(f"원자료 {len(raw):,}행, 계약 {raw['contract_preamble'].nunique()}개, "
         f"{raw['date'].min().date()} ~ {raw['date'].max().date()}")

# ------------------------------------------------------------------
# [블록 2] 계약 이름(예: KXFED-26JAN) → 해당 연월의 FOMC 회의일 매칭
#   expiry_date는 회의일과 다른 경우가 있어서 FOMC 일정 파일 기준으로 매칭
# ------------------------------------------------------------------
fomc = U.load_fomc_dates()
fomc_ym = {(d.year, d.month): d for d in fomc}

def contract_to_meeting(name):
    code = name.split("-")[1]                      # '26JAN'
    year, mon = 2000 + int(code[:2]), MONTHS[code[2:]]
    return fomc_ym.get((year, mon), pd.NaT)

cmap = {c: contract_to_meeting(c) for c in raw["contract_preamble"].unique()}
unmatched = [c for c, m in cmap.items() if pd.isna(m)]
if unmatched:
    log.warning(f"FOMC 일정에 없는 계약 {len(unmatched)}개 → 제외: {unmatched}")
raw["meeting_date"] = raw["contract_preamble"].map(cmap)
raw = raw.dropna(subset=["meeting_date"])
raw = raw[raw["date"] <= raw["meeting_date"]]     # 회의 이후 관측은 제외
log.info(f"회의 매칭 후 {len(raw):,}행, 회의 {raw['meeting_date'].nunique()}개")

# ------------------------------------------------------------------
# [블록 3] (관측일, 회의)마다 분포 모멘트 계산
#   x = strike(%), p = 확률
#   평균, 표준편차(bp), 왜도, 첨도(정규분포=3, 초과첨도 아님), 엔트로피(-Σ p ln p)
#   ※ strike가 범위 하단인지 상단인지에 따라 평균만 평행이동, 나머지는 영향 없음
# ------------------------------------------------------------------
def moments(g):
    x = g["strike"].to_numpy(float)
    p = g["p"].to_numpy(float)
    p = p / p.sum()
    mu = (p * x).sum()
    var = (p * (x - mu) ** 2).sum()
    sd = np.sqrt(var)
    skew = (p * (x - mu) ** 3).sum() / sd ** 3 if sd > 0 else np.nan
    kurt = (p * (x - mu) ** 4).sum() / var ** 2 if sd > 0 else np.nan
    pp = p[p > 0]
    return pd.Series({"mean": mu, "std_bp": sd * 100, "entropy": -(pp * np.log(pp)).sum(),
                      "skewness": skew, "kurtosis": kurt, "n_strikes": int((p > 0).sum())})

mom = raw.groupby(["date", "meeting_date"]).apply(moments).reset_index()

# ------------------------------------------------------------------
# [블록 4] 점검 로그: 분포가 한 점에 몰린 날(std=0 → 왜도·첨도 계산 불가) 건수
# ------------------------------------------------------------------
zero = (mom["std_bp"] == 0).sum()
log.info(f"모멘트 {len(mom):,}행 생성. std=0(왜도·첨도 NaN) {zero}행")
log.info(f"std_bp 요약: 평균 {mom['std_bp'].mean():.2f}, 중앙값 {mom['std_bp'].median():.2f}, 최대 {mom['std_bp'].max():.2f}")

mom.to_csv(C.FILES["kalshi"], index=False)
log.info(f"저장: {C.FILES['kalshi'].name}")
log.info("=== STEP 03 완료 ===")
