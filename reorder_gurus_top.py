#!/usr/bin/env python3
"""
HTML 섹션 재배치 - 투자고수를 맨 위로
"""

from pathlib import Path

html_path = Path('/root/.openclaw/workspace/surge-report/index.html')
content = html_path.read_text(encoding='utf-8')

# 각 섹션의 시작/끝 위치
header_end = content.find('<!-- ===== 동적 콘텐츠: 국내 급등주')
domestic_start = content.find('<!-- ===== 동적 콘텐츠: 국내 급등주')
domestic_end = content.find('<!-- ===== 동적 콘텐츠: 해외 급등주')
nasdaq_end_marker = '<!-- DYNAMIC_NASDAQ_END -->'
nasdaq_end_pos = content.find(nasdaq_end_marker) + len(nasdaq_end_marker)
# DYNAMIC_NASDAQ_END 다음의 개행까지 포함
next_after_nasdaq = content.find('\n        <!--', nasdaq_end_pos)
if next_after_nasdaq == -1:
    next_after_nasdaq = content.find('\n    <!--', nasdaq_end_pos)
if next_after_nasdaq == -1:
    next_after_nasdaq = content.find('\n    <details', nasdaq_end_pos)
heatmap_start = next_after_nasdaq

heatmap_end = content.find('<details class="logic-details">')
logic_end = content.find('<div class="update-time-wrapper">')
update_end = content.find('<details class="collapse-section gurus-collapse"')
gurus_start = content.find('<details class="collapse-section gurus-collapse"')

# tail 시작: container 닫히는 div
container_close = content.find('    </div>\n    <!-- Swiper JS -->', gurus_start)
if container_close == -1:
    container_close = content.find('    </div>\n\n    <!-- Swiper JS -->', gurus_start)
if container_close == -1:
    container_close = content.find('    </div>', gurus_start)

# 섹션 추출
header = content[:header_end]
domestic = content[domestic_start:domestic_end]
nasdaq = content[domestic_end:heatmap_start]
heatmap = content[heatmap_start:heatmap_end]
logic = content[heatmap_end:logic_end]
update = content[logic_end:gurus_start]
gurus = content[gurus_start:container_close]
tail = content[container_close:]

print(f"Sections: header={len(header)}, gurus={len(gurus)}, domestic={len(domestic)}, nasdaq={len(nasdaq)}, heatmap={len(heatmap)}, logic={len(logic)}, update={len(update)}, tail={len(tail)}")

# 새로운 순서: header → gurus → domestic → nasdaq → heatmap → logic → update → tail
new_content = header + gurus + domestic + nasdaq + heatmap + logic + update + tail

html_path.write_text(new_content, encoding='utf-8')
print("✅ 투자고수 섹션을 맨 위로 이동 완료")
print("   순서: 헤더 → [접힘]투자고수 → 국내급등주 → 해외급등주 → 히트맵 → 판별로직 → 업데이트시간")
