#!/usr/bin/env python3
"""
급등주 데이터 수집 스크립트 (템플릿 버전)
매일 아침 실행: 전일 급등 종목 데이터 수집 및 HTML 업데이트
"""

import json
import requests
from datetime import datetime, timedelta
import os

def fetch_surge_stocks():
    """
    전일 급등주 데이터 수집
    실제 API 연동 전 샘플 데이터 반환
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 샘플 데이터 (API 연결 후 대체)
    sample_data = [
        {
            "name": "삼성전자",
            "code": "005930",
            "price": "72,300",
            "change": "+5.2%",
            "volume": "15.2M",
            "reason": "AI 반도체 수주 증가 소식"
        },
        {
            "name": "SK하이닉스", 
            "code": "000660",
            "price": "145,000",
            "change": "+8.1%",
            "volume": "8.1M",
            "reason": "HBM3E 공급 확대 기대감"
        }
    ]
    
    return {
        "date": yesterday,
        "stocks": sample_data
    }

def generate_stock_cards(stocks):
    """주식 카드 HTML 생성"""
    if not stocks:
        return '<div class="empty">오늘은 급등 종목이 없습니다.</div>'
    
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
    
    # 템플릿 파일 읽기
    template_path = os.path.join(os.path.dirname(__file__), 'template.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # 주식 카드 HTML 생성
    stock_cards = generate_stock_cards(data["stocks"])
    
    # 플레이스홀더 치환 (현재 시간으로 업데이트)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_content = template.replace('{{UPDATE_DATE}}', current_time)
    html_content = html_content.replace('{{STOCK_CARDS}}', stock_cards)
    
    # index.html 저장
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML 업데이트 완료: {data['date']}")

def main():
    print(f"🚀 급등주 데이터 수집 시작: {datetime.now()}")
    
    # 데이터 수집
    data = fetch_surge_stocks()
    
    # HTML 업데이트
    update_html(data)
    
    print("✨ 작업 완료!")

if __name__ == "__main__":
    main()
