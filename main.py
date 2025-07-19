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
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def setup_driver():
    """Setup Chrome driver with Render-optimized options and fallback"""
    chrome_options = Options()
    
    # Essential headless options
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    
    # Memory and performance optimization
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--remote-debugging-port=9222")
    
    # User agent to avoid detection
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        # Try ChromeDriverManager first
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Chrome driver initialized successfully with ChromeDriverManager")
        return driver
    except Exception as e:
        logger.warning(f"ChromeDriverManager failed: {e}")
        try:
            # Fallback: try using system Chrome
            chrome_options.binary_location = "/usr/bin/google-chrome-stable"
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("Chrome driver initialized successfully with system Chrome")
            return driver
        except Exception as e2:
            logger.error(f"Both Chrome initialization methods failed: {e2}")
            raise Exception(f"Failed to initialize Chrome driver: {e2}")

def scrape_gong_transcript(url):
    """
    Scrape transcript from Gong.io with speaker names and messages only
    """
    driver = None
    try:
        logger.info(f"Starting transcript extraction for: {url}")
        driver = setup_driver()
        
        # Navigate to the URL
        driver.get(url)
        logger.info("Page loaded, waiting for transcript section")
        
        # Add explicit wait for page load
        time.sleep(3)
        
        # Wait for transcript section to load with extended timeout
        wait = WebDriverWait(driver, 60)
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "section.CallTranscript-moduleCLO4Fw[aria-label='Call transcript']"))
        )
        logger.info("Transcript section found")
        
        # Parse the page source
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Find transcript blocks
        blocks = soup.select("section.CallTranscript-moduleCLO4Fw div.monologue-wrapper")
        if not blocks:
            # Try alternative selector
            blocks = soup.select("div.monologue-wrapper")
            if not blocks:
                logger.error("No transcript blocks found with any selector")
                raise ValueError("Transcript blocks not found - the page structure may have changed")
        
        logger.info(f"Found {len(blocks)} transcript blocks")
        
        transcript = []
        for idx, blk in enumerate(blocks):
            try:
                # Extract speaker name
                speaker_element = blk.select_one("span.only-speaker-visible")
                if not speaker_element:
                    # Try alternative speaker selectors
                    speaker_element = blk.select_one(".speaker-name") or blk.select_one("[data-speaker]")
                
                speaker = speaker_element.get_text(strip=True) if speaker_element else f"Unknown Speaker {idx + 1}"
                
                # Extract words/text from the block
                words = blk.select("span.monologue-word")
                if not words:
                    # Try alternative word selectors
                    words = blk.select("span[data-start]") or blk.select(".word")
                
                if not words:
                    logger.warning(f"No words found in block {idx + 1}")
                    continue
                
                # Combine all words into the transcript message
                message = " ".join(word.get_text(strip=True) for word in words if word.get_text(strip=True))
                
                if message.strip():  # Only add non-empty messages
                    transcript.append({
                        "speaker": speaker,
                        "message": message
                    })
                    
            except Exception as e:
                logger.warning(f"Error processing block {idx + 1}: {e}")
                continue
        
        logger.info(f"Successfully extracted {len(transcript)} transcript entries")
        return transcript
        
    except TimeoutException:
        logger.error("Timeout waiting for transcript to load")
        raise Exception("Timeout waiting for transcript to load. The page may be taking too long to respond or the transcript may not be available.")
    except WebDriverException as e:
        logger.error(f"WebDriver error: {str(e)}")
        raise Exception(f"Browser error occurred: {str(e)}")
    except Exception as e:
        logger.error(f"Error scraping transcript: {str(e)}")
        raise Exception(f"Error scraping transcript: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Chrome driver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")

@app.route('/')
def home():
    return '''
    <h1>Gong Transcript Scraper API</h1>
    <p><strong>Usage:</strong> GET /transcript?url=YOUR_GONG_URL</p>
    <p><strong>Test Chrome:</strong> GET /test</p>
    <p><strong>Filter by Speaker:</strong> GET /transcript/filter?url=YOUR_GONG_URL&speaker=SPEAKER_NAME</p>
    
    <h3>Response Format:</h3>
    <pre>
{
  "success": true,
  "url": "your-gong-url",
  "transcript": [
    {
      "speaker": "Alex Johnson",
      "message": "Hey everyone, thanks for joining the call today."
    },
    {
      "speaker": "Sarah Chen", 
      "message": "Thanks Alex. I wanted to discuss our Q4 strategy and how we can improve our conversion rates."
    }
  ],
  "total_lines": 54
}
    </pre>
    '''

@app.route('/transcript')
def get_transcript():
    """Main endpoint to extract transcript from Gong URL"""
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'gong.io' not in url:
        return jsonify({"error": "Only Gong.io URLs are supported"}), 400
    
    try:
        logger.info(f"Processing transcript request for: {url}")
        transcript_data = scrape_gong_transcript(url)
        
        if not transcript_data:
            return jsonify({
                "success": False,
                "error": "No transcript data found. The call may not have a transcript available."
            }), 404
        
        return jsonify({
            "success": True,
            "url": url,
            "transcript": transcript_data,
            "total_lines": len(transcript_data)
        })
    except Exception as e:
        logger.error(f"Error processing transcript for {url}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }), 500

@app.route('/transcript/filter')
def get_filtered_transcript():
    """Endpoint to get filtered transcript by speaker"""
    url = request.args.get('url')
    speaker_filter = request.args.get('speaker')
    
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400
    
    if 'gong.io' not in url:
        return jsonify({"error": "Only Gong.io URLs are supported"}), 400
    
    try:
        logger.info(f"Processing filtered transcript request for: {url}, speaker: {speaker_filter}")
        transcript_data = scrape_gong_transcript(url)
        
        # Filter by speaker if specified
        if speaker_filter:
            original_count = len(transcript_data)
            transcript_data = [
                item for item in transcript_data 
                if speaker_filter.lower() in item["speaker"].lower()
            ]
            logger.info(f"Filtered from {original_count} to {len(transcript_data)} entries")
        
        return jsonify({
            "success": True,
            "url": url,
            "filters": {"speaker": speaker_filter} if speaker_filter else {},
            "transcript": transcript_data,
            "total_lines": len(transcript_data)
        })
    except Exception as e:
        logger.error(f"Error processing filtered transcript for {url}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }), 500

@app.route('/test')
def test_chrome():
    """Test endpoint to verify Chrome driver is working"""
    try:
        logger.info("Testing Chrome driver setup")
        driver = setup_driver()
        driver.get("https://www.google.com")
        title = driver.title
        driver.quit()
        logger.info(f"Chrome test successful, page title: {title}")
        return jsonify({
            "success": True, 
            "message": "Chrome driver is working correctly",
            "title": title,
            "status": "ready"
        })
    except Exception as e:
        logger.error(f"Chrome test failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e), 
            "error_type": type(e).__name__,
            "status": "failed"
        }), 500

@app.route('/health')
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "gong-transcript-scraper",
        "timestamp": time.time()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
