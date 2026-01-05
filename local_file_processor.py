import re
import os
import datetime
from bs4 import BeautifulSoup
import quopri

# =================================================================================================
# 전역 상수 & 매핑 (GAS: COMPANY_MAPPING)
# =================================================================================================
COMPANY_MAPPING = {
    '영림': {'display': '영림', 'brand': 'Y'},
    'www.yl.co.kr': {'display': '영림', 'brand': 'Y'},
    '우딘': {'display': '우딘', 'brand': 'W'},
    '예림': {'display': '예림', 'brand': 'y'}
}

# =================================================================================================
# MHTML / HTML 파싱 관련 함수
# =================================================================================================

def extract_html_from_mhtml(mhtml_content: str) -> str:
    """MHTML 내용에서 HTML 추출 및 디코딩"""
    try:
        # 1. HTML Content 찾기 (단순화된 패턴 매칭)
        # Content-Type: text/html 아래의 빈 줄 다음부터 경계선 전까지
        patterns = [
            r'Content-Type:\s*text\/html[\s\S]*?\r?\n\r?\n([\s\S]*?)(?=\r?\n--|Content-Type:|$)',
            r'(<html[\s\S]*?<\/html>)',
            r'(<\!DOCTYPE[\s\S]*?<\/html>)'
        ]
        
        html_content = ""
        for pattern in patterns:
            match = re.search(pattern, mhtml_content, re.IGNORECASE)
            if match:
                html_content = match.group(1).strip()
                break
        
        if not html_content and '<table' in mhtml_content:
             html_content = mhtml_content
             
        if not html_content:
            return ""
            
        # 2. Quoted-Printable 디코딩
        # Python의 quopri 라이브러리 사용 (더 강력함)
        try:
            decoded_bytes = quopri.decodestring(html_content.encode())
            try:
                return decoded_bytes.decode('utf-8')
            except UnicodeDecodeError:
                return decoded_bytes.decode('euc-kr', errors='replace')
        except Exception as e:
            print(f"디코딩 오류: {e}")
            return html_content # 실패시 원본 반환
            
    except Exception as e:
        print(f"MHTML 추출 오류: {e}")
        return ""

def parse_html_table(html_content: str) -> list:
    """HTML에서 테이블 데이터 파싱 (GAS: parseHtmlTable + parseTableBody)"""
    soup = BeautifulSoup(html_content, 'html.parser')
    all_result_data = []
    
    # 1. table.table-item 찾기
    tables = soup.find_all('table', class_='table-item')
    
    if not tables:
        # 대안: 모든 테이블 검색
        tables = soup.find_all('table')
    
    for table in tables:
        # 데이터가 있는지 확인 (간단한 체크: td 안에 숫자가 있는지)
        if not table.find('td'):
            continue
            
        # 헤더 건너뛰기 로직은 row 루프에서 처리
        rows = table.find_all('tr')
        if not rows:
            continue
            
        # tbody가 있으면 tbody 우선
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
            
        for row in rows:
            # 헤더 체크 (th가 있거나 class가 td-header 등)
            if row.find('th') or 'td-header' in row.get('class', []):
                continue
                
            cols = row.find_all(['td', 'th'])
            row_data_raw = []
            
            for col in cols:
                # div가 있으면 div 내용 사용, 아니면 셀 텍스트
                div = col.find('div')
                text = div.get_text(strip=True) if div else col.get_text(strip=True)
                row_data_raw.append(text)
                
            # 유효성 검사
            # 1. 데이터가 하나라도 있어야 함
            if not any(row_data_raw): 
                continue
            # 2. 첫 열이 '합계'가 아니어야 함
            if row_data_raw and row_data_raw[0] == '합계':
                continue
            # 3. 열 개수가 최소 4개 이상 (NO, 색상, 품명, 규격...)
            if len(row_data_raw) < 4:
                continue
            # 4. 첫 열(NO)이 숫자여야 함
            if row_data_raw[0] and not row_data_raw[0].isdigit():
                continue
                
            # 데이터 매핑 (GAS 로직 참조)
            # rowDataRaw[1]: 색상
            # rowDataRaw[2]: 품명
            # rowDataRaw[3]: 규격
            # rowDataRaw[4]: 수량
            # rowDataRaw[5]: 단가
            # rowDataRaw[6]: 금액
            # rowDataRaw[7]: 비고
            
            color_val = row_data_raw[1] if len(row_data_raw) > 1 else ''
            item_name = row_data_raw[2] if len(row_data_raw) > 2 else ''
            spec_val = row_data_raw[3] if len(row_data_raw) > 3 else ''
            
            # 품목명 조합 (GAS: productName) - 사실 로직에서는 개별 필드로 처리함
            # resultData 구조: [NO, 품목명(조합), 색상, 품명, 규격, 수량, 단가, 금액, 비고]
            
            new_row = [
                row_data_raw[0], # NO
                '',              # 품목명 (나중에 조합)
                color_val,       # 색상
                item_name,       # 품명
                spec_val,        # 규격
                row_data_raw[4] if len(row_data_raw) > 4 else '', # 수량
                row_data_raw[5] if len(row_data_raw) > 5 else '', # 단가
                row_data_raw[6] if len(row_data_raw) > 6 else '', # 금액
                row_data_raw[7] if len(row_data_raw) > 7 else '', # 비고
            ]
            all_result_data.append(new_row)
            
    return all_result_data

# =================================================================================================
# 코드 생성 및 전처리 로직 (GAS 포팅)
# =================================================================================================

def detect_company(html_content: str, all_data: list) -> dict:
    """회사명 탐지"""
    # 1. HTML 내용에서 찾기
    for keyword, info in COMPANY_MAPPING.items():
        if keyword in html_content:
            return info
            
    # 2. 데이터에서 찾기
    for row in all_data:
        color = str(row[2])
        item = str(row[3])
        combined = color + ' ' + item
        for keyword, info in COMPANY_MAPPING.items():
            if keyword in combined:
                return info
                
    return {'display': '예림', 'brand': 'y'} # 기본값

def should_add_company_prefix(color: str, item_name: str, company_display: str) -> bool:
    if company_display in color or company_display in item_name:
        return False
        
    for info in COMPANY_MAPPING.values():
        if info['display'] in color or info['display'] in item_name:
            return False
            
    return True

def preprocess_color_for_product_name(color: str) -> str:
    if not color: return ''
    color_str = str(color).strip()
    
    # 1순위: 영림{숫자} + 영문{숫자}
    if re.search(r'영림\d+\s+[A-Za-z]+\d+', color_str):
        return re.sub(r'\s+', '', color_str)
        
    # 2순위: 영림{숫자} + 한글
    match = re.match(r'(영림\d+)\s+[가-힣]', color_str)
    if match:
        return match.group(1)
        
    # 3순위: 영림{숫자}
    if re.match(r'^영림\d+$', color_str):
        return color_str
        
    # 회사명 키워드 제거
    for keyword in COMPANY_MAPPING.keys():
        color_str = color_str.replace(keyword, '').strip()
        
    # 4순위: 한글만 -> 공백제거
    if re.match(r'^[가-힣\s]+$', color_str):
        return re.sub(r'\s+', '', color_str)
        
    return color_str

def preprocess_item_name_for_product_name(item_name: str, spec: str) -> str:
    item_str = str(item_name).strip()
    
    # VER12: "평+숫자" -> "평숫자" 변환
    pyeong_match = re.search(r'(\d+)MM평', item_str)
    if pyeong_match:
        item_str = re.sub(r'\d+MM평판?', f"평{pyeong_match.group(1)}", item_str)
        
    item_str = item_str.replace('문틀', '').strip()
    item_str = re.sub(r'\(식기[XO]\)', '', item_str).strip()
    
    # 규격 첫번째 숫자 + 붙어있는 문자 패턴 제거
    spec_str = str(spec).strip()
    first_number_match = re.match(r'^(\d+)', spec_str)
    if first_number_match:
        first_num = first_number_match.group(1)
        # item_str = re.sub(f"{first_num}[가-힣]+", '', item_str).strip() # Python f-string regex handling careful
        pattern = re.compile(re.escape(first_num) + r'[가-힣]+')
        item_str = pattern.sub('', item_str).strip()
        
    return item_str

def preprocess_spec_for_product_name(spec: str) -> str:
    spec_str = str(spec).strip()
    
    if re.search(r'\/\s*N$', spec_str, re.IGNORECASE):
        return re.sub(r'\/\s*N$', '식기무', spec_str, flags=re.IGNORECASE)
        
    if re.search(r'\/\s*[SY]$', spec_str, re.IGNORECASE):
        return re.sub(r'\/\s*[SY]$', '식기유', spec_str, flags=re.IGNORECASE)
        
    if re.search(r'\/\s*([A-Za-z])$', spec_str, re.IGNORECASE):
        return re.sub(r'\/\s*([A-Za-z])$', r'\1', spec_str, flags=re.IGNORECASE) # group check
        
    if re.search(r'\/\s*$', spec_str):
        return re.sub(r'\/\s*$', '', spec_str).strip()
        
    return spec_str

def is_valid_spec_size(spec: str) -> bool:
    if not spec: return False
    numbers = re.findall(r'\d+', str(spec))
    if not numbers: return False
    max_num = max(int(n) for n in numbers)
    return max_num > 999

def classify_target(item_name: str) -> str:
    item_str = str(item_name).strip()
    
    frame_keywords = ['문틀', '발포', '분리형', '스토퍼']
    has_frame = any(kw in item_str for kw in frame_keywords)
    
    door_keywords = ['문짝', 'ABS', '도어', 'M/D', '민무늬', '탈공', '미서기', '미닫이']
    has_door = any(kw in item_str for kw in door_keywords)
    
    door_patterns = [
        r'YS-[A-Z0-9]+', r'YA-[A-Z0-9]+', r'YAT-[A-Z0-9]+', r'EZ-[A-Z0-9]+', 
        r'LS-[A-Z0-9]+', r'YM-[A-Z0-9]+', r'YAL-[A-Z0-9]+', r'YV-[A-Z0-9]+',
        r'YFL-[A-Z0-9]+', r'SW-[A-Z0-9]+', r'TD-[A-Z0-9]+', r'SL-[A-Z0-9]+'
    ]
    has_door_pattern = any(re.search(pat, item_str) for pat in door_patterns)
    
    has_yeondong = bool(re.search(r'\d+연동', item_str))
    has_rail = '레일' in item_str
    
    molding_keywords = ['몰딩', '평', '코너', '계단', '천정', '천장', '걸레', '문선', '보드', '루버', '루바', '기둥']
    has_molding = any(kw in item_str for kw in molding_keywords)
    
    if has_frame: return 'FRAME'
    if has_rail and not has_door and not has_door_pattern: return 'RAIL'
    if has_door or has_door_pattern or has_yeondong: return 'DOOR'
    if has_molding: return 'MOLDING'
    return 'NONE'

def generate_brand_color_code(color: str, brand_code: str) -> str:
    color_str = str(color).strip()
    brand = brand_code
    
    for keyword in COMPANY_MAPPING.keys():
        color_str = color_str.replace(keyword, '').strip()
        
    # 1. 영림{숫자}PS{숫자}
    match = re.search(r'영림(\d+)PS\d+', color_str)
    if match: return brand + match.group(1)
    
    # 2. PS...
    match = re.match(r'^PS(.+)$', color_str)
    if match: return brand + 'S' + match.group(1)
    
    # 3. PX...
    match = re.match(r'^PX(.+)$', color_str)
    if match: return brand + 'X' + match.group(1)
    
    # 4. 영림{숫자}
    match = re.search(r'영림(\d+)', color_str)
    if match: return brand + match.group(1)
    
    # 5. 한글만
    if re.match(r'^[가-힣\s]+$', color_str):
        cleaned = re.sub(r'\s+', '', color_str)
        return brand + cleaned[:2]
        
    # 6. 숫자 포함
    match = re.search(r'(\d+)', color_str)
    if match: return brand + match.group(1)
    
    return ''

def generate_flag_code(item_name: str) -> str:
    item_str = str(item_name).strip()
    upper_code = ''
    if '발포' in item_str: upper_code = 'B'
    elif '방염' in item_str: upper_code = 'F'
    elif '비방염' in item_str: upper_code = 'N'
    elif '알루미늄' in item_str: upper_code = 'A'
    
    lower_code = ''
    if '슬림와이드' in item_str: lower_code = 'I'
    elif '와이드' in item_str: lower_code = 'W'
    elif '슬림' in item_str: lower_code = 'S'
    elif '차음' in item_str: lower_code = 'E'
    elif '일반형' in item_str: lower_code = 'G'
    elif '가변형' in item_str: lower_code = 'K'
    elif '분리형' in item_str or '스토퍼' in item_str: lower_code = 'D'
    elif '일체' in item_str: lower_code = 'B'
    elif '히든' in item_str: lower_code = 'H'
    elif '스텝' in item_str: lower_code = 'T'
    elif '무메' in item_str or '무매' in item_str: lower_code = 'M'
    elif '미서기' in item_str or '미닫이' in item_str: lower_code = 'L'
    
    if not upper_code and lower_code: upper_code = 'N'
    if not upper_code: return ''
    
    yeondong_match = re.search(r'(\d+)연동', item_str)
    if (upper_code in ['F', 'N', 'A']) and yeondong_match:
        return upper_code + yeondong_match.group(1) + 'C'
        
    return upper_code + lower_code

def generate_model_code(item_name: str) -> str:
    item_str = str(item_name).strip()
    
    match = re.search(r'([A-Z]+)-([A-Z0-9]+)', item_str)
    if match:
        prefix = match.group(1)
        suffix = match.group(2)
        hangul_search = re.search(r'[가-힣]', suffix)
        if hangul_search:
            suffix = suffix[:hangul_search.start()]
        return prefix + suffix
        
    if '탈공' in item_str: return '탈'
    if 'M/D' in item_str and '민무늬' in item_str: return 'MD'
    
    match = re.search(r'(\S+)도어', item_str)
    if match: return match.group(1)
    
    return ''

def generate_rail_code(item_name: str) -> str:
    item_str = str(item_name).strip()
    match = re.search(r'(\d+)연동', item_str)
    yeondong_num = match.group(1) if match else ''
    
    if yeondong_num:
        slim_code = ''
        if '초슬림' in item_str: slim_code = 'SS'
        elif '슬림' in item_str: slim_code = 'S'
        return slim_code + yeondong_num + '레일'
        
    prefix = ''
    if '초슬림' in item_str: prefix += 'SS'
    elif '슬림' in item_str: prefix += 'S'
    
    if '상부' in item_str: prefix += '상'
    elif '하부' in item_str: prefix += '하'
    
    return prefix + '레일'

def generate_molding_flag_code(item_name: str) -> str:
    item_str = str(item_name).strip()
    
    if '천장' in item_str: return '천장'
    if '프레임몰딩' in item_str or '프레임' in item_str: return '프레임'
    if '기둥' in item_str: return '기둥'
    
    if '템바보드' in item_str or '템바루바' in item_str:
        code = ''
        if '방염' in item_str and '비방염' not in item_str: code += 'F'
        
        clean_str = item_str.replace('형', '')
        if '소반달' in clean_str or '소형반달' in clean_str: code += '소반달'
        elif '대반달' in clean_str or '대형반달' in clean_str: code += '대반달'
        elif '소직각' in clean_str or '소형직각' in clean_str: code += '소직각'
        elif '직각대' in clean_str or '대형직각' in clean_str: code += '직각대'
        elif '역반달' in clean_str: code += '역반달'
        
        if '템바보드' in item_str: code += 'TB'
        elif '템바루바' in item_str: code += 'TL'
        return code
        
    code = item_str
    code = code.replace('몰딩', '').replace('받이', '').replace('평판', '평').strip()
    code = re.sub(r'\d+MM\s*', '', code)
    code = re.sub(r'\([^)]*\)', '', code)
    code = re.sub(r'^\d+\s*', '', code).strip()
    
    return code

def generate_molding_spec_code(item_name: str, spec: str, remarks: str) -> str:
    item_str = str(item_name).strip()
    spec_str = str(spec).strip()
    remarks_str = str(remarks).strip()
    
    if '프레임몰딩' in item_str or '프레임' in item_str:
        match = re.search(r'프레임[^\d]*(\d+)', item_str)
        if match: return match.group(1)
        
    if '기둥' in item_str:
        match = re.search(r'\((\d+)\*(\d+)\*(\d+)\)', spec_str) or re.search(r'\((\d+)\*(\d+)\*(\d+)\)', item_str)
        if match:
            num1, num2, num3 = match.groups()
            if num3 == '9': return num1 + num2
            return num1 + num2 + num3
            
    # 1순위: 규격열 () *패턴
    match = re.search(r'\((\d+)\*(\d+)\)', spec_str)
    if match:
        num1, num2 = match.groups()
        if num2 == '9': return num1
        return num1 + num2
        
    # 2순위: 품명 () *패턴
    match = re.search(r'\((\d+)\*(\d+)\)', item_str)
    if match:
        num1, num2 = match.groups()
        if num2 == '9': return num1
        return num1 + num2
        
    # 3순위: 비고열 *패턴
    match = re.search(r'(\d+)\*(\d+)', remarks_str)
    if match:
        num1, num2 = match.groups()
        if num2 == '9': return num1
        return num1 + num2
        
    # 4순위: 품명 (숫자T)
    match_t = re.search(r'\((\d+)T\)', item_str, re.IGNORECASE)
    if match_t:
        mm_match = re.search(r'(\d+)MM', item_str)
        if mm_match: return mm_match.group(1) + match_t.group(1)
        
    # 5순위: 비고 숫자T
    match_rem_t = re.search(r'(\d+)T', remarks_str, re.IGNORECASE)
    if match_rem_t:
        mm_match = re.search(r'(\d+)MM', item_str)
        if mm_match: return mm_match.group(1) + match_rem_t.group(1)
        
    # 6순위: 템바
    if '템바' in item_str:
         match = re.search(r'(\d+)\*(\d+)', item_str)
         if match: return match.group(1) + match.group(2)
         
    # 7순위: 숫자바/번
    match = re.search(r'(\d+)(?:바용|번)', item_str)
    if match: return match.group(1)
    
    # 8순위: MM평판
    match = re.search(r'(\d+)MM평판?', item_str)
    if match: return match.group(1)
    
    # 9순위: 단순숫자
    match = re.search(r'^(\d+)$', spec_str)
    if match: return match.group(1)
    
    return ''

def generate_spec_code(spec: str) -> str:
    if not spec: return ''
    spec_str = str(spec).strip()
    numbers = re.findall(r'\d+', spec_str)
    if not numbers: return ''
    
    result = "".join(numbers)
    match = re.search(r'\/\s*([A-Za-z]+)', spec_str)
    if match: result += match.group(1).strip()
    return result

def generate_unit(item_name: str, spec: str, remarks: str) -> str:
    item_str = str(item_name).strip()
    spec_str = str(spec).strip()
    remarks_str = str(remarks).strip()
    
    # 숫자 체크
    if not any(char.isdigit() for char in (spec_str + remarks_str + item_str)):
        return ''
        
    classification = classify_target(item_str)
    
    if classification == 'RAIL': return '개'
    
    if classification == 'FRAME':
        if re.search(r'^\d+\*\/?$', spec_str) or re.search(r'^\d+\*\d+\*\/?$', spec_str):
            return '개'
        return '틀'
        
    if classification == 'DOOR': return '짝'
    
    if classification == 'MOLDING':
        if '템바보드' in item_str: return '롤'
        if '템바루바' in item_str: return 'BOX'
        return 'EA'
        
    return ''

def generate_product_code(color: str, item_name: str, spec: str, remarks: str, brand_code: str) -> str:
    try:
        classification = classify_target(item_name)
        if classification == 'NONE': return ''
        
        if classification != 'MOLDING' and not is_valid_spec_size(spec):
            return ''
            
        brand_color_code = generate_brand_color_code(color, brand_code)
        if not brand_color_code: return ''
        
        flag_model_code = ''
        if classification == 'FRAME': flag_model_code = generate_flag_code(item_name)
        elif classification == 'DOOR': flag_model_code = generate_model_code(item_name)
        elif classification == 'RAIL': flag_model_code = generate_rail_code(item_name)
        elif classification == 'MOLDING': flag_model_code = generate_molding_flag_code(item_name)
        
        spec_code = ''
        if classification == 'MOLDING': spec_code = generate_molding_spec_code(item_name, spec, remarks)
        else: spec_code = generate_spec_code(spec)
        
        if not spec_code: return ''
        
        return brand_color_code + flag_model_code + spec_code
        
    except Exception as e:
        print(f"코드 생성 오류: {e}")
        return ''
        
# =================================================================================================
# 메인 처리 로직
# =================================================================================================

def process_html_content(html_content: str, file_path_hint: str = "", target_type: str = 'ledger') -> list:
    """HTML 문자열을 직접 처리하여 ERP 데이터 반환 (In-Memory)"""
    
    # HTML 파싱
    raw_data = parse_html_table(html_content)
    if not raw_data:
        print(f"[{file_path_hint}] 데이터를 찾을 수 없습니다.")
        return []
        
    # 회사명 감지
    company_info = detect_company(html_content, raw_data)
    print(f"[{file_path_hint}] 회사 감지: {company_info['display']} ({company_info['brand']})")
    
    erp_rows = []
    
    for row in raw_data:
        # row: [NO, 품목명(공백), 색상, 품명, 규격, 수량, 단가, 금액, 비고]
        color_raw = row[2]
        item_name_raw = row[3]
        spec_raw = row[4]
        quantity_raw = row[5]
        amount_raw = row[7] # Index 7 is Amount
        remarks_raw = row[8]
        
        # 품목명 생성
        color_processed = preprocess_color_for_product_name(color_raw)
        item_name_processed = preprocess_item_name_for_product_name(item_name_raw, spec_raw)
        spec_processed = preprocess_spec_for_product_name(spec_raw)
        
        needs_prefix = should_add_company_prefix(color_processed, item_name_processed, company_info['display'])
        prefix = company_info['display'] if needs_prefix else ''
        product_name = f"{prefix}{color_processed} {item_name_processed} {spec_processed}".strip()
        
        # 코드 생성
        product_code = generate_product_code(color_raw, item_name_raw, spec_raw, remarks_raw, company_info['brand'])
        
        # ERP 행 생성 (최근 업로드 엔진은 탭 구분을 선호하므로 충분한 열 확보)
        erp_row = [''] * 30
        today = datetime.datetime.now().strftime('%Y/%m/%d')
        
        if target_type == 'estimate':
            # V7 사용자 요청: 견적서입력 팝업
            # 실제 엑셀 양식: 22열 (A~V)
            # A열(0): 순번, B열(1): 거래처코드, C열(2): 거래처명, D열(3): 일자
            # E열(4): 출하창고, F열(5): 전표담당자, G열(6): 거래처담당팀, H열(7): 거래처연락처
            # I열(8): 거래유형, J열(9): 결제조건, K열(10): 견적유효기간, L열(11): 내부용기밀
            # M열(12): 수령고객정보, N열(13): NO., O열(14): 품목코드, P열(15): 품목명
            # Q열(16): 수량, R열(17): 단가, S열(18): 공급가액, T열(19): 부가세
            # U열(20): 합계, V열(21): 비고
            erp_row = [''] * 22  # ← 22열로 변경!
            erp_row[3] = today           # 일자 (D)
            erp_row[14] = product_code   # 품목코드 (O)
            erp_row[15] = product_name   # 품목명 (P)
            erp_row[16] = quantity_raw   # 수량 (Q)
            erp_rows.append(erp_row)
        else:
            # 기본 구매입력 (Ledger) 레이아웃
            erp_row[0] = today          # 날짜
            erp_row[6] = '100'          # 100
            erp_row[16] = product_name  # 품목명 (Q) - 기존 V6 기준
            erp_row[17] = product_code  # 품목코드 (R)
            erp_row[18] = quantity_raw  # 수량 (S)
            erp_row[19] = amount_raw    # 공급가액 (T)
            erp_row[29] = remarks_raw   # 비고 (AD)
        
        erp_rows.append(erp_row)
        
    return erp_rows

def process_html_file(file_path: str, target_type: str = 'ledger') -> list:
    """단일 HTML 파일을 처리하여 ERP 업로드용 데이터 반환"""
    print(f"처리 중: {file_path} ({target_type})")
    
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        
    # MHTML인 경우
    if file_path.lower().endswith('.mhtml') or file_path.lower().endswith('.mht'):
        html_content = extract_html_from_mhtml(content)
    else:
        html_content = content
        
    return process_html_content(html_content, file_path_hint=os.path.basename(file_path), target_type=target_type)

if __name__ == "__main__":
    # 테스트용
    import sys
    # test processing logic
    pass
