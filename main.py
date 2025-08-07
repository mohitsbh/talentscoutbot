
# app.py
import streamlit as st
import os
import re
import requests
import sqlite3
import phonenumbers
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import smtplib
import tempfile
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from reportlab.lib.pagesizes import letter
from prompts import generate_questions_prompt
from utils import extract_tech_keywords, extract_resume_text, extract_skills_and_role_from_text

# ------------------------------
# Load environment variables
# ------------------------------
load_dotenv()
MISTRAL_API_KEY = os.getenv("FIREWORKS_API_KEY")
MISTRAL_API_URL = os.getenv("MISTRAL_API_URL")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_USER = os.getenv("EMAIL_ADDRESS")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD")

# ------------------------------
# Validators
# ------------------------------


def validate_email(email):
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email) is not None


def validate_phone(phone, country_code="US"):
    try:
        number = phonenumbers.parse(phone, country_code)
        return phonenumbers.is_valid_number(number)
    except phonenumbers.NumberParseException:
        return False

# ------------------------------
# Database
# ------------------------------


def init_db():
    conn = sqlite3.connect("candidates.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, phone TEXT, 
            exp INTEGER, position TEXT, location TEXT,
            tech_stack TEXT, consent TEXT, timestamp TEXT
        )
    ''')
    # Add 'country' column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE candidates ADD COLUMN country TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()
    conn.close()


def save_candidate_data(data):
    conn = sqlite3.connect("candidates.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO candidates (name, email, phone, exp, position, location, country, tech_stack, consent, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data["name"], data["email"], data["phone"], data["exp"],
        data["position"], data["location"], data["country"],
        data["tech_stack"], data["consent"], data["timestamp"]
    ))
    conn.commit()
    conn.close()


def delete_user_data(email):
    conn = sqlite3.connect("candidates.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM candidates WHERE email = ?", (email,))
    conn.commit()
    conn.close()

# ------------------------------
# Email with PDF
# ------------------------------


def send_email_with_questions(to_email, questions, candidate_name):
    subject = "Your Generated Interview Questions"
    body_text = f"Dear {candidate_name or 'Candidate'},\n\nHere are your generated interview questions:\n\n{questions}"

    message = MIMEMultipart()
    message["From"] = EMAIL_USER
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body_text, "plain"))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        pdf_path = tmp_pdf.name

    doc = SimpleDocTemplate(pdf_path)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Generated Interview Questions",
                          styles['Title']), Spacer(1, 12)]
    for q in questions.split("\n"):
        if q.strip():
            elements.append(Paragraph(q.strip(), styles['Normal']))
            elements.append(Spacer(1, 6))
    doc.build(elements)

    with open(pdf_path, "rb") as file:
        pdf_attachment = MIMEApplication(file.read(), _subtype="pdf")
        pdf_attachment.add_header(
            'Content-Disposition', 'attachment', filename="questions.pdf")
        message.attach(pdf_attachment)

    try:
        with smtplib.SMTP_SSL(EMAIL_HOST, 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(message)
        return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False
    finally:
        os.unlink(pdf_path)

# ------------------------------
# GPT Generator
# ------------------------------


def ask_gpt(prompt):
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post(MISTRAL_API_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']


def generate_pdf_bytes(questions_text: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Generated Interview Questions",
                          styles["Title"]), Spacer(1, 12)]
    for line in questions_text.strip().split('\n'):
        if line.strip():
            elements.append(Paragraph(line.strip(), styles["Normal"]))
            elements.append(Spacer(1, 6))
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="🤖 TalentScout")
st.title("🤖 TalentScout Hiring Assistant")

init_db()

with st.expander("🔐 GDPR Privacy Notice"):
    st.markdown(
        "- Data kept max 6 months\n- Right to request deletion\n- Contact: https://gdpr-info.eu/")

resume_file = st.file_uploader(
    "📤 Upload Your Resume (PDF or TXT)", type=["pdf", "txt"])
if resume_file:
    text = extract_resume_text(resume_file)
    skills, role, extracted_email = extract_skills_and_role_from_text(text)
    role = role or ""
    extracted_email = extracted_email or ""

    st.success("Resume processed.")
    st.markdown(f"**Top Skills Detected:** `{', '.join(skills)}`")
    st.markdown(f"**Inferred Role:** `{role if role else 'Not detected'}`")

    with st.form("Resume Info Confirmation"):
        manual_role = st.text_input(
            "🧑‍💼 Please confirm or edit your Job Role:", value=role)
        manual_email = st.text_input(
            "📧 Please confirm or edit your email:", value=extracted_email)
        manual_consent = st.checkbox("🔐 I consent to GDPR data processing")

        submitted_resume_form = st.form_submit_button("Continue")
        if submitted_resume_form:
            if not manual_consent:
                st.warning("❌ GDPR consent required.")
            elif not validate_email(manual_email):
                st.warning("❌ Invalid email.")
            else:
                st.session_state.candidate_info = {
                    "name": "", "email": manual_email, "phone": "",
                    "exp": 0, "position": manual_role, "location": "",
                    "country": "", "tech_stack": ", ".join(skills),
                    "consent": "yes",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                st.session_state.stage = 'generate_questions'

if 'stage' not in st.session_state:
    st.session_state.stage = 'info_gathering'

if st.session_state.stage == 'info_gathering':
    with st.form("Candidate Form"):
        name = st.text_input("Full Name")
        email = st.text_input("Email Address")
        phone = st.text_input("Phone Number")
        exp = st.number_input("Years of Experience", 0, 50, 1)
        position = st.text_input("Job Role / Position")
        location = st.text_input("Location")
        country = st.text_input("Country (e.g. US, IN, GB)")
        tech_stack = st.text_area("Tech Stack (e.g. Python, React, AWS)")
        consent = st.checkbox("I consent to data processing", value=False)
        submitted = st.form_submit_button("Submit")

        if submitted:
            if not all([name, email, phone, position, location, tech_stack]):
                st.warning("Please fill all required fields.")
            elif not validate_email(email):
                st.warning("Enter a valid email.")
            elif not validate_phone(phone, country.upper()):
                st.warning("Enter a valid phone number for your country.")
            elif not consent:
                st.warning("GDPR consent is required.")
            else:
                candidate = {
                    "name": name, "email": email, "phone": phone, "exp": exp,
                    "position": position, "location": location, "country": country,
                    "tech_stack": tech_stack, "consent": "yes",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                st.session_state.candidate_info = candidate
                save_candidate_data(candidate)
                st.session_state.stage = 'generate_questions'

if st.session_state.stage == 'generate_questions':
    st.subheader("Generating Questions...")
    data = st.session_state.candidate_info
    techs = extract_tech_keywords(data["tech_stack"])
    prompt = generate_questions_prompt(techs, data["position"])

    if 'generated_questions' not in st.session_state:
        try:
            st.session_state.generated_questions = ask_gpt(prompt)
        except Exception as e:
            st.error(f"Failed to generate questions: {e}")
            st.stop()

    questions_text = st.session_state.generated_questions
    st.success("Here are your interview questions:")
    st.write(questions_text)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔁 Regenerate"):
            st.session_state.generated_questions = ask_gpt(prompt)
            st.rerun()
    with col2:
        if st.button("📧 Email Me"):
            if send_email_with_questions(data["email"], questions_text, data["name"]):
                st.success("Email sent successfully!")
    with col3:
        pdf_bytes = generate_pdf_bytes(questions_text)
        st.download_button(
            label="📄 Download PDF",
            data=pdf_bytes,
            file_name="interview_questions.pdf",
            mime="application/pdf"
        )
    with col4:
        if st.button("✅ Finish"):
            st.success("Thank you! We'll be in touch.")
            st.session_state.stage = 'end'

# --- Deletion Section ---
with st.expander("🧹 Request Data Deletion"):
    delete_email = st.text_input("Enter your email to delete your data")
    if st.button("Delete My Data"):
        if validate_email(delete_email):
            delete_user_data(delete_email)
            st.success("Your data has been deleted.")
        else:
            st.warning("Enter a valid email.")


# Initialize DB
init_db()
