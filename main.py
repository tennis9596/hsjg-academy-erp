import streamlit as st
from streamlit_option_menu import option_menu
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

# ==========================================
# [기본 설정] 페이지 및 스타일
# ==========================================
st.set_page_config(page_title="형설지공 학원 ERP", page_icon="🏫", layout="wide")

st.markdown("""
<style>
    /* 1. 인쇄 모드 설정 */
    @media print {
        [data-testid="stSidebar"], header, footer, .stButton, .no-print { display: none !important; }
        .block-container { padding: 0 !important; max-width: 100% !important; }
    }

    /* 2. 카드형 시간표 스타일 */
    .class-card {
        background-color: #E3F2FD; border-left: 5px solid #1565C0; border-radius: 8px;
        padding: 8px; margin-bottom: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        min-height: 100px; display: flex; flex-direction: column; justify-content: center;
    }
    .cc-subject { font-size: 0.8rem; color: #555; font-weight: bold; }
    .cc-name { font-size: 1.05rem; color: #000; font-weight: 800; margin-bottom: 3px; }
    .cc-info { font-size: 0.85rem; color: #333; }
    .cc-time { font-size: 0.9rem; color: #1565C0; font-weight: 700; margin-top: 3px; }
    .cc-duration { font-size: 0.8rem; color: #E65100; font-weight: 600; }
    
    .empty-card { background-color: #FAFAFA; border: 2px dashed #E0E0E0; border-radius: 8px; min-height: 100px; }
    
    .time-axis-card {
        background-color: #263238; color: white; border-radius: 8px;
        min-height: 100px; display: flex; flex-direction: column; align-items: center; justify-content: center;
        padding: 5px; margin-bottom: 5px;
    }
    .tac-start { font-size: 1.1rem; font-weight: 800; color: #FFD54F; }
    .tac-tilde { font-size: 0.8rem; margin: 2px 0; color: #aaa; }
    .tac-end { font-size: 1.0rem; font-weight: 600; color: #fff; }

    .day-header { text-align: center; font-weight: 800; background-color: #f1f3f5; padding: 10px 0; border-radius: 5px; margin-bottom: 10px; }
    
    /* 3. 달력 스타일 */
    .cal-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    .cal-th { background-color: #eee; padding: 5px; text-align: center; font-weight: bold; border: 1px solid #ddd; }
    .cal-td { height: 80px; vertical-align: top; border: 1px solid #ddd; padding: 5px; font-size: 0.9rem; position: relative; }
    .cal-day-num { font-weight: bold; margin-bottom: 3px; display: block; color: #333; }
    .cal-badge { display: block; padding: 4px; border-radius: 4px; font-size: 0.8rem; margin-bottom: 2px; color: white; text-align: center; font-weight: bold; }
    .bg-green { background-color: #4CAF50; } 
    .bg-red { background-color: #F44336; }    
    .bg-gray { background-color: #9E9E9E; }   
    .bg-blue { background-color: #2196F3; }

    /* 4. 알림 메시지 */
    .custom-alert { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background-color: rgba(46, 125, 50, 0.95); color: white; padding: 25px 50px; border-radius: 15px; font-size: 22px; font-weight: bold; z-index: 99999; animation: fadeInOut 2s forwards; border: 2px solid #fff; }
    @keyframes fadeInOut { 0% { opacity: 0; transform: translate(-50%, -40%); } 15% { opacity: 1; transform: translate(-50%, -50%); } 85% { opacity: 1; transform: translate(-50%, -50%); } 100% { opacity: 0; transform: translate(-50%, -60%); } }
    
    /* 5. 요일 뱃지 */
    .day-badge-single { padding: 8px 0; border-radius: 8px; color: #444; font-weight: 800; text-align: center; display: block; width: 100%; border: 1px solid rgba(0,0,0,0.05); font-size: 0.9rem; }
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
        # 1. Streamlit Secrets에서 데이터 가져오기
        if "gcp_json" in st.secrets:
            if isinstance(st.secrets["gcp_json"], str):
                key_dict = json.loads(st.secrets["gcp_json"])
            else:
                key_dict = dict(st.secrets["gcp_json"])
        elif "gcp_service_account" in st.secrets:
            key_dict = dict(st.secrets["gcp_service_account"])
        else:
            raise Exception("Secrets 설정을 찾을 수 없습니다.")

        # [핵심] 비밀키 재조립 (안전한 방식)
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
        # 1. 파일 열기 시도
        doc = client.open("Academy_DB")
        # 2. 탭(워크시트) 열기 시도
        sheet = safe_api_call(doc.worksheet, sheet_name)
        # 3. 데이터 가져오기
        data = safe_api_call(sheet.get_all_records)
        return pd.DataFrame(data)
    except Exception as e:
        # 에러가 나면 화면에 빨간 글씨로 띄워줌!
        st.error(f"🚨 데이터 로드 실패 ({sheet_name}): {e}")
        return pd.DataFrame()

def clear_cache(): st.cache_data.clear()

def show_center_message(message, icon="✅"):
    placeholder = st.empty()
    placeholder.markdown(f'<div class="custom-alert"><span>{icon}</span> {message}</div>', unsafe_allow_html=True)
    time.sleep(1.2); placeholder.empty()

def add_data(sheet_name, data_dict):
    try:
        client = init_connection()
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
        ws = safe_api_call(client.open("Academy_DB").worksheet, sheet_name)
        data = safe_api_call(ws.get_all_records)
        df = pd.DataFrame(data)
        
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

# --- 유틸리티 ---
def calc_duration_min(s, e):
    try:
        t1 = datetime.strptime(s, "%H:%M")
        t2 = datetime.strptime(e, "%H:%M")
        return (t2 - t1).seconds // 60
    except: return 0

def sort_time_strings(time_list):
    try: return sorted(list(set(time_list)), key=lambda x: datetime.strptime(x, "%H:%M"))
    except: return sorted(list(set(time_list)))

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
# [메뉴] 사이드바 구성 (순서 재배치)
# ==========================================
with st.sidebar:
    st.title("🏫 형설지공 학원")
    st.markdown("# 🎓 통합 ERP 시스템")
    st.markdown("---")
    
    menu = option_menu("메뉴 선택", 
        [
            "1. 강사 관리", 
            "2. 학생 관리", 
            "3. 반 관리", 
            "4. 수강 배정", 
            "5. QR 키오스크(출석)", 
            "6. 출석 관리", 
            "7. 강사별 시간표", 
            "8. 강의실별 시간표", 
            "9. 학생 개인별 종합"
        ], 
        icons=[
            'person-video3',    # 1. 강사
            'backpack',         # 2. 학생
            'easel',            # 3. 반
            'journal-check',    # 4. 수강
            'qr-code-scan',     # 5. QR 키오스크
            'calendar-check',   # 6. 출석 체크
            'clock',            # 7. 강사 시간표
            'building',         # 8. 강의실 시간표
            'card-checklist'    # 9. 학생 종합
        ],
        menu_icon="cast", default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#f0f2f6"},
            "icon": {"color": "orange", "font-size": "18px"}, 
            "nav-link": {
                "font-size": "15px", 
                "text-align": "left", 
                "margin":"0px", 
                "white-space": "nowrap", 
                "--hover-color": "#eee"
            },
            "nav-link-selected": {"background-color": "#02ab21"},
        }
    )
    st.markdown("---")
    st.caption("Developed by 형설지공 2026")

# ==========================================================
# 1. 강사 관리
# ==========================================================
if menu == "1. 강사 관리":
    st.subheader("👨‍🏫 강사 관리")
    tab1, tab2 = st.tabs(["➕ 신규 등록", "🔧 수정 및 삭제"])
    
    # [Tab 1] 신규 등록
    with tab1:
        with st.form("teacher_create_form", clear_on_submit=True):
            name = st.text_input("이름")
            subject = st.text_input("담당 과목")
            phone = st.text_input("연락처 (010-0000-0000)")
            email = st.text_input("이메일 (알림 수신용)")
            
            if st.form_submit_button("등록하기"):
                if not name:
                    st.error("이름을 입력하세요.")
                else:
                    add_data('teachers', {
                        '이름': name, 
                        '과목': subject, 
                        '연락처': phone, 
                        '이메일': email
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

                n_name = st.text_input("이름", value=prev_name, key="edit_t_n")
                n_sub = st.text_input("과목", value=prev_sub, key="edit_t_s")
                n_ph = st.text_input("연락처", value=prev_ph, key="edit_t_p")
                n_email = st.text_input("이메일", value=prev_email, key="edit_t_e")
                
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
                            '이메일': n_email
                        })
                        st.session_state['confirm_action'] = None
                        st.session_state['t_modify_idx'] = 0
                        show_center_message("수정 완료!")
                        for key in ["edit_t_n", "edit_t_s", "edit_t_p", "edit_t_e"]:
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
# 2. 학생 관리
# ==========================================
elif menu == "2. 학생 관리":
    st.subheader("📝 학생 관리")
    t1, t2, t3, t4 = st.tabs(["📋 전체 학생 조회", "➕ 신규 등록", "🔧 수정/삭제", "📱 QR 발급/인쇄"])
    
    df_c, df_t, df_s = load_data('classes'), load_data('teachers'), load_data('students')
    all_subjects = sorted(get_col_data(df_t, '과목', 1).unique().tolist()) if not df_t.empty else []

    with t1:
        st.dataframe(df_s, use_container_width=True)

    with t2:
        if df_c.empty: st.warning("⚠️ 개설된 반이 없습니다. (반 관리 메뉴에서 먼저 반을 만들어주세요)")
        st.markdown("##### 1️⃣ 기본 정보 입력")
        c1, c2 = st.columns(2)
        name = c1.text_input("이름", key="create_name")
        phone = c1.text_input("학생 폰", key="create_phone")
        p_phone = c1.text_input("부모님 폰", key="create_p_phone")
        grade = c2.selectbox("학년", ["초4","초5","초6","중1","중2","중3","고1","고2","고3"], key="create_grade")
        school = c2.text_input("학교", key="create_school")
        
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
                nd = {'이름': name, '연락처': phone, '학부모연락처': p_phone, '학년': grade, '학교': school}
                add_data('students', nd)
                if final_enroll_list: add_data_bulk('enrollments', final_enroll_list)
                show_center_message(f"✅ {name} 등록 완료!")
                
                # 입력창 초기화
                keys_to_clear = ["create_name", "create_phone", "create_p_phone", "create_grade", "create_school"]
                for subj in all_subjects:
                    keys_to_clear.append(f"new_chk_{subj}")
                    keys_to_clear.append(f"new_tea_{subj}")
                    keys_to_clear.append(f"new_cls_{subj}")
                for key in keys_to_clear:
                    if key in st.session_state: del st.session_state[key]
                time.sleep(1.5); st.rerun()

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
                st.markdown(f"##### 🔧 '{real_n}' 학생 정보 수정")
                sc1, sc2 = st.columns(2)
                u_nm = sc1.text_input("이름", value=row.iloc[0], key=f"u_sn_{real_n}")
                u_hp = sc1.text_input("학생 폰", value=row.iloc[1], key=f"u_sp_{real_n}")
                u_pp = sc1.text_input("부모 폰", value=row.iloc[2], key=f"u_spp_{real_n}")
                grs = ["초4","초5","초6","중1","중2","중3","고1","고2","고3"]
                cur_g = row.iloc[3]
                u_gr = sc2.selectbox("학년", grs, index=grs.index(cur_g) if cur_g in grs else 0, key=f"u_sg_{real_n}")
                u_sc = sc2.text_input("학교", value=row.iloc[4], key=f"u_ssc_{real_n}")

                bc1, bc2 = st.columns(2)
                if bc1.button("💾 수정 내용 저장"):
                    st.session_state['confirm_action'] = 'update_student'
                
                if st.session_state.get('confirm_action') == 'update_student':
                    st.warning(f"⚠️ '{real_n}' 학생의 정보를 수정하시겠습니까?")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 수정합니다", type="primary"):
                        nd = {'이름': u_nm, '연락처': u_hp, '학부모연락처': u_pp, '학년': u_gr, '학교': u_sc}
                        update_data('students', '이름', real_n, nd)
                        st.session_state['confirm_action'] = None
                        show_center_message("수정 완료!")
                        if 's_search_edit' in st.session_state: del st.session_state['s_search_edit']
                        time.sleep(1); st.rerun()
                    if col_n.button("취소"):
                        st.session_state['confirm_action'] = None
                        st.rerun()

                if bc2.button("🗑️ 학생 삭제 (복구 불가)", type="primary"):
                    st.session_state['confirm_action'] = 'delete_student'

                if st.session_state.get('confirm_action') == 'delete_student':
                    st.error(f"⚠️ 경고: '{real_n}' 학생을 삭제하면 수강 기록까지 모두 사라집니다.")
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
    hours = [f"{i}시" for i in range(9, 23)]
    mins = ["00분", "10분", "20분", "30분", "40분", "50분"]
    rooms = ["기타", "101호", "102호", "103호", "104호"]

    with tab1:
        df_t = load_data('teachers')
        if df_t.empty: st.warning("선생님을 먼저 등록해주세요.")
        else:
            t_opts = (get_col_data(df_t, '이름', 0) + " (" + get_col_data(df_t, '과목', 1) + ")").tolist()
            c1, c2, c3 = st.columns([2, 1, 2])
            c_name = c1.text_input("반 이름", key="new_c_name")
            c_room = c2.selectbox("강의실", rooms, key="new_c_room")
            t_name = c3.selectbox("담당 선생님", t_opts, key="new_t_name")
            
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
                else:
                    final_sche = [f"{d} {t}" for d, t in schedule_data.items()]
                    add_data('classes', {'반이름': c_name, '선생님': t_name, '시간': ", ".join(final_sche), '강의실': c_room})
                    show_center_message(f"'{c_name}' 개설 완료!")
                    time.sleep(1); st.rerun()

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
                curr_sche_map = {}
                for p in curr_schedule_str.split(','):
                    kp = p.strip().split()
                    if len(kp)==2: curr_sche_map[kp[0]] = kp[1]

                st.divider()
                st.markdown(f"#### 🔧 '{sel_c_name}' 정보 수정")
                uc1, uc2, uc3 = st.columns([2, 1, 2])
                u_c_name = uc1.text_input("반 이름", value=sel_c_name, key=f"edit_n_{sel_c_name}")
                u_room = uc2.selectbox("강의실", rooms, index=rooms.index(curr_room), key=f"edit_r_{sel_c_name}")
                t_idx = t_opts.index(curr_teacher) if curr_teacher in t_opts else 0
                u_t_name = uc3.selectbox("담당 선생님", t_opts, index=t_idx, key=f"edit_t_{sel_c_name}")
                
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
                    st.session_state['confirm_action'] = 'update_class'
                
                if st.session_state.get('confirm_action') == 'update_class':
                    st.warning(f"⚠️ '{sel_c_name}' 반 정보를 수정하시겠습니까?")
                    col_y, col_n = st.columns([1,1])
                    if col_y.button("네, 수정합니다", type="primary"):
                        nd = {'반이름': u_c_name, '선생님': u_t_name, '시간': ", ".join(u_updated_sche), '강의실': u_room}
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
# 4. 수강 배정
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

    tab1, tab2 = st.tabs(["📋 전체 수강 현황", "➕ 수강 신청 (장바구니)"])

    with tab1:
        if df_e.empty: st.info("현재 배정된 수강 내역이 없습니다.")
        else: st.dataframe(df_e[['학생', '과목', '반이름', '담당강사', '날짜']], use_container_width=True)

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
                                                    already = df_e[(df_e.iloc[:,0]==real_name) & (df_e.iloc[:,1]==sel_subj) & (df_e.iloc[:,2]==real_cls_name)]
                                                    if not already.empty: is_exist = True
                                                except: pass
                                            if is_exist: st.warning("이미 담겼거나 수강 중인 수업입니다.")
                                            else:
                                                st.session_state.draft_enrolls.append({
                                                    '학생': real_name, '과목': sel_subj, '반이름': real_cls_name,
                                                    '담당강사': sel_tea, '날짜': str(datetime.today().date())
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
                            curr_list = df_e[df_e.iloc[:,0] == real_name_curr]
                            if not curr_list.empty:
                                for idx, row in curr_list.iterrows():
                                    subj_val, cls_val, tea_val = row.iloc[1], row.iloc[2], row.iloc[3]
                                    unique_key = f"{real_name_curr}_{cls_val}_{subj_val}"
                                    c1, c2 = st.columns([4, 1])
                                    c1.markdown(f"• :blue[[{subj_val}]] {cls_val} (담당: {tea_val})")
                                    if st.session_state.confirm_cancel_target != unique_key:
                                        if c2.button("취소", key=f"btn_cancel_{unique_key}"):
                                            st.session_state.confirm_cancel_target = unique_key
                                            st.rerun()
                                    else:
                                        with c2:
                                            st.markdown("**:red[삭제?]**")
                                            y_col, n_col = st.columns(2)
                                            if y_col.button("네", key=f"yes_{unique_key}"):
                                                delete_data_all('enrollments', {'학생': real_name_curr, '반이름': cls_val})
                                                st.session_state.confirm_cancel_target = None
                                                show_center_message("수강 취소 완료!")
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
                    now = datetime.now(); today_weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]; current_time_str = now.strftime("%H:%M")
                    my_classes = df_e[df_e.iloc[:,0] == s_name]; found_class_today = False
                    if not my_classes.empty:
                        for _, row in my_classes.iterrows():
                            c_name = row.iloc[1]; c_info = df_c[df_c.iloc[:,0] == c_name]
                            if not c_info.empty:
                                schedule_str = str(c_info.iloc[0, 2])
                                if today_weekday in schedule_str:
                                    for part in schedule_str.split(','):
                                        if part.strip().startswith(today_weekday):
                                            t_range = part.strip().split()[1]; start_time_str = t_range.split('-')[0]
                                            s_time = datetime.strptime(start_time_str, "%H:%M"); s_time = now.replace(hour=s_time.hour, minute=s_time.minute, second=0)
                                            status = "출석"; msg = f"{s_name} 학생, 환영합니다! (수업: {c_name})"; limit_time = s_time + timedelta(minutes=10)
                                            if now > limit_time: status = "지각"; msg = f"🚨 {s_name} 학생, 지각입니다! (수업: {c_name})"
                                            elif now < (s_time - timedelta(minutes=60)): status = "보강/자습"; msg = f"{s_name} 학생, 일찍 왔네요! 자습하세요."
                                            add_data('attendance', {'날짜': str(now.date()), '반이름': c_name, '학생': s_name, '상태': status, '비고': f"QR체크({current_time_str})"})
                                            if status == "지각": st.error(msg)
                                            else: st.success(msg)
                                            found_class_today = True; break
                    if not found_class_today:
                        st.info(f"{s_name} 학생, 오늘은 정규 수업이 없습니다."); 
                        if st.button("보강 출석 확인"): add_data('attendance', {'날짜': str(now.date()), '반이름': "보강/자습", '학생': s_name, '상태': "보강", '비고': f"QR체크({current_time_str})"}); st.success("보강 출석 처리되었습니다.")
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
                                                found_list.append({
                                                    'sub': t_subs.iloc[idx], 'name': row.iloc[0], 
                                                    'room': row.iloc[3], 'time': tp.split()[1], 
                                                    'dur': calc_duration_min(s, e)
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
                                            st.markdown(f"""<div class='class-card'><div class='cc-subject'>{found['sub']}</div><div class='cc-name'>{found['name']}</div><div class='cc-info'>🏫 {found['room']}</div><div class='cc-time'>⏰ {found['time']}</div><div class='cc-duration'>⏳ {found['dur']}분</div></div>""", unsafe_allow_html=True)
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
                                curr_r = str(r_data.iloc[3])
                                if curr_r not in rooms: curr_r = "기타"
                                if curr_r == r:
                                    try:
                                        s, e = t_str.split('-')
                                        if s == start_t:
                                            full_tea = str(r_data.iloc[1])
                                            tn = full_tea.split('(')[0] if "(" in full_tea else full_tea
                                            sub = full_tea.split('(')[1].replace(')', '') if "(" in full_tea else "과목"
                                            found_list.append({'sub': sub, 'name': r_data.iloc[0], 'tea': tn, 'time': t_str, 'dur': calc_duration_min(s, e)})
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
                                            st.markdown(f"""<div class='class-card' style='border-left-color:#43A047;background-color:#E8F5E9;'><div class='cc-subject'>{found['sub']}</div><div class='cc-name'>{found['name']}</div><div class='cc-info'>👨‍🏫 {found['tea']}</div><div class='cc-time'>⏰ {found['time']}</div><div class='cc-duration'>⏳ {found['dur']}분</div></div>""", unsafe_allow_html=True)
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