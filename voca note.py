import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import random
import os
import time
import nltk
import io
import json
from datetime import datetime, timedelta, timezone
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from nltk.stem import PorterStemmer

# --- 1. 환경 준비 ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()

# [수정] 한국 시간(KST)을 아주 정확하게 가져오는 함수
def get_today_kst():
    # UTC+9 시간을 강제로 설정합니다.
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d")

FONT_PATH = "malgun.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun", FONT_PATH))

# --- 2. 구글 시트 연결 ---
def get_gspread_client():
    key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def sync_data():
    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        worksheet = sh.get_worksheet(0)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        return worksheet, df
    except Exception as e:
        st.error(f"연결 실패: {e}")
        return None, pd.DataFrame(columns=["word", "mean", "root", "count", "date"])

# --- 3. 메인 로직 ---
st.set_page_config(page_title="스마트 토익 단어장", layout="wide")
st.title("📚 실시간 자동 동기화 단어장")

worksheet, df_sheet = sync_data()

# 세션 상태에 최신 데이터 유지
if 'df' not in st.session_state or st.sidebar.button("🔄 새로고침"):
    st.session_state.df = df_sheet

menu = st.sidebar.selectbox("메뉴 선택", ["단어 등록하기", "단어 목록 보기", "날짜별 단어 조회", "시험지 만들기"])

if menu == "단어 등록하기":
    st.header("📝 새 단어 등록")
    tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])
    
    with tab1:
        with st.form("single_add", clear_on_submit=True):
            word = st.text_input("영어 단어").strip().lower()
            mean = st.text_input("한글 뜻").strip()
            if st.form_submit_button("시트에 저장"):
                if word and mean:
                    # [수정] 중복 체크 로직 추가
                    existing_words = st.session_state.df['word'].tolist()
                    if word in existing_words:
                        st.error(f"⚠️ '{word}'는 이미 등록된 단어입니다!")
                    else:
                        root = stemmer.stem(word)
                        # [수정] 한국 날짜 강제 적용
                        today = get_today_kst()
                        worksheet.append_row([word, mean, root, 0, today])
                        st.success(f"✅ '{word}' 저장 완료! (날짜: {today})")
                        time.sleep(1)
                        st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("CSV 선택", type=["csv"])
        if uploaded_file and st.button("🚀 구글 시트로 일괄 전송"):
            try:
                try: user_csv = pd.read_csv(uploaded_file)
                except:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                
                today = get_today_kst()
                existing_words = st.session_state.df['word'].tolist()
                new_rows = []
                
                for _, row in user_csv.iterrows():
                    w = str(row.iloc[0]).strip().lower() # 첫번째 열 기준
                    m = str(row.iloc[1]).strip()         # 두번째 열 기준
                    if w not in existing_words:
                        r = stemmer.stem(w)
                        new_rows.append([w, m, r, 0, today])
                        existing_words.append(w) # 루프 내 중복 방지
                
                if new_rows:
                    worksheet.append_rows(new_rows)
                    st.success(f"✅ {len(new_rows)}개의 새 단어가 저장되었습니다!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("추가할 새로운 단어가 없습니다.")
            except Exception as e:
                st.error(f"오류: {e}")

# --- 메뉴 2: 단어 목록 보기 (수정/삭제/안내문구/스펠링수정 포함) ---
elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    st.info("💡 위 표에서 수정하거나 삭제할 단어의 '선택' 칸을 체크해 주세요.")
    
    curr_df = st.session_state.df
    if not curr_df.empty:
        search = st.text_input("🔍 검색 (영어)").strip().lower()
        f_df = curr_df[curr_df['word'].str.contains(search, na=False)].sort_values("word")
        
        d_df = f_df.copy(); d_df.insert(0, "선택", False)
        edited = st.data_editor(d_df, hide_index=True, use_container_width=True, key="v_editor")
        s_rows = edited[edited["선택"] == True]
        
        if not s_rows.empty:
            sel_w = s_rows.iloc[-1]["word"]
            # 시트에서 해당 단어 행 찾기
            try:
                cell = worksheet.find(sel_w)
                row_idx = cell.row
                
                st.divider(); st.subheader("⚙️ 단어 수정 및 삭제")
                c1, c2, c3 = st.columns(3)
                with c1: n_w = st.text_input("영어 수정", value=curr_df.loc[curr_df['word']==sel_w, 'word'].values[0])
                with c2: n_m = st.text_input("한글 수정", value=curr_df.loc[curr_df['word']==sel_w, 'mean'].values[0])
                with c3: n_r = st.text_input("어근 수정", value=curr_df.loc[curr_df['word']==sel_w, 'root'].values[0])
                
                b_col1, b_col2, b_col3 = st.columns([1, 4, 1])
                with b_col1:
                    if st.button("💾 시트에 반영"):
                        worksheet.update(f"A{row_idx}:C{row_idx}", [[n_w.strip().lower(), n_m.strip(), n_r.strip()]])
                        st.success("수정 완료!"); time.sleep(0.5); st.rerun()
                with b_col3:
                    if st.button("🗑️ 시트에서 삭제"):
                        worksheet.delete_rows(row_idx)
                        st.warning("삭제 완료!"); time.sleep(0.5); st.rerun()
            except: st.error("새로고침을 눌러주세요.")
    else: st.info("데이터가 없습니다.")

# --- 메뉴 3: 날짜별 단어 조회 (PDF 생성 기능 복구) ---
elif menu == "날짜별 단어 조회":
    st.header("📅 날짜별 등록 현황")
    curr_df = st.session_state.df
    if not curr_df.empty:
        all_dates = sorted(curr_df['date'].unique(), reverse=True)
        target = st.selectbox("조회할 날짜를 선택하세요", all_dates)
        
        date_df = curr_df[curr_df['date'] == target].sort_values("word")
        st.subheader(f"📍 {target} 등록 단어 ({len(date_df)}개)")
        
        # 해당 날짜 시험지 만들기 버튼
        if st.button(f"📄 {target} 단어 시험지(PDF) 생성"):
            if len(date_df) > 0:
                sel_words = date_df.to_dict('records')
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=A4)
                
                # 사용자님 고유 50개 2열 레이아웃 함수
                def draw_layout(words, is_ans, p_num):
                    c.setFont("Malgun", 16)
                    c.drawCentredString(300, 800, f"{target} 영단어 {'정답지' if is_ans else '시험지'} (P.{p_num})")
                    c.setFont("Malgun", 10)
                    for i, r in enumerate(words):
                        col = i // 25; row_i = i % 25
                        x = 70 + (col * 250); y = 740 - (row_i * 27)
                        txt = f"{i+1+(p_num-1)*50}. {r['word']}"
                        c.drawString(x, y, txt)
                        w_w = c.stringWidth(txt, "Malgun", 10) + 10
                        if is_ans:
                            c.setFillColorRGB(0.8, 0, 0)
                            m = str(r['mean'])
                            if c.stringWidth(m, "Malgun", 10) > 230: c.setFont("Malgun", 8.5)
                            c.drawString(x + w_w, y, m); c.setFont("Malgun", 10)
                        else:
                            c.drawString(x + w_w, y, "____________________")

                # PDF 페이지 생성
                for p in range(0, len(sel_words), 50):
                    draw_layout(sel_words[p:p+50], False, (p//50)+1); c.showPage()
                for p in range(0, len(sel_words), 50):
                    draw_layout(sel_words[p:p+50], True, (p//50)+1); c.showPage()
                c.save()
                st.download_button(f"📥 {target} PDF 다운로드", buf.getvalue(), f"voca_{target}.pdf")
            else:
                st.warning("해당 날짜에 단어가 없습니다.")
        
        st.divider()
        st.table(date_df[['word', 'mean']])
    else:
        st.info("저장된 단어가 없습니다.")

# --- 메뉴 4: 시험지 만들기 (사용자님 50개 2열 디자인 완벽 보존) ---
elif menu == "시험지 만들기":
    st.header("🖨️ PDF 시험지 생성")
    curr_df = st.session_state.df
    if len(curr_df) < 5: st.error("단어가 부족합니다.")
    else:
        num = st.number_input("문제 수", 5, len(curr_df), min(20, len(curr_df)))
        if st.button("PDF 생성"):
            sel_list = curr_df.sample(n=num).to_dict('records')
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            def draw_layout(words, is_ans, p_num):
                c.setFont("Malgun", 16)
                c.drawCentredString(300, 800, f"영단어 {'정답지' if is_ans else '시험지'} (Page {p_num})")
                c.setFont("Malgun", 10)
                for i, r in enumerate(words):
                    col = i // 25; row_i = i % 25
                    x = 70 + (col * 250); y = 740 - (row_i * 27)
                    txt = f"{i+1+(p_num-1)*50}. {r['word']}"
                    c.drawString(x, y, txt)
                    w_w = c.stringWidth(txt, "Malgun", 10) + 10
                    if is_ans:
                        m = str(r['mean'])
                        if c.stringWidth(m, "Malgun", 10) > 230: c.setFont("Malgun", 8.5)
                        c.drawString(x + w_w, y, m); c.setFont("Malgun", 10)
                    else: c.drawString(x + w_w, y, "____________________")
            
            for p in range(0, len(sel_list), 50):
                draw_layout(sel_list[p:p+50], False, (p//50)+1); c.showPage()
            for p in range(0, len(sel_list), 50):
                draw_layout(sel_list[p:p+50], True, (p//50)+1); c.showPage()
            c.save()
            st.download_button("📥 다운로드", buf.getvalue(), "voca.pdf")
