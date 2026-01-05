import os
import time
import json
import threading
import sys
import subprocess
from flask import Flask, jsonify
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

try:
    import local_file_processor
    from erp_upload_automation_v1 import ErpUploadAutomation
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

HISTORY_FILE = "v4_history.json"
LOGIN_URL = "http://door.yl.co.kr"
LIST_URL = "http://door.yl.co.kr/oms/ledger_list.jsp"
USER_ID = "00160003"
USER_PW = "1234"

app = Flask(__name__)
lock = threading.Lock()
is_running = False

class DoorBrowser:
    def __init__(self):
        self.driver = None

    def launch(self):
        if self.driver:
            try:
                self.driver.current_url
                return
            except:
                self.driver = None

        print("[Info] Launching Browser...")
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
        
        print("   Checking Driver...")
        try:
             service = Service(ChromeDriverManager(driver_version="142").install())
             self.driver = webdriver.Chrome(service=service, options=chrome_options)
             print("✅ 브라우저 연결 성공")
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

def run_batch_process():
    print("DEBUG: Thread run_batch_process STARTED")
    global is_running
    
    def log(msg):
        print(msg)
        try:
            with open("server.log", "a", encoding="utf-8") as f:
                f.write(str(msg) + "\n")
        except: pass

    with lock:
        if is_running:
            log("[Warning] Already running.")
            return
        is_running = True
        
    try:
        log("\n[Start] V4 Direct Automation Started...")
        history = load_history()
        new_processed = set()
        
        browser_manager.launch()
        print(f"Go to: {LIST_URL}")
        browser_manager.navigate(LIST_URL)
        time.sleep(3)
        
        transactions = []
        try:
            tbody = browser_manager.driver.find_element(By.CSS_SELECTOR, "table.table tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 6: continue
                
                date_text = cols[0].text.strip()
                chulhano = cols[1].text.strip()
                if not chulhano: continue
                
                if chulhano in history:
                    continue
                transactions.append({"date": date_text, "chulhano": chulhano})
        except Exception as e:
            print(f"Scraping Error: {e}")
            
        print(f"Target Count: {len(transactions)}")
        
        erp_uploader = ErpUploadAutomation()
        
        for item in transactions:
            chulhano = item['chulhano']
            print(f"> Processing: {chulhano} ({item['date']})")
            
            detail_url = f"http://door.yl.co.kr/oms/trans_doc.jsp?chulhano={chulhano}&younglim_gubun=임업"
            browser_manager.navigate(detail_url)
            time.sleep(1)
            
            html_content = browser_manager.get_source()
            data_rows = local_file_processor.process_html_content(html_content, file_path_hint=chulhano)
            
            if not data_rows:
                print("   No Data / Parse Failed")
                continue
            try:
                print("   Uploading to ERP...")
                erp_uploader.run(direct_data=data_rows)
                print("   [Done] Upload Complete")
                history.add(chulhano)
                new_processed.add(chulhano)
                save_history(history)
            except Exception as e:
                print(f"   [Fail] ERP Upload Failed: {e}")
        
        count = len(new_processed)
        log(f"\n[Finished] Total {count} processed.")

    except Exception as e:
        log(f"[Critical Error] {e}")
    finally:
        is_running = False
        print("DEBUG: Thread finished, is_running=False")

@app.route('/trigger', methods=['GET', 'POST'])
def trigger():
    print("DEBUG: /trigger endpoint called")
    if is_running:
        return jsonify({"status": "ignored", "message": "Already running"})
        
    thread = threading.Thread(target=run_batch_process)
    print("DEBUG: Starting thread...")
    thread.start()
    print("DEBUG: Thread started.")
    
    return jsonify({"status": "accepted", "message": "Batch process started"})

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"running": is_running, "history_count": len(load_history())})

if __name__ == "__main__":
    print("="*50)
    print("V4 Direct Automation Server")
    print("="*50)
    app.run(host='0.0.0.0', port=5000)
