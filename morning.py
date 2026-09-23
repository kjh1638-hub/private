import os
import requests
import yfinance as yf
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Referer": "https://m.stock.naver.com/"
}

def get_yfinance_ticker_data(ticker_symbol):
    """야후 파이낸스 실시간/종가 및 등락률 계산"""
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            close = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = close - prev
            rate = (change / prev) * 100
            sign = "+" if rate >= 0 else ""
            return f"{close:,.2f} ({sign}{rate:.2f}%)", rate
    except Exception:
        pass
    return "집계 대기", 0.0

def get_global_indices_and_macro():
    """1. 글로벌 주요 지수 및 매크로 지표 수집"""
    targets = [
        ("^IXIC", "나스닥 종합"),
        ("^DJI", "다우존스"),
        ("^GSPC", "S&P 500"),
        ("^SOX", "필라델피아 반도체"),
        ("KRW=X", "원/달러 환율"),
        ("CL=F", "WTI 국제유가($)")
    ]
    results = []
    for symbol, name in targets:
        val_str, _ = get_yfinance_ticker_data(symbol)
        results.append(f"• *{name}*: {val_str}")

    # 야간 코스피200 선물 (Eurex)
    try:
        fut_url = "https://polling.finance.naver.com/api/realtime/domestic/future/KOSPI200_NIGHT"
        res = requests.get(fut_url, headers=HEADERS, timeout=10)
        data = res.json().get("datas", [{}])[0]
        price = data.get("closePrice", "")
        rate = data.get("fluctuationsRatio", "")
        if price:
            sign = "+" if data.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            results.append(f"• *코스피 야간 선물*: {price}pt ({sign}{rate}%)")
        else:
            results.append("• *코스피 야간 선물*: 장 마감 집계 참조")
    except Exception:
        results.append("• *코스피 야간 선물*: 장 마감 집계 참조")

    return "\n".join(results)

def get_us_broad_movers():
    """2. 나스닥, 다우존스, S&P 500 3대 지수별 대표 특징주 전수 수집"""
    
    # 1) 나스닥 & 테크/성장 대표주
    nasdaq_candidates = [
        ("NVDA", "엔비디아"), ("AAPL", "애플"), ("MSFT", "마이크로소프트"),
        ("TSLA", "테슬라"), ("GOOGL", "알파벳"), ("AMZN", "아마존"),
        ("META", "메타"), ("AMD", "AMD"), ("AVGO", "브로드컴"),
        ("PLTR", "팔란티어"), ("QCOM", "퀄컴"), ("SMCI", "슈퍼마이크로")
    ]
    
    # 2) 다우존스 전통 우량/산업/금융주
    dow_candidates = [
        ("BA", "보잉"), ("CAT", "캐터필러"), ("GS", "골드만삭스"),
        ("JPM", "JP모건"), ("UNH", "유나이티드헬스"), ("WMT", "월마트"),
        ("HD", "홈디포"), ("CVX", "쉐브론"), ("DIS", "디즈니")
    ]
    
    # 3) S&P 500 헬스케어/에너지/필수소비재 대표주
    sp500_candidates = [
        ("LLY", "일라이릴리"), ("NVO", "노보노디스크"), ("XOM", "엑슨모빌"),
        ("COST", "코스트코"), ("PFE", "화이자"), ("COIN", "코인베이스")
    ]

    def pick_top_movers(candidates, count=5):
        items = []
        for sym, name in candidates:
            val_str, rate = get_yfinance_ticker_data(sym)
            if val_str != "집계 대기":
                items.append((name, sym, val_str, rate))
        items.sort(key=lambda x: abs(x[3]), reverse=True)
        return "\n".join([f"• {x[0]}({x[1]}): {x[2]}" for x in items[:count]])

    nasdaq_summary = pick_top_movers(nasdaq_candidates, 6)
    dow_summary = pick_top_movers(dow_candidates, 5)
    sp500_summary = pick_top_movers(sp500_candidates, 4)

    return nasdaq_summary, dow_summary, sp500_summary

def get_morning_news(limit=6):
    """3. 장전 핵심 글로벌/증시 뉴스 헤드라인 수집"""
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

def generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news):
    """4. Groq 대형 모델 기반 3대 지수 종합 심층 모닝 브리핑 (4페이지 분할)"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_morning(market_macro, nasdaq_movers, dow_movers, sp_movers, news)

    client = Groq(api_key=api_key)
    priority_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    prompt = f"""
당신은 대형 증권사 글로벌 시황 수석 애널리스트이자 프라이빗 뱅커(PB)입니다.
전날 뉴욕 증시 마감 데이터와 나스닥, 다우존스, S&P 500의 지수별 특징주 시세를 종합하여 VIP 고객을 위한 '미국 3대 지수 통합 아침 장전 브리핑'을 매우 상세하고 깊이 있게 작성하십시오.
글이 잘리지 않도록 각 문장을 깔끔하게 완결 지으며, 반드시 **[SPLIT_POINT]** 구분자를 정확히 3번 포함하여 총 4개 섹션(4개 페이지)으로 나누어 작성해야 합니다.

[수집 데이터]
1. 글로벌 주요 지수 및 매크로:
{market_macro}
2. 나스닥 핵심 빅테크 및 변동성 상위주:
{nasdaq_movers}
3. 다우존스 전통 산업·금융·소비재 특징주:
{dow_movers}
4. S&P 500 바이오/에너지/플랫폼 특징주:
{sp_movers}
5. 장전 핵심 뉴스 헤드라인:
{news}

[출력 양식 - 반드시 아래 순서와 [SPLIT_POINT]를 준수하세요]

[1부: 매크로 총평 및 헤드라인]
☀️ **간밤의 글로벌 증시 마감 총평**
- 나스닥, 다우존스, S&P 500, 필라델피아 반도체 지수의 실제 등락 수치 비교 분석
- 기술주(나스닥)와 전통 가치주(다우) 간의 로테이션(순환매) 흐름 상세 해설

🌐 **주요 매크로 지표 심층 분석**
- 원/달러 환율 흐름과 외국인 자금 방향성 영향도
- WTI 국제유가 변동 원인 및 물가/금리 경로 영향
- 필라델피아 반도체 지수 등락에 따른 국내 반도체 영향

🗞️ **오늘 아침 주요 글로벌/증시 뉴스 헤드라인**
- 수집된 뉴스 헤드라인 원본을 불릿포인트(•)로 그대로 나열

[SPLIT_POINT]

[2부: 나스닥 및 기술·AI 섹터 심층 분석]
💻 **나스닥(NASDAQ) 및 반도체/AI 특징주 분석**
- 엔비디아, 애플, 테슬라, 마이크로소프트 등 빅테크 및 반도체 특징주 개별 등락 배경
- AI, 소프트웨어, 클라우드, 전기차 업황 관련 핵심 이슈 및 시장 영향 해설

📰 **장전 핵심 글로벌 이슈 3가지**
- 시장에 가장 큰 충격을 준 글로벌 핵심 이슈 3가지 선별 및 심층 분석 (1, 2, 3 번호 부여)

[SPLIT_POINT]

[3부: 다우존스 & S&P 500 전통 우량주 및 경기민감 섹터 분석]
🏛️ **다우존스(DOW) 산업·금융·가치주 동향**
- 골드만삭스/JP모건(금융), 보잉/캐터필러(산업재), 쉐브론(에너지), 월마트(소비재) 등 다우 핵심 종목의 등락 요인 및 경기 전망

🏥 **S&P 500 헬스케어·에너지·방어주 특징**
- 일라이릴리, 노보노디스크 등 비만치료제/바이오 섹터 및 전통 소비재·원자재 기업들의 특징적인 흐름 분석

[SPLIT_POINT]

[4부: 국내 증시 개장 전망 및 실전 PB 투자 전략]
🎯 **야간선물 점검 및 오늘 코스피/코스닥 개장 전망**
- 코스피 야간 선물의 흐름으로 본 오늘 국내 지수 시초가 예상 흐름 (갭상승/갭하락/보합)
- 미국 3대 지수 흐름이 오늘 장초반 국내 기관/외국인 수급에 미칠 영향

🚀 **오늘 주목할 국내 주도 테마 3선**
- 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 강세를 보일 유력 테마 3가지 및 관련 종목군

💡 **오늘장 PB 실전 투자 전략**
1. 장초반 시초가 갭 형성 시 매매 대응 원칙
2. 오늘 반드시 챙겨야 할 거시 변수 및 외국인 수급 모니터링 포인트
"""

    for m in priority_models:
        try:
            print(f"호출 시도 모델: {m}")
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "당신은 증권사 글로벌 수석 PB 애널리스트입니다. 풍부한 분량과 깊이 있는 분석으로 격식 있는 한국어로 작성하십시오. 지정된 3개의 [SPLIT_POINT]를 빠짐없이 출력하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            print(f"★ 모델 [{m}] 4페이지 모닝 브리핑 생성 성공!")
            return response.choices[0].message.content
        except Exception as e:
            print(f"[{m}] 호출 실패: {e}")
            continue

    return make_fallback_morning(market_macro, nasdaq_movers, dow_movers, sp_movers, news)

def make_fallback_morning(market_macro, nasdaq_movers, dow_movers, sp_movers, news):
    return f"""☀️ **간밤의 글로벌 증시 모닝 리포트**
{market_macro}
[SPLIT_POINT]
💻 **나스닥 특징주**
{nasdaq_movers}
[SPLIT_POINT]
🏛️ **다우 & S&P 특징주**
{dow_movers}
{sp_movers}
[SPLIT_POINT]
🗞️ **장전 주요 뉴스**
{news}"""

def send_telegram(text):
    """5. 텔레그램 분할 안전 전송 (3~4페이지 자동 분할)"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    if "[SPLIT_POINT]" in text:
        parts = text.split("[SPLIT_POINT]")
    else:
        max_len = 2800
        parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]

    for idx, part in enumerate(parts, 1):
        msg = part.strip()
        if not msg:
            continue
        res = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": msg})

if __name__ == "__main__":
    market_macro = get_global_indices_and_macro()
    nasdaq_movers, dow_movers, sp_movers = get_us_broad_movers()
    news = get_morning_news()
    
    briefing = generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news)
    send_telegram(briefing)
