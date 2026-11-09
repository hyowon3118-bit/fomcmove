"""
08_t5_granger.py  —  T5. 선후행 관계 (Q1)
========================================
[역할] Kalshi 분포 폭 변화와 MOVE·FedWatch 변화 사이의 예측 선후관계(Granger) 양방향 검정.
  쌍: ΔKalshi std ↔ ΔMOVE,  ΔKalshi std ↔ ΔFedWatch std
  절차: (1) ADF 정상성 확인 → (2) VAR 정보기준(AIC)으로 시차 선택
        → (3) statsmodels grangercausalitytests (양방향)
  출력: outputs_verify/t5_granger.csv
※ 해석 주의: 예측 선후관계일 뿐 실제 인과 아님
※ 시차를 정보기준으로 고르는 관행의 근거 문헌은 계획서에서 '미확인'
※ 계약 교체일 차분(NaN)은 제거 → 제거 지점 앞뒤가 이어 붙여지는 한계 있음 (로그에 건수 표시)
"""
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

import config as C

log = C.get_logger("08_T5")
log.info("=== STEP 08 (T5): Granger 인과 검정 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 일별 패널 읽기
# ------------------------------------------------------------------
daily = pd.read_csv(C.OUT_DIR / "panel_daily.csv", index_col="date", parse_dates=True)

# ------------------------------------------------------------------
# [블록 2] 검정할 변수 쌍 정의 (h=2 주, h=1 보조)
# ------------------------------------------------------------------
pairs = []
for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
    pairs.append((f"d_k_std_bp_h{h}", "d_move", h))
    if C.USE_FEDWATCH:
        pairs.append((f"d_k_std_bp_h{h}", f"d_fw_std_h{h}", h))

rows = []
for a, b, h in pairs:
    d = daily[[a, b]]
    n_all = len(d)
    d = d.dropna()
    log.info(f"--- h={h}: {a} ↔ {b} | 사용 {len(d)}일 (결측 제거 {n_all - len(d)}일)")
    if len(d) < 50:
        log.warning("관측치 부족 → 건너뜀")
        continue

    # --------------------------------------------------------------
    # [블록 3] ADF 단위근 검정: 차분 변수가 정상인지 확인 (p<0.05면 정상)
    # --------------------------------------------------------------
    adf = {c: adfuller(d[c], autolag="AIC")[1] for c in (a, b)}
    for c, p in adf.items():
        log.info(f"    ADF {c}: p={p:.4f} {'(정상)' if p < C.ALPHA else '(비정상 의심)'}")

    # --------------------------------------------------------------
    # [블록 4] VAR 정보기준으로 시차 선택 (최소 1)
    # --------------------------------------------------------------
    sel = VAR(d.values).select_order(maxlags=C.GRANGER_MAXLAG)
    lag = max(1, int(getattr(sel, C.GRANGER_IC)))
    log.info(f"    선택 시차({C.GRANGER_IC.upper()}): {lag}")

    # --------------------------------------------------------------
    # [블록 5] 양방향 Granger 검정
    #   grangercausalitytests 귀무가설: 두 번째 열이 첫 번째 열을 Granger-cause 하지 않음
    # --------------------------------------------------------------
    for cause, effect in [(a, b), (b, a)]:
        res = grangercausalitytests(d[[effect, cause]], [lag])[lag][0]
        F, p = res["ssr_ftest"][0], res["ssr_ftest"][1]
        log.info(f"    {cause} → {effect}: F={F:.3f}, p={p:.4f} {'★유의' if p < C.ALPHA else ''}")
        rows.append({"h": h, "cause": cause, "effect": effect, "lag": lag, "n": len(d),
                     "F": F, "p_F": p, "p_chi2": res["ssr_chi2test"][1],
                     "adf_p_cause": adf[cause], "adf_p_effect": adf[effect]})

pd.DataFrame(rows).to_csv(C.OUT_DIR / "t5_granger.csv", index=False)
log.info("=== STEP 08 (T5) 완료 ===")
