import os
import time
import requests
from google import genai
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_market_indices():
    """1. 네이버 공식 API에서 코스피/코스닥 지수 수집"""
    print("[1/5] 지수 데이터 수집 중...")
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        items = data.get("datas", [])
        indices = []
        for item in items:
            name = item.get("itemNm", "")
            price = item.get("closePrice", "")
            change = item.get("compareToPreviousClosePrice", "")
            rate = item.get("fluctuationsRatio", "")
            direction = "+" if item.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            indices.append(f"{name}: {price}pt ({direction}{rate}%, {direction}{change}pt)")
            
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception as e:
        print(f"지수 수집 실패: {e}")
        return "지수 수집 일시 오류"

def get_market_news(limit=5):
    """2. 실시간 주요 뉴스 헤드라인 수집"""
    print("[2/5] 뉴스 헤드라인 수집 중...")
    try:
        url = "https://finance.naver.com/news/mainnews.naver"
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), "html.parser")
        
        news_titles = []
        for item in soup.select("ul.newsList li.block1 dt.articleSubject a, ul.newsList li dt.articleSubject a"):
            title = item.text.strip()
            if title and title not in news_titles:
                news_titles.append(title)
            if len(news_titles) >= limit:
                break
                
        formatted_news = [f"• {title}" for title in news_titles]
        return "\n".join(formatted_news) if formatted_news else "주요 뉴스 없음"
    except Exception as e:
        print(f"뉴스 수집 실패: {e}")
        return "뉴스 수집 일시 오류"

def get_top_movers(mode="rise", limit=10):
    """3. 상승률 / 하락률 상위 10위 수집"""
    market_type = "상승률" if mode == "rise" else "하락률"
    print(f"[3/5] {market_type} 상위 종목 수집 중...")
    results = []
    for sosok in [0, 1]:  # 0: 코스피, 1: 코스닥
        market_name = "코스피" if sosok == 0 else "코스닥"
        url = f"https://finance.naver.com/sise/sise_{mode}.naver?sosok={sosok}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), "html.parser")
            
            rows = soup.select("table.type_2 tr")
            for row in rows:
                name_tag = row.select_one("a.tltle")
                rate_tag = row.select("td.number")
                if name_tag and len(rate_tag) >= 3:
                    name = name_tag.text.strip()
                    price = rate_tag[0].text.strip()
                    rate = rate_tag[2].text.strip().replace("\n", "").replace("\t", "")
                    try:
                        rate_num = float(rate.replace("%", "").replace("+", "").replace(",", ""))
                    except ValueError:
                        rate_num = 0.0
                        
                    results.append({
                        "market": market_name,
                        "name": name,
                        "price": price,
                        "rate_str": rate,
                        "rate_num": rate_num
                    })
        except Exception:
            continue

    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    top_list = results[:limit]
    
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_list)]
    return "\n".join(formatted) if formatted else "종목 데이터 없음"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. AI 요약 브리핑 생성 (과부하 시 원본 텍스트 자동 대체)"""
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
      2. 📰 오늘의 핵심 이슈 요약 (주요 뉴스 기반)
      3. 🚀 상승률 Top 10 & 주요 테마
      4. 📉 하락률 Top 10 & 약세 요인
      5. 💡 내일장 체크포인트
    """
    
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt
                )
                if response.text:
                    print("-> AI 브리핑 생성 성공!")
                    return response.text
            except Exception as e:
                if attempt == 0 and "503" in str(e):
                    time.sleep(3)
                    continue
                raise e
    except Exception as e:
        print(f"-> AI 서버 과부하로 기본 텍스트 모드로 전환: {e}")
    
    # AI 응답 지연 시 안전망 발송
    return f"""📊 [국내 증시 마감 요약]
{market_info}

📰 오늘의 주요 뉴스 헤드라인
{news_headlines}

🚀 당일 상승률 Top 10
{top_risers}

📉 당일 하락률 Top 10
{top_fallers}

(AI 서버 혼잡으로 기본 수집 데이터가 발송되었습니다.)"""

def send_telegram(text):
    """5. 텔레그램 전송 (상세 로그 출력 포함)"""
    print("[5/5] 텔레그램 발송 시도...")
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text
    }
    
    res = requests.post(url, json=payload)
    print(f"-> 텔레그램 응답 코드: {res.status_code}")
    print(f"-> 텔레그램 응답 본문: {res.text}")
    
    if res.status_code != 200:
        raise RuntimeError(f"텔레그램 발송 실패: {res.text}")
    print("-> 텔레그램 발송 성공!")

# ★ 프로그램 시작 지점 (들여쓰기 절대 주의)
if __name__ == "__main__":
    print("=== 증시 브리핑 파이프라인 시작 ===")
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=5)
    top_risers = get_top_movers(mode="rise", limit=10)
    top_fallers = get_top_movers(mode="fall", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
    print("=== 모든 작업 완료 ===")
