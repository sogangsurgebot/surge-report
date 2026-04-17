#!/bin/bash
# 매일 아침 8시 실행: 급등주 데이터 수집 및 GitHub 커밋

cd /root/.openclaw/workspace/surge-report

echo "🚀 $(date): 급등주 데이터 업데이트 시작"

# 1. 데이터 수집 및 HTML 업데이트
python3 update_stocks.py

# 2. Git 변경사항 확인
if git diff --quiet; then
    echo "📭 변경사항 없음"
    exit 0
fi

# 3. Git 커밋 및 푸시
git add index.html
git commit -m "📈 $(date +%Y-%m-%d) 급등주 데이터 업데이트"
git push

echo "✅ $(date): 커밋 완료"
