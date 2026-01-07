# 영림 발주서 자동화 V10 - Distributed Lock Edition

## 🚀 V10 주요 개선사항

### 분산 락 시스템 (Multi-Machine Support)
**문제**: V8.1까지는 여러 컴퓨터에서 동시 실행 시 같은 주문을 중복 처리하는 문제가 있었습니다.

**해결**: Google Sheets 기반 분산 락 시스템 도입
- ✅ 여러 컴퓨터에서 동시 실행 가능
- ✅ 중복 처리 자동 방지
- ✅ 실시간 락 상태 동기화
- ✅ 타임아웃 기반 데드락 방지 (기본 30분)

---

## 📋 시스템 구조

### V10 아키텍처

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PC-A      │     │   PC-B      │     │   PC-C      │
│  V10 Server │     │  V10 Server │     │  V10 Server │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────┬───────┴───────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  Google Sheets  │
         │ processing_lock │  ← 중앙 락 저장소
         └─────────────────┘
```

### 처리 흐름

```
1️⃣ 주문 발견
   ↓
2️⃣ Google Sheets에서 락 획득 시도
   ├─ ✅ 성공 → 처리 진행
   └─ ❌ 실패 → 스킵 (다른 PC가 처리 중)
   ↓
3️⃣ 다운로드 & 파싱
   ↓
4️⃣ ERP 업로드
   ↓
5️⃣ 락 상태를 'completed'로 업데이트
```

---

## 🛠️ 설치 및 실행

### 1. 환경 설정

```bash
# 1단계: 가상환경 설정 (최초 1회)
setup_env.bat

# 2단계: .env 파일 수정
copy .env.v10.example .env
notepad .env
```

### 2. Google Sheets 락 시트 생성

V10 서버를 처음 실행하면 자동으로 `processing_lock` 시트가 생성됩니다.

**수동 생성 시**:
1. Google Sheets에 새 시트 추가: `processing_lock`
2. 헤더 행 추가:
   ```
   order_id | locked_by | locked_at | status | machine_id | notes
   ```

### 3. 서버 실행

```bash
run_v10_server.bat
```

**또는 Python 직접 실행**:
```bash
.venv\Scripts\activate
python v10_auto_server.py
```

### 4. 웹 대시보드 접속

브라우저에서 접속:
```
http://localhost:5080
```

---

## 📊 락 시스템 작동 방식

### 락 레코드 구조

| order_id   | locked_by      | locked_at           | status      | machine_id    | notes                    |
|------------|----------------|---------------------|-------------|---------------|--------------------------|
| 2601050229 | PC-A_192.168.1.100 | 2026-01-07 10:30:00 | processing  | DESKTOP-ABC   | Download attempt from ledger |
| 2601050194 | PC-B_192.168.1.101 | 2026-01-07 10:31:00 | completed   | LAPTOP-XYZ    | Download successful      |

### 락 상태 코드

- **processing**: 현재 처리 중
- **completed**: 처리 완료 (재처리 불가)
- **failed**: 처리 실패 (재시도 가능)

### 타임아웃 메커니즘

- 기본 타임아웃: **30분** (설정 가능)
- `processing` 상태가 30분 이상 지속되면 다른 PC가 재처리 가능
- 데드락 방지 및 장애 복구 기능

---

## 🔧 주요 파일 및 역할

### V10 신규 파일

| 파일 | 역할 |
|------|------|
| [lock_manager.py](lock_manager.py) | 분산 락 관리자 (핵심 모듈) |
| [v10_auto_server.py](v10_auto_server.py) | V10 메인 서버 (락 통합) |
| [run_v10_server.bat](run_v10_server.bat) | V10 실행 스크립트 |
| [.env.v10.example](.env.v10.example) | V10 환경 변수 템플릿 |
| v10_history.json | V10 로컬 히스토리 파일 |

### 기존 파일 (재사용)

| 파일 | 역할 |
|------|------|
| [config.py](config.py) | 설정 관리 (V10 설정 추가) |
| [local_file_processor.py](local_file_processor.py) | HTML 파싱 |
| [erp_upload_automation_v2.py](erp_upload_automation_v2.py) | ERP 업로드 (v1과 동일) |
| [logging_config.py](logging_config.py) | 로깅 설정 |
| [error_handler.py](error_handler.py) | 에러 관리 |

---

## ⚙️ 설정 옵션

### .env 파일 주요 설정

```bash
# 분산 락 활성화/비활성화
ENABLE_DISTRIBUTED_LOCK=true

# 락 타임아웃 (초) - 기본 30분
LOCK_TIMEOUT_SEC=1800

# 락 시트 이름
LOCK_SHEET_NAME=processing_lock

# 히스토리 파일 (V10 전용)
HISTORY_FILE=v10_history.json
```

---

## 🧪 테스트

### 분산 락 단독 테스트

```bash
.venv\Scripts\activate
python lock_manager.py
```

**테스트 항목**:
- ✅ Google Sheets 연결
- ✅ 락 획득/해제
- ✅ 중복 락 방지
- ✅ 완료 주문 재처리 방지

### 다중 PC 시뮬레이션

1. PC-A에서 V10 서버 실행
2. PC-B에서 V10 서버 실행
3. 동일한 주문이 하나의 PC에서만 처리되는지 확인

---

## 🔍 모니터링

### 웹 대시보드

V10 대시보드에는 다음 정보가 표시됩니다:

- **Distributed Lock Manager 상태**
  - ✅ Connected / ❌ Disconnected
  - Machine ID (현재 PC 식별자)
- **Auto Downloader 상태**
- **Pending/History 통계**

### 로그 확인

```bash
# 메인 로그
logs/app_YYYYMMDD.json

# 업로더 로그
logs/uploader/erp_upload_*.log

# 중요 에러
logs/critical_errors.json
```

### Google Sheets 직접 확인

1. Google Sheets 열기
2. `processing_lock` 시트 확인
3. 실시간 락 상태 확인

---

## 🚨 문제 해결

### 1. "Lock manager not connected" 경고

**원인**: Google Sheets 연결 실패

**해결**:
1. `google_oauth_credentials.json` 파일 확인
2. Google Sheets API 활성화 확인
3. 인터넷 연결 확인

**임시 대응**: 분산 락 없이 실행 (단일 PC만 사용)
```bash
ENABLE_DISTRIBUTED_LOCK=false
```

### 2. 주문이 계속 "processing" 상태로 남아있음

**원인**: PC가 처리 중 종료되어 락이 해제되지 않음

**해결**:
- 자동: 30분 타임아웃 후 다른 PC가 재처리
- 수동: Google Sheets에서 해당 행의 `status`를 `failed`로 변경

### 3. 같은 주문이 여러 PC에서 중복 처리됨

**원인**: 분산 락이 비활성화되어 있음

**해결**:
```bash
# .env 파일 확인
ENABLE_DISTRIBUTED_LOCK=true
```

### 4. 락 시트가 너무 커짐

**해결**: 자동 정리 기능 사용
```python
# Python 콘솔에서 실행
from lock_manager import DistributedLockManager
lock_mgr = DistributedLockManager()
lock_mgr.connect()
lock_mgr.cleanup_old_locks(max_age_days=7)  # 7일 이상된 완료/실패 레코드 삭제
```

---

## 📈 V8.1 대비 개선 사항

| 항목 | V8.1 | V10 |
|------|------|-----|
| **다중 PC 지원** | ❌ 중복 처리 | ✅ 분산 락으로 방지 |
| **중복 방지** | 로컬 JSON만 | Google Sheets 중앙화 |
| **PC 식별** | 없음 | Machine ID 자동 생성 |
| **데드락 방지** | 없음 | 30분 타임아웃 |
| **실시간 모니터링** | 로컬만 | 모든 PC 상태 확인 가능 |
| **히스토리 파일** | v8_history.json | v10_history.json (분리) |

---

## 🔐 보안 고려사항

### 중요 파일 (절대 공유 금지)

- `.env` - 계정 정보 포함
- `google_oauth_credentials.json` - Google API 자격증명
- `google_token.pickle` - Google 액세스 토큰
- `ecount_session.json` - ERP 세션 정보
- `v10_history.json` - 처리 이력

### 권장 사항

1. `.gitignore`에 민감 파일 추가
2. Google Sheets 공유 권한 최소화
3. `.env` 파일 암호화 저장 권장

---

## 🆚 V8.1 vs V10 비교

### 언제 V8.1을 사용할까?

- ✅ **단일 PC**에서만 실행
- ✅ 네트워크 지연에 민감한 환경
- ✅ Google Sheets 접근 불가

### 언제 V10을 사용할까?

- ✅ **여러 PC**에서 동시 실행
- ✅ 중복 처리 방지 필수
- ✅ 중앙화된 모니터링 필요
- ✅ 장애 복구 기능 필요

---

## 📞 기술 지원

### 로그 수집

문제 발생 시 다음 파일을 첨부해주세요:

```
logs/app_YYYYMMDD.json
logs/critical_errors.json
logs/uploader/erp_upload_*.log
```

### 개발 정보

- **Version**: V10.0
- **Release Date**: 2026-01-07
- **Developer**: Antigravity AI
- **License**: Proprietary

---

## 🎯 다음 버전 계획 (V11)

- [ ] PostgreSQL/MySQL 기반 락 시스템 (더 빠른 성능)
- [ ] Redis 캐시 도입
- [ ] 웹 UI 개선 (실시간 락 상태 그래프)
- [ ] 모바일 앱 (알림 및 원격 제어)
- [ ] AI 기반 에러 자동 복구

---

**V10 Distributed Lock Edition** - 여러 컴퓨터에서 안전하게 실행하세요! 🚀
