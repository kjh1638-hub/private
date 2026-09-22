import os
import time
import requests
from google import genai
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
    print("[1/4] 지수 수집...")
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        indices = []
        for item in data.get("datas", []):
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

def get_market_news(limit=6):
    """2. 네이버 주요 뉴스 헤드라인 수집"""
    print("[2/4] 뉴스 헤드라인 수집...")
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
    """3. 상승/하락률 상위 종목 수집"""
    market_type = "상승률" if mode == "rise" else "하락률"
    print(f"[3/4] {market_type} 상위 종목 수집...")
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
                rate_tags = row.select("td.number")
                if name_tag and len(rate_tags) >= 3:
                    name = name_tag.text.strip()
                    rate_str = rate_tags[2].text.strip().replace("\n", "").replace("\t", "")
                    try:
                        clean_rate = rate_str.replace("%", "").replace("+", "").replace(",", "")
                        rate_num = float(clean_rate)
                    except ValueError:
                        rate_num = 0.0
                    
                    results.append({
                        "market": market_name,
                        "name": name,
                        "rate_str": rate_str,
                        "rate_num": rate_num
                    })
        except Exception:
            continue

    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    top_list = results[:limit]
    
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_list)]
    return "\n".join(formatted) if formatted else "종목 데이터 수집 실패"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. AI 브리핑 작성 (실패 시 무조건 고품질 원본 데이터 리포트로 안전하게 자동 대체)"""
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
      📊 **국내 증시 마감 요약** (지수 및 하루 시장 총평)
      📰 **오늘의 핵심 이슈 3줄 요약** (헤드라인 뉴스를 바탕으로 당일 시장을 관통한 핵심 재료 요약)
      🚀 **상승률 Top 10 & 주도 테마** (종목 리스트 + 상승 배경 테마 코멘트)
      📉 **하락률 Top 10 & 약세 요인** (종목 리스트 + 하락 배경 요약)
      💡 **내일장 체크포인트** (1~2줄 핵심)
    """
    
    # 1. AI 호출 시도 (503 트래픽 대응 우회 목록)
    models = ["gemini-2.5-flash-lite", "gemini-3.6-flash"]
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        for m in models:
            try:
                print(f"-> AI 모델 [{m}] 호출 시도...")
                res = client.models.generate_content(model=m, contents=prompt)
                if res.text:
                    print("-> AI 브리핑 작성 성공!")
                    return res.text
            except Exception as e:
                print(f"[{m}] 호출 실패: {e}")
                time.sleep(2)
    except Exception as outer_e:
        print(f"AI 초기화 오류: {outer_e}")

    # 2. AI 서버가 모두 먹통일 경우: 프로그램이 죽지 않고 수집된 모든 원본 데이터를 꽉 채워 즉시 전송
    print("-> AI 서버 과부하로 인해 정돈된 원본 증시 리포트로 자동 전환합니다.")
    fallback_report = f"""📊 **국내 증시 마감 리포트**
{market_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}

🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}

⚠️ *(AI 분석 서버 과부하로 수집 원본 리포트가 즉시 발송되었습니다)*"""
    return fallback_report

def send_telegram(text):
    """5. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def _send(content):
        res = requests.post(url, json={"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})
        if res.status_code != 200:
            # 특수문자 문법 에러 시 일반 텍스트 전송
            requests.post(url, json={"chat_id": chat_id, "text": content})

    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            _send(part)
    else:
        _send(text)
    print("-> 텔레그램 발송 완료!")

if __name__ == "__main__":
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=6)
    top_risers = get_top_movers(mode="rise", limit=10)
    top_fallers = get_top_movers(mode="fall", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
