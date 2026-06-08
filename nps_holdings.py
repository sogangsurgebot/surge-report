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
    DART에서 국민연금공단 보고서 목록 수집 (모든 공시 유형)
    최근 1년간, 100개씩 페이지 순회
    """
    if not DART_API_KEY:
        print("❌ DART_API_KEY 미설정 — .env 에 DART 인증키를 추가하세요")
        print("   → https://opendart.fss.or.kr/ 에서 발급 가능")
        return None

    end_dt = datetime.now()
    bgn_dt = end_dt - timedelta(days=60)  # DART: corp_code 없으면 ~60일 제한

    all_items: List[Dict] = []
    page_no = 1
    page_count = 100

    while True:
        params = {
            "crtfc_key": DART_API_KEY,
            "bgn_de": bgn_dt.strftime("%Y%m%d"),
            "end_de": end_dt.strftime("%Y%m%d"),
            "pblntf_detail_ty": "D001",
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

        if page_no > 50:
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
    reason_keywords = ["변동", "신규", "처분", "임의변경", "변경", "보고", "약식", "일반"]
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
    """nps_holdings.html 생성 — index.html/gurus.html 동일 디자인 시스템"""
    now_kst = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    top_n = 30
    top_records = records[:top_n]

    rows_html = ""
    for i, r in enumerate(top_records, 1):
        dart_link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"
        naver_link = f"https://m.stock.naver.com/domestic/stock/{r['stock_code']}" if r["stock_code"] else "#"
        type_badge_color = "#e67e22" if "변동" in r["report_type"] else "#3498db" if "신규" in r["report_type"] else "#95a5a6"
        type_label = r["report_type"] if r["report_type"] else "보고"

        rows_html += f'''<tr>
            <td class="col-rank">{i}</td>
            <td class="col-name">
                <div class="stock-name">{r["stock_name"]}</div>
                <div class="stock-code">{r["stock_code"]} <span class="market-badge {r["market"].lower()}">{r["market"]}</span></div>
            </td>
            <td class="col-type">
                <span class="type-badge" style="background:{type_badge_color}15;color:{type_badge_color};border:1px solid {type_badge_color}40">{type_label}</span>
            </td>
            <td class="col-date">{r["report_date"]}</td>
            <td class="col-link">
                <a href="{naver_link}" target="_blank" rel="noopener noreferrer" class="link-btn">📈</a>
                <a href="{dart_link}" target="_blank" rel="noopener noreferrer" class="link-btn" style="margin-left:6px">📋</a>
            </td>
        </tr>\n'''

    total = len(records)

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
    <meta name="theme-color" content="#ff9a9e">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>🏛️ 국민연금 대량보유주식 | Surge Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --color-primary: #ff9a9e;
            --color-secondary: #fad0c4;
            --color-accent: #a18cd1;
            --color-text: #4a5568;
            --color-text-light: #a0aec0;
            --color-bg: linear-gradient(135deg, #fef5f5 0%, #f5f3ff 50%, #f0f9ff 100%);
            --card-bg: rgba(255,255,255,0.72);
            --card-border: rgba(255,255,255,0.85);
            --space-xs: 8px;
            --space-sm: 12px;
            --space-md: 16px;
            --space-lg: 20px;
            --space-xl: 28px;
            --font-xs: 0.75rem;
            --font-sm: 0.85rem;
            --font-md: 0.95rem;
            --font-lg: 1.1rem;
            --font-xl: 1.6rem;
            --font-2xl: 2rem;
            --card-radius: 20px;
            --card-padding: 20px;
            --container-max: 720px;
            --grid-gap: 16px;
            --shadow-soft: 0 8px 32px rgba(31,38,135,0.08);
            --shadow-card: 0 4px 24px rgba(0,0,0,0.06);
        }}
        @media (min-width: 640px) {{
            :root {{
                --space-xs: 10px;
                --space-sm: 14px;
                --space-md: 20px;
                --space-lg: 28px;
                --space-xl: 32px;
                --font-xs: 0.8rem;
                --font-sm: 0.9rem;
                --font-md: 1rem;
                --font-lg: 1.2rem;
                --font-xl: 1.8rem;
                --font-2xl: 2.2rem;
                --card-radius: 24px;
                --card-padding: 28px;
                --grid-gap: 20px;
                --container-max: 900px;
            }}
        }}
        @media (min-width: 1024px) {{
            :root {{ --container-max: 1200px; }}
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--color-bg);
            background-attachment: fixed;
            min-height: 100vh;
            color: var(--color-text);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{ max-width: var(--container-max); margin: 0 auto; padding: var(--space-md) var(--space-md) var(--space-xl); }}

        /* 헤더 */
        header {{ text-align: center; padding: var(--space-xl) 0 var(--space-lg); }}
        .logo {{ font-size: var(--font-2xl); margin-bottom: var(--space-sm); display: inline-block; animation: float 3s ease-in-out infinite; }}
        @keyframes float {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-8px)}} }}
        header h1 {{
            font-size: var(--font-xl); font-weight: 800;
            background: linear-gradient(135deg, #ff9a9e 0%, #a18cd1 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: var(--space-xs); letter-spacing: -0.5px;
        }}
        header p {{ color: var(--text-light); font-size: var(--font-sm); font-weight: 400; }}
        .version-link {{
            display: inline-block; margin-top: var(--space-sm); color: var(--color-text-light);
            font-size: var(--font-xs); text-decoration: none; opacity: 0.7; transition: opacity 0.2s;
        }}
        .version-link:hover {{ opacity: 1; }}

        /* 탭 */
        .tab-nav {{
            display: flex; justify-content: center; gap: var(--space-xs);
            margin: var(--space-lg) 0 var(--space-xl); flex-wrap: wrap;
        }}
        .tab-link {{
            padding: 10px 20px; border-radius: 20px; text-decoration: none;
            color: var(--text-light); font-size: var(--font-sm); font-weight: 500;
            background: rgba(255,255,255,0.5); border: 1px solid rgba(255,255,255,0.8);
            backdrop-filter: blur(10px); transition: all 0.25s ease; cursor: pointer;
        }}
        .tab-link:hover {{
            background: rgba(255,255,255,0.9); color: var(--color-primary);
            transform: translateY(-1px); box-shadow: var(--shadow-card);
        }}
        .tab-link.active {{
            background: linear-gradient(135deg, rgba(255,154,158,0.15) 0%, rgba(118,75,162,0.15) 100%);
            color: var(--color-primary); border-color: rgba(102,126,234,0.3); font-weight: 600;
        }}

        /* 카드 */
        .card {{
            background: var(--card-bg); border-radius: var(--card-radius); padding: var(--card-padding);
            margin: var(--space-md) 0; border: 1px solid var(--card-border);
            backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            box-shadow: var(--shadow-soft); transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .card:hover {{ transform: translateY(-2px); box-shadow: 0 12px 40px rgba(31,38,135,0.12); }}

        /* 요약 */
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-sm); margin-bottom: var(--space-lg); }}
        .summary-card {{ text-align: center; padding: var(--space-md) var(--space-sm); }}
        .summary-number {{
            font-size: 1.8rem; font-weight: 800;
            background: linear-gradient(135deg, #ff9a9e 0%, #a18cd1 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }}
        .summary-label {{ font-size: var(--font-xs); color: var(--color-text-light); font-weight: 500; }}

        /* TOP3 */
        .top3-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-md); margin-bottom: var(--space-lg); }}
        .nps-top-card {{ text-align: center; padding: var(--space-lg) var(--space-md); }}
        .top-rank {{ font-size: 2rem; margin-bottom: 8px; }}
        .top-name {{ font-size: var(--font-lg); font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }}
        .top-code {{ font-size: var(--font-xs); color: var(--color-text-light); margin: var(--space-xs) 0; }}
        .top-type {{
            font-size: var(--font-xs); font-weight: 600; color: #e67e22; margin: var(--space-xs) 0;
            padding: 3px 12px; background: rgba(230,126,34,0.08); border-radius: 12px; display: inline-block;
        }}
        .top-date {{ font-size: var(--font-xs); color: var(--color-text-light); margin-top: var(--space-xs); }}

        /* 테이블 */
        .table-card {{ overflow-x: auto; padding: var(--card-padding); }}
        .section-title {{
            font-size: var(--font-lg); font-weight: 700; color: var(--text-primary);
            margin-bottom: var(--space-md); display: flex; align-items: center; gap: var(--space-xs);
        }}
        .stock-table {{
            width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--font-sm);
        }}
        .stock-table th {{
            text-align: left; padding: 12px 10px; color: var(--text-light); font-weight: 600;
            font-size: var(--font-xs); text-transform: uppercase; letter-spacing: 0.5px;
            border-bottom: 2px solid rgba(255,154,158,0.12); white-space: nowrap;
        }}
        .stock-table td {{
            padding: 14px 10px; border-bottom: 1px solid rgba(0,0,0,0.04); vertical-align: middle;
        }}
        .stock-table tr:hover td {{ background: rgba(255,154,158,0.03); }}
        .stock-table tr:last-child td {{ border-bottom: none; }}
        .col-rank {{ width: 40px; text-align: center; color: var(--text-light); font-weight: 700; font-size: var(--font-sm); }}
        .col-name .stock-name {{ font-weight: 700; color: var(--color-text); font-size: var(--font-sm); }}
        .col-name .stock-code {{ font-size: var(--font-xs); color: var(--color-text-light); margin-top: 3px; }}
        .market-badge {{
            font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; font-weight: 600; margin-left: 4px;
        }}
        .market-badge.kospi {{ background: #e6fffa; color: #319795; }}
        .market-badge.kosdaq {{ background: #fff5f5; color: #e53e3e; }}
        .type-badge {{ font-size: var(--font-xs); padding: 4px 10px; border-radius: 10px; font-weight: 600; white-space: nowrap; }}
        .col-date {{ color: var(--text-light); font-size: var(--font-sm); }}
        .col-link {{ text-align: center; font-size: var(--font-lg); white-space: nowrap; }}
        .link-btn {{
            text-decoration: none; display: inline-flex; align-items: center; justify-content: center;
            width: 32px; height: 32px; border-radius: 8px; background: rgba(255,154,158,0.08);
            transition: all 0.2s;
        }}
        .link-btn:hover {{ background: rgba(255,154,158,0.15); transform: scale(1.1); }}

        /* 업데이트 시간 */
        .update-time {{ text-align: center; color: var(--text-light); font-size: var(--font-xs); margin: var(--space-md) 0 var(--space-lg); font-weight: 400; }}

        /* 노티스 */
        .notice {{
            margin-top: var(--space-lg); padding: var(--space-md) var(--space-lg); background: rgba(255,243,205,0.5);
            border-radius: var(--card-radius); border-left: 4px solid #ffc107; font-size: var(--font-sm);
            color: #856404; line-height: 1.7; backdrop-filter: blur(10px);
        }}
        .notice strong {{ color: #744210; }}
        .notice code {{
            background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 4px;
            font-family: 'SF Mono', monospace; font-size: var(--font-xs);
        }}


            header h1 {{ font-size: var(--font-xl); }}
            .top3-grid {{ grid-template-columns: 1fr; }}
            .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .stock-table {{ font-size: var(--font-xs); }}
            .stock-table th, .stock-table td {{ padding: 10px 6px; }}
            .tab-link {{ padding: 8px 14px; font-size: var(--font-xs); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">🏛️</div>
            <h1>국민연금 대량보유주식</h1>
            <p>DART 공시 기반 — 국민연금공단 대량보유상황보고서 목록</p>
            <a href="index.html" class="version-link">← 급등주 알림으로 돌아가기</a>
        </header>

        <nav class="tab-nav">
            <a href="index.html" class="tab-link">📈 급등주</a>
            <a href="gurus.html" class="tab-link">🏆 투자고수</a>
            <a href="nps_holdings.html" class="tab-link active">🏛️ 국민연금</a>
        </nav>

        <div class="update-time">📅 업데이트: {now_kst} KST | 총 {total}개 종목 | 최근 60일</div>

        <div class="card table-card">
            <div class="section-title">📊 보고 현황 (최신 {top_n}개)</div>
            <table class="stock-table">
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

    <script>
    window.addEventListener('pageshow', function(e) {{
        if (e.persisted) {{ window.location.reload(); }}
    }});
    document.querySelectorAll('.tab-link').forEach(function(l) {{
        l.addEventListener('click', function() {{ this.blur(); }});
    }});
    </script>
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
