import os
import time
import requests
from google import genai
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_market_indices():
    """1. 네이버 공식 API에서 코스피/코스닥 지수 수집"""
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
            indices.append(f"*{name}*: {price}pt ({direction}{rate}%, {direction}{change}pt)")
            
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception:
        return "지수 수집 일시 오류"

def get_market_news(limit=5):
    """2. 실시간 주요 뉴스 헤드라인 수집"""
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
    except Exception:
        return "뉴스 수집 일시 오류"

def get_top_movers(mode="rise", limit=10):
    """3. 상승률 / 하락률 상위 10위 수집"""
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
    """4. AI 브리핑 생성 (실패 시 원본 데이터 기반 기본 브리핑 자동 대체)"""
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
      1. 📊 **시장 마감 지수 요약**
      2. 📰 **오늘의 핵심 이슈 요약** (주요 뉴스 기반)
      3. 🚀 **상승률 Top 10 & 주요 테마**
      4. 📉 **하락률 Top 10 & 약세 요인**
      5. 💡 **내일장 체크포인트**
    """
    
    # AI 호출 시도 (최대 2회)
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt
                )
                if response.text:
                    return response.text
            except Exception as e:
                if attempt == 0 and "503" in str(e):
                    time.sleep(3)
                    continue
                raise e
    except Exception as e:
        print(f"AI 서버 혼잡으로 기본 데이터 브리핑 모드로 전환합니다: {e}")
    
    # AI 서버 과부하 시 전송할 깔끔한 데이터 요약본 (에러 방지용)
    fallback_text = f"""📊 *[국내 증시 마감 요약]*
{market_info}

📰 *오늘의 주요 뉴스 헤드라인*
{news_headlines}

🚀 *당일 상승률 Top 10*
{top_risers}

📉 *당일 하락률 Top 10*
{top_fallers}

*(AI 서버 혼잡으로 원본 데이터 브리핑이 발송되었습니다)*"""
    return fallback_text

def send_telegram(text):
    """5. 텔레그램 발송 (응답 상태 검증 및 실패 시 일반 텍스트 재전송)"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def _send_part(content):
        # 1차 시도: Markdown 모드로 전송
        payload = {"chat_id": chat_id, "text": content, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload)
        
        # 특수문자 마크다운 파싱 에러(400 Bad Request) 발생 시 일반 텍스트로 즉시 재전송
        if res.status_code != 200:
            print(f"Markdown 파싱 실패로 일반 텍스트 모드로 재전송합니다. (이유: {res.text})")
            payload_plain = {"chat_id": chat_id, "text": content}
            res = requests.post(url, json=payload_plain)

        print(f"텔레그램 응답: {res.status_code}, {res.text}")
        
        # 그래도 실패하면 에러를 발생시켜 GitHub 로그에 정확한 이유 출력
        if res.status_code != 200:
            raise RuntimeError(f"텔레그램 발송 최종 실패: {res.text}")

    # 4000자 초과 분할 처리
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            _send_part(part)
    else:
        _send_part(text)
