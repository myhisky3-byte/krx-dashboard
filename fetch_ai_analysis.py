"""
한국 주식 분석 엔진 (완전 무료 버전)
- KRX 공식 API → 밸류에이션 (PER/PBR)
- DART API → 재무제표 (무료)
- Google 뉴스 RSS → 뉴스 수집 (무료)
- 규칙 기반 키워드 감성분석 (무료)
- 규칙 기반 신호등 → 매수/관망/매도 (무료)
외부 유료 API 전혀 없음
"""

import json, time, os, re
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

DART_API_KEY = os.environ.get("DART_API_KEY", "")

# ── 감성 키워드 사전 ─────────────────────────
POSITIVE_KW = [
    "실적 개선","매출 증가","영업이익 증가","흑자","최대 실적","사상 최대",
    "수주","계약 체결","신사업","배당 확대","자사주 매입","성장","호실적",
    "어닝 서프라이즈","목표주가 상향","매수 추천","턴어라운드","회복","신고가",
]
NEGATIVE_KW = [
    "실적 악화","매출 감소","영업손실","적자","어닝 쇼크","목표주가 하향",
    "매도","리콜","소송","과징금","제재","조사","구조조정","감원","손실",
    "급락","신저가","부채 증가","공장 폐쇄",
]
MACRO_POS_KW = [
    "금리 인하","경기 회복","수출 호조","외국인 순매수","증시 상승",
    "물가 안정","성장률 상향","무역수지 흑자",
]
MACRO_NEG_KW = [
    "금리 인상","경기 침체","수출 감소","외국인 순매도","증시 하락",
    "인플레이션","성장률 하향","무역수지 적자","지정학적 리스크","공급망 위기",
]

# ── Google 뉴스 RSS ──────────────────────────
def fetch_rss(query, max_items=5):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    news = []
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read().decode("utf-8", errors="replace")
        root = ET.fromstring(content)
        ch = root.find("channel")
        if ch is None:
            return news
        for item in ch.findall("item")[:max_items]:
            t = item.find("title")
            if t is not None and t.text:
                title = re.sub(r'\s*-\s*[^-]+$', '', t.text).strip()
                if len(title) > 5:
                    news.append(title)
    except ET.ParseError:
        try:
            titles = re.findall(r'<title><!\[CDATA\[(.+?)\]\]></title>', content)
            for t in titles[1:max_items+1]:
                t = re.sub(r'\s*-\s*[^-]+$', '', t).strip()
                if len(t) > 5:
                    news.append(t)
        except:
            pass
    except Exception as e:
        print(f"    RSS 오류({query}): {e}")
    return news

def fetch_stock_news(name, max_items=4):
    news = fetch_rss(f"{name} 주가", max_items)
    if not news:
        news = fetch_rss(name, max_items)
    return news

def fetch_macro_news():
    news = []
    for q in ["코스피 전망", "한국 증시", "한국 경제"]:
        news += fetch_rss(q, 3)
        time.sleep(0.3)
    seen, unique = set(), []
    for n in news:
        if n not in seen:
            seen.add(n); unique.append(n)
    return unique[:8]

# ── 감성 분석 ────────────────────────────────
def analyze_sentiment(news, pos_kw, neg_kw):
    if not news:
        return {"score": 0, "label": "NEUTRAL", "pos": 0, "neg": 0}
    text = " ".join(news)
    pos = sum(1 for kw in pos_kw if kw in text)
    neg = sum(1 for kw in neg_kw if kw in text)
    total = pos + neg
    score = int((pos - neg) / total * 100) if total > 0 else 0
    label = "POSITIVE" if score >= 20 else "NEGATIVE" if score <= -20 else "NEUTRAL"
    return {"score": score, "label": label, "pos": pos, "neg": neg}

# ── DART 재무제표 ─────────────────────────────
def get_corp_code(stock_code):
    if not DART_API_KEY: return None
    url = f"https://opendart.fss.or.kr/api/company.json?crtfc_key={DART_API_KEY}&stock_code={stock_code}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode())["corp_code"]
    except: return None

def get_financials(corp_code, year):
    if not DART_API_KEY or not corp_code: return {}
    url = (f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
           f"?crtfc_key={DART_API_KEY}&corp_code={corp_code}"
           f"&bsns_year={year}&reprt_code=11011&fs_div=CFS")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            items = json.loads(r.read().decode()).get("list", [])
        raw = {}
        for item in items:
            label = item.get("account_nm","")
            def safe(v): return int(str(v or "0").replace(",","").replace("-","0") or 0)
            raw[label] = {"cur": safe(item.get("thstrm_amount")), "prev": safe(item.get("frmtrm_amount"))}
        return raw
    except: return {}

def parse_fin(raw):
    def g(k): return raw.get(k,{}).get("cur",0) or 0
    def gp(k): return raw.get(k,{}).get("prev",0) or 0
    rev   = g("매출액") or g("수익(매출액)")
    prevr = gp("매출액") or gp("수익(매출액)")
    op    = g("영업이익")
    net   = g("당기순이익")
    eq    = g("자본총계")
    ast   = g("자산총계")
    dbt   = g("부채총계")
    def pct(a,b): return round(a/b*100,1) if b and b>0 else None
    return {
        "revenue_growth": pct(rev-prevr, prevr),
        "op_margin":      pct(op, rev),
        "roe":            pct(net, eq),
        "debt_ratio":     pct(dbt, eq),
    }

# ── 점수 계산 ─────────────────────────────────
def calc_score(fin, per, pbr, sentiment):
    s = 50

    # 밸류에이션 (30점)
    if per:
        if per < 6: s+=18
        elif per < 10: s+=13
        elif per < 15: s+=7
        elif per < 20: s+=0
        elif per < 30: s-=7
        else: s-=15
    if pbr:
        if pbr < 0.5: s+=12
        elif pbr < 1.0: s+=8
        elif pbr < 1.5: s+=3
        elif pbr < 2.5: s+=0
        else: s-=7

    # 성장성 (25점)
    rg = fin.get("revenue_growth")
    if rg is not None:
        if rg>30: s+=15
        elif rg>15: s+=10
        elif rg>5: s+=5
        elif rg>0: s+=2
        elif rg>-10: s-=5
        else: s-=12

    # 수익성 (25점)
    roe = fin.get("roe")
    if roe is not None:
        if roe>25: s+=13
        elif roe>15: s+=8
        elif roe>8: s+=4
        elif roe<0: s-=8
    op = fin.get("op_margin")
    if op is not None:
        if op>20: s+=12
        elif op>10: s+=7
        elif op>5: s+=3
        elif op<0: s-=10
    dr = fin.get("debt_ratio")
    if dr is not None:
        if dr<50: s+=5
        elif dr<100: s+=2
        elif dr>200: s-=8

    # 뉴스 감성 (20점)
    ns = sentiment.get("score",0) if sentiment else 0
    if ns>=50: s+=12
    elif ns>=20: s+=6
    elif ns<=-20: s-=6
    elif ns<=-50: s-=12

    return max(0, min(100, s))

def to_signal(score):
    if score >= 65: return "BUY"
    if score >= 40: return "HOLD"
    return "SELL"

def make_reason(fin, per, pbr, sentiment, signal):
    parts = []
    if per and per < 12: parts.append(f"PER {per:.1f}배 저평가")
    elif per and per > 25: parts.append(f"PER {per:.1f}배 고평가")
    rg = fin.get("revenue_growth")
    if rg is not None:
        if rg > 15: parts.append(f"매출 성장률 {rg:.1f}% 양호")
        elif rg < -5: parts.append(f"매출 {abs(rg):.1f}% 감소")
    roe = fin.get("roe")
    if roe is not None:
        if roe > 15: parts.append(f"ROE {roe:.1f}% 우수")
        elif roe < 3: parts.append(f"ROE {roe:.1f}% 낮음")
    label = sentiment.get("label","NEUTRAL") if sentiment else "NEUTRAL"
    if label == "POSITIVE": parts.append("뉴스 긍정적")
    elif label == "NEGATIVE": parts.append("뉴스 부정적 요인 감지")
    if not parts:
        parts = ["지표 양호" if signal=="BUY" else "지표 부진" if signal=="SELL" else "지표 혼재"]
    return " / ".join(parts[:3])

# ── 거시 분석 ─────────────────────────────────
def macro_analysis(news, kospi_per, kospi_pbr, buffett):
    sent = analyze_sentiment(news, MACRO_POS_KW, MACRO_NEG_KW)
    val = 50
    if kospi_per:
        if kospi_per<10: val+=20
        elif kospi_per<13: val+=10
        elif kospi_per>18: val-=15
    if buffett:
        if buffett<70: val+=15
        elif buffett<90: val+=5
        elif buffett>115: val-=20
    combined = (val + (sent["score"]+100)/2) / 2
    if combined >= 60:
        sig = "BULLISH"
        summary = f"코스피 PER {kospi_per}배, 버핏지수 {buffett}%로 시장 밸류에이션이 양호합니다. 뉴스 감성도 긍정 우위로 매수 환경입니다."
    elif combined >= 40:
        sig = "NEUTRAL"
        summary = f"코스피 PER {kospi_per}배, 버핏지수 {buffett}%로 적정 수준입니다. 종목 선별이 중요한 시기입니다."
    else:
        sig = "BEARISH"
        summary = f"코스피 PER {kospi_per}배, 버핏지수 {buffett}%로 주의 구간입니다. 리스크 관리가 필요합니다."
    risks = [kw for kw in MACRO_NEG_KW if any(kw in n for n in news)][:2]
    opps  = [kw for kw in MACRO_POS_KW if any(kw in n for n in news)][:2]
    return {
        "market_signal": sig,
        "summary": summary,
        "key_risk": ", ".join(risks) if risks else "특이 리스크 없음",
        "key_opportunity": ", ".join(opps) if opps else "특이 기회 없음",
        "sentiment_score": int((sent["score"]+100)/2),
    }

# ── 메인 ─────────────────────────────────────
def main():
    print(f"🚀 분석 시작: {datetime.now()}")
    os.makedirs("docs", exist_ok=True)

    base = {}
    try:
        with open("docs/data.json", "r", encoding="utf-8") as f:
            base = json.load(f)
    except: pass

    kospi_per   = base.get("kospi",{}).get("per")
    kospi_pbr   = base.get("kospi",{}).get("pbr")
    buffett_val = base.get("buffett",{}).get("value")
    stock_map   = {s["code"]: s for s in base.get("stocks",[])}

    # 거시 뉴스
    print("📰 거시 뉴스 수집 (Google RSS)...")
    mnews = fetch_macro_news()
    print(f"  → {len(mnews)}개")
    macro = macro_analysis(mnews, kospi_per, kospi_pbr, buffett_val)
    time.sleep(1)

    # 종목 분석
    stocks_list = base.get("stocks", [])[:200]
    print(f"📊 종목 분석: {len(stocks_list)}개")
    year = str(datetime.now().year - 1)
    analyzed = []

    for i, stock in enumerate(stocks_list):
        code = stock["code"]
        name = stock["name"]
        per  = stock.get("per")
        pbr  = stock.get("pbr")

        if (i+1) % 20 == 0:
            print(f"  [{i+1}/{len(stocks_list)}]...")

        # 재무제표
        fin = {}
        if DART_API_KEY:
            cc = get_corp_code(code)
            if cc:
                fin = parse_fin(get_financials(cc, year))
            time.sleep(0.2)

        # 뉴스 (상위 60개만)
        news = []
        if i < 60:
            news = fetch_stock_news(name, 4)
            time.sleep(0.4)

        sent  = analyze_sentiment(news, POSITIVE_KW, NEGATIVE_KW)
        score = calc_score(fin, per, pbr, sent)
        sig   = to_signal(score)
        reason= make_reason(fin, per, pbr, sent, sig)

        analyzed.append({
            "code": code, "name": name,
            "market_cap": stock.get("market_cap"),
            "per": per, "pbr": pbr,
            "div_yield": stock.get("div_yield"),
            "financials": fin,
            "news": news,
            "news_sentiment": sent,
            "score": score, "signal": sig, "reason": reason,
        })

    analyzed.sort(key=lambda x: x["score"], reverse=True)

    out = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "macro": {"news": mnews, "analysis": macro},
        "stocks": analyzed,
        "summary": {
            "buy":  len([s for s in analyzed if s["signal"]=="BUY"]),
            "hold": len([s for s in analyzed if s["signal"]=="HOLD"]),
            "sell": len([s for s in analyzed if s["signal"]=="SELL"]),
        }
    }

    with open("docs/ai_analysis.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 완료! 🟢{out['summary']['buy']} 🟡{out['summary']['hold']} 🔴{out['summary']['sell']}")

if __name__ == "__main__":
    main()
