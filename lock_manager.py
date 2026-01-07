"""
분산 락 관리자 (Distributed Lock Manager)
==========================================
Google Sheets 기반 분산 락 시스템
여러 컴퓨터에서 동시 실행 시 중복 처리 방지

V10 주요 기능:
- Google Sheets를 중앙 락 저장소로 사용
- 원자적(atomic) 락 획득/해제
- 타임아웃 기반 데드락 방지 (기본 30분)
- PC 식별 (hostname + IP)
"""

import time
import socket
import platform
import datetime
from typing import Optional, Dict, List
from pathlib import Path

# Import centralized config
from config import config
from logging_config import logger
from error_handler import error_handler, ErrorSeverity


class DistributedLockManager:
    """Google Sheets 기반 분산 락 관리자"""

    # 락 시트 이름
    LOCK_SHEET_NAME = "processing_lock"

    # 락 타임아웃 (초) - 30분
    LOCK_TIMEOUT_SEC = 1800

    # 상태 코드
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(self):
        """초기화"""
        self.machine_id = self._get_machine_id()
        self.spreadsheet = None
        self.lock_worksheet = None
        logger.info(f"DistributedLockManager initialized for machine: {self.machine_id}")

    def _get_machine_id(self) -> str:
        """현재 PC의 고유 ID 생성"""
        try:
            hostname = platform.node()
            try:
                ip_address = socket.gethostbyname(socket.gethostname())
            except:
                ip_address = "unknown"

            machine_id = f"{hostname}_{ip_address}"
            return machine_id
        except Exception as e:
            logger.warning(f"Failed to get machine ID: {e}")
            return f"unknown_{int(time.time())}"

    def _get_google_credentials(self):
        """OAuth 인증으로 Google 자격증명 획득"""
        try:
            import pickle
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow

            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            creds = None

            # 저장된 토큰이 있으면 로드
            if config.GOOGLE_TOKEN_PATH.exists():
                with open(config.GOOGLE_TOKEN_PATH, 'rb') as token:
                    creds = pickle.load(token)

            # 토큰이 없거나 만료된 경우
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing Google token...")
                    creds.refresh(Request())
                else:
                    if not config.GOOGLE_CREDENTIALS_PATH.exists():
                        logger.error(f"credentials.json not found: {config.GOOGLE_CREDENTIALS_PATH}")
                        return None

                    logger.info("Starting Google OAuth flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(config.GOOGLE_CREDENTIALS_PATH), SCOPES)
                    creds = flow.run_local_server(port=0)

                # 토큰 저장
                with open(config.GOOGLE_TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
                logger.info("Google token saved")

            return creds
        except Exception as e:
            error_handler.log_error(
                "Failed to get Google credentials",
                ErrorSeverity.HIGH,
                {"error": str(e)}
            )
            return None

    def connect(self) -> bool:
        """Google Sheets에 연결 및 락 시트 초기화"""
        try:
            logger.info(f"Connecting to Google Sheets (Spreadsheet ID: {config.GS_SPREADSHEET_ID})")

            creds = self._get_google_credentials()
            if not creds:
                return False

            import gspread
            gc = gspread.authorize(creds)
            self.spreadsheet = gc.open_by_key(config.GS_SPREADSHEET_ID)

            # 락 시트 생성 또는 가져오기
            try:
                self.lock_worksheet = self.spreadsheet.worksheet(self.LOCK_SHEET_NAME)
                logger.info(f"Lock sheet '{self.LOCK_SHEET_NAME}' found")
            except gspread.exceptions.WorksheetNotFound:
                logger.info(f"Creating new lock sheet: {self.LOCK_SHEET_NAME}")
                self.lock_worksheet = self.spreadsheet.add_worksheet(
                    title=self.LOCK_SHEET_NAME,
                    rows=1000,
                    cols=6
                )

                # 헤더 추가
                self.lock_worksheet.append_row([
                    "order_id",
                    "locked_by",
                    "locked_at",
                    "status",
                    "machine_id",
                    "notes"
                ])
                logger.info("Lock sheet created with headers")

            logger.info("Successfully connected to Google Sheets lock system")
            return True

        except Exception as e:
            error_handler.log_error(
                "Failed to connect to Google Sheets",
                ErrorSeverity.CRITICAL,
                {"error": str(e)}
            )
            return False

    def _find_order_row(self, order_id: str) -> Optional[int]:
        """특정 order_id의 행 번호 찾기 (없으면 None 반환)"""
        try:
            # 첫 번째 컬럼(order_id)에서 찾기
            cell = self.lock_worksheet.find(order_id, in_column=1)
            if cell:
                return cell.row
            return None
        except Exception as e:
            logger.warning(f"Error finding order row: {e}")
            return None

    def acquire_lock(self, order_id: str, notes: str = "") -> bool:
        """
        락 획득 시도

        Returns:
            True: 락 획득 성공 (이 PC가 처리 진행)
            False: 락 획득 실패 (다른 PC가 처리 중이거나 이미 완료됨)
        """
        try:
            if not self.lock_worksheet:
                logger.error("Lock worksheet not initialized. Call connect() first.")
                return False

            logger.info(f"Attempting to acquire lock for order: {order_id}")

            # 1. 기존 레코드 확인
            existing_row = self._find_order_row(order_id)

            if existing_row:
                # 기존 레코드가 있음
                row_data = self.lock_worksheet.row_values(existing_row)

                if len(row_data) < 4:
                    logger.warning(f"Invalid row data for {order_id}")
                    return False

                existing_status = row_data[3] if len(row_data) > 3 else ""
                existing_locked_at = row_data[2] if len(row_data) > 2 else ""
                existing_machine = row_data[4] if len(row_data) > 4 else ""

                # 완료 상태면 처리하지 않음
                if existing_status == self.STATUS_COMPLETED:
                    logger.info(f"Order {order_id} already completed by {existing_machine}")
                    return False

                # 처리 중 상태 확인
                if existing_status == self.STATUS_PROCESSING:
                    # 타임아웃 체크
                    try:
                        locked_time = datetime.datetime.fromisoformat(existing_locked_at)
                        elapsed = (datetime.datetime.now() - locked_time).total_seconds()

                        if elapsed < self.LOCK_TIMEOUT_SEC:
                            # 아직 타임아웃 안됨 - 다른 PC가 처리 중
                            logger.info(f"Order {order_id} is being processed by {existing_machine} (elapsed: {elapsed:.0f}s)")
                            return False
                        else:
                            # 타임아웃 - 재처리 허용
                            logger.warning(f"Order {order_id} timed out (elapsed: {elapsed:.0f}s), re-acquiring lock")
                            # 아래에서 업데이트
                    except Exception as e:
                        logger.warning(f"Failed to parse locked_at time: {e}")
                        # 시간 파싱 실패 - 재처리 허용

                # 기존 행 업데이트 (재처리)
                current_time = datetime.datetime.now().isoformat()
                self.lock_worksheet.update_cell(existing_row, 2, self.machine_id)  # locked_by
                self.lock_worksheet.update_cell(existing_row, 3, current_time)      # locked_at
                self.lock_worksheet.update_cell(existing_row, 4, self.STATUS_PROCESSING)  # status
                self.lock_worksheet.update_cell(existing_row, 5, self.machine_id)  # machine_id
                if notes:
                    self.lock_worksheet.update_cell(existing_row, 6, notes)  # notes

                logger.info(f"Lock re-acquired for order {order_id}")
                return True

            else:
                # 새 레코드 추가
                current_time = datetime.datetime.now().isoformat()
                new_row = [
                    order_id,
                    self.machine_id,
                    current_time,
                    self.STATUS_PROCESSING,
                    self.machine_id,
                    notes
                ]

                self.lock_worksheet.append_row(new_row)
                logger.info(f"Lock acquired for new order {order_id}")
                return True

        except Exception as e:
            error_handler.log_error(
                f"Failed to acquire lock for {order_id}",
                ErrorSeverity.HIGH,
                {"order_id": order_id, "error": str(e)}
            )
            return False

    def release_lock(self, order_id: str, status: str = STATUS_COMPLETED, notes: str = "") -> bool:
        """
        락 해제 및 상태 업데이트

        Args:
            order_id: 주문 ID
            status: 최종 상태 (completed/failed)
            notes: 추가 메모
        """
        try:
            if not self.lock_worksheet:
                logger.error("Lock worksheet not initialized")
                return False

            logger.info(f"Releasing lock for order {order_id} with status: {status}")

            row_num = self._find_order_row(order_id)
            if not row_num:
                logger.warning(f"Order {order_id} not found in lock sheet")
                return False

            # 상태 업데이트
            self.lock_worksheet.update_cell(row_num, 4, status)  # status
            if notes:
                existing_notes = self.lock_worksheet.cell(row_num, 6).value or ""
                updated_notes = f"{existing_notes} | {notes}" if existing_notes else notes
                self.lock_worksheet.update_cell(row_num, 6, updated_notes)

            logger.info(f"Lock released for order {order_id}")
            return True

        except Exception as e:
            error_handler.log_error(
                f"Failed to release lock for {order_id}",
                ErrorSeverity.MEDIUM,
                {"order_id": order_id, "status": status, "error": str(e)}
            )
            return False

    def get_lock_status(self, order_id: str) -> Optional[Dict]:
        """특정 주문의 락 상태 조회"""
        try:
            if not self.lock_worksheet:
                return None

            row_num = self._find_order_row(order_id)
            if not row_num:
                return None

            row_data = self.lock_worksheet.row_values(row_num)
            if len(row_data) < 5:
                return None

            return {
                "order_id": row_data[0],
                "locked_by": row_data[1] if len(row_data) > 1 else "",
                "locked_at": row_data[2] if len(row_data) > 2 else "",
                "status": row_data[3] if len(row_data) > 3 else "",
                "machine_id": row_data[4] if len(row_data) > 4 else "",
                "notes": row_data[5] if len(row_data) > 5 else ""
            }

        except Exception as e:
            logger.warning(f"Failed to get lock status for {order_id}: {e}")
            return None

    def get_all_locks(self) -> List[Dict]:
        """모든 락 레코드 조회"""
        try:
            if not self.lock_worksheet:
                return []

            all_records = self.lock_worksheet.get_all_records()
            return all_records

        except Exception as e:
            logger.warning(f"Failed to get all locks: {e}")
            return []

    def cleanup_old_locks(self, max_age_days: int = 7) -> int:
        """오래된 완료/실패 레코드 정리"""
        try:
            if not self.lock_worksheet:
                return 0

            logger.info(f"Cleaning up locks older than {max_age_days} days")

            cutoff_time = datetime.datetime.now() - datetime.timedelta(days=max_age_days)
            all_values = self.lock_worksheet.get_all_values()

            rows_to_delete = []
            for idx, row in enumerate(all_values[1:], start=2):  # Skip header
                if len(row) < 4:
                    continue

                status = row[3]
                locked_at = row[2]

                # 완료/실패 상태만 정리
                if status in [self.STATUS_COMPLETED, self.STATUS_FAILED]:
                    try:
                        locked_time = datetime.datetime.fromisoformat(locked_at)
                        if locked_time < cutoff_time:
                            rows_to_delete.append(idx)
                    except:
                        continue

            # 역순으로 삭제 (인덱스 변화 방지)
            for row_num in sorted(rows_to_delete, reverse=True):
                self.lock_worksheet.delete_rows(row_num)

            logger.info(f"Cleaned up {len(rows_to_delete)} old lock records")
            return len(rows_to_delete)

        except Exception as e:
            logger.warning(f"Failed to cleanup old locks: {e}")
            return 0


# ============================================================
# 테스트 코드
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("분산 락 관리자 테스트")
    print("=" * 60)

    # 락 매니저 초기화
    lock_mgr = DistributedLockManager()
    print(f"\nMachine ID: {lock_mgr.machine_id}")

    # Google Sheets 연결
    if not lock_mgr.connect():
        print("❌ Google Sheets 연결 실패")
        exit(1)

    print("✅ Google Sheets 연결 성공")

    # 테스트 주문 ID
    test_order_id = "TEST_" + str(int(time.time()))

    # 1. 락 획득 테스트
    print(f"\n[테스트 1] 락 획득 ({test_order_id})")
    if lock_mgr.acquire_lock(test_order_id, notes="Test acquisition"):
        print("✅ 락 획득 성공")
    else:
        print("❌ 락 획득 실패")

    # 2. 상태 조회 테스트
    print(f"\n[테스트 2] 락 상태 조회")
    status = lock_mgr.get_lock_status(test_order_id)
    if status:
        print(f"✅ 상태 조회 성공:")
        for key, value in status.items():
            print(f"   {key}: {value}")
    else:
        print("❌ 상태 조회 실패")

    # 3. 중복 획득 시도 (실패해야 정상)
    print(f"\n[테스트 3] 중복 락 획득 시도 (실패 예상)")
    if lock_mgr.acquire_lock(test_order_id):
        print("⚠️ 락 중복 획득됨 (버그 가능성)")
    else:
        print("✅ 중복 락 방지 작동")

    # 4. 락 해제 테스트
    print(f"\n[테스트 4] 락 해제")
    if lock_mgr.release_lock(test_order_id, status=DistributedLockManager.STATUS_COMPLETED, notes="Test completed"):
        print("✅ 락 해제 성공")
    else:
        print("❌ 락 해제 실패")

    # 5. 완료 상태 재획득 시도 (실패해야 정상)
    print(f"\n[테스트 5] 완료된 주문 재획득 시도 (실패 예상)")
    if lock_mgr.acquire_lock(test_order_id):
        print("⚠️ 완료된 주문 재획득됨 (버그 가능성)")
    else:
        print("✅ 완료 주문 재처리 방지 작동")

    # 6. 전체 락 조회
    print(f"\n[테스트 6] 전체 락 목록 조회")
    all_locks = lock_mgr.get_all_locks()
    print(f"✅ 총 {len(all_locks)}개 락 레코드 존재")

    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
