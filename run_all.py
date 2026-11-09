"""
run_all.py
==========
[역할] 00 → 08 단계를 순서대로 실행. 단계마다 시작/종료/소요시간 로그 출력.
  사용법:
    python run_all.py              # 전체 실행
    python run_all.py --from 03    # 03단계부터 실행 (앞 단계 결과 파일이 있을 때)
    python run_all.py --only 06    # 06단계만 실행
  CME 공식 확률 파일이 없으면 T0(02단계)는 자동으로 건너뜀
"""
import argparse
import runpy
import sys
import time

import config as C

log = C.get_logger("run_all")

# ------------------------------------------------------------------
# [블록 1] 실행 순서 정의
# ------------------------------------------------------------------
STEPS = [
    ("00", "00a_build_kalshi_moments.py", "Kalshi 확률분포 → 모멘트 변환"),
    ("00", "00_inspect_data.py",          "입력 파일 점검"),
    ("01", "01_build_fedwatch.py",        "pyfedwatch 확률 재계산"),
    ("02", "02_t0_validate_fedwatch.py",  "T0 재현 검증"),
    ("03", "03_build_panels.py",          "분석 패널 생성"),
    ("04", "04_t1_comovement.py",         "T1 일간 동조성"),
    ("05", "05_t2_forecast_rv.py",        "T2 예측력 비교"),
    ("06", "06_t3_event_study.py",        "T3 이벤트 스터디"),
    ("07", "07_t4_interaction.py",        "T4 상호작용"),
    ("08", "08_t5_granger.py",            "T5 Granger"),
]

# ------------------------------------------------------------------
# [블록 2] 실행 범위 인자 처리
# ------------------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="start", default="00")
ap.add_argument("--only", default=None)
args = ap.parse_args()
todo = [s for s in STEPS if (s[0] == args.only if args.only else s[0] >= args.start)]

# ------------------------------------------------------------------
# [블록 3] 단계별 실행 — 에러 나면 어느 단계에서 멈췄는지 기록 후 종료
# ------------------------------------------------------------------
t_all = time.time()
for i, (num, script, desc) in enumerate(todo, 1):
    if num in ("01", "02") and not C.USE_FEDWATCH:
        log.info(f"[{i}/{len(todo)}] {num} {desc}: USE_FEDWATCH=False → 건너뜀")
        continue
    if num == "02" and not C.FILES["cme_fw"].exists():
        log.warning(f"[{i}/{len(todo)}] {num} {desc}: CME 공식 확률 파일 없음 → 건너뜀")
        continue
    log.info(f"[{i}/{len(todo)}] ▶ {num} {desc} 시작")
    t0 = time.time()
    try:
        runpy.run_path(str(C.ROOT / script), run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            log.error(f"{num} {desc} 중단: {e.code}")
            sys.exit(1)
    except Exception:
        log.exception(f"{num} {desc} 에러 → 파이프라인 중단")
        sys.exit(1)
    log.info(f"[{i}/{len(todo)}] ✔ {num} 완료 ({time.time() - t0:.1f}초)")

log.info(f"전체 완료 ({time.time() - t_all:.1f}초). 결과: {C.OUT_DIR}")
