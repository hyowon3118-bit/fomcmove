"""
09_build_kalshi_daily_et.py
===========================
[역할] 체결 단위 데이터(08 결과)로 Kalshi 일별 확률분포를 다시 만듦.
       일별 가격을 '그날 마지막 체결가'로 정하는 기준 시각을 두 가지로 만들어 비교:
         - utc  : 원저자 R 코드와 같음. UTC 자정 기준 하루 (= 동부시간 오후 7~8시에 하루가 끝남)
         - et16 : 동부시간 오후 4시 기준. 오후 4시 이후 체결은 다음 날로 넘김
                  → MOVE·2년물(뉴욕 장 마감) 종가와 시각을 맞추기 위함
  입력: DATA_DIR/trade_level_data_fed_levels.csv
  출력: DATA_DIR/daily_distributions_fed_levels_utc.csv
        DATA_DIR/daily_distributions_fed_levels_et16.csv
        (컬럼은 R 원본 출력과 같음: contract_preamble, date, expiry_date, strike,
         yes_price, daily_volume, adjusted_yes_price, probability)

분포 구성은 원저자 R 코드(convert_trade_level_data_cdfs.R)를 옮긴 kalshi_dkw.py 사용.
FOMC 설정도 원본과 같음: strike_int=0.25, days_before_horizon=180, middle-out
일별 집계(convert_to_daily, method='last')만 이 파일에서 직접 구현: 기준 시각 변경 + 마지막 시각 동시 체결은 VWAP.

※ 오후 4시는 MOVE·DGS2 종가 시각의 근사치. DGS2·MOVE의 정확한 산출 시각은 확인 못 함 → CUTOFF_HOUR로 바꿀 수 있음
"""
import argparse

import numpy as np
import pandas as pd

import config as C
import kalshi_dkw as K

log = C.get_logger("09_daily_et")
SRC = C.DATA_DIR / "trade_level_data_fed_levels.csv"
STRIKE_INT, HORIZON = 0.25, 180          # 원본 data_convert_runner.R의 FFR 설정

ap = argparse.ArgumentParser()
ap.add_argument("--cutoff-hour", type=int, default=16, help="동부시간 기준 하루 마감 시각 (기본 16시)")
args = ap.parse_args()
CUTOFF_HOUR = args.cutoff_hour

log.info("=== STEP 09: 체결 데이터 → 일별 분포 (UTC / 동부시간 기준) 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 체결 데이터 읽기 + R read_data와 같은 정리
#   - 가격: yes_price_dollars × 100 (센트). 옛 형식(yes_price)만 있으면 그대로
#   - 수량: count_fp (없으면 count)
#   - 계약명·행사가: 티커에서 추출 (예: KXFED-25DEC-T4.00 → KXFED-25DEC, 4.00)
# ------------------------------------------------------------------
tr = pd.read_csv(SRC)
log.info(f"[1/4] 체결 {len(tr):,}건, 티커 {tr['ticker'].nunique()}개 읽음")
tr["created_time"] = pd.to_datetime(tr["created_time"], utc=True, format="ISO8601")
if "yes_price_dollars" in tr:
    px = pd.to_numeric(tr["yes_price_dollars"], errors="coerce") * 100
    if "yes_price" in tr:
        px = px.fillna(pd.to_numeric(tr["yes_price"], errors="coerce"))
    tr["yes_price"] = px
qty_col = "count_fp" if "count_fp" in tr else "count"
tr["qty"] = pd.to_numeric(tr[qty_col], errors="coerce")
tr["contract_preamble"] = tr["ticker"].str.replace(r"-T\d+\.?\d*$", "", regex=True)
tr.loc[tr["contract_preamble"] == "FED-22JULY", "contract_preamble"] = "FED-22JUL"   # R 원본과 같은 예외 처리
tr["strike"] = pd.to_numeric(tr["ticker"].str.extract(r"(?<=-T)(\d+\.?\d*)")[0], errors="coerce")
bad = tr["yes_price"].isna() | tr["strike"].isna()
if bad.any():
    log.warning(f"  가격 또는 행사가를 못 읽은 체결 {bad.sum():,}건 제외")
tr = tr[~bad]

# ------------------------------------------------------------------
# [블록 2] 기준 시각별 '거래일' 정하기
# ------------------------------------------------------------------
def assign_date(ts, mode):
    if mode == "utc":                                    # R: as.Date(created_time) (UTC)
        return ts.dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    et = ts.dt.tz_convert("America/New_York")            # 서머타임 자동 반영
    d = et.dt.tz_localize(None).dt.normalize()
    return d + pd.to_timedelta((et.dt.hour >= CUTOFF_HOUR).astype(int), unit="D")


# ------------------------------------------------------------------
# [블록 3] 일별 마지막 체결가 → 분포 (kalshi_dkw = R 원본 이식)
# ------------------------------------------------------------------
cols = ["contract_preamble", "date", "expiry_date", "strike", "yes_price",
        "daily_volume", "adjusted_yes_price", "probability"]
outs = {}
for mode in ["utc", f"et{CUTOFF_HOUR}"]:
    log.info(f"[2/4] [{mode}] 일별 집계 중...")
    t = tr.assign(date=assign_date(tr["created_time"], "utc" if mode == "utc" else "et"))
    # [수정] 마지막 체결 시각에 체결이 여러 개(가격도 제각각)인 경우가 있음 (구 FED- 계약에 많음)
    #   R 원본은 파일 행 순서로 그중 하나를 고르게 돼 결과가 임의적 → 그 묶음의 거래량 가중 평균가(VWAP)를 씀
    #   (원본 R의 convert_to_daily_method='VWAP'은 하루 전체 평균이라 다름. 여기선 마지막 시각 묶음에만 적용)
    key = ["date", "contract_preamble", "strike"]
    t["is_last"] = t["created_time"].eq(t.groupby(key)["created_time"].transform("max"))
    lt = t[t["is_last"]].assign(pq=lambda x: x["yes_price"] * x["qty"])
    last = lt.groupby(key).agg(pq=("pq", "sum"), q=("qty", "sum"), p_mean=("yes_price", "mean"),
                               n_last=("yes_price", "size"), n_px=("yes_price", "nunique"))
    last["yes_price"] = np.where(last["q"] > 0, last["pq"] / last["q"], last["p_mean"])
    daily = (t.groupby(key).agg(daily_volume=("qty", "sum"))
              .join(last[["yes_price", "n_last", "n_px"]]).reset_index())
    log.info(f"  [{mode}] (날짜·계약·행사가) {len(daily):,}행, 마지막 시각에 가격이 2개 이상 → VWAP 처리 "
             f"{(daily['n_px'] > 1).sum():,}행 ({(daily['n_px'] > 1).mean():.1%})")
    daily = daily.drop(columns=["n_last", "n_px"])
    log.info(f"[3/4] [{mode}] 빈 날 채우기 → 단조성 보정(middle-out) → 구간 확률")
    d = K.fill_dataless_days(daily, HORIZON)
    d = K.clean_data(d, "middle-out")
    d = K.convert_to_probabilities(d, STRIKE_INT, HORIZON)
    d = d[cols].sort_values(["contract_preamble", "date", "strike"])
    f = C.DATA_DIR / f"daily_distributions_fed_levels_{mode}.csv"
    d.to_csv(f, index=False)
    s = d.groupby(["contract_preamble", "date"])["probability"].sum()
    log.info(f"  [{mode}] 저장 {f.name}: {len(d):,}행, 계약 {d['contract_preamble'].nunique()}개, "
             f"확률합 100 아닌 (계약·날짜) {(~np.isclose(s, 100)).sum()}개")
    outs[mode] = d

# ------------------------------------------------------------------
# [블록 4] 검증: utc 버전이 기존 R 출력(daily_distributions_fed_levels.csv)과 같은지
#   겹치는 (계약·날짜)에서 표준편차(bp) 비교. 수집 시점이 달라 최근 날짜는 다를 수 있음
# ------------------------------------------------------------------
log.info("[4/4] 기존 R 출력과 비교")


def std_bp(df):
    g = df.assign(w=df["probability"] / 100)
    mu = (g["w"] * g["strike"]).groupby([g["contract_preamble"], g["date"]]).sum().rename("mu")
    g = g.join(mu, on=["contract_preamble", "date"])
    return np.sqrt((g["w"] * (g["strike"] - g["mu"]) ** 2).groupby([g["contract_preamble"], g["date"]]).sum()) * 100


su = std_bp(outs["utc"])
old_f = C.DATA_DIR / "daily_distributions_fed_levels.csv"
if old_f.exists():
    old = pd.read_csv(old_f, parse_dates=["date"])
    so = std_bp(old)
    j = pd.concat([so.rename("old"), su.rename("new")], axis=1, join="inner")
    diff = (j["old"] - j["new"]).abs()
    log.info(f"  겹치는 (계약·날짜) {len(j):,}개 / 기존 {len(so):,}개, 새 {len(su):,}개")
    log.info(f"  std 차이: 0.01bp 이내 {(diff < 0.01).mean():.1%}, 최대 {diff.max():.3f}bp")
    if (diff >= 0.01).any():
        top = j[diff >= 0.01].assign(diff=diff[diff >= 0.01]).sort_values("diff", ascending=False).head(10)
        log.info(f"  차이 큰 (계약·날짜) 상위:\n{top.to_string()}")
    only_old = so.index.difference(su.index)
    if len(only_old):
        log.warning(f"  기존에만 있는 (계약·날짜) {len(only_old):,}개, 계약: "
                    f"{sorted(set(i[0] for i in only_old))[:20]}")
else:
    log.info("  기존 R 출력 파일 없음 → 비교 생략")

# 시각 기준에 따라 바뀐 정도
se = std_bp(outs[f"et{CUTOFF_HOUR}"])
j = pd.concat([su.rename("utc"), se.rename("et")], axis=1, join="inner")
log.info(f"  utc vs et{CUTOFF_HOUR}: std가 다른 (계약·날짜) 비율 {((j['utc'] - j['et']).abs() > 1e-9).mean():.1%}")
log.info("=== STEP 09 완료 ===")
