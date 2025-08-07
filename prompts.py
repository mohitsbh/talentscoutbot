def generate_questions_prompt(skills, role):
    skill_string = ", ".join(skills)
    return f"""
You are an AI technical interviewer.

Generate **10 technical interview questions** for a candidate applying for the role of **{role}** with the following skills: {skill_string}.

For each question, also provide a **detailed, accurate answer**. Format your response exactly like this:

Q1: <question 1>  
A1: <answer 1>

Q2: <question 2>  
A2: <answer 2>

...and so on up to Q10.
"""
