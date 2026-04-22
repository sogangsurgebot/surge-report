from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app, origins=["*"])

POSITIVE_WORDS = ['급등', '상승', '매수', '강세', '호재', '돌파', '대박', 'rally', '신고가', '터질', '폭발', '러시', '불기둥']
NEGATIVE_WORDS = ['하락', '폭락', '손절', '매도', '악재', '조정', '하락세', '물릴', '폭탄', '경고', '주의', '위험']

@app.route('/api/sentiment/<code>')
def sentiment(code):
    try:
        url = f"https://finance.naver.com/item/board.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        titles = []
        for link in soup.select('.title a')[:15]:
            text = link.get_text(strip=True)
            if text and text != '':
                titles.append(text)
        
        positive, negative, neutral = 0, 0, 0
        keywords = []
        
        for title in titles:
            p = sum(1 for w in POSITIVE_WORDS if w in title)
            n = sum(1 for w in NEGATIVE_WORDS if w in title)
            if p > n:
                positive += 1
                keywords.extend([w for w in POSITIVE_WORDS if w in title])
            elif n > p:
                negative += 1
                keywords.extend([w for w in NEGATIVE_WORDS if w in title])
            else:
                neutral += 1
        
        total = positive + negative + neutral or 1
        # 중복 제거 + 상위 3개 키워드
        seen = set()
        top_keywords = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                top_keywords.append(k)
                if len(top_keywords) >= 3:
                    break
        
        # 분위기 요약 1줄
        if positive / total >= 0.5:
            mood = '긍정적 🔥'
        elif negative / total >= 0.3:
            mood = '부정적 ⚠️'
        elif positive > negative:
            mood = '조심스럽게 긍정 🟢'
        elif negative > positive:
            mood = '신중한 관망 🔴'
        else:
            mood = '중립 ⚪'
        
        return jsonify({
            'code': code,
            'total': total,
            'positive': {'count': positive, 'ratio': round(positive/total*100)},
            'negative': {'count': negative, 'ratio': round(negative/total*100)},
            'neutral': {'count': neutral, 'ratio': round(neutral/total*100)},
            'keywords': top_keywords,
            'mood': mood,
            'titles': titles[:5]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
