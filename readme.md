# SmartHire

**SmartHire** is an AI-powered Flask web application for job seekers and recruiters, featuring automated resume parsing, job matching, skill gap analysis, and HR applicant screening.  
It uses Gemini 1.5 Flash for AI tasks, with a robust, modular Python backend and a clean, extensible UI.

---

## 🚀 Features

- **User Registration & Login** (Job seeker & HR roles)
- **Resume Upload** (PDF, DOCX, TXT)
- **AI Resume Parsing** (Gemini API)
- **Automated Job Matching & Skill Gap Analysis**
- **Personalized Course Recommendations**
- **HR Dashboard:**  
  - Post new jobs (with application links)
  - View all posted jobs
  - Screen and rank real applicants by match score and AI feedback
- **"Apply" Tracker:**  
  - Users can mark jobs as applied; HRs only see actual applicants per job
- **Dashboard Analytics:**  
  - Visual stats on skills, progress, and job matching

---

## 🗂️ Project Structure

SmartHire/
│
├── app.py # Main Flask app (App Factory, routes, setup)
├── auth_bp.py # Authentication blueprint (SQLAlchemy models)
├── extensions.py # SQLAlchemy db object
│
├── resume_parser.py # Resume text extraction & AI parsing (Gemini)
├── job_matcher.py # Resume-job matching, returns score + feedback
├── skill_gap.py # Skill gap analysis (Gemini-powered)
├── course_recommender.py # Course recommendations for missing skills
├── dashboard.py # Analytics and charts (matplotlib)
│
├── data/
│ ├── jobs.csv # All posted jobs (id, title, desc, skills, etc)
│ ├── courses.csv # List of upskilling courses (title, url, skills)
│ ├── resumes/ # All uploaded resumes
│ ├── applications.csv # Records user applications: user_id, job_id, resume, timestamp
│
├── templates/ # Jinja2 HTML templates
│ ├── layout.html
│ ├── login.html
│ ├── register.html
│ ├── user_dashboard.html
│ ├── hr_dashboard.html
│ ├── upload_resume.html
│ ├── screen_candidates.html
│ ├── index.html
│
├── static/
│ └── styles.css # App styling
│
├── .env # (Not checked in) API keys and secrets
├── requirements.txt # Python dependencies
└── README.md


---

## ⚙️ Setup Instructions

1. **Clone the Repository**
    ```bash
    git clone https://github.com/your-username/SmartHire.git
    cd SmartHire
    ```

2. **Create and Activate a Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate    # On Windows: venv\Scripts\activate
    ```

3. **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4. **Configure Environment Variables**

    - Create a `.env` file in the project root:
        ```
        GEMINI_API_KEY=your_gemini_api_key_here
        FLASK_SECRET_KEY=your_flask_secret_key_here
        ```
    - Never commit `.env` to version control!

5. **Run the Application**
    ```bash
    python app.py
    ```
    Or, for development with hot reload:
    ```bash
    flask run
    ```

---

## 💡 Usage Guide

- **Job Seeker:**
  - Register/login as "User"
  - Upload your resume
  - View your dashboard: skill gaps, recommended courses, and job matches
  - Click "Apply" to mark interest (and open application link)
- **HR:**
  - Register/login as "HR"
  - Post new jobs (with application URLs)
  - View all posted jobs, click "View Applicants" to screen only those who applied

---

## 🔒 Security Notes

- Store API keys and secrets in `.env`, not in code or git!
- For production use, switch to a real database (e.g., PostgreSQL) and deploy behind HTTPS.

---

## 🤖 AI Model

- All AI functions can use [Gemini 1.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-1.5) via Google’s API for:
    - Resume parsing (merged with local extraction by default)
    - Job-resume matching (optionally blended with local semantic scoring)
    - Skill gap analysis

---

## 🔍 Matching & Parsing (Upgraded)

- Local resume parsing is robust and fast:
  - PDF extraction tries PyPDF2 → pdfminer.six → PyMuPDF (if installed)
  - Optional spaCy-assisted skill extraction via `PhraseMatcher` (set `SPACY_MODEL=en_core_web_sm` and install if desired)
  - Section-aware skill detection + fuzzy matching + keyword extraction
- Semantic similarity uses Sentence-Transformers embeddings with strong defaults and fallbacks:
  - Preferred: set `EMBEDDINGS_MODEL` (e.g., `BAAI/bge-base-en-v1.5` or `mixedbread-ai/mxbai-embed-large-v1`)
  - Fallback: `all-MiniLM-L6-v2`
- Optional reranker boosts result quality:
  - CrossEncoder model (default `cross-encoder/ms-marco-MiniLM-L-6-v2`) reorders top candidates
  - Enable with `USE_RERANKER=1` (default on)
- Scoring blends hard skill coverage with semantic similarity; tune with `COVERAGE_WEIGHT` (default `0.65`).

### Suggested Installs (optional but recommended)
```
pip install spacy pdfminer.six pymupdf
python -m spacy download en_core_web_sm
```

---

## ⚙️ Configuration

Add any of the following to `.env` as needed:

- `PARSE_WITH_LLM_ONLY=0` (default): merge local + LLM. Set to `1` for LLM-only.
- `EMBEDDINGS_MODEL=BAAI/bge-base-en-v1.5` (or another HF model name)
- `USE_RERANKER=1` and `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`
- `COVERAGE_WEIGHT=0.65` to balance skill coverage vs semantic similarity
- `USE_AI_MATCH=1` to invoke Gemini on top candidates (blended with local by default)
- `AI_BLEND_WEIGHT=0.4` (0 = local only, 1 = AI only) when `USE_AI_MATCH=1`

To warm the embedder and caches (optional), visit `/admin/warmup_embeddings` as an HR user.

---

## 📝 License

This project is for demonstration/educational purposes.  
For commercial use, review third-party license terms for Gemini and any other data or frameworks.

---

## 👨‍💻 Contributing

Open an issue or PR to suggest features or report bugs!


---
