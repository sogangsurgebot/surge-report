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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json

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

# 선정 기준 상수 (완화된 기준)
MIN_PRICE_CHANGE = 3.0          # 최소 등락률 3% (완화: 기존 5%)
MIN_TRADE_AMOUNT = 10e8         # 최소 거래대금 10억 (완화: 기존 100억)
MIN_MARKET_CAP = 50e8           # 최소 시총 50억 (완화: 기존 500억)
MIN_SCORE_STRONG = 8            # 강한 알림 기준 (완화: 기존 10)
MIN_SCORE_NORMAL = 5            # 일반 알림 기준 (완화: 기존 7)

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
        # 시총 정보가 없으면(cap=0) 시총 필터 무시 (거래량순위 API에 hts_avls 필드 없음)
        if market_cap > 0 and market_cap < MIN_MARKET_CAP:
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
    """주식 섹션 HTML 생성 (등급 필터 항상 포함)"""

    # 시장별 테두리 색상
    border_colors = {
        "kospi": "#ff6b6b", "kosdaq": "#4ecdc4", "nasdaq": "#667eea"
    }
    border_color = border_colors.get(market_type, "#667eea")

    # 주요 섹션 여부에 따른 스타일
    section_class = "market-section-primary" if is_primary else "market-section-secondary"

    # 등급 필터 HTML (데이터 유무와 관계없이 항상 표시)
    result_id = f"{market_type}GradeResult"
    grade_filter_html = f'''<div class="grade-filter-section">
        <div class="grade-filter-header">
            <span class="grade-filter-title">📊 등락률 대역 필터</span>
            <span class="grade-filter-sub">클릭하여 해당 등급 종목 확인</span>
        </div>
        <div class="grade-filter-grid">
            <button class="grade-btn s-grade" data-grade="S" data-min="29">
                <span class="grade-label">S</span>
                <span class="grade-range">+29% ~</span>
                <span class="grade-desc">상한가 근접</span>
            </button>
            <button class="grade-btn a-grade" data-grade="A" data-min="20">
                <span class="grade-label">A</span>
                <span class="grade-range">+20% ~ 29%</span>
                <span class="grade-desc">강한 급등</span>
            </button>
            <button class="grade-btn b-grade" data-grade="B" data-min="10">
                <span class="grade-label">B</span>
                <span class="grade-range">+10% ~ 20%</span>
                <span class="grade-desc">중간 급등</span>
            </button>
            <button class="grade-btn c-grade active" data-grade="C" data-min="3">
                <span class="grade-label">C</span>
                <span class="grade-range">+3% ~ 10%</span>
                <span class="grade-desc">초기 급등</span>
            </button>
            <button class="grade-btn d-grade" data-grade="D" data-min="0">
                <span class="grade-label">D</span>
                <span class="grade-range">0% ~ 3%</span>
                <span class="grade-desc">주목 단계</span>
            </button>
            <button class="grade-btn watch-grade" data-grade="W" data-min="-100">
                <span class="grade-label">W</span>
                <span class="grade-range">전체</span>
                <span class="grade-desc">모든 종목</span>
            </button>
        </div>
        <div class="grade-result" id="{result_id}"></div>
    </div>'''

    # 빈 상태 메시지
    if not stocks:
        empty_messages = {
            "kospi": "📊 현재 KOSPI 시장에서 급등주(+3% 이상)가 감지되지 않았습니다",
            "kosdaq": "🚀 현재 KOSDAQ 시장에서 급등주(+3% 이상)가 감지되지 않았습니다",
            "nasdaq": "🇺🇸 현재 나스닥 시장이 마감되었거나 급등주가 없습니다"
        }
        empty_msg = empty_messages.get(market_type, "현재 급등주가 없습니다")
        
        return f'''<div class="market-section {section_class}" data-market="{market_type}">
    <div class="market-header" style="border-left: 4px solid {border_color};">
        <h3 class="market-title">{title} <span class="market-count">0개</span></h3>
    </div>
    {grade_filter_html}
    <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">{empty_msg}</div>
        <div class="empty-hint">장중에 다시 확인해주세요 (10분마다 자동 갱신)</div>
    </div>
</div>'''
    
    html = f'''<div class="market-section {section_class}" data-market="{market_type}">
    <div class="market-header" style="border-left: 4px solid {border_color};">
        <h3 class="market-title">{title} <span class="market-count">{len(stocks)}개</span></h3>
    </div>
    {grade_filter_html}
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


def generate_domestic_section(kospi_stocks, kosdaq_stocks):
    """국내 급등주 섹션 HTML 생성 (마커 교체용)"""
    html = '<div class="domestic-section"><h2 class="section-main-title">🇰🇷 국내 급등주</h2>'
    html += generate_stock_section(kospi_stocks, "📈 KOSPI", "kospi", is_primary=True)
    html += generate_stock_section(kosdaq_stocks, "🚀 KOSDAQ", "kosdaq", is_primary=True)
    html += '</div>'
    return html


def generate_nasdaq_section(us_stocks):
    """해외 급등주 섹션 HTML 생성 (마커 교체용)"""
    if not us_stocks:
        return ''

    html = '''<div class="international-section">
    <details class="collapse-section">
        <summary class="collapse-header">
            <span>🇺🇸 해외 급등주 보기</span>
            <span class="collapse-hint">클릭하여 펼치기</span>
        </summary>
        <div class="collapse-content">
'''
    html += generate_stock_section(us_stocks, "나스닥", "nasdaq", is_primary=False)
    html += '''        </div>
    </details>
</div>'''
    return html


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


def generate_domestic_section(kospi_stocks, kosdaq_stocks):
    """국내 급등주 섹션 HTML 생성 (마커 교체용)"""
    html = '<div class="domestic-section"><h2 class="section-main-title">🇰🇷 국내 급등주</h2>'
    html += generate_stock_section(kospi_stocks, "📈 KOSPI", "kospi", is_primary=True)
    html += generate_stock_section(kosdaq_stocks, "🚀 KOSDAQ", "kosdaq", is_primary=True)
    html += '</div>'
    return html


def generate_nasdaq_section(us_stocks):
    """해외 급등주 섹션 HTML 생성 (마커 교체용)"""
    if not us_stocks:
        return ''

    html = '''<div class="international-section">
    <details class="collapse-section">
        <summary class="collapse-header">
            <span>🇺🇸 해외 급등주 보기</span>
            <span class="collapse-hint">클릭하여 펼치기</span>
        </summary>
        <div class="collapse-content">
'''
    html += generate_stock_section(us_stocks, "나스닥", "nasdaq", is_primary=False)
    html += '''        </div>
    </details>
</div>'''
    return html


def replace_between_markers(file_path, marker_start, marker_end, new_content):
    """
    index.html에서 마커 사이의 내용만 교체
    마커 외부의 모든 내용은 보존됨
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    start_idx = content.find(marker_start)
    end_idx = content.find(marker_end)

    if start_idx == -1 or end_idx == -1:
        print(f"⚠️ 마커를 찾을 수 없음: {marker_start} / {marker_end}")
        return False

    # 마커 끝 위치 계산 (마커 텍스트 자체는 유지)
    start_pos = start_idx + len(marker_start)
    end_pos = end_idx

    new_html = content[:start_pos] + '\n' + new_content + '\n' + content[end_pos:]

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_html)

    return True


def update_html(data):
    """HTML 업데이트 - 마커 기반 부분 교체 (index.html 전체 덮어쓰기 금지)"""

    # 1. 히트맵 + 거래량 알림 교체
    extra_sections = data.get("extra_sections", "")
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_HEATMAP_START -->',
        '<!-- DYNAMIC_HEATMAP_END -->',
        extra_sections
    )

    # 2. 국내 급등주 카드 교체
    kospi = data.get("kospi_stocks", [])
    kosdaq = data.get("kosdaq_stocks", [])
    stock_cards_html = generate_domestic_section(kospi, kosdaq)
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_STOCK_CARDS_START -->',
        '<!-- DYNAMIC_STOCK_CARDS_END -->',
        stock_cards_html
    )

    # 3. 해외 급등주 (NASDAQ) 교체
    us = data.get("us_stocks", [])
    nasdaq_html = generate_nasdaq_section(us)
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_NASDAQ_START -->',
        '<!-- DYNAMIC_NASDAQ_END -->',
        nasdaq_html
    )

    # 4. 업데이트 시간 교체
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    update_time_html = f'<span>🕐 마지막 업데이트: {current_time}</span>'
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_UPDATE_TIME_START -->',
        '<!-- DYNAMIC_UPDATE_TIME_END -->',
        update_time_html
    )

    total_domestic = len(kospi) + len(kosdaq)
    print(f"✅ HTML 부분 교체 완료: 국내 {total_domestic}개 (KOSPI {len(kospi)}, KOSDAQ {len(kosdaq)}) / 해외 {len(us)}개")


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


def generate_extra_sections(kospi_stocks, kosdaq_stocks):
    """섹터 히트맵 + 거래량 폭발 알림 HTML 생성"""
    extra_sections = ""

    try:
        from sector_heatmap import get_sector_heatmap, generate_heatmap_html
        from volume_alert import detect_volume_spikes, generate_volume_alert_html

        # DB에 저장된 오늘 데이터 기준으로 분석
        heatmap_data = get_sector_heatmap()
        volume_alerts = detect_volume_spikes()

        if heatmap_data["sectors"]:
            extra_sections += generate_heatmap_html(heatmap_data)
            print(f"📊 섹터 히트맵: {len(heatmap_data['sectors'])}개 섹터")

        if volume_alerts["alerts"]:
            extra_sections += generate_volume_alert_html(volume_alerts)
            print(f"⚠️ 거래량 폭발: {volume_alerts['total_alerts']}개 종목")

    except Exception as e:
        print(f"⚠️ 히트맵/알림 생성 실패: {e}")

    return extra_sections


def is_market_open():
    """장중 여부 확인 (09:00 ~ 15:30 KST)"""
    # 한국 시간(KST, UTC+9) 기준으로 장 상태 확인
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    market_open = now_kst.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now_kst.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now_kst <= market_close


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
    # 한국 시간(KST) 현재 시간
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    
    print(f"🚀 {'='*60}")
    print(f"📅 현재 시간: {now_kst.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
    print(f"🏦 장 상태: {'열림' if is_market_open() else '마감'}")
    print(f"{'='*60}\n")

    # 1. 새로운 데이터 수집
    fresh_data = fetch_surge_stocks()

    # 2. 장중이고 데이터가 있으면 저장, 없으면 이전 데이터 사용
    if is_market_open():
        if fresh_data.get('kospi_stocks') or fresh_data.get('kosdaq_stocks'):
            save_market_data(fresh_data)
            print("📈 장중 데이터 저장 완료")
        else:
            print("⚠️ 장중인데 데이터가 없음 - 이전 데이터 유지")
    else:
        saved_data = load_market_data()
        if saved_data:
            print("📂 장 마감 - 저장된 장중 데이터로 표시")
            fresh_data = saved_data
        else:
            print("⚠️ 저장된 데이터 없음 - 현재 데이터 사용")

    # 3. 히트맵 & 거래량 알림 생성 (DB 기반)
    extra_sections = generate_extra_sections(
        fresh_data.get('kospi_stocks', []),
        fresh_data.get('kosdaq_stocks', [])
    )
    fresh_data["extra_sections"] = extra_sections

    # 4. HTML 업데이트 (최종 데이터)
    update_html(fresh_data)

    print(f"\n✨ 작업 완료!")
    print(f"💡 장 마감 후에는 마지막 장중 데이터를 표시합니다.")


if __name__ == "__main__":
    main()
