import os
import requests
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/"
}

def get_global_indices():
    """1. 미국 3대 지수 및 필라델피아 반도체 지수 수집"""
    targets = [
        ("NAS@IXIC", "나스닥"),
        ("DJI@DJI", "다우존스"),
        ("SPI@SPX", "S&P 500"),
        ("NAS@SOX", "필라델피아 반도체")
    ]
    results = []
    for code, name in targets:
        try:
            url = f"https://polling.finance.naver.com/api/realtime/world/index/{code}"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json().get("datas", [{}])[0]
            price = data.get("closePrice", "0")
            rate = data.get("fluctuationsRatio", "0")
            sign = "+" if data.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
            results.append(f"• *{name}*: {price}pt ({sign}{rate}%)")
        except Exception:
            results.append(f"• *{name}*: 집계 대기")
    return "\n".join(results)

def get_macro_indicators():
    """2. 환율, WTI 유가, 야간 코스피 선물 수집"""
    macro_items = []
    
    # 1) 원/달러 환율
    try:
        fx_url = "https://polling.finance.naver.com/api/realtime/marketindicator/exchange/FX_USDKRW"
        res = requests.get(fx_url, headers=HEADERS, timeout=10)
        data = res.json().get("datas", [{}])[0]
        price = data.get("closePrice", "0")
        rate = data.get("fluctuationsRatio", "0")
        sign = "+" if data.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
        macro_items.append(f"• *원/달러 환율*: {price}원 ({sign}{rate}%)")
    except Exception:
        macro_items.append("• *원/달러 환율*: 집계 대기")

    # 2) WTI 국제유가
    try:
        oil_url = "https://polling.finance.naver.com/api/realtime/marketindicator/oil/OIL_CL"
        res = requests.get(oil_url, headers=HEADERS, timeout=10)
        data = res.json().get("datas", [{}])[0]
        price = data.get("closePrice", "0")
        rate = data.get("fluctuationsRatio", "0")
        sign = "+" if data.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
        macro_items.append(f"• *WTI 유가*: ${price} ({sign}{rate}%)")
    except Exception:
        macro_items.append("• *WTI 유가*: 집계 대기")

    # 3) 야간 코스피200 선물 (Eurex)
    try:
        fut_url = "https://polling.finance.naver.com/api/realtime/domestic/future/KOSPI200_NIGHT"
        res = requests.get(fut_url, headers=HEADERS, timeout=10)
        data = res.json().get("datas", [{}])[0]
        price = data.get("closePrice", "0")
        rate = data.get("fluctuationsRatio", "0")
        sign = "+" if data.get("compareToPreviousPrice", {}).get("name") == "RISING" else "-"
        macro_items.append(f"• *코스피 야간 선물*: {price}pt ({sign}{rate}%)")
    except Exception:
        macro_items.append("• *코스피 야간 선물*: 장 마감 집계 참조")

    return "\n".join(macro_items)

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

def generate_morning_briefing(indices, macro, news):
    """4. Groq 대형 모델 기반 모닝 브리핑 작성"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return make_fallback_morning(indices, macro, news)

    client = Groq(api_key=api_key)
    priority_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    prompt = f"""
당신은 대형 증권사 수석 PB이자 글로벌 매크로 수석 애널리스트입니다.
간밤의 미국 증시 마감 데이터와 주요 매크로 지표, 장전 뉴스를 바탕으로 국내 VIP 투자 고객을 위한 프리미엄 아침 개장 전(장전) 모닝 브리핑을 작성해주세요.
내용이 생략되지 않도록 전문적이고 구체적인 서술을 유지하며, 아래 포맷과 [SPLIT_POINT] 구분자를 포함해 끝까지 작성하십시오.

[수집 데이터]
1. 미국 및 주요 지수:
{indices}
2. 핵심 매크로 지표 (환율/유가/야간선물):
{macro}
3. 장전 핵심 뉴스 헤드라인:
{news}

[출력 양식]
☀️ **간밤의 글로벌 증시 마감 총평**
- 다우, 나스닥, S&P 500 및 필라델피아 반도체 지수의 등락 원인과 마감 분위기 상세 해설 (4줄 이상)

🌐 **주요 매크로 지표 심층 분석**
- 원/달러 환율 흐름과 외국인 수급에 미칠 영향
- WTI 유가 변동 원인 및 인플레이션/원자재 섹터 파급 효과
- 필라델피아 반도체 지수 흐름과 국내 반도체 대형주(삼성전자, SK하이닉스) 영향도

📰 **장전 핵심 글로벌 이슈 3가지**
- 시장을 주도한 글로벌 핵심 재료 3가지를 선별해 배경 및 의미 서술 (1, 2, 3 번호 부여)

🗞️ **오늘 아침 주요 뉴스 헤드라인**
- 수집된 주요 뉴스 헤드라인 원본 목록을 불릿포인트(•)로 그대로 나열

[SPLIT_POINT]

🎯 **야간선물 점검 및 오늘 국내 증시 개장 전망**
- 코스피 야간 선물의 흐름으로 본 오늘 코스피/코스닥 예상 시초가 분위기 (상승/하락/보합 출발 여부)
- 미 증시 훈풍/한파가 국내 대형주 및 성장주에 미칠 초기 수급 방향

🚀 **오늘 주목할 주도 예상 테마 및 섹터**
- 미 증시 강세 섹터(예: AI반도체, 빅테크, 에너지, 바이오 등)와 연동되어 오늘 국내 증시에서 강세를 보일 유력 테마 3가지 및 관련 배경

💡 **오늘장 PB 실전 투자 전략**
1. 장초반 시초가 갭 형성 시 대응 원칙 (추격 매수 vs 분할 차익)
2. 오늘 중점 체크해야 할 대외 일정 및 외국인 수급 모니터링 포인트
"""

    for m in priority_models:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "당신은 증권사 수석 PB 애널리스트입니다. 냉철하고 격식 있는 한국어로 작성하십시오."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=3500
            )
            return response.choices[0].message.content
        except Exception:
            continue

    return make_fallback_morning(indices, macro, news)

def make_fallback_morning(indices, macro, news):
    return f"""☀️ **간밤의 글로벌 증시 모닝 리포트**
{indices}

🌐 **핵심 매크로 지표**
{macro}

🗞️ **장전 주요 뉴스 헤드라인**
{news}"""

def send_telegram(text):
    """5. 텔레그램 2분할 안전 전송"""
    bot_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    if "[SPLIT_POINT]" in text:
        parts = text.split("[SPLIT_POINT]")
    else:
        max_len = 3000
        parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]

    for part in parts:
        msg = part.strip()
        if not msg:
            continue
        res = requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        if res.status_code != 200:
            requests.post(url, json={"chat_id": chat_id, "text": msg})

if __name__ == "__main__":
    indices = get_global_indices()
    macro = get_macro_indicators()
    news = get_morning_news()
    
    briefing = generate_morning_briefing(indices, macro, news)
    send_telegram(briefing)
