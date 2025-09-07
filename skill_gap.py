import requests
import os
import json

# --- FIX 1: Use a current, valid model name and robust URL construction ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"

def find_skill_gap(resume_skills, jd_skills):
    """
    Use Gemini to find missing skills by semantic comparison.
    This version includes robust error handling and JSON parsing.
    """
    # --- FIX 2: Added robust error handling and logging ---
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        # Fallback: local set-difference without external API
        try:
            rs = set([s.strip().lower() for s in (resume_skills or []) if s])
            js = set([s.strip().lower() for s in (jd_skills or []) if s])
            return [s for s in (js - rs)]
        except Exception:
            return []

    if not resume_skills or not jd_skills:
        return []

    # A more robust prompt asking for a JSON list.
    prompt = (
        "You are an expert skills analyst. Compare the two lists of skills below. "
        f"Candidate's Skills: {resume_skills}\n"
        f"Required Job Skills: {jd_skills}\n"
        "Identify the skills that are present in the 'Required Job Skills' but are missing from the 'Candidate's Skills'. "
        "Consider semantic meaning (e.g., if the candidate has 'PyTorch', they do not need 'Deep Learning Framework'). "
        "Your response MUST be a single, valid JSON object with one key: 'missing_skills', which contains a list of strings. "
        "Example: {\"missing_skills\": [\"Kubernetes\", \"Terraform\"]}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 256}
    }

    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=20)

        if response.status_code != 200:
            print(f"API Error in skill_gap: Status Code {response.status_code}")
            print(f"Response: {response.text}")
            return []

        response_data = response.json()
        text_content = response_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')

        if not text_content:
            print("API response in skill_gap did not contain text content.")
            return []

        cleaned_text = text_content.strip().replace("```json", "").replace("```", "").strip()
        parsed_json = json.loads(cleaned_text)
        
        missing_skills = parsed_json.get('missing_skills', [])

        # Ensure the result is a list
        if not isinstance(missing_skills, list):
            print(f"Warning: Parsed missing_skills is not a list. Value: {missing_skills}")
            return []

        return missing_skills

    except requests.exceptions.RequestException as e:
        print(f"Network Error in skill_gap: {e}")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"--- PARSING ERROR in skill_gap ---")
        print(f"Error Type: {type(e).__name__}: {e}")
        if 'cleaned_text' in locals():
            print(f"--- Raw Text That Failed to Parse ---\n{cleaned_text}\n-------------------------------------")
        elif 'response' in locals() and hasattr(response, 'text'):
            print(f"--- Raw API Response ---\n{response.text}\n--------------------------")
    except Exception as e:
        print(f"An unexpected error occurred in skill_gap: {e}")

    # Return an empty list if any error occurs
    return []
