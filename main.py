import os
import time
import requests
from datetime import datetime
import pandas as pd
from pykrx import stock
from google import genai

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집 (이름 깨짐 원천 방지)"""
    print("[1/4] 지수 수집 중...")
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        indices = []
        for item in data.get("datas", []):
            code = item.get("itemCode", "")
            name = "코스피" if "KOSPI" in code else ("코스닥" if "KOSDAQ" in code else item.get("itemNm", "지수"))
            price = item.get("closePrice", "")
            change = item.get("compareToPreviousClosePrice", "")
            rate = item.get("fluctuationsRatio", "")
            direction = "+" if item.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            indices.append(f"*{name}*: {price}pt ({direction}{rate}%, {direction}{change}pt)")
            
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception as e:
        print(f"지수 수집 예외: {e}")
        return "코스피/코스닥 지수 수집 오류"

def get_market_news(limit=6):
    """2. 네이버 모바일 증권 주요 헤드라인 뉴스 수집"""
    print("[2/4] 뉴스 헤드라인 수집 중...")
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
        print(f"뉴스 수집 예외: {e}")
        return "뉴스 수집 일시 오류"

def get_top_movers_krx(limit=10):
    """3. 한국거래소(KRX) 공식 데이터로 당일 상승률 / 하락률 Top 10 수집 (pykrx 사용)"""
    print("[3/4] pykrx로 상/하락 종목 수집 중...")
    try:
        # 오늘 날짜 (YYYYMMDD)
        today = datetime.now().strftime("%Y%m%d")
        
        # 오늘 하루 동안의 전 종목 등락률 조회 (오늘 장이 닫힌 후이므로 오늘~오늘 조회)
        # 만약 주말이나 장 시작 전이면 최근 영업일 자동 처리
        df = stock.get_market_price_change(today, today)
        if df.empty:
            # 주말/공휴일 등으로 당일 데이터가 비어있으면 최근 영업일 탐색
            df = stock.get_market_price_change_by_ticker(today)
            
        # 등락률 순 정렬
        # 컬럼: '종목명', '등락률', '종가' 등
        df_sorted = df.sort_values(by="등락률", ascending=False)
        
        # 상승 상위
        top_risers_df = df_sorted.head(limit)
        risers = []
        for idx, (ticker, row) in enumerate(top_risers_df.iterrows(), 1):
            name = row["종목명"]
            rate = row["등락률"]
            risers.append(f"{idx}. {name} (+{rate:.2f}%)")
        top_risers_str = "\n".join(risers)
        
        # 하락 상위
        top_fallers_df = df.sort_values(by="등락률", ascending=True).head(limit)
        fallers = []
        for idx, (ticker, row) in enumerate(top_fallers_df.iterrows(), 1):
            name = row["종목명"]
            rate = row["등락률"]
            fallers.append(f"{idx}. {name} ({rate:.2f}%)")
        top_fallers_str = "\n".join(fallers)
        
        return top_risers_str, top_fallers_str
    except Exception as e:
        print(f"pykrx 수집 오류: {e}")
        return "상승 종목 수집 실패", "하락 종목 수집 실패"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. AI 브리핑 작성 (AI 실패 시 꽉 찬 알짜 데이터 리포트 전송)"""
    print("[4/4] 브리핑 생성 처리 중...")
    prompt = f"""
    당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
    아래 수집된 당일 마감 지수, 주요 헤드라인 뉴스, 상/하락 10위 종목 데이터를 바탕으로 텔레그램용 마감 브리핑을 작성해주세요.
    
    [수집 데이터]
    1. 지수: {market_info}
    2. 주요 뉴스:
    {news_headlines}
    3. 당일 상승률 Top 10:
    {top_risers}
    4. 당일 하락률 Top 10:
    {top_fallers}
    
    [작성 요구사항]
    - 모바일 텔레그램 화면에서 빠르게 훑어보기 좋게 핵심만 불릿포인트와 굵은 글씨로 작성할 것
    - 구성:
      📊 **국내 증시 마감 요약** (지수 흐름 및 하루 시장 총평)
      📰 **오늘의 핵심 이슈 3줄 요약** (헤드라인 뉴스를 바탕으로 당일 시장을 관통한 핵심 재료 요약)
      🚀 **상승률 Top 10 & 주도 테마** (종목 리스트 + 상승 배경 테마 코멘트)
      📉 **하락률 Top 10 & 약세 요인** (종목 리스트 + 하락 배경 요약)
      💡 **내일장 체크포인트** (1~2줄 핵심)
    """
    
    # AI 호출 시도
    models = ["gemini-2.5-flash", "gemini-3.6-flash"]
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        for m in models:
            try:
                res = client.models.generate_content(model=m, contents=prompt)
                if res.text:
                    print("-> AI 브리핑 완성!")
                    return res.text
            except Exception as e:
                print(f"[{m}] 호출 실패: {e}")
                time.sleep(2)
    except Exception as outer_e:
        print(f"AI 클라이언트 오류: {outer_e}")

    # AI 서버가 혼잡할 때 발송할 풍성한 원본 리포트 (데이터 누락 없음)
    print("-> 원본 증시 리포트 발송 모드 가동")
    fallback_report = f"""📊 **국내 증시 마감 리포트**
{market_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}

🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}

💡 *(AI 서버 혼잡으로 수집 원본 리포트가 발송되었습니다)*"""
    return fallback_report

def send_telegram(text):
    """5. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # 전송
    res = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    if res.status_code != 200:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    print("-> 텔레그램 발송 완료!")

if __name__ == "__main__":
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=6)
    top_risers, top_fallers = get_top_movers_krx(limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
