#!/usr/bin/env python3
"""
국민연금공단 대량보유주식 보고내역 수집 (공공데이터포털 API)
data.go.kr 데이터 ID: 15106890

[필요 사항]
1. data.go.kr 회원 가입
2. "국민연금공단 대량보유주식 보고내역" 오픈API 활용신청
3. 마이페이지 > 오픈API > 인증키 확인 후 .env 에 DATA_GO_KR_KEY=키 추가
4. API 상세 기능 정보의 엔드포인트를 NPS_API_ENDPOINT 에 설정

[참고] 더 넓은 보유 현황을 원하면 data.go.kr 3070507 "국민연금공단 국내주식 투자정보"
(연도말 기준 전체 국내주식 종목별 평가액/지분율/비중) 을 추천.
"""

import os
import sys
import json
import requests
import urllib.parse
from datetime import datetime, timezone
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

DATA_GO_KR_KEY = os.getenv("DATA_GO_KR_KEY", "")
# 실제 엔드포인트는 data.go.kr 활용신청 후 확인 (예시)
NPS_API_ENDPOINT = os.getenv(
    "NPS_API_ENDPOINT",
    "http://apis.data.go.kr/1352000/service/NpsMassHoldStkRpt/getNpsMassHoldStkRptList"
)

BASE_DIR = Path(__file__).parent
NPS_JSON_PATH = BASE_DIR / "nps_holdings.json"
NPS_HTML_PATH = BASE_DIR / "nps_holdings.html"
TEMPLATE_HTML_PATH = BASE_DIR / "template.html"


def fetch_nps_holdings() -> Optional[List[Dict]]:
    """
    공공데이터포털 API 호출 → 대량보유주식 목록 반환
    응답 구조는 공공데이터포털 일반 형태로 가정:
    {
      "response": {
        "header": { "resultCode": "00", "resultMsg": "NORMAL SERVICE." },
        "body": {
          "items": { "item": [ { ... }, ... ] },
          "totalCount": N
        }
      }
    }
    """
    if not DATA_GO_KR_KEY:
        print("❌ DATA_GO_KR_KEY 미설정 — .env 에 공공데이터포털 인증키를 추가하세요")
        return None

    # 공공데이터포털은 URL-encoded serviceKey 가 필요한 경우가 많음
    service_key = urllib.parse.unquote(DATA_GO_KR_KEY)

    # 페이지 단위로 전체 데이터 수집 (최대 1000건 가정)
    all_items: List[Dict] = []
    page_no = 1
    num_of_rows = 100

    while True:
        params = {
            "serviceKey": service_key,
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            # 일부 API는 _type=json 또는 type=json 파라미터 필요
            "_type": "json",
        }

        try:
            resp = requests.get(NPS_API_ENDPOINT, params=params, timeout=20)
            print(f"   → API 요청: page={page_no}, status={resp.status_code}")
        except requests.RequestException as e:
            print(f"❌ API 요청 실패: {e}")
            return None

        if resp.status_code != 200:
            print(f"❌ API 오류: HTTP {resp.status_code} — {resp.text[:200]}")
            return None

        # 공공데이터포털 응답 파싱 (JSON 가정)
        try:
            data = resp.json()
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 XML일 수 있음 — 일단 None 반환
            print("⚠️ JSON 파싱 실패 — 응답이 XML일 수 있습니다. 응답 일부:")
            print(resp.text[:500])
            return None

        # 공공데이터포털 표준 응답 구조 탐색
        body = data.get("response", {}).get("body", {})
        items_wrap = body.get("items", {})
        items = items_wrap.get("item", []) if isinstance(items_wrap, dict) else []
        total_count = body.get("totalCount", 0)

        if not items:
            break

        all_items.extend(items)
        print(f"   ✅ page {page_no}: {len(items)}건 수집 (누적 {len(all_items)} / {total_count})")

        if len(all_items) >= total_count:
            break
        page_no += 1

        # 안전장치
        if page_no > 20:
            print("⚠️ 페이지 상한 도달")
            break

    return all_items


def parse_nps_items(items: List[Dict]) -> List[Dict]:
    """
    API 원본 → 표준화된 딕셔너리 리스트
    필드명은 실제 API 응답에 따라 조정 필요.
    공공데이터포털 컬럼정의서 기반 가정 필드:
      - 종목명, 종목코드, 발행기관, 보고서작성기준일, 지분율, 보고사유, 보고일
    """
    parsed = []
    for raw in items:
        # 필드명 매핑 (실제 응답에 맞게 수정 필요)
        # 아래는 컬럼정의서상 이름을 기반으로 한 추정
        record = {
            "stock_name": _str(raw, "종목명", "stockName", "corp_name", "item_nm"),
            "stock_code": _str(raw, "종목코드", "stockCode", "item_cd", "stock_cd"),
            "corp_name": _str(raw, "발행기관", "발행기관명", "corpName", "issu_cmpy_nm"),
            "base_date": _str(raw, "보고서작성기준일", "보고서 작성기준일", "baseDate", "rpt_dt"),
            "holding_ratio": _float(raw, "지분율", "지분율퍼센트", "holdRate", "hold_per"),
            "report_reason": _str(raw, "보고사유", "reportReason", "report_reason", "rpt_rsn"),
            "report_date": _str(raw, "보고일", "reportDate", "report_date", "rcept_dt"),
            "market": _infer_market(raw),
        }
        parsed.append(record)

    # 지분율 높은 순 정렬
    parsed.sort(key=lambda x: x["holding_ratio"], reverse=True)
    return parsed


def _str(raw: Dict, *candidates) -> str:
    for key in candidates:
        if key in raw and raw[key] is not None:
            return str(raw[key]).strip()
    return ""


def _float(raw: Dict, *candidates) -> float:
    for key in candidates:
        if key in raw and raw[key] is not None:
            try:
                val = str(raw[key]).replace("%", "").replace(",", "").strip()
                return float(val)
            except (ValueError, TypeError):
                pass
    return 0.0


def _infer_market(raw: Dict) -> str:
    """시장 구분 추론 — 종목코드 6자리 기준"""
    code = _str(raw, "종목코드", "stockCode", "item_cd", "stock_cd")
    if len(code) == 6:
        # KOSDAQ: 코드가 0으로 시작하는 경우가 많음 (정확하지 않음, 참고용)
        if code.startswith("0") and code[1] != "0":
            return "KOSDAQ"
    return "KOSPI"


def generate_nps_html(records: List[Dict]) -> str:
    """nps_holdings.html 생성"""
    now_kst = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    # 상위 20개만 테이블로, 전체는 JSON으로
    top_n = 20
    top_records = records[:top_n]

    rows_html = ""
    for i, r in enumerate(top_records, 1):
        ratio = r["holding_ratio"]
        ratio_bar = min(ratio / 10 * 100, 100)  # 10% 기준 max width
        ratio_color = "#ff4757" if ratio >= 10 else "#e67e22" if ratio >= 7 else "#3498db"

        naver_link = f"https://finance.naver.com/item/main.nhn?code={r['stock_code']}" if r["stock_code"] else "#"

        rows_html += f'''<tr>
            <td class="col-rank">{i}</td>
            <td class="col-name">
                <div class="stock-name">{r["stock_name"]}</div>
                <div class="stock-code">{r["stock_code"]} <span class="market-badge {r["market"].lower()}">{r["market"]}</span></div>
            </td>
            <td class="col-corp">{r["corp_name"]}</td>
            <td class="col-ratio">
                <div class="ratio-bar-wrap">
                    <div class="ratio-bar" style="width:{ratio_bar}%;background:{ratio_color}"></div>
                    <span class="ratio-text">{ratio:.2f}%</span>
                </div>
            </td>
            <td class="col-date">{r["base_date"]}<br><small>{r["report_reason"]}</small></td>
            <td class="col-link">
                <a href="{naver_link}" target="_blank" rel="noopener noreferrer">📈</a>
            </td>
        </tr>\n'''

    # 전체 건수 요약
    total = len(records)
    kospi_count = sum(1 for r in records if r["market"] == "KOSPI")
    kosdaq_count = sum(1 for r in records if r["market"] == "KOSDAQ")

    # 상위 3개 종목 카드
    top3_cards = ""
    for r in records[:3]:
        top3_cards += f'''<div class="nps-top-card">
            <div class="top-rank">🥇</div>
            <div class="top-name">{r["stock_name"]}</div>
            <div class="top-code">{r["stock_code"]}</div>
            <div class="top-ratio">{r["holding_ratio"]:.2f}%</div>
            <div class="top-corp">{r["corp_name"]}</div>
        </div>'''

    # 기존 템플릿의 스타일을 재사용하면서 NPS 전용 스타일 추가
    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>국민연금 대량보유주식 | Surge Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        /* ── 기본 ─────────────────────────────── */
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

        /* ── 헤더 ─────────────────────────────── */
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

        /* ── 요약 카드 ────────────────────────── */
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

        /* ── TOP3 ─────────────────────────────── */
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
        .top-ratio {{ font-size: 1.3rem; font-weight: 700; color: #ff4757; margin: 8px 0; }}
        .top-corp {{ font-size: 0.8rem; color: #718096; }}

        /* ── 테이블 ────────────────────────────── */
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
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
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
        .col-corp {{ color: #718096; font-size: 0.85rem; }}
        .col-ratio {{ min-width: 120px; }}
        .ratio-bar-wrap {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .ratio-bar {{
            height: 6px;
            border-radius: 3px;
            min-width: 4px;
            transition: width 0.6s ease;
        }}
        .ratio-text {{ font-weight: 600; color: #2d3748; font-size: 0.9rem; white-space: nowrap; }}
        .col-date {{ color: #718096; font-size: 0.8rem; line-height: 1.4; }}
        .col-link {{ text-align: center; font-size: 1.1rem; }}
        .col-link a {{ text-decoration: none; }}

        /* ── 안내 문구 ────────────────────────── */
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

        @media (max-width: 640px) {{
            .top3-grid {{ grid-template-columns: 1fr; }}
            th, td {{ font-size: 0.8rem; padding: 8px 4px; }}
            .col-corp {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <a href="index.html" class="back-link">← 급등주 알림으로 돌아가기</a>
            <h1>🏛️ 국민연금 대량보유주식</h1>
            <p>지분율 5% 이상 보유 및 변동 보고 내역 (공공데이터포털 기반)</p>
        </header>

        <div class="update-time">📅 업데이트: {now_kst} KST | 총 {total}개 종목</div>

        <!-- 요약 카드 -->
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
                <div class="summary-number">{records[0]["holding_ratio"]:.1f}%</div>
                <div class="summary-label">최고 지분율</div>
            </div>
        </div>

        <!-- TOP3 -->
        <div class="top3-grid">
            {top3_cards}
        </div>

        <!-- 테이블 -->
        <div class="table-card">
            <div class="table-title">📊 보유 현황 상위 {top_n}개</div>
            <table>
                <thead>
                    <tr>
                        <th class="col-rank">#</th>
                        <th>종목</th>
                        <th class="col-corp">발행기관</th>
                        <th>지분율</th>
                        <th>기준일 / 사유</th>
                        <th>차트</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>

        <div class="notice">
            <strong>ℹ️ 데이터 안내</strong><br>
            • 본 데이터는 국민연금공단이 DART에 제출한 <strong>대량보유상황보고서</strong>(지분율 5% 이상 또는 1% 이상 변동) 내역입니다.<br>
            • 지분율 5% 미만 종목은 포함되지 않으며, 전체 보유 현황과는 다를 수 있습니다.<br>
            • 더 넓은 범위의 국내주식 투자 현황을 원하시면 data.go.kr "국민연금공단 국내주식 투자정보"(ID: 3070507)를 참고하세요.
        </div>
    </div>
</body>
</html>'''

    return html


def main():
    print("🏛️ 국민연금 대량보유주식 데이터 수집 시작")

    items = fetch_nps_holdings()
    if items is None:
        print("⚠️ API 미설정 또는 오류 — nps_holdings.json 기존 데이터 사용 시도")
        if NPS_JSON_PATH.exists():
            with open(NPS_JSON_PATH, 'r', encoding='utf-8') as f:
                records = json.load(f)
            print(f"   → 기존 데이터 {len(records)}건 로드")
        else:
            print("❌ 기존 데이터도 없음 — 종료")
            sys.exit(1)
    else:
        records = parse_nps_items(items)
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
