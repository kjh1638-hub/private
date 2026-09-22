import os
import time
import requests
import pandas as pd
from io import StringIO
from google import genai

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
    print("[1/4] 지수 수집 중...")
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        indices = []
        for item in data.get("datas", []):
            code = item.get("itemCode", "")
            name = "코스피" if "KOSPI" in code else ("코스닥" if "KOSDAQ" in code else "지수")
            price = item.get("closePrice", "")
            change = item.get("compareToPreviousClosePrice", "")
            rate = item.get("fluctuationsRatio", "")
            direction = "+" if item.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            indices.append(f"*{name}*: {price}pt ({direction}{rate}%, {direction}{change}pt)")
            
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception as e:
        print(f"지수 수집 오류: {e}")
        return "코스피/코스닥 수집 일시 오류"

def get_market_news(limit=6):
    """2. 주요 헤드라인 뉴스 수집"""
    print("[2/4] 뉴스 수집 중...")
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
        print(f"뉴스 수집 오류: {e}")
        return "뉴스 수집 일시 오류"

def get_top_movers(mode="rise", limit=10):
    """3. Pandas를 활용한 차단 우회 종목 수집"""
    market_type = "상승률" if mode == "rise" else "하락률"
    print(f"[3/4] {market_type} 상위 종목 수집 중...")
    results = []
    
    for sosok in [0, 1]:  # 0: 코스피, 1: 코스닥
        market_name = "코스피" if sosok == 0 else "코스닥"
        url = f"https://finance.naver.com/sise/sise_{mode}.naver?sosok={sosok}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            # HTML 구조를 무시하고 표 데이터만 즉시 추출하여 에러 방지
            dfs = pd.read_html(StringIO(res.text))
            
            for df in dfs:
                if '종목명' in df.columns and '등락률' in df.columns:
                    df = df.dropna(subset=['종목명', '등락률'])
                    for _, row in df.iterrows():
                        name = str(row['종목명']).strip()
                        rate_str = str(row['등락률']).strip()
                        try:
                            rate_num = float(rate_str.replace('%', '').replace('+', '').replace(',', ''))
                            results.append({
                                "market": market_name,
                                "name": name,
                                "rate_str": rate_str,
                                "rate_num": rate_num
                            })
                        except ValueError:
                            continue
                    break
        except Exception as e:
            print(f"{market_name} 종목 파싱 오류: {e}")
            continue

    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    top_list = results[:limit]
    
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_list)]
    return "\n".join(formatted) if formatted else "종목 데이터 수집 실패"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. 안정화된 AI 모델 브리핑 작성"""
    print("[4/4] AI 브리핑 작성 중...")
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
      📰 **오늘의 핵심 이슈 3줄 요약** (당일 시장 핵심 재료 요약)
      🚀 **상승률 Top 10 & 주도 테마** (수집된 종목 나열 + 섹터 상승 원인 코멘트)
      📉 **하락률 Top 10 & 약세 요인** (수집된 종목 나열 + 하락 배경 코멘트)
      💡 **내일장 체크포인트** (1~2줄 핵심)
    """
    
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    
    # 트래픽 과부하가 거의 없는 가장 안정적인 모델(1.5-flash)을 최우선으로 배치
    models = ["gemini-1.5-flash", "gemini-3.6-flash"]
    
    for m in models:
        try:
            res = client.models.generate_content(model=m, contents=prompt)
            if res.text:
                print(f"-> [{m}] 모델로 브리핑 작성 성공!")
                return res.text
        except Exception as e:
            print(f"[{m}] 호출 실패: {e}")
            time.sleep(2)

    print("-> 모든 AI 서버 과부하로 안전 리포트를 발송합니다.")
    return f"""📊 **국내 증시 마감 리포트**
{market_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}

🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}

💡 *(구글 AI 서버 일시 장애로 인해 원본 리포트가 발송되었습니다)*"""

def send_telegram(text):
    """5. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    res = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    if res.status_code != 200:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    print("-> 텔레그램 발송 완료!")

if __name__ == "__main__":
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=6)
    top_risers = get_top_movers(mode="rise", limit=10)
    top_fallers = get_top_movers(mode="fall", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
