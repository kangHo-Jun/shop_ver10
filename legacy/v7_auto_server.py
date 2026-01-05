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
    from erp_upload_automation_v1 import ErpUploadAutomation  # V7도 검증된 V1 엔진 사용
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

# Configuration
HISTORY_FILE = "v7_history.json"  # V7 전용 히스토리
DOWNLOAD_BASE_DIR = os.path.join(os.getcwd(), "data", "downloads")
LEDGER_DOWNLOAD_DIR = os.path.join(DOWNLOAD_BASE_DIR, "ledger")
ESTIMATE_DOWNLOAD_DIR = os.path.join(DOWNLOAD_BASE_DIR, "estimate")

LOGIN_URL = "http://door.yl.co.kr/oms/main.jsp"
LEDGER_LIST_URL = "http://door.yl.co.kr/oms/ledger_list.jsp"
ESTIMATE_LIST_URL = "http://door.yl.co.kr/oms/estimate_list.jsp"
CHECK_INTERVAL_SECONDS = 1800  # 30 minutes

app = Flask(__name__)
lock = threading.Lock()
ledger_lock = threading.Lock()    # 원장 업로드 전용 락
estimate_lock = threading.Lock()  # 견적 업로드 전용 락

# Status tracking
server_status = {
    "downloader_active": False,
    "downloader_last_run": None,
    "downloader_status": "Idle",
    "ledger_uploader_status": "Idle",
    "estimate_uploader_status": "Idle",
    "last_error": None
}

# HTML Template for V6 UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>V7 Automation Control</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; padding: 20px; background-color: #2d132c; color: #eee; }
        .container { max-width: 700px; margin: 0 auto; }
        h1 { color: #00d9ff; margin-bottom: 10px; }
        .subtitle { color: #888; margin-bottom: 30px; }
        .card { margin-bottom: 20px; padding: 25px; background: #16213e; border-radius: 12px; border: 1px solid #0f3460; }
        .card h2 { margin-top: 0; font-size: 1.1em; color: #00d9ff; }
        .btn { display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: bold; color: white; border: none; border-radius: 8px; cursor: pointer; text-decoration: none; width: 100%; box-sizing: border-box; text-align: center; margin-top: 10px; transition: all 0.2s; }
        .btn-blue { background: linear-gradient(135deg, #667eea, #764ba2); }
        .btn-blue:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); }
        .btn-green { background: linear-gradient(135deg, #11998e, #38ef7d); }
        .btn-green:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(56, 239, 125, 0.4); }
        .btn-orange { background: linear-gradient(135deg, #f093fb, #f5576c); }
        .btn-orange:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(245, 87, 108, 0.4); }
        .btn-gray { background: linear-gradient(135deg, #4b5d67, #322f3d); }
        .btn-gray:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(75, 93, 103, 0.4); }
        .btn-disabled { background: #444; cursor: not-allowed; }
        .status-box { background: #0f3460; padding: 12px; border-radius: 6px; font-family: monospace; margin-top: 15px; font-size: 0.85em; }
        .status-running { color: #38ef7d; }
        .status-idle { color: #888; }
        .refresh-link { display: block; margin-top: 25px; text-align: center; color: #667eea; }
        .section-title { font-size: 0.9em; color: #888; margin-bottom: 15px; border-bottom: 1px solid #0f3460; padding-bottom: 10px; }
    </style>
    <script>
        function triggerAction(endpoint, btnElement) {
            const originalText = btnElement.innerText;
            btnElement.innerText = "Processing...";
            btnElement.disabled = true;

            fetch(endpoint, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
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
        <h1>🌟 V7 Automation Control</h1>
        <p class="subtitle">원장조회 + 견적조회 듀얼 다운로드 시스템 (견적 O/P/Q열 지원)</p>

        <!-- Downloader Section -->
        <div class="card">
            <h2>📥 Auto Downloader (30분 간격)</h2>
            <p class="section-title">원장조회/견적조회 페이지를 자동으로 감시하고 새 주문을 다운로드합니다.</p>
            {% if status.downloader_active %}
                <button class="btn btn-disabled" disabled>✅ 자동 감시 중 (30분 간격)</button>
            {% else %}
                <button class="btn btn-green" onclick="triggerAction('/start_downloader', this)">▶ Start Auto-Downloader</button>
            {% endif %}
            <div class="status-box">
                상태: <span class="{{ 'status-running' if status.downloader_active else 'status-idle' }}">{{ status.downloader_status }}</span><br>
                마지막 실행: {{ status.downloader_last_run or 'Never' }}
            </div>
        </div>

        <!-- Upload Section: Ledger -->
        <div class="card">
            <h2>📦 원장 데이터 → 구매입력</h2>
            <p class="section-title">원장조회에서 다운로드된 파일을 ERP 구매입력에 업로드합니다.</p>
            {% if status.ledger_uploader_status == 'Running' %}
                <button class="btn btn-disabled" disabled>⏳ 업로드 중...</button>
            {% else %}
                <button class="btn btn-blue" onclick="triggerAction('/trigger_ledger', this)">⬆ Upload Ledger (구매입력)</button>
            {% endif %}
            <div class="status-box">
                상태: {{ status.ledger_uploader_status }}<br>
                원장 이력: {{ history_count.ledger }}건
            </div>
        </div>

        <!-- Upload Section: Estimate -->
        <div class="card">
            <h2>📋 견적 데이터 → 견적서입력</h2>
            <p class="section-title">견적조회에서 다운로드된 파일을 ERP 견적서입력에 업로드합니다.</p>
            {% if status.estimate_uploader_status == 'Running' %}
                <button class="btn btn-disabled" disabled>⏳ 업로드 중...</button>
            {% else %}
                <button class="btn btn-orange" onclick="triggerAction('/trigger_estimate', this)">⬆ Upload Estimate (견적서입력)</button>
            {% endif %}
            <div class="status-box">
                상태: {{ status.estimate_uploader_status }}<br>
                견적 이력: {{ history_count.estimate }}건
            </div>
        <div class="card">
            <h2>🛠 Server Control</h2>
            <p class="section-title">작업이 멈췄거나 강제 초기화가 필요한 경우 사용하세요.</p>
            <button class="btn btn-gray" onclick="triggerAction('/reset_status', this)">🔄 Reset Server Status (상태 초기화)</button>
        </div>

        <a href="javascript:location.reload()" class="refresh-link">🔄 Refresh Status</a>
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
        print("[Downloader] Thread Initiated. Waiting for start command...")
        while self.running:
            if self.active_mode:
                try:
                    self.download_cycle()
                except Exception as e:
                    print(f"[Downloader] Error: {e}")
                    server_status["last_error"] = str(e)
                    traceback.print_exc()
                
                for _ in range(CHECK_INTERVAL_SECONDS // 5):
                    if not self.running: break
                    time.sleep(5)
            else:
                time.sleep(2)

    def download_cycle(self):
        server_status["downloader_status"] = "Running"
        server_status["downloader_last_run"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print("\n[Downloader] Starting cycle...")
        
        # 1. Launch/Check Browser
        browser_manager.launch()
        
        # 브라우저가 열리면 우선 메인 페이지로 이동하여 로그인 보장
        print(f"[Downloader] Navigating to {LOGIN_URL} to ensure session...")
        browser_manager.navigate(LOGIN_URL)
        time.sleep(3) # 로그인 처리/세션 유효 대기
        
        # 2. Download from Ledger List
        print("[Downloader] Processing Ledger List...")
        self.download_from_page(LEDGER_LIST_URL, LEDGER_DOWNLOAD_DIR, "ledger")
        
        # 3. Download from Estimate List
        print("[Downloader] Processing Estimate List...")
        self.download_from_page(ESTIMATE_LIST_URL, ESTIMATE_DOWNLOAD_DIR, "estimate")
        
        print(f"[Downloader] Cycle finished.")
        server_status["downloader_status"] = "대기 중 (다음 실행: 30분 후)"

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
            
        print(f"[Downloader] {source_type}: Downloaded {new_count} new files.")


def manual_upload_process(source_type, erp_target):
    """Manual trigger logic: Load files -> Process -> Upload"""
    print(f"\n[Uploader] Manual Upload Process Started for {source_type}.")
    
    status_key = f"{source_type}_uploader_status"
    
    # 작업 락 선택
    target_lock = ledger_lock if source_type == "ledger" else estimate_lock
    
    if not target_lock.acquire(blocking=False):
        print(f"[Uploader] {source_type} upload is already in progress. Skipping.")
        return 0
        
    server_status[status_key] = "Running"
    
    try:
        history = load_history()
        history_list = history.get(source_type, [])
        
        if source_type == "ledger":
            download_dir = LEDGER_DOWNLOAD_DIR
        else:
            download_dir = ESTIMATE_DOWNLOAD_DIR
        
        if not os.path.exists(download_dir):
             print(f"[Uploader] No {source_type} download directory found.")
             server_status[status_key] = "Idle"
             return 0

        file_list = []
        for root, dirs, files in os.walk(download_dir):
            for file in files:
                if file.endswith(".html"):
                    file_list.append(os.path.join(root, file))
        
        print(f"[Uploader] Found {len(file_list)} cached {source_type} files.")
        
        pending_files = []
        for fpath in file_list:
            fname = os.path.basename(fpath)
            chulhano = os.path.splitext(fname)[0]
            if chulhano not in history_list:
                pending_files.append(fpath)
                
        if not pending_files:
            print(f"[Uploader] All {source_type} files already processed. Nothing to do.")
            server_status[status_key] = "Idle"
            return 0
            
        print(f"[Uploader] Processing {len(pending_files)} pending {source_type} files...")
        
        all_data_rows = []
        processed_chulhanos = []
        
        for fpath in pending_files:
            fname = os.path.basename(fpath)
            chulhano = os.path.splitext(fname)[0]
            
            if chulhano in history_list: continue
            
            # V7: 견적(estimate)일 경우 target_type='estimate' 전달하여 O/P/Q열 레이아웃 적용
            file_target_type = 'estimate' if source_type == 'estimate' else 'ledger'
            data_rows = local_file_processor.process_html_file(fpath, target_type=file_target_type)
            
            if data_rows:
                all_data_rows.extend(data_rows)
                processed_chulhanos.append(chulhano)
            else:
                print(f"   [Skip] No data in {chulhano}")

        if not all_data_rows:
             print(f"[Uploader] No valid data found in pending {source_type} files.")
             server_status[status_key] = "Idle"
             return 0

        # 테스트를 위해 데이터 행 수 제한 (사용자 요청: 10건)
        if len(all_data_rows) > 10:
            print(f"> [Test Mode] Data rows limited to 10 (Original: {len(all_data_rows)})")
            all_data_rows = all_data_rows[:10]

        print(f"> Batch Uploading {len(all_data_rows)} rows from {len(processed_chulhanos)} {source_type} files...")
        erp_uploader = ErpUploadAutomation()
        
        try:
            # auto_close=False로 설정하여 붙여넣기 후 수동 확인 가능하도록 수정
            success = erp_uploader.run(direct_data=all_data_rows, auto_close=False, target_type=erp_target)
            
            if success:
                for chulhano in processed_chulhanos:
                    history_list.append(chulhano)
                history[source_type] = history_list
                save_history(history)
                print(f"   [Done] {source_type} Batch Upload Success. History updated.")
                return len(processed_chulhanos)
            else:
                print(f"   [Fail] {source_type} Batch Upload returned False.")
                return 0
                
        except Exception as e:
            print(f"   [Fail] {source_type} Upload Exception: {e}")
            raise e

    except Exception as e:
        print(f"[Uploader] {source_type} Critical Error: {e}")
        server_status["last_error"] = str(e)
        traceback.print_exc()
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

@app.route('/status', methods=['GET'])
def get_status():
    history = load_history()
    return jsonify({
        "server_status": server_status,
        "history_count": {
            "ledger": len(history.get("ledger", [])),
            "estimate": len(history.get("estimate", []))
        }
    })

if __name__ == "__main__":
    print("="*50)
    print("V7 Hybrid Automation Server")
    print("원장조회 + 견적조회 듀얼 다운로드 시스템 (O/P/Q열 견적 지원)")
    print("Access the UI at: http://localhost:5070")
    print("="*50)
    
    # Init Background Downloader
    downloader_thread = AutoDownloader()
    downloader_thread.start()
    
    # V6: Auto-activate downloader on server start
    print("[V6] Auto-activating downloader on startup...")
    downloader_thread.activate()
    server_status["downloader_active"] = True
    
    # Start Web Server (V7: 포트 5070 사용)
    app.run(host='0.0.0.0', port=5070)
