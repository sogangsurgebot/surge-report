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
    """Access Token 발급 - 실패 시 None 반환"""
    if not APP_KEY or not APP_SECRET:
        print("❌ API 키 미설정 - 토큰 발급 불가")
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
            if token:
                print(f"✅ 토큰 발급 성공 ({SERVER_TYPE})")
                return token
            print("❌ 토큰 응답에 access_token 없음")
            return None
        elif resp.status_code == 403:
            print("⚠️ 토큰 rate limit (403) - 잠시 후 재시도 필요")
            return None
        else:
            print(f"❌ 토큰 발급 실패: HTTP {resp.status_code}")
            return None
    except requests.Timeout:
        print("❌ 토큰 발급 타임아웃")
        return None
    except Exception as e:
        print(f"❌ Token 오류: {e}")

    return None


def calculate_stock_score(item: dict, market_type: str = "KOSPI") -> Optional[StockScore]:
    """
    종목 점수 계산 - API 응답 데이터 검증 포함
    """
    try:
        code = item.get("mksc_shrn_iscd", "")
        name = item.get("hts_kor_isnm", "")
        
        # 필수 필드 검증
        if not code or not name:
            return None
            
        price_change_raw = item.get("prdy_ctrt", "")
        price_raw = item.get('stck_prpr', "")
        volume_raw = item.get('acml_vol', "")
        
        # 숫자 변환 및 검증
        try:
            price_change = float(price_change_raw)
            price = int(price_raw)
            volume = int(volume_raw)
        except (ValueError, TypeError):
            print(f"⚠️ 데이터 변환 실패: {name}({code}) - price_change={price_change_raw}, price={price_raw}, volume={volume_raw}")
            return None
        
        # 데이터 sanity check
        if price <= 0:
            print(f"⚠️ 비정상 가격: {name}({code}) - 가격={price}")
            return None
        if volume <= 0:
            print(f"⚠️ 비정상 거래량: {name}({code}) - 거래량={volume}")
            return None
        if abs(price_change) > 30:  # 30% 이상 변동은 이상치로 판단 (상한가 제외)
            print(f"⚠️ 비정상 등락률: {name}({code}) - 등락률={price_change}%")
            return None

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
        
        # 응답 검증
        if resp.status_code != 200:
            print(f"❌ KOSPI API 응답 오류: HTTP {resp.status_code}")
            return kospi_stocks, kosdaq_stocks
            
        try:
            data = resp.json()
        except json.JSONDecodeError:
            print(f"❌ KOSPI API 응답 파싱 실패: 유효하지 않은 JSON")
            return kospi_stocks, kosdaq_stocks

        if data.get("rt_cd") == "0":
            output = data.get("output", [])
            if not output:
                print("⚠️ KOSPI API 응답: 데이터 없음 (빈 output)")
            
            for item in output:
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
        else:
            rt_cd = data.get("rt_cd", "unknown")
            msg = data.get("msg1", "unknown error")
            print(f"❌ KOSPI API 오류: rt_cd={rt_cd}, msg={msg}")

        # KOSDAQ 조회
        resp = requests.get(url, headers=headers, params=params_kosdaq, timeout=15)
        
        # 응답 검증
        if resp.status_code != 200:
            print(f"❌ KOSDAQ API 응답 오류: HTTP {resp.status_code}")
            return kospi_stocks, kosdaq_stocks
            
        try:
            data = resp.json()
        except json.JSONDecodeError:
            print(f"❌ KOSDAQ API 응답 파싱 실패: 유효하지 않은 JSON")
            return kospi_stocks, kosdaq_stocks

        if data.get("rt_cd") == "0":
            output = data.get("output", [])
            if not output:
                print("⚠️ KOSDAQ API 응답: 데이터 없음 (빈 output)")
                
            for item in output:
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
        else:
            rt_cd = data.get("rt_cd", "unknown")
            msg = data.get("msg1", "unknown error")
            print(f"❌ KOSDAQ API 오류: rt_cd={rt_cd}, msg={msg}")

        print(f"   📊 KOSPI: {len(kospi_stocks)}개, KOSDAQ: {len(kosdaq_stocks)}개")

    except requests.Timeout:
        print(f"❌ API 타임아웃 (15초)")
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


def get_fallback_data():
    """API 실패 시 이전 저장된 데이터를 재사용하거나 실패 상태 반환"""
    saved = load_market_data()
    if saved:
        print("📂 API 실패 - 이전 저장된 데이터 재사용")
        return saved
    
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "source": "⚠️ 데이터 수집 실패",
        "server": "N/A",
        "kospi_stocks": [],
        "kosdaq_stocks": [],
        "us_stocks": [],
        "error": True
    }


def generate_stock_section(stocks, title, market_type, is_primary=False):
    """주식 섹션 HTML 생성 (A+C 하이브리드 UI)"""

    # 시장별 테두리 색상
    border_colors = {"kospi": "#ff6b6b", "kosdaq": "#4ecdc4", "nasdaq": "#667eea"}
    border_color = border_colors.get(market_type, "#667eea")
    section_class = "market-section-primary" if is_primary else "market-section-secondary"

    # 등급별 분류
    grade_ranges = {
        "S": {"min": 29, "max": 999},
        "A": {"min": 20, "max": 29},
        "B": {"min": 10, "max": 20},
        "C": {"min": 3, "max": 10},
        "D": {"min": 0, "max": 3},
    }

    grade_stocks = {"S": [], "A": [], "B": [], "C": [], "D": []}
    for stock in stocks:
        change_str = stock.get("change", "0%")
        try:
            change_rate = float(change_str.replace("%", "").replace("+", ""))
        except (ValueError, TypeError):
            change_rate = 0.0
        for grade, rng in grade_ranges.items():
            if rng["min"] <= change_rate < rng["max"]:
                grade_stocks[grade].append(stock)
                break

    grade_counts = {g: len(v) for g, v in grade_stocks.items()}
    grade_counts["ALL"] = len(stocks)

    # 디버깅
    if stocks:
        print(f"   📊 등급 분포: S:{grade_counts['S']} A:{grade_counts['A']} B:{grade_counts['B']} C:{grade_counts['C']} D:{grade_counts['D']} (총 {len(stocks)}개)")

    # 등급 탭 HTML
    grade_tab_colors = {"S": "#ff4757", "A": "#e67e22", "B": "#f39c12", "C": "#2ecc71", "D": "#3498db", "ALL": "#95a5a6"}
    tabs_html = '<div class="grade-tabs">'
    for grade in ["ALL", "S", "A", "B", "C", "D"]:
        count = grade_counts[grade]
        disabled = ' disabled' if count == 0 else ''
        active = ' active' if grade == "ALL" else ''
        color = grade_tab_colors[grade]
        label = "전체" if grade == "ALL" else grade
        tabs_html += f'<button class="grade-tab{active}{disabled}" data-grade="{grade}" style="border-bottom-color:{color}"><span>{label}</span><span class="tab-count">{count}</span></button>'
    tabs_html += '</div>'

    # 빈 상태
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
    {tabs_html}
    <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">{empty_msg}</div>
        <div class="empty-hint">장중에 다시 확인해주세요 (10분마다 자동 갱신)</div>
    </div>
</div>'''

    # S등급 카드 HTML
    s_cards_html = ''
    if grade_stocks["S"]:
        s_cards_html = '<div class="grade-content" data-grade="S"><div class="s-grade-grid">'
        for stock in grade_stocks["S"]:
            s_cards_html += _generate_stock_card_html(stock, market_type)
        s_cards_html += '</div></div>'

    # A/B/C/D 테이블 + 상세 카드 HTML
    table_html = ''
    for grade in ["A", "B", "C", "D"]:
        if not grade_stocks[grade]:
            continue
        table_html += f'<div class="grade-content" data-grade="{grade}"><div class="stock-table-wrap"><table class="stock-table"><thead><tr><th>종목</th><th>등락률</th><th>등급</th><th>거래대금</th><th>네이버</th><th></th></tr></thead><tbody>'
        for stock in grade_stocks[grade]:
            table_html += _generate_table_row_html(stock, market_type, grade)
            table_html += _generate_detail_row_html(stock, market_type, grade)
        table_html += '</tbody></table></div></div>'

    # 전체 콘텐츠
    content_html = '<div class="market-content">' + s_cards_html + table_html + '</div>'

    return f'''<div class="market-section {section_class}" data-market="{market_type}">
    <div class="market-header" style="border-left: 4px solid {border_color};">
        <h3 class="market-title">{title} <span class="market-count">{len(stocks)}개</span></h3>
    </div>
    {tabs_html}
    {content_html}
</div>'''


def _generate_stock_card_html(stock, market_type):
    """S등급 카드 HTML (기존 스타일 유지)"""
    change_class = "up" if "+" in stock["change"] else "down"
    badge = stock.get("badge", "급등")
    alert_level = stock.get("alert_level", "NORMAL")
    market_badge = f'<span class="market-badge {stock.get("market", "").lower()}">{stock.get("market", "")}</span>' if stock.get("market") else ""

    if alert_level == "STRONG":
        card_style = f'border: 2px solid #ff4757; background: linear-gradient(135deg, rgba(255,71,87,0.05) 0%, rgba(255,71,87,0.1) 100%);'
    elif alert_level == "NORMAL":
        card_style = f'border: 2px solid #ffa502; background: linear-gradient(135deg, rgba(255,165,2,0.05) 0%, rgba(255,165,2,0.1) 100%);'
    else:
        card_style = f'border: 2px solid #747d8c; background: linear-gradient(135deg, rgba(116,125,140,0.05) 0%, rgba(116,125,140,0.1) 100%);'

    score_detail = stock.get('score_details', '')

    return f'''<div class="card stock-card" style="{card_style}">
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
            <div class="stock-chart">
                <a href="https://finance.naver.com/item/main.nhn?code={stock["code"]}" target="_blank" rel="noopener noreferrer">
                    <img src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/{stock["code"]}.png" alt="{stock["name"]} 일봉 차트" loading="lazy" onerror="this.parentElement.style.display='none'">
                </a>
                <div class="stock-chart-label">📊 네이버 금융 일봉 차트</div>
            </div>
        </div>'''


def _generate_table_row_html(stock, market_type, grade):
    """테이블 row HTML"""
    change_class = "up" if "+" in stock["change"] else "down"
    grade_colors = {"A": "#e67e22", "B": "#f39c12", "C": "#2ecc71", "D": "#3498db"}
    grade_color = grade_colors.get(grade, "#95a5a6")
    badge_text = stock.get("badge", "급등")

    # 거래대금 파싱 (점수 상세에서 추출)
    trade_amount = "-"
    score_detail = stock.get('score_details', '')
    if '거래대금' in score_detail:
        parts = score_detail.split('/')
        for p in parts:
            if '거래대금' in p:
                trade_amount = p.replace('거래대금', '').strip()
                break
    if trade_amount == "-":
        trade_amount = stock.get("trade_amount", "-")

    return f'''<tr data-stock="{stock["code"]}">
                <td class="col-name"><div><div>{stock["name"]}</div><div class="col-code">{stock["code"]}</div></div></td>
                <td class="col-change {change_class}">{stock["change"]}</td>
                <td><span class="surge-badge" style="background:{grade_color};color:white;font-size:0.7rem;padding:2px 8px;border-radius:6px;">{grade}</span></td>
                <td class="col-amount">{trade_amount}</td>
                <td class="col-link"><a href="https://finance.naver.com/item/main.nhn?code={stock["code"]}" target="_blank">📈</a></td>
                <td><span class="expand-icon">▼</span></td>
            </tr>'''


def _generate_detail_row_html(stock, market_type, grade):
    """테이블 row 클릭 시 펼쳐지는 상세 카드 HTML"""
    change_class = "up" if "+" in stock["change"] else "down"
    badge = stock.get("badge", "급등")
    alert_level = stock.get("alert_level", "NORMAL")
    market_badge = f'<span class="market-badge {stock.get("market", "").lower()}">{stock.get("market", "")}</span>' if stock.get("market") else ""
    score_detail = stock.get('score_details', '')

    return f'''<tr class="stock-detail-row" data-stock="{stock["code"]}">
                <td colspan="6" class="stock-detail-cell">
                    <div class="stock-detail-card">
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
                        <div class="stock-chart">
                            <a href="https://finance.naver.com/item/main.nhn?code={stock["code"]}" target="_blank" rel="noopener noreferrer">
                                <img src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/{stock["code"]}.png" alt="{stock["name"]} 일봉 차트" loading="lazy" onerror="this.parentElement.style.display='none'">
                            </a>
                            <div class="stock-chart-label">📊 네이버 금융 일봉 차트</div>
                        </div>
                    </div>
                </td>
            </tr>'''


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

    # 5. 저평가 주식 섹션 교체 (정적 데이터지만 마커 통일성 유지)
    value_stocks_html = generate_value_stocks_section()
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_VALUE_STOCKS_START -->',
        '<!-- DYNAMIC_VALUE_STOCKS_END -->',
        value_stocks_html
    )

    # 6. 업데이트 시간 교체 (캐시 버스팅용 타임스탬프 포함)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    cache_buster = datetime.now().strftime('%Y%m%d%H%M')
    update_time_html = f'<span data-cache-buster="{cache_buster}">🕐 마지막 업데이트: {current_time}</span>'
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_UPDATE_TIME_START -->',
        '<!-- DYNAMIC_UPDATE_TIME_END -->',
        update_time_html
    )

    # 7. 깃 버전 정보 갱신
    version_info = get_git_version_info()
    version_html = f'<a href="https://github.com/sogangsurgebot/surge-report/commits/main" target="_blank">📌 {version_info}</a>'
    replace_between_markers(
        'index.html',
        '<!-- DYNAMIC_VERSION_START -->',
        '<!-- DYNAMIC_VERSION_END -->',
        version_html
    )

    total_domestic = len(kospi) + len(kosdaq)
    print(f"✅ HTML 부분 교체 완료: 국내 {total_domestic}개 (KOSPI {len(kospi)}, KOSDAQ {len(kosdaq)}) / 해외 {len(us)}개 / 저평가 6개")


def fetch_surge_stocks():
    """급등주 데이터 수집 - KOSPI/KOSDAQ 분리"""

    print(f"🚀 급등주 데이터 수집 시작: {datetime.now()}")
    print(f"   [시스템] KOSPI/KOSDAQ 분리 표시 | UI 최적화")

    token = get_access_token()
    if not token:
        return get_fallback_data()

    # KOSPI/KOSDAQ 분리 조회
    kospi_stocks, kosdaq_stocks = get_volume_rank_surge_stocks(token)
    
    # 데이터 무결성 검증: API는 성공했지만 데이터가 비어있는 경우
    total_stocks = len(kospi_stocks) + len(kosdaq_stocks)
    if total_stocks == 0:
        print("⚠️ API 응답은 성공했지만 선정된 종목이 0개 - 이전 데이터 재사용 시도")
        saved = load_market_data()
        if saved and (saved.get('kospi_stocks') or saved.get('kosdaq_stocks')):
            print("📂 이전 저장 데이터로 대체")
            return saved

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


def generate_value_stocks_section():
    """저평가 주식 섹션 HTML 생성 (오일전문가 × 세상학개론 전략)"""
    stocks = [
        {
            "name": "KB금융지주",
            "code": "105560",
            "per": "6.5배",
            "dividend": "5.2%",
            "sector": "금융지주",
            "oil_comment": "황금거위 1순위. 분기배당 도입으로 안정성 확보.",
            "sesang_comment": "밸류업 정책 수혜 기대"
        },
        {
            "name": "신한지주",
            "code": "055550",
            "per": "6.8배",
            "dividend": "5.0%",
            "sector": "금융지주",
            "oil_comment": "주주환원 강화로 배당성향 상승 중.",
            "sesang_comment": "금리 인하 시 NIM 압박 해소 예상"
        },
        {
            "name": "SK텔레콤",
            "code": "017670",
            "per": "8.2배",
            "dividend": "5.5%",
            "sector": "통신",
            "oil_comment": "구독 기반 안정 현금흐름.",
            "sesang_comment": "5G 투자 마무리 후 배당 여력 확대"
        },
        {
            "name": "하나금융지주",
            "code": "086790",
            "per": "6.2배",
            "dividend": "5.3%",
            "sector": "금융지주",
            "oil_comment": "오일전문가 압도적 1위 보유종목.",
            "sesang_comment": "밸류업 프로그램 직접 수혜"
        },
        {
            "name": "KT",
            "code": "030200",
            "per": "7.5배",
            "dividend": "5.8%",
            "sector": "통신",
            "oil_comment": "배당 매력도 업계 최상위.",
            "sesang_comment": "AI 데이터센터 연계 가치 재평가 가능"
        },
        {
            "name": "삼성화재",
            "code": "000810",
            "per": "8.8배",
            "dividend": "4.2%",
            "sector": "보험",
            "oil_comment": "보험업 안정적 수익구조.",
            "sesang_comment": "금리 하락 시 채권 평가이익 기대"
        }
    ]

    rows = ""
    for s in stocks:
        rows += f'''<tr>
            <td class="col-name"><div><div>{s['name']}</div><div class="col-code">{s['code']}</div></div></td>
            <td class="col-per">{s['per']}</td>
            <td class="col-dividend" style="color: #e74c3c; font-weight: 700;">{s['dividend']}</td>
            <td>{s['sector']}</td>
            <td style="font-size: var(--font-sm);">🛢️ {s['oil_comment']} 🎓 {s['sesang_comment']}</td>
            <td class="col-link"><a href="https://finance.naver.com/item/main.nhn?code={s['code']}" target="_blank">📈</a></td>
        </tr>'''

    return f'''<details class="collapse-section value-collapse" style="margin-top: var(--space-lg);">
    <summary class="collapse-header" style="background: linear-gradient(135deg, rgba(46,204,113,0.15) 0%, rgba(46,204,113,0.05) 100%); border: 1px solid rgba(46,204,113,0.4); border-radius: 16px; padding: var(--space-md); cursor: pointer; display: flex; align-items: center; justify-content: space-between;">
        <span style="font-size: var(--font-md); font-weight: 700; color: var(--color-text);">💎 저평가 주식 발굴</span>
        <span style="font-size: var(--font-sm); color: var(--color-text-light);">오일전문가 × 세상학개론 전략 ▼</span>
    </summary>
    <div class="collapse-content" style="padding-top: var(--space-md);">
        <div class="card value-stocks-section">
            <h2 class="gurus-title">💎 저평가 주식 발굴</h2>
            <p style="text-align:center; color:var(--color-text-light); font-size:var(--font-sm); margin-bottom:var(--space-md);">PER 10배 이하 · 배당 5% 이상 · 오일전문가의 황금거위 전략 × 세상학개론 거시 흐름</p>

            <div class="portfolio-grid">
                <div class="portfolio-item"><div class="portfolio-label">스크리닝 기준</div><div class="portfolio-value">PER ≤ 10 · 배당 ≥ 5%</div></div>
                <div class="portfolio-item"><div class="portfolio-label">투자 철학</div><div class="portfolio-value">황금 거위 × 거시 흐름</div></div>
                <div class="portfolio-item"><div class="portfolio-label">리밸런싱</div><div class="portfolio-value positive">분기별 점검</div></div>
                <div class="portfolio-item"><div class="portfolio-label">현금 보유</div><div class="portfolio-value">20% 탄약 확보</div></div>
            </div>

            <div class="value-stocks-table-wrap" style="margin-top: var(--space-lg); overflow-x: auto;">
                <table class="stock-table" style="min-width: 640px;">
                    <thead><tr><th>종목</th><th>PER</th><th>배당률</th><th>업종</th><th>전문가 코멘트</th><th>네이버</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>

            <div style="margin-top: var(--space-lg); background: linear-gradient(135deg, rgba(46,204,113,0.08) 0%, rgba(52,152,219,0.08) 100%); border-radius: var(--card-radius); padding: var(--card-padding); border: 1px solid rgba(46,204,113,0.2);">
                <h3 style="font-size: var(--font-lg); margin-bottom: var(--space-md); color: #27ae60;">📚 저평가 전략 요약</h3>
                <div style="display: grid; gap: var(--space-md);">
                    <div style="display: flex; align-items: flex-start; gap: 0.75rem;">
                        <span style="font-size: 1.2rem;">🛢️</span>
                        <div><strong style="color: #2d3748;">오일전문가의 황금 거위</strong>
                        <p style="font-size: var(--font-sm); color: var(--color-text-light); margin-top: 4px;">PER 10배 이하, 배당 5% 이상, 5년 연속 배당 이력. 배당금으로 더 저렴한 거위를 사서 거위 수를 늘린다.</p></div>
                    </div>
                    <div style="display: flex; align-items: flex-start; gap: 0.75rem;">
                        <span style="font-size: 1.2rem;">🎓</span>
                        <div><strong style="color: #2d3748;">세상학개론의 거시 흐름</strong>
                        <p style="font-size: var(--font-sm); color: var(--color-text-light); margin-top: 4px;">금리 인하 사이클 진입 시 금융지주 NIM 압박 해소, 밸류업 프로그램 수혜, AI 인프라 투자로 통신사 재평가.</p></div>
                    </div>
                    <div style="display: flex; align-items: flex-start; gap: 0.75rem;">
                        <span style="font-size: 1.2rem;">⚠️</span>
                        <div><strong style="color: #2d3748;">리스크 관리</strong>
                        <p style="font-size: var(--font-sm); color: var(--color-text-light); margin-top: 4px;">금융 비중 30% 이하, 섹터 집중 금지. PER 20배 이상 재평가 시 절반 매도. 현금 20%는 탄약.</p></div>
                    </div>
                </div>
            </div>

            <div class="date-note" style="margin-top: var(--space-md);">📅 기준일: 2026년 5월 | ⚠️ 투자 유의사항: 본 정보는 참고용이며 투자 권유가 아닙니다</div>
        </div>
    </div>
</details>'''


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

    # 3. S등급 급등주 알람 체크 (텔레그램)
    try:
        from telegram_alert import check_and_alert_s_grade
        kospi = fresh_data.get('kospi_stocks', [])
        kosdaq = fresh_data.get('kosdaq_stocks', [])
        alert_result = check_and_alert_s_grade(kospi, kosdaq)
        if alert_result.get('sent'):
            alerted_names = [s.get('name', '') for s in alert_result.get('stocks', [])]
            print(f"🚨 S등급 알람 발송: {', '.join(alerted_names)}")
        else:
            print(f"📵 {alert_result.get('message', '알람 없음')}")
    except Exception as e:
        print(f"⚠️ S등급 알람 체크 실패: {e}")

    # 4. 히트맵 & 거래량 알림 생성 (DB 기반)
    extra_sections = generate_extra_sections(
        fresh_data.get('kospi_stocks', []),
        fresh_data.get('kosdaq_stocks', [])
    )
    fresh_data["extra_sections"] = extra_sections

    # 5. HTML 업데이트 (최종 데이터)
    update_html(fresh_data)

    print(f"\n✨ 작업 완료!")
    print(f"💡 장 마감 후에는 마지막 장중 데이터를 표시합니다.")


if __name__ == "__main__":
    main()
