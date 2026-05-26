#!/usr/bin/env python3
"""
Naver Finance News Scraper
급등주 종목별 최신 뉴스 수집 모듈

Usage:
    from news_scraper import fetch_stock_news
    
    news = fetch_stock_news("005930", limit=3)
    # Returns: [{"title": str, "press": str, "date": str, "url": str, "summary": str}]
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

BASE_URL = "https://finance.naver.com/item/news_news.nhn"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://finance.naver.com/",
}


def fetch_stock_news(stock_code: str, limit: int = 3) -> List[Dict[str, str]]:
    """
    네이버 금융에서 특정 종목의 최신 뉴스를 수집합니다.
    
    Args:
        stock_code: 6자리 종목코드 (예: "005930")
        limit: 수집할 뉴스 개수 (기본 3)
    
    Returns:
        뉴스 목록 [{title, press, date, url, summary}]
    """
    params = {
        "code": stock_code,
        "page": 1,
        "sm": "title_entity_id.basic",  # 제목 검색 모드
    }
    
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.encoding = resp.apparent_encoding  # EUC-KR → UTF-8 자동 감지
        resp.raise_for_status()
    except Exception as e:
        print(f"[NewsScraper] 요청 실패 {stock_code}: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # 네이버 금융 뉴스 테이블 구조 파싱
    # <tr> 안에 <td class="title">, <td class="info">, <td class="date">
    rows = soup.select("table.type5 tr")
    
    results = []
    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 3:
            continue
        
        # 제목 + 링크
        title_td = row.select_one("td.title")
        if not title_td:
            continue
        a_tag = title_td.select_one("a")
        if not a_tag:
            continue
        
        title = a_tag.get_text(strip=True)
        href = a_tag.get("href", "")
        url = urljoin("https://finance.naver.com", href)
        
        # 언론사
        info_td = row.select_one("td.info")
        press = info_td.get_text(strip=True) if info_td else ""
        
        # 날짜
        date_td = row.select_one("td.date")
        date_str = date_td.get_text(strip=True) if date_td else ""
        
        # 뉴스 본문 요약 (선택적 — URL 열면 파싱 가능)
        summary = ""  # 기본 비공. 추후 상세 본문 파싱 가능
        
        results.append({
            "title": title,
            "press": press,
            "date": date_str,
            "url": url,
            "summary": summary,
        })
        
        if len(results) >= limit:
            break
    
    return results


def fetch_news_summary(stock_code: str, stock_name: str, limit: int = 3) -> Optional[str]:
    """
    종목의 뉴스를 수집하고 1문장 요약(외부 LLM 또는 규칙 기반)을 반환.
    현재는 뉴스 제목들을 ; 로 연결한 문자열 반환. (LLM 요약 전 단계)
    """
    news_list = fetch_stock_news(stock_code, limit=limit)
    if not news_list:
        return None
    
    # 프롬프트용 텍스트 조합
    headlines = [f"[{n['press']}] {n['title']}" for n in news_list]
    return "\n".join(headlines)


# ─── 간단 테스트 ───
if __name__ == "__main__":
    # 삼성전자 테스트
    test_code = "005930"
    print(f"=== {test_code} 뉴스 수집 테스트 ===")
    news = fetch_stock_news(test_code, limit=3)
    for i, item in enumerate(news, 1):
        print(f"{i}. [{item['press']}] {item['title']}")
        print(f"   날짜: {item['date']} | URL: {item['url']}")
        print()
    
    # 요약 문자열 테스트
    summary_text = fetch_news_summary(test_code, "삼성전자")
    print("=== 요약용 텍스트 ===")
    print(summary_text)
