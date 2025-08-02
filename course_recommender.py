import pandas as pd
import os

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
