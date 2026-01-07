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

# V10: Import distributed lock manager
from lock_manager import DistributedLockManager

# Import existing logic
try:
    import local_file_processor
    from erp_upload_automation_v2 import ErpUploadAutomation
except ImportError as e:
    logger.critical(f"Error importing modules: {e}")
    sys.exit(1)

# Server setup
app = Flask(__name__)
lock = threading.Lock()
ledger_lock = threading.Lock()
estimate_lock = threading.Lock()

# V10: Initialize distributed lock manager
distributed_lock = DistributedLockManager()

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
    "start_time": datetime.datetime.now().isoformat(),
    "lock_manager_connected": False,  # V10
    "machine_id": ""  # V10
}

# HTML Template for V10 UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>V10 Automation Control</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; background-color: #0d1117; color: #eee; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        h1 { color: #00d9ff; margin: 0; }
        .uptime { font-size: 0.8em; color: #888; }
        .machine-id { font-size: 0.7em; color: #38ef7d; margin-top: 5px; }
        .card { margin-bottom: 20px; padding: 25px; background: #16213e; border-radius: 12px; border: 1px solid #0f3460; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card h2 { margin-top: 0; font-size: 1.2em; color: #00d9ff; display: flex; justify-content: space-between; }
        .badge { font-size: 0.7em; background: #0f3460; padding: 4px 10px; border-radius: 20px; color: #38ef7d; }
        .badge-warning { background: #f5576c; color: white; }
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
        .v10-badge { background: linear-gradient(135deg, #11998e, #38ef7d); padding: 5px 12px; border-radius: 15px; font-size: 0.7em; color: white; font-weight: bold; }
    </style>
    <script>
        async function updateStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                // Update Lock Manager Status
                const lockStatus = document.getElementById('lock-status');
                const lockMachine = document.getElementById('lock-machine');
                if (data.status.lock_manager_connected) {
                    lockStatus.innerText = '✅ Connected';
                    lockStatus.style.color = '#38ef7d';
                } else {
                    lockStatus.innerText = '❌ Disconnected';
                    lockStatus.style.color = '#f5576c';
                }
                lockMachine.innerText = data.status.machine_id || 'Unknown';

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
            <div>
                <h1>⚡ V10 Dashboard <span class="v10-badge">DISTRIBUTED</span></h1>
                <div class="uptime">V10 Multi-Machine Support</div>
                <div class="machine-id" id="lock-machine">Loading...</div>
            </div>
        </div>

        <div class="card">
            <h2>🔒 Distributed Lock Manager <span class="badge" id="lock-status-badge">Active</span></h2>
            <div class="status-box">
                <div><span class="label">Status:</span><span class="val" id="lock-status">Loading...</span></div>
                <div><span class="label">Machine ID:</span><span class="val" id="lock-machine">-</span></div>
            </div>
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
            Shop Automation V10 | Distributed Lock System | &copy; 2026 Antigravity
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
    if os.path.exists(config.HISTORY_FILE):
        try:
            with open(config.HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Handle legacy format (list)
                if isinstance(data, list):
                    return {"ledger": data, "estimate": []}
                return data
        except:
            return default_history
    return default_history

def save_history(history_dict):
    with open(config.HISTORY_FILE, 'w', encoding='utf-8') as f:
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
            logger.info("[Downloader] No new files downloaded this cycle.")
        else:
            server_status["empty_cycle_count"] = 0
            logger.info(f"[Downloader] Downloaded {l_new} ledger + {e_new} estimate files.")

        server_status["downloader_status"] = "Idle"
        logger.info("[Downloader] Cycle complete. Waiting for next interval.")

    def download_from_page(self, list_url, save_dir, doc_type):
        """
        V10: Enhanced with distributed lock checking

        Args:
            list_url: URL of the list page
            save_dir: Directory to save downloads
            doc_type: 'ledger' or 'estimate'
        """
        logger.info(f"[Downloader] Fetching page: {list_url}")
        browser_manager.navigate(list_url)
        time.sleep(2)

        html_source = browser_manager.get_source()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_source, 'html.parser')

        rows = soup.select("table tbody tr")
        logger.info(f"[Downloader] Found {len(rows)} rows in table")

        history = load_history()
        downloaded_count = 0

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            order_no = cols[0].get_text(strip=True)

            if not order_no or order_no == "":
                continue

            # V10: Check distributed lock BEFORE checking local history
            if not distributed_lock.acquire_lock(order_no, notes=f"Download attempt from {doc_type}"):
                logger.info(f"[V10] Order {order_no} is locked by another machine or already completed - skipping")
                continue

            # Check local history (backward compatibility)
            if order_no in history.get(doc_type, []):
                logger.info(f"[Downloader] {order_no} already in local history - skipping")
                # Release lock since we're skipping
                distributed_lock.release_lock(order_no, status=DistributedLockManager.STATUS_COMPLETED,
                                            notes="Already in local history")
                continue

            try:
                # Find download link
                detail_link_tag = cols[0].find("a")
                if not detail_link_tag:
                    logger.warning(f"[Downloader] No link found for {order_no}")
                    distributed_lock.release_lock(order_no, status=DistributedLockManager.STATUS_FAILED,
                                                notes="No download link")
                    continue

                onclick_attr = detail_link_tag.get("onclick", "")

                import re
                match = re.search(r"openPop\('([^']+)'", onclick_attr)
                if not match:
                    logger.warning(f"[Downloader] Could not parse onclick for {order_no}")
                    distributed_lock.release_lock(order_no, status=DistributedLockManager.STATUS_FAILED,
                                                notes="Parse error")
                    continue

                relative_url = match.group(1)
                full_url = f"http://door.yl.co.kr{relative_url}"

                logger.info(f"[Downloader] Downloading {order_no} from {full_url}")
                browser_manager.navigate(full_url)
                time.sleep(2)

                detail_html = browser_manager.get_source()

                # Save to file
                filename = f"{order_no}.html"
                filepath = save_dir / filename

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(detail_html)

                logger.info(f"[Downloader] ✅ Saved {filepath}")

                # Add to local history
                history[doc_type].append(order_no)
                save_history(history)

                # V10: Update lock status to completed
                distributed_lock.release_lock(order_no, status=DistributedLockManager.STATUS_COMPLETED,
                                            notes="Download successful")

                downloaded_count += 1

            except Exception as e:
                logger.error(f"[Downloader] Error downloading {order_no}: {e}")
                # V10: Mark as failed in distributed lock
                distributed_lock.release_lock(order_id=order_no, status=DistributedLockManager.STATUS_FAILED,
                                            notes=f"Download error: {str(e)[:100]}")
                continue

        return downloaded_count

# Flask Routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stats')
def get_stats():
    history = load_history()

    ledger_files = list((config.DOWNLOADS_DIR / "ledger").glob("*.html")) + \
                   list((config.DOWNLOADS_DIR / "ledger").glob("*.mhtml"))
    estimate_files = list((config.DOWNLOADS_DIR / "estimate").glob("*.html")) + \
                     list((config.DOWNLOADS_DIR / "estimate").glob("*.mhtml"))

    ledger_ids = {f.stem for f in ledger_files}
    estimate_ids = {f.stem for f in estimate_files}

    ledger_history_set = set(history.get("ledger", []))
    estimate_history_set = set(history.get("estimate", []))

    ledger_pending = ledger_ids - ledger_history_set
    estimate_pending = estimate_ids - estimate_history_set

    return jsonify({
        "status": server_status,
        "pending": {
            "ledger": len(ledger_pending),
            "estimate": len(estimate_pending)
        },
        "history_count": {
            "ledger": len(ledger_history_set),
            "estimate": len(estimate_history_set)
        }
    })

@app.route('/trigger_ledger', methods=['POST'])
def trigger_ledger_upload():
    """Trigger ledger upload with lock awareness"""
    if not ledger_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "Ledger upload already running"}), 409

    try:
        server_status["ledger_uploader_status"] = "Running"

        def run_upload():
            try:
                logger.info("[Server] Ledger upload triggered")

                # Process files
                ledger_dir = config.DOWNLOADS_DIR / "ledger"
                html_files = list(ledger_dir.glob("*.html")) + list(ledger_dir.glob("*.mhtml"))

                history = load_history()
                history_set = set(history.get("ledger", []))

                pending_files = [f for f in html_files if f.stem not in history_set]

                if not pending_files:
                    logger.info("[Server] No pending ledger files to process")
                    server_status["ledger_uploader_status"] = "Idle"
                    ledger_lock.release()
                    return

                # Process each file
                for html_file in pending_files:
                    order_id = html_file.stem

                    # V10: Double-check distributed lock
                    lock_status = distributed_lock.get_lock_status(order_id)
                    if lock_status and lock_status['status'] == DistributedLockManager.STATUS_COMPLETED:
                        logger.info(f"[V10] {order_id} already completed by another machine - skipping")
                        continue

                    logger.info(f"[Server] Processing ledger file: {html_file.name}")

                    try:
                        # Parse and process
                        erp_data = local_file_processor.process_html_content(str(html_file))

                        if erp_data:
                            # Upload to ERP
                            automation = ErpUploadAutomation()
                            success = automation.run(direct_data=erp_data, auto_close=True, target_type='ledger')
                            automation.close(keep_browser_open=True)

                            if success:
                                # Add to history
                                history["ledger"].append(order_id)
                                save_history(history)
                                logger.info(f"[Server] ✅ Successfully uploaded {order_id}")
                            else:
                                logger.error(f"[Server] ❌ Failed to upload {order_id}")
                        else:
                            logger.warning(f"[Server] No ERP data extracted from {order_id}")

                    except Exception as e:
                        logger.error(f"[Server] Error processing {order_id}: {e}")
                        continue

                server_status["ledger_uploader_status"] = "Idle"
                logger.info("[Server] Ledger upload complete")

            except Exception as e:
                logger.error(f"[Server] Ledger upload error: {e}")
                server_status["ledger_uploader_status"] = "Idle"
            finally:
                ledger_lock.release()

        thread = threading.Thread(target=run_upload, daemon=True)
        thread.start()

        return jsonify({"status": "success", "message": "Ledger upload started"})

    except Exception as e:
        ledger_lock.release()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trigger_estimate', methods=['POST'])
def trigger_estimate_upload():
    """Trigger estimate upload with lock awareness"""
    if not estimate_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "Estimate upload already running"}), 409

    try:
        server_status["estimate_uploader_status"] = "Running"

        def run_upload():
            try:
                logger.info("[Server] Estimate upload triggered")

                # Process files
                estimate_dir = config.DOWNLOADS_DIR / "estimate"
                html_files = list(estimate_dir.glob("*.html")) + list(estimate_dir.glob("*.mhtml"))

                history = load_history()
                history_set = set(history.get("estimate", []))

                pending_files = [f for f in html_files if f.stem not in history_set]

                if not pending_files:
                    logger.info("[Server] No pending estimate files to process")
                    server_status["estimate_uploader_status"] = "Idle"
                    estimate_lock.release()
                    return

                # Process each file
                for html_file in pending_files:
                    order_id = html_file.stem

                    # V10: Double-check distributed lock
                    lock_status = distributed_lock.get_lock_status(order_id)
                    if lock_status and lock_status['status'] == DistributedLockManager.STATUS_COMPLETED:
                        logger.info(f"[V10] {order_id} already completed by another machine - skipping")
                        continue

                    logger.info(f"[Server] Processing estimate file: {html_file.name}")

                    try:
                        # Parse and process
                        erp_data = local_file_processor.process_html_content(str(html_file))

                        if erp_data:
                            # Upload to ERP
                            automation = ErpUploadAutomation()
                            success = automation.run(direct_data=erp_data, auto_close=True, target_type='estimate')
                            automation.close(keep_browser_open=True)

                            if success:
                                # Add to history
                                history["estimate"].append(order_id)
                                save_history(history)
                                logger.info(f"[Server] ✅ Successfully uploaded {order_id}")
                            else:
                                logger.error(f"[Server] ❌ Failed to upload {order_id}")
                        else:
                            logger.warning(f"[Server] No ERP data extracted from {order_id}")

                    except Exception as e:
                        logger.error(f"[Server] Error processing {order_id}: {e}")
                        continue

                server_status["estimate_uploader_status"] = "Idle"
                logger.info("[Server] Estimate upload complete")

            except Exception as e:
                logger.error(f"[Server] Estimate upload error: {e}")
                server_status["estimate_uploader_status"] = "Idle"
            finally:
                estimate_lock.release()

        thread = threading.Thread(target=run_upload, daemon=True)
        thread.start()

        return jsonify({"status": "success", "message": "Estimate upload started"})

    except Exception as e:
        estimate_lock.release()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/reset_status', methods=['POST'])
def reset_status():
    server_status["last_error"] = None
    server_status["empty_cycle_count"] = 0
    return jsonify({"status": "success"})

# Main Execution
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("V10 Auto Server Starting - Distributed Lock Edition")
    logger.info("=" * 60)

    # V10: Initialize distributed lock manager
    logger.info("[V10] Connecting to distributed lock manager...")
    if distributed_lock.connect():
        server_status["lock_manager_connected"] = True
        server_status["machine_id"] = distributed_lock.machine_id
        logger.info(f"[V10] ✅ Distributed lock manager connected (Machine: {distributed_lock.machine_id})")
    else:
        logger.warning("[V10] ⚠️ Failed to connect to distributed lock manager - running in standalone mode")
        server_status["lock_manager_connected"] = False

    # Start Auto Downloader
    downloader = AutoDownloader()
    downloader.start()
    downloader.activate()
    logger.info("[Server] Auto Downloader activated")

    # Start Flask Server
    logger.info(f"[Server] Starting Flask on port {config.FLASK_PORT}")
    logger.info(f"[Server] Dashboard: http://localhost:{config.FLASK_PORT}")

    app.run(host='0.0.0.0', port=config.FLASK_PORT, debug=config.FLASK_DEBUG, use_reloader=False)
