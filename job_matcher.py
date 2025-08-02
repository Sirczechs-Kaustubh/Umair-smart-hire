import requests
import os
import json

# It's better to read the API key once and build the full URL.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- THIS IS THE FIX ---
# Updated the model name from 'gemini-pro' to 'gemini-1.5-flash-latest', which is a current and valid model.
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"


def match_resume_to_jd(resume_info, jd_info):
    """
    Uses Gemini to compute a match score and short feedback. This version is more robust.
    """
    # 1. Check if the API key is missing.
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("ERROR: GEMINI_API_KEY environment variable not set or is a placeholder.")
        return 0, "API key is not configured."

    # 2. A more robust prompt asking specifically for a JSON object.
    prompt = (
        "You are an expert HR screening AI. Analyze the following resume and job description. "
        "Provide a match score from 0 to 100 and a single sentence of feedback. "
        "Your response MUST be a single, valid JSON object and nothing else. Do not wrap it in markdown backticks.\n"
        "Example: {\"score\": 88, \"feedback\": \"Strong technical skills but lacks direct domain experience.\"}\n\n"
        f"Resume Information:\n{json.dumps(resume_info)}\n\n"
        f"Job Description:\n{json.dumps(jd_info)}\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 256}
    }

    try:
        # 3. Make the API request
        response = requests.post(GEMINI_API_URL, json=payload)

        # 4. Check for a bad response (e.g., 4xx or 5xx errors)
        if response.status_code != 200:
            print(f"API Error: Status Code {response.status_code}")
            print(f"Response: {response.text}")
            return 0, f"API request failed with status {response.status_code}"

        # 5. Start robust parsing of the successful response
        response_data = response.json()
        text_content = response_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')

        if not text_content:
            print("API response did not contain expected text content.")
            print(f"Full Response: {response_data}")
            return 0, "Could not find content in API response."

        # The model sometimes wraps the JSON in ```json ... ```. We need to strip that.
        cleaned_text = text_content.strip().replace("```json", "").replace("```", "").strip()
        
        match_obj = json.loads(cleaned_text)
        
        score = match_obj.get('score', 0)
        feedback = match_obj.get('feedback', 'No feedback provided.')

        # A final check to ensure the score is a number.
        if not isinstance(score, (int, float)):
            print(f"Warning: Parsed score is not a number. Value: {score}")
            score = 0
            feedback = "Could not parse score from response."

        return score, feedback

    except requests.exceptions.RequestException as e:
        # Handle network errors
        print(f"Network Error: Could not connect to Gemini API. {e}")
        return 0, "Network error connecting to API."
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # Handle errors during parsing of the response. This is the most important block for debugging.
        print(f"--- PARSING ERROR ---")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {e}")
        # When a parsing error occurs, print the raw text that failed to parse.
        if 'cleaned_text' in locals():
            print(f"--- Raw Text That Failed to Parse ---\n{cleaned_text}\n-------------------------------------")
        elif 'response' in locals() and hasattr(response, 'text'):
             print(f"--- Raw API Response ---\n{response.text}\n--------------------------")
        return 0, 'Could not parse matching response'
    except Exception as e:
        # Catch any other unexpected errors
        print(f"An unexpected error occurred: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
             print(f"--- Raw API Response ---\n{response.text}\n--------------------------")
        return 0, 'An unexpected error occurred.'
