# Kalshi FOMC 확률분포와 미 국채 금리 변동성: 연구계획 (확정본 v2)

- 소속: FIXERS 2026 Fall 메인세션 리서치 B팀
- 계획서 4장 II-3) 질문 2 "예측시장 계약의 확률분포는 우리에게 무엇을 말해주는가?"의 세부 설계
- 작성일: 2026-11-03 (v2: FedWatch를 pyfedwatch 재현값으로 대체)

---

## 1. 연구 질문

| # | 질문 | 내용 |
|---|---|---|
| Q1 | 같이 움직이나 | Kalshi 분포 폭(표준편차·엔트로피)의 변화가 2년물 변동성·MOVE의 변화와 함께 움직이는가? |
| Q2 | 미리 알려주나 | FOMC 직전 분포 폭이 넓을수록 FOMC 당일 2년물 금리가 크게 움직이는가? |
| Q3 | 추가 정보가 있나 | FedWatch(연방기금선물)와 MOVE를 통제해도 Kalshi 분포가 2년물 변동을 추가로 설명하는가? |
| Q4 | 불확실성이 충격 효과를 약화시키나 | Kalshi로 측정한 불확실성이 높을 때 통화정책 충격이 2년물에 미치는 효과가 약해지는가? |

> CME FedWatch 공식 과거 데이터는 최근 1년치만 확보 가능 → **pyfedwatch로 연방기금선물 가격에서 FedWatch 확률을 재계산**해 전 기간에 사용. 확보한 1년치 공식 데이터는 재현 정확도 검증(T0)에 사용.

---

## 2. 사용하는 데이터

| # | 데이터 | 용도 | 출처 | 상태 |
|---|---|---|---|---|
| 1 | Kalshi FOMC 확률분포·모멘트 (일별) | 설명변수: `std_bp`, `entropy`, 왜도, 첨도 | 연준 원본 R 코드로 직접 생성 (`outputs/`) | 확보 |
| 2 | FOMC 회의 일정 (2021~2027) | 계약–회의 매칭, D-n 계산, pyfedwatch 입력 | [Federal Reserve FOMC 캘린더](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) (pyfedwatch `get_fomc_data_fed()`로 수집 가능) | pyfedwatch 샘플은 2024-12-18까지만 포함 → 2025~2026 추가 필요 |
| 3 | 2년물 국채 금리 일별 (DGS2) | Δ2Y, 향후 21거래일 실현변동성 | [FRED DGS2](https://fred.stlouisfed.org/series/DGS2) | 무료, 수집 필요 |
| 4 | MOVE 지수 일별 | 통제변수, Q1·Q3 비교 대상 | ICE 공식(유료) / Yahoo Finance `^MOVE`·TradingView 등 2차 출처 | 무료 출처의 정확도 확인 필요 |
| 5 | SF Fed USMPD | FOMC 발표 구간(30·70분) 2년물 변화, 통화정책 충격 | [SF Fed U.S. Monetary Policy Event-Study Database](https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/) | 무료 (2026-09-17 업데이트), 수집 필요 |
| 6 | **30일 연방기금선물(ZQ) 월물별 일별 종가** | pyfedwatch 입력 → FedWatch 확률 재계산 | 후보: Yahoo Finance 개별 월물(`ZQ{월코드}{YY}.CBT`, 예: `ZQZ25.CBT`) / [Barchart 가격 이력](https://www.barchart.com/futures/quotes/ZQJ25/price-history/historical) / CME DataMine(유료) | **출처 미확정**. 만기 지난 월물 이력 제공 여부·다운로드 유료 여부 미확인. pyfedwatch 저장소 샘플은 2023-09-15까지만 있음 |
| 7 | **연방기금 목표범위 하단·상단 (DFEDTARL, DFEDTARU)** | pyfedwatch 기준 금리범위(`watch_rate_range`) | [FRED DFEDTARL](https://fred.stlouisfed.org/series/DFEDTARL), [FRED DFEDTARU](https://fred.stlouisfed.org/series/DFEDTARU) | 무료, 수집 필요 |
| 8 | CME FedWatch 공식 과거 확률 (최근 1년) | pyfedwatch 재현 검증(T0) | [CME FedWatch](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) | 확보 가능 (1년치) |
| 9 | (선택) VIX 일별 | 금융시장 전반 변동성 통제 | [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) | 무료 |

### ZQ 데이터 필요 범위
- watch date(관측일)마다 pyfedwatch는 "직전 비FOMC 월 ~ 앞으로 N번째 회의 다음 월"의 월물이 필요함 (`fomc.py`의 계약 목록 생성 로직).
- Kalshi 표본 2022-01 ~ 2026-10, 2~3개 회의 앞까지 보면 **대략 ZQ 2021-12물 ~ 2027년 상반기물**이 필요. 정확한 목록은 pyfedwatch `FOMC(...).contract_list`로 산출.
- 형식: 월물별로 `Date` 인덱스와 `Close` 컬럼 필수 (pyfedwatch `get_fff_history` 검사 조건).

### 변수 구성 규칙
- Kalshi: 가장 가까운 FOMC 회의 계약을 쓰고 D-n(회의까지 남은 일수)으로 정렬. FOMC 당일 전후 변화는 **1개월 이상 남은 회의 계약** 사용 (DKW Table 5 방식).
- FedWatch: **Kalshi와 같은 회의**의 목표범위별 확률을 사용. 범위 중간값으로 평균·표준편차 계산.
- 이벤트 스터디 설명변수는 **회의 전날(D-1) 종가 기준**.
- Kalshi와 FedWatch는 금리 표기 기준(행사가 vs 목표범위)이 다를 수 있으나, 25bp 격자에서 상수만큼 평행이동한 차이라면 **표준편차는 영향받지 않음**(분산의 이동 불변성). 평균을 비교할 때만 Kalshi 계약 규정 확인 필요.

---

## 3. 가정

| # | 가정 | 근거 |
|---|---|---|
| A1 | Kalshi 분포의 분산(폭)은 금리 경로에 대한 시장 불확실성을 나타낸다 | Diercks, Katz & Wright (2026), *Kalshi and the Rise of Macro Markets*: 뉴스 발표 시 분산 감소(불확실성 해소) 확인 (프로젝트 파일) |
| A2 | 파생상품으로 측정한 정책 불확실성은 FOMC 당일 크게 줄고 이후 2주간 다시 오른다 → D-n 정렬 필요 | [Bauer, Lakdawala & Mueller (2022), *Market-Based Monetary Policy Uncertainty*](https://econpapers.repec.org/paper/fipfedfwp/2019-12.htm) |
| A3 | 불확실성이 높을 때 통화정책 충격의 자산가격 효과는 작다 (Q4의 근거) | [Bauer, Lakdawala & Mueller (2022)](https://econpapers.repec.org/paper/fipfedfwp/2019-12.htm): "at high levels of uncertainty a monetary policy surprise has only modest effects on assets" |
| A4 | 수준끼리의 회귀는 허구적 상관 위험이 있으므로 변화(차분)로 분석한다 | [Granger & Newbold (1974), *Spurious Regressions in Econometrics*](https://gwern.net/doc/economics/1974-granger.pdf) |
| A5 | 2년물 금리는 통화정책 뉴스를 대표하는 금리다 → 주 종속변수 | [Hanson & Stein (2015), *Monetary Policy and Long-Term Real Rates*](https://www.federalreserve.gov/econres/feds/monetary-policy-and-long-term-real-rates.htm) |
| A6 | MOVE는 2·5·10·30년물 1개월 옵션 바스켓이라 단기 금리 전용 지표가 아니다 → 보조 변수 | [ICE (2019) MOVE 인수 보도자료](https://ir.theice.com/press/news-details/2019/Intercontinental-Exchange-Completes-Acquisition-of-the-Merrill-Lynch-Option-Volatility-Estimate-MOVE-Index-from-Bank-of-America-Merrill-Lynch/default.aspx) |
| A7 | 내재변동성(MOVE, 1개월)은 같은 기간의 **향후** 실현변동성(21거래일)과 비교하고, 표본은 겹치지 않게 뽑는다 | [Christensen & Prabhala (1998)](https://academicnewsletter.sufe.edu.cn/info/358008); [Baruník & Hlínková (2016)](https://library.utia.cas.cz/separaty/2016/E/barunik-0456186.pdf) |
| A8 | FOMC 발표 전후 짧은 구간의 금리 변화로 정책 효과를 식별할 수 있다 | [Kuttner (2001)](https://ideas.repec.org/a/eee/moneco/v47y2001i3p523-544.html); [Acosta et al. (2025) / SF Fed USMPD](https://www.frbsf.org/wp-content/uploads/wp2025-30.pdf) |
| A9 | 일별 Kalshi 분포 변화를 고빈도(30·70분) 정책 충격에 회귀할 수 있다 | Diercks, Katz & Wright (2026), Table 5 ("end of previous day to end of release day", USMPD 충격 사용) |
| A10 | 일간 \|Δ2Y\| 또는 Δ2Y²는 변동성의 대용치다 (잡음이 크다는 한계 있음) | [Andersen & Bollerslev (1998), *Answering the Skeptics*](https://ideas.repec.org/a/ier/iecrev/v39y1998i4p885-905.html) |
| A11 | 꼬리 위험은 왜도·첨도로 측정한다 (±50bp 꼬리확률은 근거가 없어 제외) | Diercks, Katz & Wright (2026): 모멘트 분석에 왜도·첨도 사용 |
| A12 | FedWatch 확률은 30일 연방기금선물 가격으로 계산하며, 금리 변경은 25bp 배수이고 회의마다 **두 가지 결과(이진 트리)**만 가정한다 | [CME, *Understanding the CME Group FedWatch Tool Methodology*](https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html): "the size of a rate change is always in multiples of 25 basis points", "binary probability tree" |
| A13 | 이진 트리 때문에 **가장 가까운 회의**의 FedWatch 분포는 결과가 최대 2개 → 표준편차가 25bp·√(p(1−p)) ≤ 12.5bp로 기계적으로 제한됨. 따라서 FedWatch 통제변수는 2번째 이후 회의(누적 트리로 결과가 늘어남)에서 더 의미 있음 | A12에서 수학적으로 도출 (별도 문헌 미확인). 1개월 이상 남은 회의를 쓰는 DKW Table 5 방식과도 일치 |
| A14 | pyfedwatch는 CME FedWatch와 같은 확률을 산출한다 | [pyfedwatch README](https://github.com/ARahimiQuant/pyfedwatch): "provides the same probabilities as the tool displayed on the website" (작성자 주장, 독립 검증 아님 → T0에서 직접 검증) |

---

## 4. 검정 방법

### T0. pyfedwatch 재현 검증 (사전 단계)
- 비교: pyfedwatch 계산 확률 vs CME FedWatch 공식 과거 확률 (최근 1년, 같은 관측일·같은 회의)
- 지표: 목표범위별 확률의 최대 절대오차, 평균 절대오차
- 판단: 오차가 작으면 전 기간(2022~)에 pyfedwatch 값을 FedWatch로 사용. 크면 원인(ZQ 가격 출처, 종가 vs 정산가, 휴일 처리 등)부터 점검
- 허용 오차 기준: 미정 (근거 문헌 없음, 결과를 보고 팀 합의로 결정)

### T1. 일간 동조성 (Q1)
- 변수: ΔKalshi std, ΔKalshi entropy ↔ ΔMOVE, Δ2Y²
- 방법: 상관분석 및 OLS 회귀 (차분 변수, A4)

### T2. MOVE와의 예측력 비교 (Q1·Q3)
- 표본: 월 단위로 겹치지 않게 추출 (A7)
- 종속변수: t+1 ~ t+21거래일 2년물 실현변동성
- 식: `RV_2Y(t, t+21) = a + b·KalshiStd(t) + c·MOVE(t) + d·FedWatchStd(t) + e`
- 판단: MOVE·FedWatch를 통제한 뒤에도 b가 유의하면 Kalshi가 추가 정보를 가짐

### T3. FOMC 이벤트 스터디 (Q2·Q3)
- 종속변수: USMPD FOMC 발표 구간 2년물 변화 절댓값 |ΔUST2Y_FOMC|
- 식: `|ΔUST2Y_FOMC| = a + b·KalshiStd(D-1) + c·MOVE(D-1) + d·FedWatchStd(D-1) + e`
- KalshiStd·FedWatchStd는 같은 회의 기준. A13 때문에 주 분석은 2번째 회의, 가장 가까운 회의는 보조 분석
- 판단: b > 0 이고 유의하면 사전 분포 폭이 실제 금리 변동을 예고하며, d를 통제한 뒤에도 유의하면 선물시장 이상의 정보
- 표준오차: HC3 강건 표준오차 (DKW와 동일)

### T4. 불확실성 × 충격 상호작용 (Q4)
- 식: `ΔUST2Y_FOMC = a + b·Shock + c·(Shock × KalshiStd(D-1)) + d·KalshiStd(D-1) + e`
- Shock: USMPD 통화정책 충격
- 판단: c < 0 이고 유의하면 BLM(2022) 결과를 Kalshi로 재현

### T5. 선후행 관계 (Q1)
- 방법: Granger 인과 검정 ([Granger, 1969](https://www.econometricsociety.org/publications/econometrica/1969/08/01/investigating-causal-relations-econometric-models-and-cross))
- 방향: ΔKalshi std ↔ ΔMOVE, ΔKalshi std ↔ ΔFedWatch std (양방향)
- 시차: 정보기준(AIC 등)으로 선택 (이 관행의 근거 문헌은 미확인)
- 구현: Python `statsmodels.tsa.stattools.grangercausalitytests`
- 해석 주의: 예측 선후관계일 뿐 실제 인과는 아님

---

## 5. 실행 환경 메모 (pyfedwatch)

2026-11-03 테스트 결과:
- `pip install pyfedwatch`만 하면 **import 단계에서 실패**함 (의존 패키지 `pandas_datareader` 0.10.0이 pandas 3.x, Python 3.12+와 호환되지 않음).
- **pandas 2.2.3 + setuptools**를 함께 설치하면 정상 동작. 저장소 샘플 데이터로 2023-03-10 관측일 계산 성공.
- 실행 시 `watch_rate_range=(하단, 상단)`을 직접 넘기면 내부 FRED 호출(pandas_datareader)을 피할 수 있음 → 데이터 7번(DFEDTARL/U)을 미리 받아서 넘김.

맥 기준 설치:
```bash
python3 -m venv venv_fw
source venv_fw/bin/activate
pip3 install "pandas==2.2.3" setuptools pyfedwatch
```

---

## 6. 한계

- FOMC는 연 8회 → 2022년 이후 이벤트 표본 약 40개 내외로 작음.
- MOVE에 장기물이 포함되어 FOMC 효과가 희석될 수 있음 (A6).
- Kalshi 분포는 **회의 후 금리 수준**의 분포로, 회의별 금리 **변화** 분포와 다름.
- FedWatch는 이진 트리 가정 때문에 가장 가까운 회의의 분포 폭이 기계적으로 제한됨 (A13).
- **ZQ 월물 가격 출처 미확정** → 확보 실패 시 Q3의 FedWatch 통제가 불가능해져 v1(FedWatch 제외)으로 돌아감.
- MOVE 무료 출처의 정확도 미확인.
