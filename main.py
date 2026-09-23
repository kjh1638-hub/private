import os
import requests
from bs4 import BeautifulSoup
from groq import Groq

# 네이버 PC/모바일 웹 차단 우회용 풀 브라우저 헤더
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://finance.naver.com/"
}

def get_market_indices_and_supply():
    """1. 코스피/코스닥 지수 및 외인/기관 수급 수집 (finance.naver.com/sise 메인 크롤링)"""
    try:
        url = "https://finance.naver.com/sise/"
        res = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), "html.parser")

        # 1) 지수
        kospi_now = soup.select_one("#KOSPI_now").text.strip()
        kospi_change = soup.select_one("#KOSPI_change").text.strip().replace("\n", " ").replace("\t", "")
        
        kosdaq_now = soup.select_one("#KOSDAQ_now").text.strip()
        kosdaq_change = soup.select_one("#KOSDAQ_change").text.strip().replace("\n", " ").replace("\t", "")
        
        idx_str = f"*코스피*: {kospi_now}pt ({kospi_change}) / *코스닥*: {kosdaq_now}pt ({kosdaq_change})"
        
        # 2) 외국인 / 기관 / 개인 수급 (메인 페이지 수급 박스)
        # 투자자별 매매동향 텍스트 파싱
        supply_list = []
        trend_box = soup.select("ul.lst_trend li")
        for item in trend_box:
            txt = item.text.strip().replace("\n", " ")
            if txt:
                supply_list.append(f"• {txt}")
                
        sup_str = "\n".join(supply_list) if supply_list else "수급: 장중 실시간 데이터 참조"
        return idx_str, sup_str
    except Exception as e:
        return "지수 수집 오류", f"수급 수집 오류: {e}"

def get_market_news(limit=6):
    """2. 네이버 주요 뉴스 헤드라인 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        res = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
        data = res.json()
        titles = []
        for item in data:
            tit = item.get("tit", "")
            if tit:
                clean_title = tit.replace("&quot;", '"').replace("&amp;", '&')
                titles.append(f"• {clean_title}")
        return "\n".join(titles) if titles else "주요 뉴스 없음"
    except Exception as e:
        return f"뉴스 수집 오류: {e}"

def get_top_movers(mode="rise", limit=10):
    """3. 네이버 공식 sise_rise / sise_fall 에서 실제 종목명과 등락률 정확히 파싱"""
    results = []
    # 0: 코스피, 1: 코스닥
    for sosok, m_name in [(0, "코스피"), (1, "코스닥")]:
        try:
            url = f"https://finance.naver.com/sise/sise_{mode}.naver?sosok={sosok}"
            res = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), "html.parser")
            
            rows = soup.select("table.type_2 tr")
            for row in rows:
                name_tag = row.select_one("a.tltle")
                num_tags = row.select("td.number")
                # 종목명과 등락률(보통 3번째 td.number)이 있는지 확인
                if name_tag and len(num_tags) >= 3:
                    name = name_tag.text.strip()
                    rate_str = num_tags[2].text.strip().replace("\n", "").replace("\t", "").replace(" ", "")
                    
                    try:
                        clean_num = float(rate_str.replace("%", "").replace("+", "").replace(",", ""))
                    except ValueError:
                        clean_num = 0.0
                    
                    if name:
                        results.append({
                            "name": name,
                            "market": m_name,
                            "rate_str": rate_str,
                            "rate_num": clean_num
                        })
        except Exception:
            continue

    # 등락률 순 정렬
    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    
    top_items = results[:limit]
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_items)]
    return "\n".join(formatted) if formatted else "종목 데이터 파싱 실패"

def generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers):
    """4. Groq 초고속 AI 브리핑 (실패 시 상세 원인 콘솔 출력)"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[오류] GitHub Secrets에 GROQ_API_KEY가 없습니다!")
        return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

    prompt = f"""
당신은 전문 증권사 PB이자 시황 수석 애널리스트입니다.
아래 수집된 당일 마감 지수, 수급 동향, 주요 뉴스, 상/하락 상위 종목 데이터를 바탕으로 투자자가 한눈에 읽기 좋은 텔레그램 마감 브리핑을 작성해주세요.

[수집 데이터]
1. 지수: {market_info}
2. 투자자별 수급 동향:
{supply_info}
3. 주요 뉴스:
{news_headlines}
4. 당일 상승률 Top 10:
{top_risers}
5. 당일 하락률 Top 10:
{top_fallers}

[작성 요구사항]
- 모바일 텔레그램 가독성을 위해 불릿포인트와 굵은 글씨를 적극 활용하세요.
- 구성 형식:
  📊 **국내 증시 마감 요약**
  - 지수 흐름 및 오늘 시장 총평 요약
  
  💰 **수급 동향 분석**
  - 외국인과 기관의 매매 패턴 및 시장 영향 요약
  
  📰 **오늘의 핵심 이슈 3가지**
  - 시장을 움직인 주요 재료 요약
  
  🚀 **급등 Top 10 및 주도 테마 분석**
  - 오늘 급등한 주요 섹터/테마와 특징 종목 배경 해설
  
  📉 **급락 Top 10 및 약세 배경**
  - 급락 종목들의 하락 요인 또는 차익실현 분석
  
  💡 **내일장 대응 포인트**
  - 투자자가 챙겨야 할 핵심 체크포인트 2가지
"""
    try:
        client = Groq(api_key=api_key)
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
    except Exception as e:
        print(f"[Groq AI 호출 오류]: {e}")
        # 만약 모델명 문제라면 8b 모델로 2차 시도
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e2:
            print(f"[Groq AI 2차 시도 오류]: {e2}")

    return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

def make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers):
    return f"""📊 **국내 증시 마감 리포트**
{market_info}

💰 **투자자별 수급 동향**
{supply_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}

🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}"""

def send_telegram(text):
    """5. 텔레그램 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    max_len = 3900
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    
    for chunk in chunks:
        res = requests.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": chunk})

if __name__ == "__main__":
    market_info, supply_info = get_market_indices_and_supply()
    news_headlines = get_market_news()
    top_risers = get_top_movers("rise", 10)
    top_fallers = get_top_movers("fall", 10)
    
    briefing = generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
