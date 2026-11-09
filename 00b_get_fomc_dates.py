"""
00b_get_fomc_dates.py
=====================
[역할] 연준 FOMC 캘린더 페이지에서 회의일을 가져와 data/fomc_dates.csv 생성.
  - 직접 스크래핑 코드를 짜지 않고 pyfedwatch의 get_fomc_data_fed() 사용
    (이 함수가 https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm 을 읽어
     회의일·상태(Scheduled/Unscheduled/Cancelled/Notation Vote)를 반환)
  - 회의일 = 이틀 회의의 마지막 날(결정 발표일)
  - 정례회의(Scheduled)만 남김
  필요 설치: pip3 install "pandas==2.2.3" setuptools pyfedwatch  (계획서 5장)
"""
import pandas as pd
from pyfedwatch.datareader import get_fomc_data_fed

import config as C

log = C.get_logger("00b_fomc")
log.info("=== STEP 00b: FOMC 회의일 수집 시작 ===")

# ------------------------------------------------------------------
# [블록 1] Fed 캘린더 페이지 읽기
# ------------------------------------------------------------------
log.info("Fed 웹사이트 접속 중...")
raw = get_fomc_data_fed().reset_index()
log.info(f"가져온 회의 {len(raw)}건, 상태별: {raw['Status'].value_counts().to_dict()}")

# ------------------------------------------------------------------
# [블록 2] 정례회의만 남기고 저장
# ------------------------------------------------------------------
sched = raw[raw["Status"] == "Scheduled"].copy()
sched["date"] = pd.to_datetime(sched["FOMCDate"])
sched = sched.sort_values("date")[["date"]]
sched["date"] = sched["date"].dt.strftime("%Y-%m-%d")
sched.to_csv(C.FILES["fomc"], index=False)
log.info(f"저장: {C.FILES['fomc']} ({len(sched)}건, {sched['date'].iloc[0]} ~ {sched['date'].iloc[-1]})")

# ------------------------------------------------------------------
# [블록 3] 필요한 기간(2021-07 ~ 2028-01) 커버 여부 점검
#   Kalshi 계약이 2021-07 회의부터 2028-01 회의(KXFED-28JAN)까지 있음
# ------------------------------------------------------------------
if sched["date"].iloc[0] > "2021-07-31":
    log.warning("2021-07 회의가 없음 → 페이지에 안 나오는 과거 회의는 수동 추가 필요")
if sched["date"].iloc[-1] < "2028-01-01":
    log.warning("2028-01 회의가 없음 → 아직 일정 미발표일 수 있음. KXFED-28JAN 등은 00a에서 제외됨")
log.info("=== STEP 00b 완료 ===")
