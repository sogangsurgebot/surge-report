#!/usr/bin/env python3
"""
오일전문가 네이버 블로그 모니터 및 홈페이지 자동 반영 프로그램
- 네이버 블로그 RSS 피드 확인
- 새 포스트 감지 시 sections/experts.html 자동 업데이트
- Git 커밋 & 푸시
- 텔레그램 알림 (변경 감지 시)

크론 예시 (매일 09:00, 13:00, 17:00):
  0 9,13,17 * * 1-5 cd /root/.openclaw/workspace/surge-report && python3 oilpro_blog_updater.py >> /var/log/oilpro-updater.log 2>&1
"""

import os
import re
import json
import subprocess
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from html import unescape

# 설정
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / ".oilpro_blog_state.json"
EXPERTS_HTML = BASE_DIR / "sections" / "experts.html"
INDEX_HTML = BASE_DIR / "index.html"

# 텔레그램 설정 (선택적)
BOT_TOKEN = os.getenv("OILPRO_BOT_TOKEN", "8562807424:AAEF2vvvWA0hL8tvXpqayHtvJWs7OAFHRsk")
CHAT_ID = os.getenv("OILPRO_CHAT_ID", "8713262502")

# 네이버 블로그 RSS
BLOG_RSS = "https://blog.rss.naver.com/oilpro1.xml"
BLOG_URL = "https://blog.naver.com/oilpro1"


def load_state():
    """이전 실행 상태 로드"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"last_post_guid": "", "last_post_title": "", "last_check": "", "update_count": 0}


def save_state(state):
    """상태 저장"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_rss():
    """RSS 피드 가져오기"""
    try:
        resp = requests.get(BLOG_RSS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"❌ RSS 가져오기 실패: {e}")
        return None


def parse_latest_post(rss_text):
    """RSS에서 최신 포스트 정보 파싱"""
    try:
        root = ET.fromstring(rss_text)
        # RSS 2.0 네임스페이스
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        
        # 첫 번째 item (최신 포스트)
        items = root.findall(".//item")
        if not items:
            return None
        
        latest = items[0]
        
        post = {
            "title": latest.findtext("title", "").strip(),
            "link": latest.findtext("link", "").strip(),
            "guid": latest.findtext("guid", "").strip(),
            "pubDate": latest.findtext("pubDate", "").strip(),
            "description": latest.findtext("description", "").strip(),
        }
        
        # HTML 태그 제거한 요약
        summary = re.sub(r'<[^>]+>', '', post["description"])
        post["summary"] = summary[:300] if summary else ""
        
        return post
    except Exception as e:
        print(f"❌ RSS 파싱 실패: {e}")
        return None


def extract_stock_mentions(text):
    """텍스트에서 종목명/코드 언급 추출 (간단한 휴리스틱)"""
    # 한국 주식 종목 패턴 (괄호 안 숫자 6자리)
    stock_patterns = re.findall(r'([가-힣A-Za-z\s]+?)\s*\(?\s*(\d{6})\s*\)?', text)
    
    # 중복 제거 및 정제
    stocks = []
    seen = set()
    for name, code in stock_patterns:
        clean_name = name.strip()
        if len(clean_name) >= 2 and code not in seen:
            seen.add(code)
            stocks.append({"name": clean_name, "code": code})
    
    return stocks[:5]  # 최대 5개만


def send_telegram_notification(post, is_new=True):
    """텔레그램 알림 전송"""
    if not BOT_TOKEN or not CHAT_ID:
        return
    
    try:
        if is_new:
            message = (
                f"🛢️ *오일전문가 블로그 새 포스트 알림*\n\n"
                f"📌 *{post['title']}*\n\n"
                f"📝 {post['summary'][:100]}...\n\n"
                f"🔗 [블로그 보기]({post['link']})\n\n"
                f"⏰ {post['pubDate'][:16]}\n\n"
                f"✅ 홈페이지에 자동 반영되었습니다!"
            )
        else:
            message = (
                f"🛢️ 오일전문가 블로그 업데이트 확인\n\n"
                f"📌 {post['title']}\n"
                f"⏰ {post['pubDate'][:16]}\n\n"
                f"변경사항 없음."
            )
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "false",
        }
        
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            print("✅ 텔레그램 알림 전송 완료")
        else:
            print(f"⚠️ 텔레그램 전송 실패: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 오류: {e}")


def update_html_file(file_path, post, stocks, label=""):
    """
    단일 HTML 파일의 OILPRO_BLOG_INSIGHT 마커 교체
    """
    if not file_path.exists():
        print(f"❌ 파일 없음: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    start_marker = "<!-- OILPRO_BLOG_INSIGHT_START -->"
    end_marker = "<!-- OILPRO_BLOG_INSIGHT_END -->"
    
    if start_marker not in content:
        print(f"⚠️ 마커 없음 ({label}): {file_path}")
        return False
    
    # 종목 태그 생성
    stock_tags = ""
    for s in stocks:
        stock_tags += f'<span style="display:inline-block;padding:4px 10px;background:rgba(255,107,107,0.15);border-radius:20px;font-size:12px;color:#ff6b6b;margin:2px;">{s["name"]} ({s["code"]})</span>'
    
    new_insight = f'''
        <div class="card" style="margin-top:1rem;background:linear-gradient(135deg, rgba(255,154,158,0.1) 0%, rgba(250,208,196,0.1) 100%);border:1px solid rgba(255,154,158,0.3);">
            <div style="padding:1rem;">
                <div style="font-size:0.85rem;color:#ff6b6b;font-weight:700;margin-bottom:0.5rem;">📰 최신 블로그 인사이트</div>
                <div style="font-size:1rem;font-weight:600;color:#2d3748;margin-bottom:0.5rem;">{post["title"]}</div>
                <div style="font-size:0.8rem;color:#666;margin-bottom:0.8rem;line-height:1.5;">{post["summary"][:200]}{"..." if len(post["summary"]) > 200 else ""}</div>
                {f'<div style="margin-bottom:0.5rem;">{stock_tags}</div>' if stock_tags else ''}
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.75rem;color:#999;">🕐 {post["pubDate"][:16]}</span>
                    <a href="{post["link"]}" target="_blank" style="font-size:0.8rem;color:#ff6b6b;text-decoration:none;font-weight:600;">📎 블로그에서 읽기 →</a>
                </div>
            </div>
        </div>
'''
    
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    if start_idx == -1 or end_idx == -1:
        print(f"⚠️ 마커 위치 오류 ({label})")
        return False
    
    start_pos = start_idx + len(start_marker)
    new_content = content[:start_pos] + '\n' + new_insight + '\n' + content[end_idx:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ {label} 업데이트 완료")
    return True


def update_experts_html(post, stocks):
    """experts.html 업데이트"""
    return update_html_file(EXPERTS_HTML, post, stocks, "experts.html")


def update_index_html(post, stocks):
    """index.html 업데이트"""
    return update_html_file(INDEX_HTML, post, stocks, "index.html")


def run_daily_update_script():
    """daily_update.sh 실행하여 index.html 재생성"""
    script = BASE_DIR / "daily_update.sh"
    if not script.exists():
        print("⚠️ daily_update.sh 없음")
        return False
    
    try:
        result = subprocess.run(
            [str(script)],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        print(f"✅ daily_update.sh 실행 완료 (exit: {result.returncode})")
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️ daily_update.sh 실행 실패: {e}")
        return False


def git_commit_and_push():
    """Git 커밋 및 푸시"""
    try:
        # git add
        subprocess.run(["git", "add", "sections/experts.html", "index.html", STATE_FILE.name],
                      cwd=BASE_DIR, capture_output=True, timeout=10)
        
        # 변경사항 확인
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"],
                             cwd=BASE_DIR, capture_output=True)
        if diff.returncode == 0:
            print("📭 변경사항 없음 (커밋 생략)")
            return True
        
        # 커밋
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"auto: 오일전문가 블로그 인사이트 업데이트 ({now})"
        
        subprocess.run(["git", "commit", "-m", commit_msg],
                      cwd=BASE_DIR, capture_output=True, timeout=10)
        
        # 푸시
        push = subprocess.run(["git", "push", "origin", "main"],
                             cwd=BASE_DIR, capture_output=True, timeout=30)
        if push.returncode == 0:
            print("✅ Git 푸시 완료")
            return True
        else:
            print(f"⚠️ Git 푸시 실패: {push.stderr.decode()[:200]}")
            return False
    except Exception as e:
        print(f"⚠️ Git 작업 실패: {e}")
        return False


def main():
    print(f"🚀 오일전문가 블로그 모니터 시작: {datetime.now()}")
    print(f"   RSS: {BLOG_RSS}")
    print()
    
    # 1. 상태 로드
    state = load_state()
    print(f"📂 마지막 확인: {state.get('last_check', '없음')}")
    print(f"📂 마지막 포스트: {state.get('last_post_title', '없음')[:40]}...")
    
    # 2. RSS 가져오기
    rss_text = fetch_rss()
    if not rss_text:
        print("❌ 종료: RSS를 가져올 수 없음")
        return
    
    # 3. 최신 포스트 파싱
    post = parse_latest_post(rss_text)
    if not post:
        print("❌ 종료: 포스트 파싱 실패")
        return
    
    print(f"\n📰 최신 포스트:")
    print(f"   제목: {post['title'][:50]}")
    print(f"   날짜: {post['pubDate'][:16]}")
    print(f"   링크: {post['link'][:60]}...")
    
    # 4. 새 포스트 여부 확인
    current_guid = post.get("guid", "") or post.get("link", "")
    is_new_post = (current_guid != state.get("last_post_guid", ""))
    
    if not is_new_post:
        print(f"\n📭 새 포스트 없음 (이전과 동일)")
        state["last_check"] = datetime.now().isoformat()
        save_state(state)
        send_telegram_notification(post, is_new=False)
        return
    
    print(f"\n🆕 새 포스트 감지! 업데이트 진행...")
    
    # 5. 종목 언급 추출
    stocks = extract_stock_mentions(post["summary"] + " " + post["title"])
    if stocks:
        print(f"   📊 감지된 종목: {', '.join(s['name'] for s in stocks)}")
    
    # 6. experts.html + index.html 동시 업데이트
    experts_ok = update_experts_html(post, stocks)
    index_ok = update_index_html(post, stocks)
    
    if experts_ok or index_ok:
        # 7. Git 커밋 & 푸시
        print("\n📤 Git 커밋 & 푸시...")
        git_commit_and_push()
        
        # 8. 텔레그램 알림
        send_telegram_notification(post, is_new=True)
        
        # 9. 상태 저장
        state["last_post_guid"] = current_guid
        state["last_post_title"] = post["title"]
        state["last_check"] = datetime.now().isoformat()
        state["update_count"] = state.get("update_count", 0) + 1
        save_state(state)
        
        print(f"\n✨ 완료! 총 업데이트 횟수: {state['update_count']}")
    else:
        print("❌ HTML 업데이트 실패")


if __name__ == "__main__":
    main()
