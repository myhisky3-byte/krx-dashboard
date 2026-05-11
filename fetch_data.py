"""
네이버 금융 기반 데이터 수집
GitHub Actions에서 매일 자동 실행
"""

import json
import time
import urllib.request
import re
from datetime import datetime, timedelta
import os

def get_last_trading_day():
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

TRADING_DAY = get_last_trading_day()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

def fetch(url, encoding="utf-8"):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode(encoding, errors="ignore")
    except Exception as e:
        print(f"오류 ({url[:60]}): {e}")
        return None

def safe_float(val):
    try:
        v = float(str(val).replace(",", "").replace("%", "").strip())
        return v if v != 0 else None
    except:
        return None

def fetch_market_per(market="KOSPI"):
    code = "KOSPI" if market == "KOSPI" else "KOSDAQ"
    url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
    html = fetch(url, encoding="euc-kr")
    if not html:
        return None
    result = {}
    m = re.search(r'PER[^0-9]*([0-9,\.]+)', html)
    if m:
        result["per"] = safe_float(m.group(1))
    m = re.search(r'PBR[^0-9]*([0-9,\.]+)', html)
    if m:
        result["pbr"] = safe_float(m.group(1))
    m = re.search(r'배당수익률[^0-9]*([0-9,\.]+)', html)
    if m:
        result["div_yield"] = safe_float(m.group(1))
    m = re.search(r'시가총액[^0-9]*([0-9,]+)', html)
    if m:
        result["market_cap"] = safe_float(m.group(1))
    print(f"{market}: PER={result.get('per')}, PBR={result.get('pbr')}")
    return result if result.get("per") else None

def fetch_stock_summary(code):
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    html = fetch(url, encoding="euc-kr")
    if not html:
        return None
    result = {"code": code}
    m = re.search(r'<title>([^(]+)\(', html)
    if m:
        result["name"] = m.group(1).strip()
    m = re.search(r'PER.*?([0-9,\.]+)\s*배', html)
    if m:
        result["per"] = safe_float(m.group(1))
    m = re.search(r'PBR.*?([0-9,\.]+)\s*배', html)
    if m:
        result["pbr"] = safe_float(m.group(1))
    m = re.search(r'시가총액.*?([0-9,]+)\s*억', html)
    if m:
        result["market_cap"] = safe_float(m.group(1))
    m = re.search(r'배당수익률.*?([0-9\.]+)%', html)
    if m:
        result["div_yield"] = safe_float(m.group(1))
    return result

def fetch_stock_list():
    stocks = []
    major_stocks = [
        "005930","000660","005380","000270","051910",
        "006400","035420","035720","068270","105560",
        "055550","028260","005490","373220","207940",
        "012330","015760","034020","066570","003550",
        "032830","086790","018260","009150","011200",
        "010950","003490","017670","030200","036570",
        "251270","000100","002380","011070","042660",
        "009830","016360","021240","011780","004020",
        "047810","010130","000810","139480","326030",
        "034730","018880","271560","377300","402340"
    ]
    for i, code in enumerate(major_stocks):
        s = fetch_stock_summary(code)
        if s and s.get("per") and s.get("pbr"):
            stocks.append(s)
            print(f"  {code} {s.get('name','')}: PER={s.get('per')}")
        time.sleep(0.3)
        if (i+1) % 10 == 0:
            time.sleep(1)
    stocks.sort(key=lambda x: x.get("market_cap") or 0, reverse=True)
    return stocks

def fetch_sectors():
    url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
    html = fetch(url, encoding="euc-kr")
    if not html:
        return []
    sectors = []
    rows = re.findall(r'upjong_code=\d+[^>]*>(.*?)</a>.*?<td[^>]*>([0-9,\.]+)</td>', html, re.DOTALL)
    for name, per_str in rows[:20]:
        per = safe_float(per_str)
        if per and 0 < per < 200:
            sectors.append({
                "name": re.sub(r'<[^>]+>', '', name).strip(),
                "per": per,
                "pbr": None,
                "div_yield": None,
            })
    return sectors

def calc_buffett(market_cap_trillion):
    if not market_cap_trillion:
        return None
    v = round(market_cap_trillion / 2200 * 100, 1)
    level = "저평가" if v < 70 else "적정" if v < 90 else "고평가" if v < 115 else "위험"
    color = "green" if v < 70 else "blue" if v < 90 else "orange" if v < 115 else "red"
    return {"value": v, "market_cap_trillion": round(market_cap_trillion, 0), "gdp_trillion": 2200, "level": level, "color": color}

def load_history():
    try:
        with open("docs/history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def main():
    print(f"📊 네이버 금융 수집 시작: {datetime.now()}")
    os.makedirs("docs", exist_ok=True)

    print("코스피 수집 중...")
    kospi = fetch_market_per("KOSPI")
    time.sleep(1)

    print("코스닥 수집 중...")
    kosdaq = fetch_market_per("KOSDAQ")
    time.sleep(1)

    print("섹터 수집 중...")
    sectors = fetch_sectors()
    time.sleep(1)

    print("종목 수집 중...")
    stocks = fetch_stock_list()

    buffett = None
    if kospi and kospi.get("market_cap"):
        buffett = calc_buffett(kospi["market_cap"] / 10000)

    has_data = kospi and kospi.get("per") and kosdaq and kosdaq.get("per")
    print(f"\n결과: {'✅ 성공' if has_data else '⚠️ 실패'}")

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
