#!/usr/bin/env python3
"""
거래량 폭발 감지 모듈
- 평균 거래량 대비 N배 급증한 종목 탐지
- Unusual Volume 알림 생성
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "stock_data.db"

# 거래량 폭발 기준 (배수)
VOLUME_ALERT_THRESHOLD = 3.0  # 평균 대비 3배 이상


def get_average_volume(stock_code, days=5):
    """특정 종목의 최근 N일 평균 거래량 계산"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 최근 N일간 해당 종목의 거래량 평균
    cursor.execute('''
        SELECT AVG(volume) as avg_volume
        FROM surge_stocks s
        JOIN stock_snapshots sn ON s.snapshot_id = sn.snapshot_id
        WHERE s.stock_code = ?
        AND sn.snapshot_time >= datetime('now', '-{} days')
        AND s.volume > 0
    '''.format(days), (stock_code,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result and result[0] else None


def detect_volume_spikes(date_str=None, threshold=VOLUME_ALERT_THRESHOLD):
    """
    오늘의 거래량 폭발 종목 탐지
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 오늘의 모든 급등주 조회
    cursor.execute('''
        SELECT s.stock_code, s.stock_name, s.volume, s.change_rate,
               s.market, sn.snapshot_time
        FROM surge_stocks s
        JOIN stock_snapshots sn ON s.snapshot_id = sn.snapshot_id
        WHERE DATE(sn.snapshot_time) = ?
        AND s.volume > 0
        ORDER BY s.volume DESC
    ''', (date_str,))
    
    today_stocks = cursor.fetchall()
    conn.close()
    
    alerts = []
    
    for stock in today_stocks:
        stock_code = stock["stock_code"]
        today_volume = stock["volume"]
        
        # 평균 거래량 조회
        avg_volume = get_average_volume(stock_code, days=5)
        
        if avg_volume and avg_volume > 0:
            ratio = today_volume / avg_volume
            
            if ratio >= threshold:
                # 폭발 수준 결정
                if ratio >= 10:
                    level = "🔥🔥🔥 SUPER SPIKE"
                    level_class = "super"
                elif ratio >= 5:
                    level = "🔥🔥 MAJOR SPIKE"
                    level_class = "major"
                else:
                    level = "🔥 MINOR SPIKE"
                    level_class = "minor"
                
                alerts.append({
                    "stock_code": stock_code,
                    "stock_name": stock["stock_name"],
                    "market": stock["market"],
                    "today_volume": today_volume,
                    "avg_volume": int(avg_volume),
                    "ratio": round(ratio, 1),
                    "change_rate": stock["change_rate"],
                    "level": level,
                    "level_class": level_class,
                    "time": stock["snapshot_time"]
                })
    
    # 거래량 배수 기준 정렬
    alerts.sort(key=lambda x: x["ratio"], reverse=True)
    
    return {
        "date": date_str,
        "threshold": threshold,
        "total_alerts": len(alerts),
        "alerts": alerts[:10]  # 상위 10개만
    }


def generate_volume_alert_html(alert_data):
    """거래량 폭발 알림 HTML 생성"""
    if not alert_data["alerts"]:
        return ''
    
    html = f'''
    <div class="volume-alerts" style="margin-top:20px;padding:20px;background:linear-gradient(135deg, #fff5f5 0%, #fff 100%);border:2px solid #feb2b2;border-radius:12px;">
        <h3 style="margin-bottom:15px;color:#c53030;display:flex;align-items:center;gap:8px;">
            ⚠️ 거래량 폭발 알림
            <span style="font-size:13px;font-weight:400;color:#666;">(평균 대비 {alert_data["threshold"]}배 이상)</span>
        </h3>
    '''
    
    for alert in alert_data["alerts"][:5]:  # 상위 5개만
        # 레벨별 색상
        color_map = {
            "super": "#c53030",
            "major": "#dd6b20",
            "minor": "#d69e2e"
        }
        color = color_map.get(alert["level_class"], "#718096")
        
        html += f'''
        <div style="padding:12px;margin-bottom:10px;background:#fff;border-radius:8px;border-left:4px solid {color};box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span style="font-weight:700;color:#2d3748;">{alert["stock_name"]}</span>
                    <span style="font-size:12px;color:#666;margin-left:5px;">{alert["stock_code"]}</span>
                    <span style="font-size:11px;color:#999;margin-left:5px;">({alert["market"]})</span>
                </div>
                <span style="font-size:12px;font-weight:700;color:{color};padding:4px 8px;background:{color}15;border-radius:4px;">
                    {alert["level"]}
                </span>
            </div>
            <div style="margin-top:8px;font-size:13px;color:#4a5568;">
                <span>📊 평균 대비 <strong style="color:{color};font-size:16px;">{alert["ratio"]}배</strong></span>
                <span style="margin:0 10px;color:#cbd5e0;">|</span>
                <span>거래량: {alert["today_volume"]:,}주</span>
                <span style="margin:0 10px;color:#cbd5e0;">|</span>
                <span>등락률: <strong style="color:#e53e3e;">+{alert["change_rate"]}%</strong></span>
            </div>
        </div>
        '''
    
    if len(alert_data["alerts"]) > 5:
        html += f'<div style="text-align:center;padding:10px;color:#999;font-size:12px;">외 {len(alert_data["alerts"]) - 5}개 더...</div>'
    
    html += '</div>'
    return html


def check_unusual_volume(stock_code=None, current_volume=None):
    """
    실시간 거래량 체크 (단일 종목)
    """
    if stock_code is None or current_volume is None:
        return None
    
    avg_volume = get_average_volume(stock_code)
    
    if avg_volume and avg_volume > 0:
        ratio = current_volume / avg_volume
        if ratio >= VOLUME_ALERT_THRESHOLD:
            return {
                "stock_code": stock_code,
                "current_volume": current_volume,
                "avg_volume": int(avg_volume),
                "ratio": round(ratio, 1),
                "is_spike": True
            }
    
    return {"is_spike": False}


if __name__ == "__main__":
    # 테스트
    alerts = detect_volume_spikes()
    print(json.dumps(alerts, ensure_ascii=False, indent=2))
