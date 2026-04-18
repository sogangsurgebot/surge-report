#!/usr/bin/env python3
"""
급등주 데이터 수집 스크립트 (한국투자증권 KIS API)
거래량 순위 API 활용 - 모의투자/실전 모두 지원
"""

import os
import requests
from datetime import datetime

# 환경변수 로드
APP_KEY = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
BASE_URL = os.getenv("KIS_BASE_URL", "https://openapivts.koreainvestment.com:29443")

# 서버 타입 표시용
SERVER_TYPE = "모의투자" if "openapivts" in BASE_URL else "실전"

def get_access_token():
    """Access Token 발급"""
    if not APP_KEY or not APP_SECRET:
        print("⚠️ API 키 없음, 샘플 데이터 사용")
        return None
    
    url = f"{BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    try:
        resp = requests.post(url, json=body, timeout=10)
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            print(f"✅ 토큰 발급 성공 ({SERVER_TYPE})")
            return token
        elif resp.status_code == 403:
            print("⚠️ 토큰 rate limit - 1분 후 재시도 필요")
            return None
    except Exception as e:
        print(f"❌ Token 오류: {e}")
    
    return None

def get_volume_rank_surge_stocks(token):
    """
    거래량 순위 API로 급등주 조회
    모의투자/실전 모두 지원 (TR_ID: FHPST01710000)
    """
    
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000",  # 모의투자/실전 공용
        "custtype": "P"
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000",  # 전체
        "FID_DIV_CLS_CODE": "0",   # 전체
        "FID_BLNG_CLS_CODE": "0",  # 평균거래량
        "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }
    
    try:
        print(f"🔍 거래량 순위 API 호출 ({SERVER_TYPE})...")
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        
        print(f"   응답 코드: {data.get('rt_cd')} | {data.get('msg1', '')}")
        
        if data.get("rt_cd") == "0":
            outputs = data.get("output", [])
            print(f"   총 {len(outputs)}개 종목 조회됨")
            
            surge_stocks = []
            for item in outputs:
                try:
                    change_rate = float(item.get("prdy_ctrt", 0))
                    
                    # 급등주 조건: 등락률 +5% 이상
                    if change_rate >= 5.0:
                        price = int(item.get('stck_prpr', 0))
                        volume = int(item.get('acml_vol', 0))
                        
                        surge_stocks.append({
                            "name": item.get("hts_kor_isnm", ""),
                            "code": item.get("mksc_shrn_iscd", ""),
                            "price": f"{price:,}",
                            "change": f"{change_rate:+.2f}%",
                            "volume": f"{volume:,}",
                            "reason": "거래량 급등"
                        })
                except (ValueError, TypeError):
                    continue
            
            # 등락률 높은 순 정렬
            surge_stocks.sort(
                key=lambda x: float(x["change"].replace('%', '').replace('+', '')),
                reverse=True
            )
            
            print(f"   🔥 급등주 (+5% 이상): {len(surge_stocks)}개")
            for s in surge_stocks[:5]:
                print(f"      - {s['name']}: {s['change']}")
            
            return surge_stocks[:10]  # 상위 10개
        else:
            print(f"   ❌ API 오류: {data.get('msg1', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ API 호출 예외: {e}")
    
    return []

def get_sample_data():
    """샘플 데이터 (API 실패 시 폴백)"""
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "source": "📋 샘플 데이터",
        "server": "N/A",
        "stocks": [
            {
                "name": "삼성전자",
                "code": "005930",
                "price": "72,300",
                "change": "+5.2%",
                "volume": "15,234,567",
                "reason": "AI 반도체 수주 증가 소식"
            },
            {
                "name": "SK하이닉스",
                "code": "000660",
                "price": "145,000",
                "change": "+8.1%",
                "volume": "8,123,456",
                "reason": "HBM3E 공급 확대 기대감"
            }
        ]
    }

def generate_stock_cards(stocks):
    """주식 카드 HTML 생성"""
    if not stocks:
        return '<div class="empty">현재 급등 종목이 없습니다.</div>'
    
    cards_html = ""
    for stock in stocks:
        change_class = "up" if "+" in stock["change"] else "down"
        cards_html += f'''
        <div class="card stock-card">
            <div class="stock-header">
                <div>
                    <div class="stock-name">{stock["name"]}</div>
                    <div class="stock-code">{stock["code"]}</div>
                </div>
                <span class="surge-badge">급등 🔥</span>
            </div>
            <div class="price-info">
                <div class="price-item">
                    <div class="price-label">현재가</div>
                    <div class="price-value">{stock["price"]}</div>
                </div>
                <div class="price-item">
                    <div class="price-label">등락률</div>
                    <div class="price-value {change_class}">{stock["change"]}</div>
                </div>
                <div class="price-item">
                    <div class="price-label">거래량</div>
                    <div class="price-value">{stock["volume"]}</div>
                </div>
            </div>
            <div class="reason">
                📊 {stock["reason"]}
            </div>
        </div>
'''
    return cards_html

def update_html(data):
    """템플릿 파일을 읽어서 데이터 치환 후 HTML 생성"""
    
    template_path = os.path.join(os.path.dirname(__file__), 'template.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    stock_cards = generate_stock_cards(data["stocks"])
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_content = template.replace('{{UPDATE_DATE}}', current_time)
    html_content = html_content.replace('{{STOCK_CARDS}}', stock_cards)
    
    # 데이터 소스 표시 (실제 vs 샘플, 서버 타입)
    source_indicator = data.get("source", f"🔴 실제 데이터")
    server_type = data.get("server", SERVER_TYPE)
    if server_type and server_type != "N/A":
        source_indicator += f" | {server_type}"
    html_content = html_content.replace('{{DATA_SOURCE}}', source_indicator)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML 업데이트 완료: {len(data['stocks'])}개 종목 | {source_indicator}")

def fetch_surge_stocks():
    """급등주 데이터 수집 메인 함수"""
    
    token = get_access_token()
    if not token:
        return get_sample_data()
    
    # 거래량 순위 API로 급등주 조회
    stocks = get_volume_rank_surge_stocks(token)
    
    if stocks:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "🔴 실제 데이터",
            "server": SERVER_TYPE,
            "stocks": stocks
        }
    
    # API 실패 시 샘플 데이터
    print("⚠️ API 실패, 샘플 데이터 사용")
    return get_sample_data()

def main():
    print(f"🚀 급등주 데이터 수집 시작: {datetime.now()}")
    print(f"   서버: {BASE_URL} ({SERVER_TYPE})")
    
    data = fetch_surge_stocks()
    update_html(data)
    
    print("✨ 작업 완료!")

if __name__ == "__main__":
    main()
