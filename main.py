import os
import requests
from groq import Groq

# 다음/카카오 금융 공식 헤더 (차단 방지용)
DAUM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.daum.net/"
}

NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집 (네이버 폴링 API)"""
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=NAVER_HEADERS, timeout=10)
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

def get_market_news(limit=6):
    """2. 네이버 주요 뉴스 헤드라인 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        res = requests.get(url, headers=NAVER_HEADERS, timeout=10)
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

def get_top_movers(market_type="KOSPI", rank_type="high", limit=10):
    """3. 다음 증권 공식 API로 당일 등락률 상위 종목 수집 (rank_type: high=상승, low=하락)"""
    try:
        # 다음 증권 공식 시세 순위 엔드포인트
        url = f"https://finance.daum.net/api/trend/price_performance?page=1&perPage={limit}&market={market_type}&type={rank_type}"
        res = requests.get(url, headers=DAUM_HEADERS, timeout=10)
        data = res.json()
        items = data.get("data", [])
        
        result = []
        for idx, item in enumerate(items[:limit], 1):
            name = item.get("name", "")
            rate = item.get("changeRate", 0.0) * 100
            price = item.get("tradePrice", 0)
            sign = "+" if rate > 0 else ""
            if name:
                result.append(f"{idx}. {name} ({sign}{rate:.2f}%, {price:,}원)")
                
        return "\n".join(result) if result else "데이터 없음"
    except Exception as e:
        return f"종목 수집 오류: {e}"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. Groq 초고속 AI 브리핑"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_report(market_info, news_headlines, top_risers, top_fallers)

    prompt = f"""
당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
아래 수집된 당일 마감 지수, 주요 뉴스, 상/하락 상위 종목 데이터를 바탕으로 투자자가 한눈에 읽기 좋은 프리미엄 텔레그램 마감 브리핑을 작성해주세요.

[수집 데이터]
1. 지수: {market_info}
2. 주요 뉴스:
{news_headlines}
3. 당일 상승률 Top 10:
{top_risers}
4. 당일 하락률 Top 10:
{top_fallers}

[작성 요구사항]
- 모바일 텔레그램 가독성을 위해 불릿포인트와 굵은 글씨를 적극 활용하세요.
- 구성 형식:
  📊 **국내 증시 마감 요약**
  - 지수 흐름 및 오늘 시장 총평 요약
  
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

    return make_fallback_report(market_info, news_headlines, top_risers, top_fallers)

def make_fallback_report(market_info, news_headlines, top_risers, top_fallers):
    return f"""📊 **국내 증시 마감 리포트**
{market_info}

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
    market_info = get_market_indices()
    news_headlines = get_market_news()
    
    # 코스피 기준 상승/하락 Top 10 수집
    top_risers = get_top_movers(market_type="KOSPI", rank_type="high", limit=10)
    top_fallers = get_top_movers(market_type="KOSPI", rank_type="low", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
