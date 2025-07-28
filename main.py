from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import re

app = Flask(__name__)

def scrape_gong_transcript(url):
    """
    Enhanced Gong transcript scraper with better speaker name extraction and improved error handling
    """
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

        # Wait a bit for the page to load initially
        time.sleep(5)

        # Get the page source to check for expired access message
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Check for expired access message - multiple possible variations
        page_text = soup.get_text().lower()
        expired_indicators = [
            "access to this call has expired",
            "access has expired",
            "call has expired",
            "link has expired",
            "access expired"
        ]

        for indicator in expired_indicators:
            if indicator in page_text:
                driver.quit()
                return "Access to this call has expired"

        # Check if the page contains common error indicators
        error_indicators = [
            "not found",
            "404",
            "error",
            "access denied",
            "unauthorized",
            "forbidden"
        ]

        # If page contains obvious error indicators but not expired message
        for error_indicator in error_indicators:
            if error_indicator in page_text and "transcript" not in page_text.lower():
                driver.quit()
                return "An unexpected error occurred. The Link is not valid"

        # Continue with normal transcript extraction
        wait = WebDriverWait(driver, 30)

        # Wait for the transcript section to load
        transcript_section = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section.CallTranscript-moduleCLO4Fw[aria-label='Call transcript']"))
        )

        # Additional wait to ensure dynamic content is loaded
        time.sleep(3)

        # Get the page source after everything has loaded
        soup = BeautifulSoup(driver.page_source, "html.parser")

    except Exception as e:
        driver.quit()
        # Check if it's a timeout or element not found - likely expired/invalid link
        error_str = str(e).lower()
        if any(term in error_str for term in ["timeout", "no such element", "element not found"]):
            return "Access to this call has expired"
        else:
            return "An unexpected error occurred. The Link is not valid"

    finally:
        # Make sure driver is closed in all cases where it was successfully created
        try:
            driver.quit()
        except:
            pass

    # Parse the transcript
    transcript_section = soup.select_one("section.CallTranscript-moduleCLO4Fw[aria-label='Call transcript']")
    if not transcript_section:
        return "Access to this call has expired"

    transcript_blocks = transcript_section.select('div.monologue-wrapper')
    if not transcript_blocks:
        return "Access to this call has expired"

    output_lines = []
    for block in transcript_blocks:
        # Multiple selectors for timestamp (try different possible selectors)
        timestamp_element = (
            block.select_one('span.timestamp') or
            block.select_one('.timestamp') or
            block.select_one('[class*="timestamp"]')
        )
        timestamp = timestamp_element.get_text(strip=True) if timestamp_element else ''

        # Multiple selectors for speaker (try different possible selectors)
        speaker_element = (
            block.select_one('span.only-speaker-visible') or
            block.select_one('.only-speaker-visible') or
            block.select_one('span[class*="speaker"]') or
            block.select_one('.speaker-name') or
            block.select_one('[data-speaker]') or
            block.select_one('span.speaker') or
            block.select_one('.participant-name')
        )

        # Extract speaker name with fallback methods
        speaker = ''
        if speaker_element:
            speaker = speaker_element.get_text(strip=True)
            # If speaker element is empty, try getting from data attributes
            if not speaker:
                speaker = speaker_element.get('data-speaker', '') or speaker_element.get('title', '')

        # If still no speaker, try to find it in parent elements
        if not speaker:
            parent_block = block.parent
            if parent_block:
                alt_speaker = parent_block.select_one('[class*="speaker"]')
                if alt_speaker:
                    speaker = alt_speaker.get_text(strip=True)

        # Extract monologue text
        monologue_text = block.select_one('div.monologue-text')
        utterance = ""
        if monologue_text:
            # Try to get individual words first
            word_spans = monologue_text.select('span.monologue-word')
            if word_spans:
                utterance = " ".join([w.get_text(strip=True) for w in word_spans])
            else:
                # Fallback to getting all text
                utterance = monologue_text.get_text(" ", strip=True)

        # Only add to output if we have some content
        if utterance.strip():
            # Format: timestamp | speaker | utterance
            speaker_display = speaker if speaker else "Unknown Speaker"
            match = re.match(r"([A-Za-z\s]+)(\d{1,2}:\d{2})", speaker)
            if match:
                speaker = match.group(1).strip()
                timestamp = match.group(2).strip()
            line = f"{speaker} {timestamp} | {utterance}".strip()
            output_lines.append(line)

    return output_lines


def debug_transcript_structure(url):
    """
    Debug function to help identify the actual DOM structure for speakers
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(
        service=Service("/usr/bin/chromedriver"),
        options=chrome_options
    )

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 30)
        transcript_section = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section.CallTranscript-moduleCLO4Fw"))
        )
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    finally:
        driver.quit()

    # Debug: Find all possible speaker-related elements
    transcript_section = soup.select_one("section.CallTranscript-moduleCLO4Fw")
    if transcript_section:
        # Look for the first few transcript blocks to analyze structure
        blocks = transcript_section.select('div.monologue-wrapper')[:3]
        debug_info = []

        for i, block in enumerate(blocks):
            block_debug = {
                'block_index': i,
                'block_classes': block.get('class', []),
                'all_spans': [],
                'all_divs': []
            }

            # Get all spans in the block
            spans = block.find_all('span')
            for span in spans:
                block_debug['all_spans'].append({
                    'classes': span.get('class', []),
                    'text': span.get_text(strip=True)[:50],  # First 50 chars
                    'attributes': dict(span.attrs)
                })

            # Get all divs in the block
            divs = block.find_all('div')
            for div in divs:
                block_debug['all_divs'].append({
                    'classes': div.get('class', []),
                    'text': div.get_text(strip=True)[:50],  # First 50 chars
                    'attributes': dict(div.attrs)
                })

            debug_info.append(block_debug)

        return debug_info

    return None


@app.route('/')
def index():
    return '''<h1>Gong Transcript Scraper</h1>
<p>Use GET /transcript?url=YOUR_GONG_URL to get transcript with speaker names</p>
<p>Use GET /debug?url=YOUR_GONG_URL to debug DOM structure</p>'''


@app.route('/transcript')
def get_transcript():  
    gong_url = request.args.get('url')

    if not gong_url:
        return jsonify({'error': 'Missing required parameter: url'}), 400

    if 'gong.io' not in gong_url:
        return jsonify({'error': 'Invalid URL: Must contain "gong.io"'}), 400

    try:
        transcript_result = scrape_gong_transcript(gong_url)

        # Check if result is an error message string
        if isinstance(transcript_result, str):
            return jsonify({
                'success': False,
                'error': transcript_result,
                'url': gong_url
            }), 400

        # Normal successful transcript
        return jsonify({
            'success': True,
            'url': gong_url,
            'transcript': transcript_result,
            'total_lines': len(transcript_result),
            'note': 'Speaker names are included after timestamp and before utterance, separated by |'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred. The Link is not valid',
            'url': gong_url
        }), 500


@app.route('/debug')
def debug_structure():
    gong_url = request.args.get('url')

    if not gong_url:
        return jsonify({'error': 'Missing required parameter: url'}), 400

    if 'gong.io' not in gong_url:
        return jsonify({'error': 'Invalid URL: Must contain "gong.io"'}), 400

    try:
        debug_info = debug_transcript_structure(gong_url)
        return jsonify({
            'success': True,
            'url': gong_url,
            'debug_info': debug_info,
            'note': 'This shows the DOM structure of the first 3 transcript blocks to help identify speaker elements'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'url': gong_url
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
