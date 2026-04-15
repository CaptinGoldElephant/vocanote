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
        for col in ["word", "mean", "root", "count", "wrong_count", "date"]:
            if col not in df.columns: 
                df[col] = 0 if col in ["count", "wrong_count"] else ""
        return worksheet, df
    except Exception as e:
        st.error(f"연결 실패: {e}")
        return None, pd.DataFrame(columns=["word", "mean", "root", "count", "wrong_count", "date"])

def select_test_words(df, num):
    # 가중치 계산: 오답 횟수는 높이고, 노출 횟수는 낮춰서 취약 단어 우선 추출
    df['score'] = (df['wrong_count'].astype(int) * 2) - (df['count'].astype(int) * 0.5)
    df_sorted = df.sort_values(by='score', ascending=False)
    
    selected_list = []
    used_roots = set()
    
    for _, row in df_sorted.iterrows():
        if len(selected_list) >= num: break
        if str(row['root']) not in used_roots:
            selected_list.append(row)
            used_roots.add(str(row['root']))
            
    if len(selected_list) < num:
        current_sel = [w['word'] for w in selected_list]
        remaining = df_sorted[~df_sorted['word'].isin(current_sel)]
        needed = num - len(selected_list)
        for _, row in remaining.head(needed).iterrows():
            selected_list.append(row)
    return selected_list

def generate_pdf(selected_words, title_prefix, test_id):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    
    def draw_layout(words, is_ans, p_num):
        c.setFont("Malgun", 16)
        c.drawCentredString(300, 800, f"{title_prefix} {'정답지' if is_ans else '시험지'} (P.{p_num})")
        c.setFont("Malgun", 8)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(500, 20, f"ID: {test_id}")
        
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
                c.drawString(mean_x, y, str(r['mean']))
            else:
                c.drawString(mean_x, y, "____________________")

    for p in range(0, len(selected_words), 50):
        draw_layout(selected_words[p:p+50], False, (p//50)+1); c.showPage()
    for p in range(0, len(selected_words), 50):
        draw_layout(selected_words[p:p+50], True, (p//50)+1); c.showPage()
    c.save()
    return buf

def save_test_history(selected_words, test_id):
    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test") 
        words_str = ",".join([w['word'] for w in selected_words])
        now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
        history_ws.insert_row([test_id, now_str, words_str], 2)
    except Exception as e:
        st.error(f"히스토리 저장 실패: {e}")

# --- 4. 메인 로직 ---
st.set_page_config(page_title="스마트 토익 단어장", layout="wide")
st.title("📚 실시간 자동 동기화 단어장")

if 'worksheet' not in st.session_state or 'df' not in st.session_state or st.sidebar.button("🔄 데이터 새로고침"):
    ws, df = sync_data()
    st.session_state.worksheet = ws
    st.session_state.df = df

worksheet = st.session_state.worksheet
df_main = st.session_state.df

menu = st.sidebar.selectbox("메뉴 선택", ["단어 등록하기", "단어 목록 보기", "날짜별 단어 조회", "시험지 만들기", "오답 체크하기", "지옥의 오답 노트"])

if menu == "단어 등록하기":
    st.header("📝 새 단어 등록")
    tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])
    with tab1:
        with st.form("single_add", clear_on_submit=True):
            word = st.text_input("영어 단어").strip().lower()
            mean = st.text_input("한글 뜻").strip()
            if st.form_submit_button("시트에 저장"):
                if word and mean:
                    if word in df_main['word'].astype(str).tolist():
                        st.error(f"⚠️ '{word}'는 이미 등록된 단어입니다!")
                    else:
                        root = stemmer.stem(word)
                        today = get_today_kst()
                        worksheet.append_row([word, mean, root, 0, 0, today])
                        st.success(f"✅ '{word}' 저장 완료!")
                        time.sleep(1); st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("CSV 선택", type=["csv"])
        if uploaded_file and st.button("🚀 구글 시트로 일괄 전송"):
            try:
                try: user_csv = pd.read_csv(uploaded_file)
                except:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                today = get_today_kst()
                exist = df_main['word'].astype(str).tolist()
                new_rows = []
                for _, row in user_csv.iterrows():
                    w = str(row.iloc[0]).strip().lower()
                    m = str(row.iloc[1]).strip()
                    if w not in exist:
                        r = stemmer.stem(w); new_rows.append([w, m, r, 0, 0, today]); exist.append(w)
                if new_rows:
                    worksheet.append_rows(new_rows)
                    st.success(f"✅ {len(new_rows)}개 저장 완료!"); time.sleep(1); st.rerun()
                else: st.warning("추가할 단어가 없습니다.")
            except Exception as e: st.error(f"오류: {e}")

elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    if not df_main.empty:
        search = st.text_input("🔍 검색 (영어)").strip().lower()
        f_df = df_main[df_main['word'].astype(str).str.contains(search, na=False, case=False)].sort_values("word")
        d_df = f_df.copy(); d_df.insert(0, "선택", False)
        edited = st.data_editor(d_df, hide_index=True, use_container_width=True, key="v_editor")
        s_rows = edited[edited["선택"] == True]
        if not s_rows.empty:
            sel_w = s_rows.iloc[-1]["word"]
            try:
                cell = worksheet.find(sel_w); row_idx = cell.row
                st.divider(); st.subheader("⚙️ 단어 수정 및 삭제")
                c1, c2, c3 = st.columns(3)
                with c1: n_w = st.text_input("영어 수정", value=sel_w)
                with c2: n_m = st.text_input("한글 수정", value=f_df.loc[f_df['word']==sel_w, 'mean'].values[0])
                with c3: n_r = st.text_input("어근 수정", value=f_df.loc[f_df['word']==sel_w, 'root'].values[0])
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
            except: st.error("동기화 오류. 새로고침을 눌러주세요.")

elif menu == "날짜별 단어 조회":
    st.header("📅 날짜별 등록 현황")
    if not df_main.empty:
        target = st.selectbox("날짜 선택", sorted(df_main['date'].astype(str).unique(), reverse=True))
        date_df = df_main[df_main['date'].astype(str) == target].copy()
        
        if st.button(f"📄 {target} 시험지 생성"):
            shuffled_df = date_df.sample(frac=1).reset_index(drop=True)
            now = datetime.now(timezone(timedelta(hours=9)))
            test_id = f"{now.strftime('%y%m%d')}-{target.replace('-', '')}"
            selected_dicts = shuffled_df.to_dict('records')
            pdf_buf = generate_pdf(selected_dicts, target, test_id)
            save_test_history(selected_dicts, test_id)
            st.download_button(label="📥 PDF 다운로드", data=pdf_buf.getvalue(), file_name=f"voca_{target}.pdf", mime="application/pdf")
        st.table(date_df.sort_values("word")[['word', 'mean']])

elif menu == "시험지 만들기":
    st.header("🖨️ 랜덤 시험지 생성")
    if len(df_main) < 5: st.error("단어가 부족합니다.")
    else:
        num = st.number_input("문제 수", 5, len(df_main), 20)
        if st.button("시험지 생성 및 카운트 업데이트"):
            selected = select_test_words(df_main, num)
            now = datetime.now(timezone(timedelta(hours=9)))
            test_id = now.strftime("%y%m%d-%H%M") 
            pdf_buf = generate_pdf(selected, "랜덤", test_id)
            save_test_history(selected, test_id)
            
            with st.spinner("카운트 업데이트 중..."):
                all_data = worksheet.get_all_values()
                header = all_data[0]; rows = all_data[1:]
                word_idx = header.index("word"); count_idx = header.index("count")
                sel_words = [item['word'] for item in selected]
                for row in rows:
                    if row[word_idx] in sel_words:
                        row[count_idx] = int(row[count_idx] or 0) + 1
                worksheet.update("A2", rows)
            st.success("✅ 카운트 반영 완료!")
            st.download_button("📥 PDF 다운로드", pdf_buf.getvalue(), f"test_{test_id}.pdf")

elif menu == "오답 체크하기":
    st.header("📝 시험지 오답 체크")
    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test")
        history_data = history_ws.get_all_records()
        if not history_data: st.warning("기록된 시험지가 없습니다.")
        else:
            test_options = [f"{r['test_id']} ({r['date']})" for r in history_data[:10]]
            selected_option = st.selectbox("채점할 시험지 ID 선택", test_options)
            selected_test = next(r for r in history_data if r['test_id'] == selected_option.split(" ")[0])
            test_words = selected_test['words'].split(",")
            st.info(f"💡 시험지의 번호와 아래 목록의 번호가 일치합니다.")
            wrong_words = []
            cols = st.columns(2)
            for i, word in enumerate(test_words):
                with cols[i % 2]:
                    if st.checkbox(f"{i+1}. {word}", key=f"chk_{word}_{i}"):
                        wrong_words.append(word)
            if st.button("🔴 오답 데이터 시트에 반영"):
                if not wrong_words: st.success("🎉 만점입니다!")
                else:
                    with st.spinner("오답 횟수 업데이트 중..."):
                        all_data = worksheet.get_all_values()
                        header = all_data[0]; rows = all_data[1:]
                        word_idx = header.index("word"); wrong_idx = header.index("wrong_count")
                        for row in rows:
                            if row[word_idx] in wrong_words:
                                row[wrong_idx] = int(row[wrong_idx] or 0) + 1
                        worksheet.update("A2", rows)
                        st.success(f"✅ {len(wrong_words)}개 반영 완료!"); time.sleep(1); st.rerun()
    except Exception as e: st.error(f"오류: {e}")



elif menu == "날짜별 오답 조회":
    st.header("📅 날짜별 오답 모아보기")
    st.write("선택한 날짜의 시험에서 틀렸던 단어들을 한눈에 확인하고 시험지를 만듭니다.")

    try:
        # 1. 히스토리 데이터 확보
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test")
        history_data = history_ws.get_all_records()

        if not history_data:
            st.warning("기록된 시험 히스토리가 없습니다.")
        else:
            history_df = pd.DataFrame(history_data)
            # 날짜만 추출 (yyyy-mm-dd)
            history_df['only_date'] = history_df['date'].str.split(' ').str[0]
            available_dates = sorted(history_df['only_date'].unique(), reverse=True)

            # 2. 날짜 선택
            target_date = st.selectbox("날짜 선택", available_dates)

            # 3. 해당 날짜의 모든 시험 단어 합치기
            daily_tests = history_df[history_df['only_date'] == target_date]
            all_words_that_day = []
            for _, row in daily_tests.iterrows():
                all_words_that_day.extend(row['words'].split(","))
            
            # 중복 제거 (그날 여러 시험에 나온 단어 대비)
            all_words_that_day = list(set(all_words_that_day))

            # 4. 메인 데이터에서 해당 단어들 중 '현재 오답인 것'만 필터링
            # 즉, 그날 시험 친 단어들 중 wrong_count > 0 인 것들
            wrong_results = df_main[
                (df_main['word'].isin(all_words_that_day)) & 
                (df_main['wrong_count'].astype(int) > 0)
            ].copy()

            if wrong_results.empty:
                st.info(f"✨ {target_date}에는 모든 문제를 맞히셨거나 기록된 오답이 없습니다!")
            else:
                st.success(f"📍 {target_date}에 발생한 오답: {len(wrong_results)}개")
                
                # 단어 목록 보기 느낌의 테이블 (정렬: 많이 틀린 순)
                display_df = wrong_results.sort_values("wrong_count", ascending=False)[['word', 'mean', 'wrong_count']]
                st.table(display_df)

                st.divider()
                
                # 5. 섞어서 시험지 만들기
                st.subheader("🔄 이 오답들로만 랜덤 시험지 만들기")
                if st.button(f"📄 {target_date} 오답 랜덤 시험지 생성"):
                    # 무작위 셔플
                    shuffled_wrong = wrong_results.sample(frac=1).reset_index(drop=True)
                    selected_dicts = shuffled_wrong.to_dict('records')
                    
                    # ID 생성 (RE-날짜 형식)
                    now = datetime.now(timezone(timedelta(hours=9)))
                    test_id = f"RE-{target_date.replace('-', '')}-{now.strftime('%H%M')}"
                    
                    # PDF 생성
                    pdf_buf = generate_pdf(selected_dicts, f"{target_date} 복습", test_id)
                    
                    # 다시 히스토리에 저장 (이 시험지도 나중에 채점 가능하도록)
                    save_test_history(selected_dicts, test_id)
                    
                    st.download_button(
                        label="📥 복습 시험지 PDF 다운로드",
                        data=pdf_buf.getvalue(),
                        file_name=f"review_{target_date}.pdf",
                        mime="application/pdf"
                    )

    except Exception as e:
        st.error(f"오류 발생: {e}")


elif menu == "지옥의 오답 노트":
    st.header("🔥 지옥의 오답 노트")
    threshold = st.number_input("최소 오답 횟수", min_value=1, value=3, step=1)
    wrong_df = df_main[df_main['wrong_count'].astype(int) >= threshold].copy()
    if wrong_df.empty: st.warning("해당하는 단어가 없습니다.")
    else:
        st.success(f"해당 단어: {len(wrong_df)}개")
        if st.button("📄 오답 노트 생성"):
            shuffled = wrong_df.sample(frac=1).reset_index(drop=True)
            selected_dicts = shuffled.to_dict('records')
            now = datetime.now(timezone(timedelta(hours=9)))
            test_id = f"WRONG-{threshold}-{now.strftime('%y%m%d')}"
            pdf_buf = generate_pdf(selected_dicts, f"오답({threshold}회↑)", test_id)
            save_test_history(selected_dicts, test_id)
            st.download_button("📥 PDF 다운로드", pdf_buf.getvalue(), f"wrong_note_{test_id}.pdf")
        st.table(wrong_df.sort_values("wrong_count", ascending=False)[['word', 'mean', 'wrong_count']])
