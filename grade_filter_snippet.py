def generate_grade_filter_html(market_type, active_grade='C'):
    """등급 필터 HTML 생성 (데이터 유무와 관계없이 항상 표시)"""
    result_id = f"{market_type}GradeResult"
    
    grade_buttons = [
        ('S', '29', '+29% ~', '상한가 근접', 's-grade'),
        ('A', '20', '+20% ~ 29%', '강한 급등', 'a-grade'),
        ('B', '10', '+10% ~ 20%', '중간 급등', 'b-grade'),
        ('C', '3', '+3% ~ 10%', '초기 급등', 'c-grade'),
        ('D', '0', '0% ~ 3%', '주목 단계', 'd-grade'),
        ('W', '-100', '전체', '모든 종목', 'watch-grade'),
    ]
    
    buttons_html = ''
    for grade, min_val, range_text, desc, css_class in grade_buttons:
        active = ' active' if grade == active_grade else ''
        buttons_html += f'''
            <button class="grade-btn {css_class}{active}" data-grade="{grade}" data-min="{min_val}">
                <span class="grade-label">{grade}</span>
                <span class="grade-range">{range_text}</span>
                <span class="grade-desc">{desc}</span>
            </button>'''
    
    return f'''<div class="grade-filter-section">
        <div class="grade-filter-header">
            <span class="grade-filter-title">📊 등락률 대역 필터</span>
            <span class="grade-filter-sub">클릭하여 해당 등급 종목 확인</span>
        </div>
        <div class="grade-filter-grid">{buttons_html}
        </div>
        <div class="grade-result" id="{result_id}"></div>
    </div>'''
