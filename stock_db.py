#!/usr/bin/env python3
"""
한국투자증권 API 데이터 SQLite DB 관리 모듈
- stock_snapshots: 시점별 스냅샷 (메타데이터)
- surge_stocks: 급등주 상세 데이터
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "stock_data.db"


def init_db():
    """DB 초기화 및 테이블 생성"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 스냅샷 테이블 (시점별 메타데이터)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_time TEXT NOT NULL,
            market_status TEXT NOT NULL,
            data_source TEXT NOT NULL,
            total_kospi INTEGER DEFAULT 0,
            total_kosdaq INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 급등주 상세 데이터 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS surge_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            current_price REAL,
            change_rate REAL,
            volume INTEGER,
            trade_amount INTEGER,
            alert_level TEXT DEFAULT 'NORMAL',
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (snapshot_id) REFERENCES stock_snapshots (snapshot_id)
        )
    ''')
    
    # 인덱스 생성 (조회 성능)
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_snapshot_time 
        ON stock_snapshots (snapshot_time)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_surge_market 
        ON surge_stocks (market, snapshot_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_surge_stock 
        ON surge_stocks (stock_code, snapshot_id)
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ DB 초기화 완료: {DB_PATH}")


def save_snapshot(market_status, data_source, total_kospi=0, total_kosdaq=0):
    """스냅샷 저장 및 ID 반환"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO stock_snapshots 
        (snapshot_time, market_status, data_source, total_kospi, total_kosdaq)
        VALUES (?, ?, ?, ?, ?)
    ''', (snapshot_time, market_status, data_source, total_kospi, total_kosdaq))
    
    snapshot_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return snapshot_id


def save_stocks(snapshot_id, market, stocks):
    """급등주 데이터 저장"""
    if not stocks:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for stock in stocks:
        # change_rate 추출 (change_rate 키 우선, 없으면 change 키에서 파싱)
        change_rate = stock.get('change_rate', 0)
        if not change_rate:
            change_str = stock.get('change', '0%')
            try:
                change_rate = float(change_str.replace('%', '').replace('+', ''))
            except (ValueError, TypeError):
                change_rate = 0.0
        
        cursor.execute('''
            INSERT INTO surge_stocks 
            (snapshot_id, market, stock_code, stock_name, current_price, 
             change_rate, volume, trade_amount, alert_level, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            snapshot_id,
            market,
            stock.get('code', ''),
            stock.get('name', ''),
            stock.get('price', 0),
            change_rate,
            stock.get('volume', 0),
            stock.get('trade_amount', 0),
            stock.get('alert_level', 'NORMAL'),
            stock.get('reason', '')
        ))
    
    conn.commit()
    conn.close()
    print(f"💾 {market} {len(stocks)}개 저장 완료")


def get_latest_snapshot():
    """최신 스냅샷 조회"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM stock_snapshots 
        ORDER BY snapshot_time DESC LIMIT 1
    ''')
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'snapshot_id': row[0],
            'snapshot_time': row[1],
            'market_status': row[2],
            'data_source': row[3],
            'total_kospi': row[4],
            'total_kosdaq': row[5]
        }
    return None


def get_stocks_by_snapshot(snapshot_id, market=None):
    """특정 스냅샷의 급등주 조회"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if market:
        cursor.execute('''
            SELECT * FROM surge_stocks 
            WHERE snapshot_id = ? AND market = ?
            ORDER BY change_rate DESC
        ''', (snapshot_id, market))
    else:
        cursor.execute('''
            SELECT * FROM surge_stocks 
            WHERE snapshot_id = ?
            ORDER BY market, change_rate DESC
        ''', (snapshot_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_daily_summary(date_str=None):
    """일별 요약 통계"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(DISTINCT snapshot_id) as total_snapshots,
            SUM(total_kospi) as total_kospi_stocks,
            SUM(total_kosdaq) as total_kosdaq_stocks
        FROM stock_snapshots
        WHERE DATE(snapshot_time) = ?
    ''', (date_str,))
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'date': date_str,
        'total_snapshots': row[0] or 0,
        'total_kospi_stocks': row[1] or 0,
        'total_kosdaq_stocks': row[2] or 0
    }


def get_stock_history(stock_code, days=7):
    """특정 종목의 최근 이력 조회"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, sn.snapshot_time
        FROM surge_stocks s
        JOIN stock_snapshots sn ON s.snapshot_id = sn.snapshot_id
        WHERE s.stock_code = ?
        AND sn.snapshot_time >= datetime('now', '-{} days')
        ORDER BY sn.snapshot_time DESC
    '''.format(days), (stock_code,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def export_to_json(date_str=None, output_path=None):
    """특정 날짜 데이터를 JSON으로 내보내기"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    if output_path is None:
        output_path = f"stock_data_{date_str}.json"
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, sn.snapshot_time, sn.market_status
        FROM surge_stocks s
        JOIN stock_snapshots sn ON s.snapshot_id = sn.snapshot_id
        WHERE DATE(sn.snapshot_time) = ?
        ORDER BY sn.snapshot_time DESC, s.change_rate DESC
    ''', (date_str,))
    
    rows = cursor.fetchall()
    conn.close()
    
    data = [dict(row) for row in rows]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"📤 JSON 내보내기 완료: {output_path} ({len(data)}개)")
    return output_path


if __name__ == "__main__":
    # DB 초기화 실행
    init_db()
    print("\n📊 DB 테이블 구조:")
    print("- stock_snapshots: 시점별 스냅샷 (메타데이터)")
    print("- surge_stocks: 급등주 상세 데이터")
    print("\n💡 사용법:")
    print("  from stock_db import init_db, save_snapshot, save_stocks")
    print("  init_db()  # 최초 1회 실행")
