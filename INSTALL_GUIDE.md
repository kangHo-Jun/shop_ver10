# 매장자동화 V3 - 설치 가이드

## 📋 요구 사항

- **운영체제**: Windows 10/11
- **Python**: 3.8 이상
- **브라우저**: Google Chrome

---

## 🔧 설치 단계

### 1. Python 설치 확인
```powershell
python --version
# Python 3.x.x가 출력되어야 함
```

### 2. 프로젝트 폴더로 이동
```powershell
cd C:\Users\DSAI\Desktop\매장자동화
```

### 3. 가상환경 생성 (최초 1회)
```powershell
python -m venv .venv
```

### 4. 가상환경 활성화
```powershell
.venv\Scripts\activate
```

### 5. 의존성 설치
```powershell
pip install -r requirements.txt
```

### 6. Playwright 브라우저 설치
```powershell
playwright install chromium
```

---

## ✅ 설치 확인

```powershell
.venv\Scripts\python.exe v3_run_all.py
```

"처리할 파일이 없습니다" 메시지가 나오면 설치 성공!

---

## 📁 폴더 생성 (자동)

원본 폴더(`C:\Users\DSAI\Desktop\원본`)는 최초 실행 시 자동으로 생성됩니다.

---

## 🔐 Ecount 로그인 정보 설정

`erp_upload_automation_v1.py` 파일의 43-47번째 줄:
```python
CREDENTIALS = {
    'company_code': '회사코드',
    'username': '아이디',
    'password': '비밀번호'
}
```

---

## ❓ 문제 해결

| 증상 | 해결 방법 |
|---|---|
| `pip` 명령어 없음 | Python 재설치 (PATH 추가 옵션 체크) |
| `playwright` 오류 | `playwright install` 다시 실행 |
| Chrome 경로 오류 | Chrome이 기본 경로에 설치되어 있는지 확인 |
