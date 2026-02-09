import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. 아까 받은 열쇠로 인증하기
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", scope)
client = gspread.authorize(creds)

# 2. Academy_DB 라는 엑셀 파일 열기
try:
    sheet = client.open("Academy_DB").sheet1
    # 3. A1 칸에 글씨 써보기
    sheet.update_cell(1, 1, "M4 맥 미니에서 보낸 메시지")
    print("✅ 성공! 구글 시트를 확인해보세요.")
except Exception as e:
    print("❌ 실패...", e)