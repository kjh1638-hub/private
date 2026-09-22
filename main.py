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
    print("[1/5] 지수 데이터 수집...")
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
        print(f"지수 수집 오류: {e}")
        return "지수 수집 일시 오류"

def get_market_news(limit=6):
    """2. 네이버 주요 뉴스 헤드라인 수집"""
    print("[2/5] 뉴스 헤드라인 수집...")
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        
        titles = []
        for item in data:
            title = item.get("tit", "").replace("&quot;", '"').replace("&amp;", '&')
            if title:
                titles.append(f"- {title}")
        return "\n".join(titles) if titles else "주요 뉴스 없음"
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        return "뉴스 수집 일시 오류"

def get_top_movers(mode="rise", limit=10):
    """3. 네이버 증권 PC 웹페이지에서 상승/하락률 상위 종목 수집"""
    market_type = "상승률" if mode == "rise" else "하락률"
    print(f"[3/5] {market_type} 상위 종목 크롤링...")
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
                    # rate_tags[2]가 등락률 컬럼
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
        except Exception as e:
            print(f"{market_name} 크롤링 예외: {e}")
            continue

    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    top_list = results[:limit]
    
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_list)]
    return "\n".join(formatted) if formatted else "종목 데이터 수집 실패"

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. AI를 통해 심층 브리핑 생성"""
    print("[4/5] AI 브리핑 작성 중...")
    prompt = f"""
    당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
    아래 수집된 당일 마감 지수, 주요 헤드라인 뉴스, 상/하락 10위 종목 데이터를 바탕으로 투자자가 한눈에 읽기 좋은 프리미엄 텔레그램 마감 브리핑을 작성해주세요.
    
    [수집 데이터]
    1. 지수: {market_info}
    2. 주요 뉴스:
    {news_headlines}
    3. 당일 상승률 Top 10:
    {top_risers}
    4. 당일 하락률 Top 10:
    {top_fallers}
    
    [작성 요구사항]
    - 반드시 모든 항목을 빠짐없이 채워서 풍성하고 논리적으로 작성할 것.
    - 구성 형식:
      📊 **국내 증시 마감 요약**
      - 지수 흐름 및 오늘 시장의 총평 (1~2문장)
      
      📰 **오늘의 핵심 이슈 3가지**
      - 오늘 뉴스와 시장을 관통한 핵심 재료 요약 및 해설
      
      🚀 **급등 Top 10 및 주도 테마 분석**
      {top_risers}
      - 상위 종목들이 왜 올랐는지 섹터/테마별 원인 코멘트
      
      📉 **급락 Top 10 및 약세 원인**
      {top_fallers}
      - 하락 폭이 컸던 종목들의 악재나 차익실현 배경 코멘트
      
      💡 **내일장 대응 포인트**
      - 투자자가 주목해야 할 매크로/수급 체크포인트 2가지
    """
    
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    
    # 503 트래픽 대응 (3초 간격 최대 3회 시도)
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            if response.text:
                print("-> AI 브리핑 작성 성공!")
                return response.text
        except Exception as e:
            print(f"AI 호출 시도 {attempt+1}회 실패: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                raise e

def send_telegram(text):
    """5. 텔레그램 전송"""
    print("[5/5] 텔레그램 전송 중...")
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def _send(content):
        # 마크다운 전송 시도 후 에러 나면 일반 텍스트 전송
        res = requests.post(url, json={"chat_id": chat_id, "text": content, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": content})

    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            _send(part)
    else:
        _send(text)
    print("-> 전송 완료!")

if __name__ == "__main__":
    print("=== 증시 브리핑 파이프라인 시작 ===")
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=6)
    top_risers = get_top_movers(mode="rise", limit=10)
    top_fallers = get_top_movers(mode="fall", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
    print("=== 완료 ===")
