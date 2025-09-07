import os
import hashlib
import json
from typing import List, Dict
import requests
import pandas as pd
import rag

def recommend_courses(missing_skills, course_csv_path=None, top_n=5):
    """
    Recommend courses that help fill missing skills.
    Each course in CSV must have 'title' and 'skills' columns (skills comma-separated).
    """
    # If no specific path is given, construct the default path to data/courses.csv
    if not course_csv_path:
        course_csv_path = os.path.join(os.path.dirname(__file__), 'data', 'courses.csv')

    # Gracefully handle the case where the courses file doesn't exist
    try:
        df = pd.read_csv(course_csv_path)
    except FileNotFoundError:
        print(f"Warning: Course recommendation file not found at {course_csv_path}")
        return []

    course_scores = []
    # Ensure the list of missing skills is clean and lowercased for comparison
    missing_skills_set = set([ms.lower().strip() for ms in missing_skills])

    for _, row in df.iterrows():
        # --- THIS IS THE FIX ---
        # First, check if the value in the 'skills' column is a string.
        # This prevents the error if the cell is empty (and read as a float by Pandas).
        if isinstance(row.get('skills'), str):
            course_skills = [s.strip().lower() for s in row['skills'].split(',')]
            
            # Calculate the overlap between what the course teaches and what the user needs
            overlap = set(course_skills) & missing_skills_set
            score = len(overlap)

            # Only consider courses that teach at least one missing skill
            if score > 0:
                course_scores.append((row['title'], row['url'], score))

    # Sort the courses by how many relevant skills they teach (highest score first)
    course_scores.sort(key=lambda x: -x[2])
    
    # Format the top N recommendations for display
    recommendations = [{"title": c[0], "url": c[1]} for c in course_scores[:top_n]]
    
    return recommendations


# -------- External API + RAG ranking (new) --------
def _cache_path(key: str) -> str:
    h = hashlib.md5(key.encode('utf-8')).hexdigest()
    cache_dir = os.path.join(os.path.dirname(__file__), 'data', 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'courses_{h}.json')

def fetch_courses_external(skills: List[str], provider: str = 'coursera', max_per_skill: int = 6) -> List[Dict]:
    """Fetch course candidates from an external provider.
    Returns list of dicts: {title, url, description}
    Gracefully falls back to empty on network errors.
    """
    skills = [s for s in skills if s]
    if not skills:
        return []

    cache_file = _cache_path(json.dumps({"skills": skills, "provider": provider}))
    # Cache read
    try:
        if os.path.isfile(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass

    out: List[Dict] = []
    headers = {
        'User-Agent': 'SmartHire/1.0 (+https://localhost)'
    }
    if provider == 'coursera':
        base = 'https://www.coursera.org/api/courses.v1'
        for skill in skills:
            try:
                resp = requests.get(base, params={'q': 'search', 'query': skill, 'limit': max_per_skill}, headers=headers, timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                elements = data.get('elements', [])
                for e in elements:
                    title = e.get('name') or e.get('slug') or ''
                    if not title:
                        continue
                    slug = e.get('slug') or ''
                    url = f'https://www.coursera.org/learn/{slug}' if slug else 'https://www.coursera.org'
                    out.append({
                        'title': title,
                        'url': url,
                        'description': ''
                    })
            except Exception:
                continue
    # de-dup by title
    seen = set()
    uniq = []
    for c in out:
        t = c.get('title','').strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(c)

    # Cache write
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(uniq, f)
    except Exception:
        pass
    return uniq

def recommend_courses_rag(skills: List[str], top_n: int = 10) -> List[Dict]:
    """Use external fetch + embeddings/Jaccard ranking to recommend courses."""
    skills = [s.strip() for s in skills if s and s.strip()]
    if not skills:
        return []
    # Fetch
    courses = fetch_courses_external(skills)
    if not courses:
        # fallback to local CSV
        return recommend_courses(skills, top_n=top_n)
    # Rank
    query = ' '.join(skills)
    items = [(str(i), f"{c.get('title','')} {c.get('description','')}") for i, c in enumerate(courses)]
    ranked = rag.best_matches(query, items, top_k=top_n)
    # Map back
    picks = []
    for iid, _txt, score in ranked:
        c = courses[int(iid)]
        c['score'] = round(float(score) * 100)
        picks.append(c)
    return picks
