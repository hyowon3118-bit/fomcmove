# 02_get_move.py
# [역할] Yahoo Finance에서 MOVE 지수(^MOVE) 일별 종가를 받아 MOVE.csv(Date, Close)로 저장
# 설치: pip3 install yfinance
import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- 다운로드: 2021-12부터 현재까지 ---
logging.info("^MOVE 다운로드 시작")
df = yf.download("^MOVE", start="2021-12-01", progress=False, auto_adjust=False)
if df.empty:
    raise SystemExit("데이터 없음 — 티커나 네트워크 확인 필요")

# --- 컬럼 정리: 여러 단 컬럼이면 한 단으로 → Date, Close만 남김 ---
if df.columns.nlevels > 1:
    df.columns = df.columns.get_level_values(0)
out = df[["Close"]].reset_index()[["Date", "Close"]]

# --- 저장 ---
out.to_csv("MOVE.csv", index=False)
logging.info(f"MOVE.csv 저장: {len(out)}행, {out['Date'].min().date()} ~ {out['Date'].max().date()}")