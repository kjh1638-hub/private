import os
import time
import requests
import pandas as pd
from pykrx import stock
from datetime import datetime
from google import genai

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
    """2. 네이버 주요 뉴스 헤드라인 수집 (문법 오류 수정)"""
    try:
        url = "https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize=6"
        data = requests.get(url, headers=HEADERS, timeout=10).json()
        
        titles = []
        for item in data:
            tit = item.get('tit', '')
            if tit:
                # 백슬래시 없이 안전하게 텍스트 변환 후 리스트에 추가
                clean_title = tit.replace('&quot;', '"').replace('&amp;', '&')
                titles.append(f"• {clean_title}")
                
        return "\n".join(titles) if titles else "주요 뉴스 없음"
    except Exception as e:
        return f"뉴스 수집 오류: {e}"

def get_top_movers_krx(limit=10):
    """3. 한국거래소(KRX) 공식 데이터로 상승/하락 Top 10 수집 (클라우드 차단 우회)"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        df = stock.get_market_price_change(today, today)
        if df.empty:
            df = stock.get_market_price_change_by_ticker(today)
            
        df_sorted = df.sort_values(by="등락률", ascending=False)
        
        # 상승 상위 10
        risers = []
        for idx, (_, row) in enumerate(df_sorted.head(limit).iterrows(), 1):
            risers.append(f"{idx}. {row['종목명']} (+{row['등락률']:.2f}%)")
            
        # 하락 상위 10
        fallers = []
        for idx, (_, row) in enumerate(df.sort_values(by="등락률", ascending=True).head(limit).iterrows(), 1):
            fallers.append(f"{idx}. {row['종목명']} ({row['등락률']:.2f}%)")
            
        return "\n".join(risers), "\n".join(fallers)
    except Exception as e:
        return "상승 종목 수집 실패", "하락 종목 수집 실패"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. AI 브리핑 작성 및 서버 과부하 시 안전망 텍스트 전송"""
    prompt = f"""
    당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
    아래 데이터를 바탕으로 거래 법인이나 가망 고객에게 전달할 모바일 텔레그램용 마감 브리핑을 작성해주세요.
    
    [수집 데이터]
    1. 지수: {market_info}
    2. 주요 뉴스: \n{news_headlines}
    3. 상승률 Top 10: \n{top_risers}
    4. 하락률 Top 10: \n{top_fallers}
    
    [구성] (불릿포인트 활용)
    📊 **시장 마감 총평**
    📰 **오늘의 핵심 이슈 요약**
    🚀 **상승 주도 테마 및 원인**
    📉 **하락 테마 및 요인**
    💡 **내일장 체크포인트**
    """
    
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        # 가장 안정적인 gemini-1.5-flash 모델 적용
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        if response.text:
            return response.text
    except Exception as e:
        print(f"AI 서버 혼잡으로 원본 데이터 브리핑으로 대체합니다: {e}")
        
    return f"""📊 **국내 증시 마감 리포트**
{market_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}

🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}

💡 *(구글 AI 서버 혼잡으로 수집 원본 리포트가 즉시 발송되었습니다)*"""

def send_telegram(text):
    """5. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    res = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    # 마크다운 특수문자 충돌 시 일반 텍스트로 안전하게 재전송
    if res.status_code != 200:
        requests.post(url, json={"chat_id": chat_id, "text": text})

if __name__ == "__main__":
    market_info = get_market_indices()
    news_headlines = get_market_news()
    top_risers, top_fallers = get_top_movers_krx()
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
