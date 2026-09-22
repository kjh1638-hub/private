import os
import requests
import google.generativeai as genai
from bs4 import BeautifulSoup

# 웹사이트 크롤링 시 차단 방지를 위한 브라우저 헤더 설정
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
    url = "https://finance.naver.com/"
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.text, "html.parser")
    kospi = soup.select_one(".num_quot .num").text.strip()
    kosdaq = soup.select(".num_quot .num")[1].text.strip()
    return f"코스피: {kospi} / 코스닥: {kosdaq}"

def get_market_news(limit=6):
    """2. 네이버 증권 실시간 주요 뉴스 헤드라인 수집"""
    url = "https://finance.naver.com/news/mainnews.naver"
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), "html.parser")
    
    news_titles = []
    for item in soup.select("ul.newsList li.block1 dt.articleSubject a, ul.newsList li dt.articleSubject a"):
        title = item.text.strip()
        if title and title not in news_titles:
            news_titles.append(title)
        if len(news_titles) >= limit:
            break
            
    formatted_news = [f"- {title}" for title in news_titles]
    return "\n".join(formatted_news)

def get_top_movers(mode="rise", limit=10):
    """3. 상승률(rise) 및 하락률(fall) 상위 10개 종목 수집"""
    results = []
    for sosok in [0, 1]:  # 0: 코스피, 1: 코스닥
        market_name = "코스피" if sosok == 0 else "코스닥"
        url = f"https://finance.naver.com/sise/sise_{mode}.naver?sosok={sosok}"
        res = requests.get(url, headers=HEADERS)
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
                    rate_num = float(rate.replace("%", "").replace("+", ""))
                except ValueError:
                    rate_num = 0.0
                    
                results.append({
                    "market": market_name,
                    "name": name,
                    "price": price,
                    "rate_str": rate,
                    "rate_num": rate_num
                })

    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    top_list = results[:limit]
    
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_list)]
    return "\n".join(formatted)

def generate_briefing(market_info, news_headlines, top_risers, top_fallers):
    """4. 수집된 데이터를 구글 AI(Gemini)에 전달하여 브리핑 글 작성"""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
    
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
      1. 📊 **시장 마감 지수 요약** (지수 및 하루 흐름)
      2. 📰 **오늘의 핵심 이슈 3줄 요약** (헤드라인 뉴스를 바탕으로 당일 시장을 관통한 핵심 재료 요약)
      3. 🚀 **상승률 Top 10 & 주도 테마** (종목 리스트 + 상승 배경 테마 코멘트)
      4. 📉 **하락률 Top 10 & 약세 요인** (종목 리스트 + 하락 배경 요약)
      5. 💡 **내일장 체크포인트** (1~2줄 핵심)
    """
    response = model.generate_content(prompt)
    return response.text

def send_telegram(text):
    """5. 완성된 브리핑을 내 텔레그램 방으로 발송"""
    bot_token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # 텔레그램 글자 수 제한(4,096자) 대응
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            payload = {"chat_id": chat_id, "text": part, "parse_mode": "Markdown"}
            requests.post(url, json=payload)
    else:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=payload)

if __name__ == "__main__":
    # 데이터 수집 -> AI 요약 -> 텔레그램 전송 순차 실행
    market_info = get_market_indices()
    news_headlines = get_market_news(limit=6)
    top_risers = get_top_movers(mode="rise", limit=10)
    top_fallers = get_top_movers(mode="fall", limit=10)
    
    briefing = generate_briefing(market_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
