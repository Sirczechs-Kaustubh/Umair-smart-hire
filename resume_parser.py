import os
import docx2txt
import PyPDF2
import requests
import json

# --- FIX 1: Use a current, valid model name ---
# Updated the model from 'gemini-pro' to 'gemini-1.5-flash-latest'.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"

def extract_text_from_file(filepath):
    """Extracts text from PDF, DOCX, or TXT files."""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pdf':
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ' '.join([page.extract_text() for page in reader.pages if page.extract_text()])
        elif ext == '.docx':
            text = docx2txt.process(filepath)
        elif ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        else:
            print(f"Warning: Unsupported file format '{ext}' for file: {filepath}")
            return None
        return text
    except Exception as e:
        print(f"Error extracting text from {filepath}: {e}")
        return None

def extract_resume_entities(text, extract_type="resume"):
    """
    Use Gemini API to extract skills, experience, education, keywords from text.
    This version includes robust error handling.
    """
    # --- FIX 2: Added robust error handling and logging ---
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("ERROR: GEMINI_API_KEY environment variable not set or is a placeholder.")
        return {"skills": [], "experience": [], "education": [], "keywords": []}
        
    if not text:
        print("Error: Cannot extract entities from empty text.")
        return {"skills": [], "experience": [], "education": [], "keywords": []}

    prompt = (
        f"You are an expert resume parsing AI. Extract all relevant information from the following {extract_type} text. "
        "Your response MUST be a single, valid JSON object and nothing else. "
        "The JSON object should have four keys: 'skills' (a list of strings), 'experience' (a list of strings), "
        "'education' (a list of strings), and 'keywords' (a list of strings).\n\n"
        f"Text to parse:\n{text[:4000]}"  # Limit text size to avoid overly large requests
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}
    }

    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=30)

        if response.status_code != 200:
            print(f"API Error in resume_parser: Status Code {response.status_code}")
            print(f"Response: {response.text}")
            return {"skills": [], "experience": [], "education": [], "keywords": []}

        response_data = response.json()
        text_content = response_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')

        if not text_content:
            print("API response in resume_parser did not contain expected text content.")
            print(f"Full Response: {response_data}")
            return {"skills": [], "experience": [], "education": [], "keywords": []}

        cleaned_text = text_content.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned_text)
        
        # Ensure the parsed data has the expected keys
        for key in ['skills', 'experience', 'education', 'keywords']:
            if key not in parsed:
                parsed[key] = []

        return parsed

    except requests.exceptions.RequestException as e:
        print(f"Network Error in resume_parser: Could not connect to Gemini API. {e}")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"--- PARSING ERROR in resume_parser ---")
        print(f"Error Type: {type(e).__name__}: {e}")
        if 'cleaned_text' in locals():
            print(f"--- Raw Text That Failed to Parse ---\n{cleaned_text}\n-------------------------------------")
        elif 'response' in locals() and hasattr(response, 'text'):
            print(f"--- Raw API Response ---\n{response.text}\n--------------------------")
    except Exception as e:
        print(f"An unexpected error occurred in resume_parser: {e}")

    # If any error occurs, return a default empty structure
    return {"skills": [], "experience": [], "education": [], "keywords": []}


def parse_resume_file(filepath):
    """High-level function to parse a resume file."""
    print(f"Parsing resume file: {filepath}")
    text = extract_text_from_file(filepath)
    if text:
        entities = extract_resume_entities(text, extract_type="resume")
        print("Successfully parsed resume entities.")
        return entities
    print("Failed to extract text from resume.")
    return {}

def parse_jd_file(filepath):
    """High-level function to parse a job description file."""
    print(f"Parsing JD file: {filepath}")
    text = extract_text_from_file(filepath)
    if text:
        entities = extract_resume_entities(text, extract_type="job description")
        print("Successfully parsed JD entities.")
        return entities
    print("Failed to extract text from job description.")
    return {}
