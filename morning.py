import os
import re
import datetime
import requests
import yfinance as yf
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}

def get_yfinance_ticker_data(ticker_symbol):
    """야후 파이낸스 fast_info 및 history 이중 조회"""
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
    """Eurex 코스피200 야간선물 최종 체결가 및 등락률 수집 (해외 서버 차단 우회 및 다중 소스)"""
    
    # 1차: 네이버 모바일 증권 통합 파생 API (모바일 헤더로 요청 시 해외 IP 차단 없음)
    try:
        m_url = "https://m.stock.naver.com/api/future/KOSPI200/integration"
        m_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": "https://m.stock.naver.com/"
        }
        res = requests.get(m_url, headers=m_headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            items = data.get("itemList", []) or data.get("stockItemList", [])
            if items:
                # 거래량이 가장 많은 주력 최근월물
                top = max(items, key=lambda x: float(str(x.get("totalVolume", "0")).replace(",", "") or 0))
                close_p = float(str(top.get("closePrice") or top.get("nowPrice", 0)).replace(",", ""))
                base_p = float(str(top.get("basePrice") or top.get("previousClosePrice", 0)).replace(",", ""))
                if close_p > 0 and base_p > 0:
                    diff = close_p - base_p
                    rate = (diff / base_p) * 100
                    sign = "+" if rate >= 0 else ""
                    name = top.get("stockName", "선물 최근월물")
                    return f"{close_p:,.2f}pt ({sign}{rate:.2f}%) [{name}]"
    except Exception as e:
        print(f"[야간선물 1차 실패] {e}")

    # 2차: 네이버 금융 실시간 폴링 (글로벌 프록시 호환)
    try:
        p_url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI200"
        p_headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://finance.naver.com/"}
        res = requests.get(p_url, headers=p_headers, timeout=8)
        if res.status_code == 200:
            datas = res.json().get("datas", [])
            for d in datas:
                p = d.get("closePrice")
                r = d.get("fluctuationsRatio")
                if p and r:
                    sign = "+" if d.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
                    return f"{p}pt ({sign}{r}%)"
    except Exception as e:
        print(f"[야간선물 2차 실패] {e}")

    # 3차: Investing.com API 게이트웨이 파싱
    try:
        inv_url = "https://api.investing.com/api/financialdata/assets/investmentsIndex/historical/8880?period=P1D&interval=P1D&pointscnt=5"
        i_headers = {"User-Agent": HEADERS["User-Agent"]}
        res = requests.get(inv_url, headers=i_headers, timeout=8)
        if res.status_code == 200:
            d = res.json().get("data", [])
            if len(d) >= 2:
                latest = d[-1]
                prev = d[-2]
                close_val = latest[1]
                prev_val = prev[1]
                diff = close_val - prev_val
                rate = (diff / prev_val) * 100
                sign = "+" if rate >= 0 else ""
                return f"{close_val:,.2f}pt ({sign}{rate:.2f}%) [Eurex 연계]"
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
    """3. 장전 핵심 뉴스 헤드라인 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        m_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)", "Referer": "https://m.stock.naver.com/"}
        res = requests.get(url, headers=m_headers, timeout=8)
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
    """4. Groq 대형 모델 기반 5페이지 분할 프리미엄 모닝 브리핑 작성"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_morning(market_macro, nasdaq_movers, dow_movers, sp_movers, news)

    client = Groq(api_key=api_key)
    priority_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    
    # 오늘 날짜 명시 (환각 방지)
    today_str = datetime.date.today().strftime("%Y년 %m월 %d일")

    prompt = f"""
당신은 대형 증권사 글로벌 시황 수석 애널리스트이자 최고 수준의 프라이빗 뱅커(PB)입니다.
오늘은 [{today_str}]입니다.
아래 제공된 [실제 수집 데이터]만을 바탕으로 VIP 고객용 프리미엄 '미국 3대 지수 통합 아침 장전 브리핑'을 매우 상세하고 격식 있게 작성하십시오.

[수집 데이터 - 실제 수치 반영 필수]
1. 글로벌 주요 지수 및 매크로:
{market_macro}
2. 나스닥 핵심 빅테크 및 변동성 상위주 (티커, 종가, 등락률):
{nasdaq_movers}
3. 다우존스 전통 우량·산업·금융주 (티커, 종가, 등락률):
{dow_movers}
4. S&P 500 헬스케어·에너지·방어주 (티커, 종가, 등락률):
{sp_movers}
5. 장전 핵심 뉴스 헤드라인:
{news}

[엄격한 작성 및 환각 방지 지침]
- **사실에 기반하지 않은 일정 날조 금지**: 절대로 과거 기억에 의존해 '삼성전자 2분기 실적 발표'처럼 오늘 날짜와 무관한 특정 기업 실적 발표 일정을 허위로 지어내지 마십시오. 오늘 일정은 미 연준(Fed) 금리 발언, 환율/유가 흐름, 한은 통화신용 및 제공된 헤드라인 뉴스에 직접 언급된 거시적 일정 위주로만 객관적으로 기술하십시오.
- **수치 반영**: 위에 제공된 지수, 종목 가격, 등락률을 본문에 명확히 숫자로 인용하십시오.
- **5페이지 분할 전송**: 반드시 **[SPLIT_POINT]** 구분자를 정확히 4번 출력하여 총 5개 섹션으로 완벽히 분할되도록 하십시오.

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

[4부: 국내 증시 개장 전망 및 주도 테마 3선]
🎯 **야간선물 점검 및 오늘 코스피/코스닥 개장 전망**
- 코스피 야간선물의 수치와 등락률을 바탕으로 오늘 국내 지수 시초가 분위기(갭상승/갭하락/보합) 전망
- 미국 증시 흐름이 오늘 장초반 국내 외국인/기관 수급에 미칠 영향 분석

🚀 **오늘 주목할 국내 주도 테마 3선**
- 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 부각될 유력 테마 3가지 및 관련 수혜주

[SPLIT_POINT]

[5부: 장전 체크 뉴스, 대외 일정 및 PB 실전 전략]
🗞️ **장 시작 전 필독! 국내 증시 핵심 체크 뉴스**
- 오늘 국내 장 시작 전 투자자가 반드시 주목해야 할 핵심 뉴스/이슈 3가지를 선별하여 요약 정리

🌐 **오늘 반드시 체크해야 할 주요 일정 및 거시 변수**
- **해외 일정**: 미 연준 위원 발언, 주요국 경제지표(물가/고용/PMI) 발표 등 글로벌 체크포인트
- **국내 일정**: 외환시장 동향, 금융당국 정책 발표, 장중 외국인 선물 매매 방향성 등 실전 매크로 변수

💡 **오늘장 PB 실전 투자 전략**
1. **장초반 시초가 갭 형성 시 실전 매매 대응 원칙**
   - 갭상승 출발 시 대응 전략 (추격 매수 자제 구간 및 분할 매도 기준)
   - 갭하락 출발 시 대응 전략 (저가 분할 매수 타이밍 및 리스크 관리선)
2. **외국인 및 기관 실시간 수급 모니터링 체크포인트**
   - 장초반 선물 수급 변화 및 프로그램 매매 방향성에 따른 포트폴리오 관리 원칙
"""

    for m in priority_models:
        try:
            print(f"호출 시도 모델: {m}")
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": f"당신은 증권사 글로벌 수석 PB 애널리스트입니다. 오늘은 {today_str}입니다. 허위 사실을 지어내지 말고, 제공된 실제 수치와 팩트만을 바탕으로 전문적인 한국어 리포트를 작성하십시오. 지정된 4개의 [SPLIT_POINT]를 정확히 출력하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # 환각 방지를 위해 0.2로 낮춤
                max_tokens=4200
            )
            print(f"★ 모델 [{m}] 5페이지 모닝 브리핑 생성 성공!")
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
🎯 **개장 전망**
코스피 야간선물 수치 참조
[SPLIT_POINT]
💡 **오늘장 실전 전략**
🗞️ **장전 주요 뉴스**:
{news}"""

def send_telegram(text):
    """5. 텔레그램 5분할 안전 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    if "[SPLIT_POINT]" in text:
        parts = text.split("[SPLIT_POINT]")
    else:
        max_len = 2500
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
