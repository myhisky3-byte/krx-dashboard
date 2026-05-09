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
    # 주말이면 금요일로
    while d.weekday() >= 5:  # 5=토, 6=일
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

TRADING_DAY = get_last_trading_day()

# ───────────────────────────────────────────
# KRX 공식 API 호출
# ───────────────────────────────────────────

def fetch_krx_market_per(market="STK"):
    """코스피(STK) 또는 코스닥(KSQ) PER/PBR/배당수익률"""
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
    """섹터별 PER/PBR"""
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
    """개별종목 PER/PBR 스크리너용"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    today = TRADING_DAY
    
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
        "mktId": "ALL",
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
            return result
    except Exception as e:
        print(f"종목 리스트 오류: {e}")
        return None


def fetch_kospi_index():
    """코스피 지수 (시가총액 계산용)"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    today = datetime.now().strftime("%Y%m%d")
    
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
    """시장 전체 PER/PBR/배당수익률 파싱"""
    if not raw or "output" not in raw:
        return None
    
    items = raw["output"]
    if not items:
        return None
    
    # 시장 전체 집계 행 찾기
    total = None
    for item in items:
        name = item.get("ISU_ABBRV", "")
        if "전체" in name or name == market_name:
            total = item
            break
    
    if not total:
        total = items[0]  # 첫 행 사용
    
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
    """섹터별 PER/PBR 파싱"""
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
        
        if per and per > 0 and per < 200:  # 이상치 제거
            sectors.append({
                "name": item.get("IDX_NM", "").replace("코스피 ", "").replace("KRX ", ""),
                "per": per,
                "pbr": pbr,
                "div_yield": safe_float(item.get("DVD_YLD")),
            })
    
    return sectors[:20]  # 상위 20개 섹터


def parse_stock_list(raw):
    """개별종목 파싱 (스크리너용)"""
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
                "per": per,
                "pbr": pbr,
                "div_yield": safe_float(item.get("DVD_YLD")),
                "market_cap": safe_float(item.get("MKTCAP")),
            })
    
    # 시가총액 기준 정렬
    stocks.sort(key=lambda x: x["market_cap"] or 0, reverse=True)
    return stocks[:200]  # 상위 200개


# ───────────────────────────────────────────
# 버핏 지수 계산
# ───────────────────────────────────────────

def calculate_buffett_index(total_market_cap_billion):
    """
    버핏 지수 = 주식시장 시가총액 / GDP × 100
    한국 GDP: 약 2,200조원 (2024년 기준, 매년 업데이트 필요)
    """
    KOREA_GDP_TRILLION = 2200  # 조원
    
    if not total_market_cap_billion:
        return None
    
    market_cap_trillion = total_market_cap_billion / 1_000_000  # 억원 → 조원
    buffett_index = (market_cap_trillion / KOREA_GDP_TRILLION) * 100
    
    # 평가
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
    
    # 오늘 날짜 중복 제거
    history = [h for h in history if h.get("date") != today_str]
    
    history.append({
        "date": today_str,
        "kospi_per": today_data.get("kospi", {}).get("per"),
        "kospi_pbr": today_data.get("kospi", {}).get("pbr"),
        "kosdaq_per": today_data.get("kosdaq", {}).get("per"),
        "kosdaq_pbr": today_data.get("kosdaq", {}).get("pbr"),
        "buffett": today_data.get("buffett", {}).get("value"),
    })
    
    # 최근 730일(2년)만 유지
    history = history[-730:]
    return history


# ───────────────────────────────────────────
# 메인 실행
# ───────────────────────────────────────────

def main():
    print(f"📊 데이터 수집 시작: {datetime.now()}")
    
    os.makedirs("docs", exist_ok=True)
    
    # 1. 코스피 데이터
    print("코스피 PER/PBR 수집 중...")
    kospi_raw = fetch_krx_market_per("STK")
    kospi = parse_market_valuation(kospi_raw, "코스피")
    time.sleep(1)
    
    # 2. 코스닥 데이터
    print("코스닥 PER/PBR 수집 중...")
    kosdaq_raw = fetch_krx_market_per("KSQ")
    kosdaq = parse_market_valuation(kosdaq_raw, "코스닥")
    time.sleep(1)
    
    # 3. 섹터 데이터
    print("섹터별 밸류에이션 수집 중...")
    sector_raw = fetch_krx_sector_per()
    sectors = parse_sector_data(sector_raw)
    time.sleep(1)
    
    # 4. 개별종목
    print("개별종목 스크리너 수집 중...")
    stock_raw = fetch_krx_stock_list()
    stocks = parse_stock_list(stock_raw)
    time.sleep(1)
    
    # 5. 버핏 지수 계산
    total_cap = None
    if kospi and kospi.get("market_cap"):
        total_cap = kospi["market_cap"]
    buffett = calculate_buffett_index(total_cap)
    
    # 6. 오늘 데이터 조합
    today_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kospi": kospi or {},
        "kosdaq": kosdaq or {},
        "buffett": buffett or {},
        "sectors": sectors,
        "stocks": stocks,
    }
    
    # 7. 히스토리 업데이트
    history = load_history()
    history = append_history(history, today_data)
    
    # 8. 저장
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)
    
    with open("docs/history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 완료! 코스피 PER: {kospi.get('per') if kospi else 'N/A'}")
    print(f"✅ 버핏 지수: {buffett.get('value') if buffett else 'N/A'}%")
    print(f"✅ 섹터: {len(sectors)}개, 종목: {len(stocks)}개")


if __name__ == "__main__":
    main()
