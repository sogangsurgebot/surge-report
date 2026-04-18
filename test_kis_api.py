#!/usr/bin/env python3
"""
한국투자증권 KIS Open API 테스트 스크립트
실제 API 연결 전 모의투자로 테스트
"""

import requests
import json
from datetime import datetime

# ==========================================
# 설정 (발급받은 키 입력)
# ==========================================
APP_KEY = "YOUR_APP_KEY_HERE"          # 앱키
APP_SECRET = "YOUR_APP_SECRET_HERE"    # 앱시크릿
ACCOUNT_NUMBER = "YOUR_ACCOUNT_NUMBER"  # 계좌번호 (8자리)

# 모의투자 도메인 (실제 도메인과 다름)
BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자
# 실전: "https://openapi.koreainvestment.com:9443"

# ==========================================
# 1. Access Token 발급
# ==========================================
def get_access_token():
    """Access Token 발급 (2시간 유효)"""
    
    url = f"{BASE_URL}/oauth2/tokenP"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    response = requests.post(url, headers=headers, json=body)
    
    if response.status_code == 200:
        token = response.json().get("access_token")
        print(f"✅ Access Token 발급 성공: {token[:20]}...")
        return token
    else:
        print(f"❌ Token 발급 실패: {response.text}")
        return None

# ==========================================
# 2. 주식현재가 시세 조회 (단일 종목)
# ==========================================
def get_stock_price(token, stock_code):
    """특정 종목 현재가 조회"""
    
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"  # 주식현재가 시세
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식
        "FID_INPUT_ISCD": stock_code     # 종목코드 (6자리)
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("rt_cd") == "0":
            output = data.get("output", {})
            return {
                "name": output.get("hts_kor_isnm", "Unknown"),  # 한글종목명
                "code": stock_code,
                "price": output.get("stck_prpr", "0"),         # 현재가
                "change": output.get("prdy_vrss", "0"),        # 전일대비
                "change_rate": output.get("prdy_ctrt", "0"),   # 등락률
                "volume": output.get("acml_vol", "0")          # 누적거래량
            }
    
    print(f"❌ 조회 실패: {response.text}")
    return None

# ==========================================
# 3. 거래량 상위 종목 조회 (급등주 필터링용)
# ==========================================
def get_volume_rank(token, market="0000", rank_count=10):
    """
    거래량 순위 조회
    market: 0000(전체), 0001(코스피), 1001(코스닥), 2001(코스피200)
    """
    
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01710000"  # 거래량 순위
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": market,
        "FID_COND_SCR_DIV_CODE": "20170",
        "FID_INPUT_ISCD": market,
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("rt_cd") == "0":
            outputs = data.get("output", [])
            
            stocks = []
            for item in outputs[:rank_count]:
                change_rate = float(item.get("prdy_ctrt", 0))
                
                # 급등주 조건: 등락률 +5% 이상
                if change_rate >= 5.0:
                    stocks.append({
                        "name": item.get("hts_kor_isnm", ""),
                        "code": item.get("mksc_shrn_iscd", ""),
                        "price": item.get("stck_prpr", ""),
                        "change": f"{change_rate:+.2f}%",
                        "volume": format(int(item.get("acml_vol", 0)), ",")
                    })
            
            return stocks
    
    print(f"❌ 순위 조회 실패: {response.text}")
    return []

# ==========================================
# 메인 실행
# ==========================================
if __name__ == "__main__":
    print("=" * 50)
    print("한국투자증권 API 테스트")
    print("=" * 50)
    
    # 1. 토큰 발급
    token = get_access_token()
    if not token:
        print("❌ API 키를 확인하세요!")
        exit(1)
    
    # 2. 단일 종목 테스트
    print("\n📊 삼성전자 현재가 조회:")
    samsung = get_stock_price(token, "005930")
    if samsung:
        print(f"  종목: {samsung['name']} ({samsung['code']})")
        print(f"  현재가: {samsung['price']}")
        print(f"  등락률: {samsung['change_rate']}%")
        print(f"  거래량: {samsung['volume']}")
    
    # 3. 거래량 상위 + 급등주 조회
    print("\n🔥 거래량 상위 급등주 (+5% 이상):")
    surge_stocks = get_volume_rank(token, market="0000", rank_count=20)
    
    if surge_stocks:
        for i, stock in enumerate(surge_stocks[:5], 1):
            print(f"  {i}. {stock['name']} ({stock['code']})")
            print(f"     현재가: {stock['price']} | 등락률: {stock['change']}")
    else:
        print("  급등주 없음 또는 API 오류")
    
    print("\n✅ 테스트 완료!")
