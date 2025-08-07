import re
from PyPDF2 import PdfReader

def extract_resume_text(file):
    if file.name.endswith(".pdf"):
        reader = PdfReader(file)
        return " ".join([page.extract_text() or "" for page in reader.pages])
    else:
        return file.read().decode("utf-8")

def extract_tech_keywords(text):
    keywords = ["Python", "Java", "JavaScript", "React", "Node", "AWS", "Docker", "Kubernetes", "SQL", "Git"]
    found = [kw for kw in keywords if kw.lower() in text.lower()]
    return list(set(found))

def extract_skills_and_role_from_text(text):
    skills = extract_tech_keywords(text)
    
    # Extract role
    role_match = re.search(r"(developer|engineer|manager|analyst|architect)", text, re.IGNORECASE)
    role = role_match.group(0).title() if role_match else "Software Engineer"

    # Extract email
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    extracted_email = email_match.group(0) if email_match else ""

    return skills, role, extracted_email
