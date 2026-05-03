#!/usr/bin/env python3
"""
급등주 텔레그램 알람 모듈
- S등급(+29% 이상) / A등급(+20% ~ 29%) 종목 감지 시 텔레그램 알람 발송
- 중복 알람 방지 (날짜별 종목 코드 기록, 하루 한 종목 한 번)
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# .env 파일에서 환경변수 로드
def _load_env():
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

_load_env()

# 텔레그램 봇 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8562807424:AAEF2vvvWA0hL8tvXpqayHtvJWs7OAFHRsk")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if cid.strip()]

# 알람 기록 파일
ALERT_HISTORY_FILE = Path(__file__).parent / "telegram_alert_history.json"

# 등급 기준
S_GRADE_THRESHOLD = 29.0
A_GRADE_THRESHOLD = 20.0


def get_kst_now():
    """한국 시간(KST) 현재 시간 반환"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst)


def load_alert_history():
    """알람 기록 로드"""
    if ALERT_HISTORY_FILE.exists():
        try:
            with open(ALERT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_alert_history(history):
    """알람 기록 저장"""
    with open(ALERT_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_today_alerted_codes():
    """오늘 이미 알람 발송한 종목 코드 목록"""
    history = load_alert_history()
    today = get_kst_now().strftime("%Y-%m-%d")
    return set(history.get(today, []))


def record_alert(stock_code):
    """알람 발송 기록"""
    history = load_alert_history()
    today = get_kst_now().strftime("%Y-%m-%d")
    if today not in history:
        history[today] = []
    if stock_code not in history[today]:
        history[today].append(stock_code)
    save_alert_history(history)


def send_telegram_message(message: str) -> bool:
    """텔레그램 메시지 발송 (다중 챗 ID 지원)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("⚠️ 텔레그램 설정 없음 (TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정)")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    all_success = True
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("ok"):
                    print(f"✅ 텔레그램 알람 발송 성공 (→ {chat_id})")
                else:
                    print(f"⚠️ 텔레그램 API 오류 ({chat_id}): {result}")
                    all_success = False
            else:
                print(f"❌ 텔레그램 발송 실패 ({chat_id}): HTTP {resp.status_code}")
                all_success = False
        except requests.Timeout:
            print(f"❌ 텔레그램 발송 타임아웃 ({chat_id})")
            all_success = False
        except Exception as e:
            print(f"❌ 텔레그램 발송 오류 ({chat_id}): {e}")
            all_success = False

    return all_success


def extract_change_rate(stock: dict) -> float:
    """종목 딕셔너리에서 등락률 추출"""
    change_str = stock.get("change", "0%")
    try:
        return float(change_str.replace("%", "").replace("+", ""))
    except (ValueError, TypeError):
        return 0.0


def classify_grade(rate: float) -> str:
    """등락률로 등급 분류"""
    if rate >= S_GRADE_THRESHOLD:
        return "S"
    elif rate >= A_GRADE_THRESHOLD:
        return "A"
    return None


def get_alert_stocks(stocks: list) -> list:
    """S/A등급(+20% 이상) 종목 필터링"""
    alert_stocks = []
    for stock in stocks:
        rate = extract_change_rate(stock)
        grade = classify_grade(rate)
        if grade:
            alert_stocks.append({
                **stock,
                "change_rate": rate,
                "alert_grade": grade
            })
    return alert_stocks


def build_alert_message(stocks: list, market_name: str) -> str:
    """알람 메시지 HTML 생성 (등급별 구분)"""
    now = get_kst_now().strftime("%Y-%m-%d %H:%M")

    # 등급별 그룹화
    s_stocks = [s for s in stocks if s.get("alert_grade") == "S"]
    a_stocks = [s for s in stocks if s.get("alert_grade") == "A"]

    messages = []

    # S등급 메시지
    if s_stocks:
        if len(s_stocks) == 1:
            stock = s_stocks[0]
            name = stock.get("name", "Unknown")
            code = stock.get("code", "")
            change = stock.get("change", "0%")
            price = stock.get("price", "N/A")
            volume = stock.get("volume", "N/A")
            reason = stock.get("reason", "")
            industry = stock.get("industry", "")

            msg = f"""🚨 <b>S등급 급등주 발견!</b>

🔥 <b>{name}</b> ({code})
📈 등락률: <b>{change}</b>
💰 현재가: {price}
📊 거래량: {volume}
🏢 시장: {market_name}
{'' if not industry else f'🏭 업종: {industry}'}
{'' if not reason else f'📝 {reason}'}

⏰ 알람 시간: {now}
📎 <a href=\"https://finance.naver.com/item/main.nhn?code={code}\">네이버 금융 바로가기</a>"""
            messages.append(msg)
        else:
            msg = f"""🚨 <b>S등급 급등주 {len(s_stocks)}개 발견!</b>

"""
            for i, stock in enumerate(s_stocks, 1):
                name = stock.get("name", "Unknown")
                code = stock.get("code", "")
                change = stock.get("change", "0%")
                price = stock.get("price", "N/A")
                msg += f"""{i}. 🔥 <b>{name}</b> ({code})
   📈 {change} | 💰 {price} | 🏢 {market_name}
   📎 <a href=\"https://finance.naver.com/item/main.nhn?code={code}\">네이버 금융</a>

"""
            msg += f"⏰ 알람 시간: {now}"
            messages.append(msg)

    # A등급 메시지
    if a_stocks:
        if len(a_stocks) == 1:
            stock = a_stocks[0]
            name = stock.get("name", "Unknown")
            code = stock.get("code", "")
            change = stock.get("change", "0%")
            price = stock.get("price", "N/A")
            volume = stock.get("volume", "N/A")
            reason = stock.get("reason", "")
            industry = stock.get("industry", "")

            msg = f"""⚠️ <b>A등급 급등주 발견!</b>

📈 <b>{name}</b> ({code})
📊 등락률: <b>{change}</b>
💰 현재가: {price}
📊 거래량: {volume}
🏢 시장: {market_name}
{'' if not industry else f'🏭 업종: {industry}'}
{'' if not reason else f'📝 {reason}'}

⏰ 알람 시간: {now}
📎 <a href=\"https://finance.naver.com/item/main.nhn?code={code}\">네이버 금융 바로가기</a>"""
            messages.append(msg)
        else:
            msg = f"""⚠️ <b>A등급 급등주 {len(a_stocks)}개 발견!</b>

"""
            for i, stock in enumerate(a_stocks, 1):
                name = stock.get("name", "Unknown")
                code = stock.get("code", "")
                change = stock.get("change", "0%")
                price = stock.get("price", "N/A")
                msg += f"""{i}. 📈 <b>{name}</b> ({code})
   📊 {change} | 💰 {price} | 🏢 {market_name}
   📎 <a href=\"https://finance.naver.com/item/main.nhn?code={code}\">네이버 금융</a>

"""
            msg += f"⏰ 알람 시간: {now}"
            messages.append(msg)

    return "\n\n━━━━━━━━━━━━━━\n\n".join(messages) if len(messages) > 1 else messages[0] if messages else ""


def check_and_alert_s_grade(kospi_stocks: list, kosdaq_stocks: list) -> dict:
    """
    S/A등급 종목 체크 및 텔레그램 알람 발송
    - 중복 알람 방지 (날짜별 종목 코드 기록)
    - S등급과 A등급은 별도 메시지로 발송
    - 반환: {"sent": bool, "stocks": list, "message": str}
    """
    # S/A등급 종목 추출
    s_kospi = get_alert_stocks(kospi_stocks)
    s_kosdaq = get_alert_stocks(kosdaq_stocks)

    all_alert = []
    for s in s_kospi:
        s["market_display"] = "KOSPI"
        all_alert.append(s)
    for s in s_kosdaq:
        s["market_display"] = "KOSDAQ"
        all_alert.append(s)

    if not all_alert:
        return {"sent": False, "stocks": [], "message": "S/A등급 종목 없음"}

    # 오늘 이미 알람 보낸 종목 필터링
    alerted_codes = get_today_alerted_codes()
    new_stocks = [s for s in all_alert if s.get("code") not in alerted_codes]

    if not new_stocks:
        print(f"📵 오늘 이미 알람 발송한 종목 ({len(all_alert)}개) - 중복 방지")
        return {"sent": False, "stocks": all_alert, "message": "이미 알람 발송 완료"}

    # 등급별 카운트
    s_count = len([s for s in new_stocks if s.get("alert_grade") == "S"])
    a_count = len([s for s in new_stocks if s.get("alert_grade") == "A"])

    # 시장별 그룹화
    kospi_new = [s for s in new_stocks if s["market_display"] == "KOSPI"]
    kosdaq_new = [s for s in new_stocks if s["market_display"] == "KOSDAQ"]

    sent_any = False

    # KOSPI 알람 (S+A 통합 메시지, 등급별 구분 표시)
    if kospi_new:
        msg = build_alert_message(kospi_new, "KOSPI")
        if msg and send_telegram_message(msg):
            sent_any = True
            for s in kospi_new:
                record_alert(s.get("code", ""))

    # KOSDAQ 알람 (S+A 통합 메시지, 등급별 구분 표시)
    if kosdaq_new:
        msg = build_alert_message(kosdaq_new, "KOSDAQ")
        if msg and send_telegram_message(msg):
            sent_any = True
            for s in kosdaq_new:
                record_alert(s.get("code", ""))

    return {
        "sent": sent_any,
        "stocks": new_stocks,
        "message": f"S등급 {s_count}개, A등급 {a_count}개 알람 발송" if sent_any else "알람 발송 실패"
    }


def test_alert():
    """테스트: 가상의 S/A등급 종목으로 알람 테스트"""
    test_stocks = [
        {
            "name": "S테스트",
            "code": "000001",
            "change": "+30.00%",
            "price": "100,000",
            "volume": "1,000,000",
            "reason": "급등 STRONG (점수: 9.5)",
            "industry": "반도체"
        },
        {
            "name": "A테스트",
            "code": "000002",
            "change": "+25.00%",
            "price": "50,000",
            "volume": "500,000",
            "reason": "급등 NORMAL (점수: 7.5)",
            "industry": "바이오"
        }
    ]

    print("🔔 S/A등급 알람 테스트 시작...")
    result = check_and_alert_s_grade(test_stocks, [])
    print(f"결과: {result}")


if __name__ == "__main__":
    test_alert()
