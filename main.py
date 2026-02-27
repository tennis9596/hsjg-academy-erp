import streamlit as st
from streamlit_option_menu import option_menu
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import json
import time
import qrcode
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import os
import calendar
import os
import time

# [중요] 시스템 전체 시간을 한국 시간(KST)으로 강제 고정
# 리눅스 기반인 스트림릿 클라우드 서버에서만 작동하며, 윈도우 로컬에서는 무시됩니다.
try:
    os.environ['TZ'] = 'Asia/Seoul'
    time.tzset()
except AttributeError:
    # 윈도우 환경에서는 tzset이 없으므로 에러를 방지합니다.
    pass

# ==========================================
# [기본 설정] 페이지 및 스타일
# ==========================================
st.set_page_config(page_title="형설지공 학원 ERP", page_icon="🏫", layout="wide")

st.markdown("""
<style>
    /* 0. 다크모드 무시 및 전체 배경/글자색 강제 고정 */
    /* 기기가 다크모드여도 배경은 흰색, 글자는 검은색으로 보이게 합니다. */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }
    
    /* 사이드바 색상 고정 */
    [data-testid="stSidebar"] {
        background-color: #f0f2f6 !important;
    }
    [data-testid="stSidebar"] * {
        color: #000000 !important;
    }

    /* 1. 인쇄 모드 설정 */
    @media print {
        [data-testid="stSidebar"], header, footer, .stButton, .no-print { display: none !important; }
        .block-container { padding: 0 !important; max-width: 100% !important; }
    }

    /* 2. 대시보드 현황 카드 스타일 */
    .metric-card {
        background-color: #FFFFFF !important; 
        border: 1px solid #E0E0E0 !important; 
        border-radius: 10px;
        padding: 20px; text-align: center; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        color: #000000 !important;
    }
    .metric-title { font-size: 1rem; color: #424242 !important; margin-bottom: 5px; font-weight: 500; }
    .metric-value { font-size: 2rem; font-weight: 800; color: #1565C0 !important; }

    /* 3. 카드형 시간표 스타일 (정규/보강 공통) */
    .class-card {
        border-radius: 8px;
        padding: 8px; margin-bottom: 5px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        min-height: 100px; display: flex; flex-direction: column; justify-content: center;
        color: #000000 !important; /* 내부 글자색 검정 고정 */
    }
    .cc-subject { font-size: 0.8rem; color: #424242 !important; font-weight: bold; }
    .cc-name { font-size: 1.05rem; color: #000000 !important; font-weight: 800; margin-bottom: 3px; }
    .cc-info { font-size: 0.85rem; color: #212121 !important; }
    .cc-time { font-size: 0.9rem; color: #1565C0 !important; font-weight: 700; margin-top: 3px; }
    .cc-duration { font-size: 0.8rem; color: #E65100 !important; font-weight: 600; }
    
    .empty-card { 
        background-color: #FAFAFA !important; 
        border: 2px dashed #E0E0E0 !important; 
        border-radius: 8px; 
        min-height: 100px; 
    }
    
    .time-axis-card {
        background-color: #263238 !important; 
        color: white !important; 
        border-radius: 8px;
        min-height: 100px; display: flex; flex-direction: column; align-items: center; justify-content: center;
        padding: 5px; margin-bottom: 5px;
    }
    .tac-start { font-size: 1.1rem; font-weight: 800; color: #FFD54F !important; }
    .tac-tilde { font-size: 0.8rem; margin: 2px 0; color: #BDBDBD !important; }
    .tac-end { font-size: 1.0rem; font-weight: 600; color: #FFFFFF !important; }

    .day-header { 
        text-align: center; font-weight: 800; 
        background-color: #f1f3f5 !important; 
        color: #212121 !important;
        padding: 10px 0; border-radius: 5px; margin-bottom: 10px; 
    }
    
    /* 4. 달력 스타일 */
    .cal-table { width: 100%; border-collapse: collapse; margin-top: 10px; color: #000000 !important; }
    .cal-th { background-color: #eee !important; color: #000 !important; padding: 5px; text-align: center; font-weight: bold; border: 1px solid #ddd; }
    .cal-td { height: 80px; vertical-align: top; border: 1px solid #ddd; padding: 5px; font-size: 0.9rem; position: relative; background-color: #FFF !important; }
    .cal-day-num { font-weight: bold; margin-bottom: 3px; display: block; color: #333 !important; }
    
    /* 5. 알림 메시지 */
    .custom-alert { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background-color: rgba(46, 125, 50, 0.95); color: white !important; padding: 25px 50px; border-radius: 15px; font-size: 22px; font-weight: bold; z-index: 99999; animation: fadeInOut 2s forwards; border: 2px solid #fff; }
    
    /* 6. 요일 뱃지 */
    .day-badge-single { padding: 8px 0; border-radius: 8px; color: #212121 !important; font-weight: 800; text-align: center; display: block; width: 100%; border: 1px solid rgba(0,0,0,0.1); font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# [데이터베이스 엔진] 구글 시트 연동 핵심 함수
# ==========================================
@st.cache_resource
def init_connection():
    import re
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_json" in st.secrets:
            if isinstance(st.secrets["gcp_json"], str):
                key_dict = json.loads(st.secrets["gcp_json"])
            else:
                key_dict = dict(st.secrets["gcp_json"])
        elif "gcp_service_account" in st.secrets:
            key_dict = dict(st.secrets["gcp_service_account"])
        else:
            raise Exception("Secrets 설정을 찾을 수 없습니다.")

        if "private_key" in key_dict:
            pk = key_dict["private_key"]
            pk = pk.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
            pk = re.sub(r"\\n", "", pk)
            pk = re.sub(r"\s+", "", pk)
            key_dict["private_key"] = "-----BEGIN PRIVATE KEY-----\n" + pk + "\n-----END PRIVATE KEY-----\n"

        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    except Exception as e:
        st.error(f"⚠️ 인증 오류 발생: {e}")
        return None

    client = gspread.authorize(creds)
    return client

def safe_api_call(func, *args, **kwargs):
    max_retries = 5
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if "429" in str(e): 
                time.sleep((1.5 ** i) + 1)
                continue
            else: raise e
        except Exception as e:
            time.sleep(1)
            continue
    return func(*args, **kwargs)

@st.cache_data(ttl=3)
def load_data(sheet_name):
    try:
        client = init_connection()
        if client is None: return pd.DataFrame() 

        doc = client.open("Academy_DB") 
        sheet = safe_api_call(doc.worksheet, sheet_name)
        data = safe_api_call(sheet.get_all_records)
        return pd.DataFrame(data)
    except Exception as e:
        # st.error(f"🚨 데이터 로드 실패 ({sheet_name}): {e}") # 사용자 경험을 위해 에러 숨김 처리
        return pd.DataFrame()

def clear_cache(): st.cache_data.clear()

def show_center_message(message, icon="✅"):
    placeholder = st.empty()
    placeholder.markdown(f'<div class="custom-alert"><span>{icon}</span> {message}</div>', unsafe_allow_html=True)
    time.sleep(1.2); placeholder.empty()

def add_data(sheet_name, data_dict):
    try:
        client = init_connection()
        if client is None: return False

        ws = safe_api_call(client.open("Academy_DB").worksheet, sheet_name)
        headers = safe_api_call(ws.row_values, 1)
        
        if not headers:
            safe_api_call(ws.append_row, list(data_dict.keys()))
            headers = list(data_dict.keys())
            
        row_to_add = []
        for col_name in headers:
            row_to_add.append(str(data_dict.get(col_name, "")))
            
        safe_api_call(ws.append_row, row_to_add)
        clear_cache()
        return True
    except Exception as e:
        st.error(f"데이터 추가 실패: {e}")
        return False

def add_data_bulk(sheet_name, data_list):
    if not data_list: return
    try:
        client = init_connection()
        if client is None: return

        ws = safe_api_call(client.open("Academy_DB").worksheet, sheet_name)
        headers = safe_api_call(ws.row_values, 1)
        
        if not headers:
            headers = list(data_list[0].keys())
            safe_api_call(ws.append_row, headers)
            
        rows_to_add = []
        for item in data_list:
            row = []
            for col in headers:
                row.append(str(item.get(col, "")))
            rows_to_add.append(row)
            
        safe_api_call(ws.append_rows, rows_to_add)
        clear_cache()
    except Exception as e:
        st.error(f"일괄 추가 실패: {e}")

def update_data(sheet_name, key_col, key_val, new_data_dict):
    try:
        client = init_connection()
        if client is None: return False

        ws = safe_api_call(client.open("Academy_DB").worksheet, sheet_name)
        data = safe_api_call(ws.get_all_records)
        df = pd.DataFrame(data)
        
        if df.empty or key_col not in df.columns: return False

        target_indices = df[df[key_col].astype(str) == str(key_val)].index
        if len(target_indices) == 0: return False
            
        row_num = target_indices[0] + 2
        headers = safe_api_call(ws.row_values, 1)
        
        for col_name, new_val in new_data_dict.items():
            if col_name in headers:
                col_idx = headers.index(col_name) + 1
                safe_api_call(ws.update_cell, row_num, col_idx, str(new_val))
                
        clear_cache()
        return True
    except Exception as e:
        st.error(f"수정 실패: {e}")
        return False

def delete_data_all(sheet_name, criteria_dict):
    try:
        client = init_connection()
        if client is None: return False

        ws = safe_api_call(client.open("Academy_DB").worksheet, sheet_name)
        data = safe_api_call(ws.get_all_records)
        
        rows_to_delete = []
        for i, row in enumerate(data):
            match = True
            for k, v in criteria_dict.items():
                if str(row.get(k)) != str(v):
                    match = False
                    break
            if match:
                rows_to_delete.append(i + 2)
        
        if rows_to_delete:
            for r in sorted(rows_to_delete, reverse=True):
                safe_api_call(ws.delete_rows, r)
            clear_cache()
            return True
        return False
    except Exception as e:
        st.error(f"삭제 실패: {e}")
        return False

# --- 유틸리티 및 시간 중복 체크 함수 ---
def calc_duration_min(s, e):
    try:
        # 파이썬 기본 시간함수는 24:00을 에러로 인식하므로, 수식으로 직접 계산하도록 업그레이드!
        s_hour, s_min = map(int, s.split(':'))
        e_hour, e_min = map(int, e.split(':'))
        return (e_hour * 60 + e_min) - (s_hour * 60 + s_min)
    except: return 0

def sort_time_strings(time_list):
    # 9:00, 10:00, 24:00 등이 순서대로 예쁘게 정렬되도록 로직 강화
    def time_to_min(t_str):
        try:
            h, m = map(int, t_str.split(':'))
            return h * 60 + m
        except: return 0
    return sorted(list(set(time_list)), key=time_to_min)

def get_col_data(df, col, idx):
    if col in df.columns: return df[col]
    elif len(df.columns) > idx: return df.iloc[:, idx]
    else: return pd.Series([])

# QR 관련
def generate_styled_qr(data, student_name):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data); qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    top_p, bot_p = 60, 60
    canvas_w, canvas_h = qr_img.width + 40, qr_img.height + top_p + bot_p
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    canvas.paste(qr_img, ((canvas_w - qr_img.width) // 2, top_p))
    draw = ImageDraw.Draw(canvas)
    
    font_path = "font.ttf" if os.path.exists("font.ttf") else "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
    try:
        fh = ImageFont.truetype(font_path, 30); fn = ImageFont.truetype(font_path, 35)
    except:
        fh = ImageFont.load_default(); fn = ImageFont.load_default()
        
    draw.text(((canvas_w - draw.textlength("형설지공 학원", font=fh)) / 2, 15), "형설지공 학원", fill="black", font=fh)
    draw.text(((canvas_w - draw.textlength(student_name, font=fn)) / 2, canvas_h - 50), student_name, fill="black", font=fn)
    return canvas

def decode_qr(image_input):
    try:
        if image_input is None: return None
        bytes_data = image_input.getvalue()
        img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        return data if data else None
    except: return None

# ==========================================
# [스마트 로그인 시스템]
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'role' not in st.session_state: st.session_state['role'] = None
if 'username' not in st.session_state: st.session_state['username'] = None

if not st.session_state['logged_in']:
    st.markdown("<br><br><h1 style='text-align: center; color: #1565C0;'>🏫 형설지공 ERP 로그인</h1><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        with st.container(border=True):
            login_type = st.radio("로그인 권한 선택", ["👨‍🏫 강사", "👑 원장(관리자)"], horizontal=True)
            st.divider()
            
            if login_type == "👑 원장(관리자)":
                admin_pw = st.text_input("마스터 비밀번호", type="password")
                if st.button("원장님 로그인", use_container_width=True, type="primary"):
                    if admin_pw == "1234":  # 원장님 비밀번호 (원하시는 숫자로 바꾸셔도 됩니다)
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = 'admin'
                        st.session_state['username'] = '원장'
                        st.rerun()
                    else: st.error("비밀번호가 틀렸습니다.")
            else:
                df_t_login = load_data('teachers')
                if df_t_login.empty:
                    st.warning("등록된 강사가 없습니다. 원장님 계정으로 접속하여 강사를 먼저 등록해주세요.")
                else:
                    t_names = df_t_login.iloc[:, 0].tolist()
                    sel_t = st.selectbox("강사명 선택", t_names)
                    t_pw = st.text_input("비밀번호 (기본값: 연락처 뒷 4자리)", type="password")
                    
                    if st.button("강사 로그인", use_container_width=True, type="primary"):
                        row = df_t_login[df_t_login.iloc[:,0] == sel_t].iloc[0]
                        expected_pw = ""
                        if '비밀번호' in df_t_login.columns: expected_pw = str(row.get('비밀번호', ''))
                        
                        if not expected_pw or expected_pw == "nan":
                            phone = str(row.get('연락처', '0000')).replace('-', '')
                            expected_pw = phone[-4:] if len(phone)>=4 else "0000"
                            
                        if t_pw == expected_pw:
                            st.session_state['logged_in'] = True
                            st.session_state['role'] = 'teacher'
                            st.session_state['username'] = sel_t
                            st.rerun()
                        else: st.error("비밀번호가 일치하지 않습니다.")
    st.stop()  # 로그인 안 되면 여기서 화면 멈춤

# ==========================================
# [메뉴] 사이드바 구성 (역할별 권한 분리 적용)
# ==========================================
with st.sidebar:
    st.title("🏫 형설지공 학원")
    st.markdown(f"**반갑습니다, {st.session_state['username']}님!**")
    
    if st.button("🚪 로그아웃"):
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['username'] = None
        st.rerun()
    st.markdown("---")
    
    # 전체 메뉴 리스트 (맨 뒤에 '내 정보 수정' 추가)
    all_menus = [
        "🏠 대시보드", "1. 강사 관리", "2. 학생 관리", "3. 반 관리", "4. 수강 배정", 
        "5. QR 키오스크(출석)", "6. 출석 관리", "7. 강사별 시간표", "8. 강의실별 시간표", 
        "9. 학생 개인별 종합", "10. 일일 업무 일지", "11. 업무 일지 관리", "👤 내 정보 수정"
    ]
    all_icons = [
        'house', 'person-video3', 'backpack', 'easel', 'journal-check', 
        'qr-code-scan', 'calendar-check', 'clock', 'building', 'card-checklist', 
        'pencil-square', 'search', 'person-gear'
    ]
    
    # 강사 로그인 시 숨길 메뉴 설정
    if st.session_state['role'] == 'teacher':
        # 강사는 1, 5, 11번 메뉴만 못 보게 설정 (내 정보 수정은 허용)
        hidden_menus = ["1. 강사 관리", "5. QR 키오스크(출석)", "11. 업무 일지 관리"]
        
        indices = [i for i, m in enumerate(all_menus) if m not in hidden_menus]
        display_menus = [all_menus[i] for i in indices]
        display_icons = [all_icons[i] for i in indices]
    else:
        display_menus = all_menus
        display_icons = all_icons

    menu = option_menu("메뉴 선택", display_menus, icons=display_icons, menu_icon="cast", default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#f0f2f6"},
            "icon": {"color": "orange", "font-size": "18px"}, 
            "nav-link": {"font-size": "15px", "text-align": "left", "margin":"0px", "white-space": "nowrap", "--hover-color": "#eee"},
            "nav-link-selected": {"background-color": "#02ab21"},
        }
    )
    
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        clear_cache(); st.rerun()

    st.markdown("---")
    st.caption("Developed by 형설지공 2026")

# (이 바로 아래에 # 🏠 대시보드 (메인 화면) 이 이어지면 정상입니다!)
# ==========================================
# 🏠 대시보드 (메인 화면)
# ==========================================
if menu == "🏠 대시보드":
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60000, limit=None, key="dashboard_refresh")
    
    col_title, col_date = st.columns([3, 1])
    with col_title: st.subheader("📊 학원 실시간 현황 및 출결 관제탑")
    with col_date: selected_date = st.date_input("🗓️ 조회 날짜 선택", datetime.today().date(), format="YYYY/MM/DD")
    
    df_s, df_t, df_c, df_a, df_e = load_data('students'), load_data('teachers'), load_data('classes'), load_data('attendance'), load_data('enrollments') 
    
    # 1. 오늘 예정된 모든 수업과 수강생 명단 추출
    days_ko = ["월", "화", "수", "목", "금", "토", "일"]
    target_yoil = days_ko[selected_date.weekday()]
    
    target_classes = []
    expected_attendances = [] 
    
    if not df_c.empty:
        for _, row in df_c.iterrows():
            c_name = row.iloc[0]
            c_teacher = row.iloc[1]
            c_type = row.get('구분', '정규')
            is_valid_date = True
            
            if c_type == '보강':
                try:
                    s_dt = datetime.strptime(str(row.get('시작일', '')), "%Y-%m-%d").date()
                    e_dt = datetime.strptime(str(row.get('종료일', '')), "%Y-%m-%d").date()
                    if not (s_dt <= selected_date <= e_dt): is_valid_date = False
                except: pass
            
            if is_valid_date and target_yoil in str(row.iloc[2]):
                for part in str(row.iloc[2]).split(','):
                    if part.strip().startswith(target_yoil):
                        t_range = part.strip().split()[1]
                        start_t = t_range.split('-')[0]
                        
                        enrolled_students = []
                        if not df_e.empty:
                            matched_enrolls = df_e[df_e.iloc[:,2] == c_name]
                            for sn in matched_enrolls.iloc[:,0].tolist():
                                s_grade, s_phone, p_phone = "", "", ""
                                if not df_s.empty:
                                    s_info = df_s[df_s.iloc[:,0] == sn]
                                    if not s_info.empty:
                                        if len(s_info.columns)>3: s_grade = str(s_info.iloc[0, 3]).replace("초등학교", "초").replace("중학교", "중").replace("고등학교", "고")
                                        s_phone = str(s_info.iloc[0, 1])
                                        p_phone = str(s_info.iloc[0, 2])
                                enrolled_students.append(f"{sn}({s_grade})" if s_grade else sn)
                                expected_attendances.append((sn, c_name, c_teacher, start_t, s_phone, p_phone))
                                
                        # [핵심 변경 1] 학생이 1명이라도 배정된 반(enrolled_students가 비어있지 않은 경우)만 추가!
                        if enrolled_students:
                            target_classes.append({
                                'time': t_range, 'start_t': start_t, 'name': c_name,
                                'teacher': c_teacher, 'room': row.iloc[3] if len(row) > 3 else "기타",
                                'students': enrolled_students, 'type': c_type, 'reason': row.get('사유', '')
                            })

    # 2. 출결 분석 및 미등원 자동 결석 처리 로직
    now = datetime.now()
    target_str = str(selected_date)
    daily_att = df_a[df_a.iloc[:,0].astype(str) == target_str] if not df_a.empty else pd.DataFrame()
    
    action_required = [] 
    late_list = []       
    absent_list = []     
    auto_absent_to_db = [] 
    
    att_map = {}
    if not daily_att.empty:
        for _, r in daily_att.iterrows():
            att_map[(r.iloc[2], r.iloc[1])] = r.iloc[3] 
            
    for sn, cname, c_tea, st_time, sph, pph in expected_attendances:
        if (sn, cname) in att_map:
            status = att_map[(sn, cname)]
            if status == '지각': late_list.append((sn, cname, c_tea, st_time, sph))
            elif status == '결석': absent_list.append((sn, cname, c_tea, st_time, sph))
        else:
            try:
                h, m = map(int, st_time.split(':'))
                class_dt = datetime.combine(selected_date, datetime.min.time()).replace(hour=h, minute=m)
                
                if selected_date < now.date() or (selected_date == now.date() and now.hour >= 22):
                    auto_absent_to_db.append({'날짜': target_str, '반이름': cname, '학생': sn, '상태': '결석', '비고': '시스템 자동결석(22시경과)'})
                elif selected_date == now.date() and now >= class_dt + timedelta(minutes=10):
                    action_required.append((sn, cname, c_tea, st_time, sph, pph))
            except: pass
            
    if auto_absent_to_db:
        add_data_bulk('attendance', auto_absent_to_db)
        st.rerun() 

    # [핵심 변경 2] 문자열 시간(예: "17:00")을 분(minute)으로 변환하여 완벽하게 최신순 정렬
    def time_to_min_for_sort(t_str):
        try:
            h, m = map(int, t_str.split(':'))
            return h * 60 + m
        except: return 0
        
    action_required.sort(key=lambda x: time_to_min_for_sort(x[3]), reverse=True)
    late_list.sort(key=lambda x: time_to_min_for_sort(x[3]), reverse=True)
    absent_list.sort(key=lambda x: time_to_min_for_sort(x[3]), reverse=True)

    # 3. 메트릭 현황판
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"""<div class="metric-card"><div class="metric-title">총 재원생</div><div class="metric-value">{len(df_s)}명</div></div>""", unsafe_allow_html=True)
    with c2: st.markdown(f"""<div class="metric-card"><div class="metric-title">오늘 활성된 반</div><div class="metric-value">{len(target_classes)}개</div></div>""", unsafe_allow_html=True)
    with c3: 
        att_count = len([k for k, v in att_map.items() if v in ['출석', '지각', '보강/자습']])
        st.markdown(f"""<div class="metric-card"><div class="metric-title">오늘 등원 완료</div><div class="metric-value">{att_count}명</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="metric-card" style="border-color:#ff4b4b!important;"><div class="metric-title">오늘 미등원/결석</div><div class="metric-value" style="color:#ff4b4b!important;">{len(action_required) + len(absent_list)}명</div></div>""", unsafe_allow_html=True)

    st.divider()

    # 4. 실시간 출결 관제 (경고창)
    col_alert, col_list = st.columns([1.2, 1])
    
    with col_alert:
        st.markdown(f"##### 🚨 실시간 연락 요망 (수업 시작 10분 경과 미등원자)")
        if not action_required:
            st.success("✅ 현재 미등원(지각 의심) 학생이 없습니다. 모두 무사히 등원했습니다!")
        else:
            if selected_date == now.date() and 'last_action_req' not in st.session_state: st.session_state.last_action_req = 0
            if selected_date == now.date() and len(action_required) > st.session_state.last_action_req:
                st.toast("🚨 새로운 미등원(지각 의심) 학생이 감지되었습니다! 데스크 연락 바랍니다.", icon="🚨")
                st.session_state.last_action_req = len(action_required)
                
            for sn, cname, c_tea, tm, sph, pph in action_required:
                with st.container(border=True):
                    c_text, c_btn = st.columns([3, 1])
                    c_text.markdown(f"**[{cname}] {sn} 학생** (담당: :blue[{c_tea}] / 시작: {tm})")
                    c_text.caption(f"학생📱: {sph} | 부모님📞: {pph}")
                    if c_btn.button("결석 확정", key=f"btn_abs_{sn}_{cname}", type="primary"):
                        add_data('attendance', {'날짜': target_str, '반이름': cname, '학생': sn, '상태': '결석', '비고': '관리자 수동 확정'})
                        show_center_message(f"{sn} 결석 처리 완료!")
                        st.rerun()

    with col_list:
        st.markdown(f"##### 🚩 오늘의 지각 및 결석 확정자")
        if not late_list and not absent_list:
            st.info("오늘 발생한 지각/결석 확정 내역이 없습니다.")
        else:
            for sn, cname, c_tea, tm, sph in late_list:
                st.warning(f"**[지각]** {sn} | {cname} (담당: {c_tea}) | 시작: {tm}")
            for sn, cname, c_tea, tm, sph in absent_list:
                st.error(f"**[결석]** {sn} | {cname} (담당: {c_tea}) | 시작: {tm}")

    st.divider()
    
    # 5. 시간표 렌더링
    st.markdown(f"##### 📅 {selected_date.month}/{selected_date.day} 강의실 배정 현황 및 수강 명단")
    
    if target_classes:
        rooms = ["101호", "102호", "103호", "104호", "기타"]
        unique_starts = sorted(list(set(tc['start_t'] for tc in target_classes)))
        
        header_cols = st.columns([1] + [2]*len(rooms))
        header_cols[0].markdown("<div class='day-header'>⏰ 시간</div>", unsafe_allow_html=True)
        for i, r in enumerate(rooms): header_cols[i+1].markdown(f"<div class='day-header'>{r}</div>", unsafe_allow_html=True)
            
        for start_t in unique_starts:
            cols = st.columns([1] + [2]*len(rooms))
            cols[0].markdown(f"<div class='time-axis-card'><span class='tac-start'>{start_t}</span></div>", unsafe_allow_html=True)
            
            for i, r in enumerate(rooms):
                matched = [tc for tc in target_classes if tc['room'] == r and tc['start_t'] == start_t]
                with cols[i+1]:
                    if matched:
                        for mc in matched:
                            student_count = len(mc['students'])
                            std_str = ", ".join(mc['students']) if student_count > 0 else "배정생 없음"
                            
                            if mc['type'] == '보강':
                                card_style = "background-color: #FFF3E0; border-left-color: #FF9800;"
                                title_color = "#E65100"
                                badge = f"<span style='background-color:#FF9800; color:white; padding:2px 6px; border-radius:4px; font-size:0.7rem; margin-left:5px;'>보강: {mc['reason']}</span>"
                            else:
                                card_style = "background-color: #E3F2FD; border-left-color: #1565C0;"
                                title_color = "#1565C0"
                                badge = ""
                            
                            st.markdown(f"""
                            <div class='class-card' style='min-height: 80px; {card_style}'>
                                <div class='cc-name'>{mc['name']} {badge}</div>
                                <div class='cc-info'>👨‍🏫 {mc['teacher']}</div>
                                <div class='cc-info' style='margin-top:6px; font-size:0.8rem; color:#424242; line-height: 1.3;'>
                                    <strong style='color:{title_color}; font-size:0.85rem;'>👥 총 {student_count}명</strong><br>
                                    <span style='color:#666;'>{std_str}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.markdown("<div class='empty-card' style='min-height: 80px; display:flex; align-items:center; justify-content:center; color:#ccc; font-size:0.8rem;'>비어있음</div>", unsafe_allow_html=True)
    else:
        st.success("해당 날짜에 예정된 수업이 없습니다.")

# ==========================================================
# 1. 강사 관리
# ==========================================================
elif menu == "1. 강사 관리":
    st.subheader("👨‍🏫 강사 관리")
    tab1, tab2 = st.tabs(["➕ 신규 등록", "🔧 수정 및 삭제"])
    
    # [Tab 1] 신규 등록
    with tab1:
        with st.form("teacher_create_form", clear_on_submit=True):
            name = st.text_input("이름")
            subject = st.text_input("담당 과목")
            phone = st.text_input("연락처 (010-0000-0000)")
            email = st.text_input("이메일 (알림 수신용)")
            address = st.text_input("주소 ")  # <-- 주소 추가!
            pw = st.text_input("임시 로그인 비밀번호 (미입력시 연락처 뒷 4자리로 자동설정)")
            
            if st.form_submit_button("등록하기"):
                if not name:
                    st.error("이름을 입력하세요.")
                else:
                    add_data('teachers', {
                        '이름': name, 
                        '과목': subject, 
                        '연락처': phone, 
                        '이메일': email, 
                        '주소': address,  # <-- 주소 추가!
                        '비밀번호': pw
                    })
                    show_center_message(f"{name} 선생님 등록 완료!")
                    st.rerun()

    # [Tab 2] 수정 및 삭제
    with tab2:
        df_t = load_data('teachers')
        if not df_t.empty:
            t_names = get_col_data(df_t, '이름', 0).astype(str)
            t_options = t_names.tolist()
            
            idx = st.session_state.get('t_modify_idx', 0)
            if idx >= len(t_options): idx = 0
            
            selected_t = st.selectbox("수정할 선생님 선택", t_options, index=idx)
            if selected_t in t_options: st.session_state['t_modify_idx'] = t_options.index(selected_t)
            
            if selected_t:
                row = df_t[df_t[df_t.columns[0]] == selected_t].iloc[0]
                
                st.divider()
                st.markdown(f"##### 🔧 '{selected_t}' 선생님 정보 수정")
                
                prev_name = row.iloc[0]
                prev_sub = row.iloc[1] if len(row) > 1 else ""
                prev_ph = row.iloc[2] if len(row) > 2 else ""
                prev_email = row.iloc[3] if len(row) > 3 else ""
                
                # 구글 시트에 아직 '주소'나 '비밀번호' 열이 없을 수도 있으니 안전하게 가져오기
                prev_addr = row.get('주소', '')
                if pd.isna(prev_addr): prev_addr = ""
                
                prev_pw = row.get('비밀번호', '')
                if pd.isna(prev_pw): prev_pw = ""

                n_name = st.text_input("이름", value=prev_name, key="edit_t_n")
                n_sub = st.text_input("과목", value=prev_sub, key="edit_t_s")
                n_ph = st.text_input("연락처", value=prev_ph, key="edit_t_p")
                n_email = st.text_input("이메일", value=prev_email, key="edit_t_e")
                n_addr = st.text_input("주소", value=prev_addr, key="edit_t_addr") # <-- 주소 추가!
                n_pw = st.text_input("비밀번호", value=prev_pw, key="edit_t_pw")
                
                c1, c2 = st.columns(2)
                
                if c1.button("💾 수정 저장"):
                    st.session_state['confirm_action'] = 'update_teacher'
                
                if st.session_state.get('confirm_action') == 'update_teacher':
                    st.warning(f"⚠️ 정말로 '{selected_t}' 선생님 정보를 수정하시겠습니까?")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 수정합니다", type="primary"):
                        update_data('teachers', '이름', selected_t, {
                            '이름': n_name, 
                            '과목': n_sub, 
                            '연락처': n_ph, 
                            '이메일': n_email, 
                            '주소': n_addr,  # <-- 주소 추가!
                            '비밀번호': n_pw
                        })
                        st.session_state['confirm_action'] = None
                        st.session_state['t_modify_idx'] = 0
                        show_center_message("수정 완료!")
                        for key in ["edit_t_n", "edit_t_s", "edit_t_p", "edit_t_e", "edit_t_addr", "edit_t_pw"]:
                            if key in st.session_state: del st.session_state[key]
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()

                if c2.button("🗑️ 삭제하기"):
                    st.session_state['confirm_action'] = 'delete_teacher'
                
                if st.session_state.get('confirm_action') == 'delete_teacher':
                    st.error(f"⚠️ 경고: '{selected_t}' 선생님을 삭제하시겠습니까? (복구 불가)")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 삭제합니다", type="primary"):
                        delete_data_all('teachers', {'이름': selected_t})
                        st.session_state['confirm_action'] = None
                        st.session_state['t_modify_idx'] = 0
                        show_center_message("삭제 완료!", icon="🗑️")
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()

# ==========================================
# 2. 학생 관리 (재원/퇴원/휴원/졸업 상태 관리 적용)
# ==========================================
elif menu == "2. 학생 관리":
    st.subheader("📝 학생 관리")
    t1, t2, t3, t4 = st.tabs(["📋 전체 학생 조회", "➕ 신규 등록", "🔧 수정/상태변경", "📱 QR 발급/인쇄"])
    
    df_c, df_t, df_s = load_data('classes'), load_data('teachers'), load_data('students')
    all_subjects = sorted(get_col_data(df_t, '과목', 1).unique().tolist()) if not df_t.empty else []

    # --- 첫 번째 탭: 학생 조회 및 상세 메모장 ---
    with t1:
        if not df_s.empty:
            # 상태 열이 없으면 기본값 '재원'으로 채우기
            display_df = df_s.copy()
            if '상태' not in display_df.columns: display_df['상태'] = '재원'
            else: display_df['상태'] = display_df['상태'].fillna('재원')
                
            status_filter = st.radio("상태 필터", ["재원", "휴원", "퇴원", "졸업", "전체보기"], horizontal=True)
            
            if status_filter != "전체보기":
                display_df = display_df[display_df['상태'] == status_filter]
                
            # 1. 상단: 요약된 전체 학생 목록
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # 2. 하단: 특정 학생 클릭(선택) 시 나타나는 상세 메모장
            st.markdown("### 📝 학생 상세 프로필 (타임라인 메모장)")
            
            df_s['L'] = df_s.iloc[:,0] + " (" + df_s.iloc[:,3] + ", " + df_s['상태'] + ")"
            s_ops = ["(학생을 선택하세요)"] + df_s['L'].tolist()
            selected_memo_student = st.selectbox("🔍 상세 조회할 학생 선택", s_ops)
            
            if selected_memo_student != "(학생을 선택하세요)":
                real_n = selected_memo_student.split(' (')[0]
                s_row = df_s[df_s.iloc[:,0] == real_n].iloc[0]
                
                # 데이터 불러오기
                df_e = load_data('enrollments')
                df_sr = load_data('student_records')
                
                with st.container(border=True):
                    # 기본 정보 헤더
                    st.markdown(f"#### 🧑‍🎓 {real_n} 학생 종합 기록부")
                    c1, c2, c3 = st.columns(3)
                    c1.caption(f"**상태:** {s_row.get('상태', '재원')}")
                    c2.caption(f"**학교/학년:** {s_row.get('학교', '')} ({s_row.get('학년', '')})")
                    c3.caption(f"**최초 등록일:** {s_row.get('등록일', '기록없음')}")
                    
                    st.markdown("---")
                    
                    # 수강 이력 (타임라인)
                    st.markdown("##### 📘 수강 이력")
                    if not df_e.empty:
                        my_enrolls = df_e[df_e['학생'] == real_n]
                        if my_enrolls.empty:
                            st.info("수강 이력이 없습니다.")
                        else:
                            for _, e_row in my_enrolls.iterrows():
                                e_subj = e_row.get('과목', '')
                                e_cls = e_row.get('반이름', '')
                                e_tea = e_row.get('담당강사', '')
                                e_start = e_row.get('날짜', '')
                                e_status = e_row.get('상태', '수강중')
                                e_end = e_row.get('종료일', '')
                                
                                if e_status == "수강종료":
                                    st.markdown(f"• ⬛ ~~[{e_subj}] {e_cls} ({e_tea})~~ : {e_start} ~ {e_end} (수강종료)")
                                else:
                                    st.markdown(f"• 🟦 **[{e_subj}] {e_cls} ({e_tea})** : {e_start} ~ 현재 (수강중)")
                    else:
                        st.info("수강 이력이 없습니다.")
                        
                    st.markdown("---")
                    
                    # 상담 및 특이사항 기록 (Menu 10에서 작성한 내용 연동)
                    st.markdown("##### 💬 상담 및 특이사항 (최근 5건)")
                    if not df_sr.empty:
                        my_records = df_sr[df_sr['학생명'] == real_n]
                        if my_records.empty:
                            st.info("기록된 상담이나 특이사항이 없습니다.")
                        else:
                            for _, r_row in my_records.tail(5)[::-1].iterrows():
                                st.markdown(f"**[{r_row['날짜']}] {r_row['분류']}** (작성: {r_row['강사명']})")
                                st.caption(f"{r_row['세부내용']}")
                    else:
                        st.info("기록된 상담이나 특이사항이 없습니다.")
                        
        else:
            st.info("등록된 학생이 없습니다.")

    # --- 두 번째 탭: 신규 등록 (상태 추가) ---
    with t2:
        if df_c.empty: st.warning("⚠️ 개설된 반이 없습니다. (반 관리 메뉴에서 먼저 반을 만들어주세요)")
        st.markdown("##### 1️⃣ 기본 정보 입력")
        c1, c2 = st.columns(2)
        name = c1.text_input("이름", key="create_name")
        phone = c1.text_input("학생 폰", key="create_phone")
        p_phone = c1.text_input("부모님 폰", key="create_p_phone")
        
        grade = c2.selectbox("학년", ["초4","초5","초6","중1","중2","중3","고1","고2","고3"], key="create_grade")
        school = c2.text_input("학교", key="create_school")
        # [수정] 선택지에 '졸업' 항목 추가!
        new_status = c2.selectbox("현재 상태", ["재원", "휴원", "퇴원", "졸업"], key="create_status") 
        
        st.divider()
        st.markdown("##### 2️⃣ 수강 과목 및 반 선택")
        final_enroll_list = []
        for subj in all_subjects:
            if st.checkbox(f"📘 {subj} 수강", key=f"new_chk_{subj}"):
                sub_teachers = df_t[df_t.iloc[:, 1] == subj].iloc[:, 0].tolist()
                c_tea, c_cls = st.columns([1, 2])
                with c_tea:
                    sel_teas = st.multiselect(f"담당 선생님 ({subj})", sub_teachers, key=f"new_tea_{subj}")
                if sel_teas:
                    cls_options = []
                    cls_map = {}
                    for tea in sel_teas:
                        t_classes = df_c[df_c.iloc[:, 1].str.contains(tea)]
                        for _, r in t_classes.iterrows():
                            lbl = f"{r.iloc[0]} ({r.iloc[2]})"
                            cls_options.append(lbl)
                            cls_map[lbl] = {'반이름': r.iloc[0], '담당강사': r.iloc[1]}
                    with c_cls:
                        sel_cls_labels = st.multiselect(f"배정할 반 ({subj})", cls_options, key=f"new_cls_{subj}")
                        for lbl in sel_cls_labels:
                            info = cls_map[lbl]
                            final_enroll_list.append({
                                '학생': name,
                                '과목': subj,
                                '반이름': info['반이름'],
                                '담당강사': info['담당강사'],
                                '날짜': str(datetime.today().date())
                            })
        
        if st.button("💾 학생 저장 및 수강 등록", type="primary"):
            if not name:
                st.error("이름을 입력해주세요.")
            else:
                # 데이터베이스에 상태 필드 함께 저장
                nd = {'이름': name, '연락처': phone, '학부모연락처': p_phone, '학년': grade, '학교': school, '상태': new_status}
                add_data('students', nd)
                if final_enroll_list: add_data_bulk('enrollments', final_enroll_list)
                show_center_message(f"✅ {name} 등록 완료!")
                
                # 입력창 초기화
                keys_to_clear = ["create_name", "create_phone", "create_p_phone", "create_grade", "create_school", "create_status"]
                for subj in all_subjects:
                    keys_to_clear.append(f"new_chk_{subj}")
                    keys_to_clear.append(f"new_tea_{subj}")
                    keys_to_clear.append(f"new_cls_{subj}")
                for key in keys_to_clear:
                    if key in st.session_state: del st.session_state[key]
                time.sleep(1.5); st.rerun()

    # --- 세 번째 탭: 수정 및 삭제 (상태 변경 중심) ---
    with t3:
        if not df_s.empty:
            st.markdown("### 🔍 학생 검색 및 수정")
            k = st.text_input("이름 검색", key='s_search_edit')
            df_s['L'] = df_s.iloc[:,0] + " (" + df_s.iloc[:,3] + ")"
            f = df_s[df_s.iloc[:,0].str.contains(k)] if k else df_s
            s_ops = f['L'].tolist()
            s_sel = st.selectbox("학생 선택", s_ops)
            
            if s_sel:
                real_n = s_sel.split(' (')[0]
                row = df_s[df_s.iloc[:,0] == real_n].iloc[0]
                st.divider()
                st.markdown(f"##### 🔧 '{real_n}' 학생 정보 및 상태 수정")
                sc1, sc2 = st.columns(2)
                u_nm = sc1.text_input("이름", value=row.iloc[0], key=f"u_sn_{real_n}")
                u_hp = sc1.text_input("학생 폰", value=row.iloc[1], key=f"u_sp_{real_n}")
                u_pp = sc1.text_input("부모 폰", value=row.iloc[2], key=f"u_spp_{real_n}")
                grs = ["초4","초5","초6","중1","중2","중3","고1","고2","고3"]
                cur_g = row.iloc[3]
                u_gr = sc2.selectbox("학년", grs, index=grs.index(cur_g) if cur_g in grs else 0, key=f"u_sg_{real_n}")
                u_sc = sc2.text_input("학교", value=row.iloc[4], key=f"u_ssc_{real_n}")
                
                # [수정] 기존 상태값 불러오기 및 '졸업' 항목 추가!
                cur_stat = str(row.get('상태', '재원'))
                if cur_stat not in ["재원", "휴원", "퇴원", "졸업"]: cur_stat = "재원"
                u_stat = sc2.selectbox("상태 변경 (퇴원/졸업 처리)", ["재원", "휴원", "퇴원", "졸업"], index=["재원", "휴원", "퇴원", "졸업"].index(cur_stat), key=f"u_stat_{real_n}")

                st.markdown("---")
                if st.button("💾 정보 및 상태 업데이트", type="primary", use_container_width=True):
                    st.session_state['confirm_action'] = 'update_student'
                
                if st.session_state.get('confirm_action') == 'update_student':
                    st.warning(f"⚠️ '{real_n}' 학생의 정보를 수정하시겠습니까?")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 수정합니다", type="primary"):
                        nd = {'이름': u_nm, '연락처': u_hp, '학부모연락처': u_pp, '학년': u_gr, '학교': u_sc, '상태': u_stat}
                        update_data('students', '이름', real_n, nd)
                        st.session_state['confirm_action'] = None
                        show_center_message("수정 완료!")
                        if 's_search_edit' in st.session_state: del st.session_state['s_search_edit']
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()

                st.divider()
                st.caption("⚠️ 테스트 데이터를 지우거나 실수로 등록한 경우에만 아래 삭제 버튼을 사용하세요. 그만둔 학생은 위에서 상태를 '퇴원'이나 '졸업'으로 변경하는 것이 안전합니다.")
                if st.button("🗑️ 학생 데이터 영구 삭제 (복구 불가)"):
                    st.session_state['confirm_action'] = 'delete_student'

                if st.session_state.get('confirm_action') == 'delete_student':
                    st.error(f"⚠️ 정말로 '{real_n}' 학생 데이터를 영구 삭제하시겠습니까?")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 모두 삭제합니다", type="primary"):
                        delete_data_all('students', {'이름': real_n})
                        delete_data_all('enrollments', {'학생': real_n})
                        st.session_state['confirm_action'] = None
                        show_center_message("삭제 완료", icon="🗑️")
                        if 's_search_edit' in st.session_state: del st.session_state['s_search_edit']
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()

    # --- 네 번째 탭: QR 발급 (기존과 동일) ---
    with t4:
        st.markdown("### 📱 QR 코드 발급 및 인쇄")
        df = load_data('students')
        if not df.empty:
            s = st.selectbox("학생 선택", df.iloc[:,0], key='qr_sel_main')
            if s:
                row = df[df.iloc[:,0]==s].iloc[0]
                ph = str(row.iloc[1])[-4:] if len(row)>1 else "0000"
                img = generate_styled_qr(f"{s}/{ph}", s)
                c_qr1, c_qr2 = st.columns([1, 1.5])
                with c_qr1: st.image(img, caption=f"{s} 학생 QR", width=300)
                with c_qr2:
                    st.success(f"✅ **{s}** 학생의 QR코드가 생성되었습니다.")
                    st.markdown("**🖨️ 인쇄:** `Ctrl + P`를 눌러 인쇄하세요.")
                    st.divider()
                    buf = io.BytesIO(); img.save(buf, format="PNG"); byte_im = buf.getvalue()
                    st.download_button("💾 이미지 다운로드", data=byte_im, file_name=f"형설지공_{s}_QR.png", mime="image/png", type="primary")

# ==========================================
# 3. 반 관리
# ==========================================
elif menu == "3. 반 관리":
    st.subheader("📚 반 관리")
    tab1, tab2 = st.tabs(["➕ 반 개설", "🔧 반 정보 수정/삭제"])
    
    days = ["월", "화", "수", "목", "금", "토", "일"]
    day_colors = {"월":"#FFEBEE", "화":"#FFF3E0", "수":"#E8F5E9", "목":"#E3F2FD", "금":"#F3E5F5", "토":"#FAFAFA", "일":"#FFEBEE"}
    
    # [핵심] 기존 range(9, 23)을 range(9, 25)로 변경하여 밤 12시(24시)까지 선택 가능하게 확장!
    hours = [f"{i}시" for i in range(9, 25)] 
    mins = ["00분", "10분", "20분", "30분", "40분", "50분"]
    rooms = ["기타", "101호", "102호", "103호", "104호"]

    # ------------------------------------------
    # [Tab 1] 반 개설
    # ------------------------------------------
    with tab1:
        df_t = load_data('teachers')
        if df_t.empty: st.warning("선생님을 먼저 등록해주세요.")
        else:
            class_type = st.radio("수업 구분", ["📘 정규 수업", "📙 보강/단기특강"], horizontal=True)
            st.divider()

            t_opts = (get_col_data(df_t, '이름', 0) + " (" + get_col_data(df_t, '과목', 1) + ")").tolist()
            c1, c2, c3 = st.columns([2, 1, 2])
            c_name = c1.text_input("반 이름 (예: 중2 수학 보강)", key="new_c_name")
            c_room = c2.selectbox("강의실", rooms, key="new_c_room")
            t_name = c3.selectbox("담당 선생님", t_opts, key="new_t_name")
            
            start_d, end_d, reason = "", "", ""
            if class_type == "📙 보강/단기특강":
                st.info("💡 보강은 지정된 기간(날짜)에만 시간표에 표시되며 지각/결석 체크가 진행됩니다.")
                dc1, dc2, dc3 = st.columns(3)
                start_d = dc1.date_input("시작일")
                end_d = dc2.date_input("종료일")
                reason = dc3.selectbox("보강 사유", ["휴일 대체", "시험 대비", "진도 보충", "질의응답", "기타"])
            
            st.write("🕒 **요일 및 시간 설정**")
            schedule_data = {}
            for day in days:
                d_c1, d_c2, d_c3, d_c4, d_c5, d_c6 = st.columns([1, 2, 2, 0.5, 2, 2])
                with d_c1:
                    chk_col, badge_col = st.columns([0.3, 0.7])
                    with chk_col: is_chk = st.checkbox("", key=f"new_chk_{day}", label_visibility="collapsed")
                    with badge_col: st.markdown(f'<div class="day-badge-single" style="background-color:{day_colors[day]};">{day}</div>', unsafe_allow_html=True)
                with d_c2: sh = st.selectbox("시", hours, key=f"new_sh_{day}", label_visibility="collapsed", disabled=not is_chk)
                with d_c3: sm = st.selectbox("분", mins, key=f"new_sm_{day}", label_visibility="collapsed", disabled=not is_chk)
                with d_c4: st.write("~")
                with d_c5: eh = st.selectbox("시", hours, index=1, key=f"new_eh_{day}", label_visibility="collapsed", disabled=not is_chk)
                with d_c6: em = st.selectbox("분", mins, key=f"new_em_{day}", label_visibility="collapsed", disabled=not is_chk)
                if is_chk:
                    schedule_data[day] = f"{sh.replace('시',':')}{sm.replace('분','')}-{eh.replace('시',':')}{em.replace('분','')}"

            if st.button("반 만들기 (저장)", type="primary"):
                if not c_name: st.error("반 이름을 입력해주세요.")
                elif not schedule_data: st.error("요일을 최소 하나 이상 선택해주세요.")
                elif class_type == "📙 보강/단기특강" and start_d > end_d: st.error("종료일이 시작일보다 빠를 수 없습니다.")
                else:
                    final_sche = [f"{d} {t}" for d, t in schedule_data.items()]
                    add_data('classes', {
                        '반이름': c_name, '선생님': t_name, '시간': ", ".join(final_sche), '강의실': c_room,
                        '구분': "보강" if "보강" in class_type else "정규",
                        '시작일': str(start_d) if start_d else "",
                        '종료일': str(end_d) if end_d else "",
                        '사유': reason
                    })
                    show_center_message(f"'{c_name}' 개설 완료!")
                    time.sleep(1); st.rerun()

    # ------------------------------------------
    # [Tab 2] 반 수정 및 삭제
    # ------------------------------------------
    with tab2:
        df_c = load_data('classes')
        df_t = load_data('teachers')
        if df_c.empty: st.info("개설된 반이 없습니다.")
        else:
            t_opts = (get_col_data(df_t, '이름', 0) + " (" + get_col_data(df_t, '과목', 1) + ")").tolist() if not df_t.empty else []
            c_opts = df_c.iloc[:, 0].tolist()
            sel_c_name = st.selectbox("수정할 반 선택", c_opts)
            
            if sel_c_name:
                curr_row = df_c[df_c.iloc[:, 0] == sel_c_name].iloc[0]
                curr_teacher = str(curr_row.iloc[1])
                curr_schedule_str = str(curr_row.iloc[2])
                curr_room = str(curr_row.iloc[3]) if len(curr_row) > 3 else "기타"
                if curr_room not in rooms: curr_room = "기타"
                
                # 기존 정규/보강 데이터 불러오기 (없으면 기본값)
                curr_type = curr_row['구분'] if '구분' in df_c.columns else '정규'
                curr_sd_str = curr_row['시작일'] if '시작일' in df_c.columns else ''
                curr_ed_str = curr_row['종료일'] if '종료일' in df_c.columns else ''
                curr_reason = curr_row['사유'] if '사유' in df_c.columns else '기타'
                
                curr_sche_map = {}
                for p in curr_schedule_str.split(','):
                    kp = p.strip().split()
                    if len(kp)==2: curr_sche_map[kp[0]] = kp[1]

                st.divider()
                st.markdown(f"#### 🔧 '{sel_c_name}' 정보 수정")
                
                # 수업 구분 수정
                u_class_type = st.radio("수업 구분 수정", ["📘 정규 수업", "📙 보강/단기특강"], index=0 if curr_type == '정규' else 1, horizontal=True, key=f"edit_type_{sel_c_name}")
                st.divider()
                
                uc1, uc2, uc3 = st.columns([2, 1, 2])
                u_c_name = uc1.text_input("반 이름", value=sel_c_name, key=f"edit_n_{sel_c_name}")
                u_room = uc2.selectbox("강의실", rooms, index=rooms.index(curr_room), key=f"edit_r_{sel_c_name}")
                t_idx = t_opts.index(curr_teacher) if curr_teacher in t_opts else 0
                u_t_name = uc3.selectbox("담당 선생님", t_opts, index=t_idx, key=f"edit_t_{sel_c_name}")
                
                # 보강일 경우 날짜/사유 수정
                u_start_d, u_end_d, u_reason = "", "", ""
                if u_class_type == "📙 보강/단기특강":
                    udc1, udc2, udc3 = st.columns(3)
                    
                    # 날짜 기본값 세팅
                    try: def_sd = datetime.strptime(str(curr_sd_str), "%Y-%m-%d").date() if curr_sd_str else datetime.today().date()
                    except: def_sd = datetime.today().date()
                    try: def_ed = datetime.strptime(str(curr_ed_str), "%Y-%m-%d").date() if curr_ed_str else datetime.today().date()
                    except: def_ed = datetime.today().date()
                    
                    u_start_d = udc1.date_input("시작일", value=def_sd, key=f"u_sd_{sel_c_name}")
                    u_end_d = udc2.date_input("종료일", value=def_ed, key=f"u_ed_{sel_c_name}")
                    
                    r_opts = ["휴일 대체", "시험 대비", "진도 보충", "질의응답", "기타"]
                    r_idx = r_opts.index(curr_reason) if curr_reason in r_opts else 4
                    u_reason = udc3.selectbox("보강 사유", r_opts, index=r_idx, key=f"u_reason_{sel_c_name}")
                
                st.write("🕒 **시간 수정**")
                u_updated_sche = []
                for day in days:
                    has_d = day in curr_sche_map
                    sh_i, sm_i, eh_i, em_i = 0, 0, 0, 0
                    if has_d:
                        try:
                            s, e = curr_sche_map[day].split('-')
                            sh_i = hours.index(s.split(':')[0]+"시")
                            sm_i = mins.index(s.split(':')[1]+"분" if len(s.split(':')[1])==2 else "0"+s.split(':')[1]+"분")
                            eh_i = hours.index(e.split(':')[0]+"시")
                            em_i = mins.index(e.split(':')[1]+"분" if len(e.split(':')[1])==2 else "0"+e.split(':')[1]+"분")
                        except: pass
                    ud1, ud2, ud3, ud4, ud5, ud6 = st.columns([1, 2, 2, 0.5, 2, 2])
                    with ud1:
                        chk_col, badge_col = st.columns([0.3, 0.7])
                        with chk_col: u_chk = st.checkbox("", value=has_d, key=f"u_chk_{day}_{sel_c_name}", label_visibility="collapsed")
                        with badge_col: st.markdown(f'<div class="day-badge-single" style="background-color:{day_colors[day]};">{day}</div>', unsafe_allow_html=True)
                    with ud2: u_sh = st.selectbox("시", hours, index=sh_i, key=f"u_sh_{day}_{sel_c_name}", label_visibility="collapsed", disabled=not u_chk)
                    with ud3: u_sm = st.selectbox("분", mins, index=sm_i, key=f"u_sm_{day}_{sel_c_name}", label_visibility="collapsed", disabled=not u_chk)
                    with ud4: st.write("~")
                    with ud5: u_eh = st.selectbox("시", hours, index=eh_i, key=f"u_eh_{day}_{sel_c_name}", label_visibility="collapsed", disabled=not u_chk)
                    with ud6: u_em = st.selectbox("분", mins, index=em_i, key=f"u_em_{day}_{sel_c_name}", label_visibility="collapsed", disabled=not u_chk)
                    if u_chk:
                        st_t = f"{u_sh.replace('시',':')}{u_sm.replace('분','')}"
                        en_t = f"{u_eh.replace('시',':')}{u_em.replace('분','')}"
                        u_updated_sche.append(f"{day} {st_t}-{en_t}")
                
                st.divider()
                ub1, ub2 = st.columns(2)
                
                if ub1.button("💾 수정사항 저장", type="primary"):
                    if u_class_type == "📙 보강/단기특강" and u_start_d > u_end_d:
                        st.error("종료일이 시작일보다 빠를 수 없습니다.")
                    else:
                        st.session_state['confirm_action'] = 'update_class'
                
                if st.session_state.get('confirm_action') == 'update_class':
                    st.warning(f"⚠️ '{sel_c_name}' 반 정보를 수정하시겠습니까?")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 수정합니다", type="primary"):
                        nd = {
                            '반이름': u_c_name, 
                            '선생님': u_t_name, 
                            '시간': ", ".join(u_updated_sche), 
                            '강의실': u_room,
                            '구분': "보강" if "보강" in u_class_type else "정규",
                            '시작일': str(u_start_d) if u_start_d else "",
                            '종료일': str(u_end_d) if u_end_d else "",
                            '사유': u_reason
                        }
                        update_data('classes', '반이름', sel_c_name, nd)
                        st.session_state['confirm_action'] = None
                        show_center_message("수정 완료!")
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()
                
                if ub2.button("🗑️ 반 삭제"):
                    st.session_state['confirm_action'] = 'delete_class'
                
                if st.session_state.get('confirm_action') == 'delete_class':
                    st.error(f"⚠️ 경고: '{sel_c_name}' 반을 삭제하면 소속된 학생들의 수강 기록도 모두 삭제됩니다.")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 삭제합니다", type="primary"):
                        delete_data_all('classes', {'반이름': sel_c_name})
                        delete_data_all('enrollments', {'반이름': sel_c_name})
                        st.session_state['confirm_action'] = None
                        show_center_message("삭제 완료!", icon="🗑️")
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()

# ==========================================
# 4. 수강 배정 (수강종료 타임라인 보존 기능 적용)
# ==========================================
elif menu == "4. 수강 배정":
    st.subheader("🔗 수강 배정 관리")
    
    df_e = load_data('enrollments')
    df_s = load_data('students')
    df_t = load_data('teachers')
    df_c = load_data('classes')

    if 'draft_enrolls' not in st.session_state: st.session_state.draft_enrolls = []
    if 'confirm_save_cart' not in st.session_state: st.session_state.confirm_save_cart = False
    if 'confirm_cancel_target' not in st.session_state: st.session_state.confirm_cancel_target = None

    # [핵심 내부 함수] 지우개 대신 빨간펜(수강종료)을 칠하는 함수
    def cancel_class_soft(student_name, class_name):
        try:
            client = init_connection()
            ws = safe_api_call(client.open("Academy_DB").worksheet, 'enrollments')
            data = safe_api_call(ws.get_all_records)
            headers = safe_api_call(ws.row_values, 1)
            
            if '상태' not in headers:
                safe_api_call(ws.update_cell, 1, len(headers)+1, '상태')
                headers.append('상태')
            if '종료일' not in headers:
                safe_api_call(ws.update_cell, 1, len(headers)+1, '종료일')
                headers.append('종료일')
                
            for i, row in enumerate(data):
                if str(row.get('학생')) == str(student_name) and str(row.get('반이름')) == str(class_name) and str(row.get('상태')) != '수강종료':
                    status_col = headers.index('상태') + 1
                    end_date_col = headers.index('종료일') + 1
                    safe_api_call(ws.update_cell, i+2, status_col, '수강종료')
                    safe_api_call(ws.update_cell, i+2, end_date_col, str(datetime.today().date()))
            clear_cache()
            return True
        except Exception as e:
            st.error(f"수강 종료 처리 실패: {e}")
            return False

    tab1, tab2 = st.tabs(["📋 전체 수강 현황", "➕ 수강 신청 (장바구니)"])

    with tab1:
        if df_e.empty: st.info("현재 배정된 수강 내역이 없습니다.")
        else: 
            # '수강종료'가 아닌 현재 '수강중'인 목록만 보여줌
            if '상태' not in df_e.columns: df_e['상태'] = '수강중'
            active_e = df_e[df_e['상태'] != '수강종료']
            st.dataframe(active_e[['학생', '과목', '반이름', '담당강사', '날짜']], use_container_width=True)

    with tab2:
        if df_s.empty or df_t.empty or df_c.empty:
            st.warning("학생, 강사, 반 데이터가 모두 있어야 배정이 가능합니다.")
        else:
            c_left, c_right = st.columns([1, 1.2])
            with c_left:
                st.markdown("### 1️⃣ 학생 선택")
                df_s['L'] = df_s.iloc[:,0] + " (" + df_s.iloc[:,4] + ")" 
                s_list = df_s['L'].tolist()
                sel_student_label = st.selectbox("학생을 선택하세요", s_list, key="assign_sel_std")

                if sel_student_label:
                    real_name = sel_student_label.split(' (')[0]
                    s_info = df_s[df_s.iloc[:,0] == real_name].iloc[0]
                    st.success(f"👤 **{s_info.iloc[0]}** ({s_info.iloc[3]})")
                    
                    st.divider()
                    st.markdown("### 2️⃣ 수업 담기")
                    all_subjects = sorted(get_col_data(df_t, '과목', 1).unique().tolist())
                    sel_subj = st.selectbox("과목 선택", ["(선택하세요)"] + all_subjects)
                    
                    if sel_subj != "(선택하세요)":
                        sub_teachers = df_t[df_t.iloc[:, 1] == sel_subj].iloc[:, 0].tolist()
                        if not sub_teachers: st.error("해당 과목의 강사가 없습니다.")
                        else:
                            sel_tea = st.selectbox("강사 선택", ["(선택하세요)"] + sub_teachers)
                            if sel_tea and sel_tea != "(선택하세요)":
                                t_classes = df_c[df_c.iloc[:, 1].str.contains(sel_tea)]
                                if t_classes.empty: st.error("해당 강사의 개설된 반이 없습니다.")
                                else:
                                    cls_opts = [f"{r.iloc[0]} ({r.iloc[2]})" for _, r in t_classes.iterrows()]
                                    sel_cls_full = st.selectbox("반 선택", ["(선택하세요)"] + cls_opts)
                                    if sel_cls_full and sel_cls_full != "(선택하세요)":
                                        real_cls_name = sel_cls_full.split(' (')[0]
                                        if st.button("⬇️ 장바구니에 담기", type="primary"):
                                            is_exist = False
                                            for item in st.session_state.draft_enrolls:
                                                if item['학생'] == real_name and item['반이름'] == real_cls_name and item['과목'] == sel_subj: is_exist = True
                                            if not df_e.empty:
                                                try:
                                                    # 이미 수강중인지 확인 (수강종료된 반은 다시 담을 수 있음)
                                                    already = df_e[(df_e.iloc[:,0]==real_name) & (df_e.iloc[:,1]==sel_subj) & (df_e.iloc[:,2]==real_cls_name) & (df_e.get('상태', '') != '수강종료')]
                                                    if not already.empty: is_exist = True
                                                except: pass
                                            if is_exist: st.warning("이미 담겼거나 수강 중인 수업입니다.")
                                            else:
                                                st.session_state.draft_enrolls.append({
                                                    '학생': real_name, '과목': sel_subj, '반이름': real_cls_name,
                                                    '담당강사': sel_tea, '날짜': str(datetime.today().date()),
                                                    '상태': '수강중', '종료일': '' # 새로운 데이터 등록 시 기본값
                                                })
                                                st.rerun()

            with c_right:
                st.markdown(f"### 🛒 수강 신청 목록 ({len(st.session_state.draft_enrolls)}건)")
                if st.session_state.draft_enrolls:
                    for i, item in enumerate(st.session_state.draft_enrolls):
                        with st.container():
                            cc1, cc2 = st.columns([4, 1])
                            cc1.markdown(f"**{item['학생']}** - :blue[[{item['과목']}]] {item['반이름']} ({item['담당강사']})")
                            if cc2.button("삭제", key=f"draft_del_{i}"):
                                del st.session_state.draft_enrolls[i]
                                st.rerun()
                    st.divider()
                    if not st.session_state.confirm_save_cart:
                        if st.button("💾 전체 저장하기 (배정 확정)", type="primary", use_container_width=True):
                            st.session_state.confirm_save_cart = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ 총 {len(st.session_state.draft_enrolls)}건의 수업을 배정하시겠습니까?")
                        col_y, col_n = st.columns([1, 1])
                        if col_y.button("네, 저장합니다", type="primary", use_container_width=True):
                            add_data_bulk('enrollments', st.session_state.draft_enrolls)
                            st.session_state.draft_enrolls = []
                            st.session_state.confirm_save_cart = False
                            show_center_message("✅ 배정 완료!")
                            time.sleep(1.5); st.rerun()
                        if col_n.button("취소", use_container_width=True):
                            st.session_state.confirm_save_cart = False
                            st.rerun()
                else: st.info("왼쪽에서 수업을 선택하고 '담기'를 눌러주세요.")

                if sel_student_label:
                    st.markdown("---")
                    st.markdown("#### 📋 현재 수강 중인 수업")
                    real_name_curr = sel_student_label.split(' (')[0]
                    if not df_e.empty:
                        try:
                            # 현재 수강중인(수강종료가 아닌) 수업만 표시
                            if '상태' not in df_e.columns: df_e['상태'] = '수강중'
                            curr_list = df_e[(df_e.iloc[:,0] == real_name_curr) & (df_e['상태'] != '수강종료')]
                            
                            if not curr_list.empty:
                                for idx, row in curr_list.iterrows():
                                    subj_val, cls_val, tea_val = row.iloc[1], row.iloc[2], row.iloc[3]
                                    unique_key = f"{real_name_curr}_{cls_val}_{subj_val}"
                                    c1, c2 = st.columns([4, 1.2])
                                    c1.markdown(f"• :blue[[{subj_val}]] {cls_val} (담당: {tea_val})")
                                    
                                    if st.session_state.confirm_cancel_target != unique_key:
                                        if c2.button("수강종료", key=f"btn_cancel_{unique_key}"):
                                            st.session_state.confirm_cancel_target = unique_key
                                            st.rerun()
                                    else:
                                        with c2:
                                            st.markdown("**:red[종료확인?]**")
                                            y_col, n_col = st.columns(2)
                                            if y_col.button("네", key=f"yes_{unique_key}"):
                                                # [핵심] 완전 삭제(delete) 대신 상태 변경(cancel_class_soft) 실행
                                                cancel_class_soft(real_name_curr, cls_val)
                                                st.session_state.confirm_cancel_target = None
                                                show_center_message("수강 종료 처리 완료!")
                                                time.sleep(1); st.rerun()
                                            if n_col.button("아니오", key=f"no_{unique_key}"):
                                                st.session_state.confirm_cancel_target = None
                                                st.rerun()
                            else: st.caption("현재 수강 중인 수업이 없습니다.")
                        except: st.caption("데이터 로드 중...")
                    else: st.caption("현재 수강 중인 수업이 없습니다.")

# ==========================================
# 5. QR 키오스크(출석)
# ==========================================
elif menu == "5. QR 키오스크(출석)":
    st.empty(); st.markdown("""<style>.block-container{padding-top:2rem;} h1{text-align:center;color:#1565C0;}</style>""", unsafe_allow_html=True)
    st.title("📷 형설지공 학원 출석 키오스크"); st.write("카메라에 QR코드를 비춰주세요.")
    img_file_buffer = st.camera_input("QR 스캔", label_visibility="hidden")
    if img_file_buffer:
        decoded_text = decode_qr(img_file_buffer)
        if decoded_text:
            try:
                s_name, s_phone4 = decoded_text.split('/')
                df_s, df_e, df_c = load_data('students'), load_data('enrollments'), load_data('classes')
                student_row = df_s[df_s['이름'] == s_name]
                if student_row.empty: st.error("등록되지 않은 학생입니다.")
                else:
                    now = datetime.now()
                    today_weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
                    current_time_str = now.strftime("%H:%M")
                    my_classes = df_e[df_e.iloc[:,0] == s_name]
                    found_class_today = False
                    
                    if not my_classes.empty:
                        for _, row in my_classes.iterrows():
                            c_name = row.iloc[1]
                            c_info = df_c[df_c.iloc[:,0] == c_name]
                            if not c_info.empty:
                                c_row = c_info.iloc[0]
                                schedule_str = str(c_row.iloc[2])
                                
                                # [추가] 보강반일 경우 오늘 날짜가 기간 내에 있는지 확인
                                c_type = c_row['구분'] if '구분' in df_c.columns else '정규'
                                is_valid_today = True
                                if c_type == '보강':
                                    c_start = c_row['시작일'] if '시작일' in df_c.columns else ''
                                    c_end = c_row['종료일'] if '종료일' in df_c.columns else ''
                                    try:
                                        s_dt = datetime.strptime(str(c_start), "%Y-%m-%d").date()
                                        e_dt = datetime.strptime(str(c_end), "%Y-%m-%d").date()
                                        if not (s_dt <= now.date() <= e_dt): is_valid_today = False
                                    except: pass
                                
                                if is_valid_today and today_weekday in schedule_str:
                                    for part in schedule_str.split(','):
                                        if part.strip().startswith(today_weekday):
                                            t_range = part.strip().split()[1]
                                            start_time_str = t_range.split('-')[0]
                                            s_time = datetime.strptime(start_time_str, "%H:%M")
                                            s_time = now.replace(hour=s_time.hour, minute=s_time.minute, second=0)
                                            
                                            status = "출석"
                                            msg = f"{s_name} 학생, 환영합니다! (수업: {c_name})"
                                            limit_time = s_time + timedelta(minutes=10)
                                            
                                            if now > limit_time: 
                                                status = "지각"
                                                msg = f"🚨 {s_name} 학생, 지각입니다! (수업: {c_name})"
                                            elif now < (s_time - timedelta(minutes=60)): 
                                                status = "보강/자습"
                                                msg = f"{s_name} 학생, 일찍 왔네요! 자습하세요."
                                                
                                            add_data('attendance', {'날짜': str(now.date()), '반이름': c_name, '학생': s_name, '상태': status, '비고': f"QR체크({current_time_str})"})
                                            if status == "지각": st.error(msg)
                                            else: st.success(msg)
                                            found_class_today = True
                                            break
                    if not found_class_today:
                        st.info(f"{s_name} 학생, 오늘은 정규 및 보강 수업이 없습니다."); 
                        if st.button("자습 출석 확인"): 
                            add_data('attendance', {'날짜': str(now.date()), '반이름': "자습", '학생': s_name, '상태': "보강", '비고': f"QR체크({current_time_str})"})
                            st.success("자습 출석 처리되었습니다.")
            except: st.error("QR 오류")
        else: st.warning("QR 인식 실패")

# ==========================================
# 6. 출석 관리
# ==========================================
elif menu == "6. 출석 관리":
    st.subheader("✅ 수동 출석 체크")
    df_e = load_data('enrollments')
    if df_e.empty: st.info("수강 배정 데이터가 없습니다. 먼저 수강 배정을 진행해주세요.")
    else:
        c1, c2 = st.columns(2)
        td = c1.date_input("날짜", datetime.today())
        class_list = sorted(df_e.iloc[:,2].unique().tolist())
        cls = c2.selectbox("반 선택", class_list)
        if cls:
            stds = sorted(list(set(df_e[df_e.iloc[:,2] == cls].iloc[:,0].tolist())))
            st.divider()
            st.markdown(f"#### 📢 '{cls}' 출석부 ({len(stds)}명)")
            with st.form("att_form", clear_on_submit=True):
                cols = st.columns(4)
                res = {}
                for i, s in enumerate(stds):
                    with cols[i % 4]:
                        is_present = st.checkbox(s, value=True, key=f"att_chk_{s}")
                        res[s] = "출석" if is_present else "결석"
                st.markdown("---")
                memo = st.text_input("특이사항 (선택)", placeholder="지각, 조퇴 등 특이사항이 있다면 적어주세요.")
                if st.form_submit_button("출석 저장"):
                    if not stds: st.error("수강생이 없습니다.")
                    else:
                        save_list = []
                        for s_name, status in res.items():
                            save_list.append({'날짜': str(td), '반이름': cls, '학생': s_name, '상태': status, '비고': memo})
                        add_data_bulk('attendance', save_list)
                        show_center_message(f"✅ {cls} 출석 저장 완료!")
                        time.sleep(1); st.rerun()

# ==========================================
# 7. 강사별 시간표
# ==========================================
elif menu == "7. 강사별 시간표":
    st.subheader("📅 강사별 주간 시간표")
    df_c, df_t, df_e, df_s = load_data('classes'), load_data('teachers'), load_data('enrollments'), load_data('students')
    if not df_t.empty and not df_c.empty:
        t_names = get_col_data(df_t, '이름', 0); t_subs = get_col_data(df_t, '과목', 1)
        days_ko = ["월", "화", "수", "목", "금", "토", "일"]
        tabs = st.tabs([f"{n} ({s})" for n, s in zip(t_names, t_subs)])
        for idx, teacher_raw in enumerate(t_names):
            with tabs[idx]:
                my_classes = df_c[df_c.iloc[:,1].str.contains(teacher_raw)]
                local_times = set()
                if not my_classes.empty:
                    for _, row in my_classes.iterrows():
                        for tp in str(row.iloc[2]).split(','):
                            try: local_times.add(tp.split()[1].split('-')[0])
                            except: pass
                sorted_timeline = sort_time_strings(list(local_times))
                if not sorted_timeline: st.info("수업 없음")
                else:
                    cols = st.columns([0.5] + [1]*7)
                    cols[0].write("")
                    for i, d in enumerate(days_ko): cols[i+1].markdown(f"<div class='day-header'>{d}</div>", unsafe_allow_html=True)
                    for start_t in sorted_timeline:
                        cols = st.columns([0.5] + [1]*7)
                        max_end = start_t
                        for _, row in my_classes.iterrows():
                             for tp in str(row.iloc[2]).split(','):
                                try:
                                    s, e = tp.split()[1].split('-')
                                    if s == start_t and e > max_end: max_end = e
                                except: pass
                        with cols[0]: st.markdown(f"<div class='time-axis-card'><span class='tac-start'>{start_t}</span><span class='tac-tilde'>~</span><span class='tac-end'>{max_end}</span></div>", unsafe_allow_html=True)
                        for i, d in enumerate(days_ko):
                            found_list = []
                            for _, row in my_classes.iterrows():
                                for tp in str(row.iloc[2]).split(','):
                                    if tp.strip().startswith(d):
                                        try:
                                            s, e = tp.split()[1].split('-')
                                            if s == start_t:
                                                c_type = row['구분'] if '구분' in df_c.columns else '정규'
                                                c_reason = row['사유'] if '사유' in df_c.columns else ''
                                                found_list.append({
                                                    'sub': t_subs.iloc[idx], 'name': row.iloc[0], 
                                                    'room': row.iloc[3] if len(row)>3 else "기타", 'time': tp.split()[1], 
                                                    'dur': calc_duration_min(s, e), 'type': c_type, 'reason': c_reason
                                                })
                                        except: pass
                            with cols[i+1]:
                                if found_list:
                                    sub_cols = st.columns(len(found_list))
                                    for si, found in enumerate(found_list):
                                        with sub_cols[si]:
                                            detail_info = []
                                            if not df_e.empty and not df_s.empty:
                                                try:
                                                    std_names = df_e[df_e.iloc[:, 2] == found['name']].iloc[:,0].tolist()
                                                    matched_std = df_s[df_s.iloc[:,0].isin(std_names)]
                                                    for _, r in matched_std.iterrows(): detail_info.append(f"• {r.iloc[0]} ({r.iloc[3]}, {r.iloc[4]})")
                                                except: pass
                                            std_count = len(detail_info)
                                            
                                            # [핵심] 보강반 오렌지색 스타일 적용
                                            if found['type'] == '보강':
                                                card_style = "background-color: #FFF3E0; border-left-color: #FF9800;"
                                                badge = f"<div style='background-color:#FF9800; color:white; padding:2px 4px; border-radius:4px; font-size:0.65rem; display:inline-block; margin-bottom:3px;'>보강: {found['reason']}</div>"
                                            else:
                                                card_style = "background-color: #E3F2FD; border-left-color: #1565C0;"
                                                badge = ""
                                                
                                            st.markdown(f"""<div class='class-card' style='{card_style}'>{badge}<div class='cc-subject'>{found['sub']}</div><div class='cc-name'>{found['name']}</div><div class='cc-info'>🏫 {found['room']}</div><div class='cc-time'>⏰ {found['time']}</div><div class='cc-duration'>⏳ {found['dur']}분</div></div>""", unsafe_allow_html=True)
                                            with st.popover(f"👥 {std_count}명", use_container_width=True):
                                                st.markdown(f"**{found['name']} 수강생 ({std_count}명)**")
                                                if detail_info:
                                                    for info in sorted(detail_info): st.markdown(info)
                                                else: st.caption("수강생이 없습니다.")
                                else: st.markdown("<div class='empty-card'></div>", unsafe_allow_html=True)

# ==========================================
# 8. 강의실별 시간표
# ==========================================
elif menu == "8. 강의실별 시간표":
    st.subheader("🏫 강의실 배정 현황")
    df_c, df_e, df_s = load_data('classes'), load_data('enrollments'), load_data('students')
    if not df_c.empty:
        days_ko = ["월", "화", "수", "목", "금", "토", "일"]
        d_tabs = st.tabs(days_ko)
        rooms = ["기타", "101호", "102호", "103호", "104호"]
        for idx, day in enumerate(days_ko):
            with d_tabs[idx]:
                day_times = set()
                day_classes = []
                for _, row in df_c.iterrows():
                    for tp in str(row.iloc[2]).split(','):
                        if tp.strip().startswith(day):
                            try:
                                t_range = tp.split()[1]
                                day_times.add(t_range.split('-')[0])
                                day_classes.append((row, t_range))
                            except: pass
                sorted_timeline = sort_time_strings(list(day_times))
                if not sorted_timeline: st.info("수업 없음")
                else:
                    cols = st.columns([0.3] + [1]*len(rooms))
                    cols[0].write("")
                    for i, r in enumerate(rooms): cols[i+1].markdown(f"<div class='day-header'>{r}</div>", unsafe_allow_html=True)
                    for start_t in sorted_timeline:
                        cols = st.columns([0.3] + [1]*len(rooms))
                        max_end = start_t
                        for r_data, t_str in day_classes:
                            try:
                                s, e = t_str.split('-')
                                if s == start_t and e > max_end: max_end = e
                            except: pass
                        with cols[0]: st.markdown(f"<div class='time-axis-card'><span class='tac-start'>{start_t}</span><span class='tac-tilde'>~</span><span class='tac-end'>{max_end}</span></div>", unsafe_allow_html=True)
                        for i, r in enumerate(rooms):
                            found_list = []
                            for r_data, t_str in day_classes:
                                curr_r = str(r_data.iloc[3]) if len(r_data)>3 else "기타"
                                if curr_r not in rooms: curr_r = "기타"
                                if curr_r == r:
                                    try:
                                        s, e = t_str.split('-')
                                        if s == start_t:
                                            full_tea = str(r_data.iloc[1])
                                            tn = full_tea.split('(')[0] if "(" in full_tea else full_tea
                                            sub = full_tea.split('(')[1].replace(')', '') if "(" in full_tea else "과목"
                                            c_type = r_data['구분'] if '구분' in df_c.columns else '정규'
                                            c_reason = r_data['사유'] if '사유' in df_c.columns else ''
                                            found_list.append({'sub': sub, 'name': r_data.iloc[0], 'tea': tn, 'time': t_str, 'dur': calc_duration_min(s, e), 'type': c_type, 'reason': c_reason})
                                    except: pass
                            with cols[i+1]:
                                if found_list:
                                    sub_cols = st.columns(len(found_list))
                                    for si, found in enumerate(found_list):
                                        with sub_cols[si]:
                                            detail_info = []
                                            if not df_e.empty and not df_s.empty:
                                                try:
                                                    std_names = df_e[df_e.iloc[:, 2] == found['name']].iloc[:,0].tolist()
                                                    matched_std = df_s[df_s.iloc[:,0].isin(std_names)]
                                                    for _, r in matched_std.iterrows(): detail_info.append(f"• {r.iloc[0]} ({r.iloc[3]}, {r.iloc[4]})")
                                                except: pass
                                            std_count = len(detail_info)
                                            
                                            # [핵심] 보강반 오렌지색 스타일 적용
                                            if found['type'] == '보강':
                                                card_style = "background-color: #FFF3E0; border-left-color: #FF9800;"
                                                badge = f"<div style='background-color:#FF9800; color:white; padding:2px 4px; border-radius:4px; font-size:0.65rem; display:inline-block; margin-bottom:3px;'>보강: {found['reason']}</div>"
                                            else:
                                                card_style = "background-color: #E8F5E9; border-left-color: #43A047;" # 강의실 기본은 초록색 유지
                                                badge = ""

                                            st.markdown(f"""<div class='class-card' style='{card_style}'>{badge}<div class='cc-subject'>{found['sub']}</div><div class='cc-name'>{found['name']}</div><div class='cc-info'>👨‍🏫 {found['tea']}</div><div class='cc-time'>⏰ {found['time']}</div><div class='cc-duration'>⏳ {found['dur']}분</div></div>""", unsafe_allow_html=True)
                                            with st.popover(f"👥 {std_count}명", use_container_width=True):
                                                st.markdown(f"**{found['name']} 수강생 ({std_count}명)**")
                                                for info in sorted(detail_info): st.markdown(info)
                                else: st.markdown("<div class='empty-card'></div>", unsafe_allow_html=True)

# ==========================================
# 9. 학생 개인별 종합
# ==========================================
elif menu == "9. 학생 개인별 종합":
    st.subheader("📊 학생 개인별 종합 기록부")
    df_s = load_data('students')
    df_e = load_data('enrollments')
    df_a = load_data('attendance')

    if df_s.empty: st.warning("등록된 학생이 없습니다.")
    else:
        df_s['L'] = df_s.iloc[:,0] + " (" + df_s.iloc[:,4] + ")"
        s_list = df_s['L'].tolist()
        s_sel = st.selectbox("학생을 선택하세요", s_list)
        
        if s_sel:
            real_name = s_sel.split(' (')[0]
            s_info = df_s[df_s.iloc[:,0] == real_name].iloc[0]
            
            st.divider()
            col_p1, col_p2 = st.columns([1, 4])
            with col_p1:
                qr_img = generate_styled_qr(f"{real_name}", real_name)
                st.image(qr_img, width=130)
            with col_p2:
                st.markdown(f"### **{s_info.iloc[0]}**")
                st.caption(f"🏫 {s_info.iloc[4]} ({s_info.iloc[3]}) | 📞 {s_info.iloc[1]}")
                st.caption(f"👪 학부모: {s_info.iloc[2]}")

            st.markdown("---")
            st.markdown("##### 📘 수강 및 배정 현황")
            if not df_e.empty:
                try:
                    my_classes = df_e[df_e.iloc[:,0] == real_name]
                    if my_classes.empty: st.info("현재 수강 중인 수업이 없습니다.")
                    else:
                        display_df = my_classes.iloc[:, [1, 2, 3]]
                        display_df.columns = ["수강 과목", "수강 반", "담당 선생님"]
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                except: st.error("데이터 구조를 불러오는 중입니다.")
            else: st.info("수강 기록이 없습니다.")

            st.divider()
            if 'view_year' not in st.session_state:
                st.session_state.view_year = datetime.today().year
                st.session_state.view_month = datetime.today().month

            c_nav1, c_nav2, c_nav3 = st.columns([1, 2, 1])
            with c_nav1:
                if st.button("◀ 이전 달", use_container_width=True):
                    st.session_state.view_month -= 1
                    if st.session_state.view_month == 0:
                        st.session_state.view_month = 12
                        st.session_state.view_year -= 1
                    st.rerun()
            with c_nav2: st.markdown(f"<h4 style='text-align: center; margin-top:5px;'>📅 {st.session_state.view_year}년 {st.session_state.view_month}월</h4>", unsafe_allow_html=True)
            with c_nav3:
                if st.button("다음 달 ▶", use_container_width=True):
                    st.session_state.view_month += 1
                    if st.session_state.view_month == 13:
                        st.session_state.view_month = 1
                        st.session_state.view_year += 1
                    st.rerun()

            att_map = {}
            if not df_a.empty:
                try:
                    target_ym = f"{st.session_state.view_year}-{st.session_state.view_month:02d}"
                    my_att = df_a[df_a.iloc[:,2] == real_name]
                    month_data = my_att[my_att.iloc[:,0].astype(str).str.contains(target_ym)]
                    for _, row in month_data.iterrows():
                        d_str = str(row.iloc[0])
                        day_int = int(d_str.split('-')[2])
                        status = row.iloc[3]
                        if day_int not in att_map: att_map[day_int] = []
                        att_map[day_int].append(status)
                except: pass

            d_cols = st.columns(7)
            days_ko = ["월", "화", "수", "목", "금", "토", "일"]
            for i, d in enumerate(days_ko): d_cols[i].markdown(f"<div style='text-align:center; color:gray; font-size:0.8rem;'>{d}</div>", unsafe_allow_html=True)
            month_cal = calendar.monthcalendar(st.session_state.view_year, st.session_state.view_month)
            for week in month_cal:
                w_cols = st.columns(7)
                for i, day in enumerate(week):
                    with w_cols[i]:
                        if day == 0: st.write("") 
                        else:
                            st.markdown(f"**{day}**")
                            if day in att_map:
                                statuses = att_map[day]
                                for s in statuses:
                                    if s == '출석': st.markdown(f"<span style='color:green; font-size:0.8rem;'>🟢 출석</span>", unsafe_allow_html=True)
                                    elif s == '지각': st.markdown(f"<span style='color:orange; font-size:0.8rem;'>🟠 지각</span>", unsafe_allow_html=True)
                                    elif s == '결석': st.markdown(f"<span style='color:red; font-size:0.8rem;'>🔴 결석</span>", unsafe_allow_html=True)
                            else: st.markdown("<br>", unsafe_allow_html=True)
            
            if att_map:
                st.markdown("---")
                all_statuses = [s for sublist in att_map.values() for s in sublist]
                c1, c2, c3 = st.columns(3)
                c1.metric("이달의 출석", f"{all_statuses.count('출석')}회")
                c2.metric("지각", f"{all_statuses.count('지각')}회")
                c3.metric("결석", f"{all_statuses.count('결석')}회")

# ==========================================
# 10. 일일 업무 일지 (강사용 스마트 화면)
# ==========================================
elif menu == "10. 일일 업무 일지":
    st.subheader("일일 업무 일지 작성 및 피드백 확인")
    st.markdown("오늘 진행한 수업 내용과 학생 개별 특이사항을 기록해 주세요.")
    
    df_t, df_c, df_s = load_data('teachers'), load_data('classes'), load_data('students')
    
    # [핵심] 로그인한 사람의 역할(Role)에 따라 선택지 완벽 분리
    if st.session_state['role'] == 'teacher':
        # 강사는 본인 이름으로만 고정!
        teacher_names = [st.session_state['username']]
        # 반 목록도 본인이 담당하는 반만 쏙 뽑아옵니다.
        my_classes = df_c[df_c.iloc[:, 1].str.contains(st.session_state['username'])] if not df_c.empty else pd.DataFrame()
        class_names = my_classes.iloc[:, 0].tolist() if not my_classes.empty else ["담당 배정된 반이 없습니다."]
    else:
        # 원장님은 전체 다 볼 수 있음!
        teacher_names = df_t.iloc[:, 0].tolist() if not df_t.empty else ["등록된 강사 없음"]
        class_names = df_c.iloc[:, 0].tolist() if not df_c.empty else ["등록된 반 없음"]
        
    student_names = df_s.iloc[:, 0].tolist() if not df_s.empty else ["등록된 학생 없음"]
    
    tab1, tab2, tab3 = st.tabs(["📚 반별 수업 일지 작성", "🧑‍🎓 학생 개별 기록 작성", "💬 원장님 피드백 확인"])
    
    # ---------------------------------------------------------
    # 탭 1: 반별 수업 일지 작성 폼
    # ---------------------------------------------------------
    with tab1:
        with st.form("class_log_form", clear_on_submit=True):
            st.markdown("##### 📚 오늘 수업하신 반의 진도와 숙제를 입력하세요.")
            col1, col2, col3 = st.columns(3)
            with col1: log_date = st.date_input("날짜", datetime.today().date())
            with col2: log_teacher = st.selectbox("담당 강사", teacher_names)
            with col3: log_class = st.selectbox("대상 반", class_names)
            
            log_book = st.text_input("사용 교재 (예: 개념원리 수학상 50p~65p)")
            log_progress = st.text_area("수업 진도 및 내용 (최대한 상세히 적어주세요)", height=100)
            log_homework = st.text_input("부과된 숙제 (없으면 '없음'으로 기재)")
            
            if st.form_submit_button("반별 일지 저장하기", use_container_width=True):
                if log_class == "담당 배정된 반이 없습니다.": 
                    st.error("배정된 반이 없습니다. 원장님께 문의해주세요.")
                elif not log_progress: 
                    st.warning("수업 진도 및 내용을 입력해 주세요.")
                else:
                    add_data('class_logs', {
                        '날짜': str(log_date), '강사명': log_teacher, '대상반': log_class, 
                        '사용교재': log_book, '수업진도': log_progress, '부과된숙제': log_homework
                    })
                    st.success(f"✅ [{log_class}] 반의 일지가 저장되었습니다!")

    # ---------------------------------------------------------
    # 탭 2: 학생 개별 기록 작성 폼
    # ---------------------------------------------------------
    with tab2:
        with st.form("student_record_form", clear_on_submit=True):
            st.markdown("##### 🧑‍🎓 특정 학생의 테스트 결과나 상담, 특이사항을 기록하세요.")
            col1, col2, col3 = st.columns(3)
            with col1: sr_date = st.date_input("날짜", datetime.today().date())
            with col2: sr_teacher = st.selectbox("작성 강사", teacher_names)
            with col3: sr_student = st.selectbox("대상 학생", student_names)
            
            col_cat, col_score = st.columns([1, 1])
            with col_cat: sr_category = st.selectbox("기록 분류", ["테스트 결과", "학생 상담", "학부모 상담", "특이사항 (태도 등)"])
            with col_score: sr_score = st.text_input("테스트 점수 (테스트 결과인 경우에만 숫자 입력)")
            sr_details = st.text_area("세부 내용", height=150)
            
            if st.form_submit_button("학생 개별 기록 저장하기", use_container_width=True):
                if sr_student == "등록된 학생 없음": 
                    st.error("등록된 학생이 없습니다.")
                elif not sr_details: 
                    st.warning("세부 내용을 입력해 주세요.")
                else:
                    add_data('student_records', {
                        '날짜': str(sr_date), '강사명': sr_teacher, '학생명': sr_student, 
                        '분류': sr_category, '세부내용': sr_details, '점수': sr_score if sr_score.strip() else ""
                    })
                    st.success(f"✅ [{sr_student}] 학생 기록이 저장되었습니다!")

    # ---------------------------------------------------------
    # 탭 3: 내 일지 피드백 확인
    # ---------------------------------------------------------
    with tab3:
        # [핵심] 강사는 무조건 본인 이름으로 검색 고정!
        if st.session_state['role'] == 'teacher':
            search_teacher = st.session_state['username']
            st.markdown(f"##### 💬 **{search_teacher} 강사님**, 원장님이 남겨주신 피드백을 확인하세요.")
        else:
            search_teacher = st.selectbox("조회할 강사명 선택", teacher_names)
            st.markdown(f"##### 💬 **{search_teacher} 강사님**의 피드백 내역")
            
        df_cl, df_sr = load_data('class_logs'), load_data('student_records')
        has_feedback = False
        st.divider()
        
        # 1) 반별 수업 일지 피드백 렌더링
        if not df_cl.empty and '관리자코멘트' in df_cl.columns:
            my_cl_fb = df_cl[(df_cl['강사명'].astype(str) == search_teacher) & (df_cl['관리자코멘트'].astype(str).str.strip() != '')]
            if not my_cl_fb.empty:
                st.markdown("###### 📚 반별 수업 일지 피드백")
                for _, row in my_cl_fb.tail(10)[::-1].iterrows():
                    has_feedback = True
                    with st.expander(f"📅 {row['날짜']} | [{row['대상반']}] 수업 일지", expanded=True):
                        st.markdown(f"**📖 교재:** {row.get('사용교재', '')}")
                        st.markdown(f"**🏃 진도:**\n{row.get('수업진도', '')}")
                        st.markdown(f"**📝 숙제:** {row.get('부과된숙제', '')}")
                        st.info(f"💬 **원장님 코멘트:**\n{row['관리자코멘트']}")
                        
        # 2) 학생 개별 기록 피드백 렌더링
        if not df_sr.empty and '관리자코멘트' in df_sr.columns:
            my_sr_fb = df_sr[(df_sr['강사명'].astype(str) == search_teacher) & (df_sr['관리자코멘트'].astype(str).str.strip() != '')]
            if not my_sr_fb.empty:
                st.markdown("---")
                st.markdown("###### 🧑‍🎓 학생 개별 기록 피드백")
                for _, row in my_sr_fb.tail(10)[::-1].iterrows():
                    has_feedback = True
                    score_str = f" (점수: {row.get('점수', '')}점)" if str(row.get('점수', '')).strip() else ""
                    with st.expander(f"📅 {row['날짜']} | [{row['학생명']}] - {row.get('분류', '')}{score_str}", expanded=True):
                        st.markdown(f"**📋 내용:**\n{row.get('세부내용', '')}")
                        st.success(f"💬 **원장님 코멘트:**\n{row['관리자코멘트']}")
                    
        if not has_feedback: 
            st.caption("도착한 피드백이 없습니다. 오늘도 수고 많으셨습니다! 😊")

# ==========================================
# 업무 일지 관리 (원장님 피드백 화면)
# ==========================================
elif menu == "업무 일지 관리":
    st.subheader("업무 일지 열람 및 관리자 피드백")
    st.markdown("강사님들이 작성한 일지를 확인하고, 피드백이나 격려의 코멘트를 남겨주세요.")
    
    df_cl = load_data('class_logs')
    df_sr = load_data('student_records')
    df_t = load_data('teachers')
    
    teacher_names = df_t.iloc[:, 0].tolist() if not df_t.empty else []
    
    # 1. 날짜 및 강사 필터 선택 (나란히 배치)
    col_d, col_t = st.columns([1, 2])
    with col_d:
        selected_date = st.date_input("🗓️ 조회 날짜 선택", datetime.today().date(), key="fb_date")
        target_date_str = str(selected_date)
    with col_t:
        # [핵심] 여러 명의 강사를 선택할 수 있는 필터 (아무것도 안 고르면 전체 표시)
        selected_teachers = st.multiselect("👨‍🏫 강사 필터 (비워두면 전체 강사 조회)", teacher_names, default=[])
    
    # 코멘트 저장을 위한 맞춤형 내부 함수
    def update_feedback(sheet_name, r_date, r_teacher, r_target_col, r_target_val, new_comment):
        try:
            client = init_connection()
            ws = safe_api_call(client.open("Academy_DB").worksheet, sheet_name)
            data = safe_api_call(ws.get_all_records)
            df = pd.DataFrame(data)
            headers = safe_api_call(ws.row_values, 1)
            
            if '관리자코멘트' not in headers:
                safe_api_call(ws.update_cell, 1, len(headers)+1, '관리자코멘트')
                headers.append('관리자코멘트')
                
            match = df[(df['날짜'].astype(str) == str(r_date)) & 
                       (df['강사명'].astype(str) == str(r_teacher)) & 
                       (df[r_target_col].astype(str) == str(r_target_val))]
            
            if not match.empty:
                row_idx = int(match.index[0]) + 2
                col_idx = headers.index('관리자코멘트') + 1
                safe_api_call(ws.update_cell, row_idx, col_idx, str(new_comment))
                clear_cache()
                return True
            return False
        except Exception as e:
            st.error(f"코멘트 저장 실패: {e}")
            return False

    tab1, tab2 = st.tabs(["📚 반별 수업 일지 피드백", "🧑‍🎓 학생 개별 기록 피드백"])
    
    # ---------------------------------------------------------
    # 탭 1: 반별 수업 일지 열람 및 피드백
    # ---------------------------------------------------------
    with tab1:
        if df_cl.empty:
            st.info("작성된 수업 일지가 없습니다.")
        else:
            daily_cl = df_cl[df_cl['날짜'].astype(str) == target_date_str]
            
            # [핵심] 선택한 강사만 필터링
            if selected_teachers:
                daily_cl = daily_cl[daily_cl['강사명'].isin(selected_teachers)]
                
            if daily_cl.empty:
                st.info(f"해당 조건으로 작성된 수업 일지가 없습니다.")
            else:
                for idx, row in daily_cl.iterrows():
                    c_teacher = row.get('강사명', '')
                    c_class = row.get('대상반', '')
                    c_book = row.get('사용교재', '')
                    c_prog = row.get('수업진도', '')
                    c_hw = row.get('부과된숙제', '')
                    c_comment = row.get('관리자코멘트', '') if '관리자코멘트' in row else ''
                    
                    with st.expander(f"👨‍🏫 {c_teacher} 강사님 - [{c_class}] 수업 일지", expanded=True):
                        col_info, col_fb = st.columns([1.5, 1])
                        with col_info:
                            st.markdown(f"**📖 사용 교재:** {c_book}")
                            st.markdown(f"**🏃 수업 진도 및 내용:**\n{c_prog}")
                            st.markdown(f"**📝 숙제:** {c_hw}")
                        with col_fb:
                            new_fb = st.text_area("💬 원장님 코멘트 남기기", value=c_comment, key=f"fb_cl_{idx}", height=120)
                            if st.button("💾 코멘트 저장", key=f"btn_cl_{idx}", type="primary", use_container_width=True):
                                if update_feedback('class_logs', target_date_str, c_teacher, '대상반', c_class, new_fb):
                                    show_center_message("✅ 코멘트가 저장되었습니다!")
                                    time.sleep(1); st.rerun()
    
    # ---------------------------------------------------------
    # 탭 2: 학생 개별 기록 열람 및 피드백
    # ---------------------------------------------------------
    with tab2:
        if df_sr.empty:
            st.info("작성된 학생 개별 기록이 없습니다.")
        else:
            daily_sr = df_sr[df_sr['날짜'].astype(str) == target_date_str]
            
            # [핵심] 선택한 강사만 필터링
            if selected_teachers:
                daily_sr = daily_sr[daily_sr['강사명'].isin(selected_teachers)]
                
            if daily_sr.empty:
                st.info(f"해당 조건으로 작성된 학생 개별 기록이 없습니다.")
            else:
                for idx, row in daily_sr.iterrows():
                    s_teacher = row.get('강사명', '')
                    s_student = row.get('학생명', '')
                    s_cat = row.get('분류', '')
                    s_detail = row.get('세부내용', '')
                    s_score = row.get('점수', '')
                    s_comment = row.get('관리자코멘트', '') if '관리자코멘트' in row else ''
                    
                    score_str = f" (점수: {s_score}점)" if str(s_score).strip() else ""
                    
                    with st.expander(f"🧑‍🎓 {s_student} 학생 - {s_cat}{score_str} / 작성자: {s_teacher} 강사", expanded=True):
                        col_info, col_fb = st.columns([1.5, 1])
                        with col_info:
                            st.markdown(f"**📋 세부 내용:**\n{s_detail}")
                        with col_fb:
                            new_fb = st.text_area("💬 원장님 코멘트 남기기", value=s_comment, key=f"fb_sr_{idx}", height=120)
                            if st.button("💾 코멘트 저장", key=f"btn_sr_{idx}", type="primary", use_container_width=True):
                                if update_feedback('student_records', target_date_str, s_teacher, '학생명', s_student, new_fb):
                                    show_center_message("✅ 코멘트가 저장되었습니다!")
                                    time.sleep(1); st.rerun()

# ==========================================
# 👤 내 정보 수정 (강사 전용 마이페이지)
# ==========================================
elif menu == "👤 내 정보 수정":
    st.subheader("👤 내 정보 관리")
    
    if st.session_state['role'] == 'teacher':
        st.info("💡 연락처, 주소, 로그인 비밀번호를 직접 수정하실 수 있습니다.")
        df_t = load_data('teachers')
        my_name = st.session_state['username']
        
        if not df_t.empty and my_name in df_t.iloc[:, 0].values:
            # 로그인한 강사의 행 데이터 추출
            my_info = df_t[df_t.iloc[:, 0] == my_name].iloc[0]
            
            with st.container(border=True):
                st.markdown(f"#### 👨‍🏫 {my_name} 선생님 정보")
                col1, col2 = st.columns(2)
                
                with col1:
                    new_phone = st.text_input("📱 연락처 수정", value=str(my_info.get('연락처', '')))
                    new_email = st.text_input("📧 이메일 수정", value=str(my_info.get('이메일', '')))
                
                with col2:
                    # 비밀번호는 보안상 type="password"로 설정
                    new_pw = st.text_input("🔐 비밀번호 변경", value=str(my_info.get('비밀번호', '')), type="password")
                    st.caption("※ 비밀번호를 비우면 전화번호 뒷자리로 로그인됩니다.")

                new_addr = st.text_area("🏠 주소 수정 ", value=str(my_info.get('주소', '')))
                
                if st.button("💾 내 정보 업데이트", type="primary", use_container_width=True):
                    update_data('teachers', '이름', my_name, {
                        '연락처': new_phone,
                        '이메일': new_email,
                        '주소': new_addr,
                        '비밀번호': new_pw
                    })
                    show_center_message("정보가 안전하게 변경되었습니다!")
                    time.sleep(1)
                    st.rerun()
        else:
            st.error("강사 정보를 불러올 수 없습니다. 관리자에게 문의하세요.")
            
    elif st.session_state['role'] == 'admin':
        st.success("👑 원장님(관리자)은 '1. 강사 관리' 메뉴에서 모든 강사의 정보를 제어하실 수 있습니다.")
        st.markdown("원장님의 마스터 비밀번호는 보안상 코드 파일(`main.py`)에서 직접 수정해 주세요.")