"""
03_build_panels.py
==================
[역할] 검정(T1~T5)에 쓸 분석용 데이터셋 2개 생성.
  출력1: outputs_verify/panel_daily.csv  — 일별 (T1, T2, T5)
  출력2: outputs_verify/panel_event.csv  — FOMC 이벤트별 (T3, T4)

변수 규칙 (계획서 2장 '변수 구성 규칙'):
  - Kalshi/FedWatch 모두 회의 순번 h=1(가장 가까운), h=2(두 번째) 각각 생성
  - 차분은 같은 회의 계약 안에서만 (계약이 바뀌는 날 제거)
  - 이벤트 설명변수는 회의 전날(D-1) 종가 기준
"""
import numpy as np
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
fw = None
if C.USE_FEDWATCH:
    fw = pd.read_csv(C.OUT_DIR / "fedwatch_moments.csv", parse_dates=["watch_date", "meeting"])
    fw = fw.rename(columns={"watch_date": "date"})
else:
    log.info("USE_FEDWATCH=False → FedWatch 변수 없이 패널 생성")

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
# [블록 3] Kalshi·FedWatch h별 값 붙이기
# ------------------------------------------------------------------
k_vals = [c for c in ["std_bp", "entropy", "skew", "kurt"] if c in kalshi.columns]
for h in HS:
    daily = daily.join(U.select_horizon(kalshi, h, k_vals, "k"), how="left")
    log.info(f"h={h}: Kalshi std 결측 {daily[f'k_std_bp_h{h}'].isna().sum()}일")
    if fw is not None:
        daily = daily.join(U.select_horizon(fw, h, ["fw_std_bp", "fw_mean"], "fw"), how="left")
        log.info(f"h={h}: FedWatch std 결측 {daily[f'fw_fw_std_bp_h{h}'].isna().sum()}일")
        # 같은 h에서 Kalshi와 FedWatch가 같은 회의를 가리키는지 확인 (계획서: '같은 회의' 사용)
        both = daily[[f"k_meeting_h{h}", f"fw_meeting_h{h}"]].dropna()
        mismatch = (both.iloc[:, 0] != both.iloc[:, 1]).sum()
        log.info(f"h={h}: Kalshi–FedWatch 대상 회의 불일치 {mismatch}일 / {len(both)}일")

# ------------------------------------------------------------------
# [블록 4] 차분 변수 (A4: 수준이 아닌 변화로 분석)
# ------------------------------------------------------------------
for h in HS:
    for v in k_vals:
        daily[f"d_k_{v}_h{h}"] = U.diff_within_meeting(daily, f"k_{v}_h{h}", f"k_meeting_h{h}")
    if fw is not None:
        daily[f"d_fw_std_h{h}"] = U.diff_within_meeting(daily, f"fw_fw_std_bp_h{h}", f"fw_meeting_h{h}")
daily["d_move"] = daily["move"].diff()
if vix is not None:
    daily["d_vix"] = daily["vix"].diff()

# ------------------------------------------------------------------
# [블록 5] 향후 21거래일 실현변동성 (T2 종속변수, A7)
#   RV(t) = sqrt( Σ_{j=1..21} Δ2Y(t+j)² ), 옵션으로 연율화
# ------------------------------------------------------------------
sq = daily["d2y_bp"] ** 2
fwd_sum = sq[::-1].rolling(C.RV_WINDOW, min_periods=C.RV_WINDOW).sum()[::-1].shift(-1)
daily["rv_fwd_bp"] = np.sqrt(fwd_sum) * (np.sqrt(252 / C.RV_WINDOW) if C.ANNUALIZE else 1)
daily["is_fomc"] = daily.index.isin(fomc_dates)
daily.index.name = "date"
daily.to_csv(C.OUT_DIR / "panel_daily.csv")
log.info(f"panel_daily.csv 저장: {daily.shape}")

# ------------------------------------------------------------------
# [블록 6] USMPD 읽기 → FOMC 이벤트별 2년물 변화와 충격
# ------------------------------------------------------------------
us = pd.read_excel(C.FILES["usmpd"], sheet_name=C.USMPD_SHEET or 0)
if C.USMPD_COLS["event_type"] and C.USMPD_EVENT_FILTER:
    us = us[us[C.USMPD_COLS["event_type"]] == C.USMPD_EVENT_FILTER]
need = [C.USMPD_COLS["date"], C.USMPD_COLS["y2"]] + C.USMPD_SHOCK_COLS
miss = [c for c in need if c not in us.columns]
if miss:
    raise SystemExit(f"USMPD 컬럼 없음: {miss} → 00_inspect_data.py 결과 보고 config.py 수정")
us = us[need].rename(columns={C.USMPD_COLS["date"]: "date", C.USMPD_COLS["y2"]: "dUST2Y"})
us["date"] = pd.to_datetime(us["date"]).dt.normalize()
dup = us["date"].duplicated().sum()
if dup:
    log.warning(f"USMPD 같은 날짜 {dup}건 중복 (이벤트 종류 필터 확인 필요) → 첫 행만 사용")
    us = us.drop_duplicates("date")
log.info(f"USMPD: {len(us)}개 이벤트")

# ------------------------------------------------------------------
# [블록 7] 이벤트 패널: FOMC 회의일 × D-1 설명변수
#   D-1 = 회의일 직전 거래일. D-1에서 h=1 회의가 해당 FOMC인지 검증
# ------------------------------------------------------------------
rows = []
fomc_in = fomc_dates[(fomc_dates >= C.SAMPLE_START) & (fomc_dates <= C.SAMPLE_END)]
for fd in fomc_in:
    prev = daily.loc[:fd - pd.Timedelta(days=1)]
    if prev.empty:
        continue
    d1 = prev.iloc[-1]
    row = {"fomc_date": fd, "d1_date": prev.index[-1], "move_d1": d1["move"]}
    if "vix" in daily:
        row["vix_d1"] = d1["vix"]
    for h in HS:
        row[f"kstd_h{h}_d1"] = d1[f"k_std_bp_h{h}"]
        row[f"kent_h{h}_d1"] = d1.get(f"k_entropy_h{h}", np.nan)
        if fw is not None:
            row[f"fwstd_h{h}_d1"] = d1[f"fw_fw_std_bp_h{h}"]
    row["h1_is_this_meeting"] = d1["k_meeting_h1"] == fd
    rows.append(row)

event = pd.DataFrame(rows).merge(us, left_on="fomc_date", right_on="date", how="left").drop(columns="date")
event["abs_dUST2Y"] = event["dUST2Y"].abs()
bad = (~event["h1_is_this_meeting"]).sum()
if bad:
    log.warning(f"D-1의 h=1 계약이 해당 회의가 아닌 이벤트 {bad}건 (Kalshi 결측 또는 일정 불일치)")
log.info(f"이벤트 {len(event)}개 중 USMPD 매칭 {event['dUST2Y'].notna().sum()}개")
event.to_csv(C.OUT_DIR / "panel_event.csv", index=False)
log.info("=== STEP 03 완료 ===")
