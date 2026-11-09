"""
06_t3_event_study.py  —  T3. FOMC 이벤트 스터디 (Q2·Q3)
======================================================
[역할] FOMC 직전(D-1) Kalshi 분포 폭이 FOMC 발표 구간 2년물 변화 크기를 예고하는지 검정.
  식: |ΔUST2Y_FOMC| = a + b·KalshiStd(D-1) + c·MOVE(D-1) + d·FedWatchStd(D-1) + e
  - KalshiStd·FedWatchStd는 같은 회의 순번 h 기준
  - 주 분석 h=2, 보조 h=1 (A13)
  - 표준오차: HC3 (DKW와 동일)
  판단: b>0 & 유의 → 사전 분포 폭이 금리 변동 예고 / d 통제 후에도 유의 → 선물시장 이상의 정보
  출력: outputs_verify/t3_ols.csv
"""
import pandas as pd

import config as C
import utils as U

log = C.get_logger("06_T3")
log.info("=== STEP 06 (T3): FOMC 이벤트 스터디 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 이벤트 패널 읽기
# ------------------------------------------------------------------
ev = pd.read_csv(C.OUT_DIR / "panel_event.csv", parse_dates=["fomc_date", "d1_date"])
log.info(f"이벤트 {len(ev)}개, |ΔUST2Y| 유효 {ev['abs_dUST2Y'].notna().sum()}개 (표본 작음 주의: 계획서 6장)")

# ------------------------------------------------------------------
# [블록 2] 사양별 회귀
#   (1) Kalshi만  (2) Kalshi+MOVE  (3) Kalshi+MOVE+FedWatch
# ------------------------------------------------------------------
out = []
for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
    k, f = f"kstd_h{h}_d1", f"fwstd_h{h}_d1"
    specs = {
        "(1) Kalshi":         [k],
        "(2) Kalshi+MOVE":    [k, "move_d1"],
    }
    if C.USE_FEDWATCH:
        specs["(3) Kalshi+MOVE+FW"] = [k, "move_d1", f]
    for name, xs in specs.items():
        _, rows = U.run_ols(ev, "abs_dUST2Y", xs, f"T3 h{h} {name}", logger=log)
        out.append(rows.assign(h=h, spec=name))
res = pd.concat(out)
res.to_csv(C.OUT_DIR / "t3_ols.csv", index=False)

# ------------------------------------------------------------------
# [블록 3] 판단 요약 (b의 부호·유의성)
# ------------------------------------------------------------------
for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
    for spec in ["(1) Kalshi", "(3) Kalshi+MOVE+FW" if C.USE_FEDWATCH else "(2) Kalshi+MOVE"]:
        r = res[(res["h"] == h) & (res["spec"] == spec) & (res["var"] == f"kstd_h{h}_d1")]
        if r.empty:
            continue
        b, p = r["coef"].iloc[0], r["p"].iloc[0]
        ok = (b > 0) and (p < C.ALPHA)
        log.info(f"[판단] h={h} {spec}: b={b:.4f}, p={p:.4f} → {'b>0 & 유의' if ok else '기준 미충족'}")
log.info("=== STEP 06 (T3) 완료 ===")
