"""
한국 주식시장 밸류에이션 대시보드 - 데이터 수집 스크립트
매일 GitHub Actions에서 자동 실행됨
"""

import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import os

# ───────────────────────────────────────────
# 최근 거래일 계산 (주말/공휴일 제외)
# ───────────────────────────────────────────

def get_last_trading_day():
    """가장 최근 거래일 반환 (주말 제외, 오늘 포함)"""
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

TRADING_DAY = get_last_trading_day()

# ───────────────────────────────────────────
# KRX 공식 API 호출
# ───────────────────────────────────────────

def fetch_krx_market_per(market="STK"):
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    today = TRADING_DAY
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
        "mktId": market,
        "trdDd": today,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false"
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT03901.cmd"
    }
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result
    except Exception as e:
        print(f"KRX API 오류 ({market}): {e}")
        return None


def fetch_krx_sector_per():
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    today = TRADING_DAY
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT03502",
        "mktId": "ALL",
        "trdDd": today,
        "money": "1",
        "csvxls_isNo": "false"
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT03502.cmd"
    }
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result
    except Exception as e:
        print(f"섹터 API 오류: {e}")
        return None


def fetch_krx_stock_list():
    """코스피 + 코스닥 전체 종목"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    today = TRADING_DAY
    all_stocks = []

    for market in ["STK", "KSQ"]:  # 코스피 + 코스닥
        params = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
            "mktId": market,
            "trdDd": today,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false"
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT03901.cmd"
        }
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                items = result.get("output", [])
                for item in items:
                    item["_market"] = "KOSPI" if market == "STK" else "KOSDAQ"
                all_stocks.extend(items)
        except Exception as e:
            print(f"종목 리스트 오류 ({market}): {e}")
        time.sleep(0.5)

    return {"output": all_stocks}


def fetch_kospi_index():
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    today = TRADING_DAY
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT00101",
        "idxIndMidclssCd": "01",
        "trdDd": today,
        "money": "1",
        "csvxls_isNo": "false"
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT00101.cmd"
    }
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result
    except Exception as e:
        print(f"지수 API 오류: {e}")
        return None


# ───────────────────────────────────────────
# 데이터 파싱 & 가공
# ───────────────────────────────────────────

def parse_market_valuation(raw, market_name):
    if not raw or "output" not in raw:
        return None
    items = raw["output"]
    if not items:
        return None
    total = None
    for item in items:
        name = item.get("ISU_ABBRV", "")
        if "전체" in name or name == market_name:
            total = item
            break
    if not total:
        total = items[0]
    def safe_float(val):
        try:
            return float(str(val).replace(",", ""))
        except:
            return None
    return {
        "per": safe_float(total.get("PER")),
        "pbr": safe_float(total.get("PBR")),
        "div_yield": safe_float(total.get("DVD_YLD")),
        "market_cap": safe_float(total.get("MKTCAP")),
    }


def parse_sector_data(raw):
    if not raw or "output" not in raw:
        return []
    sectors = []
    for item in raw["output"]:
        def safe_float(val):
            try:
                return float(str(val).replace(",", ""))
            except:
                return None
        per = safe_float(item.get("PER"))
        pbr = safe_float(item.get("PBR"))
        if per and per > 0 and per < 200:
            sectors.append({
                "name": item.get("IDX_NM", "").replace("코스피 ", "").replace("KRX ", ""),
                "per": per,
                "pbr": pbr,
                "div_yield": safe_float(item.get("DVD_YLD")),
            })
    return sectors[:20]


def parse_stock_list(raw):
    """코스피 + 코스닥 전체 종목 파싱"""
    if not raw or "output" not in raw:
        return []
    stocks = []
    for item in raw["output"]:
        def safe_float(val):
            try:
                v = float(str(val).replace(",", ""))
                return v if v > 0 else None
            except:
                return None
        per = safe_float(item.get("PER"))
        pbr = safe_float(item.get("PBR"))
        if per and per > 0 and per < 500 and pbr and pbr > 0:
            stocks.append({
                "code": item.get("ISU_SRT_CD", ""),
                "name": item.get("ISU_ABBRV", ""),
                "market": item.get("_market", "KOSPI"),
                "per": per,
                "pbr": pbr,
                "div_yield": safe_float(item.get("DVD_YLD")),
                "market_cap": safe_float(item.get("MKTCAP")),
            })
    # 시가총액 기준 정렬
    stocks.sort(key=lambda x: x["market_cap"] or 0, reverse=True)
    return stocks  # 전체 종목 반환


# ───────────────────────────────────────────
# 버핏 지수 계산
# ───────────────────────────────────────────

def calculate_buffett_index(total_market_cap_billion):
    KOREA_GDP_TRILLION = 2200
    if not total_market_cap_billion:
        return None
    market_cap_trillion = total_market_cap_billion / 1_000_000
    buffett_index = (market_cap_trillion / KOREA_GDP_TRILLION) * 100
    if buffett_index < 70:
        level = "저평가"
        color = "green"
    elif buffett_index < 90:
        level = "적정"
        color = "blue"
    elif buffett_index < 115:
        level = "고평가"
        color = "orange"
    else:
        level = "심각한 고평가"
        color = "red"
    return {
        "value": round(buffett_index, 1),
        "market_cap_trillion": round(market_cap_trillion, 0),
        "gdp_trillion": KOREA_GDP_TRILLION,
        "level": level,
        "color": color
    }


# ───────────────────────────────────────────
# 히스토리 데이터 관리
# ───────────────────────────────────────────

def load_history(filepath="docs/history.json"):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def append_history(history, today_data):
    today_str = datetime.now().strftime("%Y-%m-%d")
    history = [h for h in history if h.get("date") != today_str]
    history.append({
        "date": today_str,
        "kospi_per": today_data.get("kospi", {}).get("per"),
        "kospi_pbr": today_data.get("kospi", {}).get("pbr"),
        "kosdaq_per": today_data.get("kosdaq", {}).get("per"),
        "kosdaq_pbr": today_data.get("kosdaq", {}).get("pbr"),
        "buffett": today_data.get("buffett", {}).get("value"),
    })
    history = history[-730:]
    return history


# ───────────────────────────────────────────
# 메인 실행
# ───────────────────────────────────────────

def main():
    print(f"📊 데이터 수집 시작: {datetime.now()}")
    print(f"📅 기준 거래일: {TRADING_DAY}")
    os.makedirs("docs", exist_ok=True)

    print("코스피 PER/PBR 수집 중...")
    kospi_raw = fetch_krx_market_per("STK")
    kospi = parse_market_valuation(kospi_raw, "코스피")
    time.sleep(1)

    print("코스닥 PER/PBR 수집 중...")
    kosdaq_raw = fetch_krx_market_per("KSQ")
    kosdaq = parse_market_valuation(kosdaq_raw, "코스닥")
    time.sleep(1)

    print("섹터별 밸류에이션 수집 중...")
    sector_raw = fetch_krx_sector_per()
    sectors = parse_sector_data(sector_raw)
    time.sleep(1)

    print("코스피 + 코스닥 전체 종목 수집 중...")
    stock_raw = fetch_krx_stock_list()
    stocks = parse_stock_list(stock_raw)
    print(f"  → {len(stocks)}개 종목 수집 완료")
    time.sleep(1)

    total_cap = None
    if kospi and kospi.get("market_cap"):
        total_cap = kospi["market_cap"]
    buffett = calculate_buffett_index(total_cap)

    today_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trading_day": TRADING_DAY,
        "kospi": kospi or {},
        "kosdaq": kosdaq or {},
        "buffett": buffett or {},
        "sectors": sectors,
        "stocks": stocks,
    }

    history = load_history()
    history = append_history(history, today_data)

    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)

    with open("docs/history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"✅ 완료! 코스피 PER: {kospi.get('per') if kospi else 'N/A'}")
    print(f"✅ 버핏 지수: {buffett.get('value') if buffett else 'N/A'}%")
    print(f"✅ 섹터: {len(sectors)}개, 종목: {len(stocks)}개")


if __name__ == "__main__":
    main()
