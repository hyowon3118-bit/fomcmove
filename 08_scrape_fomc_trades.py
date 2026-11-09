"""
08_scrape_fomc_trades.py
========================
[역할] Kalshi 연방기금금리 수준 계약(KXFED + 구 FED-)의 체결(trade) 내역을 전부 받아
       체결 단위 CSV(trade_level_data_fed_levels.csv)로 저장.
       → 09_build_kalshi_daily_et.py가 이 파일로 '동부시간 오후 4시 기준' 일별 가격을 만듦.

방식은 원저자 수집 코드와 같음 (github.com/jdkatz21/Prediction_Markets_Public)
  - 티커 목록: tickers.autogenerate_kalshi_tickers('KXFED') + 구 FED- 목록(get_tickers('fed_levels'))
               + 'FED' 시리즈 자동 생성(있으면)
  - 티커마다 /historical/trades 와 /markets/trades 두 곳에서 받아 합치고 trade_id로 중복 제거
    (2026-04 Kalshi가 과거·최근 체결을 두 엔드포인트로 나눔: clients_kalshi.get_all_trades_for_ticker)
  - 인증 없이 요청 (Kalshi 문서상 체결 조회는 공개 엔드포인트)

실행 (맥 터미널, Kalshi 접속 가능한 곳에서):
    pip3 install requests pandas
    python3 08_scrape_fomc_trades.py                 # 전체
    python3 08_scrape_fomc_trades.py --limit 5       # 티커 5개만 시험
  - 중간에 끊겨도 다시 실행하면 이미 받은 티커는 건너뜀 (trades_fomc/ 폴더에 티커별 파일)
  - 출력: DATA_DIR/trades_fomc/<티커>.csv, DATA_DIR/trade_level_data_fed_levels.csv
"""
import argparse
import time

import pandas as pd
import requests

import config as C
import kalshi_tickers_upstream as upstream

log = C.get_logger("08_scrape")
BASE = "https://api.elections.kalshi.com/trade-api/v2"
RAW_DIR = C.DATA_DIR / "trades_fomc"
RAW_DIR.mkdir(exist_ok=True)
OUT = C.DATA_DIR / "trade_level_data_fed_levels.csv"

# ------------------------------------------------------------------
# [블록 1] HTTP 요청: 429(요청 과다)·5xx는 기다렸다가 재시도
# ------------------------------------------------------------------
session = requests.Session()


def get_json(path, params, tries=6):
    for i in range(tries):
        r = session.get(BASE + path, params=params, timeout=30)
        if r.status_code == 404:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            wait = 2 ** i
            log.warning(f"    {r.status_code} → {wait}초 후 재시도 ({i + 1}/{tries})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"요청 실패: {path} {params}")


def paginate_trades(path, ticker):
    rows, cursor, page = [], None, 0
    while True:
        params = {"ticker": ticker, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = get_json(path, params)
        if data is None:
            break
        rows.extend(data.get("trades", []))
        cursor = data.get("cursor")
        page += 1
        time.sleep(0.1)
        if not cursor:
            break
    return rows, page


# ------------------------------------------------------------------
# [블록 2] 티커 목록 만들기
# ------------------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=None, help="앞에서부터 티커 N개만 (시험용)")
args = ap.parse_args()

log.info("=== STEP 08: Kalshi FOMC 체결 데이터 수집 시작 ===")
log.info("[1/3] 티커 목록 만드는 중...")
tickers = set(upstream.get_tickers("fed_levels"))
log.info(f"  구 FED- 목록(원저자 tickers.py): {len(tickers)}개")
for series in ["KXFED", "FED"]:
    try:
        found = upstream.autogenerate_kalshi_tickers(series)
        log.info(f"  {series} 시리즈 자동 생성: {len(found)}개")
        tickers.update(found)
    except Exception as e:
        log.warning(f"  {series} 시리즈 자동 생성 실패 → 건너뜀: {e}")
tickers = sorted(t for t in tickers if "-T" in t)        # 'X% 초과' threshold 계약만 (R 코드의 strike 추출 규칙)
if args.limit:
    tickers = tickers[: args.limit]
pd.Series(tickers, name="ticker").to_csv(RAW_DIR / "_ticker_list.csv", index=False)
log.info(f"  최종 {len(tickers)}개 티커 → {RAW_DIR / '_ticker_list.csv'}")

# ------------------------------------------------------------------
# [블록 3] 티커별 체결 다운로드 (이미 받은 티커는 건너뜀)
# ------------------------------------------------------------------
log.info("[2/3] 티커별 체결 다운로드")
t0, n_new, n_empty, n_fail = time.time(), 0, 0, 0
for i, tk in enumerate(tickers, 1):
    f = RAW_DIR / f"{tk}.csv"
    if f.exists():
        continue
    try:
        hist, ph = paginate_trades("/historical/trades", tk)
        live, pl = paginate_trades("/markets/trades", tk)
    except Exception as e:
        n_fail += 1
        log.error(f"  [{i}/{len(tickers)}] {tk} 실패 → 다음 실행 때 다시 시도: {e}")
        continue
    df = pd.DataFrame(hist + live)
    if not df.empty:
        df = df.drop_duplicates("trade_id").sort_values("created_time")
    else:
        n_empty += 1
    df.to_csv(f, index=False)                              # 빈 파일도 저장 (재실행 때 건너뛰기용)
    n_new += 1
    log.info(f"  [{i}/{len(tickers)}] {tk}: 과거 {len(hist):,}건({ph}쪽) + 최근 {len(live):,}건({pl}쪽) "
             f"→ {len(df):,}건 | 경과 {(time.time() - t0) / 60:.1f}분")
log.info(f"  새로 받음 {n_new}개 (체결 없음 {n_empty}개), 실패 {n_fail}개")

# ------------------------------------------------------------------
# [블록 4] 티커별 파일 합쳐서 저장 (R 원본 입력과 같은 형식)
# ------------------------------------------------------------------
log.info("[3/3] 합치는 중...")
parts = []
for tk in tickers:
    f = RAW_DIR / f"{tk}.csv"
    if f.exists() and f.stat().st_size > 1:
        try:
            parts.append(pd.read_csv(f))
        except pd.errors.EmptyDataError:
            pass
allt = pd.concat(parts, ignore_index=True).drop_duplicates("trade_id").sort_values(["ticker", "created_time"])
allt.to_csv(OUT, index=False)
log.info(f"  저장: {OUT} ({len(allt):,}건, 티커 {allt['ticker'].nunique()}개, "
         f"{allt['created_time'].min()} ~ {allt['created_time'].max()})")
log.info(f"  컬럼: {list(allt.columns)}")
if n_fail:
    log.warning(f"실패한 티커 {n_fail}개 있음 → 이 스크립트를 한 번 더 실행하면 그것만 다시 받음")
log.info("=== STEP 08 완료 ===")
