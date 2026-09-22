import os
import time
import requests
from google import genai

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
    print("[1/5] 지수 데이터 수집 중...")
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        indices = []
        for item in data.get("datas", []):
            name = item.get("stockExchangeType", {}).get("name", "") or item.get("itemNm", "")
            price = item.get("closePrice", "")
            change = item.get("compareToPreviousClosePrice", "")
            rate = item.get("fluctuationsRatio", "")
            direction = "+" if item.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            indices.append(f"*{name}*: {price}pt ({direction}{rate}%, {direction}{change}pt)")
            
        return " / ".join(indices) if indices else "코스피/코스닥 지수 수집 완료"
    except Exception as e:
        print(f"지수 수집 실패: {e}")
        return "지수 정보 수집 일시 오류"

def get_market_news(limit=5):
    """2. 네이버 모바일 뉴스 API로 헤드라인 수집 (차단 및 인코딩 오류 해결)"""
    print("[2/5] 뉴스 헤드라인 수집 중...")
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        titles = []
        for item in data:
            title = item.get("tit", "").replace("&quot;", '"').replace("&amp;", '&')
            if title:
                titles.append(f"• {title}")
        return "\n".join(titles) if titles else "주요 뉴스 없음"
    except Exception as e:
        print(f"뉴스 수집 실패: {e}")
        return "뉴스 수집 일시 오류"

def get_top_movers(mode="rise", limit=10):
    """3. 네이버 공식 랭킹 API로 상승/하락 Top 10 수집 (HTML 크롤링 에러 원천 차단)"""
    market_type = "상승률" if mode == "rise" else "하락률"
    print(f"[3/5] {market_type} 상위 종목 수집 중...")
    
    ranking_type = "INCREASE" if mode == "rise" else "DECREASE"
    all_items = []
    
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            url = f"https://m.stock.naver.com/api/stocks/ranking/{market}?rankingType={ranking_type}&page=1&pageSize={limit}"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json()
            
            for item in data.get("stocks", []):
                name = item.get("stockName", "")
                price = item.get("closePrice", "")
                rate = float(item.get("fluctuationsRatio", 0.0))
                sign = "+" if rate > 0 else ""
                all_items.append({
                    "market": market,
                    "name": name,
                    "price": price,
                    "rate_num": rate,
                    "rate_str": f"{sign}{rate}%"
                })
        except Exception as e:
            print(f"{market} 랭킹 수집 실패: {e}")
            continue

    # 코스피/코스닥 통합 정렬
    reverse = True if mode == "rise" else False
    all_items.sort(key=lambda x: x["rate_num"], reverse=reverse)
    top_list = all_items[:limit]
    
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_list)]
    return "\n".join(formatted) if formatted else "종목 데이터 없음"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. AI 브리핑 생성"""
    print("[4/5] AI 브리핑 생성 요청 중...")
    prompt = f"""
    당신은 전문 증권사 PB이자 시황 애널리스트입니다.
    아래 수집된 지수, 주요 헤드라인 뉴스, 상/하락 10위 종목 데이터를 종합 분석하여 텔레그램용 마감 브리핑을 작성해주세요.
    
    [수집 데이터]
    1. 지수: {market_info}
    2. 주요 헤드라인 뉴스:
    {news_headlines}
    3. 당일 상승률 Top 10:
    {top_risers}
    4. 당일 하락률 Top 10:
    {top_fallers}
    
    [출력 요구사항]
    - 모바일 텔레그램 화면에서 빠르게 훑어보기 좋게 핵심만 불릿포인트와 굵은 글씨로 작성할 것
    - 구성:
      1. 📊 시장 마감 지수 요약
      2. 📰 오늘의 핵심 이슈 3줄 요약 (헤드라인 뉴스를 바탕으로 당일 시장을 관통한 핵심 재료 요약)
      3. 🚀 상승률 Top 10 & 주도 테마 (종목 리스트 + 상승 배경 테마 코멘트)
      4. 📉 하락률 Top 10 & 약세 요인 (종목 리스트 + 하락 배경 요약)
      5. 💡 내일장 체크포인트 (1~2줄 핵심)
    """
    
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        if response.text:
            print("-> AI 브리핑 생성 성공!")
            return response.text
    except Exception as e:
        print(f"-> AI 서버 일시 오류로 원본 데이터 포맷으로 발송: {e}")
    
    # AI 지연 시 Fallback
    return f"""📊 [국내 증시 마감 요약]
{market_info}

📰 오늘의 주요 뉴스 헤드라인
{news_headlines}

🚀 당일 상승률 Top 10
{top_risers}

📉 당일 하락률 Top 10
{top_fallers}"""

def send_telegram(text):
    """5. 텔레그램 발송"""
    print("[5/5] 텔레그램 발송 시도...")
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {"chat_id": chat_id, "text": text}
    res = requests.post(url, json=payload)
    print(f"-> 전송 결과: {res.status_code}")

if __name__ == "__main__":
    print("=== 증시 브리핑 파이프라인 시작 ===")
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=5)
    top_risers = get_top_movers(mode="rise", limit=10)
    top_fallers = get_top_movers(mode="fall", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
    print("=== 완료 ===")
