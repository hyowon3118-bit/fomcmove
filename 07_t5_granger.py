"""
07_t5_granger.py  —  T5. 선후행 관계 (Q1)
====================================
[역할] Kalshi 분포 폭 변화(Δstd)와 MOVE 변화(ΔMOVE) 사이의 예측 선후관계(Granger)를 양방향으로 검정.
  절차: (1) ADF 정상성 확인
        (2) 주 결과: BIC로 고른 시차 + HC3·HAC 강건 Wald 검정 (둘 다 보고)
        (3) 견고성: 시차 1·2·3·5·10 민감도(HC3·HAC), 연도 하나씩 빼기, 극단값 1% 윈저라이즈
  출력: outputs/<timing>/t5_granger.csv          — 주 결과 (BIC 시차, HC3·HAC)
        outputs/<timing>/t5_granger_robust.csv   — 견고성 점검 전체
※ [수정 2026-11-10] 이전 버전은 AIC 시차 + 동분산 F검정(grangercausalitytests).
   AIC는 탐색 범위 끝까지 시차를 늘렸고(최대 10 → 10, 15 → 12~15), 일별 변화는 꼬리가 두꺼워
   이분산을 고려하지 않은 F검정이 과대 유의를 낼 수 있어서 바꿈
※ [수정 2026-11-10] 피드백: HC3는 이분산에만 강건하고 시계열 자기상관은 처리 못 함
   → HAC(Newey-West, truncation lag = utils.nw_maxlags) Wald 검정을 추가해 HC3와 나란히 보고
   (자기상관이 있다면 HC3 단독 결과의 p값은 과소평가될 수 있음)
※ 해석 주의: 예측 선후관계일 뿐 실제 인과 아님
※ 시차를 정보기준으로 고르는 관행의 근거 문헌은 계획서에서 '미확인'. HAC truncation lag
  공식(floor(4·(T/100)^(2/9)))도 관행적 규칙일 뿐 이 맥락에 맞는 근거는 '미확인'
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller

import config as C
import utils as U

log = C.get_logger("07_T5")
log.info("=== STEP 07 (T5): Granger 선후행 검정 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 일별 패널 읽기
# ------------------------------------------------------------------
daily = pd.read_csv(C.OUT_DIR / "panel_daily.csv", index_col="date", parse_dates=True)
LAGS = [1, 2, 3, 5, 10]


# ------------------------------------------------------------------
# [블록 2] Granger 검정 함수 (HC3 또는 HAC 강건 Wald)
#   effect(t) = c + Σ_{i=1..L} a_i·effect(t-i) + Σ_{i=1..L} b_i·cause(t-i) + e
#   귀무가설: b_1 = … = b_L = 0  (cause가 effect를 Granger-cause 하지 않음)
#   시차는 행 순서 기준 (결측일을 뺀 뒤 앞뒤 거래일이 이어 붙음 — 결측 7~8일)
#   cov="HC3": 이분산 강건만. cov="HAC": + 자기상관 강건(Newey-West, lag=utils.nw_maxlags)
#   검정통계량: Wald F (분자자유도=L, 분모자유도=n_obs−n_param)
# ------------------------------------------------------------------
def granger_test(d, cause, effect, L, cov="HC3", drop_idx=None):
    X = pd.concat({**{f"e{i}": d[effect].shift(i) for i in range(1, L + 1)},
                   **{f"c{i}": d[cause].shift(i) for i in range(1, L + 1)}}, axis=1)
    df = pd.concat([d[effect].rename("y"), X], axis=1).dropna()
    if drop_idx is not None:
        df = df[~df.index.isin(drop_idx)]
    if cov == "HAC":
        lag = U.nw_maxlags(len(df))
        m = sm.OLS(df["y"], sm.add_constant(df.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
    else:
        m = sm.OLS(df["y"], sm.add_constant(df.drop(columns="y"))).fit(cov_type=cov)
    names = list(m.params.index)
    R = np.zeros((L, len(names)))
    for j in range(L):
        R[j, names.index(f"c{j + 1}")] = 1
    w = m.wald_test(R, use_f=True, scalar=True)
    df_num, df_denom = L, int(m.nobs) - len(names)
    return float(w.statistic), float(w.pvalue), int(m.nobs), df_num, df_denom


main_rows, rob_rows = [], []
for h in [C.MAIN_HORIZON, C.AUX_HORIZON]:
    a, b = f"d_k_std_bp_h{h}", "d_move"
    d = daily[[a, b]]
    n_all = len(d)
    d = d.dropna()
    log.info(f"--- h={h}: {a} ↔ {b} | 사용 {len(d)}일 (결측 제거 {n_all - len(d)}일)")
    if len(d) < 50:
        log.warning("관측치 부족 → 건너뜀")
        continue

    # --------------------------------------------------------------
    # [블록 3] ADF 단위근 검정 (p<0.05면 정상)
    # --------------------------------------------------------------
    adf = {c: adfuller(d[c], autolag="AIC")[1] for c in (a, b)}
    for c, p in adf.items():
        log.info(f"    ADF {c}: p={p:.4f} {'(정상)' if p < C.ALPHA else '(비정상 의심)'}")

    # --------------------------------------------------------------
    # [블록 4] 주 결과: BIC 시차 + HC3·HAC 둘 다
    # --------------------------------------------------------------
    sel = VAR(d.values).select_order(maxlags=C.GRANGER_MAXLAG)
    lag = max(1, int(sel.bic))
    log.info(f"    선택 시차: BIC={sel.bic} (참고 AIC={sel.aic}, HQIC={sel.hqic}) → {lag}")
    for cause, effect in [(a, b), (b, a)]:
        for cov in ["HC3", "HAC"]:
            F, p, n, dfn, dfd = granger_test(d, cause, effect, lag, cov=cov)
            log.info(f"    [주,{cov}] {cause} → {effect}: 시차 {lag}, F({dfn},{dfd})={F:.3f}, "
                     f"p={p:.4f} {'★유의' if p < C.ALPHA else ''}")
            main_rows.append({"h": h, "cause": cause, "effect": effect, "lag": lag, "lag_rule": "BIC",
                              "cov": cov, "n": n, "df_num": dfn, "df_denom": dfd, "F": F, "p": p,
                              "adf_p_cause": adf[cause], "adf_p_effect": adf[effect]})

    # --------------------------------------------------------------
    # [블록 5] 견고성: 시차 민감도(HC3·HAC) / 연도 하나씩 빼기 / 윈저라이즈
    # --------------------------------------------------------------
    wins = d.copy()
    for c in wins:
        lo, hi = wins[c].quantile([0.01, 0.99])
        wins[c] = wins[c].clip(lo, hi)
    for cause, effect in [(a, b), (b, a)]:
        tag = f"{'Kalshi→MOVE' if cause == a else 'MOVE→Kalshi'}"
        for cov in ["HC3", "HAC"]:
            ps = []
            for L in LAGS:
                F, p, n, dfn, dfd = granger_test(d, cause, effect, L, cov=cov)
                ps.append(f"L{L}:{p:.3f}")
                rob_rows.append({"h": h, "cause": cause, "effect": effect, "check": "lag", "cov": cov, "lag": L,
                                 "detail": "", "n": n, "F": F, "p": p})
                F, p, n, dfn, dfd = granger_test(wins, cause, effect, L, cov=cov)
                rob_rows.append({"h": h, "cause": cause, "effect": effect, "check": "winsor1pct", "cov": cov,
                                 "lag": L, "detail": "", "n": n, "F": F, "p": p})
            log.info(f"    [시차 민감도,{cov}] {tag}: " + " ".join(ps))
            yp = []
            for y in sorted(set(d.index.year)):
                F, p, n, dfn, dfd = granger_test(d, cause, effect, lag, cov=cov, drop_idx=d.index[d.index.year == y])
                yp.append(f"{y}제외:{p:.3f}")
                rob_rows.append({"h": h, "cause": cause, "effect": effect, "check": "drop_year", "cov": cov,
                                 "lag": lag, "detail": str(y), "n": n, "F": F, "p": p})
            log.info(f"    [연도 제외,{cov}, 시차 {lag}] {tag}: " + " ".join(yp))

pd.DataFrame(main_rows).to_csv(C.OUT_DIR / "t5_granger.csv", index=False)
pd.DataFrame(rob_rows).to_csv(C.OUT_DIR / "t5_granger_robust.csv", index=False)
log.info("=== STEP 07 (T5) 완료 ===")
