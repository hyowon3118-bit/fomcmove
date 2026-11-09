"""
06_t1_comovement.py  —  T1. 일간 동조성 (Q1)
=======================================
[역할] Kalshi 분포 폭 변화가 2년물 변동성·MOVE 변화와 같은 날 함께 움직이는지 검정.
  변수: ΔKalshi std, ΔKalshi entropy  ↔  ΔMOVE, Δ2Y²
  방법: (1) 상관계수(피어슨·스피어만)  (2) OLS (차분 변수, A4)
  출력: outputs/<timing>/t1_corr.csv, t1_ols.csv
※ T1 표준오차 방식은 계획서에 지정 없음 → 다른 검정과 같은 HC3 사용
"""
import pandas as pd
from scipy import stats

import config as C
import utils as U

log = C.get_logger("06_T1")
log.info("=== STEP 06 (T1): 일간 동조성 검정 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 일별 패널 읽기
# ------------------------------------------------------------------
daily = pd.read_csv(C.OUT_DIR / "panel_daily.csv", index_col="date", parse_dates=True)
HS = sorted({C.AUX_HORIZON, C.MAIN_HORIZON})

# ------------------------------------------------------------------
# [블록 2] 상관분석: Kalshi 변화 × (ΔMOVE, Δ2Y²)
# ------------------------------------------------------------------
corr_rows = []
for h in HS:
    for kx in [f"d_k_std_bp_h{h}", f"d_k_entropy_h{h}"]:
        if kx not in daily:
            continue
        for y in ["d_move", "d2y_sq"]:
            d = daily[[kx, y]].dropna()
            r, p = stats.pearsonr(d[kx], d[y])
            rho, ps = stats.spearmanr(d[kx], d[y])
            corr_rows.append({"h": h, "x": kx, "y": y, "n": len(d),
                              "pearson": r, "p_pearson": p, "spearman": rho, "p_spearman": ps})
            log.info(f"h={h} {kx:<20} vs {y:<7} n={len(d)} 피어슨={r:.3f}(p={p:.3f}) 스피어만={rho:.3f}(p={ps:.3f})")
corr = pd.DataFrame(corr_rows)
corr.to_csv(C.OUT_DIR / "t1_corr.csv", index=False)

# ------------------------------------------------------------------
# [블록 3] OLS: ΔMOVE, Δ2Y² 를 Kalshi 변화에 회귀
#   FOMC 당일은 불확실성이 기계적으로 크게 줄어드는 날(A2)이라
#   전체 표본 / FOMC 당일 제외 표본 두 가지로 실행
# ------------------------------------------------------------------
ols_rows = []
for h in HS:
    for kx in [f"d_k_std_bp_h{h}", f"d_k_entropy_h{h}"]:
        if kx not in daily:
            continue
        for y in ["d_move", "d2y_sq"]:
            for tag, df in [("all", daily), ("exFOMC", daily[~daily["is_fomc"]])]:
                _, rows = U.run_ols(df, y, [kx], f"T1 h{h} {y}~{kx} [{tag}]", logger=log)
                ols_rows.append(rows.assign(sample=tag, h=h))
pd.concat(ols_rows).to_csv(C.OUT_DIR / "t1_ols.csv", index=False)

# ------------------------------------------------------------------
# [블록 4] 추가 사양 (계획서 외, 팀 결정으로 추가): |ΔKalshi| ~ Δ2Y²
#   이유: 금리가 크게 움직인 날 Kalshi 폭이 줄기도(뉴스로 불확실성 해소)
#         늘기도 해서, 부호 있는 ΔKalshi로는 효과가 상쇄됨.
#         Δ2Y²는 항상 양수(움직임 크기)이므로 Kalshi도 변화 '크기'로 비교
#   방법: 상관(피어슨·스피어만) + OLS(HC3), 종속변수 Δ2Y², 설명변수 |ΔKalshi|
#   출력: outputs/<timing>/t1_abs.csv
# ------------------------------------------------------------------
log.info("--- 추가 사양: |ΔKalshi| ~ Δ2Y² ---")
abs_rows = []
for h in HS:
    for v in ["std_bp", "entropy"]:
        kx = f"d_k_{v}_h{h}"
        if kx not in daily:
            continue
        ax = f"abs_{kx}"
        daily[ax] = daily[kx].abs()
        d = daily[[ax, "d2y_sq"]].dropna()

        # 상관
        r, p = stats.pearsonr(d[ax], d["d2y_sq"])
        rho, ps = stats.spearmanr(d[ax], d["d2y_sq"])
        log.info(f"h={h} {ax:<24} vs d2y_sq n={len(d)} 피어슨={r:.3f}(p={p:.3f}) 스피어만={rho:.3f}(p={ps:.3f})")

        # OLS (HC3)
        _, rows = U.run_ols(daily, "d2y_sq", [ax], f"T1abs h{h} d2y_sq~{ax}", logger=log)
        abs_rows.append(rows.assign(h=h, pearson=r, p_pearson=p, spearman=rho, p_spearman=ps))

        # 판단
        rr = rows[rows["var"] == ax]
        b, pb = rr["coef"].iloc[0], rr["p"].iloc[0]
        ok = (b > 0) and (pb < C.ALPHA)
        log.info(f"[판단] h={h} |Δ{v}|: b={b:.3f}, p={pb:.4f} → {'b>0 & 유의 (크기가 함께 움직임)' if ok else '기준 미충족'}")

pd.concat(abs_rows).to_csv(C.OUT_DIR / "t1_abs.csv", index=False)
log.info("=== STEP 06 (T1) 완료 ===")
