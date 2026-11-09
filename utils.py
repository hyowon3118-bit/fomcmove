"""
utils.py
========
[역할] 각 단계 스크립트가 공통으로 쓰는 데이터 로더와 계산 함수.
  - 원자료 읽기 + 컬럼 표준화
  - FOMC 회의 순번(h) 계산
  - 회귀 결과 정리
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

import config as C

log = C.get_logger("utils")


# ------------------------------------------------------------------
# [블록 1] FRED 형식 CSV 읽기
#   FRED 다운로드 CSV는 첫 컬럼이 날짜(DATE 또는 observation_date),
#   두 번째 컬럼이 값. 결측은 '.' 또는 빈칸 → NaN 처리
# ------------------------------------------------------------------
def read_fred_csv(path, name):
    df = pd.read_csv(path)
    df.columns = ["date", name]
    df["date"] = pd.to_datetime(df["date"])
    df[name] = pd.to_numeric(df[name], errors="coerce")
    df = df.dropna().set_index("date").sort_index()
    log.info(f"FRED {name}: {len(df):,}행, {df.index.min().date()} ~ {df.index.max().date()}")
    return df


# ------------------------------------------------------------------
# [블록 2] FOMC 회의일 목록 읽기
# ------------------------------------------------------------------
def load_fomc_dates():
    df = pd.read_csv(C.FILES["fomc"])
    dates = pd.to_datetime(df[C.FOMC_DATE_COL]).sort_values().drop_duplicates().reset_index(drop=True)
    log.info(f"FOMC 회의일: {len(dates)}개, {dates.min().date()} ~ {dates.max().date()}")
    return dates


# ------------------------------------------------------------------
# [블록 3] 회의 순번(h) 계산
#   관측일 t 기준으로 '아직 열리지 않은(t보다 뒤의)' 회의 중 몇 번째인지.
#   예) 회의 전날(D-1)에는 그 회의가 h=1.
#   FOMC 당일에는 그날 회의는 끝난 것으로 보고 다음 회의가 h=1.
# ------------------------------------------------------------------
def meeting_horizon(obs_dates: pd.Series, meeting_dates: pd.Series, fomc_dates: pd.Series) -> pd.Series:
    fomc_arr = fomc_dates.values
    n_before_obs = np.searchsorted(fomc_arr, obs_dates.values, side="right")      # t 이하 회의 수
    n_upto_meeting = np.searchsorted(fomc_arr, meeting_dates.values, side="right")  # 해당 회의까지 회의 수
    return pd.Series(n_upto_meeting - n_before_obs, index=obs_dates.index)


# ------------------------------------------------------------------
# [블록 4] Kalshi 모멘트 읽기 + 회의 순번(h) 부여
# ------------------------------------------------------------------
def load_kalshi(fomc_dates):
    raw = pd.read_csv(C.FILES["kalshi"])
    inv = {v: k for k, v in C.KALSHI_COLS.items() if v in raw.columns}
    missing = set(C.KALSHI_COLS.values()) - set(raw.columns)
    if missing:
        log.warning(f"Kalshi 파일에 없는 컬럼(무시됨): {missing}")
    df = raw[list(inv)].rename(columns=inv)
    df["date"] = pd.to_datetime(df["date"])
    df["meeting"] = pd.to_datetime(df["meeting"])
    df["h"] = meeting_horizon(df["date"], df["meeting"], fomc_dates)
    df = df[df["h"] >= 1]
    df["d_minus_n"] = (df["meeting"] - df["date"]).dt.days      # 회의까지 남은 일수 (D-n)
    log.info(f"Kalshi: {len(df):,}행, 회의 {df['meeting'].nunique()}개, h 분포 {df['h'].value_counts().sort_index().to_dict()}")
    return df


# ------------------------------------------------------------------
# [블록 5] 2년물 금리 → 일간 변화(bp)와 제곱
# ------------------------------------------------------------------
def load_dgs2():
    df = read_fred_csv(C.FILES["dgs2"], "dgs2")
    df["d2y_bp"] = df["dgs2"].diff() * 100          # %p → bp
    df["d2y_sq"] = df["d2y_bp"] ** 2                # A10: 변동성 대용치
    return df


# ------------------------------------------------------------------
# [블록 6] MOVE / VIX 읽기
# ------------------------------------------------------------------
def load_move():
    raw = pd.read_csv(C.FILES["move"])
    df = raw[[C.MOVE_COLS["date"], C.MOVE_COLS["value"]]].copy()
    df.columns = ["date", "move"]
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None).dt.normalize()
    df["move"] = pd.to_numeric(df["move"], errors="coerce")
    df = df.dropna().drop_duplicates("date").set_index("date").sort_index()
    log.info(f"MOVE: {len(df):,}행, {df.index.min().date()} ~ {df.index.max().date()}")
    return df


def load_vix():
    if not C.FILES["vix"].exists():
        log.info("VIX 파일 없음 → VIX 통제 생략")
        return None
    return read_fred_csv(C.FILES["vix"], "vix")


# ------------------------------------------------------------------
# [블록 7] 회의 순번 h의 값만 뽑아 넓은(wide) 일별 시계열로 변환
#   예) h=2 → 매일 '두 번째로 다가오는 회의'의 std_bp
#   같은 h라도 날짜가 지나면 대상 회의가 바뀌므로 meeting 컬럼도 같이 남김
# ------------------------------------------------------------------
def select_horizon(df, h, value_cols, prefix):
    sub = df[df["h"] == h].sort_values("date").drop_duplicates("date", keep="last")
    out = sub.set_index("date")[["meeting"] + value_cols]
    out.columns = [f"{prefix}_meeting_h{h}"] + [f"{prefix}_{c}_h{h}" for c in value_cols]
    return out


# ------------------------------------------------------------------
# [블록 8] 같은 회의 계약 안에서만 차분
#   h=1 대상 회의가 바뀌는 날(회의 다음날)의 차분은 서로 다른 계약 간 비교라 제거
# ------------------------------------------------------------------
def diff_within_meeting(df, value_col, meeting_col):
    d = df[value_col].diff()
    same = df[meeting_col].eq(df[meeting_col].shift())
    return d.where(same)


# ------------------------------------------------------------------
# [블록 9] OLS + HC3 회귀 실행 후 결과를 표 한 줄씩으로 정리
# ------------------------------------------------------------------
def run_ols(df, y, xs, label, cov="HC3", logger=None):
    logger = logger or log
    d = df[[y] + xs].dropna()
    if len(d) < len(xs) + 5:
        logger.warning(f"[{label}] 관측치 {len(d)}개로 너무 적어 건너뜀")
        return None, pd.DataFrame()
    model = sm.OLS(d[y], sm.add_constant(d[xs])).fit(cov_type=cov)
    logger.info(f"[{label}] N={int(model.nobs)}, R²={model.rsquared:.3f}")
    for x in xs:
        logger.info(f"    {x:<28} b={model.params[x]: .4f}  se={model.bse[x]:.4f}  p={model.pvalues[x]:.4f}")
    rows = pd.DataFrame({
        "model": label, "y": y, "var": model.params.index,
        "coef": model.params.values, "se": model.bse.values,
        "t": model.tvalues.values, "p": model.pvalues.values,
        "nobs": int(model.nobs), "r2": model.rsquared,
    })
    return model, rows
