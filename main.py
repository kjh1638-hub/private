import os
import requests
import pandas as pd
from pykrx import stock
from datetime import datetime
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        data = requests.get(url, headers=HEADERS, timeout=10).json()
        indices = []
        for item in data.get("datas", []):
            code = item.get("itemCode", "")
            name = "코스피" if "KOSPI" in code else ("코스닥" if "KOSDAQ" in code else "지수")
            indices.append(f"*{name}*: {item['closePrice']}pt ({item['fluctuationsRatio']}%)")
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception as e:
        return f"지수 수집 오류: {e}"

def get_market_news():
    """2. 네이버 주요 뉴스 헤드라인 수집"""
    try:
        url = "https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize=6"
        data = requests.get(url, headers=HEADERS, timeout=10).json()
        titles = []
        for item in data:
            tit = item.get('tit', '')
            if tit:
                clean_title = tit.replace('&quot;', '"').replace('&amp;', '&')
                titles.append(f"• {clean_title}")
        return "\n".join(titles) if titles else "주요 뉴스 없음"
    except Exception as e:
        return f"뉴스 수집 오류: {e}"

def get_top_movers_krx(limit=10):
    """3. 한국거래소(KRX) 공식 데이터로 상승/하락 Top 10 수집"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        df = stock.get_market_price_change(today, today)
        if df.empty:
            df = stock.get_market_price_change_by_ticker(today)
            
        df_sorted = df.sort_values(by="등락률", ascending=False)
        
        risers = []
        for idx, (_, row) in enumerate(df_sorted.head(limit).iterrows(), 1):
            risers.append(f"{idx}. {row['종목명']} (+{row['등락률']:.2f}%)")
            
        fallers = []
        for idx, (_, row) in enumerate(df.sort_values(by="등락률", ascending=True).head(limit).iterrows(), 1):
            fallers.append(f"{idx}. {row['종목명']} ({row['등락률']:.2f}%)")
            
        return "\n".join(risers), "\n".join(fallers)
    except Exception as e:
        return "상승 종목 수집 실패", "하락 종목 수집 실패"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. Groq (Llama-3.3-70B) 기반 초고속 AI 심층 브리핑"""
    prompt = f"""
    당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
    아래 수집된 당일 마감 지수, 주요 뉴스, 상/하락 상위 10위 종목 데이터를 바탕으로 투자자가 한눈에 읽기 좋은 프리미엄 텔레그램 마감 브리핑을 작성해주세요.
    
    [수집 데이터]
    1. 지수: {market_info}
    2. 주요 뉴스:
    {news_headlines}
    3. 당일 상승률 Top 10:
    {top_risers}
    4. 당일 하락률 Top 10:
    {top_fallers}
    
    [작성 요구사항]
    - 모바일 텔레그램 가독성을 위해 불릿포인트와 굵은 글씨를 활용할 것
    - 구성 형식:
      📊 **국내 증시 마감 요약**
      - 지수 흐름 및 오늘 시장 총평 요약
      
      📰 **오늘의 핵심 이슈 3가지**
      - 수집된 뉴스와 시장을 관통한 핵심 재료 요약 및 해설
      
      🚀 **급등 Top 10 및 주도 테마 분석**
      {top_risers}
      - 상위 종목들이 왜 올랐는지 섹터/테마별 원인 해설
      
      📉 **급락 Top 10 및 약세 배경**
      {top_fallers}
      - 하락 폭이 컸던 종목들의 악재나 차익실현 원인 해설
      
      💡 **내일장 대응 포인트**
      - 투자자가 주목해야 할 수급/매크로 체크포인트 2가지
    """
    
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "당신은 냉철하고 분석력이 뛰어난 전문 증권사 PB 애널리스트입니다."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=2500
    )
    return response.choices[0].message.content

def send_telegram(text):
    """5. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # 메시지가 4000자 초과 시 분할 전송
    max_len = 3900
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    
    for chunk in chunks:
        res = requests.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": chunk})

if __name__ == "__main__":
    market_info = get_market_indices()
    news_headlines = get_market_news()
    top_risers, top_fallers = get_top_movers_krx()
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
