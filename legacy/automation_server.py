"""
자동화 서버 - 원클릭 실행
==========================
GAS 스크립트 완료 신호를 받아 ERP 업로드 자동화를 실행

사용법:
1. 이 서버를 먼저 실행: python automation_server.py
2. Google Sheets에서 GAS 스크립트 실행
3. GAS 완료 시 자동으로 ERP 업로드 실행
"""

from flask import Flask, jsonify, request
import subprocess
import sys
import threading
import time
from pathlib import Path

app = Flask(__name__)

# 설정
SCRIPT_DIR = Path(__file__).parent
ERP_UPLOAD_SCRIPT = SCRIPT_DIR / "erp_upload_automation.py"
PYTHON_EXE = SCRIPT_DIR / ".venv" / "Scripts" / "python.exe"

# 상태 관리
is_running = False


def run_erp_upload():
    """ERP 업로드 스크립트 실행"""
    global is_running
    
    if is_running:
        print("⚠️ 이미 실행 중입니다. 무시됨.")
        return
    
    is_running = True
    print("\n" + "=" * 50)
    print("🚀 GAS 완료 신호 수신! ERP 업로드 시작...")
    print("=" * 50)
    
    try:
        # 잠시 대기 (GAS 스크립트가 시트에 데이터 쓰기 완료할 시간)
        time.sleep(2)
        
        # ERP 업로드 스크립트 실행
        result = subprocess.run(
            [str(PYTHON_EXE), str(ERP_UPLOAD_SCRIPT)],
            cwd=str(SCRIPT_DIR),
            capture_output=False
        )
        
        print("\n✅ ERP 업로드 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
    
    finally:
        is_running = False


@app.route('/trigger', methods=['GET', 'POST'])
def trigger_upload():
    """GAS에서 호출하는 트리거 엔드포인트"""
    print("\n📨 트리거 요청 수신됨")
    
    # 비동기로 실행 (즉시 응답 반환)
    thread = threading.Thread(target=run_erp_upload)
    thread.start()
    
    return jsonify({
        "status": "success",
        "message": "ERP 업로드가 시작되었습니다"
    })


@app.route('/status', methods=['GET'])
def get_status():
    """현재 상태 확인"""
    return jsonify({
        "running": is_running,
        "server": "online"
    })


@app.route('/', methods=['GET'])
def home():
    """서버 상태 확인용 홈페이지"""
    return """
    <html>
    <head><title>자동화 서버</title></head>
    <body style="font-family: Arial; padding: 20px;">
        <h1>🤖 자동화 서버 실행 중</h1>
        <p>GAS 스크립트 완료 시 자동으로 ERP 업로드가 실행됩니다.</p>
        <hr>
        <p><strong>엔드포인트:</strong></p>
        <ul>
            <li><code>GET/POST /trigger</code> - ERP 업로드 실행</li>
            <li><code>GET /status</code> - 현재 상태 확인</li>
        </ul>
        <hr>
        <p><a href="/trigger">수동으로 트리거 실행</a></p>
    </body>
    </html>
    """


if __name__ == "__main__":
    print("=" * 50)
    print("🤖 자동화 서버 시작")
    print("=" * 50)
    print(f"📍 트리거 URL: http://localhost:5000/trigger")
    print(f"📍 상태 확인: http://localhost:5000/status")
    print("=" * 50)
    print("\nGAS 스크립트에서 완료 시 위 URL을 호출하면")
    print("자동으로 ERP 업로드가 실행됩니다.")
    print("\n서버 종료: Ctrl+C")
    print("=" * 50 + "\n")
    
    # 서버 시작 (debug=False로 프로덕션 모드)
    app.run(host='0.0.0.0', port=5000, debug=False)
