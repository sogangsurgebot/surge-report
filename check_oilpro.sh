#!/bin/bash
# 오일전문가 YouTube 채널 주간 업데이트 확인 스크립트
# 매주 금요일 실행: 새 "주식 현황" 영상 확인 및 텔레그램 알림

BOT_TOKEN="8562807424:AAEF2vvvWA0hL8tvXpqayHtvJWs7OAFHRsk"
CHAT_ID="8713262502"
LOG_FILE="/tmp/oilpro-check.log"
STATE_FILE="/root/.openclaw/workspace/surge-report/.oilpro_last_video"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checking oilpro channel..." >> "$LOG_FILE"

# YouTube 채널 RSS 피드 가져오기
RSS_URL="https://www.youtube.com/feeds/videos.xml?channel_id=UCkK2KC4ltG_y5x8S1d4T8DQ"

# yt-dlp로 최근 영상 정보 가져오기
LATEST_VIDEO=$(yt-dlp --playlist-end 1 --print "%(title)s" "https://youtube.com/@oilprof" 2>/dev/null)
LATEST_URL=$(yt-dlp --playlist-end 1 --print "%(webpage_url)s" "https://youtube.com/@oilprof" 2>/dev/null)

if [ -z "$LATEST_VIDEO" ]; then
    echo "[$(date)] Failed to fetch video info" >> "$LOG_FILE"
    exit 1
fi

# 이전에 체크한 영상과 비교
if [ -f "$STATE_FILE" ]; then
    LAST_VIDEO=$(cat "$STATE_FILE")
else
    LAST_VIDEO=""
fi

# 새 영상이 있는지 확인 (주식 현황 관련 영상만)
if echo "$LATEST_VIDEO" | grep -q "주식 현황" && [ "$LATEST_VIDEO" != "$LAST_VIDEO" ]; then
    # 새 영상 발견! 텔레그램 알림 전송
    MESSAGE="🛢️ *오일전문가 주간 업데이트 알림*%0A%0A📅 새 영상이 업로드되었습니다!%0A%0A🎬 *$LATEST_VIDEO*%0A%0A▶️ [영상 보기]($LATEST_URL)%0A%0A📊 매주 금요일 정기 업데이트 확인됨."
    
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=${MESSAGE}" \
        -d "parse_mode=Markdown" \
        -d "disable_web_page_preview=false" >> "$LOG_FILE" 2>&1
    
    echo "[$(date)] New video found and notification sent: $LATEST_VIDEO" >> "$LOG_FILE"
    
    # 상태 파일 업데이트
    echo "$LATEST_VIDEO" > "$STATE_FILE"
else
    echo "[$(date)] No new stock status video found. Latest: $LATEST_VIDEO" >> "$LOG_FILE"
fi

echo "[$(date)] Check completed." >> "$LOG_FILE"
