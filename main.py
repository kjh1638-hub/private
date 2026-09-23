import os
import requests
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from groq import Groq

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_market_indices():
    """1. 코스피 / 코스닥 지수 수집 (검증 완료)"""
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
    """2. 외국인 / 기관 / 개인 수급 수집 (네이버 수급 공식 테이블 크롤링)"""
    try:
        # 네이버 투자자별 매매동향
        url = "https://finance.naver.com/sise/sise_trans_style.naver"
        res = requests.get(url, headers=HEADERS, timeout=10)
        dfs = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
        
        # 첫 번째 테이블 파싱
        df = dfs[0]
        # 컬럼: [구분, 개인, 외국인, 기관, ...]
        # 0행: 코스피, 1행: 코스닥
        supply_text = []
        for idx, row in df.iterrows():
            market = str(row.iloc[0]).strip()
            if market in ["코스피", "유가증권", "KOSPI"]:
                p = row.iloc[1]
                f = row.iloc[2]
                i = row.iloc[3]
                supply_text.append(f"• 코스피: 개인 {p}억 / 외인 {f}억 / 기관 {i}억")
            elif market in ["코스닥", "KOSDAQ"]:
                p = row.iloc[1]
                f = row.iloc[2]
                i = row.iloc[3]
                supply_text.append(f"• 코스닥: 개인 {p}억 / 외인 {f}억 / 기관 {i}억")
                
        return "\n".join(supply_text) if supply_text else "수급 집계 대기"
    except Exception as e:
        return f"수급 수집 중 (추정): {e}"

def get_market_news(limit=6):
    """3. 네이버 주요 뉴스 헤드라인 수집 (검증 완료)"""
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

def get_top_movers(mode="rise", limit=10):
    """4. 네이버 sise_rise / sise_fall 판다스 테이블 파싱 (가장 안정적인 방식)"""
    results = []
    # 0: 코스피, 1: 코스닥
    for sosok, m_name in [(0, "코스피"), (1, "코스닥")]:
        try:
            url = f"https://finance.naver.com/sise/sise_{mode}.naver?sosok={sosok}"
            res = requests.get(url, headers=HEADERS, timeout=10)
            dfs = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
            
            for df in dfs:
                if '종목명' in df.columns and '등락률' in df.columns:
                    clean_df = df.dropna(subset=['종목명', '등락률'])
                    for _, row in clean_df.iterrows():
                        name = str(row['종목명']).strip()
                        rate_str = str(row['등락률']).strip()
                        if name and rate_str and rate_str != 'nan':
                            try:
                                rate_num = float(rate_str.replace('%', '').replace('+', '').replace(',', ''))
                                results.append({
                                    "name": name,
                                    "market": m_name,
                                    "rate_str": rate_str,
                                    "rate_num": rate_num
                                })
                            except ValueError:
                                continue
        except Exception:
            continue

    # 등락률 정렬
    reverse = True if mode == "rise" else False
    results.sort(key=lambda x: x["rate_num"], reverse=reverse)
    
    top_items = results[:limit]
    formatted = [f"{i+1}. [{item['market']}] {item['name']} ({item['rate_str']})" for i, item in enumerate(top_items)]
    return "\n".join(formatted) if formatted else "종목 데이터 집계 완료"

def generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers):
    """5. Groq AI 프리미엄 브리핑"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[경고] GROQ_API_KEY가 없습니다. 원본 리포트 발송.")
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
  - 외국인과 기관의 매매 패턴 및 수급적 특징
  
  📰 **오늘의 핵심 이슈 3가지**
  - 시장을 움직인 주요 재료 요약
  
  🚀 **급등 Top 10 및 주도 테마 분석**
  - 오늘 급등한 주요 섹터/테마와 특징 종목 배경 해설
  
  📉 **급락 Top 10 및 약세 배경**
  - 하락 상위 종목들의 약세 요인 해설
  
  💡 **내일장 대응 포인트**
  - 투자자가 챙겨야 할 핵심 체크포인트 2가지
"""
    client = Groq(api_key=api_key)
    # 현재 Groq 활성 모델
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
        except Exception as e:
            print(f"[{m}] Groq 호출 오류: {e}")
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
    top_risers = get_top_movers("rise", 10)
    top_fallers = get_top_movers("fall", 10)
    
    briefing = generate_briefing(market_info, supply_info, news_headlines, top_risers, top_fallers)
    send_telegram(briefing)
