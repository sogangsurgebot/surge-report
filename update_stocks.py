#!/usr/bin/env python3
"""
급등주 데이터 수집 스크립트
매일 아침 실행: 전일 급등 종목 데이터 수집 및 HTML 업데이트
"""

import json
import requests
from datetime import datetime, timedelta
import os

# TODO: 한국투자증권 API 또는 Yahoo Finance API 키 설정
# KRX (한국거래소) API 또는 다른 데이터 소스 사용 가능

def fetch_surge_stocks():
    """
    전일 급등주 데이터 수집
    실제 API 연동 전 샘플 데이터 반환
    """
    # TODO: 실제 API 연결
    # 예시: 한국투자증권 KIS Open API, Yahoo Finance, 등
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 샘플 데이터 (API 연결 후 대체)
    sample_data = [
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
    
    return {
        "date": yesterday,
        "stocks": sample_data
    }

def update_html(data):
    """HTML 파일 업데이트"""
    
    stocks_html = ""
    for stock in data["stocks"]:
        stocks_html += f'''
        <div class="stock-card">
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
                    <div class="price-value">{stock["change"]}</div>
                </div>
                <div class="price-item">
                    <div class="price-label">거래량</div>
                    <div class="price-value" style="font-size: 1.1rem;">{stock["volume"]}</div>
                </div>
            </div>
            <div class="reason">
                📊 {stock["reason"]}
            </div>
        </div>
'''

    html_content = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>급등주 알림 | Surge Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        header {{
            text-align: center;
            padding: 40px 0;
        }}
        header h1 {{
            font-size: 2.5rem;
            background: linear-gradient(90deg, #ff6b6b, #ffd93d);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        header p {{ color: #888; }}
        .update-time {{
            text-align: center;
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 20px;
        }}
        .stock-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 20px;
            margin: 15px 0;
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
        }}
        .stock-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .stock-name {{
            font-size: 1.3rem;
            font-weight: bold;
        }}
        .stock-code {{ color: #888; font-size: 0.9rem; }}
        .surge-badge {{
            background: #e74c3c;
            color: #fff;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: bold;
        }}
        .price-info {{
            display: flex;
            gap: 20px;
            margin-top: 15px;
        }}
        .price-item {{
            text-align: center;
        }}
        .price-label {{ color: #888; font-size: 0.8rem; }}
        .price-value {{ font-size: 1.5rem; font-weight: bold; color: #ff6b6b; }}
        .reason {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: #aaa;
            font-size: 0.95rem;
        }}
        .telegram-cta {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #0088cc;
            color: #fff;
            padding: 15px 30px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: bold;
            box-shadow: 0 4px 15px rgba(0,136,204,0.4);
        }}
        .empty {{
            text-align: center;
            padding: 60px 20px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📈 급등주 알림</h1>
            <p>실시간 급등 종목 정보</p>
        </header>
        
        <div class="update-time">
            🕐 마지막 업데이트: {data["date"]} 08:00
        </div>
        
        {stocks_html if stocks_html else '<div class="empty">오늘은 급등 종목이 없습니다.</div>'}
    </div>

    <a href="https://t.me/sogangsurgebot" class="telegram-cta" target="_blank">
        📱 텔레그램으로 알림받기
    </a>
</body>
</html>
'''
    
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
