# 🛒 영림 발주서 자동화 시스템 V8

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Web%20UI-green.svg)](https://flask.palletsprojects.com/)
[![Playwright](https://img.shields.io/badge/Playwright-Browser%20Automation-orange.svg)](https://playwright.dev/)

영림 발주서(HTML/MHTML)를 자동으로 다운로드하고 이카운트(Ecount) ERP에 업로드하는 **하이브리드 웹 자동화 시스템**입니다.

---

## ✨ V8 주요 기능

### 🚀 핵심 개선 사항
- **로그인 프리(Login-Free)**: 기존 브라우저 세션 재사용으로 로그인 과정 생략
- **자동 종료**: 데이터 붙여넣기 후 즉시 종료하여 사용자가 바로 F8로 저장 가능
- **실시간 상태 알림**: 웹 UI에서 다운로드/업로드 진행 상황 실시간 모니터링

### 📦 주요 기능
- **Auto-Downloader**: 30분 간격으로 영림 사이트 자동 감시 및 신규 주문 수집
- **지능형 파싱**: HTML/MHTML 파일에서 품목 코드 자동 생성 (GAS 로직 완전 이식)
- **원장/견적 지원**: 구매입력(원장) 및 견적서입력 모두 지원
- **중복 방지**: 처리된 주문 자동 기록으로 중복 업로드 원천 차단
- **웹 UI 제어**: 브라우저에서 버튼 클릭만으로 모든 작업 제어

---

## 🖥️ 시스템 요구사항

- **OS**: Windows 10/11
- **Python**: 3.8 이상
- **브라우저**: Avast Browser (자동 설치)
- **네트워크**: 영림 사이트 및 이카운트 ERP 접속 가능

---

## 📥 설치 방법

### 1. 저장소 클론
```powershell
git clone https://github.com/kangHo-Jun/Shop_Automation.git
cd Shop_Automation
```

### 2. Python 가상환경 생성
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. 패키지 설치
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 4. 설정 파일 준비
- `google_oauth_credentials.json`: Google Sheets API 인증 정보 (선택사항)
- 브라우저 프로필은 자동 생성됨 (`avast_automation_profile/`)

---

## 🚀 사용 방법

### 서버 실행
```powershell
run_v8_server.bat
```
또는
```powershell
.venv\Scripts\python.exe v8_auto_server.py
```

### 웹 UI 접속
브라우저에서 `http://localhost:5080` 접속

### 작업 흐름
1. **자동 다운로드**: Auto-Downloader가 30분마다 신규 주문 자동 수집
2. **업로드 실행**: 웹 UI에서 `Upload Ledger` 또는 `Upload Estimate` 버튼 클릭
3. **최종 저장**: ERP 화면에서 데이터 확인 후 `F8` 키로 저장

---

## 📂 프로젝트 구조

```
Shop_Automation/
├── v8_auto_server.py              # 메인 제어 서버 (Flask)
├── local_file_processor.py        # HTML 파싱 및 품목 코드 생성
├── erp_upload_automation_v1.py    # ERP 브라우저 자동화
├── erp_upload_automation_v2.py    # ERP 업로드 (대체 버전)
├── login_door_yl.py               # 영림 사이트 로그인
├── run_v8_server.bat              # 서버 실행 스크립트
├── requirements.txt               # Python 패키지 목록
├── .gitignore                     # Git 제외 파일
│
├── GAS_Source/                    # Google Apps Script 원본
│   └── code_generation.gs
│
├── data/                          # 데이터 저장 (Git 제외)
│   └── downloads/                 # 다운로드된 주문서
│
├── logs/                          # 로그 파일 (Git 제외)
│
├── docs/                          # 문서
│   ├── INSTALL_GUIDE.md
│   ├── USER_MANUAL.md
│   ├── walkthrough.md
│   └── process.md
│
└── legacy/                        # 레거시 버전 (V3-V7)
```

---

## 🛠️ 기술 스택

| 분류 | 기술 |
|:---|:---|
| **Backend** | Python 3.8+, Flask |
| **브라우저 자동화** | Playwright, Selenium |
| **데이터 파싱** | BeautifulSoup4, quopri |
| **시스템 제어** | pyperclip, keyboard |
| **스케줄링** | threading |

---

## 📊 주요 해결 과제

| 문제 | 해결 방안 |
|:---|:---|
| MHTML 인코딩 깨짐 | `quopri` 라이브러리로 Quoted-Printable 디코딩 |
| 브라우저 세션 충돌 | 독립 프로필 `avast_automation_profile` 사용 |
| JavaScript 입력 차단 | 물리적 `Ctrl+V` 키보드 시뮬레이션 |
| 복잡한 팝업 구조 | 텍스트 기반 Bounding Box 탐지 |
| 품목 코드 생성 | GAS 정규표현식 로직 Python 완전 이식 |

---

## 📖 문서

- [설치 가이드](INSTALL_GUIDE.md)
- [사용자 매뉴얼](USER_MANUAL.md)
- [V8 사용 설명서](walkthrough.md)
- [개발 과정 기록](process.md)

---

## 🔒 보안 주의사항

> [!WARNING]
> 다음 파일들은 **절대 Git에 커밋하지 마세요**:
> - `google_oauth_credentials.json`
> - `google_token.pickle`
> - `*_history.json`
> - `data/downloads/` (실제 주문서 데이터)

---

## 📝 라이선스

Internal Use Only - 내부 사용 전용

---

## 👨‍💻 개발 히스토리

- **V1-V3**: CLI 기반 자동화
- **V4**: 중복 방지 시스템
- **V5-V6**: 하이브리드 웹 서버
- **V7**: 견적서 대응 및 물리적 붙여넣기
- **V8**: 로그인 프리 + 자동 종료 + 실시간 알림 (현재)

---

**최종 업데이트**: 2026-01-05  
**Repository**: https://github.com/kangHo-Jun/Shop_Automation
