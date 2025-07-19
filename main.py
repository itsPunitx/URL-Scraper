from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

app = Flask(__name__)

def _format_ms(ms):
    """Convert milliseconds to formatted time string (HH:MM:SS.mmm)
    Example: 120350 → '00:02:00.350'
    """
    secs, milli = divmod(ms, 1000)
    mins, secs = divmod(secs, 60)
    hrs, mins = divmod(mins, 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{milli:03d}"

def scrape_gong_transcript(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    chrome_options.binary_location = "/usr/bin/chromium"
    
    driver = webdriver.Chrome(
        service=Service("/usr/bin/chromedriver"),
        options=chrome_options
    )
    
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 30)
        
        # Wait for transcript section to load
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "section.CallTranscript-moduleCLO4Fw[aria-label='Call transcript']")
            )
        )
        
        # Get page source while Selenium is still active
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
    finally:
        driver.quit()
    
    # Find transcript blocks
    blocks = soup.select("section.CallTranscript-moduleCLO4Fw div.monologue-wrapper")
    
    if not blocks:
        raise ValueError("Transcript blocks not found")
    
    transcript = []
    
    for blk in blocks:
        # Extract speaker name
        speaker_element = blk.select_one("span.only-speaker-visible")
        speaker = speaker_element.get_text(strip=True) if speaker_element else "Unknown"
        
        # Find all word elements in this monologue block
        words = blk.select("span.monologue-word")
        
        if not words:
            continue
        
        # Join all words to create the utterance text
        text = " ".join(w.get_text(strip=True) for w in words)
        
        # Get timing from first and last word
        try:
            start_ms = int(words[0].get("data-start", "0"))
            end_ms = int(words[-1].get("data-end", "0"))
        except (ValueError, AttributeError):
            # Fallback to block-level timing if word-level timing fails
            try:
                start_ms = int(blk.get("data-start", "0"))
                end_ms = int(blk.get("data-end", "0"))
            except (ValueError, AttributeError):
                start_ms = 0
                end_ms = 0
        
        # Only add non-empty utterances
        if text.strip():
            transcript.append({
                "speaker": speaker,
                "start": _format_ms(start_ms),
                "end": _format_ms(end_ms),
                "start_ms": start_ms,  # Include raw milliseconds for sorting/filtering
                "end_ms": end_ms,
                "utterance": text.strip()
            })
    
    return transcript

@app.route('/')
def index():
    return '''
    <h1>Gong Transcript API</h1>
    <p>Use GET /transcript?url=YOUR_GONG_URL to get transcript with speaker names and timestamps</p>
    <h2>Response Format:</h2>
    <pre>
{
  "success": true,
  "url": "...",
  "transcript": [
    {
      "speaker": "Alex Johnson",
      "start": "00:00:12.450",
      "end": "00:00:25.120",
      "start_ms": 12450,
      "end_ms": 25120,
      "utterance": "Hey everyone, thanks for joining the call today."
    }
  ],
  "total_lines": 54
}
    </pre>
    '''

@app.route('/transcript')
def get_transcript():
    gong_url = request.args.get('url')
    
    if not gong_url:
        return jsonify({
            'success': False,
            'error': 'Missing required parameter: url'
        }), 400
    
    if 'gong.io' not in gong_url:
        return jsonify({
            'success': False,
            'error': 'Invalid URL: Must contain "gong.io"'
        }), 400
    
    try:
        transcript_data = scrape_gong_transcript(gong_url)
        
        return jsonify({
            'success': True,
            'url': gong_url,
            'transcript': transcript_data,
            'total_lines': len(transcript_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'url': gong_url
        }), 500

@app.route('/transcript/filter')
def get_transcript_filtered():
    """Optional endpoint to filter transcript by speaker or time range"""
    gong_url = request.args.get('url')
    speaker_filter = request.args.get('speaker')
    start_time = request.args.get('start_ms', type=int)
    end_time = request.args.get('end_ms', type=int)
    
    if not gong_url:
        return jsonify({
            'success': False,
            'error': 'Missing required parameter: url'
        }), 400
    
    try:
        transcript_data = scrape_gong_transcript(gong_url)
        
        # Apply filters
        filtered_data = transcript_data
        
        if speaker_filter:
            filtered_data = [t for t in filtered_data if speaker_filter.lower() in t['speaker'].lower()]
        
        if start_time is not None:
            filtered_data = [t for t in filtered_data if t['start_ms'] >= start_time]
        
        if end_time is not None:
            filtered_data = [t for t in filtered_data if t['end_ms'] <= end_time]
        
        return jsonify({
            'success': True,
            'url': gong_url,
            'filters_applied': {
                'speaker': speaker_filter,
                'start_ms': start_time,
                'end_ms': end_time
            },
            'transcript': filtered_data,
            'total_lines': len(filtered_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'url': gong_url
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)