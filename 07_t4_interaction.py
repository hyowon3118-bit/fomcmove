"""
07_t4_interaction.py  —  T4. 불확실성 × 충격 상호작용 (Q4)
=========================================================
[역할] Kalshi 불확실성이 높을 때 통화정책 충격의 2년물 효과가 약해지는지 검정 (BLM 2022 재현).
  식: ΔUST2Y_FOMC = a + b·Shock + c·(Shock × KalshiStd(D-1)) + d·KalshiStd(D-1) + e
  Shock: USMPD 통화정책 충격 (config.USMPD_SHOCK_COLS 의 각 컬럼마다 실행)
  판단: c<0 & 유의 → 불확실성이 충격 효과를 약화
  표준오차: HC3
  출력: outputs_verify/t4_ols.csv
※ 회의 순번 h는 계획서 T4에 지정 없음 → T3와 같게 h=2 주, h=1 보조로 둘 다 실행
"""
import pandas as pd

import config as C
import utils as U

log = C.get_logger("07_T4")
log.info("=== STEP 07 (T4): 불확실성 × 충격 상호작용 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 이벤트 패널 읽기
# ------------------------------------------------------------------
ev = pd.read_csv(C.OUT_DIR / "panel_event.csv", parse_dates=["fomc_date", "d1_date"])

# ------------------------------------------------------------------
# [블록 2] 충격 변수 × h 조합마다 상호작용항 만들고 회귀
# ------------------------------------------------------------------
out = []
for shock in C.USMPD_SHOCK_COLS:
    if shock not in ev:
        log.warning(f"충격 컬럼 '{shock}' 없음 → 건너뜀")
        continue
    for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
        k = f"kstd_h{h}_d1"
        inter = f"{shock}_x_{k}"
        ev[inter] = ev[shock] * ev[k]
        _, rows = U.run_ols(ev, "dUST2Y", [shock, inter, k], f"T4 {shock} h{h}", logger=log)
        if rows.empty:
            continue
        out.append(rows.assign(h=h, shock=shock))

        # [블록 3] 판단: 상호작용 계수 c
        r = rows[rows["var"] == inter]
        c, p = r["coef"].iloc[0], r["p"].iloc[0]
        ok = (c < 0) and (p < C.ALPHA)
        log.info(f"[판단] {shock} h={h}: c={c:.4f}, p={p:.4f} → {'c<0 & 유의 (BLM 재현)' if ok else '기준 미충족'}")

if out:
    pd.concat(out).to_csv(C.OUT_DIR / "t4_ols.csv", index=False)
log.info("=== STEP 07 (T4) 완료 ===")
