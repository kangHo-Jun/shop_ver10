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

# Import foundation modules
from config import config
from logging_config import logger
from error_handler import error_handler, ErrorSeverity

# Import existing logic
try:
    import local_file_processor
    from erp_upload_automation_v1 import ErpUploadAutomation
except ImportError as e:
    logger.critical(f"Error importing modules: {e}")
    sys.exit(1)

# Server setup
app = Flask(__name__)
lock = threading.Lock()
ledger_lock = threading.Lock()
estimate_lock = threading.Lock()

# Status tracking
server_status = {
    "downloader_active": False,
    "downloader_last_run": None,
    "downloader_status": "Idle",
    "ledger_uploader_status": "Idle",
    "estimate_uploader_status": "Idle",
    "last_error": None,
    "last_log": "",
    "empty_cycle_count": 0,
    "start_time": datetime.datetime.now().isoformat()
}

# HTML Template for V8.1 UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>V8.1 Automation Control</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background-color: #0d1117; color: #eee; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        h1 { color: #00d9ff; margin: 0; }
        .uptime { font-size: 0.8em; color: #888; }
        .card { margin-bottom: 20px; padding: 25px; background: #16213e; border-radius: 12px; border: 1px solid #0f3460; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card h2 { margin-top: 0; font-size: 1.2em; color: #00d9ff; display: flex; justify-content: space-between; }
        .badge { font-size: 0.7em; background: #0f3460; padding: 4px 10px; border-radius: 20px; color: #38ef7d; }
        .btn { display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: bold; color: white; border: none; border-radius: 8px; cursor: pointer; text-decoration: none; width: 100%; box-sizing: border-box; text-align: center; margin-top: 10px; transition: all 0.2s; }
        .btn-blue { background: linear-gradient(135deg, #667eea, #764ba2); }
        .btn-green { background: linear-gradient(135deg, #11998e, #38ef7d); }
        .btn-orange { background: linear-gradient(135deg, #f093fb, #f5576c); }
        .btn-gray { background: linear-gradient(135deg, #4b5d67, #322f3d); }
        .btn:disabled { background: #444; opacity: 0.6; cursor: not-allowed; transform: none !important; box-shadow: none !important; }
        .status-box { background: #0f3460; padding: 15px; border-radius: 8px; font-family: 'Cascadia Code', monospace; margin-top: 15px; font-size: 0.9em; line-height: 1.6; }
        .label { color: #888; margin-right: 10px; }
        .val { color: #fff; }
        .pending-count { color: #f5576c; font-weight: bold; }
        .footer { text-align: center; margin-top: 40px; color: #444; font-size: 0.8em; }
        .pulse { animation: pulse-animation 2s infinite; }
        @keyframes pulse-animation { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
    <script>
        async function updateStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                
                // Update Downloader
                document.getElementById('dl-status').innerText = data.status.downloader_status;
                document.getElementById('dl-last').innerText = data.status.downloader_last_run || 'None';
                
                // Update Ledger
                document.getElementById('l-pending').innerText = data.pending.ledger;
                document.getElementById('l-history').innerText = data.history_count.ledger;
                const lBtn = document.getElementById('btn-l');
                if (data.pending.ledger > 0 && data.status.ledger_uploader_status === 'Idle') {
                    lBtn.disabled = false;
                    lBtn.innerText = `⬆ Upload Ledger (${data.pending.ledger} items)`;
                } else {
                    lBtn.disabled = true;
                    if (data.status.ledger_uploader_status === 'Running') lBtn.innerText = '⏳ Processing...';
                    else lBtn.innerText = '⬆ No new items to upload';
                }

                // Update Estimate
                document.getElementById('e-pending').innerText = data.pending.estimate;
                document.getElementById('e-history').innerText = data.history_count.estimate;
                const eBtn = document.getElementById('btn-e');
                if (data.pending.estimate > 0 && data.status.estimate_uploader_status === 'Idle') {
                    eBtn.disabled = false;
                    eBtn.innerText = `⬆ Upload Estimate (${data.pending.estimate} items)`;
                } else {
                    eBtn.disabled = true;
                    if (data.status.estimate_uploader_status === 'Running') eBtn.innerText = '⏳ Processing...';
                    else eBtn.innerText = '⬆ No new items to upload';
                }
            } catch (e) { console.error("Stats update failed", e); }
        }

        function triggerAction(endpoint, btn) {
            btn.disabled = true;
            fetch(endpoint, { method: 'POST' })
                .then(r => r.json())
                .then(d => { setTimeout(updateStats, 1000); })
                .catch(e => { alert(e); btn.disabled = false; });
        }

        setInterval(updateStats, 3000);
        window.onload = updateStats;
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ V8.1 Dashboard</h1>
            <div class="uptime">V8.1 Enhanced Server</div>
        </div>

        <div class="card">
            <h2>📥 Auto Downloader <span class="badge pulse">Active</span></h2>
            <div class="status-box">
                <div><span class="label">Status:</span><span class="val" id="dl-status">Loading...</span></div>
                <div><span class="label">Last Run:</span><span class="val" id="dl-last">-</span></div>
            </div>
        </div>

        <div class="card">
            <h2>📦 Purchase Order (원장)</h2>
            <div class="status-box">
                <div><span class="label">Pending:</span><span class="val pending-count" id="l-pending">0</span> items</div>
                <div><span class="label">History:</span><span class="val" id="l-history">0</span> processed</div>
            </div>
            <button id="btn-l" class="btn btn-blue" onclick="triggerAction('/trigger_ledger', this)" disabled>⬆ Upload Ledger</button>
        </div>

        <div class="card">
            <h2>📋 Sales Estimate (견적)</h2>
            <div class="status-box">
                <div><span class="label">Pending:</span><span class="val pending-count" id="e-pending">0</span> items</div>
                <div><span class="label">History:</span><span class="val" id="e-history">0</span> processed</div>
            </div>
            <button id="btn-e" class="btn btn-orange" onclick="triggerAction('/trigger_estimate', this)" disabled>⬆ Upload Estimate</button>
        </div>

        <div class="card">
            <h2>⚙️ Control</h2>
            <button class="btn btn-gray" onclick="triggerAction('/reset_status', this)">🔄 Reset Server Status</button>
        </div>

        <div class="footer">
            Shop Automation V8.1 | &copy; 2026 Antigravity
        </div>
    </div>
</body>
</html>
"""

class DoorBrowser:
    """Browser controller for scraping"""
    def __init__(self):
        self.driver = None

    def launch(self):
        if self.driver:
            try:
                self.driver.current_url
                return
            except:
                self.driver = None

        logger.info("[Browser] Launching Avast Browser for Scraping...")
        avast_path = r"C:\Program Files\AVAST Software\Browser\Application\AvastBrowser.exe"
        profile_dir = config.base_dir / config.BROWSER_PROFILE_NAME
        debug_port = config.BROWSER_DEBUG_PORT
        
        cmd = [
            avast_path,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check", 
            config.YOUNGRIM_URL
        ]
        
        if config.BROWSER_HEADLESS:
            logger.info("[Browser] Running in HEADLESS mode (No Window)")
            cmd.insert(1, "--headless=new")
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
    """Load history with ledger/estimate separation"""
    default_history = {"ledger": [], "estimate": []}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Handle legacy format (list)
                if isinstance(data, list):
                    return {"ledger": data, "estimate": []}
                return data
        except:
            return default_history
    return default_history

def save_history(history_dict):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_dict, f, ensure_ascii=False, indent=2)

class AutoDownloader(threading.Thread):
    """Background thread to download files from both ledger and estimate pages"""
    def __init__(self):
        super().__init__()
        self.running = True
        self.active_mode = False
        self.daemon = True 

    def activate(self):
        self.active_mode = True

    def run(self):
        logger.info("[Downloader] Thread Initiated. Waiting for start command...")
        while self.running:
            if self.active_mode:
                try:
                    self.download_cycle()
                except Exception as e:
                    error_handler.handle(e, context={"thread": "Downloader"}, severity=ErrorSeverity.HIGH)
                
                # Intelligent Wait based on empty cycles
                wait_sec = config.DOWNLOAD_INTERVAL_SEC
                if server_status["empty_cycle_count"] >= 5:
                    wait_sec = min(wait_sec * 2, 7200) # Max 2 hours
                    logger.info(f"[Downloader] Consecutive empty cycles detected ({server_status['empty_cycle_count']}). Extending wait to {wait_sec//60} min.")
                
                for _ in range(wait_sec // 5):
                    if not self.running: break
                    time.sleep(5)
            else:
                time.sleep(2)

    def download_cycle(self):
        server_status["downloader_status"] = "Running"
        server_status["downloader_last_run"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        logger.info("[Downloader] Starting cycle...")
        
        # 1. Launch/Check Browser
        browser_manager.launch()
        
        logger.info(f"[Downloader] Navigating to {config.YOUNGRIM_URL} to ensure session...")
        browser_manager.navigate(config.YOUNGRIM_URL)
        time.sleep(3)
        
        # 2. Download from Ledger List
        logger.info("[Downloader] Processing Ledger List...")
        l_new = self.download_from_page(config.YOUNGRIM_LEDGER_URL, config.DOWNLOADS_DIR / "ledger", "ledger")
        
        # 3. Download from Estimate List
        logger.info("[Downloader] Processing Estimate List...")
        e_new = self.download_from_page(config.YOUNGRIM_ESTIMATE_URL, config.DOWNLOADS_DIR / "estimate", "estimate")
        
        if l_new == 0 and e_new == 0:
            server_status["empty_cycle_count"] += 1
        else:
            server_status["empty_cycle_count"] = 0
            
        logger.info(f"[Downloader] Cycle finished. New: L={l_new}, E={e_new}")
        server_status["downloader_status"] = "Idle"

    def download_from_page(self, list_url, save_base_dir, source_type):
        """Download items from a specific list page"""
        browser_manager.navigate(list_url)
        time.sleep(3)
        
        targets = []
        try:
            tbody = browser_manager.driver.find_element(By.CSS_SELECTOR, "table.table tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 6: continue
                
                date_text = cols[0].text.strip()
                chulhano = cols[1].text.strip()
                if not chulhano or not date_text: continue
                
                targets.append({"date": date_text, "chulhano": chulhano})
        except Exception as e:
            print(f"[Downloader] {source_type} List Warning: {e}")
            
        print(f"[Downloader] Found {len(targets)} items in {source_type} list.")

        new_count = 0
        for item in targets:
            date_str = item['date']
            chulhano = item['chulhano']
            
            save_dir = os.path.join(save_base_dir, date_str)
            os.makedirs(save_dir, exist_ok=True)
            
            file_path = os.path.join(save_dir, f"{chulhano}.html")
            
            if os.path.exists(file_path):
                continue
                
            print(f"   [Download] New {source_type} Item: {chulhano} ({date_str})")
            
            detail_url = f"http://door.yl.co.kr/oms/trans_doc.jsp?chulhano={chulhano}&younglim_gubun=임업"
            browser_manager.navigate(detail_url)
            time.sleep(1)
            
            html_content = browser_manager.get_source()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            new_count += 1
            time.sleep(1)
            
        return new_count

def manual_upload_process(source_type, erp_target):
    """Manual trigger logic with Early Stop and Logging."""
    logger.info(f"[Uploader] Manual Upload Process Triggered for {source_type}.")
    
    status_key = f"{source_type}_uploader_status"
    target_lock = ledger_lock if source_type == "ledger" else estimate_lock
    
    if not target_lock.acquire(blocking=False):
        logger.warning(f"[Uploader] {source_type} upload is already in progress. Skipping.")
        return 0
        
    server_status[status_key] = "Running"
    
    try:
        # Load local history
        history = load_history()
        history_list = history.get(source_type, [])
        
        target_dir = config.DOWNLOADS_DIR / source_type
        if not target_dir.exists():
             logger.info(f"[Uploader] No {source_type} directory found at {target_dir}. Early Stop.")
             return 0

        # Scan for files
        file_list = []
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".html"):
                    file_list.append(os.path.join(root, file))
        
        # Filter files not in history
        pending_files = []
        for fpath in file_list:
            fname = os.path.basename(fpath)
            chulhano = os.path.splitext(fname)[0]
            if chulhano not in history_list:
                pending_files.append(fpath)
                
        # --- EARLY STOP ---
        if not pending_files:
            logger.info(f"[Uploader] All {source_type} items already processed in history. No new files found. Stopping without launching browser.")
            return 0
            
        logger.info(f"[Uploader] Found {len(pending_files)} pending {source_type} files. Proceeding with upload...")
        
        all_data_rows = []
        processed_chulhanos = []
        
        for fpath in pending_files:
            fname = os.path.basename(fpath)
            chulhano = os.path.splitext(fname)[0]
            
            # V7/V8 logic: Determine type for parser
            file_target_type = 'estimate' if source_type == 'estimate' else 'ledger'
            try:
                data_rows = local_file_processor.process_html_file(fpath, target_type=file_target_type)
                if data_rows:
                    all_data_rows.extend(data_rows)
                    processed_chulhanos.append(chulhano)
            except Exception as e:
                error_handler.handle(e, context={"file": fname, "type": source_type}, severity=ErrorSeverity.MEDIUM)

        if not all_data_rows:
             logger.info(f"[Uploader] No valid data rows extracted from {len(pending_files)} pending files.")
             return 0

        logger.info(f"[Uploader] Batch Uploading {len(all_data_rows)} rows to ERP ({erp_target})...")
        server_status["last_log"] = f"Uploading {len(all_data_rows)} rows..."
        
        # ERP Upload with Retry (Phase 2 Improvement)
        erp_uploader = ErpUploadAutomation()
        max_retries = config.MAX_RETRIES
        delay = config.RETRY_DELAY_SEC
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[Uploader] {source_type} Upload Attempt {attempt+1}/{max_retries}...")
                success = erp_uploader.run(direct_data=all_data_rows, auto_close=False, target_type=erp_target)
                
                if success:
                    for chulhano in processed_chulhanos:
                        history_list.append(chulhano)
                    history[source_type] = history_list
                    save_history(history)
                    logger.info(f"[Uploader] {source_type} Batch Upload SUCCESS on attempt {attempt+1}.")
                    return len(processed_chulhanos)
                else:
                    logger.warning(f"[Uploader] {source_type} Batch Upload returned False on attempt {attempt+1}.")
            
            except Exception as e:
                error_handler.handle(e, context={"action": "erp_upload", "attempt": attempt+1}, severity=ErrorSeverity.MEDIUM)
            
            if attempt < max_retries - 1:
                logger.info(f"[Uploader] Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2 # Exponential backoff
        
        logger.error(f"[Uploader] {source_type} Batch Upload FAILED after {max_retries} attempts.")
        return 0

    except Exception as e:
        error_handler.handle(e, context={"uploader": source_type}, severity=ErrorSeverity.CRITICAL)
        return -1
    finally:
        server_status[status_key] = "Idle"
        target_lock.release()

# ---------------------------------------------------------
# Flask Endpoints
# ---------------------------------------------------------

downloader_thread = None

@app.route('/')
def index():
    history = load_history()
    history_count = {
        "ledger": len(history.get("ledger", [])),
        "estimate": len(history.get("estimate", []))
    }
    return render_template_string(HTML_TEMPLATE, status=server_status, history_count=history_count)

@app.route('/start_downloader', methods=['POST'])
def start_downloader_endpoint():
    global downloader_thread
    if server_status["downloader_active"]:
        return jsonify({"status": "ignored", "message": "Downloader already active"})
    
    if downloader_thread:
        downloader_thread.activate()
        server_status["downloader_active"] = True
        return jsonify({"status": "started", "message": "Auto-Downloader Started (원장+견적 30분 간격)"})
    
    return jsonify({"status": "error", "message": "Thread not initialized"})

@app.route('/trigger_ledger', methods=['POST', 'GET'])
def trigger_ledger_upload():
    if server_status["ledger_uploader_status"] == "Running":
         return jsonify({"status": "ignored", "message": "Ledger Uploader is already running"})
    
    thread = threading.Thread(target=manual_upload_process, args=("ledger", "ledger"))
    thread.start()
    
    return jsonify({"status": "accepted", "message": "Ledger Batch Upload Started (→ 구매입력)"})

@app.route('/trigger_estimate', methods=['POST', 'GET'])
def trigger_estimate_upload():
    if server_status["estimate_uploader_status"] == "Running":
         return jsonify({"status": "ignored", "message": "Estimate Uploader is already running"})
    
    thread = threading.Thread(target=manual_upload_process, args=("estimate", "estimate"))
    thread.start()
    
    return jsonify({"status": "accepted", "message": "Estimate Batch Upload Started (→ 견적서입력)"})
    
@app.route('/reset_status', methods=['POST'])
def reset_status_endpoint():
    """상태를 강제로 Idle로 초기화하고 락을 해제합니다."""
    global server_status
    server_status["ledger_uploader_status"] = "Idle"
    server_status["estimate_uploader_status"] = "Idle"
    
    # 락이 잠겨있는 경우 강제 해제 (안전한 방식은 아니나 행 발생 시 복구용)
    try:
        if ledger_lock.locked(): ledger_lock.release()
        if estimate_lock.locked(): estimate_lock.release()
    except:
        pass
        
    return jsonify({"status": "reset", "message": "Server status has been reset to Idle."})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Return structured stats for dashboard."""
    history = load_history()
    
    # Simple count of pending files
    l_pending = 0
    e_pending = 0
    try:
        if (config.DOWNLOADS_DIR / "ledger").exists():
            l_pending = len([f for f in os.listdir(config.DOWNLOADS_DIR / "ledger") if f.endswith(".html")])
        if (config.DOWNLOADS_DIR / "estimate").exists():
            e_pending = len([f for f in os.listdir(config.DOWNLOADS_DIR / "estimate") if f.endswith(".html")])
    except:
        pass

    return jsonify({
        "status": server_status,
        "history_count": {
            "ledger": len(history.get("ledger", [])),
            "estimate": len(history.get("estimate", []))
        },
        "pending": {
            "ledger": l_pending,
            "estimate": e_pending
        },
        "config": {
            "interval": config.DOWNLOAD_INTERVAL_SEC,
            "port": config.FLASK_PORT
        }
    })

if __name__ == "__main__":
    logger.info("="*50)
    logger.info("⚡ V8.1 Enhanced Automation Server")
    logger.info(f"Access UI: http://localhost:{config.FLASK_PORT}")
    logger.info("="*50)
    
    # Init Background Downloader
    downloader_thread = AutoDownloader()
    downloader_thread.start()
    
    # Auto-activate
    downloader_thread.activate()
    server_status["downloader_active"] = True
    
    # Run server
    app.run(host='0.0.0.0', port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
