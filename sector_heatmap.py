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

# 섹터 이모티콘 매핑
SECTOR_EMOJIS = {
    "반도체": "💻",
    "금융": "🏦",
    "바이오": "💊",
    "에너지": "⚡",
    "자동차": "🚗",
    "IT": "📱",
    "배터리": "🔋",
    "디스플레이": "📺",
    "건설": "🏗️",
    "유통": "🛒",
    "철강": "🏭",
    "조선": "🚢",
    "미디어": "🎬",
    "기타": "📦",
}

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
        AND sn.snapshot_id = (SELECT MAX(snapshot_id) FROM stock_snapshots WHERE DATE(snapshot_time) = ?)
        ORDER BY s.change_rate DESC
    ''', (date_str, date_str))
    
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
        # change_rate를 float으로 안전하게 변환
        try:
            change_val = float(row["change_rate"])
        except (ValueError, TypeError):
            change_val = 0.0
        stats["max_change"] = max(stats["max_change"], change_val)
        stats["stocks"].append({
            "code": row["stock_code"],
            "name": row["stock_name"],
            "change": change_val,
            "market": row["market"]
        })
    
    # 평균 계산
    for sector, stats in sector_stats.items():
        if stats["stocks"]:
            changes = [s["change"] for s in stats["stocks"] if isinstance(s["change"], (int, float))]
            if changes:
                stats["avg_change"] = sum(changes) / len(changes)
    
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
    """컴팩트 히트맵 HTML 생성 — chip/badge 형태"""
    if not heatmap_data["sectors"]:
        return '<div style="padding:20px;text-align:center;color:#999;font-size:0.85rem;">📊 오늘의 급등주 데이터가 없습니다</div>'
    
    # Heat intensity 점수 계산: 평균 등락률 가중치 + 종목 수 가중치
    def get_heat_score(sector):
        avg = sector["avg_change"]
        cnt = sector["count"]
        return avg * 3 + cnt * 0.8
    
    scores = [get_heat_score(s) for s in heatmap_data["sectors"]]
    max_score = max(scores) if scores else 1
    
    def get_heat_bg(score):
        ratio = score / max_score if max_score > 0 else 0
        # 연한 배경색들
        if ratio >= 0.8:
            return "#ffebee"  # 매우 뜨거움 — 연한 빨강
        elif ratio >= 0.6:
            return "#fff3e0"  # 뜨거움 — 연한 주황
        elif ratio >= 0.4:
            return "#fff8e1"  # 따뜻함 — 연한 노랑
        elif ratio >= 0.2:
            return "#e8f5e9"  # 미약 — 연한 초록
        else:
            return "#eceff1"  # 차가움 — 연한 회청
    
    def get_heat_color(score):
        ratio = score / max_score if max_score > 0 else 0
        if ratio >= 0.8:
            return "#d32f2f"
        elif ratio >= 0.6:
            return "#e65100"
        elif ratio >= 0.4:
            return "#f57c00"
        elif ratio >= 0.2:
            return "#388e3c"
        else:
            return "#546e7a"
    
    total_stocks = heatmap_data["total_stocks"]
    date_str = heatmap_data["date"]
    
    html = f'''<div class="heatmap-compact">
    <div class="heatmap-compact-header">
        <span>🔥 오늘 뜨는 섹터</span>
        <span class="heatmap-compact-count">총 {total_stocks}개</span>
    </div>
    <div class="heatmap-chips">
'''
    
    for sector in heatmap_data["sectors"][:8]:  # 상위 8개 섹터
        score = get_heat_score(sector)
        bg = get_heat_bg(score)
        color = get_heat_color(score)
        emoji = SECTOR_EMOJIS.get(sector["name"], "📦")
        name = sector["name"]
        count = sector["count"]
        avg = sector["avg_change"]
        
        html += f'''<div class="heat-chip" style="background:{bg};color:{color};">
    <span class="chip-emoji">{emoji}</span>
    <span class="chip-name">{name}</span>
    <span class="chip-count">{count}종목</span>
    <span class="chip-avg">+{avg:.1f}%</span>
</div>
'''
    
    html += '''    </div>
</div>'''
    
    return html


if __name__ == "__main__":
    # 테스트
    heatmap = get_sector_heatmap()
    print(json.dumps(heatmap, ensure_ascii=False, indent=2))
