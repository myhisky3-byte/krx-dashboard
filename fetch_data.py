"""
yfinance 기반 한국 주식 데이터 수집
GitHub Actions에서 매일 자동 실행
"""

import json
import time
import yfinance as yf
from datetime import datetime, timedelta
import os
import warnings
warnings.filterwarnings('ignore')

def get_last_trading_day():
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

TRADING_DAY = get_last_trading_day()

def safe_float(val, default=None):
    try:
        v = float(val)
        return round(v, 2) if v and v == v else default  # nan 체크
    except:
        return default

# ── 주요 종목 목록 ─────────────────────────────────
KOSPI_STOCKS = [
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    ("005380.KS", "현대차"),
    ("000270.KS", "기아"),
    ("051910.KS", "LG화학"),
    ("006400.KS", "삼성SDI"),
    ("028260.KS", "삼성물산"),
    ("005490.KS", "POSCO홀딩스"),
    ("373220.KS", "LG에너지솔루션"),
    ("207940.KS", "삼성바이오로직스"),
    ("105560.KS", "KB금융"),
    ("055550.KS", "신한지주"),
    ("086790.KS", "하나금융지주"),
    ("003550.KS", "LG"),
    ("012330.KS", "현대모비스"),
    ("015760.KS", "한국전력"),
    ("034020.KS", "두산에너빌리티"),
    ("066570.KS", "LG전자"),
    ("032830.KS", "삼성생명"),
    ("018260.KS", "삼성에스디에스"),
    ("009150.KS", "삼성전기"),
    ("011200.KS", "HMM"),
    ("010950.KS", "S-Oil"),
    ("003490.KS", "대한항공"),
    ("017670.KS", "SK텔레콤"),
    ("030200.KS", "KT"),
    ("036570.KS", "엔씨소프트"),
    ("000100.KS", "유한양행"),
    ("002380.KS", "KCC"),
    ("004020.KS", "현대제철"),
]

KOSDAQ_STOCKS = [
    ("035420.KQ", "NAVER"),
    ("035720.KQ", "카카오"),
    ("068270.KQ", "셀트리온"),
    ("251270.KQ", "넷마블"),
    ("011070.KQ", "LG이노텍"),
    ("042660.KQ", "한화오션"),
    ("009830.KQ", "한화솔루션"),
    ("016360.KQ", "삼성증권"),
    ("021240.KQ", "코웨이"),
    ("011780.KQ", "금호석유"),
    ("047810.KQ", "한국항공우주"),
    ("010130.KQ", "고려아연"),
    ("000810.KQ", "삼성화재"),
    ("139480.KQ", "이마트"),
    ("326030.KQ", "SK바이오팜"),
    ("034730.KQ", "SK"),
    ("018880.KQ", "한온시스템"),
    ("271560.KQ", "오리온"),
    ("377300.KQ", "카카오페이"),
    ("402340.KQ", "SK스퀘어"),
]

SECTORS = {
    "반도체": ["005930.KS", "000660.KS", "009150.KS"],
    "자동차": ["005380.KS", "000270.KS", "012330.KS"],
    "금융": ["105560.KS", "055550.KS", "086790.KS", "032830.KS"],
    "바이오": ["207940.KS", "068270.KQ", "326030.KQ"],
    "화학": ["051910.KS", "009830.KQ", "011780.KQ"],
    "IT/전기전자": ["066570.KS", "018260.KS", "011070.KQ"],
    "배터리": ["006400.KS", "373220.KS", "051910.KS"],
    "통신": ["017670.KS", "030200.KS"],
    "철강": ["005490.KS", "004020.KS"],
    "항공/운수": ["003490.KS", "011200.KS", "047810.KQ"],
    "유통": ["139480.KQ", "271560.KQ"],
    "에너지": ["010950.KS", "015760.KS"],
}

def fetch_stock_data(ticker, name):
    """yfinance로 종목 데이터 수집"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        
        per = safe_float(info.get("trailingPE") or info.get("forwardPE"))
        pbr = safe_float(info.get("priceToBook"))
        div = safe_float(info.get("dividendYield"))
        if div:
            div = round(div * 100, 2)  # 소수 → 퍼센트
        
        cap = safe_float(info.get("marketCap"))
        cap_billion = round(cap / 100000000, 0) if cap else None  # 원 → 억원
        
        price = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        
        code = ticker.split(".")[0]
        
        result = {
            "code": code,
            "name": name,
            "per": per,
            "pbr": pbr,
            "div_yield": div,
            "market_cap": cap_billion,
            "price": price,
        }
        
        print(f"  ✅ {name}({code}): PER={per}, PBR={pbr}, 시총={cap_billion}억")
        return result
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return None

def calc_market_average(stocks):
    """시가총액 가중평균 PER/PBR 계산"""
    valid = [s for s in stocks if s and s.get("per") and s.get("pbr") and s.get("market_cap")]
    if not valid:
        return None
    
    total_cap = sum(s["market_cap"] for s in valid)
    if not total_cap:
        return None
    
    # 가중평균
    w_per = sum(s["per"] * s["market_cap"] for s in valid) / total_cap
    w_pbr = sum(s["pbr"] * s["market_cap"] for s in valid) / total_cap
    
    # 배당 단순평균
    div_list = [s["div_yield"] for s in valid if s.get("div_yield")]
    avg_div = sum(div_list) / len(div_list) if div_list else None
    
    return {
        "per": round(w_per, 2),
        "pbr": round(w_pbr, 2),
        "div_yield": round(avg_div, 2) if avg_div else None,
        "market_cap": round(total_cap, 0),
    }

def calc_sector_data(stocks_map):
    """섹터별 PER 계산"""
    result = []
    for sector_name, tickers in SECTORS.items():
        codes = [t.split(".")[0] for t in tickers]
        sector_stocks = [stocks_map.get(c) for c in codes if stocks_map.get(c)]
        sector_stocks = [s for s in sector_stocks if s and s.get("per")]
        
        if sector_stocks:
            avg_per = sum(s["per"] for s in sector_stocks) / len(sector_stocks)
            avg_pbr = None
            pbr_list = [s["pbr"] for s in sector_stocks if s.get("pbr")]
            if pbr_list:
                avg_pbr = sum(pbr_list) / len(pbr_list)
            div_list = [s["div_yield"] for s in sector_stocks if s.get("div_yield")]
            avg_div = sum(div_list) / len(div_list) if div_list else None
            
            result.append({
                "name": sector_name,
                "per": round(avg_per, 2),
                "pbr": round(avg_pbr, 2) if avg_pbr else None,
                "div_yield": round(avg_div, 2) if avg_div else None,
            })
    
    return result

def calc_buffett(total_cap_billion):
    """버핏 지수 계산"""
    if not total_cap_billion:
        return None
    trillion = total_cap_billion / 10000  # 억원 → 조원
    v = round(trillion / 2200 * 100, 1)
    level = "저평가" if v < 70 else "적정" if v < 90 else "고평가" if v < 115 else "위험"
    color = "green" if v < 70 else "blue" if v < 90 else "orange" if v < 115 else "red"
    return {
        "value": v,
        "market_cap_trillion": round(trillion, 1),
        "gdp_trillion": 2200,
        "level": level,
        "color": color,
    }

def load_history():
    try:
        with open("docs/history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def main():
    print(f"📊 yfinance 데이터 수집 시작: {datetime.now()}")
    print(f"📅 기준 거래일: {TRADING_DAY}")
    os.makedirs("docs", exist_ok=True)

    # 전체 종목 수집
    all_stocks = []
    stocks_map = {}

    print("\n[코스피 종목 수집]")
    for ticker, name in KOSPI_STOCKS:
        s = fetch_stock_data(ticker, name)
        if s:
            all_stocks.append(s)
            stocks_map[s["code"]] = s
        time.sleep(0.5)

    print("\n[코스닥 종목 수집]")
    for ticker, name in KOSDAQ_STOCKS:
        s = fetch_stock_data(ticker, name)
        if s:
            all_stocks.append(s)
            stocks_map[s["code"]] = s
        time.sleep(0.5)

    # 시장 평균 계산
    kospi_stocks = [stocks_map.get(t.split(".")[0]) for t, _ in KOSPI_STOCKS]
    kospi_stocks = [s for s in kospi_stocks if s]
    kosdaq_stocks = [stocks_map.get(t.split(".")[0]) for t, _ in KOSDAQ_STOCKS]
    kosdaq_stocks = [s for s in kosdaq_stocks if s]

    print("\n[시장 평균 계산]")
    kospi = calc_market_average(kospi_stocks)
    kosdaq = calc_market_average(kosdaq_stocks)
    print(f"코스피 평균: {kospi}")
    print(f"코스닥 평균: {kosdaq}")

    # 섹터별 계산
    sectors = calc_sector_data(stocks_map)
    print(f"섹터: {len(sectors)}개")

    # 버핏 지수
    total_cap = (kospi.get("market_cap") or 0) + (kosdaq.get("market_cap") or 0) if kospi and kosdaq else None
    buffett = calc_buffett(total_cap)

    # 시가총액순 정렬
    all_stocks.sort(key=lambda x: x.get("market_cap") or 0, reverse=True)

    has_data = kospi and kospi.get("per") and kosdaq and kosdaq.get("per")
    print(f"\n결과: {'✅ 성공' if has_data else '⚠️ 실패'}")
    print(f"코스피 PER: {kospi.get('per') if kospi else 'N/A'}")
    print(f"코스닥 PER: {kosdaq.get('per') if kosdaq else 'N/A'}")
    print(f"종목: {len(all_stocks)}개")

    if has_data:
        today_data = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "trading_day": TRADING_DAY,
            "kospi": kospi,
            "kosdaq": kosdaq,
            "buffett": buffett or {},
            "sectors": sectors,
            "stocks": all_stocks,
        }

        history = load_history()
        today_str = datetime.now().strftime("%Y-%m-%d")
        history = [h for h in history if h.get("date") != today_str]
        history.append({
            "date": today_str,
            "kospi_per": kospi.get("per"),
            "kospi_pbr": kospi.get("pbr"),
            "kosdaq_per": kosdaq.get("per"),
            "buffett": buffett.get("value") if buffett else None,
        })
        history = history[-730:]

        with open("docs/data.json", "w", encoding="utf-8") as f:
            json.dump(today_data, f, ensure_ascii=False, indent=2)
        with open("docs/history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        print("✅ 저장 완료!")
    else:
        print("⚠️ 데이터 없음 - 기존 파일 유지")
        try:
            with open("docs/data.json", "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M") + " (이전 데이터)"
            with open("docs/data.json", "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except:
            pass

if __name__ == "__main__":
    main()
