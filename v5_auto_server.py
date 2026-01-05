import os
import time
import json
import threading
import sys
import subprocess
import datetime
from flask import Flask, jsonify, request, render_template_string
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import traceback

# Import existing logic
try:
    import local_file_processor
    from erp_upload_automation_v1 import ErpUploadAutomation
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

# Configuration
HISTORY_FILE = "v4_history.json" # Share history with V4 for compatibility
DOWNLOAD_BASE_DIR = os.path.join(os.getcwd(), "data", "downloads")
LOGIN_URL = "http://door.yl.co.kr"
LIST_URL = "http://door.yl.co.kr/oms/ledger_list.jsp"
CHECK_INTERVAL_SECONDS = 1800 # 30 minutes

app = Flask(__name__)
lock = threading.Lock() # Global lock for thread safety

# Status tracking
server_status = {
    "downloader_active": False,
    "downloader_last_run": None,
    "downloader_status": "Idle",
    "uploader_status": "Idle",
    "last_error": None
}

# HTML Template for UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>V5 Automation Control</title>
    <style>
        body { font-family: sans-serif; padding: 20px; background-color: #f0f2f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { color: #1a73e8; margin-bottom: 30px; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        .card { margin-bottom: 20px; padding: 20px; border: 1px solid #ddd; border-radius: 8px; }
        .card h2 { margin-top: 0; font-size: 1.2em; color: #333; }
        .btn { display: inline-block; padding: 12px 24px; font-size: 16px; font-weight: bold; color: white; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; width: 100%; box-sizing: border-box; text-align: center; }
        .btn-green { background-color: #28a745; }
        .btn-green:hover { background-color: #218838; }
        .btn-blue { background-color: #007bff; }
        .btn-blue:hover { background-color: #0069d9; }
        .btn-disabled { background-color: #6c757d; cursor: not-allowed; }
        .status-box { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; margin-top: 10px; font-size: 0.9em; }
        .refresh-link { display: block; margin-top: 20px; text-align: center; color: #666; }
    </style>
    <script>
        function triggerAction(endpoint, btnElement) {
            // Remove confirm dialog
            // if(!confirm("Are you sure?")) return;
            
            // Visual feedback on button
            const originalText = btnElement.innerText;
            btnElement.innerText = "Processing...";
            btnElement.disabled = true;

            fetch(endpoint, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    // Remove success alert
                    // alert(data.message);
                    console.log(data.message);
                    location.reload();
                })
                .catch(err => {
                    alert("Error: " + err);
                    btnElement.innerText = originalText;
                    btnElement.disabled = false;
                });
        }
    </script>
</head>
<body>
    <div class="container">
        <h1>V5 Automation Control</h1>

        <!-- Downloader Section -->
        <div class="card">
            <h2>1. Auto Downloader (30m Interval)</h2>
            <p>Automatically downloads files every 30 minutes in the background.</p>
            {% if status.downloader_active %}
                <button class="btn btn-disabled" disabled>✅ Running (Interval: 30m)</button>
            {% else %}
                <button class="btn btn-green" onclick="triggerAction('/start_downloader', this)">▶ Start Auto-Downloader</button>
            {% endif %}
            <div class="status-box">
                Status: {{ status.downloader_status }}<br>
                Last Run: {{ status.downloader_last_run or 'Never' }}
            </div>
        </div>

        <!-- Uploader Section -->
        <div class="card">
            <h2>2. Manual Batch Upload</h2>
            <p>Uploads all pending downloaded files to ERP.</p>
             {% if status.uploader_status == 'Running' %}
                <button class="btn btn-disabled" disabled>⏳ Uploading...</button>
            {% else %}
                <button class="btn btn-blue" onclick="triggerAction('/trigger', this)">⬆ Start Batch Upload</button>
            {% endif %}
            <div class="status-box">
                Status: {{ status.uploader_status }}<br>
                History Count: {{ history_count }}
            </div>
        </div>
        
        <a href="javascript:location.reload()" class="refresh-link">🔄 Refresh Status</a>
    </div>
</body>
</html>
"""

class DoorBrowser:
    """Browser controller for scraping (Reused from V4)"""
    def __init__(self):
        self.driver = None

    def launch(self):
        if self.driver:
            try:
                self.driver.current_url
                return
            except:
                self.driver = None

        print("[Browser] Launching Avast Browser for Scraping...")
        avast_path = r"C:\Program Files\AVAST Software\Browser\Application\AvastBrowser.exe"
        profile_dir = os.path.join(os.getcwd(), "avast_automation_profile")
        debug_port = 9333
        
        cmd = [
            avast_path,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check", 
            LOGIN_URL
        ]
        # Launch browser process
        subprocess.Popen(cmd)
        time.sleep(3)
        
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        
        print("[Browser] Connecting Driver...")
        try:
             service = Service(ChromeDriverManager(driver_version="142").install())
             self.driver = webdriver.Chrome(service=service, options=chrome_options)
             print("✅ Browser Connected")
        except Exception as e:
             print(f"[Error] Driver Init Failed: {e}")
             raise e

    def get_source(self):
        return self.driver.page_source

    def navigate(self, url):
        self.driver.get(url)

browser_manager = DoorBrowser()

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_history(processed_set):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(processed_set), f, ensure_ascii=False, indent=2)

class AutoDownloader(threading.Thread):
    """Background thread to download files every 30 mins"""
    def __init__(self):
        super().__init__()
        self.running = True
        self.active_mode = False # Starts inactive until button press
        self.daemon = True 

    def activate(self):
        self.active_mode = True

    def run(self):
        print("[Downloader] Thread Initiated. Waiting for start command...")
        while self.running:
            if self.active_mode:
                try:
                    self.download_cycle()
                except Exception as e:
                    print(f"[Downloader] Error: {e}")
                    server_status["last_error"] = str(e)
                    traceback.print_exc()
                
                # Wait for next cycle
                # Check status frequently to allow updates
                for _ in range(CHECK_INTERVAL_SECONDS // 5):
                    if not self.running: break
                    time.sleep(5)
            else:
                # Idle loop waiting for activation
                time.sleep(2)

    def download_cycle(self):
        server_status["downloader_status"] = "Running"
        server_status["downloader_last_run"] = datetime.datetime.now().isoformat()
        
        print("\n[Downloader] Starting cycle...")
        
        # 1. Launch/Check Browser
        browser_manager.launch()
        
        # 2. Go to List
        browser_manager.navigate(LIST_URL)
        time.sleep(3)
        
        # 3. Parse List
        targets = []
        try:
            tbody = browser_manager.driver.find_element(By.CSS_SELECTOR, "table.table tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 6: continue
                
                date_text = cols[0].text.strip() # YYYY-MM-DD
                chulhano = cols[1].text.strip()
                if not chulhano or not date_text: continue
                
                targets.append({"date": date_text, "chulhano": chulhano})
        except Exception as e:
            print(f"[Downloader] List Warning: {e}")
            
        print(f"[Downloader] Found {len(targets)} items in list.")

        # 4. Check & Download
        new_count = 0
        for item in targets:
            date_str = item['date']
            chulhano = item['chulhano']
            
            # Directory: data/downloads/YYYY-MM-DD/
            save_dir = os.path.join(DOWNLOAD_BASE_DIR, date_str)
            os.makedirs(save_dir, exist_ok=True)
            
            file_path = os.path.join(save_dir, f"{chulhano}.html")
            
            if os.path.exists(file_path):
                continue
                
            print(f"   [Download] New Item: {chulhano} ({date_str})")
            
            detail_url = f"http://door.yl.co.kr/oms/trans_doc.jsp?chulhano={chulhano}&younglim_gubun=임업"
            browser_manager.navigate(detail_url)
            time.sleep(1) # Wait for load
            
            html_content = browser_manager.get_source()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            new_count += 1
            time.sleep(1) # Polite delay
            
        print(f"[Downloader] Cycle finished. Downloaded {new_count} new files.")
        server_status["downloader_status"] = "Waiting (Next run in 30m)"


def manual_upload_process():
    """Manual trigger logic: Load files -> Process -> Upload"""
    print("\n[Uploader] Manual Upload Process Started.")
    server_status["uploader_status"] = "Running"
    
    try:
        history = load_history()
        
        if not os.path.exists(DOWNLOAD_BASE_DIR):
             print("[Uploader] No download directory found.")
             server_status["uploader_status"] = "Idle"
             return 0

        # Collect all html files
        file_list = []
        for root, dirs, files in os.walk(DOWNLOAD_BASE_DIR):
            for file in files:
                if file.endswith(".html"):
                    file_list.append(os.path.join(root, file))
        
        print(f"[Uploader] Found {len(file_list)} cached files.")
        
        pending_files = []
        for fpath in file_list:
            fname = os.path.basename(fpath)
            chulhano = os.path.splitext(fname)[0]
            if chulhano not in history:
                pending_files.append(fpath)
                
        if not pending_files:
            print("[Uploader] All files already processed. Nothing to do.")
            server_status["uploader_status"] = "Idle"
            return 0
            
        print(f"[Uploader] Processing {len(pending_files)} pending files...")
        
        # 1. Merge All Data
        all_data_rows = []
        processed_chulhanos = []
        
        for fpath in pending_files:
            fname = os.path.basename(fpath)
            chulhano = os.path.splitext(fname)[0]
            
            if chulhano in history: continue
            
            # print(f"> Parsing: {chulhano}")
            data_rows = local_file_processor.process_html_file(fpath)
            
            if data_rows:
                all_data_rows.extend(data_rows)
                processed_chulhanos.append(chulhano)
            else:
                print(f"   [Skip] No data in {chulhano}")

        if not all_data_rows:
             print("[Uploader] No valid data found in pending files.")
             server_status["uploader_status"] = "Idle"
             return 0

        # 2. Upload Once
        print(f"> Batch Uploading {len(all_data_rows)} rows from {len(processed_chulhanos)} files...")
        erp_uploader = ErpUploadAutomation()
        
        try:
            # auto_close=True to avoid blocking input() wait
            success = erp_uploader.run(direct_data=all_data_rows, auto_close=True)
            
            if success:
                # 3. Update History
                for chulhano in processed_chulhanos:
                    history.add(chulhano)
                save_history(history)
                print(f"   [Done] Batch Upload Success. History updated.")
                return len(processed_chulhanos)
            else:
                print("   [Fail] Batch Upload returned False.")
                return 0
                
        except Exception as e:
            print(f"   [Fail] Upload Exception: {e}")
            raise e

    except Exception as e:
        print(f"[Uploader] Critical Error: {e}")
        server_status["last_error"] = str(e)
        traceback.print_exc()
        return -1
    finally:
        server_status["uploader_status"] = "Idle"

# ---------------------------------------------------------
# Flask Endpoints
# ---------------------------------------------------------

downloader_thread = None

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, status=server_status, history_count=len(load_history()))

@app.route('/start_downloader', methods=['POST'])
def start_downloader_endpoint():
    global downloader_thread
    if server_status["downloader_active"]:
        return jsonify({"status": "ignored", "message": "Downloader already active"})
    
    if downloader_thread:
        downloader_thread.activate()
        server_status["downloader_active"] = True
        return jsonify({"status": "started", "message": "Auto-Downloader Started (Runs every 30m)"})
    
    return jsonify({"status": "error", "message": "Thread not initialized"})

@app.route('/trigger', methods=['POST', 'GET'])
def trigger_upload():
    if server_status["uploader_status"] == "Running":
         return jsonify({"status": "ignored", "message": "Uploader is already running"})
    
    thread = threading.Thread(target=manual_upload_process)
    thread.start()
    
    return jsonify({"status": "accepted", "message": "Batch Upload Started in Background"})

@app.route('/status', methods=['GET'])
def get_status():
    history = load_history()
    return jsonify({
        "server_status": server_status,
        "history_count": len(history)
    })

if __name__ == "__main__":
    print("="*50)
    print("V5 Hybrid Automation Server")
    print("Access the UI at: http://localhost:5000")
    print("="*50)
    
    # Init Background Downloader (Idle state)
    downloader_thread = AutoDownloader()
    downloader_thread.start()
    
    # Start Web Server
    app.run(host='0.0.0.0', port=5000)
