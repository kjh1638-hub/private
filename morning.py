import os
import re
import datetime
import requests
import yfinance as yf
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://m.stock.naver.com/"
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
    """코스피200 선물 최근월물 실제 체결가 및 전일 정산가 직접 계산"""
    try:
        url = "https://m.stock.naver.com/api/future/KOSPI200/integration"
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            items = data.get("itemList", []) or data.get("stockItemList", [])
            if items:
                def get_vol(x):
                    try:
                        return float(str(x.get("totalVolume", 0)).replace(",", ""))
                    except Exception:
                        return 0.0
                
                # 현재 거래량 1위인 주력 선물 자동 선별
                top = max(items, key=get_vol)
                close_p = float(str(top.get("closePrice") or top.get("nowPrice", 0)).replace(",", ""))
                base_p = float(str(top.get("basePrice") or top.get("previousClosePrice", 0)).replace(",", ""))
                name = top.get("stockName", "코스피200 선물 최근월물")

                if 200.0 <= close_p <= 550.0 and base_p > 0:
                    diff = close_p - base_p
                    rate = (diff / base_p) * 100
                    sign = "+" if rate >= 0 else ""
                    return f"{close_p:,.2f}pt ({sign}{rate:.2f}%) [{name}]"
    except Exception as e:
        print(f"[선물 수집 오류] {e}")

    return "코스피200 선물 집계 대기"

def get_today_economic_schedule():
    """오늘 날짜 기준 공식 경제/증시 캘린더 실제 일정 수집"""
    today_dt = datetime.date.today()
    today_ymd = today_dt.strftime("%Y%m%d")
    schedules = []

    try:
        url = f"https://m.stock.naver.com/api/economic/calendar?date={today_ymd}"
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            data = res.json()
            items = data.get("calendarList", []) or data.get("list", [])
            for it in items[:6]:
                nation = it.get("nation", "")
                event = it.get("event", "") or it.get("title", "")
                time_str = it.get("time", "")
                if event:
                    prefix = f"[{nation}] " if nation else ""
                    time_prefix = f"({time_str}) " if time_str else ""
                    schedules.append(f"• {prefix}{time_prefix}{event}")
    except Exception:
        pass

    if schedules:
        return "\n".join(schedules)
    else:
        return "• 오늘 예정된 주요국 대형 경제지표 발표 없음 (장중 외환 및 수급 모니터링 중심)"

def get_global_indices_and_macro():
    """1. 순수 글로벌 주요 지수, 환율, 유가, 야간선물 수집"""
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
    """2. 나스닥, 다우, S&P 500 주요 종목 티커/가격/등락률 수집"""
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

    def format_movers(candidates, count=5):
        items = []
        for sym, name in candidates:
            val_str, rate, price = get_yfinance_ticker_data(sym)
            if val_str != "집계 대기":
                items.append((name, sym, val_str, rate, price))
        items.sort(key=lambda x: abs(x[3]), reverse=True)
        return "\n".join([f"• **{x[0]} ({x[1]}, ${x[4]:,.2f}, {'+' if x[3]>=0 else ''}{x[3]:.2f}%)**" for x in items[:count]])

    nasdaq_summary = format_movers(nasdaq_candidates, 5)
    dow_summary = format_movers(dow_candidates, 4)
    sp500_summary = format_movers(sp500_candidates, 4)

    return nasdaq_summary, dow_summary, sp500_summary

def get_morning_news(limit=10):
    """3. 장전 핵심 뉴스 헤드라인 10개 수집"""
    try:
        url = f"https://m.stock.naver.com/api/news/list?category=mainnews&page=1&pageSize={limit}"
        m_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)", "Referer": "https://m.stock.naver.com/"}
        res = requests.get(url, headers=m_headers, timeout=6)
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

def call_groq_ai(client, system_prompt, user_prompt, max_tokens=2500):
    """Groq AI 모델 안정 호출"""
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
                max_tokens=max_tokens
            )
            return res.choices[0].message.content
        except Exception as e:
            print(f"[{m}] 호출 실패: {e}")
            continue
    return ""

def generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news_list, today_schedules):
    """2단계 분할 호출로 텔레그램 글자 수 초과 없이 완결 작성"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return "GROQ API KEY 누락"

    client = Groq(api_key=api_key)
    today_str = datetime.date.today().strftime("%Y년 %m월 %d일")
    news_text = "\n".join([f"{idx+1}. {n}" for idx, n in enumerate(news_list)])

    system_prompt = f"당신은 국내 대형 증권사 수석 PB이자 글로벌 시황 애널리스트입니다. 오늘은 {today_str}입니다. 글이 잘리지 않도록 핵심 위주로 명확하고 격식 있게 서술하십시오."

    # 1차 호출: 1부, 2부, 3부 (순수 미국 및 글로벌 증시 분석)
    prompt_part1 = f"""
아래 데이터를 바탕으로 '글로벌 모닝 브리핑 1부~3부'를 작성하십시오.
반드시 [SPLIT_POINT] 구분자를 포함하여 1부, 2부, 3부를 분할하십시오.

[수집 데이터]
1. 글로벌 매크로 지표:
{market_macro}
2. 나스닥 종목:
{nasdaq_movers}
3. 다우존스 종목:
{dow_movers}
4. S&P 500 종목:
{sp_movers}

[엄격한 작성 규칙]
- **한국 주식 언급 금지**: 1부, 2부, 3부는 '순수 글로벌/미국 증시' 리포트입니다. 삼성전자, SK하이닉스, 코스피 등 한국 증시나 종목을 절대 언급하지 마십시오.
- **종목 서식 필수**: 종목명, 티커, 가격, 등락률은 반드시 **굵은 글씨(**)**로 쓰고, 설명은 일반 글씨로 간결하게 쓰십시오.
  * 예시: • **엔비디아 (NVDA, $135.20, +4.15%)**: 차세대 AI 가속기 수요 호조로 상승 마감.
- **분량 조절**: 문장이 도중에 잘리지 않도록 각 섹션당 핵심 내용 위주로 명확하게 작성하십시오.

[출력 양식]
[1부: 매크로 총평 및 주요 지표]
☀️ **간밤의 글로벌 증시 마감 총평**
- 나스닥, 다우존스, S&P 500, 필라델피아 반도체 지수의 실제 등락 수치와 퍼센트 비교 분석
- 기술주와 가치주 간의 순환매 및 시장 심리 해설

🌐 **주요 매크로 지표 심층 분석**
- 원/달러 환율 실제 수치 및 외환 동향
- WTI 국제유가 등락 배경 및 원자재 시장 영향
- 필라델피아 반도체 지수 등락 요인 해설

[SPLIT_POINT]

[2부: 나스닥 및 기술·AI 섹터 심층 분석]
💻 **나스닥(NASDAQ) 및 반도체/AI 특징주 분석**
- 수집된 나스닥 종목들의 가격/등락률을 볼드체로 명시하고 개별 등락 배경 간결 해설

📰 **장전 핵심 글로벌 이슈 5가지**
- 시장에 가장 큰 영향을 준 글로벌 핵심 이슈 5가지 선별 및 심층 분석 (1번부터 5번까지 번호 부여)

[SPLIT_POINT]

[3부: 다우존스 & S&P 500 전통 우량주 및 경기민감 섹터 분석]
🏛️ **다우존스(DOW) 산업·금융·가치주 동향**
- 수집된 다우 종목들의 가격/등락률을 볼드체로 명시하고 금융, 산업재 종목별 등락 원인 분석

🏥 **S&P 500 헬스케어·에너지·방어주 특징**
- 수집된 S&P 500 종목들의 가격/등락률을 볼드체로 명시하고 헬스케어, 에너지 섹터 흐름 분석
"""

    # 2차 호출: 4부(국내 개장 전망 및 테마), 5부(뉴스 10선, 일정, PB 실전 전략)
    prompt_part2 = f"""
아래 데이터를 바탕으로 '국내 증시 개장 전망 및 실전 전략 4부~5부'를 작성하십시오.
반드시 [SPLIT_POINT] 구분자를 포함하여 4부와 5부를 분할하십시오.

[수집 데이터]
- 글로벌 및 코스피 야간선물:
{market_macro}
- 장전 핵심 뉴스 10선:
{news_text}
- 오늘 [{today_str}] 공식 증시 캘린더:
{today_schedules}

[엄격한 작성 규칙]
- **일정 날조 금지**: 과거 기억에 의한 기업 실적 발표를 지어내지 말고, 제공된 [공식 증시 캘린더] 팩트만을 다루십시오.
- **5부 뉴스 10선**: 1번부터 10번까지 헤드라인 위주로 명확하고 깔끔하게 요약하십시오.
- **분량 조절**: 텔레그램에서 내용이 잘리지 않도록 핵심 전략 위주로 완성도 있게 마무리하십시오.

[출력 양식]
[4부: 국내 증시 개장 전망 및 주도 테마 3선]
🎯 **야간선물 점검 및 오늘 코스피/코스닥 개장 전망**
- 코스피 야간선물 수치를 바탕으로 오늘 국내 지수 시초가 분위기(갭상승/갭하락/보합) 전망
- 미국 증시 흐름이 오늘 장초반 국내 수급에 미칠 영향 분석

🚀 **오늘 주목할 국내 주도 테마 3선**
- 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 부각될 유력 테마 3가지 및 관련 수혜주

[SPLIT_POINT]

[5부: 장전 체크 뉴스 10선, 대내외 일정 및 PB 실전 전략]
🗞️ **장 시작 전 필독! 국내 증시 핵심 체크 뉴스 10선**
- 수집된 뉴스 10개를 1번부터 10번까지 번호 매김 형식으로 깔끔하게 나열

🌐 **오늘 [{today_str}] 반드시 체크해야 할 대내외 공식 일정**
- 수집된 [공식 증시 캘린더]를 바탕으로 오늘 발표될 주요 지표 및 이벤트 정리

💡 **오늘장 PB 실전 투자 전략**
1. **장초반 시초가 갭 형성 시 실전 매매 대응 원칙**
   - 갭상승 및 갭하락 출발 시 구체적 대응 수칙
2. **외국인 및 기관 실시간 수급 모니터링 체크포인트**
   - 장초반 선물 수급 변화 및 프로그램 매매 대응 기준
"""

    print("★ [1/2] 1부~3부(글로벌 증시) 생성 중...")
    res_part1 = call_groq_ai(client, system_prompt, prompt_part1, max_tokens=2500)
    
    print("★ [2/2] 4부~5부(국내 전망 및 전략) 생성 중...")
    res_part2 = call_groq_ai(client, system_prompt, prompt_part2, max_tokens=2500)

    return f"{res_part1.strip()}\n\n[SPLIT_POINT]\n\n{res_part2.strip()}"

def send_telegram(text):
    """텔레그램 4,000자 초과 방지 분할 안전 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    if "[SPLIT_POINT]" in text:
        raw_parts = text.split("[SPLIT_POINT]")
    else:
        raw_parts = [text]

    # 각 섹션이 텔레그램 글자 수 제한(4096자)을 넘지 않도록 2800자 단위 재분할
    final_messages = []
    for p in raw_parts:
        content = p.strip()
        if not content:
            continue
        if len(content) > 3000:
            final_messages.extend([content[i:i+2800] for i in range(0, len(content), 2800)])
        else:
            final_messages.append(content)

    for idx, msg in enumerate(final_messages, 1):
        # 마크다운 서식으로 전송 시도, 특수문자 에러 시 일반 텍스트 fallback
        res = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": msg})

if __name__ == "__main__":
    market_macro = get_global_indices_and_macro()
    nasdaq_movers, dow_movers, sp_movers = get_us_broad_movers()
    news_list = get_morning_news(limit=10)
    today_schedules = get_today_economic_schedule()
    print(f"★ [수집 확인] 오늘 증시 캘린더 일정:\n{today_schedules}")
    
    briefing = generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news_list, today_schedules)
    send_telegram(briefing)
