#!/usr/bin/env python3
"""
섹터별 급등 히트맵 생성 모듈
- 오늘의 급등주들을 업종별로 집계
- 히트맵 시각화 데이터 생성
"""

import sqlite3
import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent / "stock_data.db"


# 업종 매핑 (KOSPI/KOSDAQ 종목코드 기반)
SECTOR_MAP = {
    # 반도체
    "005930": "반도체", "000660": "반도체", "006400": "반도체", "035720": "반도체",
    "068270": "반도체", "096770": "반도체", "102280": "반도체",
    # 금융
    "105560": "금융", "055550": "금융", "086790": "금융", "003550": "금융",
    "004170": "금융", "031440": "금융",
    # 바이오
    "068270": "바이오", "207940": "바이오", "006280": "바이오", "128940": "바이오",
    # 에너지
    "003550": "에너지", "010950": "에너지", "000720": "에너지", "015760": "에너지",
    # 자동차
    "005380": "자동차", "000270": "자동차", "012330": "자동차", "011210": "자동차",
    # IT/소프트웨어
    "035720": "IT", "035760": "IT", "035900": "IT", "018260": "IT",
    # 배터리
    "005490": "배터리", "051910": "배터리", "006360": "배터리",
    # 디스플레이
    "034220": "디스플레이", "034730": "디스플레이", "066570": "디스플레이",
}


def get_sector_by_code(stock_code, stock_name=""):
    """종목코드로 업종 추정"""
    # 정확한 매핑
    if stock_code in SECTOR_MAP:
        return SECTOR_MAP[stock_code]
    
    # 이름 기반 추정
    name = stock_name.upper()
    sector_keywords = {
        "반도체": ["반도체", "칩", "소재", "반도"],
        "금융": ["금융", "보험", "증권", "카드"],
        "바이오": ["바이오", "제약", "의약", "헬스케어", "치료"],
        "에너지": ["에너지", "전력", "발전", "유류", "가스"],
        "자동차": ["자동차", "차", "모빌리티"],
        "IT": ["소프트웨어", "플랫폼", "플랫폼", "IT", "게임", "메타버스"],
        "배터리": ["배터리", "이차전지", "리튬"],
        "디스플레이": ["디스플레이", "LCD", "OLED", "패널"],
        "건설": ["건설", "건축"],
        "유통": ["유통", "백화점", "마트", "쇼핑"],
        "철강": ["철강", "강철", "철강재"],
        "조선": ["조선", "선박"],
        "미디어": ["방송", "미디어", "엔터", "콘텐츠"],
    }
    
    for sector, keywords in sector_keywords.items():
        for kw in keywords:
            if kw in name:
                return sector
    
    return "기타"


def get_sector_heatmap(date_str=None):
    """특정 날짜의 섹터별 급등 히트맵 생성"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 해당 날짜의 모든 급등주 조회
    cursor.execute('''
        SELECT s.stock_code, s.stock_name, s.change_rate, s.market, 
               sn.snapshot_time
        FROM surge_stocks s
        JOIN stock_snapshots sn ON s.snapshot_id = sn.snapshot_id
        WHERE DATE(sn.snapshot_time) = ?
        ORDER BY s.change_rate DESC
    ''', (date_str,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # 섹터별 집계
    sector_stats = defaultdict(lambda: {
        "count": 0,
        "avg_change": 0.0,
        "max_change": 0.0,
        "stocks": [],
        "total_volume": 0
    })
    
    for row in rows:
        sector = get_sector_by_code(row["stock_code"], row["stock_name"])
        stats = sector_stats[sector]
        stats["count"] += 1
        stats["max_change"] = max(stats["max_change"], row["change_rate"])
        stats["stocks"].append({
            "code": row["stock_code"],
            "name": row["stock_name"],
            "change": row["change_rate"],
            "market": row["market"]
        })
    
    # 평균 계산
    for sector, stats in sector_stats.items():
        if stats["stocks"]:
            stats["avg_change"] = sum(s["change"] for s in stats["stocks"]) / len(stats["stocks"])
    
    # 정렬 (종목수 많은 순 → 평균 등락률 높은 순)
    sorted_sectors = sorted(
        sector_stats.items(),
        key=lambda x: (x[1]["count"], x[1]["avg_change"]),
        reverse=True
    )
    
    return {
        "date": date_str,
        "total_stocks": len(rows),
        "sectors": [
            {
                "name": name,
                "count": stats["count"],
                "avg_change": round(stats["avg_change"], 2),
                "max_change": round(stats["max_change"], 2),
                "top_stock": stats["stocks"][0] if stats["stocks"] else None,
                "stocks": stats["stocks"][:5]  # 상위 5개만
            }
            for name, stats in sorted_sectors
        ]
    }


def generate_heatmap_html(heatmap_data):
    """히트맵 HTML 생성"""
    if not heatmap_data["sectors"]:
        return '<div style="padding:20px;text-align:center;color:#999;">📊 오늘의 급등주 데이터가 없습니다</div>'
    
    # 색상 결정 함수
    def get_color(count, max_count):
        ratio = count / max_count if max_count > 0 else 0
        if ratio >= 0.7:
            return "#ff4757"  # 강한 빨강
        elif ratio >= 0.5:
            return "#ffa502"  # 주황
        elif ratio >= 0.3:
            return "#2ed573"  # 초록
        else:
            return "#747d8c"  # 회색
    
    max_count = max(s["count"] for s in heatmap_data["sectors"]) if heatmap_data["sectors"] else 1
    
    html = f'''
    <div class="sector-heatmap">
        <h3 style="margin-bottom:15px;color:#2d3748;">🔥 오늘 뜨는 섹터</h3>
        <p style="font-size:13px;color:#666;margin-bottom:20px;">
            {heatmap_data["date"]} 기준 총 {heatmap_data["total_stocks"]}개 종목
        </p>
        <div style="display:flex;flex-wrap:wrap;gap:10px;">
    '''
    
    for sector in heatmap_data["sectors"][:8]:  # 상위 8개만
        color = get_color(sector["count"], max_count)
        top_stock = sector["top_stock"]
        top_info = f"{top_stock['name']} +{top_stock['change']}%" if top_stock else ""
        
        html += f'''
        <div style="flex:1;min-width:120px;padding:15px;border-radius:12px;background:{color}15;border:2px solid {color};text-align:center;">
            <div style="font-size:20px;font-weight:700;color:{color};">{sector["name"]}</div>
            <div style="font-size:24px;font-weight:800;color:#2d3748;margin:5px 0;">{sector["count"]}개</div>
            <div style="font-size:12px;color:#666;">평균 +{sector["avg_change"]}%</div>
            {f'<div style="font-size:11px;color:#999;margin-top:5px;">🏆 {top_info}</div>' if top_info else ''}
        </div>
        '''
    
    html += '</div></div>'
    return html


if __name__ == "__main__":
    # 테스트
    heatmap = get_sector_heatmap()
    print(json.dumps(heatmap, ensure_ascii=False, indent=2))
