import os
import requests
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Referer": "https://m.stock.naver.com/"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집"""
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
            trends = data.get("bizTrendList", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if trends:
                latest = trends[0]
                p_val = latest.get("personalPureBuyQuant", "0")
                f_val = latest.get("foreignerPureBuyQuant", "0")
                i_val = latest.get("organPureBuyQuant", "0")
                supply_results.append(f"• {m_name}: 개인 {p_val}억 / 외인 {f_val}억 / 기관 {i_val}억")
        except Exception:
            continue
    return "\n".join(supply_results) if supply_results else "• 수급: 장마감 후 집계 데이터 참조"

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
    """4. 네이버 모바일 시가총액/등락 순위 API로 상승/하락 Top 10 추출"""
    all_stocks = []
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page=1&pageSize=100"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json()
            stocks = data.get("stocks", [])
            for s in stocks:
                name = s.get("stockName", "")
                rate_str = str(s.get("fluctuationsRatio", "0")).replace("%", "").replace(",", "")
                try:
                    rate_num = float(rate_str)
                    if name:
                        all_stocks.append({
                            "name": name,
                            "market": "코스피" if market == "KOSPI" else "코스닥",
                            "rate": rate_num
                        })
                except ValueError:
                    continue
        except Exception as e:
            continue

    if not all_stocks:
        return "종목 수집 실패", "종목 수집 실패"

    all_stocks.sort(key=lambda x: x["rate"], reverse=True)
    top_risers = [f"{i+1}. {item['market']} {item['name']} (+{item['rate']:.2f}%)" for i, item in enumerate(all_stocks[:limit])]

    all_stocks.sort(key=lambda x: x["rate"], reverse=False)
    top_fallers = [f"{i+1}. {item['market']} {item['name']} ({item['rate']:.2f}%)" for i, item in enumerate(all_stocks[:limit])]

    return "\n".join(top_risers), "\n".join(top_fallers)

def generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers):
    """5. 고성능 모델 기반 상세 브리핑 (최대 토큰 확장)"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

    client = Groq(api_key=api_key)
    priority_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    prompt = f"""
당신은 대형 증권사 수석 PB 애널리스트입니다.
제공된 당일 국내 증시 마감 데이터를 바탕으로 VIP 고객용 텔레그램 마감 브리핑을 깊이 있고 상세하게 작성해주세요.
분량 제한 때문에 내용을 압축하거나 생략하지 마시고, 각 항목마다 충분한 배경 설명과 개별 종목 분석을 담아주십시오.

[수집 데이터]
1. 지수: {market_info}
2. 수급:
{supply_info}
3. 주요 뉴스 헤드라인:
{news_headlines}
4. 당일 상승률 Top 10:
{top_risers}
5. 당일 하락률 Top 10:
{top_fallers}

[작성 형식 및 필수 포함 항목]

📊 **국내 증시 마감 총평**
- 코스피와 코스닥 지수 수치 및 등락폭 분석
- 대형주/성장주 흐름, 시장 내부 분위기 및 총평을 4줄 이상 깊이 있게 서술

💰 **투자자별 수급 동향**
- 코스피/코스닥 개인, 외국인, 기관 매매 패턴 분석
- 외국인/기관 수급의 성격과 시장에 미친 영향 시사점

📰 **오늘의 핵심 이슈 3가지**
- 시장을 움직인 가장 중요한 3대 테마/이슈 선별 요약 (1, 2, 3 번호 부여 및 상세 배경 서술)

🗞️ **오늘의 주요 뉴스 헤드라인**
- 수집된 주요 뉴스 헤드라인 원본 목록을 불릿포인트(•)로 그대로 나열

[SPLIT_POINT]

🚀 **주도 섹터 및 급등 Top 10 상세 분석**
- 상승률 상위 10개 종목 각각의 상승 배경 및 개별 호재 요약 (1번부터 10번까지 빠짐없이 종목명, 등락률, 주요 상승 요인을 명확히 기술)
- 전체 주도 테마 및 공통 상승 원인 종합 분석

📉 **급락 Top 10 및 약세 배경 분석**
- 하락률 상위 10개 종목 각각의 하락 요인 및 약세 배경 요약 (1번부터 10번까지 빠짐없이 종목명, 등락률, 주요 하락 원인을 명확히 기술)
- 공통 차익실현 및 약세 배경 종합 분석

💡 **내일장 대응 포인트**
1. 수급 흐름 체크포인트
2. 대외 거시 변수 및 모니터링 요소
"""

    for m in priority_models:
        try:
            print(f"호출 시도 모델: {m}")
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "당신은 냉철하고 분석력이 뛰어난 대형 증권사 수석 PB 애널리스트입니다. 정중하고 격식 있는 한국어로 전달하며, 모든 요청 항목을 풍부한 설명과 함께 누락 없이 완성하십시오."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=3500  # 풍부한 분량을 위해 3500토큰으로 확장
            )
            print(f"★ 모델 [{m}] 브리핑 생성 성공!")
            return response.choices[0].message.content
        except Exception as e:
            print(f"[{m}] 호출 실패: {e}")
            continue

    return make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers)

def make_fallback_report(market_info, supply_info, news_headlines, top_risers, top_fallers):
    return f"""📊 **국내 증시 마감 리포트**
{market_info}

💰 **투자자별 수급 동향**
{supply_info}

📰 **오늘의 주요 뉴스 헤드라인**
{news_headlines}
[SPLIT_POINT]
🚀 **당일 상승률 Top 10**
{top_risers}

📉 **당일 하락률 Top 10**
{top_fallers}"""

def send_telegram(text):
    """6. 텔레그램 전송 (메시지 한도 초과 시 2개로 분할 전송)"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # [SPLIT_POINT] 태그가 있으면 1부와 2부로 깔끔하게 분할
    if "[SPLIT_POINT]" in text:
        parts = text.split("[SPLIT_POINT]")
    else:
        # 태그가 없더라도 3000자 초과 시 문단 단위 분할
        max_len = 3000
        parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]

    for part in parts:
        msg = part.strip()
        if not msg:
            continue
        # 마크다운 전송 시도 후 에러 시 일반 텍스트 전송
        res = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": msg})

if __name__ == "__main__":
    market_info = get_market_indices()
    supply_info = get_market_supply()
    news_headlines = get_market_news()
    top_risers, top_fallers = get_top_movers_naver(10)
    
    briefing = generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
