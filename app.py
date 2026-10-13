import streamlit as st
import pandas as pd
import gspread
import random
import re

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Vocabulary learning", page_icon="✨")

# --- GOOGLE SHEETS SETUP ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1g0u_rkhoWTq1bi6-KrUaVF3QQ7iBB-024oGG5nPxPrs/edit?gid=0#gid=0"

@st.cache_resource
def get_gspread_client():
    """Caches the authenticated client."""
    creds_dict = dict(st.secrets["gcp_service_account"])
    return gspread.service_account_from_dict(creds_dict)

@st.cache_data(ttl=300) 
def get_tab_names():
    client = get_gspread_client()
    sheet = client.open_by_url(SHEET_URL)
    return [ws.title for ws in sheet.worksheets()]

@st.cache_data(ttl=30)
def load_data_from_sheet(tab_name):
    client = get_gspread_client()
    sheet = client.open_by_url(SHEET_URL)
    worksheet = sheet.worksheet(tab_name)
    records = worksheet.get_all_records()
    return pd.DataFrame(records)

# --- TEXT MATCHING & NORMALIZATION ---
def clean_text(text):
    """Trims whitespace, collapses internal spaces, and lowercases."""
    t = str(text).lower().strip().strip(".,!?:;")
    return re.sub(r'\s+', ' ', t)

def is_correct_match(user_input, target):
    """
    Checks if user_input matches the target answer, treating anything
    in parentheses () or brackets [] as optional.
    """
    user_clean = clean_text(user_input)
    target_clean = clean_text(target)
    
    if not user_clean:
        return False

    valid_answers = set()
    
    # 1. Full original string
    valid_answers.add(target_clean)
    
    # 2. Version without any bracketed text (e.g., 'casa (f)' -> 'casa')
    without_bracket_content = re.sub(r'[\(\[].*?[\)\]]', '', target_clean)
    without_bracket_content = clean_text(without_bracket_content)
    if without_bracket_content:
        valid_answers.add(without_bracket_content)
        
    # 3. Version keeping bracket text but stripping the brackets (e.g., '(to) run' -> 'to run')
    symbols_removed = re.sub(r'[\(\)\[\]]', '', target_clean)
    symbols_removed = clean_text(symbols_removed)
    if symbols_removed:
        valid_answers.add(symbols_removed)

    # Allow user input with or without literal bracket symbols
    user_symbols_removed = re.sub(r'[\(\)\[\]]', '', user_clean)
    user_symbols_removed = clean_text(user_symbols_removed)

    return (user_clean in valid_answers) or (user_symbols_removed in valid_answers)

# --- SESSION STATE & QUEUE MANAGEMENT ---
def start_new_session(df, direction):
    """Initializes the active recall session."""
    st.session_state.queue = df.to_dict('records') 
    random.shuffle(st.session_state.queue) 
    
    st.session_state.total_words = len(df)
    st.session_state.words_completed = 0
    st.session_state.direction = direction
    
    if direction == "English -> Spanish":
        st.session_state.q_lang, st.session_state.a_lang = "English", "Spanish"
    else:
        st.session_state.q_lang, st.session_state.a_lang = "Spanish", "English"
        
    st.session_state.status = "asking"
    st.session_state.show_sparkles = False
    st.session_state.current_card = st.session_state.queue.pop(0) if st.session_state.queue else None

def advance_card(requeue=False):
    """Moves to next card, appending the failed card to the queue if needed."""
    if requeue and st.session_state.current_card:
        st.session_state.queue.append(st.session_state.current_card)
    
    if st.session_state.queue:
        st.session_state.current_card = st.session_state.queue.pop(0)
        st.session_state.status = "asking"
    else:
        st.session_state.current_card = None
        st.session_state.status = "finished"

# --- SIDEBAR UI ---
st.sidebar.title("📚 Library & Settings")

try:
    tab_names = get_tab_names()
    
    selected_set = st.sidebar.selectbox("Choose a vocabulary set:", options=tab_names)
    direction = st.sidebar.radio("Practice Direction:", ["English -> Spanish", "Spanish -> English"])
    
    if st.sidebar.button("Start / Reset Practice", type="primary", use_container_width=True):
        with st.sidebar.status("Loading vocabulary data..."):
            df = load_data_from_sheet(selected_set)
            
            if "English" not in df.columns or "Spanish" not in df.columns:
                st.sidebar.error("Your sheet must contain columns named 'English' and 'Spanish'!")
            else:
                start_new_session(df, direction)
                st.rerun()

except Exception as e:
    st.sidebar.error("Could not connect to Google Sheets. Check your Secrets and Share settings!")
    st.sidebar.exception(e)

# --- MAIN APP UI ---
st.title("Vocabulary learning ✨")

if "current_card" not in st.session_state:
    st.info("👈 Please select a vocabulary set and click **Start / Reset Practice** in the sidebar to begin.")
else:
    card = st.session_state.current_card
    
    # Finished state
    if card is None or st.session_state.status == "finished":
        st.success(f"🎉 Fantastic job! You've successfully mastered all {st.session_state.total_words} words!")
        st.balloons()
        
    # Active testing state
    else:
        q_lang = st.session_state.q_lang
        a_lang = st.session_state.a_lang
        
        question = card.get(q_lang, "N/A")
        target_answer = card.get(a_lang, "N/A")
        
        # Success feedback toast
        if st.session_state.show_sparkles:
            st.success("Correct! ✨ ✅")
            st.session_state.show_sparkles = False
            
        # Progress Counter
        queue_len = len(st.session_state.queue) + 1
        progress_val = st.session_state.words_completed / st.session_state.total_words if st.session_state.total_words > 0 else 1
        
        st.progress(
            progress_val, 
            text=f"Mastered: {st.session_state.words_completed} / {st.session_state.total_words} | Remaining in Queue: {queue_len}"
        )
        st.divider()
        
        # Display Prompt
        st.markdown(f"**Translate to {a_lang}:**")
        with st.container(border=True):
            st.markdown(f"<h2 style='text-align: center;'>{question}</h2>", unsafe_allow_html=True)
            
        st.write("")
        
        # State 1: Normal Question
        if st.session_state.status == "asking":
            with st.form("ask_form", clear_on_submit=True):
                user_val = st.text_input("Your Answer:", autocomplete="off")
                
                col1, col2 = st.columns(2)
                sub_btn = col1.form_submit_button("Submit Answer", type="primary", use_container_width=True)
                idk_btn = col2.form_submit_button("I don't know", use_container_width=True)
                
                if sub_btn:
                    if not user_val.strip():
                        st.warning("Please type an answer or click 'I don't know'.")
                    elif is_correct_match(user_val, target_answer):
                        st.session_state.words_completed += 1
                        st.session_state.show_sparkles = True
                        advance_card(requeue=False)
                        st.rerun()
                    else:
                        st.session_state.status = "wrong"
                        st.rerun()
                        
                elif idk_btn:
                    st.session_state.status = "idk"
                    st.rerun()

        # State 2: Incorrect Answer
        elif st.session_state.status == "wrong":
            st.info(f"Not quite! The correct answer is **{target_answer}**.")
            st.caption("This word will be placed back into your queue so you can revisit it later.")
            
            col1, col2 = st.columns(2)
            if col1.button("Next Word (Try again later) ➡️", type="primary", use_container_width=True):
                advance_card(requeue=True)
                st.rerun()
                
            if col2.button("I was actually right (typo) ✅", use_container_width=True):
                st.session_state.words_completed += 1
                st.session_state.show_sparkles = True
                advance_card(requeue=False)
                st.rerun()

        # State 3: "I Don't Know" Forced Retype
        elif st.session_state.status == "idk":
            st.warning(f"The correct answer is **{target_answer}**.")
            st.caption("Tip: Anything in brackets like (text) is optional.")
            st.write("Type the answer below to continue:")
            
            with st.form("idk_form", clear_on_submit=True):
                user_val = st.text_input("Retype the answer:", autocomplete="off")
                sub_btn = st.form_submit_button("Submit to continue", type="primary", use_container_width=True)
                
                if sub_btn:
                    if is_correct_match(user_val, target_answer):
                        advance_card(requeue=True)
                        st.rerun()
                    else:
                        st.error("That didn't match. Type the translation shown above to proceed.")
