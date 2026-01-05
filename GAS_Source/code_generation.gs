// 스크립트 실행에 필요한 권한: DriveApp, SpreadsheetApp

// 전역 상수
const HEADERS = ["품목명", "품목코드", "", "단위"];
const DRIVE_FOLDER_ID = '1pPgU1alLhTfvqoCXoXRhC1EVvZez7SvG';
const SPREADSHEET_ID = '1qEbhwGw4mstuMkhAJyFMK4QiIrZR_Gw3bFMR1wb2Las';
const OUTPUT_SHEET_NAME = '결과';
const LOG_SHEET_NAME = 'Processed_Log';

// 회사명 매핑 (VER09)
const COMPANY_MAPPING = {
  '영림': { display: '영림', brand: 'Y' },
  'www.yl.co.kr': { display: '영림', brand: 'Y' },
  '우딘': { display: '우딘', brand: 'W' },
  '예림': { display: '예림', brand: 'y' }
};

/**
 * 메인 함수 - MHTML 및 HTML 파일 자동 처리 (VER12-FIX4)
 */
function automateEstimateParsing() {
  const folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);

  // 1. 폴더에 새로운 파일이 있는지 확인
  const filesIteratorCheck = folder.getFiles();
  if (!filesIteratorCheck.hasNext()) {
    Logger.log("새로운 업로드 파일이 없습니다. 작업 종료.");
    return;
  }

  // 2. 결과 시트가 있으면 삭제 후 새로 생성
  let outputSheet = spreadsheet.getSheetByName(OUTPUT_SHEET_NAME);
  if (outputSheet) {
    spreadsheet.deleteSheet(outputSheet);
  }
  outputSheet = spreadsheet.insertSheet(OUTPUT_SHEET_NAME);

  // 헤더 추가
  outputSheet.appendRow(HEADERS);
  outputSheet.getRange(1, 1, 1, HEADERS.length).setFontWeight("bold").setHorizontalAlignment("center");
  outputSheet.setFrozenRows(1);

  // 3. 로그 시트 준비
  let logSheet = spreadsheet.getSheetByName(LOG_SHEET_NAME);
  if (!logSheet) {
    logSheet = spreadsheet.insertSheet(LOG_SHEET_NAME);
    logSheet.appendRow(["File ID", "File Name", "Processed Date"]);
  }

  const processedIds = logSheet.getLastRow() > 1
    ? logSheet.getRange(2, 1, logSheet.getLastRow() - 1, 1).getValues().flat().filter(String)
    : [];

  // 4. 폴더 내 HTML/MHTML 파일 목록 수집
  const fileMetadatas = [];
  const filesIterator = folder.getFiles();
  while (filesIterator.hasNext()) {
    const file = filesIterator.next();
    const fileName = file.getName().toLowerCase();
    if (fileName.endsWith('.html') || fileName.endsWith('.mhtml') || fileName.endsWith('.mht')) {
      if (processedIds.includes(file.getId())) continue;
      fileMetadatas.push({
        id: file.getId(),
        name: file.getName(),
        created: file.getDateCreated()
      });
    }
  }

  // 5. 생성 날짜순 정렬
  fileMetadatas.sort((a, b) => a.created.getTime() - b.created.getTime());

  // 6. 전체 데이터 수집
  let allExtractedData = [];
  let allHtmlContent = '';  // HTML 전체 내용 저장 (회사명 탐지용)

  fileMetadatas.forEach(metadata => {
    try {
      Logger.log(`=== 파일 처리 시작: ${metadata.name} ===`);
      const file = DriveApp.getFileById(metadata.id);
      const fileContent = file.getBlob().getDataAsString();
      
      let htmlContent;
      if (metadata.name.toLowerCase().endsWith('.mhtml') || metadata.name.toLowerCase().endsWith('.mht')) {
        htmlContent = extractHtmlFromMhtml(fileContent);
      } else {
        htmlContent = fileContent;
      }
      
      // HTML 내용 누적 저장 (회사명 탐지용)
      allHtmlContent += htmlContent + '\n';
      
      const extractedData = parseHtmlTable(htmlContent);
      if (extractedData.length > 0) {
        allExtractedData = allExtractedData.concat(extractedData);
        logSheet.appendRow([metadata.id, metadata.name, new Date()]);
        Logger.log(`파일 "${metadata.name}" 처리 완료: ${extractedData.length}행 추가`);
      } else {
        Logger.log(`파일 "${metadata.name}"에서 데이터 없음`);
      }
    } catch (e) {
      Logger.log(`파일 "${metadata.name}" 처리 중 오류: ${e.toString()}`);
    }
  });

  // 7. 회사명 탐지
  const companyInfo = detectCompany(allExtractedData, allHtmlContent);
  Logger.log(`회사명 탐지: ${companyInfo.display} (브랜드: ${companyInfo.brand})`);

  // 8. 코드 생성 및 데이터 변환 (객체 구조로 변경하여 원본 유지)
  const processedObjects = allExtractedData.map(row => {
    const colorRaw = row[2] || '';
    const itemNameRaw = row[3] || '';
    const specRaw = row[4] || '';
    const quantityRaw = row[5] || '';  // 수량
    const amountRaw = row[7] || '';    // 공급가액
    const remarksRaw = row[8] || '';   // 비고
    
    // 품목명 생성 (전처리된 데이터)
    const colorProcessed = preprocessColorForProductName(colorRaw);
    const itemNameProcessed = preprocessItemNameForProductName(itemNameRaw, specRaw);
    const specProcessed = preprocessSpecForProductName(specRaw);
    
    // 회사명 추가 여부 판단
    const needsCompanyPrefix = shouldAddCompanyPrefix(colorProcessed, itemNameProcessed, companyInfo.display);
    const companyPrefix = needsCompanyPrefix ? companyInfo.display : '';
    
    const productName = `${companyPrefix}${colorProcessed} ${itemNameProcessed} ${specProcessed}`.trim();
    
    // 품목코드 생성 (원본 데이터)
    const productCode = generateProductCode(colorRaw, itemNameRaw, specRaw, remarksRaw, companyInfo.brand);
    
    // 단위 생성 (원본 데이터)
    const unit = generateUnit(itemNameRaw, specRaw, remarksRaw);
    
    // 결과 시트용 행
    const resultRow = [
      productName,  // 품목명
      productCode,  // 품목코드
      '',           // 빈칸
      unit          // 단위
    ];
    
    // ERP 시트용 행 (총 30개 열)
    const erpRow = new Array(30).fill('');
    const today = Utilities.formatDate(new Date(), "GMT+9", "yyyy/MM/dd");
    
    erpRow[0] = today;        // A열: 날짜
    erpRow[6] = '100';        // G열: 100
    erpRow[16] = productName; // Q열: 품목명
    erpRow[17] = productCode; // R열: 품목코드
    erpRow[18] = quantityRaw; // S열: 수량
    erpRow[19] = amountRaw;   // T열: 공급가액
    erpRow[29] = remarksRaw;  // AD열: 비고
    
    return {
      hasCode: !!(productCode && productCode.trim() !== ''),
      resultRow: resultRow,
      erpRow: erpRow
    };
  });

  // 9. 코드 있는 행 먼저, 코드 없는 행 나중에 정렬
  const withCode = processedObjects.filter(obj => obj.hasCode);
  const withoutCode = processedObjects.filter(obj => !obj.hasCode);
  const sortedObjects = withCode.concat(withoutCode);

  // 10. 스프레드시트에 데이터 쓰기
  // 10-1. 결과 시트
  const resultData = sortedObjects.map(obj => obj.resultRow);
  if (resultData.length > 0) {
    const dataColumns = resultData[0].length;
    outputSheet.getRange(2, 1, resultData.length, dataColumns).setValues(resultData);
    Logger.log(`결과 시트: ${resultData.length}행 작성 완료`);
  }
  
  // 10-2. ERP 시트
  const erpData = sortedObjects.map(obj => obj.erpRow);
  if (erpData.length > 0) {
    let erpSheet = spreadsheet.getSheetByName('erp');
    if (erpSheet) {
      spreadsheet.deleteSheet(erpSheet);
    }
    erpSheet = spreadsheet.insertSheet('erp');
    
    const erpColumns = erpData[0].length;
    erpSheet.getRange(1, 1, erpData.length, erpColumns).setValues(erpData);
    Logger.log(`ERP 시트: ${erpData.length}행 작성 완료`);
  }
  
  // 11. 처리 완료 후 폴더 비우기
  const filesToDelete = folder.getFiles();
  while (filesToDelete.hasNext()) {
    const file = filesToDelete.next();
    const fileName = file.getName().toLowerCase();
    if (fileName.endsWith('.html') || fileName.endsWith('.mhtml') || fileName.endsWith('.mht')) {
      file.setTrashed(true);
      Logger.log(`파일 삭제: ${file.getName()}`);
    }
  }
  
  // 12. 완료 메시지 표시 - ERP 업로드 안내 (토스트 - 비차단)
  SpreadsheetApp.getActiveSpreadsheet().toast(
    `완료! 결과: ${resultData.length}행, ERP: ${erpData.length}행\n이제 erp_upload_automation.py 실행하세요!`,
    '✅ 작업 완료',
    10  // 10초간 표시
  );
  
  Logger.log("=== 모든 파일 처리 완료 ===");
}

/**
 * 회사명 탐지 함수
 */
function detectCompany(allData, htmlContent) {
  // 1. HTML 전체 내용에서 먼저 찾기 (홈페이지 주소 등)
  if (htmlContent) {
    for (const [keyword, info] of Object.entries(COMPANY_MAPPING)) {
      if (htmlContent.includes(keyword)) {
        Logger.log(`HTML에서 회사명 발견: ${keyword} → 표시: ${info.display}, 브랜드: ${info.brand}`);
        return info;
      }
    }
  }
  
  // 2. 데이터 테이블에서 찾기
  for (const row of allData) {
    const colorStr = (row[2] || '').toString();
    const itemStr = (row[3] || '').toString();
    const combinedStr = colorStr + ' ' + itemStr;
    
    // 회사명 매핑 체크
    for (const [keyword, info] of Object.entries(COMPANY_MAPPING)) {
      if (combinedStr.includes(keyword)) {
        Logger.log(`데이터에서 회사명 발견: ${keyword} → 표시: ${info.display}, 브랜드: ${info.brand}`);
        return info;
      }
    }
  }
  
  Logger.log('회사명을 찾을 수 없음 - 기본값(예림) 사용');
  return { display: '예림', brand: 'y' };
}

/**
 * 회사명 접두사 추가 여부 판단
 */
function shouldAddCompanyPrefix(color, itemName, companyDisplay) {
  const colorStr = color.toString();
  const itemStr = itemName.toString();
  
  // 색상이나 품목명에 이미 회사 표시명이 있으면 추가 안함
  if (colorStr.includes(companyDisplay) || itemStr.includes(companyDisplay)) {
    return false;
  }
  
  // 다른 회사 표시명이 있는지도 체크
  for (const info of Object.values(COMPANY_MAPPING)) {
    if (colorStr.includes(info.display) || itemStr.includes(info.display)) {
      return false;
    }
  }
  
  return true;
}

/**
 * 품목명용 색상 전처리 (VER10)
 */
function preprocessColorForProductName(color) {
  // 방어 코드
  if (!color || color === undefined || color === null) {
    return '';
  }
  
  let colorStr = color.toString().trim();
  
  // VER10: 회사명 제거 전에 영림{숫자} 패턴 먼저 체크
  
  // 1순위: 영림{숫자} + 영문{숫자} → 공백 제거, 전부 출력
  if (/영림\d+\s+[A-Za-z]+\d+/.test(colorStr)) {
    return colorStr.replace(/\s+/g, '');
  }
  
  // 2순위: 영림{숫자} + 한글 → 영림{숫자}만 출력
  const younglimHangulMatch = colorStr.match(/^(영림\d+)\s+[가-힣]/);
  if (younglimHangulMatch) {
    return younglimHangulMatch[1];
  }
  
  // 3순위: 영림{숫자} → 그대로
  if (/^영림\d+$/.test(colorStr)) {
    return colorStr;
  }
  
  // VER10: 여기서 회사명 키워드 제거 (영림{숫자} 패턴이 아닌 경우만)
  for (const keyword of Object.keys(COMPANY_MAPPING)) {
    colorStr = colorStr.replace(keyword, '').trim();
  }
  
  // 4순위: 한글만 → 공백 제거, 전부 출력
  if (/^[가-힣\s]+$/.test(colorStr)) {
    return colorStr.replace(/\s+/g, '');
  }
  
  // 기타 → 그대로
  return colorStr;
}

/**
 * 품목명용 품명 전처리 (VER12: 평+숫자 패턴 추가)
 */
function preprocessItemNameForProductName(itemName, spec) {
  let itemStr = itemName.toString().trim();
  
  // VER12: "평+숫자" → "평숫자" 변환, MM 삭제
  // 예: "40MM평판" → "평40"
  const pyeongMatch = itemStr.match(/(\d+)MM평/);
  if (pyeongMatch) {
    itemStr = itemStr.replace(/\d+MM평판?/, `평${pyeongMatch[1]}`);
  }
  
  // "문틀" 삭제
  itemStr = itemStr.replace(/문틀/g, '').trim();
  
  // "(식기X)" 또는 "(식기O)" 삭제
  itemStr = itemStr.replace(/\(식기[XO]\)/g, '').trim();
  
  // 규격 첫번째 숫자 + 붙어있는 문자 패턴 제거 (VER08 추가)
  const specStr = spec.toString().trim();
  const firstNumberMatch = specStr.match(/^(\d+)/);
  
  if (firstNumberMatch) {
    const firstNumber = firstNumberMatch[1];
    // 품목명에서 "숫자+문자" 패턴 찾아서 제거
    // 예: "210바", "140형", "100바" 등
    const numberPatternRegex = new RegExp(firstNumber + '[가-힣]+', 'g');
    itemStr = itemStr.replace(numberPatternRegex, '').trim();
  }
  
  return itemStr;
}

/**
 * 품목명용 규격 전처리 (VER08)
 */
function preprocessSpecForProductName(spec) {
  const specStr = spec.toString().trim();
  
  // / N → 식기무
  if (/\/\s*N$/i.test(specStr)) {
    return specStr.replace(/\/\s*N$/i, '식기무');
  }
  
  // / S 또는 / Y → 식기유
  if (/\/\s*[SY]$/i.test(specStr)) {
    return specStr.replace(/\/\s*[SY]$/i, '식기유');
  }
  
  // / 문자 → 문자만
  if (/\/\s*([A-Za-z])$/i.test(specStr)) {
    return specStr.replace(/\/\s*([A-Za-z])$/i, '$1');
  }
  
  // / 만 있음 → 제거
  if (/\/\s*$/.test(specStr)) {
    return specStr.replace(/\/\s*$/, '').trim();
  }
  
  return specStr;
}

/**
 * 품목코드 생성 함수 (VER12-FIX4: 몰딩 추가)
 */
function generateProductCode(color, itemName, spec, remarks, brandCode) {
  try {
    // 1. 대상 분류
    const classification = classifyTarget(itemName);
    
    if (classification === 'NONE') {
      return ''; // 대상 분류 실패
    }
    
    // 1-1. 규격 크기 체크 (예외 규칙) - VER12: 몰딩은 체크 제외
    if (classification !== 'MOLDING' && !isValidSpecSize(spec)) {
      Logger.log(`규격 크기 예외: ${spec} - 코드 생성 제외`);
      return ''; // 규격이 작으면 코드 없음
    }
    
    // 2. 브랜드/색상코드 생성
    const brandColorCode = generateBrandColorCode(color, brandCode);
    if (!brandColorCode) {
      Logger.log(`브랜드/색상코드 생성 실패: color=${color}, brandCode=${brandCode}`);
      return '';
    }
    
    // 3. 플래그/모델코드 생성
    let flagModelCode = '';
    if (classification === 'FRAME') {
      flagModelCode = generateFlagCode(itemName);
    } else if (classification === 'DOOR') {
      flagModelCode = generateModelCode(itemName);
    } else if (classification === 'RAIL') {
      flagModelCode = generateRailCode(itemName);
    } else if (classification === 'MOLDING') {
      // VER12: 몰딩 플래그코드 생성
      flagModelCode = generateMoldingFlagCode(itemName);
    }
    
    // 4. 규격코드 생성
    let specCode = '';
    if (classification === 'MOLDING') {
      // VER12: 몰딩 전용 규격코드
      specCode = generateMoldingSpecCode(itemName, spec, remarks);
    } else {
      specCode = generateSpecCode(spec);
    }
    
    if (!specCode) return '';
    
    // 5. 최종 코드 조합
    const finalCode = brandColorCode + flagModelCode + specCode;
    Logger.log(`코드 생성: ${color} + ${itemName} + ${spec} → ${finalCode}`);
    
    return finalCode;
  } catch (e) {
    Logger.log(`코드 생성 오류: ${e.toString()}`);
    return '';
  }
}

/**
 * 규격 크기 체크 (VER08)
 */
function isValidSpecSize(spec) {
  if (!spec) return false;
  
  const specStr = spec.toString().trim();
  const numbers = specStr.match(/\d+/g);
  
  if (!numbers || numbers.length === 0) return false;
  
  // 모든 숫자 중 최대값이 999 이하면 false (부품/액세서리로 판단)
  const maxNumber = Math.max(...numbers.map(n => parseInt(n)));
  const isValid = maxNumber > 999;
  
  Logger.log(`규격 크기 체크: ${spec} → 최대값: ${maxNumber} → ${isValid ? '정상' : '예외'}`);
  
  return isValid;
}

/**
 * 대상 분류 (문틀/문짝/레일/몰딩) - VER12-FIX4: 기둥 추가
 * 우선순위: 문틀 > 레일 > 문짝 > 몰딩
 */
function classifyTarget(itemName) {
  const itemStr = itemName.toString().trim();
  
  // 문틀 키워드
  const frameKeywords = ['문틀', '발포', '분리형', '스토퍼'];
  const hasFrame = frameKeywords.some(kw => itemStr.includes(kw));
  
  // 문짝 키워드
  const doorKeywords = ['문짝', 'ABS', '도어', 'M/D', '민무늬', '탈공', '미서기', '미닫이'];
  const hasDoor = doorKeywords.some(kw => itemStr.includes(kw));
  
  // VER11 수정: 문짝 패턴 - 영문+숫자 조합 허용
  const doorPatterns = /YS-[A-Z0-9]+|YA-[A-Z0-9]+|YAT-[A-Z0-9]+|EZ-[A-Z0-9]+|LS-[A-Z0-9]+|YM-[A-Z0-9]+|YAL-[A-Z0-9]+|YV-[A-Z0-9]+|YFL-[A-Z0-9]+|SW-[A-Z0-9]+|TD-[A-Z0-9]+|SL-[A-Z0-9]+/;
  const hasDoorPattern = doorPatterns.test(itemStr);
  
  // 연동 키워드
  const hasYeondong = /\d+연동/.test(itemStr);
  
  // 레일 키워드
  const hasRail = itemStr.includes('레일');
  
  // VER12-FIX4: 몰딩 키워드 (기둥 추가)
  const moldingKeywords = ['몰딩', '평', '코너', '계단', '천정', '천장', '걸레', '문선', '보드', '루버', '루바', '기둥'];
  const hasMolding = moldingKeywords.some(kw => itemStr.includes(kw));
  
  // 우선순위: 문틀 > 레일 > 문짝 > 몰딩
  if (hasFrame) {
    return 'FRAME';
  }
  
  // 레일 조건 (연동 조건 제거)
  if (hasRail && !hasDoor && !hasDoorPattern) {
    return 'RAIL';
  }
  
  if (hasDoor || hasDoorPattern || hasYeondong) {
    return 'DOOR';
  }
  
  // VER12: 몰딩 (마지막 순위)
  if (hasMolding) {
    return 'MOLDING';
  }
  
  return 'NONE';
}

/**
 * 브랜드/색상코드 생성 (VER11)
 */
function generateBrandColorCode(color, brandCode) {
  let colorStr = color.toString().trim();
  const brand = brandCode; // 'Y', 'W', 'y' 등
  
  // VER09: 회사명 키워드 제거
  for (const keyword of Object.keys(COMPANY_MAPPING)) {
    colorStr = colorStr.replace(keyword, '').trim();
  }
  
  Logger.log(`브랜드/색상코드 생성: 원본="${color}", 전처리 후="${colorStr}", 브랜드="${brand}"`);
  
  // 1순위: 영림{숫자}PS{숫자} → 브랜드 + 숫자 (PS 제거)
  const younglimPsMatch = colorStr.match(/영림(\d+)PS\d+/);
  if (younglimPsMatch) {
    return brand + younglimPsMatch[1];
  }
  
  // 2순위: PS{문자+숫자} → 브랜드 + S + 문자+숫자
  const psMatch = colorStr.match(/^PS(.+)$/);
  if (psMatch) {
    return brand + 'S' + psMatch[1];
  }
  
  // 3순위: PX{문자+숫자} → 브랜드 + X + 문자+숫자 (VER11 추가)
  const pxMatch = colorStr.match(/^PX(.+)$/);
  if (pxMatch) {
    return brand + 'X' + pxMatch[1];
  }
  
  // 4순위: 영림{숫자} → 브랜드 + 숫자
  const younglimMatch = colorStr.match(/영림(\d+)/);
  if (younglimMatch) {
    return brand + younglimMatch[1];
  }
  
  // 5순위: 한글만 (공백 포함) → 브랜드 + 한글 2글자 (공백 제거 후)
  if (/^[가-힣\s]+$/.test(colorStr)) {
    const cleanedColor = colorStr.replace(/\s+/g, '');
    const result = brand + cleanedColor.substring(0, 2);
    Logger.log(`한글 색상 처리: "${colorStr}" → 공백제거 "${cleanedColor}" → "${result}"`);
    return result;
  }
  
  // 6순위: 기타 숫자 포함 → 브랜드 + 숫자
  const numberMatch = colorStr.match(/(\d+)/);
  if (numberMatch) {
    return brand + numberMatch[1];
  }
  
  Logger.log(`브랜드/색상코드 생성 실패: 처리할 수 있는 패턴 없음 (colorStr="${colorStr}")`);
  return '';
}

/**
 * 문틀 플래그코드 생성 (VER08)
 */
function generateFlagCode(itemName) {
  const itemStr = itemName.toString().trim();
  
  // 상위 카테고리 확인
  let upperCode = '';
  if (itemStr.includes('발포')) {
    upperCode = 'B';
  } else if (itemStr.includes('방염')) {
    upperCode = 'F';
  } else if (itemStr.includes('비방염')) {
    upperCode = 'N';
  } else if (itemStr.includes('알루미늄')) {
    upperCode = 'A';
  }
  
  // 하위 카테고리 확인
  let lowerCode = '';
  
  // 발포의 하위
  if (itemStr.includes('슬림와이드')) {
    lowerCode = 'I';
  } else if (itemStr.includes('와이드')) {
    lowerCode = 'W';
  } else if (itemStr.includes('슬림')) {
    lowerCode = 'S';
  } else if (itemStr.includes('차음')) {
    lowerCode = 'E';
  } else if (itemStr.includes('일반형')) {
    lowerCode = 'G';
  }
  // 방염/비방염의 하위
  else if (itemStr.includes('가변형')) {
    lowerCode = 'K';
  } else if (itemStr.includes('분리형') || itemStr.includes('스토퍼')) {
    lowerCode = 'D';
  } else if (itemStr.includes('일체')) {
    lowerCode = 'B';
  } else if (itemStr.includes('히든')) {
    lowerCode = 'H';
  } else if (itemStr.includes('스텝')) {
    lowerCode = 'T';
  } else if (itemStr.includes('무메') || itemStr.includes('무매')) {
    lowerCode = 'M';
  } else if (itemStr.includes('미서기') || itemStr.includes('미닫이')) {
    lowerCode = 'L';
  }
  
  // 하위카테고리만 있고 상위카테고리가 없으면 비방염(N)
  if (!upperCode && lowerCode) {
    upperCode = 'N';
  }
  
  // 상위 없으면 코드 생성 안함
  if (!upperCode) {
    return '';
  }
  
  // 연동 체크 (예외 규칙)
  const yeondongMatch = itemStr.match(/(\d+)연동/);
  
  // 예외: 방염/비방염/알루미늄 + *연동 → 상위 + *C (다른 하위 무시)
  if ((upperCode === 'F' || upperCode === 'N' || upperCode === 'A') && yeondongMatch) {
    return upperCode + yeondongMatch[1] + 'C';
  }
  
  return upperCode + lowerCode;
}

/**
 * 문짝 모델코드 생성 (VER11 수정)
 */
function generateModelCode(itemName) {
  const itemStr = itemName.toString().trim();
  
  // VER11 수정: 영문-패턴 → 영문+숫자만 추출 (한글 제거)
  const patternMatch = itemStr.match(/([A-Z]+)-([A-Z0-9]+)/);
  
  if (patternMatch) {
    const prefix = patternMatch[1];  // 영문 부분 (YS, YA 등)
    let suffix = patternMatch[2];    // 하이픈 뒤 부분
    
    // VER11: 한글이 나타나면 그 전까지만 추출
    const hangulIndex = suffix.search(/[가-힣]/);
    if (hangulIndex !== -1) {
      suffix = suffix.substring(0, hangulIndex);
    }
    
    const result = prefix + suffix;
    Logger.log(`영문-패턴 추출: "${itemStr}" → "${result}"`);
    return result;
  }
  
  // 2순위: 탈공 → 탈
  if (itemStr.includes('탈공')) {
    return '탈';
  }
  
  // 3순위: M/D + 민무늬 → MD
  if (itemStr.includes('M/D') && itemStr.includes('민무늬')) {
    return 'MD';
  }
  
  // 4순위: *도어 → 도어 앞 문자
  const doorMatch = itemStr.match(/(\S+)도어/);
  if (doorMatch && doorMatch[1]) {
    return doorMatch[1];
  }
  
  return '';
}

/**
 * 레일 코드 생성 (VER10)
 */
function generateRailCode(itemName) {
  const itemStr = itemName.toString().trim();
  
  // 연동 숫자 추출
  const yeondongMatch = itemStr.match(/(\d+)연동/);
  const yeondongNum = yeondongMatch ? yeondongMatch[1] : '';
  
  // === 연동 패턴이 있을 때 ===
  if (yeondongNum) {
    let slimCode = '';
    if (itemStr.includes('초슬림')) {
      slimCode = 'SS';
    } else if (itemStr.includes('슬림')) {
      slimCode = 'S';
    }
    return slimCode + yeondongNum + '레일';
  }
  
  // === 연동 패턴이 없을 때 ===
  let prefix = '';
  
  // 슬림/초슬림 체크 (초슬림 우선!)
  if (itemStr.includes('초슬림')) {
    prefix += 'SS';
  } else if (itemStr.includes('슬림')) {
    prefix += 'S';
  }
  
  // 상부/하부 체크
  if (itemStr.includes('상부')) {
    prefix += '상';
  } else if (itemStr.includes('하부')) {
    prefix += '하';
  }
  
  return prefix + '레일';
}

/**
 * 몰딩 플래그코드 생성 (VER12-FIX4)
 */
function generateMoldingFlagCode(itemName) {
  const itemStr = itemName.toString().trim();
  
  // 수정1: 천장 키워드 우선 추출
  if (itemStr.includes('천장')) {
    Logger.log(`몰딩 플래그코드 (천장): "${itemStr}" → "천장"`);
    return '천장';
  }
  
  // 수정4: 프레임몰딩/프레임 처리
  if (itemStr.includes('프레임몰딩') || itemStr.includes('프레임')) {
    Logger.log(`몰딩 플래그코드 (프레임): "${itemStr}" → "프레임"`);
    return '프레임';
  }
  
  // 수정4: 기둥 처리
  if (itemStr.includes('기둥')) {
    Logger.log(`몰딩 플래그코드 (기둥): "${itemStr}" → "기둥"`);
    return '기둥';
  }
  
  // 템바보드/템바루바 예외 처리 (업데이트2)
  if (itemStr.includes('템바보드') || itemStr.includes('템바루바')) {
    let code = '';
    
    // 수정2: 방염만 F 추가, 비방염은 생략
    if (itemStr.includes('방염') && !itemStr.includes('비방염')) {
      code += 'F';
    }
    // 비방염일 때는 아무것도 추가 안함 (N 생략)
    
    // "형" 제거 후 패턴 추출
    let cleanStr = itemStr.replace(/형/g, '');
    
    // 패턴 추출
    if (cleanStr.includes('소반달') || cleanStr.includes('소형반달')) {
      code += '소반달';
    } else if (cleanStr.includes('대반달') || cleanStr.includes('대형반달')) {
      code += '대반달';
    } else if (cleanStr.includes('소직각') || cleanStr.includes('소형직각')) {
      code += '소직각';
    } else if (cleanStr.includes('직각대') || cleanStr.includes('대형직각')) {
      code += '직각대';
    } else if (cleanStr.includes('역반달')) {
      code += '역반달';
    }
    
    // TB 또는 TL 추가 (맨 뒤)
    if (itemStr.includes('템바보드')) {
      code += 'TB';
    } else if (itemStr.includes('템바루바')) {
      code += 'TL';
    }
    
    Logger.log(`템바보드/루바 플래그코드: "${itemStr}" → "${code}"`);
    return code;
  }
  
  // 일반 몰딩 (업데이트1)
  let code = itemStr;
  
  // "몰딩", "받이" 제거, "평판" → "평" 축약
  code = code.replace(/몰딩/g, '')
            .replace(/받이/g, '')
            .replace(/평판/g, '평')
            .trim();
  
  // 숫자+MM 패턴 제거 (예: "60MM" 제거)
  code = code.replace(/\d+MM\s*/g, '').trim();
  
  // 괄호와 내용물 제거
  code = code.replace(/\([^)]*\)/g, '').trim();
  
  // 숫자만 있는 경우 제거 (예: "901" → "")
  code = code.replace(/^\d+\s*/, '').trim();
  
  Logger.log(`몰딩 플래그코드: "${itemStr}" → "${code}"`);
  return code;
}

/**
 * 몰딩 규격코드 생성 (VER12-FIX4)
 */
function generateMoldingSpecCode(itemName, spec, remarks) {
  const itemStr = itemName.toString().trim();
  const specStr = spec.toString().trim();
  const remarksStr = remarks.toString().trim();
  
  // 수정4: 프레임몰딩 - 프레임 뒤의 숫자만 추출
  if (itemStr.includes('프레임몰딩') || itemStr.includes('프레임')) {
    const frameMatch = itemStr.match(/프레임[^\d]*(\d+)/);
    if (frameMatch) {
      Logger.log(`몰딩 규격 (프레임): "${itemStr}" → "${frameMatch[1]}"`);
      return frameMatch[1];
    }
  }
  
  // 수정4: 기둥 - (숫자*숫자*숫자) 패턴, *9 제거
  if (itemStr.includes('기둥')) {
    // 규격열 또는 품명에서 (숫자*숫자*숫자) 패턴 찾기
    const tripleMatch = specStr.match(/\((\d+)\*(\d+)\*(\d+)\)/) || 
                       itemStr.match(/\((\d+)\*(\d+)\*(\d+)\)/);
    
    if (tripleMatch) {
      const num1 = tripleMatch[1];
      const num2 = tripleMatch[2];
      const num3 = tripleMatch[3];
      
      // *9는 제거 (마지막 숫자가 9이면 제외)
      if (num3 === '9') {
        const result = num1 + num2;
        Logger.log(`몰딩 규격 (기둥): "${itemStr}" → "${result}" (*9 제거)`);
        return result;
      }
      
      const result = num1 + num2 + num3;
      Logger.log(`몰딩 규격 (기둥): "${itemStr}" → "${result}"`);
      return result;
    }
  }
  
  // 1순위: 규격열의 () 안에 *를 포함한 숫자 패턴
  const specParenMatch = specStr.match(/\((\d+)\*(\d+)\)/);
  if (specParenMatch) {
    const num1 = specParenMatch[1];
    const num2 = specParenMatch[2];
    
    // *9는 제거
    if (num2 === '9') {
      Logger.log(`몰딩 규격 (규격열): "${specStr}" → "${num1}" (*9 제거)`);
      return num1;
    }
    
    const result = num1 + num2;
    Logger.log(`몰딩 규격 (규격열): "${specStr}" → "${result}"`);
    return result;
  }
  
  // 2순위: 품명의 () 안에 *를 포함한 숫자 패턴
  const itemParenMatch = itemStr.match(/\((\d+)\*(\d+)\)/);
  if (itemParenMatch) {
    const num1 = itemParenMatch[1];
    const num2 = itemParenMatch[2];
    
    // *9는 제거
    if (num2 === '9') {
      Logger.log(`몰딩 규격 (품명): "${itemStr}" → "${num1}" (*9 제거)`);
      return num1;
    }
    
    const result = num1 + num2;
    Logger.log(`몰딩 규격 (품명): "${itemStr}" → "${result}"`);
    return result;
  }
  
  // 3순위: 비고열에서 숫자*숫자 패턴
  const remarksStarMatch = remarksStr.match(/(\d+)\*(\d+)/);
  if (remarksStarMatch) {
    const num1 = remarksStarMatch[1];
    const num2 = remarksStarMatch[2];
    
    // *9는 제거
    if (num2 === '9') {
      Logger.log(`몰딩 규격 (비고): "${remarksStr}" → "${num1}" (*9 제거)`);
      return num1;
    }
    
    const result = num1 + num2;
    Logger.log(`몰딩 규격 (비고): "${remarksStr}" → "${result}"`);
    return result;
  }
  
  // 4순위: 품명의 (숫자T) 패턴
  const itemTMatch = itemStr.match(/\((\d+)T\)/i);
  if (itemTMatch) {
    // MM평판 패턴에서 숫자 추출
    const mmMatch = itemStr.match(/(\d+)MM/);
    if (mmMatch) {
      const result = mmMatch[1] + itemTMatch[1];
      Logger.log(`몰딩 규격 (T패턴-품명): "${itemStr}" → "${result}"`);
      return result;
    }
  }
  
  // 5순위: 비고의 숫자T 패턴
  const remarksTMatch = remarksStr.match(/(\d+)T/i);
  if (remarksTMatch) {
    // 품명에서 MM평판 패턴 찾기
    const mmMatch = itemStr.match(/(\d+)MM/);
    if (mmMatch) {
      const result = mmMatch[1] + remarksTMatch[1];
      Logger.log(`몰딩 규격 (T패턴-비고): 품명="${itemStr}", 비고="${remarksStr}" → "${result}"`);
      return result;
    }
  }
  
  // 6순위: 품명에 템바보드/템바루바 + 숫자*숫자 (괄호 없음)
  if (itemStr.includes('템바보드') || itemStr.includes('템바루바')) {
    const match = itemStr.match(/(\d+)\*(\d+)/);
    if (match) {
      const result = match[1] + match[2];
      Logger.log(`몰딩 규격 (템바): "${itemStr}" → "${result}"`);
      return result;
    }
  }
  
  // 7순위: 품명에서 "숫자바용" 또는 "숫자번" 패턴
  const itemNumMatch = itemStr.match(/(\d+)(?:바용|번)/);
  if (itemNumMatch) {
    Logger.log(`몰딩 규격 (바용/번): "${itemStr}" → "${itemNumMatch[1]}"`);
    return itemNumMatch[1];
  }
  
  // 8순위: 품명에서 "숫자MM평판" 패턴 (규격이 없는 경우)
  const mmMatch = itemStr.match(/(\d+)MM평판?/);
  if (mmMatch) {
    Logger.log(`몰딩 규격 (MM평판): "${itemStr}" → "${mmMatch[1]}"`);
    return mmMatch[1];
  }
  
  // 9순위: 규격열에 단순 숫자만 있는 경우
  const simpleNumber = specStr.match(/^(\d+)$/);
  if (simpleNumber) {
    Logger.log(`몰딩 규격 (단순숫자): "${specStr}" → "${simpleNumber[1]}"`);
    return simpleNumber[1];
  }
  
  Logger.log(`몰딩 규격 생성 실패: itemName="${itemName}", spec="${spec}", remarks="${remarks}"`);
  return '';
}

/**
 * 규격코드 생성 (VER08)
 */
function generateSpecCode(spec) {
  if (!spec) return '';
  
  const specStr = spec.toString().trim();
  
  // 숫자 추출
  const numbers = specStr.match(/\d+/g);
  if (!numbers || numbers.length === 0) return '';
  
  let result = numbers.join('');
  
  // "/" 이후 문자 추출
  const slashMatch = specStr.match(/\/\s*([A-Za-z]+)/);
  if (slashMatch && slashMatch[1]) {
    result += slashMatch[1].trim();
  }
  
  return result;
}

/**
 * 단위 생성 (VER12-FIX4: 몰딩 추가)
 */
function generateUnit(itemName, spec, remarks) {
  const itemStr = itemName.toString().trim();
  const specStr = spec.toString().trim();
  const remarksStr = remarks.toString().trim();
  
  // 규격 또는 비고에 숫자 없으면 단위 없음
  if (!/\d/.test(specStr) && !/\d/.test(remarksStr) && !/\d/.test(itemStr)) {
    return '';
  }
  
  // classifyTarget 함수로 분류 (재사용)
  const classification = classifyTarget(itemStr);
  
  // 레일 → 개
  if (classification === 'RAIL') {
    return '개';
  }
  
  // 문틀 → 틀 또는 개 (VER11: 예외 규칙 추가)
  if (classification === 'FRAME') {
    // VER11: 규격이 특정 형태면 "개"로 변경
    // 패턴: 숫자* 또는 숫자*/ 또는 숫자*숫자* 또는 숫자*숫자*/
    if (/^\d+\*\/?$/.test(specStr) || /^\d+\*\d+\*\/?$/.test(specStr)) {
      Logger.log(`문틀 단위 예외: ${specStr} → 개`);
      return '개';
    }
    return '틀';
  }
  
  // 문짝 → 짝
  if (classification === 'DOOR') {
    return '짝';
  }
  
  // VER12-FIX4: 몰딩 → EA (기본), 롤 (템바보드), BOX (템바루바)
  if (classification === 'MOLDING') {
    if (itemStr.includes('템바보드')) {
      return '롤';
    } else if (itemStr.includes('템바루바')) {
      return 'BOX';
    } else {
      return 'EA';
    }
  }
  
  return '';
}

/**
 * MHTML에서 HTML 추출
 */
function extractHtmlFromMhtml(mhtmlContent) {
  try {
    const patterns = [
      /Content-Type:\s*text\/html[\s\S]*?\r?\n\r?\n([\s\S]*?)(?=\r?\n--|Content-Type:|$)/i,
      /(<html[\s\S]*?<\/html>)/i,
      /(<\!DOCTYPE[\s\S]*?<\/html>)/i
    ];

    let htmlContent = "";
    for (const pattern of patterns) {
      const match = mhtmlContent.match(pattern);
      if (match && match[1]) {
        htmlContent = match[1].trim();
        break;
      }
    }

    if (!htmlContent && mhtmlContent.includes('<table')) {
      htmlContent = mhtmlContent;
    }

    if (!htmlContent) {
      Logger.log("HTML 내용을 찾을 수 없음");
      return "";
    }

    htmlContent = decodeQuotedPrintableFixed(htmlContent);
    Logger.log("MHTML에서 HTML 추출 및 디코딩 성공");
    return htmlContent;
  } catch (e) {
    Logger.log(`MHTML 추출 중 오류: ${e.toString()}`);
    return "";
  }
}

/**
 * Quoted-Printable 디코딩
 */
function decodeQuotedPrintableFixed(str) {
  try {
    let result = str
      .replace(/=\r?\n/g, '')
      .replace(/=3D/g, '=')
      .replace(/=20/g, ' ');
    
    result = result.replace(/(=[0-9A-F]{2})+/gi, function(match) {
      try {
        const urlEncoded = match.replace(/=/g, '%');
        return decodeURIComponent(urlEncoded);
      } catch (e) {
        return match;
      }
    });
    
    return result;
  } catch (e) {
    Logger.log(`디코딩 오류: ${e.toString()}`);
    return str;
  }
}

/**
 * HTML 테이블 파싱 (VER08)
 */
function parseHtmlTable(htmlContent) {
  let allResultData = [];
  
  // 모든 table.table-item 찾기 (matchAll 사용)
  const tableRegex = /<table[^>]*class="[^"]*table-item[^"]*"[^>]*>[\s\S]*?<tbody>([\s\S]*?)<\/tbody>[\s\S]*?<\/table>/gi;
  const allMatches = [...htmlContent.matchAll(tableRegex)];
  
  if (allMatches.length === 0) {
    Logger.log("table-item 클래스 테이블 없음, 대안 패턴 시도");
    
    // 대안: 모든 테이블 찾기
    const allTableRegex = /<table[^>]*>([\s\S]*?)<\/table>/gi;
    let match;
    let tableIndex = 0;
    
    while ((match = allTableRegex.exec(htmlContent)) !== null) {
      tableIndex++;
      const tableContent = match[1];
      
      if (tableContent.includes('<td') && />\s*\d+\s*</.test(tableContent)) {
        Logger.log(`테이블 ${tableIndex}에서 데이터 발견, 처리 시도`);
        
        const tbodyMatch = tableContent.match(/<tbody>([\s\S]*?)<\/tbody>/i);
        const bodyContent = tbodyMatch ? tbodyMatch[1] : tableContent;
        
        const parsedData = parseTableBody(bodyContent);
        if (parsedData.length > 0) {
          Logger.log(`테이블 ${tableIndex}에서 ${parsedData.length}개 행 추출 성공`);
          allResultData = allResultData.concat(parsedData);
        }
      }
    }
    
    if (allResultData.length === 0) {
      Logger.log("모든 테이블 파싱 실패");
    }
    
    return allResultData;
  }
  
  // table-item 클래스 테이블들 처리
  Logger.log(`${allMatches.length}개의 table-item 테이블 발견`);
  
  allMatches.forEach((match, index) => {
    const tableBody = match[1];
    Logger.log(`테이블 ${index + 1} 파싱 시작`);
    const parsedData = parseTableBody(tableBody);
    if (parsedData.length > 0) {
      Logger.log(`테이블 ${index + 1}에서 ${parsedData.length}개 행 추출`);
      allResultData = allResultData.concat(parsedData);
    }
  });
  
  Logger.log(`총 ${allResultData.length}개 데이터 행 추출됨 (전체 테이블)`);
  return allResultData;
}

/**
 * 테이블 body 파싱 (VER08)
 */
function parseTableBody(tableBody) {
  const resultData = [];
  const rowRegex = /<tr[\s\S]*?>([\s\S]*?)<\/tr>/g;
  let rowMatch;
  let rowCount = 0;

  while ((rowMatch = rowRegex.exec(tableBody)) !== null) {
    rowCount++;
    const rowHtml = rowMatch[1];
    
    if (rowHtml.includes('td-header') || rowHtml.includes('<th')) {
      Logger.log(`행 ${rowCount}: 헤더 행 건너뜀`);
      continue;
    }
    
    const columnRegex = /<t[hd][^>]*>([\s\S]*?)<\/t[hd]>/g;
    const rowDataRaw = [];
    let columnMatch;
    
    while ((columnMatch = columnRegex.exec(rowHtml)) !== null) {
      let cellContent = columnMatch[1];
      
      const divMatch = cellContent.match(/<div[^>]*>([\s\S]*?)<\/div>/);
      if (divMatch && divMatch[1]) {
        cellContent = divMatch[1];
      }
      
      cellContent = cellContent
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .trim();
      
      rowDataRaw.push(cellContent);
    }
    
    const hasData = rowDataRaw.some(cell => cell.trim() !== '');
    const isNotTotal = (rowDataRaw[0] || '').trim() !== '합계';
    
    if (!hasData || !isNotTotal) {
      continue;
    }
    
    if (rowDataRaw.length < 4) {
      continue;
    }
    
    if (rowDataRaw[0] && !/^\d+$/.test(rowDataRaw[0].trim())) {
      continue;
    }
    
    // 색상 값 추출 - 원본 그대로 저장
    let colorVal = rowDataRaw[1] ? rowDataRaw[1].trim() : '';

    const productName = `${colorVal} ${rowDataRaw[2] || ''} ${rowDataRaw[3] || ''}`.trim();

    const newRow = [
      rowDataRaw[0] || '',          // NO
      productName,                  // 품목명 (조합)
      colorVal,                     // 색상
      rowDataRaw[2] || '',          // 품명
      rowDataRaw[3] || '',          // 규격
      rowDataRaw[4] || '',          // 수량
      rowDataRaw[5] || '',          // 단가
      rowDataRaw[6] || '',          // 금액
      rowDataRaw[7] || ''           // 비고
    ];

    resultData.push(newRow);
    Logger.log(`행 ${rowCount}: 데이터 추가 - 품목명: ${productName}`);
  }

  Logger.log(`총 ${resultData.length}개 데이터 행 추출됨`);
  return resultData;
}

/**
 * 처리된 파일 로그 초기화
 */
function clearProcessedLog() {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  const logSheet = spreadsheet.getSheetByName(LOG_SHEET_NAME);
  if (logSheet) {
    logSheet.clear();
    logSheet.appendRow(["File ID", "File Name", "Processed Date"]);
    Logger.log("처리 로그 초기화 완료");
  }
}