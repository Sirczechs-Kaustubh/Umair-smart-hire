import requests
import os
import json
from typing import Tuple, List

# It's better to read the API key once and build the full URL.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- THIS IS THE FIX ---
# Updated the model name from 'gemini-pro' to 'gemini-1.5-flash-latest', which is a current and valid model.
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"


def _local_match(resume_info: dict, jd_info: dict) -> Tuple[int, str]:
    """Embedding + coverage based score. Returns (0-100 score, short feedback)."""
    try:
        import rag
    except Exception:
        rag = None  # type: ignore

    rskills: List[str] = [s.strip() for s in (resume_info or {}).get('skills', []) if s and s.strip()]
    jskills: List[str] = [s.strip() for s in (jd_info or {}).get('skills', []) if s and s.strip()]
    rs = set(s.lower() for s in rskills)
    js = set(s.lower() for s in jskills)
    coverage = (len(rs & js) / len(js)) if js else 0.0

    # Build text representations for semantic match
    rtext = ' '.join(rskills + (resume_info or {}).get('education', []) + (resume_info or {}).get('experience', []))
    jtext = ' '.join(jskills + [str((jd_info or {}).get('description', ''))])
    semantic = 0.0
    if rag:
        try:
            ranked = rag.best_matches(rtext or ' '.join(rskills), [("jd", jtext)], top_k=1)
            if ranked:
                semantic = float(ranked[0][2])
        except Exception:
            semantic = 0.0
    # Combine; give more weight to hard skill coverage
    cov_w = float(os.getenv('COVERAGE_WEIGHT', '0.65'))
    sem_w = 1.0 - cov_w
    score = int(round(100 * (cov_w * coverage + sem_w * semantic))) if (coverage or semantic) else 0
    fb = f"Covers {int(coverage*100)}% JD skills; semantic {int(semantic*100)}%."
    return score, fb


def match_resume_to_jd(resume_info, jd_info):
    """
    Uses Gemini to compute a match score and short feedback when configured.
    Otherwise, uses a strong local embedding-based scorer with reranking.
    """
    # If API key is missing or disabled, use local scorer
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY" or os.getenv('USE_AI_MATCH', '0') != '1':
        return _local_match(resume_info, jd_info)

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

        # Blend AI score with local score to stabilize outputs
        try:
            lscore, lfb = _local_match(resume_info, jd_info)
            blend_w = float(os.getenv('AI_BLEND_WEIGHT', '0.4'))  # 0 = local only, 1 = AI only
            final = int(round((blend_w * float(score)) + ((1.0 - blend_w) * float(lscore))))
            feedback = feedback or lfb
            return final, feedback
        except Exception:
            return score, feedback

    except requests.exceptions.RequestException as e:
        # Handle network errors
        print(f"Network Error: Could not connect to Gemini API. {e}")
        return _local_match(resume_info, jd_info)
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
        return _local_match(resume_info, jd_info)
    except Exception as e:
        # Catch any other unexpected errors
        print(f"An unexpected error occurred: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
             print(f"--- Raw API Response ---\n{response.text}\n--------------------------")
        return _local_match(resume_info, jd_info)
