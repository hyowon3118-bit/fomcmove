"""
01_build_fedwatch.py
====================
[역할] pyfedwatch로 연방기금선물(ZQ) 가격에서 FedWatch 확률을 관측일마다 재계산.
  출력1: outputs_verify/fedwatch_probs_long.csv   (관측일 × 회의 × 금리변경폭 확률)
  출력2: outputs_verify/fedwatch_moments.csv      (관측일 × 회의별 평균·표준편차 bp)

전제(계획서 5장):
  - pandas 2.2.3 + setuptools + pyfedwatch 설치
  - watch_rate_range 를 직접 넘겨 내부 FRED 호출을 피함 (여기선 rate_cols=False로
    '금리 변경폭(bp)' 컬럼을 받고, 목표범위 중간값은 DFEDTARL/U에서 직접 더함)
"""
import numpy as np
import pandas as pd
import pyfedwatch as fw

import config as C
import utils as U

log = C.get_logger("01_fedwatch")
log.info("=== STEP 01: pyfedwatch FedWatch 확률 재계산 시작 ===")

# ------------------------------------------------------------------
# [블록 1] ZQ 월물 가격 읽기 함수 (pyfedwatch user_func)
#   pyfedwatch 규칙: 첫 인자 이름이 반드시 'symbol', 반환 DF에 'Date'와 'Close' 필요
#   같은 월물을 관측일마다 반복해서 읽으므로 메모리 캐시 사용
# ------------------------------------------------------------------
_ZQ_CACHE = {}

def read_zq(symbol, path):
    if symbol not in _ZQ_CACHE:
        f = path / f"{symbol}.csv"
        if not f.exists():
            raise FileNotFoundError(f"ZQ 월물 파일 없음: {f.name}")
        df = pd.read_csv(f)[["Date", "Close"]]
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        _ZQ_CACHE[symbol] = df.dropna().sort_values("Date")
    return _ZQ_CACHE[symbol].copy()      # pyfedwatch가 원본을 변경하므로 복사본 반환

# ------------------------------------------------------------------
# [블록 2] 입력 준비: FOMC 일정, 목표범위, 관측일 목록
#   관측일 = Kalshi 관측일 ∪ CME 공식 확률 관측일 (평일만)
# ------------------------------------------------------------------
fomc_dates = U.load_fomc_dates()
fomc_str = [d.strftime("%Y-%m-%d") for d in fomc_dates]

tl = U.read_fred_csv(C.FILES["dfedtarl"], "lower")
tu = U.read_fred_csv(C.FILES["dfedtaru"], "upper")
target = tl.join(tu, how="inner")

kalshi_dates = pd.to_datetime(pd.read_csv(C.FILES["kalshi"])[C.KALSHI_COLS["date"]]).unique()
watch_dates = pd.DatetimeIndex(kalshi_dates)
if C.FILES["cme_fw"].exists():
    cme_dates = pd.to_datetime(pd.read_csv(C.FILES["cme_fw"])[C.CME_FW_COLS["watch_date"]]).unique()
    watch_dates = watch_dates.union(pd.DatetimeIndex(cme_dates))
watch_dates = watch_dates[watch_dates.dayofweek < 5].sort_values()
log.info(f"계산할 관측일: {len(watch_dates):,}개 ({watch_dates.min().date()} ~ {watch_dates.max().date()})")

# ------------------------------------------------------------------
# [블록 3] 관측일마다 pyfedwatch 실행
#   generate_hike_info(rate_cols=False) → 컬럼 = 현재 대비 금리 변경폭(bp), 값 = 확률
#   실패한 날짜는 원인과 함께 기록하고 건너뜀
# ------------------------------------------------------------------
records, failures = [], []
for i, wd in enumerate(watch_dates, 1):
    wd_str = wd.strftime("%Y-%m-%d")
    try:
        lo, hi = target.loc[:wd].iloc[-1][["lower", "upper"]]       # 관측일 기준 목표범위
        model = fw.fedwatch.FedWatch(watch_date=wd_str, fomc_dates=fomc_str,
                                     num_upcoming=C.FEDWATCH_NUM_UPCOMING,
                                     user_func=read_zq, path=C.ZQ_DIR)
        res = model.generate_hike_info(rate_cols=False, watch_rate_range=(lo, hi))
        long = res.stack().rename("prob").reset_index()
        long.columns = ["watch_date", "meeting", "hike_bp", "prob"]
        long["mid_now"] = (lo + hi) / 2
        long["range_low"] = lo + long["hike_bp"].astype(float) / 100    # 결과 목표범위 하단 (%)
        records.append(long)
    except Exception as e:
        failures.append({"watch_date": wd_str, "error": f"{type(e).__name__}: {e}"})
    if i % 100 == 0 or i == len(watch_dates):
        log.info(f"  진행 {i}/{len(watch_dates)}  성공 {len(records)}  실패 {len(failures)}")

if failures:
    fail_df = pd.DataFrame(failures)
    fail_df.to_csv(C.OUT_DIR / "fedwatch_failures.csv", index=False)
    log.warning(f"실패 {len(failures)}건 → fedwatch_failures.csv. 주요 원인: "
                f"{fail_df['error'].str.split(':').str[0].value_counts().head(3).to_dict()}")

if not records:
    raise SystemExit("pyfedwatch 계산 결과가 하나도 없음. ZQ 파일과 FOMC 일정 확인 필요")

probs = pd.concat(records, ignore_index=True)
probs["watch_date"] = pd.to_datetime(probs["watch_date"])
probs["meeting"] = pd.to_datetime(probs["meeting"])
probs.to_csv(C.OUT_DIR / "fedwatch_probs_long.csv", index=False)
log.info(f"확률 저장: fedwatch_probs_long.csv ({len(probs):,}행)")

# ------------------------------------------------------------------
# [블록 4] 회의별 분포 모멘트 계산 (계획서 '변수 구성 규칙')
#   평균(%) = 현재 범위 중간값 + Σ p·변경폭
#   표준편차(bp) = sqrt(Σ p·(변경폭 − 평균변경폭)²)  ← 평행이동 불변
#   확률 합이 1에서 크게 벗어나면 경고
# ------------------------------------------------------------------
def moments(g):
    p = g["prob"].to_numpy(float)
    s = g["hike_bp"].to_numpy(float)
    psum = p.sum()
    mu = (p * s).sum() / psum
    sd = np.sqrt((p * (s - mu) ** 2).sum() / psum)
    return pd.Series({"fw_mean": g["mid_now"].iloc[0] + mu / 100, "fw_std_bp": sd,
                      "prob_sum": psum, "n_outcomes": int((p > 1e-6).sum())})

mom = probs.groupby(["watch_date", "meeting"]).apply(moments).reset_index()
mom["h"] = U.meeting_horizon(mom["watch_date"], mom["meeting"], fomc_dates)
bad = (mom["prob_sum"] - 1).abs() > 0.01
if bad.any():
    log.warning(f"확률 합 ≠ 1 인 관측 {bad.sum()}건 (ZQ 가격 이상 가능)")
mom.to_csv(C.OUT_DIR / "fedwatch_moments.csv", index=False)

# A13 점검: h=1 의 표준편차는 12.5bp 이하여야 함
h1_max = mom.loc[mom["h"] == 1, "fw_std_bp"].max()
log.info(f"A13 점검: h=1 FedWatch std 최대 {h1_max:.2f}bp (이론 상한 12.5bp)")
log.info(f"h별 평균 std: {mom.groupby('h')['fw_std_bp'].mean().round(2).to_dict()}")
log.info("=== STEP 01 완료 ===")
