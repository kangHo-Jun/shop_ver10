import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    """Centerlized configuration loader for Shop Automation."""
    
    def __init__(self, env_file=".env"):
        load_dotenv(env_file)
        self.base_dir = Path(os.getcwd())
        
        # Server
        self.FLASK_PORT = int(os.getenv("FLASK_PORT", 5080))
        self.FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
        
        # URLs
        self.YOUNGRIM_URL = os.getenv("YOUNGRIM_URL", "http://door.yl.co.kr/oms/main.jsp")
        self.YOUNGRIM_LEDGER_URL = os.getenv("YOUNGRIM_LEDGER_URL", "http://door.yl.co.kr/oms/ledger_list.jsp")
        self.YOUNGRIM_ESTIMATE_URL = os.getenv("YOUNGRIM_ESTIMATE_URL", "http://door.yl.co.kr/oms/estimate_list.jsp")
        self.DOWNLOAD_INTERVAL_SEC = int(os.getenv("DOWNLOAD_INTERVAL_SEC", 1800))
        
        # Ecount (ERP) Settings
        self.ECOUNT_LOGIN_URL = os.getenv("ECOUNT_LOGIN_URL", "https://login.ecount.com/Login")
        self.ECOUNT_COMPANY_CODE = os.getenv("ECOUNT_COMPANY_CODE", "")
        self.ECOUNT_ID = os.getenv("ECOUNT_ID", "")
        self.ECOUNT_PASSWORD = os.getenv("ECOUNT_PASSWORD", "")
        
        # Google Sheets Settings
        self.GS_SPREADSHEET_ID = os.getenv("GS_SPREADSHEET_ID", "1qEbhwGw4mstuMkhAJyFMK4QiIrZR_Gw3bFMR1wb2Las")
        self.GS_SHEET_NAME = os.getenv("GS_SHEET_NAME", "erp")
        
        # Paths
        self.DATA_DIR = self.base_dir / os.getenv("DATA_DIR", "data") # Keep this line if DATA_DIR is still needed as a separate concept
        self.DOWNLOADS_DIR = self.base_dir / "data" / "downloads"
        self.LOGS_DIR = self.base_dir / "logs"
        self.UPLOADER_LOGS_DIR = self.LOGS_DIR / "uploader"
        self.HISTORY_FILE = self.base_dir / os.getenv("HISTORY_FILE", "v10_history.json")  # V10: Updated history file
        self.GOOGLE_TOKEN_PATH = self.base_dir / "google_token.pickle"
        self.GOOGLE_CREDENTIALS_PATH = self.base_dir / "google_oauth_credentials.json"
        self.ECOUNT_SESSION_PATH = self.base_dir / "ecount_session.json"
        
        # Ensure directories exist
        for d in [self.DOWNLOADS_DIR, self.LOGS_DIR, self.UPLOADER_LOGS_DIR]:
            d.mkdir(parents=True, exist_ok=True)
        (self.DOWNLOADS_DIR / "ledger").mkdir(parents=True, exist_ok=True)
        (self.DOWNLOADS_DIR / "estimate").mkdir(parents=True, exist_ok=True)
        
        # Browser
        self.BROWSER_DEBUG_PORT = int(os.getenv("BROWSER_DEBUG_PORT", 9333))
        self.BROWSER_PROFILE_NAME = os.getenv("BROWSER_PROFILE_NAME", "avast_automation_profile")
        self.CHROMEDRIVER_VERSION = os.getenv("CHROMEDRIVER_VERSION", "142")
        
        # Retry
        self.MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
        self.RETRY_DELAY_SEC = int(os.getenv("RETRY_DELAY_SEC", 2))

        # V10: Distributed Lock Settings
        self.LOCK_TIMEOUT_SEC = int(os.getenv("LOCK_TIMEOUT_SEC", 1800))  # 30 minutes default
        self.LOCK_SHEET_NAME = os.getenv("LOCK_SHEET_NAME", "processing_lock")
        self.ENABLE_DISTRIBUTED_LOCK = os.getenv("ENABLE_DISTRIBUTED_LOCK", "true").lower() == "true"

    def __repr__(self):
        return f"<Config V10 Ports={self.FLASK_PORT} Interval={self.DOWNLOAD_INTERVAL_SEC} DistLock={self.ENABLE_DISTRIBUTED_LOCK}>"

# Singleton instance
config = Config()
