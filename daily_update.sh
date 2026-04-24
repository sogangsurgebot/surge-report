#!/bin/bash
# 30분 간격 실행: 급등주 데이터 수집 및 GitHub 커밋

cd /root/.openclaw/workspace/surge-report

# 환경변수 로드 (API 키)
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | xargs)
fi

echo "🚀 $(TZ=Asia/Seoul date): 급등주 데이터 업데이트 시작"

# 1. 데이터 수집 및 HTML 업데이트 (섹션 조합 방식)
python3 update_stocks.py

# 데이터 수집 실패 체크 (종목 0개면 종료)
if [ -f market_data.json ]; then
    STOCK_COUNT=$(python3 -c "import json; d=json.load(open('market_data.json')); print(len(d.get('kospi_stocks',[]))+len(d.get('kosdaq_stocks',[])))" 2>/dev/null || echo "0")
    if [ "$STOCK_COUNT" = "0" ]; then
        echo "❌ 데이터 수집 실패 (0개 종목) - Git 푸시 중단"
        exit 1
    fi
fi

# 2. Git 변경사항 확인
if git diff --quiet; then
    echo "📭 변경사항 없음"
    exit 0
fi

# 3. Git 커밋 및 푸시
git add index.html template.html
git commit -m "📈 $(date '+%Y-%m-%d %H:%M') 급등주 데이터 업데이트"
git push

echo "✅ $(date): 커밋 완료"
