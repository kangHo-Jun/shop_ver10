import os
import shutil
import glob
import sys
from pathlib import Path
import local_file_processor
from erp_upload_automation_v1 import ErpUploadAutomation

# ============================================================
# 설정
# ============================================================
SOURCE_DIR = Path(r"C:\Users\DSAI\Desktop\원본")
COMPLETED_DIR = SOURCE_DIR / "완료"

def get_all_files(directory):
    """지정된 디렉토리의 모든 HTML/MHTML 파일 찾기 (오래된 순)"""
    if not directory.exists():
        print(f"❌ 폴더를 찾을 수 없습니다: {directory}")
        return []
        
    files = []
    for ext in ('*.html', '*.mhtml', '*.mht'):
        files.extend(directory.glob(ext))
        
    if not files:
        return []
        
    # 수정 시간 기준 정렬 (오래된 순 - FIFO)
    return sorted(files, key=os.path.getmtime)

def main():
    print("=" * 60)
    print("🚀 매장자동화 V3 - 통합 일괄 업로드")
    print("=" * 60)
    
    # 1. 원본 폴더 확인
    if not SOURCE_DIR.exists():
        print(f"⚠️ 원본 폴더가 없습니다. 생성합니다: {SOURCE_DIR}")
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        print("📁 폴더 생성 완료. HTML 파일을 넣고 다시 실행해주세요.")
        return

    # 2. 모든 파일 찾기
    files = get_all_files(SOURCE_DIR)
    if not files:
        print(f"ℹ️ 처리할 파일이 없습니다. (경로: {SOURCE_DIR})")
        return
        
    print(f"📦 총 {len(files)}개 파일을 발견했습니다. 데이터 통합을 시작합니다.\n")
    
    all_erp_data = []
    processed_files = []
    
    # 3. 모든 파일 분석 및 데이터 통합
    for index, file_path in enumerate(files, 1):
        print(f"📄 [{index}/{len(files)}] 분석 중: {file_path.name}")
        try:
            erp_data = local_file_processor.process_html_file(str(file_path))
            if erp_data:
                all_erp_data.extend(erp_data)
                processed_files.append(file_path)
                print(f"   ✅ {len(erp_data)}개 행 데이터 추출")
            else:
                print("   ⚠️ 데이터 없음 (스킵)")
        except Exception as e:
            print(f"   ❌ 오류 발생: {e}")
            
    if not all_erp_data:
        print("\n⚠️ 전송할 데이터가 하나도 없습니다.")
        return

    print("-" * 60)
    print(f"📊 총 {len(all_erp_data)}개 통합 데이터 준비 완료")
    print("-" * 60)

    # 4. Ecount ERP 일괄 업로드
    try:
        print("\n[단계 2] Ecount ERP 일괄 업로드")
        automation = ErpUploadAutomation()
        
        # 통합 데이터 주입 (auto_close=True로 완료 후 즉시 복귀)
        success = automation.run(direct_data=all_erp_data, auto_close=True)
        
        if success:
            # 5. 처리된 파일들 일괄 이동
            print("\n[단계 3] 파일 정리")
            if not COMPLETED_DIR.exists():
                COMPLETED_DIR.mkdir()
            
            count = 0
            for file_path in processed_files:
                try:
                    destination = COMPLETED_DIR / file_path.name
                    if destination.exists():
                        os.remove(destination)
                    shutil.move(str(file_path), str(destination))
                    count += 1
                except Exception as e:
                    print(f"   ❌ 이동 실패 ({file_path.name}): {e}")
            
            print(f"   📦 총 {count}개 파일 완료 폴더로 이동됨")
            print("\n✨ 모든 작업이 성공적으로 완료되었습니다!")
        else:
            print("\n⚠️ ERP 업로드 실패로 파일은 이동하지 않습니다.")
            
    except Exception as e:
        print(f"❌ 자동화 수행 중 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'automation' in locals():
            # 브라우저를 닫지 않고 유지 (사용자 요청)
            automation.close(keep_browser_open=True)

if __name__ == "__main__":
    main()
