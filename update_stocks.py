#!/usr/bin/env python3
"""
급등주 데이터 수집 스크립트 (한국투자증권 KIS API) - 개선판
정교한 급등주 선정 로직 및 UI 최적화

[UI 개선]
- 국내 주식 상단 전체 너비 배치
- 나스닥 하단 축소/접기 가능 섹션
- KOSPI/KOSDAQ 시장 구분 표시
"""

import os
import requests
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

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

# 선정 기준 상수
MIN_PRICE_CHANGE = 5.0          # 최소 등락률 5%
MIN_TRADE_AMOUNT = 100e8        # 최소 거래대금 100억
MIN_MARKET_CAP = 500e8          # 최소 시총 500억
MIN_SCORE_STRONG = 10           # 강한 알림 기준
MIN_SCORE_NORMAL = 7            # 일반 알림 기준

# 점수 가중치
WEIGHT_PRICE_CHANGE = 2.5       # 등락률 가중치
WEIGHT_VOLUME = 2.0             # 거래량 비율 가중치
WEIGHT_TRADE_AMOUNT = 1.5       # 거래대금 가중치
WEIGHT_MARKET_CAP = 1.0         # 시총 가중치


@dataclass
class StockScore:
    """종목 점수 데이터"""
    code: str
    name: str
    market: str  # KOSPI, KOSDAQ
    total_score: float
    price_change: float
    trade_amount: int
    market_cap: int
    alert_level: str
    details: Dict


# 종목별 회사 정보 및 시장 구분
COMPANY_INFO = {
    # KOSPI
    "005930": {"industry": "반도체/전자", "desc": "세계 최대 메모리 반도체 기업", "market": "KOSPI"},
    "000660": {"industry": "반도체/전자", "desc": "HBM 메모리 전문 글로벌 선도기업", "market": "KOSPI"},
    "035420": {"industry": "인터넷/플랫폼", "desc": "국내 대표 포털 및 검색 플랫폼", "market": "KOSPI"},
    "035720": {"industry": "인터넷/플랫폼", "desc": "카카오톡 메신저 플랫폼 기업", "market": "KOSPI"},
    "051910": {"industry": "화학/배터리", "desc": "전기차 배터리 소재 글로벌 1위", "market": "KOSPI"},
    "006400": {"industry": "배터리/전자", "desc": "전기차 배터리 및 소재 전문기업", "market": "KOSPI"},
    "373220": {"industry": "배터리/전자", "desc": "세계 2위 전기차 배터리 제조사", "market": "KOSPI"},
    "105560": {"industry": "금융/은행", "desc": "국내 대표 금융지주사", "market": "KOSPI"},
    "086790": {"industry": "금융/은행", "desc": "하나금융그룹 지주사", "market": "KOSPI"},
    "000270": {"industry": "자동차/제조", "desc": "글로벌 완성차 제조 기업", "market": "KOSPI"},
    "005380": {"industry": "자동차/제조", "desc": "세계 3위 규모 완성차 기업", "market": "KOSPI"},
    "012330": {"industry": "전자/디스플레이", "desc": "세계 최대 TV/디스플레이 패널", "market": "KOSPI"},
    "207940": {"industry": "바이오/제약", "desc": "글로벌 바이오시밀러 선도기업", "market": "KOSPI"},
    "068270": {"industry": "바이오/제약", "desc": "셀트리온 그룹 지주사", "market": "KOSPI"},
    # KOSDAQ
    "247540": {"industry": "바이오/제약", "desc": "혁신신약 개발 바이오 기업", "market": "KOSDAQ"},
    "049080": {"industry": "반도체/장비", "desc": "반도체 테스트 소켓 전문기업", "market": "KOSDAQ"},
    "069540": {"industry": "전자/광학", "desc": "LED 및 광학 부품 제조", "market": "KOSDAQ"},
    "093370": {"industry": "반도체/소재", "desc": "반도체 장비 및 부품 제조", "market": "KOSDAQ"},
    "084370": {"industry": "바이오/진단", "desc": "유전자 분석 및 진단키트", "market": "KOSDAQ"},
    "134790": {"industry": "전자/부품", "desc": "전자부품 및 전원공급장치", "market": "KOSDAQ"},
    "196490": {"industry": "리조트/서비스", "desc": "강원랜드 카지노 리조트", "market": "KOSDAQ"},
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


def calculate_stock_score(item: dict, market_type: str = "KOSPI") -> Optional[StockScore]:
    """
    종목 점수 계산
    """
    try:
        code = item.get("mksc_shrn_iscd", "")
        name = item.get("hts_kor_isnm", "")
        price_change = float(item.get("prdy_ctrt", 0))
        price = int(item.get('stck_prpr', 0))
        volume = int(item.get('acml_vol', 0))
        
        # 거래대금 계산
        trade_amount = price * volume
        
        # 시총
        market_cap_str = item.get("hts_avls", "0").replace(",", "")
        market_cap = int(market_cap_str) * 1e8 if market_cap_str else 0
        
        # 기본 필터링
        if price_change < MIN_PRICE_CHANGE:
            return None
        if trade_amount < MIN_TRADE_AMOUNT:
            return None
        if market_cap < MIN_MARKET_CAP:
            return None
        
        # 점수 계산
        details = {}
        total_score = 0
        
        # 1. 등락률 점수
        price_score = min(price_change / 5, 2.5)
        details['price_change'] = {
            'value': price_change,
            'score': round(price_score, 2),
            'max': WEIGHT_PRICE_CHANGE
        }
        total_score += price_score
        
        # 2. 거래대금 점수
        trade_amount_billions = trade_amount / 1e8
        if trade_amount_billions >= 500:
            trade_score = WEIGHT_TRADE_AMOUNT
        elif trade_amount_billions >= 100:
            trade_score = (trade_amount_billions / 500) * WEIGHT_TRADE_AMOUNT
        else:
            trade_score = 0
        details['trade_amount'] = {
            'value': trade_amount_billions,
            'score': round(trade_score, 2),
            'max': WEIGHT_TRADE_AMOUNT
        }
        total_score += trade_score
        
        # 3. 시총 점수
        market_cap_billions = market_cap / 1e8
        if market_cap_billions >= 5000:
            cap_score = WEIGHT_MARKET_CAP
        else:
            cap_score = (market_cap_billions / 5000) * WEIGHT_MARKET_CAP
        details['market_cap'] = {
            'value': market_cap_billions,
            'score': round(cap_score, 2),
            'max': WEIGHT_MARKET_CAP
        }
        total_score += cap_score
        
        # 4. 거래량 비율 점수
        avg_volume = int(item.get('avrg_vol', '0').replace(",", ""))
        if avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio >= 5:
                vol_score = WEIGHT_VOLUME
            elif volume_ratio >= 3:
                vol_score = WEIGHT_VOLUME * 0.6
            elif volume_ratio >= 2:
                vol_score = WEIGHT_VOLUME * 0.3
            else:
                vol_score = 0
        else:
            volume_ratio = 0
            vol_score = 0
        
        details['volume_ratio'] = {
            'value': round(volume_ratio, 1),
            'score': round(vol_score, 2),
            'max': WEIGHT_VOLUME
        }
        total_score += vol_score
        
        # 알림 레벨 결정
        if total_score >= MIN_SCORE_STRONG:
            alert_level = "STRONG"
        elif total_score >= MIN_SCORE_NORMAL:
            alert_level = "NORMAL"
        else:
            alert_level = "WATCH"
        
        return StockScore(
            code=code,
            name=name,
            market=market_type,
            total_score=round(total_score, 2),
            price_change=price_change,
            trade_amount=trade_amount,
            market_cap=market_cap,
            alert_level=alert_level,
            details=details
        )
        
    except (ValueError, TypeError) as e:
        return None


def get_volume_rank_surge_stocks(token) -> Tuple[List[dict], List[dict]]:
    """
    거래량 순위 API로 KOSPI/KOSDAQ 급등주 조회 - 시장별 분리
    """
    kospi_stocks = []
    kosdaq_stocks = []
    
    # KOSPI 조회
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPST01710000",
        "custtype": "P"
    }
    
    # KOSPI
    params_kospi = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0001",  # KOSPI
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }
    
    # KOSDAQ
    params_kosdaq = {
        "FID_COND_MRKT_DIV_CODE": "Q",  # KOSDAQ
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0002",  # KOSDAQ
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
        print(f"🔍 KOSPI/KOSDAQ 거래량 순위 API 호출 ({SERVER_TYPE})...")
        
        # KOSPI 조회
        resp = requests.get(url, headers=headers, params=params_kospi, timeout=15)
        data = resp.json()
        
        if data.get("rt_cd") == "0":
            for item in data.get("output", []):
                score = calculate_stock_score(item, "KOSPI")
                if score:
                    company = COMPANY_INFO.get(score.code, {"industry": "기타", "desc": "", "market": "KOSPI"})
                    badge = "🔥 STRONG" if score.alert_level == "STRONG" else "⚡ NORMAL" if score.alert_level == "NORMAL" else "👀 WATCH"
                    kospi_stocks.append({
                        "name": score.name, "code": score.code, "market": "KOSPI",
                        "price": f"{int(item.get('stck_prpr', 0)):,}",
                        "change": f"{score.price_change:+.2f}%",
                        "volume": f"{int(item.get('acml_vol', 0)):,}",
                        "reason": f"급등 {score.alert_level.lower()} (점수: {score.total_score:.1f})",
                        "industry": company["industry"], "desc": company["desc"],
                        "badge": badge, "alert_level": score.alert_level,
                        "score_details": f"등락 {score.price_change:.1f}% / 거래대금 {score.trade_amount/1e8:.0f}억"
                    })
        
        # KOSDAQ 조회
        resp = requests.get(url, headers=headers, params=params_kosdaq, timeout=15)
        data = resp.json()
        
        if data.get("rt_cd") == "0":
            for item in data.get("output", []):
                score = calculate_stock_score(item, "KOSDAQ")
                if score:
                    company = COMPANY_INFO.get(score.code, {"industry": "기타", "desc": "", "market": "KOSDAQ"})
                    badge = "🔥 STRONG" if score.alert_level == "STRONG" else "⚡ NORMAL" if score.alert_level == "NORMAL" else "👀 WATCH"
                    kosdaq_stocks.append({
                        "name": score.name, "code": score.code, "market": "KOSDAQ",
                        "price": f"{int(item.get('stck_prpr', 0)):,}",
                        "change": f"{score.price_change:+.2f}%",
                        "volume": f"{int(item.get('acml_vol', 0)):,}",
                        "reason": f"급등 {score.alert_level.lower()} (점수: {score.total_score:.1f})",
                        "industry": company["industry"], "desc": company["desc"],
                        "badge": badge, "alert_level": score.alert_level,
                        "score_details": f"등락 {score.price_change:.1f}% / 거래대금 {score.trade_amount/1e8:.0f}억"
                    })
        
        print(f"   📊 KOSPI: {len(kospi_stocks)}개, KOSDAQ: {len(kosdaq_stocks)}개")
        
    except Exception as e:
        print(f"❌ API 오류: {e}")
    
    return kospi_stocks, kosdaq_stocks


def get_nasdaq_surge_stocks(token):
    """나스닥 등락률 순위 API"""
    url = f"{BASE_URL}/uapi/overseas-price/v1/ranking/fluctuation"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFS76310001",
        "custtype": "P"
    }
    params = {
        "AUTH": "", "EXCD": "NAS", "SYMB": "", "GB1": "0", "GB2": "1",
        "GB3": "0", "GB4": "0", "GB5": "0", "GB6": "0", "GB7": "0",
        "GB8": "0", "GB9": "0", "GB10": "0", "GB11": "0", "GB12": "0",
        "GB13": "0", "PAGE_SIZE": "20"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        
        if data.get("rt_cd") == "0":
            surge_stocks = []
            for item in data.get("output", []):
                try:
                    change_rate = float(item.get("rate", 0))
                    if change_rate >= 5.0:
                        badge = "🔥 STRONG" if change_rate >= 10 else "⚡ NORMAL" if change_rate >= 7 else "👀 WATCH"
                        surge_stocks.append({
                            "name": item.get("name", ""), "code": item.get("symb", ""),
                            "price": f"${float(item.get('clos', 0)):.2f}",
                            "change": f"{change_rate:+.2f}%",
                            "volume": f"{int(item.get('tvol', 0)):,}",
                            "reason": f"나스닥 급등 ({change_rate:+.1f}%)",
                            "industry": "미국 기술주", "desc": "나스닥 상장",
                            "badge": badge, "alert_level": "NORMAL" if change_rate >= 7 else "WATCH"
                        })
                except (ValueError, TypeError):
                    continue
            return surge_stocks[:6]
    except Exception as e:
        print(f"❌ 나스닥 API 오류: {e}")
    
    return []


def get_sample_data():
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "source": "📋 샘플 데이터",
        "server": "N/A",
        "kospi_stocks": [
            {"name": "삼성전자", "code": "005930", "market": "KOSPI", "price": "72,300", "change": "+5.2%", "volume": "15,234,567",
             "reason": "급등 확인 (점수: 7.5)", "industry": "반도체/전자", "desc": "세계 최대 메모리 반도체", "badge": "⚡ NORMAL", "alert_level": "NORMAL"},
        ],
        "kosdaq_stocks": [
            {"name": "기가레인", "code": "049080", "market": "KOSDAQ", "price": "12,300", "change": "+15.2%", "volume": "5,234,567",
             "reason": "급등 강력 (점수: 10.5)", "industry": "반도체/장비", "desc": "반도체 테스트 소켓", "badge": "🔥 STRONG", "alert_level": "STRONG"},
        ],
        "us_stocks": []
    }


def generate_stock_section(stocks, title, market_type, is_primary=False):
    """주식 섹션 HTML 생성"""
    
    # 시장별 테두리 색상
    border_colors = {
        "kospi": "#ff6b6b", "kosdaq": "#4ecdc4", "nasdaq": "#667eea"
    }
    border_color = border_colors.get(market_type, "#667eea")
    
    # 주요 섹션 여부에 따른 스타일
    section_class = "market-section-primary" if is_primary else "market-section-secondary"
    
    # 빈 상태 메시지
    if not stocks:
        empty_messages = {
            "kospi": "📊 현재 KOSPI 시장에서 급등주(+5% 이상)가 감지되지 않았습니다",
            "kosdaq": "🚀 현재 KOSDAQ 시장에서 급등주(+5% 이상)가 감지되지 않았습니다",
            "nasdaq": "🇺🇸 현재 나스닥 시장이 마감되었거나 급등주가 없습니다"
        }
        empty_msg = empty_messages.get(market_type, "현재 급등주가 없습니다")
        
        return f'''<div class="market-section {section_class}" data-market="{market_type}">
    <div class="market-header" style="border-left: 4px solid {border_color};">
        <h3 class="market-title">{title} <span class="market-count">0개</span></h3>
    </div>
    <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">{empty_msg}</div>
        <div class="empty-hint">장중에 다시 확인해주세요 (30분마다 자동 갱신)</div>
    </div>
</div>'''

    
    # 시장별 테두리 색상
    border_colors = {
        "kospi": "#ff6b6b", "kosdaq": "#4ecdc4", "nasdaq": "#667eea"
    }
    border_color = border_colors.get(market_type, "#667eea")
    
    # 주요 섹션 여부에 따른 스타일
    section_class = "market-section-primary" if is_primary else "market-section-secondary"
    
    html = f'''<div class="market-section {section_class}" data-market="{market_type}">
    <div class="market-header" style="border-left: 4px solid {border_color};">
        <h3 class="market-title">{title} <span class="market-count">{len(stocks)}개</span></h3>
    </div>
    <div class="stocks-grid {'stocks-grid-3col' if is_primary else 'stocks-grid-2col'}">
'''
    
    for stock in stocks[:6]:  # 최대 6개
        change_class = "up" if "+" in stock["change"] else "down"
        badge = stock.get("badge", "급등")
        alert_level = stock.get("alert_level", "NORMAL")
        market_badge = f'<span class="market-badge {stock.get("market", "").lower()}">{stock.get("market", "")}</span>' if stock.get("market") else ""
        
        # 알림 레벨별 스타일
        if alert_level == "STRONG":
            card_style = f'border: 2px solid #ff4757; background: linear-gradient(135deg, rgba(255,71,87,0.05) 0%, rgba(255,71,87,0.1) 100%);'
        elif alert_level == "NORMAL":
            card_style = f'border: 2px solid #ffa502; background: linear-gradient(135deg, rgba(255,165,2,0.05) 0%, rgba(255,165,2,0.1) 100%);'
        else:
            card_style = f'border: 2px solid #747d8c; background: linear-gradient(135deg, rgba(116,125,140,0.05) 0%, rgba(116,125,140,0.1) 100%);'
        
        score_detail = stock.get('score_details', '')
        
        html += f'''        <div class="card stock-card" style="{card_style}">
            <div class="stock-header">
                <div>
                    <div class="stock-name">{stock["name"]} {market_badge}</div>
                    <div class="stock-code">{stock["code"]}</div>
                </div>
                <span class="surge-badge badge-{alert_level.lower()}">{badge}</span>
            </div>
            <div class="price-info">
                <div class="price-item"><div class="price-label">현재가</div><div class="price-value">{stock["price"]}</div></div>
                <div class="price-item"><div class="price-label">등락률</div><div class="price-value {change_class}">{stock["change"]}</div></div>
                <div class="price-item"><div class="price-label">거래량</div><div class="price-value">{stock["volume"]}</div></div>
            </div>
            <div class="stock-reason">
                📊 {stock["reason"]}
                {f'<div class="score-detail">{score_detail}</div>' if score_detail else ''}
            </div>
            {(f'<div class="company-info"><div class="company-industry">{stock["industry"]}</div><div class="company-desc">{stock["desc"]}</div></div>') if stock.get("industry") else ''}
        </div>
'''
    
    html += '''    </div>
</div>'''
    return html


def generate_stock_cards(kospi_stocks, kosdaq_stocks, us_stocks):
    """전체 주식 카드 HTML 생성 - KOSDAQ 가시성 개선 레이아웃"""
    
    # 1. 국내 주식 메인 섹션 (KOSPI + KOSDAQ 합쳐서 표시)
    domestic_html = '<div class="domestic-section">'
    domestic_html += '<h2 class="section-main-title">🇰🇷 국내 급등주</h2>'
    
    # KOSPI 섹션
    domestic_html += generate_stock_section(kospi_stocks, "📈 KOSPI", "kospi", is_primary=True)
    
    # KOSDAQ 섹션 (강조된 스타일)
    domestic_html += generate_stock_section(kosdaq_stocks, "🚀 KOSDAQ", "kosdaq", is_primary=True)
    
    domestic_html += '</div>'
    
    # 2. 해외 주식 섹션 (접을 수 있는 형태)
    nasdaq_html = ''
    if us_stocks:
        nasdaq_html = '''<div class="international-section">
    <details class="collapse-section">
        <summary class="collapse-header">
            <span>🇺🇸 해외 급등주 보기</span>
            <span class="collapse-hint">클릭하여 펼치기</span>
        </summary>
        <div class="collapse-content">
''' + generate_stock_section(us_stocks, "나스닥", "nasdaq", is_primary=False) + '''
        </div>
    </details>
</div>'''
    
    return domestic_html + nasdaq_html


def get_git_version_info():
    try:
        commit_hash = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL).decode().strip()
        commit_time = subprocess.check_output(['git', 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d %H:%M'], cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL).decode().strip()
        return f"v.{commit_hash} | {commit_time}"
    except:
        return "v.unknown | unknown"


def load_section(filename):
    section_path = SECTIONS_DIR / filename
    if section_path.exists():
        with open(section_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def update_html(data):
    """HTML 생성 - 개선된 레이아웃"""
    
    header = load_section('header.html')
    criteria = load_section('criteria.html')
    experts = load_section('experts.html')
    footer = load_section('footer.html')
    
    # 주식 카드 (KOSPI, KOSDAQ, NASDAQ 분리)
    kospi = data.get("kospi_stocks", [])
    kosdaq = data.get("kosdaq_stocks", [])
    us = data.get("us_stocks", [])
    
    stock_cards = generate_stock_cards(kospi, kosdaq, us)
    
    # 플레이스홀더 치환
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    version_info = get_git_version_info()
    
    source_indicator = data.get("source", "🔴 실제 데이터")
    server_type = data.get("server", SERVER_TYPE)
    if server_type and server_type != "N/A":
        source_indicator += f" | {server_type}"
    
    header = header.replace('{{UPDATE_DATE}}', current_time)
    header = header.replace('{{DATA_SOURCE}}', source_indicator)
    header = header.replace('{{VERSION_INFO}}', version_info)
    
    # 추가 CSS 삽입 (레이아웃 개선용)
    additional_css = '''
<style>
/* KOSDAQ 가시성 개선 - 추가 CSS */
.section-main-title {
    font-size: var(--font-xl);
    font-weight: 700;
    text-align: center;
    margin: var(--space-xl) 0 var(--space-md);
    color: #2d3748;
}

.domestic-section {
    margin-bottom: var(--space-xl);
}

.market-section-primary {
    margin-bottom: var(--space-lg);
}

.market-section-primary .market-header {
    background: rgba(255,255,255,0.9);
    padding: var(--space-md);
    border-radius: 12px;
    margin-bottom: var(--space-md);
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.market-count {
    font-size: var(--font-sm);
    color: var(--color-text-light);
    font-weight: 500;
    background: rgba(0,0,0,0.05);
    padding: 4px 12px;
    border-radius: 20px;
}

.market-badge {
    font-size: 0.65rem;
    padding: 2px 6px;
    border-radius: 4px;
    margin-left: 6px;
    font-weight: 600;
}

.market-badge.kospi {
    background: #ff6b6b;
    color: white;
}

.market-badge.kosdaq {
    background: #4ecdc4;
    color: white;
}

.stocks-grid-3col {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-md);
}

@media (min-width: 640px) {
    .stocks-grid-3col {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (min-width: 1024px) {
    .stocks-grid-3col {
        grid-template-columns: repeat(3, 1fr);
    }
}

.stocks-grid-2col {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-md);
}

@media (min-width: 640px) {
    .stocks-grid-2col {
        grid-template-columns: repeat(2, 1fr);
    }
}

/* 해외 주식 접기 섹션 */
.international-section {
    margin-top: var(--space-xl);
}

.collapse-section {
    background: rgba(255,255,255,0.6);
    border-radius: var(--card-radius);
    border: 1px solid rgba(255,255,255,0.8);
    overflow: hidden;
}

.collapse-header {
    padding: var(--space-md);
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    color: #2d3748;
    list-style: none;
    transition: background 0.2s;
}

.collapse-header:hover {
    background: rgba(255,255,255,0.8);
}

.collapse-header::-webkit-details-marker {
    display: none;
}

.collapse-hint {
    font-size: var(--font-xs);
    color: var(--color-text-light);
    font-weight: 400;
}

.collapse-content {
    padding: 0 var(--space-md) var(--space-md);
}

/* 알림 뱃지 스타일 */
.badge-strong {
    background: linear-gradient(135deg, #ff4757 0%, #ff6b81 100%);
    color: white;
}

.badge-normal {
    background: linear-gradient(135deg, #ffa502 0%, #ffb74d 100%);
    color: white;
}

.badge-watch {
    background: linear-gradient(135deg, #747d8c 0%, #95a5a6 100%);
    color: white;
}

.score-detail {
    font-size: 0.75rem;
    color: #667eea;
    margin-top: 4px;
    opacity: 0.8;
}

/* 빈 상태 스타일 */
.empty-state {
    text-align: center;
    padding: var(--space-xl) var(--space-md);
    background: rgba(255,255,255,0.6);
    border-radius: var(--card-radius);
    border: 2px dashed rgba(160, 174, 192, 0.4);
    margin: var(--space-md) 0;
}

.empty-icon {
    font-size: 3rem;
    margin-bottom: var(--space-sm);
    opacity: 0.6;
}

.empty-text {
    font-size: var(--font-md);
    color: var(--color-text);
    font-weight: 500;
    margin-bottom: var(--space-xs);
}

.empty-hint {
    font-size: var(--font-xs);
    color: var(--color-text-light);
}

.stock-reason {
    margin-top: 8px;
    padding: 8px 12px;
    background: rgba(102,126,234,0.08);
    border-radius: 8px;
    font-size: 0.85rem;
    color: #667eea;
    font-weight: 600;
}
/* 판별로직 접기/펼치기 스타일 */
.logic-details {
    background: rgba(255,255,255,0.6);
    border-radius: var(--card-radius);
    border: 1px solid rgba(255,255,255,0.8);
    overflow: hidden;
    margin: var(--space-md) 0;
}

.logic-summary {
    padding: var(--space-md);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 4px;
    list-style: none;
    transition: background 0.2s;
}

.logic-summary:hover {
    background: rgba(255,255,255,0.8);
}

.logic-summary::-webkit-details-marker {
    display: none;
}

.summary-title {
    font-size: var(--font-lg);
    font-weight: 700;
    color: var(--color-accent);
    display: flex;
    align-items: center;
    gap: 8px;
}

.summary-title::before {
    content: '▶';
    font-size: 0.8rem;
    transition: transform 0.3s;
    color: var(--color-accent);
}

.logic-details[open] .summary-title::before {
    transform: rotate(90deg);
}

.summary-hint {
    font-size: var(--font-sm);
    color: var(--color-text-light);
}

.logic-content {
    padding: 0 var(--space-md) var(--space-md);
}

/* details 애니메이션 */
.logic-details[open] .logic-content {
    animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
</style>
'''
    
    # HTML 조합 (CSS 삽입)
    html_content = header.replace('</head>', f'{additional_css}</head>')
    
    # 히트맵/거래량 알림 섹션 삽입 (있는 경우)
    extra_sections = data.get("extra_sections", "")
    html_content += criteria + experts + extra_sections + stock_cards + footer
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    total_domestic = len(kospi) + len(kosdaq)
    print(f"✅ HTML 업데이트: 국내 {total_domestic}개 (KOSPI {len(kospi)}, KOSDAQ {len(kosdaq)}) / 해외 {len(us)}개")


def fetch_surge_stocks():
    """급등주 데이터 수집 - KOSPI/KOSDAQ 분리"""
    
    print(f"🚀 급등주 데이터 수집 시작: {datetime.now()}")
    print(f"   [시스템] KOSPI/KOSDAQ 분리 표시 | UI 최적화")
    
    token = get_access_token()
    if not token:
        return get_sample_data()
    
    # KOSPI/KOSDAQ 분리 조회
    kospi_stocks, kosdaq_stocks = get_volume_rank_surge_stocks(token)
    
    # 해외 주식
    us_stocks = get_nasdaq_surge_stocks(token)
    
    # DB 저장
    try:
        from stock_db import init_db, save_snapshot, save_stocks
        init_db()  # 테이블 없으면 생성
        snapshot_id = save_snapshot(
            market_status="OPEN" if is_market_open() else "CLOSED",
            data_source=SERVER_TYPE,
            total_kospi=len(kospi_stocks),
            total_kosdaq=len(kosdaq_stocks)
        )
        save_stocks(snapshot_id, "KOSPI", kospi_stocks)
        save_stocks(snapshot_id, "KOSDAQ", kosdaq_stocks)
        print(f"✅ DB 저장 완료 (snapshot_id: {snapshot_id})")
        
        # 섹터 히트맵 & 거래량 폭발 알림 생성
        try:
            from sector_heatmap import get_sector_heatmap, generate_heatmap_html
            from volume_alert import detect_volume_spikes, generate_volume_alert_html
            
            heatmap_data = get_sector_heatmap()
            volume_alerts = detect_volume_spikes()
            
            # HTML 파일에 추가할 섹션 생성
            extra_sections = ""
            if heatmap_data["sectors"]:
                extra_sections += generate_heatmap_html(heatmap_data)
            if volume_alerts["alerts"]:
                extra_sections += generate_volume_alert_html(volume_alerts)
            
            # data에 저장 (update_html에서 사용)
            data["extra_sections"] = extra_sections
            print(f"📊 섹터 히트맵: {len(heatmap_data['sectors'])}개 / 거래량 폭발: {volume_alerts['total_alerts']}개")
        except Exception as e:
            print(f"⚠️ 히트맵/알림 생성 실패: {e}")
        
    except Exception as e:
        print(f"⚠️ DB 저장 실패: {e}")
    
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "source": "🔴 실제 데이터",
        "server": SERVER_TYPE,
        "kospi_stocks": kospi_stocks,
        "kosdaq_stocks": kosdaq_stocks,
        "us_stocks": us_stocks
    }


def is_market_open():
    """장중 여부 확인 (09:00 ~ 15:30)"""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def save_market_data(data):
    """장중 데이터를 JSON 파일로 저장"""
    data["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["market_status"] = "OPEN" if is_market_open() else "CLOSED"
    
    with open('market_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 장중 데이터 저장 완료: {data['saved_at']} (장{'' if is_market_open() else ' 마감'})")


def load_market_data():
    """저장된 마지막 장중 데이터 로드"""
    if os.path.exists('market_data.json'):
        try:
            with open('market_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📂 저장된 데이터 로드: {data.get('saved_at', 'unknown')}")
            return data
        except Exception as e:
            print(f"⚠️ 데이터 로드 실패: {e}")
            return None
    return None


def main():
    print(f"🚀 {'='*60}")
    print(f"📅 현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🏦 장 상태: {'열림' if is_market_open() else '마감'}")
    print(f"{'='*60}\n")
    
    # 1. 새로운 데이터 수집
    fresh_data = fetch_surge_stocks()
    
    # 2. 장중이고 데이터가 있으면 저장, 없으면 이전 데이터 사용
    if is_market_open():
        # 장중: 새 데이터 저장
        if fresh_data.get('kospi_stocks') or fresh_data.get('kosdaq_stocks'):
            save_market_data(fresh_data)
            print("📈 장중 데이터 저장 완료")
        else:
            print("⚠️ 장중인데 데이터가 없음 - 이전 데이터 유지")
    else:
        # 장 마감: 저장된 데이터가 있으면 사용
        saved_data = load_market_data()
        if saved_data:
            print("📂 장 마감 - 저장된 장중 데이터로 표시")
            fresh_data = saved_data
        else:
            print("⚠️ 저장된 데이터 없음 - 현재 데이터 사용")
    
    print(f"\n✨ 작업 완료!")
    print(f"💡 장 마감 후에는 마지막 장중 데이터를 표시합니다.")


if __name__ == "__main__":
    main()
