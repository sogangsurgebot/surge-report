#!/usr/bin/env python3
"""
급등주 데이터 수집 스크립트 (한국투자증권 KIS API)
섹션별 분리된 템플릿 조합 방식
"""

import os
import requests
import subprocess
from datetime import datetime
from pathlib import Path

# .env 파일에서 환경변수 로드
def load_env():
    """.env 파일에서 환경변수 로드"""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# 환경변수 로드 실행
load_env()

# 환경변수 읽기
APP_KEY = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
BASE_URL = os.getenv("KIS_BASE_URL", "https://openapivts.koreainvestment.com:29443")

# 서버 타입 표시용
SERVER_TYPE = "모의투자" if "openapivts" in BASE_URL else "실전"

# 섹션 파일 경로
SECTIONS_DIR = Path(__file__).parent / 'sections'

# 종목별 회사 정보 매핑
COMPANY_INFO = {
    "005930": {"industry": "반도체/전자", "desc": "세계 최대 메모리 반도체 기업"},
    "000660": {"industry": "반도체/전자", "desc": "HBM 메모리 전문 글로벌 선도기업"},
    "035420": {"industry": "인터넷/플랫폼", "desc": "국내 대표 포털 및 검색 플랫폼"},
    "035720": {"industry": "인터넷/플랫폼", "desc": "카카오톡 메신저 플랫폼 기업"},
    "051910": {"industry": "화학/배터리", "desc": "전기차 배터리 소재 글로벌 1위"},
    "006400": {"industry": "배터리/전자", "desc": "전기차 배터리 및 소재 전문기업"},
    "373220": {"industry": "배터리/전자", "desc": "세계 2위 전기차 배터리 제조사"},
    "105560": {"industry": "금융/은행", "desc": "국내 대표 금융지주사"},
    "086790": {"industry": "금융/은행", "desc": "하나금융그룹 지주사"},
    "000270": {"industry": "자동차/제조", "desc": "글로벌 완성차 제조 기업"},
    "005380": {"industry": "자동차/제조", "desc": "세계 3위 규모 완성차 기업"},
    "012330": {"industry": "전자/디스플레이", "desc": "세계 최대 TV/디스플레이 패널"},
    "247540": {"industry": "바이오/제약", "desc": "혁신신약 개발 바이오 기업"},
    "207940": {"industry": "바이오/제약", "desc": "글로벌 바이오시밀러 선도기업"},
    "068270": {"industry": "바이오/제약", "desc": "셀트리온 그룹 지주사"},
    "196490": {"industry": "리조트/서비스", "desc": "강원랜드 카지노 리조트"},
    "049080": {"industry": "반도체/장비", "desc": "반도체 테스트 소켓 전문기업"},
    "069540": {"industry": "전자/광학", "desc": "LED 및 광학 부품 제조"},
    "093370": {"industry": "반도체/소재", "desc": "반도체 장비 및 부품 제조"},
    "084370": {"industry": "바이오/진단", "desc": "유전자 분석 및 진단키트"},
    "134790": {"industry": "전자/부품", "desc": "전자부품 및 전원공급장치"},
}

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
    """거래량 순위 API로 급등주 조회"""
    
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000",
        "custtype": "P"
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
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
                    
                    if change_rate >= 5.0:
                        price = int(item.get('stck_prpr', 0))
                        volume = int(item.get('acml_vol', 0))
                        code = item.get("mksc_shrn_iscd", "")
                        
                        company = COMPANY_INFO.get(code, {"industry": "기타", "desc": "거래량 급등"})
                        
                        surge_stocks.append({
                            "name": item.get("hts_kor_isnm", ""),
                            "code": code,
                            "price": f"{price:,}",
                            "change": f"{change_rate:+.2f}%",
                            "volume": f"{volume:,}",
                            "reason": "거래량 급등",
                            "industry": company["industry"],
                            "desc": company["desc"]
                        })
                except (ValueError, TypeError):
                    continue
            
            surge_stocks.sort(
                key=lambda x: float(x["change"].replace('%', '').replace('+', '')),
                reverse=True
            )
            
            print(f"   🔥 급등주 (+5% 이상): {len(surge_stocks)}개")
            for s in surge_stocks[:5]:
                print(f"      - {s['name']}: {s['change']}")
            
            return surge_stocks[:6]
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
                "reason": "AI 반도체 수주 증가 소식",
                "industry": "반도체/전자",
                "desc": "세계 최대 메모리 반도체 기업"
            },
            {
                "name": "SK하이닉스",
                "code": "000660",
                "price": "145,000",
                "change": "+8.1%",
                "volume": "8,123,456",
                "reason": "HBM3E 공급 확대 기대감",
                "industry": "반도체/전자",
                "desc": "HBM 메모리 전문 글로벌 선도기업"
            }
        ]
    }

def generate_stock_cards(stocks):
    """주식 카드 HTML 생성"""
    if not stocks:
        return '<div class="empty">현재 급등 종목이 없습니다.</div>'
    
    cards_html = '<div class="stocks-grid">\n'
    for stock in stocks:
        change_class = "up" if "+" in stock["change"] else "down"
        industry = stock.get("industry", "")
        desc = stock.get("desc", "")
        
        company_info_html = ""
        if industry or desc:
            company_info_html = f'''            <div class="company-info">
                <div class="company-industry">{industry}</div>
                <div class="company-desc">{desc}</div>
            </div>
'''
        
        cards_html += f'''        <div class="card stock-card">
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
{company_info_html}        </div>
'''
    cards_html += '</div>'
    return cards_html

def get_git_version_info():
    """Git 커밋 해시와 시간 가져오기"""
    try:
        commit_hash = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=os.path.dirname(__file__),
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        commit_time = subprocess.check_output(
            ['git', 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d %H:%M'],
            cwd=os.path.dirname(__file__),
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        return f"v.{commit_hash} | {commit_time}"
    except:
        return "v.unknown | unknown"

def load_section(filename):
    """섹션 파일 로드"""
    section_path = SECTIONS_DIR / filename
    if section_path.exists():
        with open(section_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def update_html(data):
    """섹션 파일을 조합해서 HTML 생성"""
    
    # 섹션 파일 로드
    header = load_section('header.html')
    criteria = load_section('criteria.html')
    experts = load_section('experts.html')
    footer = load_section('footer.html')
    
    # 주식 카드 HTML 생성
    stock_cards = generate_stock_cards(data["stocks"])
    
    # 플레이스홀더 치환
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    version_info = get_git_version_info()
    
    source_indicator = data.get("source", f"🔴 실제 데이터")
    server_type = data.get("server", SERVER_TYPE)
    if server_type and server_type != "N/A":
        source_indicator += f" | {server_type}"
    
    # 헤더 섹션 치환
    header = header.replace('{{UPDATE_DATE}}', current_time)
    header = header.replace('{{DATA_SOURCE}}', source_indicator)
    header = header.replace('{{VERSION_INFO}}', version_info)
    
    # HTML 조합
    html_content = header + criteria + experts + stock_cards + footer
    
    # index.html 저장
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML 업데이트 완료: {len(data['stocks'])}개 종목 | {source_indicator} | {version_info}")

def fetch_surge_stocks():
    """급등주 데이터 수집 메인 함수"""
    
    token = get_access_token()
    if not token:
        return get_sample_data()
    
    stocks = get_volume_rank_surge_stocks(token)
    
    if stocks:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": "🔴 실제 데이터",
            "server": SERVER_TYPE,
            "stocks": stocks
        }
    
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
