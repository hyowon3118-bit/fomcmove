"""
02_t0_validate_fedwatch.py  —  T0. pyfedwatch 재현 검증
=======================================================
[역할] pyfedwatch 재계산 확률 vs CME FedWatch 공식 과거 확률(최근 1년)을
       같은 관측일·같은 회의·같은 목표범위끼리 맞춰 오차 계산.
  지표: 최대 절대오차, 평균 절대오차 (전체 / 회의 순번 h별 / 월별)
  출력: outputs_verify/t0_errors_detail.csv, t0_summary.csv
※ 허용 오차 기준은 계획서상 '미정' → 코드는 수치만 보고, 판정은 팀 합의로.
"""
import pandas as pd

import config as C
import utils as U

log = C.get_logger("02_T0")
log.info("=== STEP 02 (T0): pyfedwatch 재현 검증 시작 ===")

# ------------------------------------------------------------------
# [블록 1] 두 확률 자료 읽기
#   CME 공식 확률이 0~100 단위면 0~1로 변환
#   목표범위 하단은 소수 둘째 자리로 반올림해서 매칭 키로 사용
# ------------------------------------------------------------------
fomc_dates = U.load_fomc_dates()
pyfw = pd.read_csv(C.OUT_DIR / "fedwatch_probs_long.csv", parse_dates=["watch_date", "meeting"])

cme_raw = pd.read_csv(C.FILES["cme_fw"])
cme = cme_raw.rename(columns={v: k for k, v in C.CME_FW_COLS.items()})[list(C.CME_FW_COLS)]
cme["watch_date"] = pd.to_datetime(cme["watch_date"])
cme["meeting"] = pd.to_datetime(cme["meeting"])
if cme["prob"].max() > 1.5:
    log.info("CME 확률이 % 단위로 판단 → 100으로 나눔")
    cme["prob"] = cme["prob"] / 100

for d in (pyfw, cme):
    d["range_low"] = d["range_low"].round(2)
log.info(f"pyfedwatch {len(pyfw):,}행 / CME 공식 {len(cme):,}행")

# ------------------------------------------------------------------
# [블록 2] 매칭
#   outer join: 한쪽에만 있는 범위는 확률 0으로 간주 (누락된 범위도 오차에 반영)
#   단, 두 자료가 공통으로 가진 (관측일, 회의) 조합만 비교
# ------------------------------------------------------------------
keys = ["watch_date", "meeting"]
common = pyfw[keys].drop_duplicates().merge(cme[keys].drop_duplicates(), on=keys)
log.info(f"공통 (관측일, 회의) 조합: {len(common):,}개")
if common.empty:
    raise SystemExit("겹치는 관측일·회의가 없음. 날짜 형식/회의일 표기 확인 필요")

m = (pyfw.merge(common, on=keys)[keys + ["range_low", "prob"]]
       .merge(cme.merge(common, on=keys), on=keys + ["range_low"], how="outer",
              suffixes=("_py", "_cme")))
m[["prob_py", "prob_cme"]] = m[["prob_py", "prob_cme"]].fillna(0.0)
m["abs_err"] = (m["prob_py"] - m["prob_cme"]).abs()
m["h"] = U.meeting_horizon(m["watch_date"], m["meeting"], fomc_dates)
m.to_csv(C.OUT_DIR / "t0_errors_detail.csv", index=False)

# ------------------------------------------------------------------
# [블록 3] 오차 요약 (전체 / h별 / 월별)
# ------------------------------------------------------------------
def summ(g):
    return pd.Series({"n": len(g), "MAE": g["abs_err"].mean(), "MaxAE": g["abs_err"].max()})

overall = summ(m).to_frame("전체").T
by_h = m.groupby("h").apply(summ)
by_h.index = [f"h={i}" for i in by_h.index]
by_month = m.groupby(m["watch_date"].dt.to_period("M")).apply(summ)
by_month.index = by_month.index.astype(str)
summary = pd.concat([overall, by_h, by_month])
summary.to_csv(C.OUT_DIR / "t0_summary.csv")

log.info(f"전체: MAE={overall['MAE'].iloc[0]:.4f}, MaxAE={overall['MaxAE'].iloc[0]:.4f}")
for idx, r in by_h.iterrows():
    log.info(f"  {idx}: n={int(r['n'])}, MAE={r['MAE']:.4f}, MaxAE={r['MaxAE']:.4f}")

# ------------------------------------------------------------------
# [블록 4] 오차 큰 사례 상위 10개 출력 → 원인 점검용
#   (계획서: ZQ 가격 출처, 종가 vs 정산가, 휴일 처리 등)
# ------------------------------------------------------------------
worst = m.sort_values("abs_err", ascending=False).head(10)
log.info("오차 상위 10건:\n" + worst.to_string(index=False))
log.info("=== STEP 02 (T0) 완료: 허용 기준은 팀 합의로 결정 ===")
