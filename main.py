import os
import requests
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://stock.naver.com/"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집 (검증된 네이버 폴링 API)"""
    try:
        url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        indices = []
        for item in data.get("datas", []):
            code = item.get("itemCode", "")
            name = "코스피" if "KOSPI" in code else ("코스닥" if "KOSDAQ" in code else "지수")
            price = item.get("closePrice", "")
            rate = item.get("fluctuationsRatio", "")
            direction = "+" if item.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            indices.append(f"*{name}*: {price}pt ({direction}{rate}%)")
        return " / ".join(indices) if indices else "지수 정보 없음"
    except Exception as e:
        return f"지수 수집 오류: {e}"

def get_market_supply():
    """2. 외국인 / 기관 / 개인 수급 수집"""
    supply_results = []
    for code, m_name in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
        try:
            url = f"https://m.stock.naver.com/api/index/{code}/trend"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json()
            # 최신 1건 수급 데이터 가져오기
            latest = data[0] if isinstance(data, list) and data else (data.get("bizTrendList", [{}])[0] if isinstance(data, dict) else {})
            
            p_val = latest.get("personalValue", "0")
            f_val = latest.get("foreignValue", "0")
            i_val = latest.get("institutionValue", "0")
            
            supply_results.append(f"• {m_name}: 개인 {p_val}억 / 외인 {f_val}억 / 기관 {i_val}억")
        except Exception:
            continue
            
    return "\n".join(supply_results) if supply_results else "수급 데이터 장중 집계 중"

def get_market_news(limit=6):
    """3. 네이버 주요 뉴스 헤드라인 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        res = requests.get(url, headers=HEADERS, timeout=10)
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

def get_top_movers_naver(limit=10):
    """4. 네이버 전체 주식 데이터에서 상승/하락률 Top 10 추출 (List 파싱 버그 완벽 수정)"""
    try:
        url = "https://stock.naver.com/api/domestic/market/stock/default?tradeType=KRX&marketType=ALL&orderType=marketSum&pageSize=3000"
        res = requests.get(url, headers=HEADERS, timeout=15)
        raw_data = res.json()
        
        # API 응답이 리스트든 딕셔너리든 모두 처리
        if isinstance(raw_data, list):
            stocks = raw_data
        elif isinstance(raw_data, dict):
            stocks = raw_data.get("stocks", []) or raw_data.get("stockList", []) or []
        else:
            stocks = []

        if not stocks:
            return "상승 종목 데이터 없음", "하락 종목 데이터 없음"

        parsed_stocks = []
        for s in stocks:
            name = s.get("stockName", "")
            rate_val = s.get("fluctuationsRatio", 0)
            try:
                rate_num = float(str(rate_val).replace("%", "").replace(",", ""))
                parsed_stocks.append({
                    "name": name,
                    "rate": rate_num
                })
            except (ValueError, TypeError):
                continue

        # 상승률 순 정렬
        parsed_stocks.sort(key=lambda x: x["rate"], reverse=True)
        top_risers = [f"{i+1}. {item['name']} (+{item['rate']:.2f}%)" for i, item in enumerate(parsed_stocks[:limit])]

        # 하락률 순 정렬
        parsed_stocks.sort(key=lambda x: x["rate"], reverse=False)
        top_fallers = [f"{i+1}. {item['name']} ({item['rate']:.2f}%)" for i, item in enumerate(parsed_stocks[:limit])]

        return "\n".join(top_risers), "\n".join(top_fallers)
    except Exception as e:
        return f"상승 종목 수집 오류: {e}", f"하락 종목 수집 오류: {e}"

def generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers):
    """5. Groq AI 프리미엄 브리핑"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
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
- 모바일 텔레그램 가독성을 위해 불릿포인트와 굵은 글씨를 활용하세요.
- 구성 형식:
  📊 **국내 증시 마감 요약**
  - 지수 흐름 및 오늘 시장 총평
  
  💰 **수급 동향 분석**
  - 외국인과 기관의 매매 패턴 및 수급적 의미
  
  📰 **오늘의 핵심 이슈 3가지**
  - 시장을 움직인 주요 재료 요약
  
  🚀 **급등 Top 10 및 주도 테마 분석**
  - 오늘 강세를 보인 섹터/테마와 상승 이유
  
  📉 **급락 Top 10 및 약세 배경**
  - 급락 종목들의 하락 요인 또는 차익실현 분석
  
  💡 **내일장 대응 포인트**
  - 투자자가 챙겨야 할 핵심 체크포인트 2가지
"""
    client = Groq(api_key=api_key)
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    
    for m in models:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "당신은 냉철하고 분석력이 뛰어난 전문 증권사 PB 애널리스트입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2500
            )
            return response.choices[0].message.content
        except Exception:
            continue

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
    """6. 텔레그램 전송"""
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
    market_info = get_market_indices()
    supply_info = get_market_supply()
    news_headlines = get_market_news()
    top_risers, top_fallers = get_top_movers_naver(10)
    
    briefing = generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
