import os
import re
import datetime
import requests
import yfinance as yf
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
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
    """Eurex 야간선물 및 코스피200 선물 안정 수집"""
    
    # 1. 네이버 모바일 대표 파생 API
    try:
        url = "https://m.stock.naver.com/front-api/v1/marketIndex/prices?category=futures&reutersCode=10100"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)"}, timeout=6)
        if res.status_code == 200:
            data = res.json().get("result", [])
            if data:
                p = data[0].get("closePrice")
                r = data[0].get("fluctuationsRatio")
                if p and r:
                    sign = "+" if not str(r).startswith("-") and not str(r).startswith("+") else ""
                    return f"{p}pt ({sign}{r}%) [코스피200 선물 최근월물]"
    except Exception as e:
        print(f"[선물 수집 1차] {e}")

    # 2. 다음(Daum) 금융 선물 최근월물 API
    try:
        daum_url = "https://finance.daum.net/api/quote/KRX:10100/summary"
        d_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.daum.net/"}
        res = requests.get(daum_url, headers=d_headers, timeout=6)
        if res.status_code == 200:
            d = res.json().get("data", {})
            trade_p = float(d.get("tradePrice", 0))
            change_rate = float(d.get("changeRate", 0)) * 100
            sign = "+" if change_rate >= 0 else ""
            if 200.0 <= trade_p <= 600.0:
                return f"{trade_p:,.2f}pt ({sign}{change_rate:.2f}%) [선물 최근월물]"
    except Exception as e:
        print(f"[선물 수집 2차] {e}")

    # 3. 야후 파이낸스 KOSPI 200 연계 지표 프록시
    try:
        val_str, r, p = get_yfinance_ticker_data("^KS200")
        if val_str != "집계 대기":
            return f"{val_str} [코스피200 지수 연동 기준]"
    except Exception as e:
        print(f"[선물 수집 3차] {e}")

    return "장 마감 정산 확인"

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
        return "\n".join([f"• **{x[0]} ({x[1]}, ${x[4]:,.2f}, {'+' if x[3]>=0 else ''}{x[3]:.2f}%)**" for x in items[:count]])

    nasdaq_summary = format_movers(nasdaq_candidates, 6)
    dow_summary = format_movers(dow_candidates, 5)
    sp500_summary = format_movers(sp500_candidates, 4)

    return nasdaq_summary, dow_summary, sp500_summary

def get_morning_news(limit=10):
    """3. 장전 핵심 뉴스 헤드라인 10개 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        m_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)", "Referer": "https://m.stock.naver.com/"}
        res = requests.get(url, headers=m_headers, timeout=8)
        data = res.json()
        titles = []
        for item in data:
            tit = item.get("tit", "")
            if tit:
                clean_title = tit.replace("&quot;", '"').replace("&amp;", '&').replace("&lt;", '<').replace("&gt;", '>')
                titles.append(clean_title)
        return titles if titles else ["장전 주요 뉴스 집계 중"]
    except Exception as e:
        return [f"뉴스 수집 오류: {e}"]

def call_groq_ai(client, system_prompt, user_prompt):
    """Groq AI 모델 호출 함수"""
    priority_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    for m in priority_models:
        try:
            res = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=3000
            )
            return res.choices[0].message.content
        except Exception as e:
            print(f"[{m}] 호출 실패: {e}")
            continue
    return ""

def generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news_list):
    """4. 토큰 잘림 방지를 위해 2단계 분할 호출로 1부~5부 완전 작성"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return "GROQ API KEY 누락"

    client = Groq(api_key=api_key)
    today_str = datetime.date.today().strftime("%Y년 %m월 %d일")
    news_text = "\n".join([f"{idx+1}. {n}" for idx, n in enumerate(news_list)])

    system_prompt = f"당신은 국내 최고 증권사 글로벌 수석 PB 애널리스트입니다. 오늘은 {today_str}입니다. 허위 사실을 날조하지 말고, 깊이 있고 격식 있는 한국어로 서술하십시오."

    # 1차 호출: 1부, 2부, 3부 (미국 및 글로벌 집중 분석)
    prompt_part1 = f"""
아래 데이터를 바탕으로 '미국 3대 지수 모닝 브리핑 1부~3부'를 작성하십시오.
반드시 [SPLIT_POINT] 구분자를 포함하여 1부, 2부, 3부를 분할하십시오.

[수집 데이터]
1. 글로벌 주요 지표:
{market_macro}
2. 나스닥 핵심주:
{nasdaq_movers}
3. 다우존스 전통주:
{dow_movers}
4. S&P 500 특징주:
{sp_movers}

[작성 규칙]
- 종목명, 티커, 가격, 등락률은 반드시 굵은 글씨(**)로 쓰고, 원인 설명은 일반 글씨(연한 글씨)로 작성하십시오.
  (예: • **엔비디아(NVDA, $135.20, +4.15%)**: 차세대 AI 가속기 수요 견조로 상승...)

[출력 양식]
[1부: 매크로 총평 및 주요 지표]
☀️ **간밤의 글로벌 증시 마감 총평**
- 나스닥, 다우존스, S&P 500, 필라델피아 반도체 지수의 실제 등락 수치와 퍼센트를 구체적으로 비교 분석
- 기술주(나스닥)와 전통 가치주(다우) 간의 순환매 흐름 상세 해설

🌐 **주요 매크로 지표 심층 분석**
- 원/달러 환율 실제 수치 및 외국인 수급 영향도
- WTI 국제유가 등락 배경 및 원자재/물가 경로
- 필라델피아 반도체 지수 등락에 따른 국내 반도체(삼성전자, SK하이닉스) 파급 효과

[SPLIT_POINT]

[2부: 나스닥 및 기술·AI 섹터 심층 분석]
💻 **나스닥(NASDAQ) 및 반도체/AI 특징주 분석**
- 수집된 나스닥 종목들의 가격/등락률을 볼드체로 명시하고 개별 등락 배경 상세 해설
- AI 가속기, 클라우드, 전기차 업황 관련 핵심 이슈 분석

📰 **장전 핵심 글로벌 이슈 5가지**
- 시장에 가장 큰 영향을 준 글로벌 핵심 이슈 5가지 선별 및 심층 분석 (1번부터 5번까지 번호 부여)

[SPLIT_POINT]

[3부: 다우존스 & S&P 500 전통 우량주 및 경기민감 섹터 분석]
🏛️ **다우존스(DOW) 산업·금융·가치주 동향**
- 수집된 다우 종목들의 가격/등락률을 볼드체로 명시하고 종목별 등락 원인 분석

🏥 **S&P 500 헬스케어·에너지·방어주 특징**
- 수집된 S&P 500 종목들의 가격/등락률을 볼드체로 명시하고 바이오, 에너지, 방어주 흐름 분석
"""

    # 2차 호출: 4부, 5부 (국내 개장 전망, 뉴스 10선, 일정, PB 실전 전략)
    prompt_part2 = f"""
아래 데이터를 바탕으로 '국내 증시 개장 전망 및 실전 전략 4부~5부'를 작성하십시오.
반드시 [SPLIT_POINT] 구분자를 포함하여 4부와 5부를 분할하십시오.

[수집 데이터]
- 글로벌 및 코스피 야간선물:
{market_macro}
- 장전 핵심 뉴스 헤드라인 10선:
{news_text}

[작성 규칙]
- **일정 허위 날조 절대 금지**: 과거 기억에 의존해 오늘 날짜와 맞지 않는 특정 개별 기업의 실적 발표(예: 삼성전자 실적 등)를 절대로 지어내지 마십시오. 오늘 일정은 미 연준(Fed) 금리 정책, 주요국 경제지표(고용/물가/환율), 그리고 [뉴스 헤드라인 10선]에 실제 명시된 공시/정책 일정만을 작성하십시오.

[출력 양식]
[4부: 국내 증시 개장 전망 및 주도 테마 3선]
🎯 **야간선물 점검 및 오늘 코스피/코스닥 개장 전망**
- 코스피 야간선물 수치를 바탕으로 오늘 국내 지수 시초가 분위기(갭상승/갭하락/보합) 전망
- 미국 증시 흐름이 오늘 장초반 국내 외국인/기관 수급에 미칠 영향 분석

🚀 **오늘 주목할 국내 주도 테마 3선**
- 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 부각될 유력 테마 3가지 및 관련 수혜주

[SPLIT_POINT]

[5부: 장전 체크 뉴스 10선, 대내외 일정 및 PB 실전 전략]
🗞️ **장 시작 전 필독! 국내 증시 핵심 체크 뉴스 10선**
- 수집된 뉴스 10개를 기반으로 오늘 장전 투자자가 반드시 알아야 할 국내외 핵심 뉴스 10가지를 1번부터 10번까지 빠짐없이 요약

🌐 **오늘 반드시 체크해야 할 대내외 주요 일정 및 거시 변수**
- **해외 일정**: 미 연준 통화정책 및 연사 발언, 주요국 경제지표 발표 등 공인된 일정
- **국내 일정**: 외환시장 동향, 금융당국 정책 발표, 수집된 뉴스 10선에 공시된 실제 일정

💡 **오늘장 PB 실전 투자 전략**
1. **장초반 시초가 갭 형성 시 실전 매매 대응 원칙**
   - 갭상승 출발 시 대응 전략 (추격 매수 자제 구간 및 분할 매도 기준)
   - 갭하락 출발 시 대응 전략 (저가 분할 매수 타이밍 및 리스크 관리선)
2. **외국인 및 기관 실시간 수급 모니터링 체크포인트**
   - 장초반 선물 수급 변화 및 프로그램 매매 방향성에 따른 포트폴리오 관리 원칙
"""

    print("★ [1/2] 1부~3부 생성 중...")
    res_part1 = call_groq_ai(client, system_prompt, prompt_part1)
    
    print("★ [2/2] 4부~5부 생성 중...")
    res_part2 = call_groq_ai(client, system_prompt, prompt_part2)

    # 1부~3부와 4부~5부를 합쳐서 반환
    full_briefing = f"{res_part1.strip()}\n\n[SPLIT_POINT]\n\n{res_part2.strip()}"
    return full_briefing

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
        # 마크다운 전송 후 실패 시 일반 텍스트 재전송
        res = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": msg})

if __name__ == "__main__":
    market_macro = get_global_indices_and_macro()
    nasdaq_movers, dow_movers, sp_movers = get_us_broad_movers()
    news_list = get_morning_news(limit=10)
    
    briefing = generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news_list)
    send_telegram(briefing)
