import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

print("--- 🕵️‍♂️ [hsjg Academy-ERP] 연결 진단 시작 ---")

# 1. secrets.json 파일이 있는지 확인
if not os.path.exists("secrets.json"):
    print("❌ [실패] 폴더에 'secrets.json' 파일이 없습니다!")
    print("👉 다운로드 받은 키 파일을 이 폴더로 옮기고 이름을 secrets.json으로 바꿔주세요.")
    exit()
else:
    print("✅ [통과] secrets.json 파일 존재함")

try:
    # 2. 인증 시도 및 이메일 확인
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", scope)
    client = gspread.authorize(creds)
    
    robot_email = creds.service_account_email
    print(f"✅ [통과] 인증 성공! (로봇 이름: {robot_email})")
    
    # 3. 구글 시트 찾기
    print("⏳ 'Academy_DB' 시트를 찾는 중...")
    sheet = client.open("Academy_DB").sheet1
    print("✅ [통과] 시트 찾기 성공!")

    # 4. 쓰기 테스트
    sheet.update_cell(1, 1, "연결 성공했습니다!")
    print("🎉 [최종 성공] 구글 시트 A1 칸을 확인해보세요. 글자가 바뀌었을 겁니다.")

except gspread.exceptions.SpreadsheetNotFound:
    print("\n❌ [치명적 오류] 'Academy_DB' 시트를 찾을 수 없습니다!")
    print("--- 해결 방법 ---")
    print(f"1. 구글 시트 제목이 정확히 'Academy_DB'인지 확인하세요. (띄어쓰기 주의)")
    print(f"2. 구글 시트 [공유] 버튼을 누르고 아래 이메일이 추가되어 있는지 확인하세요.")
    print(f"👉 추가해야 할 이메일: {robot_email}")
    
except Exception as e:
    print(f"\n❌ [기타 오류] {e}")