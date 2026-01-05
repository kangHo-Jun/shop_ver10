"""
V8 ERP 시트 → Ecount 업로드 자동화
==================================
V8 특징:
- 로그인 로직 제거 (이미 로그인된 브라우저 사용)
- 붙여넣기 후 즉시 종료
- 상태 알림 콜백 지원
"""

import time
import pyperclip
from pathlib import Path
from playwright.sync_api import sync_playwright

# 로그 디렉토리
LOG_DIR = Path("c:/Users/DSAI/Desktop/매장자동화/logs/uploader")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 이카운트 로그인 정보
ECOUNT_CREDENTIALS = {
    'company_code': '650217',
    'username': 'zartkang',
    'password': 'dnemfosem3835!'
}
LOGIN_URL = "https://login.ecount.com/Login"

# ============================================================
# V8 자동화 클래스
# ============================================================
class ErpUploadAutomationV2:
    def __init__(self, status_callback=None):
        """
        Args:
            status_callback: 상태 알림 콜백 함수 (선택)
                             format: callback(message: str)
        """
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.erp_data = []
        self.clipboard_text = ""
        self.status_callback = status_callback
        
        # 로그 파일 설정
        log_filename = LOG_DIR / f"erp_upload_{time.strftime('%Y%m%d_%H%M%S')}.log"
        self.log_file = open(log_filename, 'w', encoding='utf-8')
    
    def log(self, message: str):
        """로그 출력 (콘솔 + 파일 + 콜백)"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        self.log_file.write(log_line + "\n")
        self.log_file.flush()
        
        # 상태 콜백 호출
        if self.status_callback:
            self.status_callback(message)
    
    def copy_to_clipboard(self) -> bool:
        """데이터를 클립보드에 복사"""
        if not self.erp_data:
            self.log("ℹ️ 복사할 데이터가 없습니다")
            return False
        
        self.log(f"📋 {len(self.erp_data)}건 데이터 클립보드 복사 중...")
        
        lines = []
        for row in self.erp_data:
            row_str = [str(cell) if cell is not None else "" for cell in row]
            lines.append("\t".join(row_str))
        
        clipboard_text = "\r\n".join(lines)
        self.clipboard_text = clipboard_text
        
        try:
            pyperclip.copy(clipboard_text)
            self.log(f"✅ 클립보드 복사 완료 (데이터 길이: {len(clipboard_text)}자)")
            return True
        except Exception as e:
            self.log(f"❌ 클립보드 복사 실패: {e}")
            return False
    
    # ========================================
    # 브라우저 연결 (V8: 로그인 없이 직접 연결)
    # ========================================
    def start_browser(self, headless=False):
        """브라우저 연결 (로그인 없이 기존 브라우저 사용)"""
        self.log("🌐 브라우저 연결 중...")
        self.playwright = sync_playwright().start()
        
        # 1. Avast 브라우저(port 9333) 연결 시도
        try:
            self.log("   Avast 브라우저 연결 시도 (port 9333)...")
            self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9333")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.page = self.context.new_page()
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
            else:
                self.page = self.context.new_page()
            
            self.log("✅ Chrome 브라우저에 연결 성공!")
            return
        except Exception as e:
            self.log(f"   ℹ️ Chrome 연결 실패: {e}")
        
        # 3. 새 Chrome 시작
        import subprocess
        profile_path = Path("c:/Users/DSAI/ecount_automation/chrome_profile")
        profile_path.mkdir(parents=True, exist_ok=True)
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
        
        subprocess.Popen(
            chrome_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        time.sleep(3)
        
        self.browser = self.playwright.chromium.connect_over_cdp(f"http://localhost:{debug_port}")
        self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        
        self.log("✅ 새 Chrome 프로세스 시작 및 연결 완료")
    
    def login(self) -> bool:
        """이카운트 자동 로그인"""
        try:
            self.log(f"🔐 로그인 페이지 이동: {LOGIN_URL}")
            self.page.goto(LOGIN_URL, timeout=60000)
            time.sleep(2)
            
            # 회사코드 입력
            self.log("   회사코드 입력...")
            self.page.locator('input[name="com_code"]').fill(ECOUNT_CREDENTIALS['company_code'])
            
            # 아이디 입력
            self.log("   아이디 입력...")
            self.page.locator('input[name="id"]').fill(ECOUNT_CREDENTIALS['username'])
            
            # 비밀번호 입력
            self.log("   비밀번호 입력...")
            self.page.locator('input[name="passwd"]').fill(ECOUNT_CREDENTIALS['password'])
            
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
            time.sleep(3)
            return True
            
        except Exception as e:
            self.log(f"❌ 로그인 오류: {e}")
            return False
    
    def navigate_to_target_page(self, target_type='ledger') -> bool:
        """대상 페이지로 이동 (V8: 로그인 안됐으면 수동 로그인 대기)"""
        try:
            base_url = "https://loginab.ecount.com/ec5/view/erp?w_flag=1"
            if target_type == 'estimate':
                self.log(f"📍 견적서입력 페이지로 이동 시도...")
                target_hash = "menuType=MENUTREE_000004&menuSeq=MENUTREE_000486&groupSeq=MENUTREE_000030&prgId=E040201&depth=4"
            else:
                self.log(f"📍 구매입력 페이지로 이동 시도...")
                target_hash = "menuType=MENUTREE_000004&menuSeq=MENUTREE_000510&groupSeq=MENUTREE_000031&prgId=E040303&depth=4"
            
            # 바로 페이지 이동
            full_url = f"{base_url}#{target_hash}"
            self.page.goto(full_url, timeout=30000, wait_until="networkidle")
            time.sleep(3)
            
            # 로그인 페이지로 리다이렉트되었는지 확인
            if "login.ecount.com" in self.page.url:
                self.log("⚠️ 로그인이 필요합니다. 자동 로그인 시도...")
                
                # 자동 로그인 수행
                if not self.login():
                    self.log("❌ 자동 로그인 실패. 종료합니다.")
                    return False
                
                # 로그인 후 다시 대상 페이지로 이동
                self.log(f"   대상 페이지로 다시 이동...")
                self.page.goto(full_url, timeout=30000, wait_until="networkidle")
                time.sleep(3)
            
            # 버튼 존재 여부 확인
            if self.page.locator('#webUploader').count() == 0:
                self.log("   버튼이 보이지 않음. 페이지 새로고침...")
                self.page.reload(wait_until="networkidle")
                time.sleep(3)
            
            page_name = "견적서입력" if target_type == 'estimate' else "구매입력"
            self.log(f"✅ {page_name} 페이지 이동 완료")
            return True
        except Exception as e:
            self.log(f"❌ 페이지 이동 실패: {e}")
            return False
    
    def open_web_uploader(self) -> bool:
        """웹자료올리기 버튼 클릭하여 팝업 열기"""
        try:
            self.log("📤 '웹자료올리기' 버튼 클릭...")
            
            uploader_selectors = [
                '#webUploader',
                '#toolbar_toolbar_item_web_uploader button',
                'button[data-item-key="web_uploader_footer_toolbar"]',
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
                self.log("❌ 웹자료올리기 버튼을 찾을 수 없습니다")
                return False
            
            # JavaScript로 클릭
            self.page.evaluate(f"document.querySelector('{uploader_selector}').click();")
            
            self.log("   팝업 로딩 대기 (5초)...")
            time.sleep(5)
            
            # 팝업 열림 확인
            popup_selectors = [
                '.ui-dialog:visible:has(span.ui-dialog-title:has-text("웹자료올리기"))',
                'div.ui-dialog:visible:has-text("웹자료올리기")',
                '.ui-dialog:visible',
            ]
            
            for sel in popup_selectors:
                try:
                    if self.page.locator(sel).first.count() > 0:
                        self.log(f"✅ 웹자료올리기 팝업 열림 확인")
                        return True
                except:
                    continue
            
            self.log("⚠️ 팝업 감지 실패, 재시도...")
            uploader_button.click(force=True)
            time.sleep(3)
            
            return True
            
        except Exception as e:
            self.log(f"❌ 웹자료올리기 버튼 클릭 실패: {e}")
            return False
    
    def paste_data_in_popup(self) -> bool:
        """팝업 내 테이블에 데이터 붙여넣기"""
        try:
            self.log("📋 팝업에 데이터 붙여넣기 중...")
            
            partial_target_text = "엑셀서식내려받기로"
            
            target_popup = None
            popups = self.page.locator('.ui-dialog:visible')
            for i in range(popups.count()):
                popup = popups.nth(i)
                if partial_target_text in popup.inner_text():
                    target_popup = popup
                    self.log(f"   ✅ [매칭 성공] 팝업 {i+1}에서 키워드 발견")
                    break
            
            if not target_popup:
                self.log("❌ '웹자료올리기' 팝업을 찾을 수 없습니다.")
                return False
            
            # 셀 탐지 및 클릭
            target_cell = target_popup.locator('span.grid-input-data:visible').first
            if target_cell.count() == 0:
                target_cell = target_popup.locator('input:visible').first
            
            if target_cell.count() == 0:
                self.log("❌ 입력 가능한 셀을 찾을 수 없습니다.")
                return False
            
            # 클릭 및 붙여넣기
            self.log("   셀 클릭 및 포커스 대기...")
            target_cell.click(force=True)
            time.sleep(1.5)
            
            self.log("   🎹 Ctrl+V 붙여넣기 실행...")
            self.page.keyboard.press('Control+v')
            
            # 스크린샷 저장
            screenshot_path = LOG_DIR / f"success_paste_{time.strftime('%H%M%S')}.png"
            self.page.screenshot(path=str(screenshot_path))
            self.log(f"   📸 스크린샷 저장: {screenshot_path}")
            
            return True
            
        except Exception as e:
            self.log(f"❌ 붙여넣기 실패: {e}")
            return False
    
    # ========================================
    # V8 메인 실행 (간소화)
    # ========================================
    def run(self, direct_data=None, target_type='ledger'):
        """전체 자동화 실행 (V8: 붙여넣기 후 즉시 종료)
        
        Args:
            direct_data: 직접 전달할 데이터
            target_type: 'ledger' for 구매입력, 'estimate' for 견적서입력
        
        Returns:
            bool: 성공 여부
        """
        page_name = "견적서입력" if target_type == 'estimate' else "구매입력"
        
        self.log("=" * 60)
        self.log(f"V8 ERP 업로드 자동화 시작 ({page_name})")
        self.log("=" * 60)
        
        try:
            # 1. 데이터 준비
            self.log(f"\n📊 데이터 준비 중...")
            if direct_data:
                self.erp_data = direct_data
                self.log(f"   ✅ {len(self.erp_data)}행 데이터 로드 완료")
            else:
                self.log("❌ 데이터가 없습니다")
                return False
            
            # 2. 클립보드에 복사
            if not self.copy_to_clipboard():
                return False
            
            # 3. 브라우저 연결 (로그인 없음)
            self.start_browser()
            
            # 4. 대상 페이지로 이동 (로그인 체크 없음)
            self.log(f"\n📍 {page_name} 페이지로 이동...")
            if not self.navigate_to_target_page(target_type=target_type):
                return False
            
            # 5. 웹자료올리기 팝업 열기
            self.log("\n📤 웹자료올리기 팝업 열기...")
            if not self.open_web_uploader():
                return False
            
            # 6. 붙여넣기
            self.log("\n📋 데이터 붙여넣기...")
            if not self.paste_data_in_popup():
                return False
            
            # 7. V8 핵심: 즉시 종료 메시지
            self.log("\n" + "=" * 60)
            self.log("✅ 데이터 붙여넣기 완료!")
            self.log("=" * 60)
            self.log("")
            self.log("📝 다음 단계:")
            self.log("   1. 데이터를 확인하세요")
            self.log("   2. 필요시 수동으로 수정하세요")
            self.log("   3. 저장(F8) 버튼을 클릭하세요")
            self.log("")
            self.log("🏁 프로그램을 종료합니다. 브라우저는 그대로 유지됩니다.")
            self.log("=" * 60)
            
            return True
            
        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
            return False
        finally:
            # 브라우저는 닫지 않음 (사용자가 계속 사용)
            if self.log_file:
                self.log_file.close()
            if self.playwright:
                self.playwright.stop()


# ============================================================
# 메인 실행
# ============================================================
if __name__ == "__main__":
    automation = ErpUploadAutomationV2()
    automation.run()
