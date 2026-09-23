import os
import requests
from groq import Groq

# 네이버 증권 전용 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://stock.naver.com/"
}

def get_market_indices_and_supply():
    """1. 코스피 / 코스닥 지수 및 개인/외국인/기관 수급 수집 (네이버 integration API)"""
    indices_info = []
    supply_info = []
    
    for code, market_name in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
        try:
            url = f"https://m.stock.naver.com/api/index/{code}/integration"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json()
            
            # 지수 정보
            deal_trend = data.get("dealTrend", {})
            price = deal_trend.get("closePrice", "")
            rate = deal_trend.get("fluctuationsRatio", "")
            direction = "+" if float(rate) > 0 else ""
            indices_info.append(f"*{market_name}*: {price}pt ({direction}{rate}%)")
            
            # 수급 동향 (단위: 억 원)
            investors = data.get("investors", [])
            # investors 예시: [{"investor": "개인", "price": 1200}, {"investor": "외국인", "price": -500}, {"investor": "기관", "price": -700}]
            inv_text = []
            for inv in investors:
                name = inv.get("investor", "")
                val = inv.get("price", 0)
                sign = "+" if val > 0 else ""
                inv_text.append(f"{name} {sign}{val:,}억")
            
            if inv_text:
                supply_info.append(f"• {market_name}: " + " / ".join(inv_text))
        except Exception as e:
            indices_info.append(f"*{market_name}* 수집 오류")
            
    idx_str = " / ".join(indices_info) if indices_info else "지수 정보 없음"
    sup_str = "\n".join(supply_info) if supply_info else "수급 정보 없음"
    return idx_str, sup_str

def get_market_news(limit=6):
    """2. 네이버 주요 뉴스 헤드라인 수집"""
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

def get_top_movers_naver(limit=10):
    """3. 네이버 공식 주식 API로 상승/하락률 상위 종목 수집"""
    try:
        # 네이버 증권 전체 주식 시세 데이터 엔드포인트
        url = "https://stock.naver.com/api/domestic/market/stock/default?tradeType=KRX&marketType=ALL&orderType=marketSum&pageSize=3000"
        res = requests.get(url, headers=HEADERS, timeout=15)
        data = res.json()
        
        stocks = data.get("stocks", [])
        if not stocks:
            return "상승 종목 수집 실패", "하락 종목 수집 실패"

        # 등락률 기준 필터링 및 변환
        parsed_stocks = []
        for s in stocks:
            name = s.get("stockName", "")
            rate_str = str(s.get("fluctuationsRatio", "0")).replace("%", "").replace(",", "")
            try:
                rate_num = float(rate_str)
                parsed_stocks.append({
                    "name": name,
                    "rate": rate_num,
                    "market": s.get("marketName", "")
                })
            except ValueError:
                continue

        # 1) 상승 상위 Top 10
        parsed_stocks.sort(key=lambda x: x["rate"], reverse=True)
        top_risers = []
        for idx, item in enumerate(parsed_stocks[:limit], 1):
            top_risers.append(f"{idx}. {item['name']} (+{item['rate']:.2f}%)")

        # 2) 하락 상위 Top 10
        parsed_stocks.sort(key=lambda x: x["rate"], reverse=False)
        top_fallers = []
        for idx, item in enumerate(parsed_stocks[:limit], 1):
            top_fallers.append(f"{idx}. {item['name']} ({item['rate']:.2f}%)")

        return "\n".join(top_risers), "\n".join(top_fallers)
    except Exception as e:
        return f"상승 종목 수집 오류: {e}", f"하락 종목 수집 오류: {e}"

def generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers):
    """4. Groq 초고속 AI 브리핑"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

    prompt = f"""
당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
아래 수집된 당일 마감 지수, 외국인/기관 수급 동향, 주요 뉴스, 상/하락 상위 종목 데이터를 바탕으로 거래 법인 및 VIP 고객용 텔레그램 마감 브리핑을 작성해주세요.

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
  - 외국인과 기관의 코스피/코스닥 순매수/매도 특징 및 시장 영향
  
  📰 **오늘의 핵심 이슈 3가지**
  - 수집된 뉴스와 시장을 관통한 핵심 재료 요약
  
  🚀 **급등 Top 10 및 주도 테마 분석**
  - 오늘 급등한 섹터/테마 원인 및 특징 종목 해설
  
  📉 **급락 Top 10 및 약세 배경**
  - 하락 폭이 컸던 종목들의 악재나 차익실현 원인 해설
  
  💡 **내일장 대응 포인트**
  - 투자자가 주목해야 할 수급/매크로 체크포인트 2가지
"""
    client = Groq(api_key=api_key)
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    
    for m in models:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "당신은 냉철하고 분석력이 뛰어난 전문 증권사 PB 애널리스트입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2500
            )
            return response.choices[0].message.content
        except Exception:
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
    """5. 텔레그램 전송"""
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
    market_info, supply_info = get_market_indices_and_supply()
    news_headlines = get_market_news()
    top_risers, top_fallers = get_top_movers_naver(10)
    
    briefing = generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
