#!/usr/bin/env python3
"""
국민연금공단 대량보유주식 보고내역 수집 (DART OpenAPI)
금융감독원 전자공시시스템 opendart.fss.or.kr

[필요 사항]
1. https://opendart.fss.or.kr/ 에서 인증키 발급 (회원가입 후 OpenAPI 신청)
2. .env 에 DART_API_KEY=인증키 추가

[API 흐름]
1. list.json — 대량보유상황보고서 목록 (최근 1년)
2. flr_nm "국민연금공단" 필터
3. 종목별 최신 보고 기준으로 테이블 생성
4. 지분율은 DART 목록에 없으므로 rcept_no 기반 상세 링크 제공

[참고] list.json 응답 예시:
  {
    "corp_code": "00126380",
    "corp_name": "삼성전자",       ← 발행회사
    "stock_code": "005930",       ← 종목코드 (네이버 금융 링크용)
    "report_nm": "주식등의대량보유상황보고서(변동보고)",
    "rcept_no": "20250513000778", ← 접수번호 (상세 링크용)
    "flr_nm": "국민연금공단",     ← 보고자명
    "rcept_dt": "20250513",       ← 접수일
    "rm": "지분율 변동"            ← 비고
  }
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

# ── 환경변수 ─────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

load_env()

DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_BASE = "https://opendart.fss.or.kr/api"

BASE_DIR = Path(__file__).parent
NPS_JSON_PATH = BASE_DIR / "nps_holdings.json"
NPS_HTML_PATH = BASE_DIR / "nps_holdings.html"


def dart_list(params: Dict) -> Optional[Dict]:
    """DART list.json 호출"""
    url = f"{DART_BASE}/list.json"
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            print(f"❌ DART HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()
    except requests.RequestException as e:
        print(f"❌ DART 요청 실패: {e}")
        return None


def fetch_nps_reports() -> Optional[List[Dict]]:
    """
    DART에서 국민연금공단 대량보유상황보고서 목록 수집
    최근 1년간, 100개씩 페이지 순회
    """
    if not DART_API_KEY:
        print("❌ DART_API_KEY 미설정 — .env 에 DART 인증키를 추가하세요")
        print("   → https://opendart.fss.or.kr/ 에서 발급 가능")
        return None

    end_dt = datetime.now()
    bgn_dt = end_dt - timedelta(days=365)

    all_items: List[Dict] = []
    page_no = 1
    page_count = 100

    while True:
        params = {
            "crtfc_key": DART_API_KEY,
            "bgn_de": bgn_dt.strftime("%Y%m%d"),
            "end_de": end_dt.strftime("%Y%m%d"),
            "pblntf_detail_ty": "C",      # 대량보유상황보고서
            "page_count": page_count,
            "page_no": page_no,
        }

        data = dart_list(params)
        if data is None:
            return None

        # DART 에러 코드 처리
        status = data.get("status", "")
        if status != "000":
            msg = data.get("message", "unknown")
            print(f"❌ DART 에러: [{status}] {msg}")
            return None

        items = data.get("list", [])
        if not items:
            break

        # 국민연금공단 필터
        for item in items:
            flr = item.get("flr_nm", "")
            if "국민연금" in flr or "NPS" in flr.upper():
                all_items.append(item)

        total_page = data.get("total_page", 1)
        print(f"   → page {page_no}/{total_page}: {len(items)}건 중 NPS {sum(1 for i in items if '국민연금' in i.get('flr_nm',''))}건")

        if page_no >= total_page:
            break
        page_no += 1

        if page_no > 20:
            print("⚠️ 페이지 상한 도달")
            break

    print(f"   ✅ 총 수집: {len(all_items)}건")
    return all_items


def parse_report_name(report_nm: str) -> Dict[str, str]:
    """
    report_nm 에서 종목명/사유 추출
    예: "주식등의대량보유상황보고서(변동보고)" → {"type": "변동보고"}
    예: "주식등의대량보유상황보고서(삼성전자)" → {"stock": "삼성전자"}
    """
    m = re.search(r'\(([^)]+)\)', report_nm)
    inner = m.group(1) if m else ""

    # 괄호 안 내용이 종목명인지 사유인지 추론
    # 사유 패턴: 임의변경, 변동보고, 처분보고, 신규보고 등
    reason_keywords = ["변동", "신규", "처분", "임의변경", "변경", "보고"]
    is_reason = any(k in inner for k in reason_keywords) and len(inner) <= 10

    if is_reason:
        return {"reason": inner, "stock": ""}
    else:
        return {"reason": "", "stock": inner}


def deduplicate_by_stock(items: List[Dict]) -> List[Dict]:
    """
    같은 종목(stock_code 기준)이 여러 번 보고된 경우 최신 접수일(rcept_dt)만 남김
    """
    by_stock: Dict[str, Dict] = {}
    for item in items:
        code = item.get("stock_code", "").strip()
        if not code or code == "000000":
            # 종목코드가 없으면 corp_name 기준
            key = item.get("corp_name", "")
        else:
            key = code

        if key not in by_stock:
            by_stock[key] = item
        else:
            # 더 최신 보고로 교체
            existing_dt = by_stock[key].get("rcept_dt", "0")
            new_dt = item.get("rcept_dt", "0")
            if new_dt > existing_dt:
                by_stock[key] = item

    # 접수일 기준 내림차순
    result = list(by_stock.values())
    result.sort(key=lambda x: x.get("rcept_dt", ""), reverse=True)
    return result


def enrich_records(items: List[Dict]) -> List[Dict]:
    """DART 원본 → 표준화된 레코드"""
    records = []
    for raw in items:
        parsed = parse_report_name(raw.get("report_nm", ""))
        code = raw.get("stock_code", "").strip()
        corp = raw.get("corp_name", "").strip()

        record = {
            "stock_name": parsed.get("stock") or corp,
            "stock_code": code if code and code != "000000" else "",
            "corp_name": corp,
            "report_type": parsed.get("reason") or raw.get("rm", ""),
            "report_date": _fmt_date(raw.get("rcept_dt", "")),
            "rcept_no": raw.get("rcept_no", ""),
            "flr_nm": raw.get("flr_nm", ""),
            "report_nm": raw.get("report_nm", ""),
            "market": _infer_market(code),
        }
        records.append(record)
    return records


def _fmt_date(ymd: str) -> str:
    if len(ymd) == 8:
        return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
    return ymd


def _infer_market(code: str) -> str:
    if len(code) == 6:
        if code.startswith("0") and code[1] != "0":
            return "KOSDAQ"
    return "KOSPI"


def generate_nps_html(records: List[Dict]) -> str:
    """nps_holdings.html 생성"""
    now_kst = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    # 상위 30개
    top_n = 30
    top_records = records[:top_n]

    rows_html = ""
    for i, r in enumerate(top_records, 1):
        dart_link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"
        naver_link = f"https://finance.naver.com/item/main.nhn?code={r['stock_code']}" if r["stock_code"] else "#"

        type_badge_color = "#e67e22" if "변동" in r["report_type"] else "#3498db" if "신규" in r["report_type"] else "#95a5a6"

        rows_html += f'''<tr>
            <td class="col-rank">{i}</td>
            <td class="col-name">
                <div class="stock-name">{r["stock_name"]}</div>
                <div class="stock-code">{r["stock_code"]} <span class="market-badge {r["market"].lower()}">{r["market"]}</span></div>
            </td>
            <td class="col-type">
                <span class="type-badge" style="background:{type_badge_color}15;color:{type_badge_color};border:1px solid {type_badge_color}40">{r["report_type"]}</span>
            </td>
            <td class="col-date">{r["report_date"]}</td>
            <td class="col-link">
                <a href="{naver_link}" target="_blank" rel="noopener noreferrer">📈</a>
                <a href="{dart_link}" target="_blank" rel="noopener noreferrer" style="margin-left:8px">📋</a>
            </td>
        </tr>\n'''

    total = len(records)
    kospi_count = sum(1 for r in records if r["market"] == "KOSPI")
    kosdaq_count = sum(1 for r in records if r["market"] == "KOSDAQ")

    # TOP3 카드 (최신 3건)
    top3_cards = ""
    medal = ["🥇", "🥈", "🥉"]
    for idx, r in enumerate(records[:3], 0):
        top3_cards += f'''<div class="nps-top-card">
            <div class="top-rank">{medal[idx]}</div>
            <div class="top-name">{r["stock_name"]}</div>
            <div class="top-code">{r["stock_code"]} · {r["market"]}</div>
            <div class="top-type">{r["report_type"]}</div>
            <div class="top-date">{r["report_date"]}</div>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>국민연금 대량보유주식 | Surge Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans KR', -apple-system, sans-serif;
            background: linear-gradient(135deg, #f0f9ff 0%, #f5f3ff 50%, #fef5f5 100%);
            min-height: 100vh;
            color: #4a5568;
            line-height: 1.6;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 20px 20px 40px;
        }}
        header {{
            text-align: center;
            padding: 40px 0 20px;
        }}
        .back-link {{
            display: inline-block;
            margin-bottom: 15px;
            color: #a0aec0;
            text-decoration: none;
            font-size: 0.9rem;
        }}
        .back-link:hover {{ color: #667eea; }}
        header h1 {{
            font-size: 1.9rem;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        header p {{
            color: #a0aec0;
            font-size: 0.95rem;
            font-weight: 300;
        }}
        .update-time {{
            text-align: center;
            color: #a0aec0;
            font-size: 0.8rem;
            margin: 15px 0 25px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}
        .summary-card {{
            background: rgba(255,255,255,0.7);
            border-radius: 16px;
            padding: 16px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.8);
            backdrop-filter: blur(10px);
        }}
        .summary-number {{
            font-size: 1.6rem;
            font-weight: 700;
            color: #667eea;
        }}
        .summary-label {{
            font-size: 0.75rem;
            color: #a0aec0;
            margin-top: 4px;
        }}
        .top3-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .nps-top-card {{
            background: rgba(255,255,255,0.75);
            border-radius: 20px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.8);
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.05);
        }}
        .top-rank {{ font-size: 1.4rem; margin-bottom: 8px; }}
        .top-name {{ font-size: 1.1rem; font-weight: 600; color: #2d3748; }}
        .top-code {{ font-size: 0.75rem; color: #a0aec0; margin: 4px 0; }}
        .top-type {{
            font-size: 0.85rem;
            font-weight: 600;
            color: #e67e22;
            margin: 8px 0;
            padding: 2px 10px;
            background: rgba(230,126,34,0.1);
            border-radius: 12px;
            display: inline-block;
        }}
        .top-date {{ font-size: 0.8rem; color: #718096; }}

        .table-card {{
            background: rgba(255,255,255,0.7);
            border-radius: 24px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.8);
            backdrop-filter: blur(10px);
            overflow-x: auto;
        }}
        .table-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 16px;
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th {{
            text-align: left;
            padding: 10px 8px;
            color: #a0aec0;
            font-weight: 500;
            border-bottom: 1px solid #e2e8f0;
            white-space: nowrap;
        }}
        td {{
            padding: 12px 8px;
            border-bottom: 1px solid #edf2f7;
            vertical-align: middle;
        }}
        tr:hover td {{ background: rgba(102,126,234,0.03); }}

        .col-rank {{ width: 40px; text-align: center; color: #a0aec0; font-weight: 600; }}
        .col-name .stock-name {{ font-weight: 600; color: #2d3748; font-size: 0.95rem; }}
        .col-name .stock-code {{ font-size: 0.75rem; color: #a0aec0; margin-top: 2px; }}
        .market-badge {{
            font-size: 0.65rem;
            padding: 1px 5px;
            border-radius: 4px;
            font-weight: 500;
        }}
        .market-badge.kospi {{ background: #e6fffa; color: #319795; }}
        .market-badge.kosdaq {{ background: #fff5f5; color: #e53e3e; }}
        .col-type {{ min-width: 100px; }}
        .type-badge {{
            font-size: 0.75rem;
            padding: 3px 8px;
            border-radius: 10px;
            font-weight: 600;
            white-space: nowrap;
        }}
        .col-date {{ color: #718096; font-size: 0.85rem; }}
        .col-link {{ text-align: center; font-size: 1.1rem; white-space: nowrap; }}
        .col-link a {{ text-decoration: none; }}

        .notice {{
            margin-top: 24px;
            padding: 16px 20px;
            background: rgba(255,243,205,0.6);
            border-radius: 12px;
            border-left: 4px solid #ffc107;
            font-size: 0.8rem;
            color: #856404;
            line-height: 1.5;
        }}
        .notice code {{
            background: rgba(0,0,0,0.05);
            padding: 1px 4px;
            border-radius: 3px;
            font-family: monospace;
        }}

        @media (max-width: 640px) {{
            .top3-grid {{ grid-template-columns: 1fr; }}
            th, td {{ font-size: 0.8rem; padding: 8px 4px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <a href="index.html" class="back-link">← 급등주 알림으로 돌아가기</a>
            <h1>🏛️ 국민연금 대량보유주식</h1>
            <p>DART 공시 기반 — 국민연금공단 대량보유상황보고서 목록</p>
        </header>

        <div class="update-time">📅 업데이트: {now_kst} KST | 총 {total}개 종목 | 최근 1년</div>

        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-number">{total}</div>
                <div class="summary-label">보고 종목 수</div>
            </div>
            <div class="summary-card">
                <div class="summary-number">{kospi_count}</div>
                <div class="summary-label">KOSPI</div>
            </div>
            <div class="summary-card">
                <div class="summary-number">{kosdaq_count}</div>
                <div class="summary-label">KOSDAQ</div>
            </div>
            <div class="summary-card">
                <div class="summary-number">{records[0]["report_date"] if records else "-"}</div>
                <div class="summary-label">최신 보고일</div>
            </div>
        </div>

        <div class="top3-grid">
            {top3_cards}
        </div>

        <div class="table-card">
            <div class="table-title">📊 보고 현황 상위 {top_n}개</div>
            <table>
                <thead>
                    <tr>
                        <th class="col-rank">#</th>
                        <th>종목</th>
                        <th>보고 유형</th>
                        <th>접수일</th>
                        <th>링크</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <div class="notice">
            <strong>ℹ️ 데이터 안내</strong><br>
            • 본 데이터는 <strong>금융감독원 DART</strong>에서 제공하는 공시 목록입니다.<br>
            • 지분율은 DART 목록 API에 포함되지 않아 <strong>📋 버튼</strong>으로 원문 보고서를 확인하세요.<br>
            • 같은 종목이 여러 번 보고된 경우 <strong>최신 접수일 기준</strong>으로 중복 제거됩니다.<br>
            • 📈 버튼: 네이버 금융 종목 페이지 · 📋 버튼: DART 공시 원문 보기<br>
            • DART API 키 발급: <code>https://opendart.fss.or.kr</code>
        </div>
    </div>
</body>
</html>'''
    return html


def main():
    print("🏛️ 국민연금 대량보유주식 데이터 수집 시작 (DART)")
    print(f"   → DART API 키: {'설정됨' if DART_API_KEY else '미설정'}")

    items = fetch_nps_reports()
    if items is None:
        print("⚠️ API 미설정 또는 오류 — 기존 데이터 사용 시도")
        if NPS_JSON_PATH.exists():
            with open(NPS_JSON_PATH, 'r', encoding='utf-8') as f:
                records = json.load(f)
            print(f"   → 기존 데이터 {len(records)}건 로드")
        else:
            print("❌ 기존 데이터도 없음 — 종료")
            # 빈 페이지라도 생성 (사용자 경험)
            records = []
    else:
        deduped = deduplicate_by_stock(items)
        records = enrich_records(deduped)
        with open(NPS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"   ✅ {len(records)}건 저장 → {NPS_JSON_PATH}")

    html = generate_nps_html(records)
    with open(NPS_HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"   ✅ HTML 생성 → {NPS_HTML_PATH}")

    print("✨ 완료")


if __name__ == "__main__":
    main()
