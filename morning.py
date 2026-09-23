import os
import re
import requests
import yfinance as yf
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/"
}

def get_yfinance_ticker_data(ticker_symbol):
    """야후 파이낸스 fast_info 및 history 이중 조회로 누락 없는 시세 수집"""
    try:
        t = yf.Ticker(ticker_symbol)
        try:
            fi = t.fast_info
            price = fi.last_price
            prev = fi.previous_close
            if price is not None and prev is not None and prev > 0:
                change = price - prev
                rate = (change / prev) * 100
                sign = "+" if rate >= 0 else ""
                return f"{price:,.2f} ({sign}{rate:.2f}%)", rate, price
        except Exception:
            pass

        hist = t.history(period="1mo")
        if not hist.empty and len(hist) >= 2:
            close = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = close - prev
            rate = (change / prev) * 100
            sign = "+" if rate >= 0 else ""
            return f"{close:,.2f} ({sign}{rate:.2f}%)", rate, close
    except Exception:
        pass
    return "집계 대기", 0.0, 0.0

def get_kospi200_night_futures():
    """코스피200 야간선물(Eurex) 한글 인코딩(CP949) 및 태그 스트리핑 기반 실제 시세 수집"""
    
    # 1. 네이버 증권 시세 메인 (CP949 한글 디코딩 필수)
    try:
        url = "https://finance.naver.com/sise/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        # 네이버 PC 웹페이지는 EUC-KR(CP949) 인코딩이므로 강제 변환
        html = res.content.decode("cp949", "ignore")
        clean_text = re.sub(r'<[^>]+>', ' ', html)
        clean_text = ' '.join(clean_text.split())

        idx = clean_text.find("야간선물")
        if idx != -1:
            chunk = clean_text[idx:idx+150]
            # 야간선물 텍스트 부근에서 가격(예: 350.25)과 등락률(예: +2.15% 또는 2.15%) 추출
            price_m = re.search(r'([\d,]+\.\d{2})', chunk)
            rate_m = re.search(r'([+-]?[\d,]+(?:\.\d+)?%)', chunk)
            
            if price_m and rate_m:
                price = price_m.group(1)
                rate = rate_m.group(1)
                sign = "+" if ("상승" in chunk or "+" in rate) and not rate.startswith("-") else ""
                clean_rate = rate if (rate.startswith("+") or rate.startswith("-")) else f"{sign}{rate}"
                return f"{price}pt ({clean_rate})"
    except Exception as e:
        print(f"[야간선물 1차 실패] {e}")

    # 2. 네이버 모바일 통합 검색 (UTF-8) 백업
    try:
        url = "https://m.search.naver.com/search.naver?query=%EC%BD%94%EC%8A%A4%ED%94%BC200+%EC%95%BC%EA%B0%84%EC%84%A0%EB%AC%BC"
        m_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
        res = requests.get(url, headers=m_headers, timeout=10)
        clean_text = re.sub(r'<[^>]+>', ' ', res.text)
        clean_text = ' '.join(clean_text.split())

        idx = clean_text.find("야간선물")
        if idx != -1:
            chunk = clean_text[idx:idx+150]
            price_m = re.search(r'([\d,]+\.\d{2})', chunk)
            rate_m = re.search(r'([+-]?[\d,]+(?:\.\d+)?%)', chunk)
            if price_m and rate_m:
                price = price_m.group(1)
                rate = rate_m.group(1)
                sign = "+" if ("상승" in chunk or "+" in rate) and not rate.startswith("-") else ""
                clean_rate = rate if (rate.startswith("+") or rate.startswith("-")) else f"{sign}{rate}"
                return f"{price}pt ({clean_rate})"
    except Exception as e:
        print(f"[야간선물 2차 실패] {e}")

    # 3. 다음(Daum) 통합 검색 백업
    try:
        url = "https://search.daum.net/search?w=tot&q=%EC%BD%94%EC%8A%A4%ED%94%BC200%20%EC%95%BC%EA%B0%84%EC%84%A0%EB%AC%BC"
        res = requests.get(url, headers=HEADERS, timeout=10)
        clean_text = re.sub(r'<[^>]+>', ' ', res.text)
        clean_text = ' '.join(clean_text.split())

        idx = clean_text.find("야간선물")
        if idx != -1:
            chunk = clean_text[idx:idx+150]
            price_m = re.search(r'([\d,]+\.\d{2})', chunk)
            rate_m = re.search(r'([+-]?[\d,]+(?:\.\d+)?%)', chunk)
            if price_m and rate_m:
                return f"{price_m.group(1)}pt ({rate_m.group(1)})"
    except Exception as e:
        print(f"[야간선물 3차 실패] {e}")

    return "야간선물 집계 대기"

def get_global_indices_and_macro():
    """1. 글로벌 주요 지수, 환율, 유가, 야간선물 수집"""
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
        val_str, _, _ = get_yfinance_ticker_data(symbol)
        results.append(f"• *{name}*: {val_str}")

    night_fut = get_kospi200_night_futures()
    print(f"★ [수집 확인] 코스피 야간선물: {night_fut}")
    results.append(f"• *코스피 야간 선물*: {night_fut}")

    return "\n".join(results)

def get_us_broad_movers():
    """2. 나스닥, 다우, S&P 500 주요 종목 티커/가격/등락률 전수 수집"""
    nasdaq_candidates = [
        ("NVDA", "엔비디아"), ("AAPL", "애플"), ("MSFT", "마이크로소프트"),
        ("TSLA", "테슬라"), ("GOOGL", "알파벳"), ("AMZN", "아마존"),
        ("META", "메타"), ("AMD", "AMD"), ("AVGO", "브로드컴"),
        ("PLTR", "팔란티어"), ("QCOM", "퀄컴"), ("SMCI", "슈퍼마이크로")
    ]
    dow_candidates = [
        ("BA", "보잉"), ("CAT", "캐터필러"), ("GS", "골드만삭스"),
        ("JPM", "JP모건"), ("UNH", "유나이티드헬스"), ("WMT", "월마트"),
        ("HD", "홈디포"), ("CVX", "쉐브론"), ("DIS", "디즈니")
    ]
    sp500_candidates = [
        ("LLY", "일라이릴리"), ("NVO", "노보노디스크"), ("XOM", "엑슨모빌"),
        ("COST", "코스트코"), ("PFE", "화이자"), ("COIN", "코인베이스")
    ]

    def format_movers(candidates, count=6):
        items = []
        for sym, name in candidates:
            val_str, rate, price = get_yfinance_ticker_data(sym)
            if val_str != "집계 대기":
                items.append((name, sym, val_str, rate, price))
        items.sort(key=lambda x: abs(x[3]), reverse=True)
        return "\n".join([f"• {x[0]} ({x[1]}): ${x[4]:,.2f} ({'+' if x[3]>=0 else ''}{x[3]:.2f}%)" for x in items[:count]])

    nasdaq_summary = format_movers(nasdaq_candidates, 6)
    dow_summary = format_movers(dow_candidates, 5)
    sp500_summary = format_movers(sp500_candidates, 4)

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
    """4. Groq 대형 모델 기반 4페이지 심층 모닝 브리핑 작성"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_morning(market_macro, nasdaq_movers, dow_movers, sp_movers, news)

    client = Groq(api_key=api_key)
    priority_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    prompt = f"""
당신은 대형 증권사 글로벌 시황 수석 애널리스트이자 프라이빗 뱅커(PB)입니다.
아래 제공된 [수집 데이터]를 바탕으로 VIP 고객용 프리미엄 '미국 3대 지수 통합 아침 장전 브리핑'을 상세하고 깊이 있게 작성하십시오.

[수집 데이터 - 실제 수치 반영 필수]
1. 글로벌 주요 지수 및 매크로 (실제 등락 수치 반드시 본문에 언급):
{market_macro}
2. 나스닥 핵심 빅테크 및 변동성 상위주 (티커, 종가, 등락률):
{nasdaq_movers}
3. 다우존스 전통 우량·산업·금융주 (티커, 종가, 등락률):
{dow_movers}
4. S&P 500 헬스케어·에너지·방어주 (티커, 종가, 등락률):
{sp_movers}
5. 장전 핵심 뉴스 헤드라인:
{news}

[작성 및 출력 지침]
- **데이터 인용 원칙**: 위에 주어진 실제 지수/가격/등락률 수치를 본문에 직접 숫자로 인용하며 분석하십시오.
- **코스피 야간선물 분석**: 4부에서 코스피 야간선물의 실제 수치(지수 포인트 및 등락률)를 직접 인용하여 오늘 아침 개장 갭 방향(상승/하락/보합)을 명확하게 짚어주십시오. 수치에 0.00%라고 적혀 있지 않은 한 절대로 0% 변동이라거나 보합세라고 임의 왜곡하지 마십시오.
- **종목 언급 원칙**: 본문에서 미국 주식을 설명할 때는 반드시 티커와 실제 가격, 등락률을 함께 병기하십시오. 예: 엔비디아(NVDA, $135.20, +4.15%)
- **글로벌 이슈 5가지**: 장전 핵심 글로벌 이슈는 반드시 1번부터 5번까지 5가지를 작성하십시오.
- **분할 전송**: 반드시 **[SPLIT_POINT]** 구분자를 정확히 3번 출력하여 총 4개 섹션으로 나누어지도록 하십시오.

---

[출력 양식 - 반드시 아래 순서와 [SPLIT_POINT] 준수]

[1부: 매크로 총평 및 헤드라인]
☀️ **간밤의 글로벌 증시 마감 총평**
- 나스닥, 다우존스, S&P 500, 필라델피아 반도체 지수의 실제 등락 수치와 퍼센트를 구체적으로 비교 분석
- 기술주(나스닥)와 전통 가치주(다우) 간의 순환매 및 지수별 차별화 흐름 상세 해설

🌐 **주요 매크로 지표 심층 분석**
- 원/달러 환율 실제 수치 및 등락률 기반 외국인 수급 영향도 분석
- WTI 국제유가 실제 수치 및 등락 배경, 원자재/물가 경로 분석
- 필라델피아 반도체 지수 실제 등락률 기반 국내 반도체(삼성전자, SK하이닉스) 파급 효과

🗞️ **오늘 아침 주요 글로벌/증시 뉴스 헤드라인**
- 수집된 뉴스 헤드라인 원본을 불릿포인트(•)로 그대로 나열

[SPLIT_POINT]

[2부: 나스닥 및 기술·AI 섹터 심층 분석]
💻 **나스닥(NASDAQ) 및 반도체/AI 특징주 분석**
- 수집된 나스닥 종목들의 종가와 등락률을 명시하며 개별 등락 요인 및 배경 상세 해설
- AI 가속기, 클라우드, 소프트웨어, 전기차 업황 관련 핵심 이슈 및 시장 영향

📰 **장전 핵심 글로벌 이슈 5가지**
- 시장에 가장 큰 영향을 준 글로벌 핵심 이슈 5가지를 선별하여 배경 및 시사점 심층 분석 (1번부터 5번까지 번호 부여)

[SPLIT_POINT]

[3부: 다우존스 & S&P 500 전통 우량주 및 경기민감 섹터 분석]
🏛️ **다우존스(DOW) 산업·금융·가치주 동향**
- 수집된 다우 종목들의 종가와 등락률을 명시하며 금융, 산업재, 방산, 소비재 종목별 등락 원인 분석

🏥 **S&P 500 헬스케어·에너지·방어주 특징**
- 수집된 S&P 500 종목들의 종가와 등락률을 명시하며 바이오/비만치료제, 에너지, 유통 방어주의 흐름 분석

[SPLIT_POINT]

[4부: 국내 증시 개장 전망 및 실전 PB 투자 전략]
🎯 **야간선물 점검 및 오늘 코스피/코스닥 개장 전망**
- 코스피 야간 선물의 실제 수치와 등락률을 바탕으로 오늘 국내 지수 시초가 분위기(갭상승/갭하락/보합) 전망
- 미국 증시 흐름이 오늘 장초반 국내 외국인/기관 수급에 미칠 영향 분석

🚀 **오늘 주목할 국내 주도 테마 3선**
- 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 부각될 유력 테마 3가지 및 관련 수혜주

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
                    {"role": "system", "content": "당신은 증권사 글로벌 수석 PB 애널리스트입니다. 제공된 실제 수치를 적극 활용하여 격식 있는 한국어로 전문적인 리포트를 작성하십시오. 지정된 3개의 [SPLIT_POINT]를 정확히 출력하세요."},
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
    """5. 텔레그램 4분할 안전 전송"""
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
