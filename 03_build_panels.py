"""
03_build_panels.py
==================
[역할] 검정(T1~T5)에 쓸 분석용 데이터셋 2개 생성.
  출력: outputs_verify/panel_daily.csv  — 일별 (T1, T5)

변수 규칙 (계획서 2장 '변수 구성 규칙'):
  - Kalshi 회의 순번 h=1(가장 가까운), h=2(두 번째) 각각 생성
  - 차분은 같은 회의 계약 안에서만 (직전 거래일 대비)
"""
import pandas as pd

import config as C
import utils as U

log = C.get_logger("03_panels")
log.info("=== STEP 03: 분석용 패널 생성 시작 ===")
HS = sorted({C.AUX_HORIZON, C.MAIN_HORIZON})

# ------------------------------------------------------------------
# [블록 1] 원자료 읽기
# ------------------------------------------------------------------
fomc_dates = U.load_fomc_dates()
kalshi = U.load_kalshi(fomc_dates)
dgs2 = U.load_dgs2()
move = U.load_move()
vix = U.load_vix()

# ------------------------------------------------------------------
# [블록 2] 일별 패널 뼈대 = 2년물 거래일 (표본 기간 내)
#   Kalshi는 주말에도 값이 있을 수 있으나 금리 거래일 기준으로 맞춤
# ------------------------------------------------------------------
daily = dgs2.loc[C.SAMPLE_START:C.SAMPLE_END].copy()
daily = daily.join(move, how="left")
if vix is not None:
    daily = daily.join(vix, how="left")
log.info(f"일별 뼈대: {len(daily):,} 거래일, MOVE 결측 {daily['move'].isna().sum()}일")

# ------------------------------------------------------------------
# [블록 3] Kalshi h별 값 붙이기
# ------------------------------------------------------------------
k_vals = [c for c in ["std_bp", "entropy", "skew", "kurt"] if c in kalshi.columns]
for h in HS:
    daily = daily.join(U.select_horizon(kalshi, h, k_vals, "k"), how="left")
    log.info(f"h={h}: Kalshi std 결측 {daily[f'k_std_bp_h{h}'].isna().sum()}일")

# ------------------------------------------------------------------
# [블록 4] 차분 변수 (A4: 수준이 아닌 변화로 분석)
# ------------------------------------------------------------------
#   [수정 2026-11-09] Kalshi 차분은 '같은 계약' 안에서 먼저 계산한 뒤 h를 붙임
#   - 이전 방식(h열 안에서 차분 후 계약 바뀌는 날 제거)은 FOMC 당일을 전부 결측으로 만듦
#     (당일 h=1이 다음 회의로 바뀌기 때문)
#   - 새 방식: Δ(t) = 같은 회의 계약의 [t 종가 − 직전 거래일 종가], h는 t 기준
#     → FOMC 당일엔 '다음 회의 계약'의 전날 대비 변화가 들어감
#     (DKW 2026 Table 5: "meetings more than one month ahead, end of previous day to end of release day")
#   - 직전 '거래일'(2년물 거래일 기준) 값이 없으면 결측 처리
tdays = daily.index
prev_td = pd.Series(tdays[:-1], index=tdays[1:])                     # 거래일 → 직전 거래일
kd = kalshi[kalshi["date"].isin(tdays)].sort_values(["meeting", "date"]).copy()
prev_obs = kd.groupby("meeting")["date"].shift()                     # 같은 계약의 직전 관측일
valid = prev_obs.eq(kd["date"].map(prev_td))                          # 직전 관측일 = 직전 거래일인지
for v in k_vals:
    kd[f"d_{v}"] = kd.groupby("meeting")[v].diff().where(valid)
for h in HS:
    sub = U.select_horizon(kd, h, [f"d_{v}" for v in k_vals], "tmp")
    for v in k_vals:
        daily[f"d_k_{v}_h{h}"] = sub[f"tmp_d_{v}_h{h}"]
    n_f = daily.loc[daily.index.isin(fomc_dates), f"d_k_std_bp_h{h}"].notna().sum()
    log.info(f"h={h}: Δstd 비결측 {daily[f'd_k_std_bp_h{h}'].notna().sum()}일 (그중 FOMC 당일 {n_f}일)")
daily["d_move"] = daily["move"].diff()
if vix is not None:
    daily["d_vix"] = daily["vix"].diff()

# ------------------------------------------------------------------
# [블록 5] FOMC 당일 표시 후 저장
# ------------------------------------------------------------------
daily["is_fomc"] = daily.index.isin(fomc_dates)
daily.index.name = "date"
daily.to_csv(C.OUT_DIR / "panel_daily.csv")
log.info(f"panel_daily.csv 저장: {daily.shape}")

log.info("=== STEP 03 완료 ===")
