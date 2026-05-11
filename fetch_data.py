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

def get_last_trading_day():
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

TRADING_DAY = get_last_trading_day()

def fetch_krx(bld, params):
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://data.krx.co.kr/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    data = urllib.parse.urlencode({"bld": bld, **params}).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode("utf-8"))
            print(f"KRX 응답 ({bld[-8:]}): {len(result.get('output', []))}개")
            return result
    except Exception as e:
        print(f"KRX 오류: {e}")
        return None

def safe_float(val):
    try:
        v = float(str(val).replace(",", ""))
        return v if v > 0 else None
    except:
        return None

def parse_market(raw):
    if not raw or "output" not in raw or not raw["output"]:
        return None
    items = raw["output"]
    total = next((i for i in items if "전체" in i.get("ISU_ABBRV", "")), items[0])
    return {
        "per": safe_float(total.get("PER")),
        "pbr": safe_float(total.get("PBR")),
        "div_yield": safe_float(total.get("DVD_YLD")),
        "market_cap": safe_float(total.get("MKTCAP")),
    }

def parse_sectors(raw):
    if not raw or "output" not in raw:
        return []
    result = []
    for item in raw["output"]:
        per = safe_float(item.get("PER"))
        if per and 0 < per < 200:
            result.append({
                "name": item.get("IDX_NM", "").replace("코스피 ", "").replace("KRX ", ""),
                "per": per,
                "pbr": safe_float(item.get("PBR")),
                "div_yield": safe_float(item.get("DVD_YLD")),
            })
    return result[:20]

def parse_stocks(raw):
    if not raw or "output" not in raw:
        return []
    stocks = []
    for item in raw["output"]:
        per = safe_float(item.get("PER"))
        pbr = safe_float(item.get("PBR"))
        if per and 0 < per < 500 and pbr and pbr > 0:
            stocks.append({
                "code": item.get("ISU_SRT_CD", ""),
                "name": item.get("ISU_ABBRV", ""),
                "per": per,
                "pbr": pbr,
                "div_yield": safe_float(item.get("DVD_YLD")),
                "market_cap": safe_float(item.get("MKTCAP")),
            })
    stocks.sort(key=lambda x: x["market_cap"] or 0, reverse=True)
    return stocks

def calc_buffett(market_cap_billion):
    if not market_cap_billion:
        return None
    t = market_cap_billion / 10000  # 억원 → 조원
    v = round(t / 2200 * 100, 1)
    level = "저평가" if v < 70 else "적정" if v < 90 else "고평가" if v < 115 else "위험"
    color = "green" if v < 70 else "blue" if v < 90 else "orange" if v < 115 else "red"
    return {"value": v, "market_cap_trillion": round(t, 0), "gdp_trillion": 2200, "level": level, "color": color}

def load_history():
    try:
        with open("docs/history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def main():
    print(f"📊 수집 시작: {datetime.now()} / 거래일: {TRADING_DAY}")
    os.makedirs("docs", exist_ok=True)

    p = {"mktId": "STK", "trdDd": TRADING_DAY, "share": "1", "money": "1", "csvxls_isNo": "false"}
    kospi = parse_market(fetch_krx("dbms/MDC/STAT/standard/MDCSTAT03901", p))
    time.sleep(1)

    p["mktId"] = "KSQ"
    kosdaq = parse_market(fetch_krx("dbms/MDC/STAT/standard/MDCSTAT03901", p))
    time.sleep(1)

    sectors = parse_sectors(fetch_krx("dbms/MDC/STAT/standard/MDCSTAT03502",
        {"mktId": "ALL", "trdDd": TRADING_DAY, "money": "1", "csvxls_isNo": "false"}))
    time.sleep(1)

    p["mktId"] = "ALL"
    stocks = parse_stocks(fetch_krx("dbms/MDC/STAT/standard/MDCSTAT03901", p))
    time.sleep(1)

    buffett = calc_buffett(kospi.get("market_cap") if kospi else None)

    has_data = kospi and kospi.get("per") and kosdaq and kosdaq.get("per")

    if has_data:
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
        today_str = datetime.now().strftime("%Y-%m-%d")
        history = [h for h in history if h.get("date") != today_str]
        history.append({"date": today_str, "kospi_per": kospi.get("per"), "kospi_pbr": kospi.get("pbr"), "kosdaq_per": kosdaq.get("per"), "buffett": buffett.get("value") if buffett else None})
        history = history[-730:]

        with open("docs/data.json", "w", encoding="utf-8") as f:
            json.dump(today_data, f, ensure_ascii=False, indent=2)
        with open("docs/history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        print(f"✅ 완료! 코스피 PER: {kospi.get('per')} / 종목: {len(stocks)}개")
    else:
        print("⚠️ KRX 데이터 없음 - 기존 data.json 유지")
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
