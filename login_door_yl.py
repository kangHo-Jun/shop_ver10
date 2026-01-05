import os
import time
import subprocess
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Targets
LOGIN_URL = "http://door.yl.co.kr"
USER_ID = "00160003"
USER_PW = "1234"

# Possible Avast Browser Paths
AVAST_PATHS = [
    r"C:\Program Files (x86)\AVAST Software\Browser\Application\AvastBrowser.exe",
    r"C:\Program Files\AVAST Software\Browser\Application\AvastBrowser.exe",
    r"C:\Users\{}\AppData\Local\AVAST Software\Browser\Application\AvastBrowser.exe".format(os.getlogin())
]

def find_avast_binary():
    for path in AVAST_PATHS:
        if os.path.exists(path):
            return path
    return None

def kill_browser():
    """Force closes existing Avast Browser instances to unlock the profile."""
    print("Closing existing Avast Browser instances...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "AvastBrowser.exe"], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2) # Wait for file locks to release
    except Exception as e:
        print(f"Warning during kill: {e}")

def launch_browser(binary_path):
    """Launches Avast Browser with remote debugging and specific profile."""
    # Use a LOCAL isolation profile to avoid locks with the main browser
    profile_dir = os.path.join(os.getcwd(), "avast_automation_profile")
    if not os.path.exists(profile_dir):
        os.makedirs(profile_dir)
        
    cmd = [
        binary_path,
        f"--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        LOGIN_URL
    ]
    
    print(f"Launching Avast Browser from: {binary_path}")
    print(f"Profile (Isolated): {profile_dir}")
    
    # Launch as a separate process
    process = subprocess.Popen(cmd)
    return process

def main():
    # input("준비되셨으면 Enter를 눌러주세요...")
    
    binary_path = find_avast_binary()
    if not binary_path:
        print("ERROR: Could not find Avast Secure Browser executable.")
        print("Checked paths:", AVAST_PATHS)
        return

    # 1. Kill existing instances
    kill_browser()

    # 2. Launch browser with debug port
    process = launch_browser(binary_path)
    
    # 3. Wait & Connect Loop
    print("Waiting for browser to initialize...")
    driver = None
    
    for attempt in range(3):
        try:
            time.sleep(5) # Wait 5s, 10s, 15s...
            print(f"Connection attempt {attempt+1}/3...")
            
            options = Options()
            options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            print("Successfully connected to Avast Browser.")
            break
        except Exception as e:
            print(f"Connection failed: {e}")
            if attempt == 2:
                print("Could not connect after 3 attempts. Aborting.")
                # Kill the process we spawned if we can't control it
                process.kill() 
                return

    # 4. Connected - Proceed
    try:
        
        # 5. Interactive Login Wait
        # 6. Navigate to Ledger List (V4 Batch Logic)
        list_url = "http://door.yl.co.kr/oms/ledger_list.jsp"
        driver.get(list_url)
        print(f"Navigated to List: {list_url}")
        time.sleep(3) # Wait for table load
        
        # Check Login (Redirects usually change URL)
        if "login" in driver.current_url.lower():
            print("="*50)
            print(" [알림] 로그인이 필요합니다.")
            input(" 브라우저에서 로그인 후, 이 창에서 [Enter]를 눌러주세요...")
            driver.get(list_url)
            time.sleep(3)
        
        # 7. Scrape Transactions
        print("Scraping transaction list...")
        transactions = []
        try:
            # Find all rows text first to avoid stale elements
            tbody = driver.find_element(By.CSS_SELECTOR, "table.table tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            
            for row in rows:
                try:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 6: continue
                    
                    date_text = cols[0].text.strip() # "25-12-11"
                    chulhano = cols[1].text.strip()  # "2512110277"
                    
                    if not chulhano: continue # Skip summary rows
                    
                    # Filter Date (>= 25-12-11)
                    # String comparison works for YY-MM-DD
                    if date_text >= "25-12-11":
                        transactions.append({
                            "date": date_text,
                            "chulhano": chulhano
                        })
                except Exception as e:
                    continue # Skip bad row
        except Exception as e:
            print(f"Error scraping list: {e}")
            
        print(f"Found {len(transactions)} transactions to process.")
        
        # 8. Download Loop
        save_dir = r"C:\Users\DSAI\Desktop\원본"
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        for idx, item in enumerate(transactions):
            chulhano = item['chulhano']
            date = item['date']
            filename = f"거래명세서_{chulhano}.html"
            save_path = os.path.join(save_dir, filename)
            
            print(f"[{idx+1}/{len(transactions)}] Checking {date} - {chulhano}...")
            
            if os.path.exists(save_path):
                print(f"   Skipping (Already exists): {filename}")
                continue
            
            # Download
            target_url = f"http://door.yl.co.kr/oms/trans_doc.jsp?chulhano={chulhano}&younglim_gubun=임업"
            driver.get(target_url)
            time.sleep(1.5) # Wait for load
            
            html_content = driver.page_source
            if "거래명세서" not in html_content and "로그인" in html_content:
                print("   Logged out? Pausing...")
                input("Login again and press Enter...")
                driver.get(target_url)
                time.sleep(1.5)
                html_content = driver.page_source

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"   ✅ Saved: {filename}")
            
        print("\n" + "="*50)
        print("✨ All downloads completed!")
        print("="*50)
        print("\nScript finished. Browser window remains open.")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        # If connection failed, we might want to kill the process we started
        # process.kill()

if __name__ == "__main__":
    main()
