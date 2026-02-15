# Windows 로그라이크 선택지 매크로

이 프로젝트는 **앱플레이어 위에서 실행되는 게임**에서 선택지를 자동으로 찾고 클릭하는 도구입니다.

## 지원 기능
- 이미지 기반 선택지 클릭
  - 선택지 이미지를 미리 등록
  - 화면에서 템플릿 매칭(OpenCV)으로 위치 탐지 후 자동 클릭
- 텍스트 기반 선택지 클릭
  - OCR(Tesseract)로 화면 텍스트 분석
  - 키워드가 포함된 텍스트 위치를 자동 클릭
- 클릭 방식
  - 앱플레이어 API가 아니라 **실제 Windows 커서 클릭(pyautogui)**
- 설정 저장
  - `macro_config.json`에 템플릿/키워드/경로 설정 저장

---

## 최종 파일(EXE) 받는 가장 쉬운 방법
Python 설치 없이 쓰려면 `RogueMacro.exe`가 필요합니다.

### 방법 A) GitHub Actions로 EXE 자동 생성 (권장)
1. GitHub 저장소 → **Actions** 탭
2. **Build Windows EXE** 워크플로 선택
3. **Run workflow** 클릭
4. 완료 후 Artifacts에서 `RogueMacro-exe` 다운로드
5. 압축 해제 후 `RogueMacro.exe` 실행

> 이 방법은 Windows 빌드 서버에서 자동으로 exe를 만들어 줍니다.

### 방법 B) Windows PC에서 더블클릭 빌드
1. 이 프로젝트를 Windows에 내려받기
2. `build_windows_exe.bat` 더블클릭
3. 완료 후 `dist\RogueMacro.exe` 실행

---

## 사용 방법
1. `RogueMacro.exe` 실행
2. 앱플레이어/게임을 화면에 띄움
3. 이미지 모드
   - `이미지 추가`로 선택지 스크린샷 등록
   - 필요 시 `이미지 모드 목표 이름` 입력
   - `이미지 모드 시작`
4. 텍스트 모드
   - Tesseract 경로 확인
   - 키워드 입력(쉼표 구분)
   - `텍스트 모드 시작`
5. 중지는 `중지` 버튼 또는 마우스를 좌상단(0,0) 이동(FAILSAFE)

## OCR 준비물 (텍스트 모드)
- Tesseract 설치: https://github.com/UB-Mannheim/tesseract/wiki
- 기본 경로: `C:\Program Files\Tesseract-OCR\tesseract.exe`

## 주의
- 게임 정책/약관에 따라 자동화 도구 사용이 제한될 수 있습니다.
- OCR 인식률은 해상도/폰트/배경/언어 설정에 영향을 받습니다.
