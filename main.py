from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import os

app = Flask(__name__)

def setup_driver():
    """Setup Chrome driver with appropriate options for Render deployment"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_gong_transcript(url):
    """
    Scrape transcript from Gong.io with speaker names and messages only
    """
    driver = None
    try:
        driver = setup_driver()
        driver.get(url)
        
        # Wait for transcript section to load
        wait = WebDriverWait(driver, 30)
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "section.CallTranscript-moduleCLO4Fw[aria-label='Call transcript']"))
        )
        
        # Parse the page source
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Find transcript blocks
        blocks = soup.select("section.CallTranscript-moduleCLO4Fw div.monologue-wrapper")
        if not blocks:
            raise ValueError("Transcript blocks not found")
        
        transcript = []
        for blk in blocks:
            # Extract speaker name
            speaker_element = blk.select_one("span.only-speaker-visible")
            speaker = speaker_element.get_text(strip=True) if speaker_element else "Unknown"
            
            # Extract words/text from the block
            words = blk.select("span.monologue-word")
            if not words:
                continue
            
            # Combine all words into the transcript message
            message = " ".join(word.get_text(strip=True) for word in words)
            
            if message.strip():  # Only add non-empty messages
                transcript.append({
                    "speaker": speaker,
                    "message": message
                })
        
        return transcript
        
    except TimeoutException:
        raise Exception("Timeout waiting for transcript to load")
    except WebDriverException as e:
        raise Exception(f"WebDriver error: {str(e)}")
    except Exception as e:
        raise Exception(f"Error scraping transcript: {str(e)}")
    finally:
        if driver:
            driver.quit()

@app.route('/')
def home():
    return '''
    <h1>Gong Transcript Scraper</h1>
    <p>Usage: GET /transcript?url=YOUR_GONG_URL</p>
    <h3>Response Format:</h3>
    <pre>
    {
      "success": true,
      "url": "...",
      "transcript": [
        {
          "speaker": "Alex Johnson",
          "message": "Hey everyone, thanks for joining the call today."
        },
        {
          "speaker": "Sarah Chen", 
          "message": "Thanks Alex. I wanted to discuss our Q4 strategy..."
        }
      ],
      "total_lines": 54
    }
    </pre>
    '''

@app.route('/transcript')
def get_transcript():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'gong.io' not in url:
        return jsonify({"error": "Only Gong.io URLs are supported"}), 400
    
    try:
        transcript_data = scrape_gong_transcript(url)
        return jsonify({
            "success": True,
            "url": url,
            "transcript": transcript_data,
            "total_lines": len(transcript_data)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/transcript/filter')
def get_filtered_transcript():
    url = request.args.get('url')
    speaker_filter = request.args.get('speaker')
    
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'gong.io' not in url:
        return jsonify({"error": "Only Gong.io URLs are supported"}), 400
    
    try:
        transcript_data = scrape_gong_transcript(url)
        
        # Filter by speaker if specified
        if speaker_filter:
            transcript_data = [
                item for item in transcript_data 
                if speaker_filter.lower() in item["speaker"].lower()
            ]
        
        return jsonify({
            "success": True,
            "url": url,
            "filters": {"speaker": speaker_filter} if speaker_filter else {},
            "transcript": transcript_data,
            "total_lines": len(transcript_data)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
