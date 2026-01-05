"""
ERP 시트 → Ecount 업로드 자동화
================================
Google Sheets의 "ERP" 시트 데이터를 읽어서
Ecount ERP의 웹자료올리기 팝업에 붙여넣기

참고: ecount_web_automation_v3.py
"""

import time
import pyperclip
# Import centralized config
from config import config

# ============================================================
# 설정 (V8.1: 중앙 설정 관리 도입)
# ============================================================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# ============================================================
# 메인 자동화 클래스
# ============================================================
class ErpUploadAutomation:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.erp_data = []
        self.clipboard_text = ""  # JavaScript 붙여넣기용 데이터
        
        # 로그 파일 설정 (config 사용)
        log_filename = config.UPLOADER_LOGS_DIR / f"erp_upload_{time.strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = open(log_filename, 'w', encoding='utf-8')
    
    def log(self, message: str):
        """로그 출력 (콘솔 + 파일)"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        self.log_file.write(log_line + "\n")
        self.log_file.flush()
    
    # ========================================
    # Google Sheets 관련
    # ========================================
    def get_google_credentials(self):
        """OAuth 인증으로 Google 자격증명 획득"""
        creds = None
        
        # 저장된 토큰이 있으면 로드
        if config.GOOGLE_TOKEN_PATH.exists():
            with open(config.GOOGLE_TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
        
        # 토큰이 없거나 만료된 경우
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.log("🔄 토큰 갱신 중...")
                creds.refresh(Request())
            else:
                if not config.GOOGLE_CREDENTIALS_PATH.exists():
                    self.log(f"❌ credentials.json 파일이 필요합니다: {config.GOOGLE_CREDENTIALS_PATH}")
                    self.log("   Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 생성하고")
                    self.log("   credentials.json 파일을 다운로드하세요.")
                    return None
                
                self.log("🔐 Google 인증을 위해 브라우저가 열립니다...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(config.GOOGLE_CREDENTIALS_PATH), SCOPES)
                creds = flow.run_local_server(port=0)
            
            # 토큰 저장
            with open(config.GOOGLE_TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
            self.log("✅ 토큰 저장 완료")
        
        return creds
    
    def fetch_erp_sheet_data(self) -> bool:
        """ERP 시트에서 데이터 읽기"""
        try:
            self.log(f"📊 Google Sheets 연결 중...")
            
            creds = self.get_google_credentials()
            if not creds:
                return False
            
            import gspread
            gc = gspread.authorize(creds)
            spreadsheet = gc.open_by_key(config.GS_SPREADSHEET_ID)
            worksheet = spreadsheet.worksheet(config.GS_SHEET_NAME)
            
            # 모든 데이터 가져오기
            all_values = worksheet.get_all_values()
            
            if not all_values:
                self.log("ℹ️ ERP 시트에 데이터가 없습니다")
                return False
            
            self.erp_data = all_values
            self.log(f"✅ {len(self.erp_data)}행 데이터 로드 완료")
            return True
            
        except Exception as e:
            self.log(f"❌ Google Sheets 읽기 실패: {e}")
            return False
    
    def copy_to_clipboard(self) -> bool:
        """데이터를 클립보드에 복사 (+ 내부 변수에도 저장)"""
        if not self.erp_data:
            self.log("ℹ️ 복사할 데이터가 없습니다")
            return False
        
        self.log(f"📋 {len(self.erp_data)}건 데이터 클립보드 복사 중...")
        
        lines = []
        for row in self.erp_data:
            row_str = [str(cell) if cell is not None else "" for cell in row]
            lines.append("\t".join(row_str))
        
        clipboard_text = "\r\n".join(lines)
        
        # 클래스 변수에 저장 (브라우저에서 JavaScript로 사용하기 위해)
        self.clipboard_text = clipboard_text
        
        try:
            pyperclip.copy(clipboard_text)
            self.log(f"✅ 클립보드 복사 완료 (데이터 길이: {len(clipboard_text)}자)")
            return True
        except Exception as e:
            self.log(f"❌ 클립보드 복사 실패: {e}")
            return False
    
    # ========================================
    # 브라우저/Ecount 관련
    # ========================================
    def start_browser(self, headless=False):
        """브라우저 시작 - 기존 Avast/Chrome 연결 시도"""
        self.log("🌐 브라우저 연결 중...")
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        
        # 1. 먼저 Avast 브라우저 연결 시도 (V6 다운로더와 공유)
        try:
            self.log(f"   Avast 브라우저 연결 시도 (port {config.BROWSER_DEBUG_PORT})...")
            self.browser = self.playwright.chromium.connect_over_cdp(f"http://localhost:{config.BROWSER_DEBUG_PORT}")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            
            # ERP 업로드는 항상 새 탭에서 진행 (기존 탭은 다운로더가 사용 중)
            self.page = self.context.new_page()
            self.log("   ✅ Avast에 새 탭 생성 (ERP 업로드용)")
            
            self.is_connected_to_existing = True
            self.log("✅ Avast 브라우저에 연결 성공!")
            return
            
        except Exception as e:
            self.log(f"   ℹ️ Avast 연결 실패: {e}")
        
        # 2. Chrome 브라우저(port 9222) 연결 시도
        try:
            self.log("   Chrome 연결 시도 (port 9222)...")
            self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            
            if self.context.pages:
                self.page = self.context.pages[0]
                self.log("   ✅ 기존 Chrome 탭에 연결됨")
            else:
                self.page = self.context.new_page()
                self.log("   ✅ Chrome에 새 탭 생성")
            
            self.is_connected_to_existing = True
            self.log("✅ 기존 Chrome에 연결 성공!")
            return
            
        except Exception as e:
            self.log(f"   ℹ️ Chrome 연결 실패: {e}")
            self.log("   → 새 독립 Chrome 프로세스를 시작합니다...")
        
        # 2. 독립 Chrome 프로세스 시작 (스크립트 종료 후에도 유지됨)
        import subprocess
        import socket
        
        profile_path = Path("c:/Users/DSAI/ecount_automation/chrome_profile")
        profile_path.mkdir(parents=True, exist_ok=True)
        
        # 사용 가능한 포트 찾기
        debug_port = 9223
        
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        chrome_args = [
            chrome_path,
            f"--user-data-dir={profile_path}",
            f"--remote-debugging-port={debug_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank"
        ]
        
        # 독립 프로세스로 Chrome 시작 (Python 종료 후에도 살아있음)
        subprocess.Popen(
            chrome_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        
        # Chrome 시작 대기
        time.sleep(3)
        
        # CDP로 연결
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(f"http://localhost:{debug_port}")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = self.context.new_page()
            
            self.is_connected_to_existing = True  # CDP 연결이므로 스크립트 종료 시 브라우저 유지
            self.log("✅ 독립 Chrome 프로세스 시작 및 연결 완료 (스크립트 종료 후에도 유지됨)")
        except Exception as e:
            self.log(f"❌ CDP 연결 실패: {e}")
            raise
    
    def check_login_status(self) -> bool:
        """현재 페이지에서 로그인 상태 확인"""
        try:
            # ERP 페이지로 이동해서 로그인 상태 확인
            current_url = self.page.url
            
            # 이미 ERP 페이지에 있는지 확인
            if "loginab.ecount.com/ec5" in current_url or "login" not in current_url.lower():
                self.page.goto("https://loginab.ecount.com/ec5/view/erp", timeout=10000)
                time.sleep(2)
            
            # 로그인 페이지로 리다이렉트되었는지 확인
            if "login.ecount.com" in self.page.url:
                return False
            
            return True
        except:
            return False
    
    def load_session(self) -> bool:
        """세션 상태 확인 - 기존 Chrome 사용 시 별도 로드 불필요"""
        if hasattr(self, 'is_connected_to_existing') and self.is_connected_to_existing:
            self.log("🔍 기존 Chrome 로그인 상태 확인...")
            if self.check_login_status():
                self.log("✅ 기존 Chrome에서 이미 로그인됨!")
                return True
            else:
                self.log("ℹ️ 기존 Chrome이지만 로그인 필요")
                return False
        
        # 새 브라우저인 경우 기존 세션 파일 확인
        if not config.ECOUNT_SESSION_PATH.exists():
            self.log("ℹ️ 저장된 세션 없음")
            return False
        
        try:
            import json
            with open(config.ECOUNT_SESSION_PATH, 'r') as f:
                cookies = json.load(f)
            
            self.context.add_cookies(cookies)
            self.log("✅ 세션 로드 완료")
            
            # 세션 유효성 검증
            # ERP 메인 대시보드나 메뉴로의 접근 성공 여부 확인
            self.page.goto("https://loginab.ecount.com/ec5/view/erp", timeout=20000, wait_until="networkidle")
            time.sleep(3)
            
            # URL에 login이 포함되어 있다면 세션 만료로 판단
            current_url = self.page.url
            if "login.ecount.com" in current_url or "Login" in current_url:
                self.log(f"ℹ️ 세션 만료됨 (현재 URL: {current_url}), 재로그인 필요")
                return False
            
            self.log("✅ 세션 유효함")
            return True
            
        except Exception as e:
            self.log(f"⚠️ 세션 로드 실패: {e}")
            return False
    
    def save_session(self):
        """현재 세션 저장"""
        try:
            import json
            cookies = self.context.cookies()
            with open(config.ECOUNT_SESSION_PATH, 'w') as f:
                json.dump(cookies, f)
            self.log("✅ 세션 저장 완료")
        except Exception as e:
            self.log(f"⚠️ 세션 저장 실패: {e}")
    
    def login(self) -> bool:
        """이카운트 로그인"""
        try:
            self.log(f"🔐 로그인 페이지 이동: {config.ECOUNT_LOGIN_URL}")
            self.page.goto(config.ECOUNT_LOGIN_URL, timeout=60000)
            time.sleep(2)
            
            # 회사코드 입력
            self.log("   회사코드 입력...")
            self.page.locator('input[name="com_code"]').fill(config.ECOUNT_COMPANY_CODE)
            
            # 아이디 입력
            self.log("   아이디 입력...")
            self.page.locator('input[name="id"]').fill(config.ECOUNT_ID)
            
            # 비밀번호 입력
            self.log("   비밀번호 입력...")
            self.page.locator('input[name="passwd"]').fill(config.ECOUNT_PASSWORD)
            
            time.sleep(1)
            
            # 로그인 버튼 클릭
            self.log("   로그인 버튼 클릭...")
            self.page.locator('button[id="save"]').click()
            
            # 로그인 완료 대기
            self.page.wait_for_url(
                lambda url: not url.startswith('https://login.ecount.com/'), 
                timeout=15000
            )
            
            if self.page.url.startswith('https://login.ecount.com/'):
                self.log("❌ 로그인 실패")
                return False
            
            self.log("✅ 로그인 성공")
            time.sleep(5)
            self.save_session()
            return True
            
        except Exception as e:
            self.log(f"❌ 로그인 오류: {e}")
            return False
    
    def navigate_to_target_page(self, target_type='ledger') -> bool:
        """대상 페이지로 이동
        
        Args:
            target_type: 'ledger' for 구매입력, 'estimate' for 견적서입력
        """
        try:
            base_url = "https://loginab.ecount.com/ec5/view/erp?w_flag=1"
            if target_type == 'estimate':
                self.log(f"📍 견적서입력 페이지로 이동 시도...")
                target_hash = "menuType=MENUTREE_000004&menuSeq=MENUTREE_000486&groupSeq=MENUTREE_000030&prgId=E040201&depth=4"
            else:
                self.log(f"📍 구매입력 페이지로 이동 시도...")
                target_hash = "menuType=MENUTREE_000004&menuSeq=MENUTREE_000510&groupSeq=MENUTREE_000031&prgId=E040303&depth=4"
            
            # 1. 우선 메인 ERP 페이지로 이동 (세션 확인 루틴)
            if not self.page.url.startswith("https://loginab.ecount.com/ec5/view/erp"):
                self.log(f"   메인 ERP 페이지 접속: {base_url}")
                self.page.goto(base_url, timeout=30000, wait_until="networkidle")
                time.sleep(2)
            
            # 2. 로그인 페이지로 튕겼는지 확인
            if "login.ecount.com" in self.page.url:
                self.log("⚠️ 다시 로그인 페이지로 이동됨. 재로그인 시도...")
                if not self.login():
                    self.log("❌ 재로그인 실패")
                    return False
                # 로그인 후 다시 메인으로 이동
                self.page.goto(base_url, timeout=30000, wait_until="networkidle")
                time.sleep(2)

            # 3. JavaScript로 hash 변경 (Ecount의 표준 방식)
            self.log(f"   해시 변경: {target_hash}")
            js_code = f"window.location.hash = '{target_hash}';"
            self.page.evaluate(js_code)
            
            self.log("   페이지 로딩 대기 (5초)...")
            time.sleep(5)
            
            # 4. 버튼 존재 여부 확인 (최종 검증)
            if self.page.locator('#webUploader').count() == 0:
                self.log("⚠️ 버튼이 보이지 않음. 페이지를 새로고침(Reload) 합니다...")
                self.page.reload(wait_until="networkidle")
                time.sleep(3)
                self.page.evaluate(js_code) # 다시 한번 시도
                time.sleep(3)

            page_name = "견적서입력" if target_type == 'estimate' else "구매입력"
            self.log(f"✅ {page_name} 페이지 이동 완료")
            return True
        except Exception as e:
            self.log(f"❌ 페이지 이동 실패: {e}")
            return False
    
    def dismiss_all_popups(self):
        """ERP 로딩 후 나타나는 모든 알림/팝업 및 하단 만족도 조사 레이어 제거"""
        try:
            self.log("🧹 모든 알림 및 방해 레이어 제거 중...")
            
            # 1. 팝업 닫기 버튼 및 만족도 조사 레이어 닫기
            selectors = [
                '.notification-close', 
                '.ec-popup-close', 
                '.close-button',
                '.ec-base-layer .close', # 만족도 조사 등 하단 레이어 닫기 버튼
                'button.ec-base-button-close',
                '.ec-layer-close',
                '.ec-messenger-close', # 메신저 알림 닫기
                '.ec-base-layer button.close' # 하단 레이어 닫기
            ]
            for sel in selectors:
                try:
                    locs = self.page.locator(sel)
                    for i in range(locs.count()):
                        if locs.nth(i).is_visible(timeout=500):
                            locs.nth(i).click(force=True)
                            time.sleep(0.3)
                except:
                    continue

            # 2. '오늘하루그만보기' 또는 '닫기' 텍스트 버튼 클릭
            btn_texts = ["오늘하루그만보기", "확인", "닫기", "Confirm", "Close"]
            for text in btn_texts:
                try:
                    btns = self.page.locator(f'button:has-text("{text}"), a:has-text("{text}"), span:has-text("{text}")')
                    for i in range(btns.count()):
                        btn = btns.nth(i)
                        if btn.is_visible(timeout=500):
                            btn.click(force=True)
                            time.sleep(0.3)
                except:
                    continue
                    
            # 3. 만약 레이어가 여전히 보인다면 JavaScript로 강제 숨김 (만족도 조사 등)
            self.page.evaluate('''() => {
                const overlays = document.querySelectorAll('.ec-base-layer, .notification-overlay, .ec-popup-overlay');
                overlays.forEach(el => el.style.display = 'none');
            }''')
            
        except Exception as e:
            self.log(f"   (주의) 팝업 제거 중 경미한 이슈: {e}")

    def open_web_uploader(self) -> bool:
        """웹자료올리기 버튼 클릭하여 팝업 열기"""
        try:
            # 1. 방해되는 팝업 제거
            self.dismiss_all_popups()
            
            self.log("📤 '웹자료올리기' 버튼 클릭...")
            
            # 여러 셀렉터를 순차적으로 시도 (구매입력 vs 견적서입력 페이지마다 다름)
            uploader_selectors = [
                '#webUploader',  # 구매입력 페이지
                '#toolbar_toolbar_item_web_uploader button',  # 견적서입력 페이지
                'button[data-item-key="web_uploader_footer_toolbar"]',  # 견적서입력 대체
            ]
            
            uploader_button = None
            uploader_selector = None
            
            for sel in uploader_selectors:
                try:
                    btn = self.page.locator(sel).first
                    if btn.count() > 0:
                        uploader_button = btn
                        uploader_selector = sel
                        self.log(f"   ✅ 웹자료올리기 버튼 발견: {sel}")
                        break
                except:
                    continue
            
            if not uploader_button:
                debug_path = Path("c:/Users/DSAI/Desktop/매장자동화/debug_button_missing.png")
                self.page.screenshot(path=str(debug_path))
                self.log(f"   ⚠️ 버튼 감지 실패! 스크린샷 저장: {debug_path}")
                raise Exception("웹자료올리기 버튼을 찾을 수 없습니다")
            
            # 버튼이 로딩될 때까지 대기
            try:
                uploader_button.wait_for(state='attached', timeout=30000)
            except Exception as e:
                debug_path = Path("c:/Users/DSAI/Desktop/매장자동화/debug_button_missing.png")
                self.page.screenshot(path=str(debug_path))
                self.log(f"   ⚠️ 버튼 감지 실패! 스크린샷 저장: {debug_path}")
                raise e
            
            # 2. JavaScript로 강제 클릭 (오버레이 무시)
            self.log("   JS 강제 클릭 시도 (오버레이 대응)...")
            
            # 클릭 전 방해되는 알림 레이어 제거
            self.dismiss_all_popups()
            
            self.page.evaluate(f"document.querySelector('{uploader_selector}').click();")
            
            self.log("   팝업 로딩 대기 (6초)...")
            time.sleep(6)
            
            # 팝업이 실제로 열렸는지 확인 (다양한 셀렉터 및 텍스트 시도)
            popup_selectors = [
                # 팝업 제목이 "웹자료올리기"인 ui-dialog 컨테이너 (가장 확실함)
                '.ui-dialog:visible:has(span.ui-dialog-title:has-text("웹자료올리기"))',
                'div.ui-dialog:visible:has-text("웹자료올리기")',
                '.ui-dialog:visible',
                'div[data-role="pop-container"]:visible',
                '.ec-popup-container:visible',
                'iframe[name*="popup"]'
            ]
            
            popup_found = False
            for sel in popup_selectors:
                try:
                    if self.page.locator(sel).first.count() > 0:
                        popup_found = True
                        self.log(f"✅ 웹자료올리기 팝업 열림 확인 ({sel})")
                        break
                except:
                    continue
            
            # 만약 못 찾았지만 프레임이 여러 개인 경우 확인
            if not popup_found:
                frames = self.page.frames
                self.log(f"   현재 프레임 수: {len(frames)}")
                for frame in frames:
                    if "웹자료올리기" in (frame.title() or "") or "webUploader" in (frame.name or ""):
                        popup_found = True
                        self.log(f"✅ 프레임 내에서 팝업 확인됨: {frame.name}")
                        break
            
            if popup_found:
                return True
            else:
                self.log("⚠️ 팝업이 감지되지 않았습니다. 다시 한번 강제 클릭 시도...")
                uploader_button.click(force=True)
                time.sleep(5)
                
                # 재시도 로직 동일
                for sel in popup_selectors:
                    try:
                        if self.page.locator(sel).first.count() > 0:
                            self.log(f"✅ 재시도 후 팝업 열림 확인 ({sel})")
                            return True
                    except: continue
                
                # 최종 실패 시 스크린샷 저장
                debug_path = LOG_DIR / f"debug_popup_not_found_{time.strftime('%H%M%S')}.png"
                self.page.screenshot(path=str(debug_path))
                self.log(f"❌ 팝업 열기 최종 실패. 스크린샷 저장: {debug_path}")
                return False
            
        except Exception as e:
            self.log(f"❌ 웹자료올리기 버튼 클릭 실패: {e}")
            return False
    
    def paste_data_in_popup(self) -> bool:
        """팝업 내 테이블의 1행 '일자' 열에 데이터 붙여넣기"""
        try:
            self.log("📋 팝업 테이블에서 1행 '일자' 열 클릭 및 붙여넣기...")
            
            # 이 단계에서는 dismiss_all_popups를 호출하지 않습니다. 
            # (자칫 '웹자료올리기' 팝업의 닫기 버튼을 클릭하여 스스로 꺼버릴 위험이 있기 때문)
            
            # 사용자 요청 문구의 일부만 사용하여 유연하게 탐지 (띄어쓰기/개행 차이 대비)
            partial_target_text = "엑셀서식내려받기로"
            
            # 모든 보이는 팝업 중 해당 텍스트를 포함하는 것을 찾음
            target_popup = None
            try:
                popups = self.page.locator('.ui-dialog:visible')
                for i in range(popups.count()):
                    popup = popups.nth(i)
                    if partial_target_text in popup.inner_text():
                        target_popup = popup
                        self.log(f"   ✅ [매칭 성공] 팝업 {i+1}에서 키워드 발견")
                        break
            except Exception as e:
                self.log(f"   ⚠️ 팝업 탐지 중 오류: {e}")
            
            if not target_popup:
                self.log("❌ '웹자료올리기' 안내 문구가 포함된 팝업을 찾을 수 없습니다.")
                debug_path = LOG_DIR / f"debug_popup_missing_{time.strftime('%H%M%S')}.png"
                self.page.screenshot(path=str(debug_path))
                return False
                
            # 타겟 팝업 내에서 셀 탐지
            target_cell = target_popup.locator('span.grid-input-data:visible').first
            if target_cell.count() == 0:
                self.log("   ⚠️ span 셀을 찾을 수 없습니다. 이미 활성화된 input이 있는지 확인합니다...")
                target_cell = target_popup.locator('input:visible, .grid-input-data-edit input:visible').first

            if target_cell.count() == 0:
                self.log("❌ 팝업 내에서 입력 가능한 셀을 찾을 수 없습니다.")
                return False
            
            # 셀의 위치 정보 로그 기록
            box = target_cell.bounding_box()
            if box:
                self.log(f"   ✅ 타겟 발견: x={box['x']}, y={box['y']}, w={box['width']}")
            
            # 셀 클릭하여 포커스 (force=True로 간섭 무시)
            self.log("   셀 클릭 및 포커스 대기 (1.5초)...")
            target_cell.click(force=True)
            time.sleep(1.5) 
            
            # 사용자 요청대로 물리적 Ctrl+V 실행
            self.log("   🎹 물리적 Ctrl+V 붙여넣기 실행...")
            self.page.keyboard.press('Control+v')
            
            # 붙여넣기 후 대기
            self.log("   ✅ 붙여넣기 완료! 데이터 처리 대기 (10초)...")
            self.page.screenshot(path=str(LOG_DIR / f"success_paste_{time.strftime('%H%M%S')}.png"))
            time.sleep(10)
            
            # 팝업이 여전히 열려있는지 확인
            try:
                popup_still_open = self.page.locator('div.ui-dialog:visible:has-text("웹자료올리기")').first.is_visible(timeout=2000)
                if popup_still_open:
                    self.log("   ✅ 팝업이 열려있습니다. 수동 조작을 기다립니다.")
                else:
                    self.log("   ⚠️ 팝업이 닫혔습니다. 데이터가 자동 저장되었을 수 있습니다.")
            except:
                self.log("   ⚠️ 팝업 상태를 확인할 수 없습니다.")
            
            return True
            
        except Exception as e:
            self.log(f"❌ 붙여넣기 실패: {e}")
            import traceback
            traceback.print_exc()
            return False

    
    # ========================================
    # 메인 실행
    # ========================================
    def run(self, direct_data=None, auto_close=False, target_type='ledger'):
        """전체 자동화 실행
        
        Args:
            direct_data: 직접 전달할 데이터 (없으면 Google Sheets에서 읽음)
            auto_close: True면 사용자 확인 없이 종료
            target_type: 'ledger' for 구매입력, 'estimate' for 견적서입력
        """
        self.log("=" * 60)
        self.log("ERP 시트 → Ecount 업로드 자동화 시작")
        self.log("=" * 60)
        
        try:
            # 1. 데이터 준비 (직접 주입 또는 Google Sheets)
            self.log("\n[단계 0] ERP 데이터 준비")
            
            if direct_data:
                self.erp_data = direct_data
                self.log(f"✅ 전달받은 데이터 {len(self.erp_data)}행 로드 완료")
            else:
                if not self.fetch_erp_sheet_data():
                    self.log("❌ ERP 시트 데이터 읽기 실패 - 종료")
                    return
            
            # 2. 클립보드에 복사
            if not self.copy_to_clipboard():
                self.log("❌ 클립보드 복사 실패 - 종료")
                return
            
            # 3. 브라우저 시작
            self.start_browser(headless=False)
            
            # 4. 세션 로드 또는 로그인
            self.log("\n[단계 1] 로그인")
            if not self.load_session():
                if not self.login():
                    self.log("❌ 로그인 실패 - 종료")
                    return
            
            # 5. 대상 페이지로 이동
            page_name = "견적서입력" if target_type == 'estimate' else "구매입력"
            self.log(f"\n[단계 2] 대상 페이지 이동 ({page_name})")
            if not self.navigate_to_target_page(target_type=target_type):
                self.log("❌ 페이지 이동 실패 - 종료")
                return
            
            # 6. 웹자료올리기 팝업 열기
            self.log("\n[단계 3] 웹자료올리기 팝업 열기")
            if not self.open_web_uploader():
                self.log("❌ 팝업 열기 실패 - 종료")
                return
            
            # 7. 붙여넣기
            self.log("\n[단계 4] 데이터 붙여넣기")
            if not self.paste_data_in_popup():
                self.log("❌ 붙여넣기 실패 - 종료")
                return
            
            # 8. 완료
            self.log("\n" + "=" * 60)
            self.log("✅ 데이터 붙여넣기 완료!")
            
            if auto_close:
                self.log("🚀 자동 모드: 처리를 완료했습니다.")
                time.sleep(1)
            else:
                self.log("✋ 멈춤: 이후 수동으로 조작하세요.")
                self.log("   - 데이터를 확인한 후 저장(F8) 버튼을 클릭하거나 팝업을 닫으세요.")
                self.log("   - 브라우저는 세션 유지를 위해 닫지 않습니다.")
            self.log("=" * 60)
                # 서버 모드에서는 input()을 사용하지 않음 (무한 대기 방지)
                # 대신 브라우저 세션을 그대로 둠
            
            return True
            
        except KeyboardInterrupt:
            self.log("\n⚠️ 사용자가 중단했습니다.")
            return False
        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
            return False
    
    def close(self, keep_browser_open=False):
        """브라우저 종료"""
        if not keep_browser_open:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            print("🔒 브라우저 종료 완료")
        else:
            print("🔓 브라우저를 닫지 않고 유지합니다.")
            
        if self.log_file:
            self.log_file.close()


# ============================================================
# 메인 실행
# ============================================================
if __name__ == "__main__":
    automation = ErpUploadAutomation()
    try:
        automation.run()
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다.")
    finally:
        automation.close()
