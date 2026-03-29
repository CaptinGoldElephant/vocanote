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

# 1. 환경 및 시간설정
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()

def get_today_kst():
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d")

FONT_PATH = "malgun.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun", FONT_PATH))

# --- 2. 구글 시트 연결 및 데이터 로직 ---
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
        # 컬럼 누락 방지
        for col in ["word", "mean", "root", "count", "date"]:
            if col not in df.columns: df[col] = ""
        return worksheet, df
    except Exception as e:
        st.error(f"연결 실패: {e}")
        return None, pd.DataFrame(columns=["word", "mean", "root", "count", "date"])

def select_test_words(df, num):
    df_sorted = df.sort_values(by='count')
    selected_list = []
    used_roots = set()
    
    for _, row in df_sorted.iterrows():
        if len(selected_list) >= num: break
        if row['root'] not in used_roots:
            selected_list.append(row)
            used_roots.add(row['root'])
            
    if len(selected_list) < num:
        current_sel = [w['word'] for w in selected_list]
        remaining = df_sorted[~df_sorted['word'].isin(current_sel)]
        needed = num - len(selected_list)
        for _, row in remaining.head(needed).iterrows():
            selected_list.append(row)
    return selected_list

def generate_pdf(selected_words, title_prefix):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    
    def draw_layout(words, is_ans, p_num):
        c.setFont("Malgun", 16)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(300, 800, f"{title_prefix} {'정답지' if is_ans else '시험지'} (P.{p_num})")
        c.setFont("Malgun", 10)
        
        for i, r in enumerate(words):
            col = i // 25; row_i = i % 25
            x = 70 + (col * 250); y = 740 - (row_i * 27)
            
            num_txt = f"{i+1+(p_num-1)*50}. "
            word_txt = f"{r['word']} : "
            
            c.setFillColorRGB(0, 0, 0)
            c.drawString(x, y, num_txt)
            word_x = x + c.stringWidth(num_txt, "Malgun", 10)
            c.drawString(word_x, y, word_txt)
            
            mean_x = word_x + c.stringWidth(word_txt, "Malgun", 10)
            
            if is_ans:
                c.setFillColorRGB(0.8, 0, 0) 
                m = str(r['mean'])
                if c.stringWidth(m, "Malgun", 10) > 150: c.setFont("Malgun", 8.5)
                c.drawString(mean_x, y, m)
                c.setFont("Malgun", 10)
            else:
                c.setFillColorRGB(0, 0, 0)
                c.drawString(mean_x, y, "____________________")

    for p in range(0, len(selected_words), 50):
        draw_layout(selected_words[p:p+50], False, (p//50)+1); c.showPage()
    for p in range(0, len(selected_words), 50):
        draw_layout(selected_words[p:p+50], True, (p//50)+1); c.showPage()
    c.save()
    return buf

# --- 4. 메인 로직 ---
st.set_page_config(page_title="스마트 토익 단어장", layout="wide")
st.title("📚 실시간 자동 동기화 단어장")

worksheet, df_sheet = sync_data()

if 'df' not in st.session_state or st.sidebar.button("🔄 데이터 새로고침"):
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
                    existing_words = st.session_state.df['word'].astype(str).tolist()
                    if word in existing_words:
                        st.error(f"⚠️ '{word}'는 이미 등록된 단어입니다!")
                    else:
                        root = stemmer.stem(word)
                        today = get_today_kst()
                        worksheet.append_row([word, mean, root, 0, today])
                        st.success(f"✅ '{word}' 저장 완료!")
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
                existing_words = st.session_state.df['word'].astype(str).tolist()
                new_rows = []
                for _, row in user_csv.iterrows():
                    w = str(row.iloc[0]).strip().lower()
                    m = str(row.iloc[1]).strip()
                    if w not in existing_words:
                        r = stemmer.stem(w)
                        new_rows.append([w, m, r, 0, today])
                        existing_words.append(w)
                
                if new_rows:
                    worksheet.append_rows(new_rows)
                    st.success(f"✅ {len(new_rows)}개 저장 완료!")
                    time.sleep(1); st.rerun()
                else: st.warning("추가할 단어가 없습니다.")
            except Exception as e: st.error(f"오류: {e}")

elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    st.info("💡 위 표에서 수정하거나 삭제할 단어의 '선택' 칸을 체크해 주세요.")
    curr_df = st.session_state.df
    if not curr_df.empty:
        search = st.text_input("🔍 검색 (영어)").strip().lower()
        f_df = curr_df[curr_df['word'].str.contains(search, na=False, case=False)].sort_values("word")
        
        d_df = f_df.copy(); d_df.insert(0, "선택", False)
        edited = st.data_editor(d_df, hide_index=True, use_container_width=True, key="v_editor")
        s_rows = edited[edited["선택"] == True]
        
        if not s_rows.empty:
            sel_w = s_rows.iloc[-1]["word"]
            try:
                cell = worksheet.find(sel_w)
                row_idx = cell.row
                st.divider(); st.subheader("⚙️ 단어 수정 및 삭제")
                c1, c2, c3 = st.columns(3)
                with c1: n_w = st.text_input("영어 수정", value=sel_w)
                with c2: n_m = st.text_input("한글 수정", value=curr_df.loc[curr_df['word']==sel_w, 'mean'].values[0])
                with c3: n_r = st.text_input("어근 수정", value=curr_df.loc[curr_df['word']==sel_w, 'root'].values[0])
                
                b_col1, b_col2, b_col3 = st.columns([1, 4, 1])
                with b_col1:
                    if st.button("💾 시트에 반영"):
                        worksheet.update_cell(row_idx, 1, n_w.strip().lower())
                        worksheet.update_cell(row_idx, 2, n_m.strip())
                        worksheet.update_cell(row_idx, 3, n_r.strip())
                        st.success("수정 완료!"); time.sleep(0.5); st.rerun()
                with b_col3:
                    if st.button("🗑️ 시트에서 삭제"):
                        worksheet.delete_rows(row_idx)
                        st.warning("삭제 완료!"); time.sleep(0.5); st.rerun()
            except: st.error("데이터 동기화가 필요합니다. 새로고침을 눌러주세요.")
    else: st.info("데이터가 없습니다.")

elif menu == "날짜별 단어 조회":
    st.header("📅 날짜별 등록 현황")
    if not st.session_state.df.empty:
        target = st.selectbox("날짜 선택", sorted(st.session_state.df['date'].unique(), reverse=True))
        date_df = st.session_state.df[st.session_state.df['date'] == target].sort_values("word")
        if st.button(f"📄 {target} 시험지 생성"):
            pdf_buf = generate_pdf(date_df.to_dict('records'), target)
            st.download_button(f"📥 {target} PDF 다운로드", pdf_buf.getvalue(), f"voca_{target}.pdf")
        st.table(date_df[['word', 'mean']])

elif menu == "시험지 만들기":
    st.header("🖨️ 랜덤 시험지 생성")
    curr_df = st.session_state.df
    if len(curr_df) < 5: st.error("단어가 부족합니다.")
    else:
        num = st.number_input("문제 수", 5, len(curr_df), 20)
        if st.button("시험지 생성 및 카운트 업데이트"):
            selected = select_test_words(curr_df, num)
            pdf_buf = generate_pdf(selected, "랜덤")
            with st.spinner("카운트 업데이트 중..."):
                for item in selected:
                    cell = worksheet.find(item['word'])
                    curr_val = int(worksheet.cell(cell.row, 4).value or 0)
                    worksheet.update_cell(cell.row, 4, curr_val + 1)
            st.success("✅ 카운트 반영 완료!")
            st.download_button("📥 PDF 다운로드", pdf_buf.getvalue(), "voca_test.pdf")
