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
        
        # Paths
        self.DATA_DIR = self.base_dir / os.getenv("DATA_DIR", "data")
        self.DOWNLOADS_DIR = self.base_dir / os.getenv("DOWNLOADS_DIR", "data/downloads")
        self.LOGS_DIR = self.base_dir / os.getenv("LOGS_DIR", "logs")
        self.HISTORY_FILE = os.getenv("HISTORY_FILE", "v8_history.json")
        
        # Ensure directories exist
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        (self.DOWNLOADS_DIR / "ledger").mkdir(parents=True, exist_ok=True)
        (self.DOWNLOADS_DIR / "estimate").mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Browser
        self.BROWSER_DEBUG_PORT = int(os.getenv("BROWSER_DEBUG_PORT", 9333))
        self.BROWSER_PROFILE_NAME = os.getenv("BROWSER_PROFILE_NAME", "avast_automation_profile")
        self.CHROMEDRIVER_VERSION = os.getenv("CHROMEDRIVER_VERSION", "142")
        
        # Retry
        self.MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
        self.RETRY_DELAY_SEC = int(os.getenv("RETRY_DELAY_SEC", 2))

    def __repr__(self):
        return f"<Config Ports={self.FLASK_PORT} Interval={self.DOWNLOAD_INTERVAL_SEC}>"

# Singleton instance
config = Config()
