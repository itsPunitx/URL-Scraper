from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

app = Flask(__name__)

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    return driver

def extract_transcript(url):
    driver = get_driver()
    driver.get(url)

    try:
        wait = WebDriverWait(driver, 20)

        # Wait for transcript to load
        transcript_section = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section[aria-label='Call transcript']"))
        )

        # Scroll to bottom to trigger lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # Allow additional content to load

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        transcript_blocks = soup.select("div.TranscriptGroup-module__groupItem")

        results = []

        for block in transcript_blocks:
            # Try extracting speaker name from multiple selector options
            speaker_el = (
                block.select_one('span.only-speaker-visible') or
                block.select_one('.only-speaker-visible') or
                block.select_one('span[class*="speaker"]') or
                block.select_one('.speaker-name') or
                block.select_one('[data-speaker]') or
                block.select_one('span.speaker') or
                block.select_one('.participant-name')
            )

            speaker = speaker_el.get_text(strip=True) if speaker_el else "Unknown"

            # Extract timestamp
            time_el = block.select_one('div[class*="TranscriptGroup-module__timestamp"] span')
            timestamp = time_el.get_text(strip=True) if time_el else "Unknown"

            # Extract actual transcript text
            utterance_el = block.select_one('div[class*="TranscriptGroup-module__textContent"]')
            utterance = utterance_el.get_text(strip=True) if utterance_el else ""

            # Combine and format: Speaker Timestamp | Transcript
            if utterance:
                line = f"{speaker} {timestamp} | {utterance}"
                results.append(line)

    except Exception as e:
        return {"success": False, "error": str(e), "transcript": []}
    finally:
        driver.quit()

    return {"success": True, "transcript": results, "total_lines": len(results)}

@app.route("/transcript")
def get_transcript():
    url = request.args.get("url")
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    data = extract_transcript(url)
    return jsonify(data)

# Optional debug endpoint to inspect raw HTML structure
@app.route("/debug")
def debug_html():
    url = request.args.get("url")
    if not url:
        return "No URL provided", 400

    driver = get_driver()
    driver.get(url)
    time.sleep(5)
    html = driver.page_source
    driver.quit()

    with open("debug_output.html", "w", encoding="utf-8") as f:
        f.write(html)

    return "HTML written to debug_output.html"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
