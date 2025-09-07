import os
import re
import json
import difflib
import requests
import docx2txt
import PyPDF2
from typing import List, Set
import hashlib
import time

# --- FIX 1: Use a current, valid model name ---
# Updated the model from 'gemini-pro' to 'gemini-1.5-flash-latest'.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Default to combining local parsing with LLM enrichment when an API key is set
# Set PARSE_WITH_LLM_ONLY=1 to force LLM-only behavior
PARSE_WITH_LLM_ONLY = os.getenv("PARSE_WITH_LLM_ONLY", "0") == "1"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"

def extract_text_from_file(filepath):
    """Extracts text from PDF, DOCX, or TXT files. Tries multiple backends for PDFs."""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        text = None
        if ext == '.pdf':
            # First try PyPDF2
            try:
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = ' '.join([page.extract_text() or '' for page in reader.pages]).strip()
            except Exception:
                text = None
            # Fallback to pdfminer.six if installed
            if not text:
                try:
                    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
                    text = (pdfminer_extract_text(filepath) or '').strip()
                except Exception:
                    text = None
            # Optional: PyMuPDF (fitz) if available
            if not text:
                try:
                    import fitz  # type: ignore
                    doc = fitz.open(filepath)
                    parts = []
                    for page in doc:
                        parts.append(page.get_text())
                    text = ' '.join(parts).strip()
                except Exception:
                    text = None
        elif ext == '.docx':
            text = docx2txt.process(filepath) or ''
        elif ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        else:
            print(f"Warning: Unsupported file format '{ext}' for file: {filepath}")
            return None
        return (text or '').strip()
    except Exception as e:
        print(f"Error extracting text from {filepath}: {e}")
        return None

def _normalize_skill(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def _load_skill_vocab() -> Set[str]:
    """Build a skill vocabulary from jobs.csv + a fallback static list."""
    vocab: Set[str] = set()
    base = os.path.dirname(os.path.abspath(__file__))
    jobs_csv = os.path.join(base, 'data', 'jobs.csv')
    try:
        import csv
        with open(jobs_csv, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                skills = (row.get('skills') or '')
                for s in str(skills).split(','):
                    s2 = _normalize_skill(s)
                    if s2:
                        vocab.add(s2)
    except Exception:
        pass

    # Minimal curated fallback list for common tech and soft skills
    fallback = [
        'python', 'java', 'javascript', 'typescript', 'react', 'redux', 'node.js', 'nodejs', 'express', 'html', 'css',
        'flask', 'django', 'sql', 'postgresql', 'mysql', 'mongodb', 'aws', 'gcp', 'azure', 'docker', 'kubernetes',
        'linux', 'git', 'ci', 'cd', 'ci/cd', 'rest', 'restful apis', 'graphql', 'pandas', 'numpy', 'scikit-learn',
        'sklearn', 'tensorflow', 'pytorch', 'nlp', 'computer vision', 'opencv', 'data analysis', 'etl', 'airflow',
        'spark', 'hadoop', 'tableau', 'power bi', 'agile', 'scrum', 'jira', 'communication', 'leadership'
    ]
    for s in fallback:
        vocab.add(_normalize_skill(s))
    return vocab

def _split_sections(text: str) -> dict:
    """Rudimentary section splitter: returns lowercased section name -> text block.
    Looks for common headings and splits on them. Robust to extra punctuation and spaces.
    """
    if not text:
        return {}
    headings = [
        'skills', 'technical skills', 'tech skills', 'core competencies', 'competencies', 'tech stack', 'tools',
        'experience', 'work experience', 'professional experience', 'employment history', 'projects',
        'education', 'certifications', 'achievements', 'summary', 'objective'
    ]
    # Build a regex that matches headings at line starts
    pat = re.compile(r"^(?P<h>" + r"|".join([re.escape(h) for h in headings]) + r")\b\s*[:\-]*\s*$", re.IGNORECASE | re.MULTILINE)
    sections = {}
    last_pos = 0
    last_name = 'preamble'
    for m in pat.finditer(text):
        # close previous section
        sections[last_name.lower()] = sections.get(last_name.lower(), '') + text[last_pos:m.start()]
        last_name = m.group('h').lower()
        last_pos = m.end()
    # tail
    sections[last_name.lower()] = sections.get(last_name.lower(), '') + text[last_pos:]
    return sections

ALIASES = {
    'js': 'javascript', 'node': 'node.js', 'nodejs': 'node.js', 'ts': 'typescript', 'tf': 'tensorflow',
    'sklearn': 'scikit-learn', 'pyspark': 'spark', 'postgres': 'postgresql', 'mongodb': 'mongodb',
    'reactjs': 'react', 'gitlab ci': 'ci', 'github actions': 'ci', 'ci/cd': 'ci', 'oop': 'object oriented programming',
    'nlp': 'nlp', 'cv': 'computer vision', 'k8s': 'kubernetes'
}

SEPARATORS = r"[,;/\|\u2022\u2023\u25E6\u2043\u2219\u00B7]"  # commas, slashes, bullets

def _canon_skill(s: str) -> str:
    s2 = _normalize_skill(s)
    if not s2:
        return ''
    return ALIASES.get(s2, s2)

def _extract_skills_from_section(txt: str, vocab: Set[str]) -> Set[str]:
    out: Set[str] = set()
    if not txt:
        return out
    # Split by common separators and newlines
    parts = re.split(SEPARATORS + r"|\n", txt)
    parts = [p.strip() for p in parts if p and p.strip()]
    for p in parts:
        c = _canon_skill(p)
        if not c:
            continue
        if c in vocab:
            out.add(c)
            continue
        # Fuzzy match to vocab for near-misses (e.g., Javascript vs JavaScript, TypScritp, etc.)
        close = difflib.get_close_matches(c, vocab, n=1, cutoff=0.88)
        if close:
            out.add(close[0])
        else:
            out.add(c)
    return out

def _scan_text_for_skills(txt: str, vocab: Set[str]) -> Set[str]:
    out: Set[str] = set()
    if not txt:
        return out
    t = ' ' + txt.lower() + ' '
    # Multi-word first
    multi = sorted([v for v in vocab if ' ' in v], key=len, reverse=True)
    for phrase in multi:
        if phrase in t:
            out.add(phrase)
            t = t.replace(phrase, ' ')
    # Single tokens
    for v in vocab:
        if ' ' in v:
            continue
        if re.search(rf"(?<![\w\-]){re.escape(v)}(?![\w\-])", t):
            out.add(v)
    return out

def _local_extract_entities(text: str) -> dict:
    """Local, fast entity extraction: skills from a vocab, simple education/experience heuristics."""
    if not text:
        return {"skills": [], "experience": [], "education": [], "keywords": []}
    vocab = _load_skill_vocab()
    skills_found: Set[str] = set()
    sections = _split_sections(text)
    # Prefer explicit skills sections if present
    for key in ['skills', 'technical skills', 'tech skills', 'core competencies', 'competencies', 'tech stack', 'tools']:
        if key in sections:
            skills_found |= _extract_skills_from_section(sections[key], vocab)
    # Also scan the whole text to pick up missed items
    skills_found |= _scan_text_for_skills(text, vocab)

    # Education heuristics
    edu = []
    edu_patterns = [r"b\.?tech|bachelor|b\.sc|bs\b", r"m\.?tech|master|m\.sc|ms\b", r"phd|doctorate"]
    for p in edu_patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            edu.append(p.replace('\\', ''))

    # Experience lines (very naive)
    exp = []
    for line in text.splitlines():
        if re.search(r"\b(\d+\+?\s*(years|yrs))\b", line, flags=re.IGNORECASE):
            exp.append(line.strip()[:200])

    # Keywords: keep top frequent tokens excluding stopwords and numbers
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-\+\.]{1,}", text.lower())
    stop = set(['the','and','for','with','from','this','that','have','has','are','was','were','your','their','our','you','in','on','to','of','as','by','an','a'])
    freq = {}
    for tok in tokens:
        if tok in stop:
            continue
        freq[tok] = freq.get(tok, 0) + 1
    keywords = [w for w,_ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:30]]

    # Optional: spaCy-assisted extraction if available
    try:
        import spacy  # type: ignore
        nlp = None
        # Try to load preferred model via env var; fallback to en_core_web_sm
        spacy_model = os.getenv('SPACY_MODEL', 'en_core_web_sm')
        try:
            nlp = spacy.load(spacy_model)
        except Exception:
            nlp = None
        if nlp is not None:
            from spacy.matcher import PhraseMatcher  # type: ignore
            doc = nlp(text)
            # Phrase match skills from vocab (more robust tokenization than regex)
            pm = PhraseMatcher(nlp.vocab, attr='LOWER')
            patterns = [nlp.make_doc(v) for v in sorted(vocab) if v]
            # Avoid enormous matchers for very large vocabs
            for i in range(0, len(patterns), 1000):
                pm.add(f'SKILLS_{i}', patterns[i:i+1000])
            matched = set()
            for m_id, start, end in pm(doc):
                span = doc[start:end]
                matched.add(_canon_skill(span.text))
            skills_found |= matched

            # Extra heuristic: capture tokens following phrases like "experience with", "proficient in"
            triggers = re.compile(r"\b(experience with|proficient in|worked with|using)\b", re.IGNORECASE)
            for sent in doc.sents:
                if triggers.search(sent.text):
                    # take nouns and proper nouns as potential tools/skills
                    for tok in sent:
                        if tok.pos_ in {"PROPN", "NOUN"} and len(tok.text) > 1:
                            cand = _canon_skill(tok.text)
                            if cand in vocab or len(cand) > 2:
                                skills_found.add(cand)
    except Exception:
        pass

    return {
        "skills": sorted({_canon_skill(s) for s in skills_found if s}),
        "experience": exp[:20],
        "education": edu[:10],
        "keywords": keywords
    }

def _cache_paths(key: str):
    cache_dir = os.path.join(os.path.dirname(__file__), 'data', 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    h = hashlib.md5(key.encode('utf-8')).hexdigest()
    return os.path.join(cache_dir, f"llm_parse_{h}.json")

def _cache_get(key: str):
    path = _cache_paths(key)
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def _cache_set(key: str, data: dict):
    path = _cache_paths(key)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"data": data, "ts": int(time.time())}, f)
    except Exception:
        pass

def extract_resume_entities(text, extract_type="resume"):
    """
    Use Gemini API to extract skills, experience, education, keywords from text.
    This version includes robust error handling.
    """
    # --- FIX 2: Added robust error handling and logging ---
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        # No external API: local fast extraction
        return _local_extract_entities(text)
        
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
        # Cache by text+type to avoid repeated requests and rate limits
        cache_key = f"{extract_type}:{hashlib.md5(text.encode('utf-8')).hexdigest()}"
        cached = _cache_get(cache_key)
        if cached and isinstance(cached, dict) and 'data' in cached:
            return cached['data']

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

        # Ensure types
        for k in ['skills','experience','education','keywords']:
            if k not in parsed or not isinstance(parsed[k], list):
                parsed[k] = []

        if PARSE_WITH_LLM_ONLY:
            _cache_set(cache_key, parsed)
            return parsed

        # Optionally enrich with local extractor when explicitly allowed
        try:
            local = _local_extract_entities(text)
            ls = set([_normalize_skill(s) for s in local.get('skills', [])])
            gs = set([_normalize_skill(s) for s in parsed.get('skills', [])])
            merged = sorted(ls | gs)
            parsed['skills'] = merged
            parsed['experience'] = (parsed.get('experience') or [])[:30]
            parsed['education'] = (parsed.get('education') or [])[:20]
            parsed['keywords'] = (parsed.get('keywords') or local.get('keywords') or [])[:50]
        except Exception:
            pass
        _cache_set(cache_key, parsed)
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
