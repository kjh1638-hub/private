import os
import requests
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Referer": "https://m.stock.naver.com/"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        indices = []
        for item in data.get("datas", []):
            code = item.get("itemCode", "")
            name = "코스피" if "KOSPI" in code else ("코스닥" if "KOSDAQ" in code else "지수")
            price = item.get("closePrice", "")
            rate = item.get("fluctuationsRatio", "")
            direction = "+" if item.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            indices.append(f"*{name}*: {price}pt ({direction}{rate}%)")
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception as e:
        return f"지수 수집 오류: {e}"

def get_market_supply():
    """2. 외국인 / 기관 / 개인 수급 수집 (모바일 공식 trend API)"""
    supply_results = []
    for code, m_name in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
        try:
            url = f"https://m.stock.naver.com/api/index/{code}/trend"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json()
            
            # trend API 규격: 리스트이거나 bizTrendList 키를 포함
            target = None
            if isinstance(data, list) and len(data) > 0:
                target = data[0]
            elif isinstance(data, dict):
                trend_list = data.get("bizTrendList", [])
                if trend_list:
                    target = trend_list[0]
            
            if target:
                p_val = target.get("personalPureBuyQuant", "0")
                f_val = target.get("foreignerPureBuyQuant", "0")
                i_val = target.get("organPureBuyQuant", "0")
                supply_results.append(f"• {m_name}: 개인 {p_val}억 / 외인 {f_val}억 / 기관 {i_val}억")
        except Exception:
            continue
            
    return "\n".join(supply_results) if supply_results else "수급: 장마감 후 공시 집계 참조"

def get_market_news(limit=6):
    """3. 네이버 주요 뉴스 헤드라인 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        titles = []
        for item in data:
            tit = item.get("tit", "")
            if tit:
                clean_title = tit.replace("&quot;", '"').replace("&amp;", '&')
                titles.append(f"• {clean_title}")
        return "\n".join(titles) if titles else "주요 뉴스 없음"
    except Exception as e:
        return f"뉴스 수집 오류: {e}"

def get_top_movers(mode="UP", limit=10):
    """4. 네이버 모바일 실시간 순위 API (mode: UP=상승, DOWN=하락)"""
    try:
        url = f"https://m.stock.naver.com/api/stocks/ranking/{mode}?pageSize={limit}&page=1"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        # rankingList 혹은 stocks 키 파싱
        items_data = []
        if isinstance(data, dict):
            items_data = data.get("rankingList") or data.get("stocks") or []
        elif isinstance(data, list):
            items_data = data

        results = []
        for idx, item in enumerate(items_data[:limit], 1):
            name = item.get("itemTitle") or item.get("stockName") or item.get("itemName") or ""
            rate = item.get("changeRate") or item.get("fluctuationsRatio") or "0"
            sign = "+" if mode == "UP" else ""
            if name:
                results.append(f"{idx}. {name} ({sign}{rate}%)")
                
        return "\n".join(results) if results else "종목 데이터 집계 완료"
    except Exception as e:
        return f"종목 수집 오류: {e}"

def generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers):
    """5. Groq 초고속 AI 브리핑"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[경고] GROQ_API_KEY 환경변수가 설정되지 않았습니다.")
        return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

    prompt = f"""
당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
아래 수집된 당일 마감 지수, 수급 동향, 주요 뉴스, 상/하락 상위 종목 데이터를 바탕으로 투자자가 한눈에 읽기 좋은 프리미엄 텔레그램 마감 브리핑을 작성해주세요.

[수집 데이터]
1. 지수: {market_info}
2. 투자자별 수급 동향:
{supply_info}
3. 주요 뉴스:
{news_headlines}
4. 당일 상승률 Top 10:
{top_risers}
5. 당일 하락률 Top 10:
{top_fallers}

[작성 요구사항]
- 모바일 텔레그램 가독성을 위해 불릿포인트와 굵은 글씨를 적극 활용하세요.
- 구성 형식:
  📊 **국내 증시 마감 요약**
  - 지수 흐름 및 오늘 시장 총평 요약
  
  💰 **수급 동향 분석**
  - 외국인과 기관의 매매 패턴 및 수급적 특징
  
  📰 **오늘의 핵심 이슈 3가지**
  - 시장을 움직인 주요 재료 요약
  
  🚀 **급등 Top 10 및 주도 테마 분석**
  - 상승 상위 종목들의 섹터 특징 및 배경
  
  📉 **급락 Top 10 및 약세 배경**
  - 하락 상위 종목들의 약세 요인
  
  💡 **내일장 대응 포인트**
  - 투자자가 챙겨야 할 핵심 체크포인트 2가지
"""
    client = Groq(api_key=api_key)
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    for m in models:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "당신은 냉철하고 전문적인 증권사 PB 애널리스트입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[{m}] Groq 호출 오류: {e}")
            continue

    return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

def make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers):
    return f"""📊 **국내 증시 마감 리포트**
{market_info}

💰 **투자자별 수급 동향**
{supply_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}

🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}"""

def send_telegram(text):
    """6. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    max_len = 3900
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    
    for chunk in chunks:
        res = requests.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": chunk})

if __name__ == "__main__":
    market_info = get_market_indices()
    supply_info = get_market_supply()
    news_headlines = get_market_news()
    top_risers = get_top_movers("UP", 10)
    top_fallers = get_top_movers("DOWN", 10)
    
    briefing = generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
