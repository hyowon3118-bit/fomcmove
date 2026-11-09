"""
05_t2_forecast_rv.py  —  T2. MOVE와의 예측력 비교 (Q1·Q3)
=========================================================
[역할] t 시점 Kalshi 분포 폭이 향후 21거래일 2년물 실현변동성을
       MOVE·FedWatch를 통제한 뒤에도 설명하는지 검정.
  식: RV_2Y(t, t+21) = a + b·KalshiStd(t) + c·MOVE(t) + d·FedWatchStd(t) + e
  표본: 21거래일 간격으로 겹치지 않게 추출 (A7)
  판단: 통제 후에도 b 유의 → Kalshi가 추가 정보 보유
  출력: outputs_verify/t2_ols.csv
※ T2 표준오차 방식은 계획서에 지정 없음 → HC3 사용 (표본이 겹치지 않으므로 HAC 불필요)
"""
import pandas as pd

import config as C
import utils as U

log = C.get_logger("05_T2")
log.info("=== STEP 05 (T2): 실현변동성 예측력 비교 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 일별 패널 → 겹치지 않는 표본 추출
#   RV가 계산된 날 중 첫날부터 21거래일 간격으로 선택
# ------------------------------------------------------------------
daily = pd.read_csv(C.OUT_DIR / "panel_daily.csv", index_col="date", parse_dates=True)
valid = daily.dropna(subset=["rv_fwd_bp"])
sample = valid.iloc[::C.RV_WINDOW]
log.info(f"비중첩 표본: {len(sample)}개 시점 ({sample.index.min().date()} ~ {sample.index.max().date()})")

# ------------------------------------------------------------------
# [블록 2] 회귀 사양 단계적으로 추가
#   (1) Kalshi만  (2) MOVE만  (3) Kalshi+MOVE  (4) Kalshi+MOVE+FedWatch
#   h=2 주 분석, h=1 보조 (A13)
# ------------------------------------------------------------------
out = []
for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
    k, f = f"k_std_bp_h{h}", f"fw_fw_std_bp_h{h}"
    specs = {
        "(1) Kalshi":            [k],
        "(2) MOVE":              ["move"],
        "(3) Kalshi+MOVE":       [k, "move"],
    }
    if C.USE_FEDWATCH:
        specs["(4) Kalshi+MOVE+FW"] = [k, "move", f]
    for name, xs in specs.items():
        _, rows = U.run_ols(sample, "rv_fwd_bp", xs, f"T2 h{h} {name}", logger=log)
        out.append(rows.assign(h=h, spec=name))

res = pd.concat(out)
res.to_csv(C.OUT_DIR / "t2_ols.csv", index=False)

# ------------------------------------------------------------------
# [블록 3] 판단 요약: 사양 (4)에서 Kalshi 계수 b의 유의성
# ------------------------------------------------------------------
for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
    final = "(4) Kalshi+MOVE+FW" if C.USE_FEDWATCH else "(3) Kalshi+MOVE"   # 가장 많이 통제한 사양
    r = res[(res["h"] == h) & (res["spec"] == final) & (res["var"] == f"k_std_bp_h{h}")]
    if r.empty:
        continue
    b, p = r["coef"].iloc[0], r["p"].iloc[0]
    verdict = "유의 → 추가 정보 있음" if p < C.ALPHA else "유의하지 않음"
    log.info(f"[판단] h={h} {final}: b={b:.4f}, p={p:.4f} → {verdict}")
log.info("=== STEP 05 (T2) 완료 ===")
