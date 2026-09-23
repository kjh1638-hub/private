import os
import re
import datetime
import requests
import yfinance as yf
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
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
    """Eurex 코스피200 야간선물 글로벌 직결 게이트웨이 (해외 IP 완벽 호환)"""
    
    # 1. Investing.com 글로벌 선물 API (KOSPI 200 지수선물 최근월물)
    try:
        inv_url = "https://api.investing.com/api/financialdata/8880/historical/chart/?interval=PT1M&pointscnt=10"
        inv_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": "https://kr.investing.com/"
        }
        res = requests.get(inv_url, headers=inv_headers, timeout=8)
        if res.status_code == 200:
            data = res.json().get("data", [])
            if len(data) >= 2:
                latest_p = float(data[-1][1])
                prev_p = float(data[0][1])
                diff = latest_p - prev_p
                rate = (diff / prev_p) * 100
                sign = "+" if rate >= 0 else ""
                if 250.0 <= latest_p <= 550.0:
                    return f"{latest_p:,.2f}pt ({sign}{rate:.2f}%) [Eurex 야간선물]"
    except Exception as e:
        print(f"[선물 수집 1차 인베스팅] {e}")

    # 2. 인베스팅 모바일 웹 다이렉트 파싱 백업
    try:
        url = "https://m.investing.com/indices/korea-200-futures"
        m_headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15"}
        res = requests.get(url, headers=m_headers, timeout=8)
        if res.status_code == 200:
            html = res.text
            p_m = re.search(r'data-test="instrument-price-last"[^>]*>([0-9,.]+)<', html)
            r_m = re.search(r'data-test="instrument-price-change-percent"[^>]*>([+-]?[0-9,.]+)%?<', html)
            if p_m and r_m:
                p_val = float(p_m.group(1).replace(",", ""))
                r_val = float(r_m.group(1).replace(",", "").replace("+", ""))
                sign = "+" if r_val >= 0 else ""
                if 250.0 <= p_val <= 550.0:
                    return f"{p_val:,.2f}pt ({sign}{r_val:.2f}%) [Eurex 야간선물]"
    except Exception as e:
        print(f"[선물 수집 2차 인베스팅 웹] {e}")

    # 3. 네이버 모바일 통합 지표 (Reuters KOSPI 200 선물)
    try:
        n_url = "https://m.stock.naver.com/front-api/v1/marketIndex/prices?category=futures&reutersCode=10100"
        res = requests.get(n_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            res_data = res.json().get("result", [])
            if res_data:
                p = res_data[0].get("closePrice")
                r = res_data[0].get("fluctuationsRatio")
                comp = res_data[0].get("compareToPreviousClosePrice", "")
                if p and r:
                    r_clean = str(r).replace("%", "").strip()
                    sign = "+" if comp == "2" or (not r_clean.startswith("-") and float(r_clean) > 0) else ""
                    p_clean = float(str(p).replace(",", ""))
                    if 250.0 <= p_clean <= 550.0:
                        return f"{p}pt ({sign}{r_clean}%) [코스피200 선물]"
    except Exception as e:
        print(f"[선물 수집 3차 네이버] {e}")

    return "장 마감 정산 확인"

def get_today_economic_schedule():
    """오늘 날짜 기준 공식 경제/증시 캘린더 실제 일정 수집"""
    today_dt = datetime.date.today()
    today_ymd = today_dt.strftime("%Y%m%d")
    schedules = []

    try:
        url = f"https://m.stock.naver.com/api/economic/calendar?date={today_ymd}"
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            items = data.get("calendarList", []) or data.get("list", [])
            for it in items[:8]:
                nation = it.get("nation", "")
                event = it.get("event", "") or it.get("title", "")
                time_str = it.get("time", "")
                if event:
                    prefix = f"[{nation}] " if nation else ""
                    time_prefix = f"({time_str}) " if time_str else ""
                    schedules.append(f"• {prefix}{time_prefix}{event}")
    except Exception as e:
        print(f"[캘린더 수집 1차] {e}")

    try:
        url_sub = f"https://m.stock.naver.com/api/calendar/event?date={today_ymd}"
        res = requests.get(url_sub, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            events = data.get("events", [])
            for ev in events[:5]:
                tit = ev.get("title", "")
                if tit:
                    schedules.append(f"• [국내 증시] {tit}")
    except Exception as e:
        print(f"[캘린더 수집 2차] {e}")

    if schedules:
        return "\n".join(schedules)
    else:
        return "• 오늘 예정된 주요국 대형 경제지표 및 특이 증시 일정 없음 (장중 외환/외국인 선물 수급 중심 장세)"

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
        # 종목명, 티커, 가격, 등락률을 굵은 글씨로 고정
        return "\n".join([f"• **{x[0]} ({x[1]}, ${x[4]:,.2f}, {'+' if x[3]>=0 else ''}{x[3]:.2f}%)**" for x in items[:count]])

    nasdaq_summary = format_movers(nasdaq_candidates, 6)
    dow_summary = format_movers(dow_candidates, 5)
    sp500_summary = format_movers(sp500_candidates, 4)

    return nasdaq_summary, dow_summary, sp500_summary

def get_morning_news(limit=20):
    """3. 장전 핵심 뉴스 헤드라인 20개 수집"""
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

def call_groq_ai(client, system_prompt, user_prompt, max_tokens=3200):
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
    """4. 3단계 분할 호출로 1부~6부 내용 축소 없이 완벽 작성"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return "GROQ API KEY 누락"

    client = Groq(api_key=api_key)
    today_str = datetime.date.today().strftime("%Y년 %m월 %d일")
    news_text = "\n".join([f"{idx+1}. {n}" for idx, n in enumerate(news_list)])

    system_prompt = f"당신은 국내 대형 증권사 수석 PB이자 글로벌 시황 애널리스트입니다. 오늘은 {today_str}입니다. 내용을 임의로 줄이거나 축약하지 말고 깊이 있게 작성하십시오."

    # 1차 호출: 1부, 2부, 3부 (글로벌 지표 및 미국 3대 지수 분석)
    prompt_part1 = f"""
아래 수집 데이터를 기반으로 '글로벌 모닝 브리핑 1부~3부'를 매우 깊이 있고 상세하게 작성하십시오.
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

[작성 및 서식 규칙]
- **종목 서식 필수**: 종목명, 티커, 가격, 등락률은 반드시 **굵은 글씨(**)**로 쓰고, 뒤따르는 원인 설명은 일반 글씨(연한 글씨)로 작성하십시오.
  * 예시: • **엔비디아 (NVDA, $135.20, +4.15%)**: 차세대 AI 가속기 수요 견조로 상승세 지속...

[출력 양식]
[1부: 매크로 총평 및 주요 지표]
☀️ **간밤의 글로벌 증시 마감 총평**
- 나스닥, 다우존스, S&P 500, 필라델피아 반도체 지수의 실제 등락 수치와 퍼센트를 구체적으로 비교 분석
- 기술주(나스닥)와 가치주(다우) 간의 순환매 및 투자 심리 상세 해설 (충분한 분량 서술)

🌐 **주요 매크로 지표 심층 분석**
- 원/달러 환율 실제 수치 및 외국인 수급 영향도 분석
- WTI 국제유가 등락 배경 및 원자재/물가 경로 분석
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
- 수집된 다우 종목들의 가격/등락률을 볼드체로 명시하고 금융, 산업재, 방산 종목별 등락 요인 분석

🏥 **S&P 500 헬스케어·에너지·방어주 특징**
- 수집된 S&P 500 종목들의 가격/등락률을 볼드체로 명시하고 바이오, 에너지, 소비재 흐름 분석
"""

    # 2차 호출: 4부(개장 전망 & 주도 테마 3선), 5부(뉴스 20선)
    prompt_part2 = f"""
아래 수집 데이터를 기반으로 '국내 증시 개장 전망 및 장전 체크 뉴스 20선 4부~5부'를 작성하십시오.
반드시 [SPLIT_POINT] 구분자를 포함하여 4부와 5부를 분할하십시오.

[수집 데이터]
- 글로벌 및 코스피 야간선물:
{market_macro}
- 장전 핵심 뉴스 헤드라인 20선:
{news_text}

[작성 지침]
- **야간선물 분석**: 코스피 야간선물 수치(포인트 및 등락률)를 바탕으로 오늘 코스피/코스닥의 시초가 갭 방향(상승/하락/보합)을 명확하게 짚어주십시오.
- **국내 주도 테마 3선**: 간밤 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 가장 강하게 부각될 유력 테마 3가지를 구체적인 국내 관련 수혜 종목군과 함께 명확히 제시하십시오.
- **5부 뉴스 20선**: 수집된 뉴스 20개를 1번부터 20번까지 빠짐없이 번호를 매겨 누락 없이 충실하게 요약 정리하십시오.

[출력 양식]
[4부: 국내 증시 개장 전망 및 주도 테마 3선]
🎯 **야간선물 점검 및 오늘 코스피/코스닥 개장 전망**
- 코스피 야간선물 흐름을 바탕으로 오늘 국내 지수 시초가 분위기(갭상승/갭하락/보합) 전망
- 미국 증시 흐름이 오늘 장초반 국내 외국인/기관 수급에 미칠 영향 분석

🚀 **오늘 주목할 국내 주도 테마 3선**
- 미 증시 강세 섹터와 연동되어 오늘 국내 증시에서 부각될 유력 테마 3가지 및 관련 수혜주

[SPLIT_POINT]

[5부: 장 시작 전 필독! 국내 증시 핵심 체크 뉴스 20선]
🗞️ **오늘 아침 주요 뉴스 헤드라인 20선**
- 수집된 뉴스 20개를 기반으로 오늘 장전 투자자가 반드시 알아야 할 국내외 핵심 뉴스 20가지를 1번부터 20번까지 빠짐없이 요약 정리
"""

    # 3차 호출: 6부(대내외 일정 및 PB 실전 전략)
    prompt_part3 = f"""
아래 데이터를 바탕으로 '대내외 공식 증시 일정 및 오늘장 PB 실전 투자 전략 6부'를 완결성 있게 작성하십시오.

[수집 데이터]
- 오늘 [{today_str}] 공식 증시 캘린더 일정:
{today_schedules}

[작성 및 환각 방지 지침]
- 과거 기억이나 개별 기업 실적발표를 허위로 지어내지 마십시오.
- 오직 위에 제공된 [공식 증시 캘린더 일정]과 실제 거시 변수(외환시장, 금리)만을 바탕으로 오늘 일정을 정리하십시오.

[출력 양식]
[6부: 대내외 주요 일정 및 PB 실전 투자 전략]
🌐 **오늘 [{today_str}] 반드시 체크해야 할 대내외 공식 일정**
- 수집된 [공식 증시 캘린더 일정]을 바탕으로 오늘 발표될 주요국 경제지표 및 국내 증시 이벤트를 불릿포인트(•)로 정리

💡 **오늘장 PB 실전 투자 전략**
1. **장초반 시초가 갭 형성 시 실전 매매 대응 원칙**
   - 갭상승 출발 시 대응 전략 (추격 매수 자제 구간 및 분할 매도 기준)
   - 갭하락 출발 시 대응 전략 (저가 분할 매수 타이밍 및 리스크 관리선)
2. **외국인 및 기관 실시간 수급 모니터링 체크포인트**
   - 장초반 선물 수급 변화 및 프로그램 매매 방향성에 따른 포트폴리오 관리 원칙
"""

    print("★ [1/3] 1부~3부 생성 중...")
    res_part1 = call_groq_ai(client, system_prompt, prompt_part1, max_tokens=3200)
    
    print("★ [2/3] 4부~5부 생성 중...")
    res_part2 = call_groq_ai(client, system_prompt, prompt_part2, max_tokens=3200)

    print("★ [3/3] 6부 생성 중...")
    res_part3 = call_groq_ai(client, system_prompt, prompt_part3, max_tokens=2000)

    full_briefing = f"{res_part1.strip()}\n\n[SPLIT_POINT]\n\n{res_part2.strip()}\n\n[SPLIT_POINT]\n\n{res_part3.strip()}"
    return full_briefing

def send_telegram(text):
    """5. 텔레그램 6분할 안전 전송"""
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
    news_list = get_morning_news(limit=20)
    today_schedules = get_today_economic_schedule()
    print(f"★ [수집 확인] 오늘 증시 캘린더 일정:\n{today_schedules}")
    
    briefing = generate_morning_briefing(market_macro, nasdaq_movers, dow_movers, sp_movers, news_list, today_schedules)
    send_telegram(briefing)
