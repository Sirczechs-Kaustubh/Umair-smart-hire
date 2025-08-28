# app.py

import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import pandas as pd

# Import your local modules
import resume_parser, skill_gap, course_recommender, job_matcher, dashboard

# Import extensions and blueprints
from extensions import db
from auth_bp import auth_bp, User

import csv
from datetime import datetime
# Safe import for python-dotenv (so the app still runs if not installed)
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(*args, **kwargs):  # no-op fallback
        return False
    
# ---- SQLite fallback to avoid Anaconda DLL issues ----
try:
    import pysqlite3  # type: ignore
    import sys
    sys.modules['sqlite3'] = pysqlite3
    sys.modules['sqlite'] = pysqlite3
except Exception:
    pass
# ------------------------------------------------------

# Call it once early to load .env if present
load_dotenv()

class CompanyProfile(db.Model):
    __tablename__ = 'company_profiles'
    id = db.Column(db.Integer, primary_key=True)
    hr_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    name = db.Column(db.String(200), default='Your Company Name')
    description = db.Column(db.Text, default='Your company description goes here.')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    to_user_id = db.Column(db.Integer, nullable=False)     # the candidate (User)
    from_hr_id = db.Column(db.Integer, nullable=False)     # the HR sender
    job_id = db.Column(db.Integer, nullable=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='unread')    # 'unread' | 'read'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserProfile(db.Model):
    __tablename__ = 'user_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    full_name = db.Column(db.String(200), default='')
    objective = db.Column(db.Text, default='')
    gender = db.Column(db.String(20), default='')
    education = db.Column(db.Text, default='')
    experience = db.Column(db.Text, default='')
    skills = db.Column(db.Text, default='')
    hobbies = db.Column(db.Text, default='')
    resume_filename = db.Column(db.String(300), default='')
    courses_completed = db.Column(db.Integer, default=0)

APPLICATIONS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'applications.csv')

def record_application(user_id, job_id, resume_filename):
    """Append a new application to the applications.csv file."""
    applied_at = datetime.utcnow().isoformat()
    file_exists = os.path.isfile(APPLICATIONS_CSV)
    with open(APPLICATIONS_CSV, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(['user_id', 'job_id', 'resume_filename', 'applied_at'])
        writer.writerow([user_id, job_id, resume_filename, applied_at])



# ---------user section----------------
def get_user_applications(user_id):
    """Returns a set of job_ids the user has applied to."""
    applied_jobs = set()
    if os.path.isfile(APPLICATIONS_CSV):
        with open(APPLICATIONS_CSV, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if str(row['user_id']) == str(user_id):
                    applied_jobs.add(int(row['job_id']))
    return applied_jobs

def get_applicants_for_job(job_id):
    """Return a list of dicts for users who applied to job_id."""
    applicants = []
    if os.path.isfile(APPLICATIONS_CSV):
        with open(APPLICATIONS_CSV, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if int(row['job_id']) == int(job_id):
                    applicants.append(row)
    return applicants

def get_applicants_for_jobs(job_ids):
    found = []
    if os.path.isfile(APPLICATIONS_CSV):
        with open(APPLICATIONS_CSV, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    if int(row['job_id']) in job_ids:
                        found.append(row)
                except:
                    continue
    return found

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__)

    # ---------- Core paths (single source of truth) ----------
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    resumes_dir = os.path.join(data_dir, 'resumes')
    jobs_dir    = os.path.join(data_dir, 'jobs')
    os.makedirs(resumes_dir, exist_ok=True)
    os.makedirs(jobs_dir,    exist_ok=True)

    # CSV paths in app.config so all helpers use the same files
    app.config['JOBS_CSV']         = os.path.join(data_dir, 'jobs.csv')
    app.config['APPLICATIONS_CSV'] = os.path.join(data_dir, 'applications.csv')
    # after you set data_dir
    app.config['POSTED_CSV'] = os.path.join(data_dir, 'posted.csv')


    # ---------- Jinja helpers ----------
    @app.context_processor
    def inject_unread_counts():
        try:
            if session.get('role') == 'User' and session.get('user_id'):
                uid = int(session['user_id'])
                unread = Notification.query.filter_by(to_user_id=uid, status='unread').count()
                return {"user_unread_notifs": unread}
        except Exception:
            pass
        return {"user_unread_notifs": 0}

    @app.context_processor
    def inject_route_flags():
        from flask import request
        return {
            "current_endpoint": request.endpoint or "",
            "current_path": request.path or "/",
        }

    # ---------- Flask / DB config ----------
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecret')
    app.debug = True  # umair1

    db_path = os.path.join(data_dir, 'smarthire.db')  # single definitive DB path
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(auth_bp)

    # ---------- Small helper route (no inline JS in template) ----------
    @app.route('/hr/screen_candidates_select', methods=['GET'])
    def screen_candidates_select():
        if 'user_id' not in session or session.get('role') != 'HR':
            flash("Please log in as an HR user to access this page.", "warning")
            return redirect(url_for('auth.login'))
        jid = request.args.get('job_id', type=int)
        if jid is None:
            flash("Please select a job to screen.", "warning")
            return redirect(url_for('hr_dashboard'))
        return redirect(url_for('screen_candidates', job_id=jid))

    # ---------- CSV helpers ----------
    def record_posted_job(hr_id: str, job_id: int, title: str, description: str, skills: str, deadline: str):
        """Append a minimal posted-job record to posted.csv (now with description & skills)."""
        posted_csv = app.config['POSTED_CSV']
        file_exists = os.path.isfile(posted_csv)
        with open(posted_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['hr_id', 'job_id', 'title', 'description', 'skills', 'deadline']
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                'hr_id': hr_id,
                'job_id': int(job_id),
                'title': title,
                'description': description,
                'skills': skills,
                'deadline': deadline
            })


    def get_jobs():
        """
        Robustly read jobs.csv and normalize columns.
        Returns list of dicts with keys: id, title, description, skills, deadline, apply_url, hr_id
        """
        jobs_csv = app.config['JOBS_CSV']
        required = ['title', 'description', 'skills', 'deadline', 'apply_url', 'hr_id']

        if not os.path.exists(jobs_csv):
            return []

        # --- Try Pandas first (most reliable for properly quoted CSVs) ---
        try:
            df = pd.read_csv(jobs_csv, engine='python')  # engine='python' is more tolerant
            # Drop accidental unnamed cols
            df = df.loc[:, ~df.columns.astype(str).str.startswith('Unnamed')]
            # Ensure all required columns exist
            for col in required:
                if col not in df.columns:
                    df[col] = '' if col != 'hr_id' else ''
            # Stable id
            df['id'] = df.index
            # Make hr_id strings for consistent filtering
            df['hr_id'] = df['hr_id'].astype(str).fillna('')
            # Return
            return df[required + ['id']].to_dict('records')

        except Exception as e:
            print("Error reading jobs.csv (pandas):", e)

        # --- Fallback: robust csv.reader with header mapping if possible ---
        jobs = []
        try:
            with open(jobs_csv, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                raw_header = next(reader, None)
                header = [h.strip().lower() for h in raw_header] if raw_header else []

                # Map known columns if present
                idx = {name: (header.index(name) if name in header else None) for name in required}

                def get_cell(row, name, default=''):
                    j = idx.get(name)
                    return row[j].strip() if (j is not None and j < len(row)) else default

                i = 0
                for row in reader:
                    if not row or all(part.strip() == '' for part in row):
                        continue

                    # Path A: header has names → normal extraction
                    if any(idx.values()):
                        jobs.append({
                            'id': i,
                            'title':       get_cell(row, 'title'),
                            'description': get_cell(row, 'description'),
                            'skills':      get_cell(row, 'skills'),
                            'deadline':    get_cell(row, 'deadline'),
                            'apply_url':   get_cell(row, 'apply_url'),
                            'hr_id':       get_cell(row, 'hr_id')
                        })
                        i += 1
                        continue

                    # Path B: no/unknown header → heuristic by row length.
                    # Common patterns we recover:
                    #  - 6+ cols: [title, ...description..., skills, deadline, apply_url, hr_id]
                    #  - 5 cols:  [title, description, skills, deadline, apply_url]
                    #  - 4 cols:  [title, description, skills, deadline]
                    n = len(row)
                    title = row[0].strip() if n >= 1 else ''
                    if n >= 6:
                        hr_id     = row[-1].strip()
                        apply_url = row[-2].strip()
                        deadline  = row[-3].strip()
                        skills    = row[-4].strip()
                        description = ','.join([c.strip() for c in row[1:-4]])  # glue the middle back
                    elif n == 5:
                        hr_id     = ''
                        apply_url = row[-1].strip()
                        deadline  = row[-2].strip()
                        skills    = row[-3].strip()
                        description = ','.join([c.strip() for c in row[1:-3]])
                    elif n == 4:
                        hr_id     = ''
                        apply_url = ''
                        deadline  = row[-1].strip()
                        skills    = row[-2].strip()
                        description = ','.join([c.strip() for c in row[1:-2]])
                    else:
                        # Too short/malformed; skip
                        continue

                    jobs.append({
                        'id': i,
                        'title': title,
                        'description': description,
                        'skills': skills,
                        'deadline': deadline,
                        'apply_url': apply_url,
                        'hr_id': hr_id
                    })
                    i += 1

            return jobs

        except Exception as e2:
            print("Error reading jobs.csv via csv.reader:", e2)

        # --- Last resort: build from posted.csv to keep the UI alive ---
        try:
            posted = get_posted_jobs(hr_id=None)  # [{'job_id','title','description','skills','deadline','hr_id'}...]
            out = []
            for p in posted:
                out.append({
                    'id': int(p.get('job_id', -1)),
                    'title': p.get('title', ''),
                    'description': p.get('description', ''),
                    'skills': p.get('skills', ''),
                    'deadline': p.get('deadline', ''),
                    'apply_url': '',                 # unknown here
                    'hr_id': p.get('hr_id', '')
                })
            return out
        except Exception:
            pass

        # If absolutely nothing works:
        return []

    def get_applicants_for_jobs(job_ids):
        """Return all application rows where job_id is in job_ids."""
        apps_csv = app.config['APPLICATIONS_CSV']
        if not os.path.isfile(apps_csv):
            return []
        out = []
        with open(apps_csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    if int(row.get('job_id', -1)) in job_ids:
                        out.append(row)
                except Exception:
                    continue
        return out

    def get_applicants_for_job(job_id):
        """Return application rows for a single job id."""
        return get_applicants_for_jobs([int(job_id)])

    def get_user_applications(user_id):
        """Return set of job_ids already applied by a user."""
        apps_csv = app.config['APPLICATIONS_CSV']
        if not os.path.isfile(apps_csv):
            return set()
        ids = set()
        with open(apps_csv, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    if int(row.get('user_id', -1)) == int(user_id):
                        ids.add(int(row.get('job_id', -1)))
                except Exception:
                    continue
        return ids

    def record_application(user_id, job_id, resume_filename):
        """Append a new application row (idempotency left to caller)."""
        apps_csv = app.config['APPLICATIONS_CSV']
        file_exists = os.path.isfile(apps_csv)
        with open(apps_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['user_id', 'job_id', 'resume_filename'])
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                'user_id': int(user_id),
                'job_id': int(job_id),
                'resume_filename': resume_filename
            })

    # ---------- Routes ----------
    with app.app_context():

        @app.route('/')
        def index():
            return render_template('index.html')

        def get_or_create_user_profile(uid: int) -> UserProfile:
            prof = UserProfile.query.filter_by(user_id=uid).first()
            if not prof:
                prof = UserProfile(user_id=uid)
                db.session.add(prof)
                db.session.commit()
            return prof

        @app.route('/user/home')
        def user_home():
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in as a User.", "warning")
                return redirect(url_for('auth.login'))
            uid = session['user_id']
            prof = get_or_create_user_profile(uid)
            # Progress: jobs applied (from applications.csv), courses completed (from profile)
            applied = len(get_user_applications(uid))
            completed = prof.courses_completed or 0
            # naive totals (you can tune later)
            total_jobs = max(len(get_jobs()), 1)
            total_courses = 5
            # safe percentages
            jobs_pct = int(round((applied / total_jobs) * 100)) if total_jobs else 0
            courses_pct = int(round((completed / total_courses) * 100)) if total_courses else 0

            return render_template(
                'user_home.html',
                profile=prof,
                applied=applied, total_jobs=total_jobs,
                completed=completed, total_courses=total_courses,
                jobs_pct=jobs_pct, courses_pct=courses_pct
            )

        @app.route('/user/profile', methods=['GET','POST'])
        def user_profile():
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in as a User.", "warning")
                return redirect(url_for('auth.login'))
            uid = session['user_id']
            prof = get_or_create_user_profile(uid)

            if request.method == 'POST':
                prof.full_name = (request.form.get('full_name') or '').strip()
                prof.objective = (request.form.get('objective') or '').strip()
                prof.gender = (request.form.get('gender') or '').strip()
                prof.education = (request.form.get('education') or '').strip()
                prof.experience = (request.form.get('experience') or '').strip()
                prof.skills = (request.form.get('skills') or '').strip()
                prof.hobbies = (request.form.get('hobbies') or '').strip()

                # optional resume upload
                file = request.files.get('resume_file')
                if file and file.filename:
                    filename = f"user_{uid}_{file.filename}"
                    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'resumes', filename)
                    file.save(path)
                    prof.resume_filename = filename
                    # keep your existing parse -> session flow
                    entities = resume_parser.parse_resume_file(path)
                    session['resume_info'] = entities

                db.session.commit()
                flash("Profile saved.", "success")
                return redirect(url_for('user_profile'))

            return render_template('user_profile.html', profile=prof)
        
        @app.route('/jobs/<int:job_id>')
        def job_view(job_id):
            jobs = get_jobs()
            if job_id >= len(jobs):
                flash("Job not found.", "warning")
                return redirect(url_for('user_dashboard'))
            j = jobs[job_id]
            return render_template('job_view.html', job=j, job_id=job_id)


        @app.route('/user/upload_resume', methods=['GET', 'POST'])
        def upload_resume():
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login'))
            if request.method == 'POST':
                file = request.files.get('resume_file')
                if file:
                    filename = f"user_{session['user_id']}_{file.filename}"
                    path = os.path.join(resumes_dir, filename)
                    file.save(path)
                    entities = resume_parser.parse_resume_file(path)
                    session['resume_info'] = entities
                    flash('Resume uploaded and parsed!', 'success')
                    return redirect(url_for('user_dashboard'))
            return render_template('upload_resume.html')

        @app.route('/user/dashboard')
        def user_dashboard():
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login'))

            resume_info = session.get('resume_info')
            skill_gap_report, course_recs, job_matches, progress_chart = [], [], [], None

            jobs = get_jobs()

            if resume_info and jobs:
                first_job_skills = str(jobs[0].get('skills', '')).split(',') if pd.notna(jobs[0].get('skills')) else []
                resume_skills = resume_info.get('skills', [])
                skill_gap_report = skill_gap.find_skill_gap(resume_skills, first_job_skills)
                course_recs = course_recommender.recommend_courses(skill_gap_report)

                for job in jobs:
                    jd_inf = {
                        'skills': str(job.get('skills', '')).split(',') if pd.notna(job.get('skills')) else [],
                        'experience': job.get('experience', ''),
                        'education': job.get('education', '')
                    }
                    score, feedback = job_matcher.match_resume_to_jd(resume_info, jd_inf)
                    job_matches.append({
                        'id': job.get('id'),
                        'title': job.get('title', 'N/A'),
                        'score': score,
                        'feedback': feedback,
                        'apply_url': job.get('apply_url', '#')
                    })

                progress_chart = dashboard.generate_user_progress_chart(len(job_matches), len(course_recs))

            applied_jobs = get_user_applications(session['user_id'])
            return render_template(
                'user_dashboard.html',
                skill_gap=skill_gap_report,
                course_recs=course_recs,
                job_matches=job_matches,
                progress_chart=progress_chart,
                applied_jobs=applied_jobs
            )

        # ---------- Post Job (GET page + POST save; Apply URL optional) ----------
        @app.route('/hr/post_job', methods=['GET', 'POST'])
        def post_job():
            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))

            if request.method == 'GET':
                return render_template('post_job.html')

            # POST save
            title = (request.form.get('title') or '').strip()
            description = (request.form.get('description') or '').strip()
            skills = (request.form.get('skills') or '').strip()
            deadline = (request.form.get('deadline') or '').strip()
            apply_url = (request.form.get('apply_url') or '').strip()   # optional
            hr_id = str(session['user_id'])

            if not all([title, description, skills, deadline]):
                flash("Title, Description, Skills, and Deadline are required.", "danger")
                return redirect(url_for('post_job'))

            jobs_csv = app.config['JOBS_CSV']

            # Determine the row index that this new job will get in jobs.csv
            new_index = 0
            if os.path.exists(jobs_csv):
                try:
                    record_posted_job(
                        hr_id=hr_id,
                        job_id=new_index,
                        title=title,
                        description=description,   # <-- add
                        skills=skills,             # <-- add
                        deadline=deadline
                    )
                except Exception as e:
                    print("Error writing posted.csv:", e)

            # Append to jobs.csv (keep existing behavior)
            row = pd.DataFrame([{
                'title': title,
                'description': description,
                'skills': skills,
                'deadline': deadline,
                'apply_url': apply_url,
                'hr_id': hr_id
            }])
            try:
                row.to_csv(jobs_csv, mode='a', header=not os.path.exists(jobs_csv), index=False)
            except Exception as e:
                print("Error writing jobs.csv:", e)
                flash("Failed to save job. Check server logs/permissions.", "danger")
                return redirect(url_for('post_job'))

            # ALSO: record a minimal entry in posted.csv for HR Home
            try:
                record_posted_job(hr_id=hr_id, job_id=new_index, title=title, deadline=deadline)
            except Exception as e:
                print("Error writing posted.csv:", e)

            flash("Job posted successfully!", "success")
            return redirect(url_for('hr_home'))


        @app.route('/hr/dashboard')
        def hr_dashboard():
            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))

            hr_id = str(session['user_id'])

            # Jobs this HR posted (from posted.csv), keep their job_id (index in jobs.csv)
            posted_jobs = get_posted_jobs(hr_id=hr_id)  # [{'job_id', 'title', 'deadline', 'description','skills',...}]
            posted_ids = [int(j['job_id']) for j in posted_jobs]

            # Pull full jobs list from jobs.csv to enrich/validate
            all_jobs = get_jobs()
            job_by_id = {int(j['id']): j for j in all_jobs}
            hr_jobs = []
            for pj in posted_jobs:
                j = job_by_id.get(int(pj['job_id']))
                if j:
                    hr_jobs.append(j)
                else:
                    # fallback to posted.csv row if jobs.csv changed
                    hr_jobs.append({
                        'id': int(pj['job_id']),
                        'title': pj.get('title', 'Untitled'),
                        'skills': pj.get('skills', ''),
                        'description': pj.get('description', ''),
                        'deadline': pj.get('deadline', '')
                    })

            # Applicants belonging to this HR's jobs
            applicants = get_applicants_for_jobs(posted_ids)  # from applications.csv

            # Build "Applied Candidates" table + compute match scores
            rows = []
            resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'resumes')
            for app_row in applicants:
                try:
                    uid = int(app_row['user_id'])
                    jid = int(app_row['job_id'])
                except Exception:
                    continue

                user = User.query.get(uid)
                cand_name = user.username if user else f"User {uid}"
                job = job_by_id.get(jid)
                job_title = job['title'] if job else next((p['title'] for p in posted_jobs if int(p['job_id']) == jid), f"Job {jid}")

                jd_info = {
                    "skills": str(job.get('skills', '')).split(',') if job else [],
                    "title": job_title,
                    "description": job.get('description', '') if job else ''
                }

                score = "-"
                resume_file = app_row.get('resume_filename')
                if resume_file:
                    rpath = os.path.join(resumes_dir, resume_file)
                    if os.path.isfile(rpath):
                        resume_info = resume_parser.parse_resume_file(rpath)
                        s, _fb = job_matcher.match_resume_to_jd(resume_info, jd_info)
                        score = s if s is not None else "-"

                rows.append({
                    "user_id": uid,
                    "candidate": cand_name,
                    "job_id": jid,
                    "job_title": job_title,
                    "score": score,
                })

            # --- Analytics: applicants per job (including zeros) ---
            from collections import Counter
            counts = Counter(int(a['job_id']) for a in applicants if str(a.get('job_id','')).isdigit())
            chart_labels = [j['title'] for j in hr_jobs]                       # ordered by hr_jobs
            chart_values = [counts.get(int(j['id']), 0) for j in hr_jobs]

            # Bar chart (PNG base64). If no jobs, don't draw empty axes.
            counts_chart = None
            if chart_labels:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt
                import io, base64

                buf = io.BytesIO()
                plt.figure(figsize=(8,4.5))
                plt.bar(range(len(chart_values)), chart_values)
                plt.xticks(range(len(chart_labels)), chart_labels, rotation=25, ha='right')
                plt.ylabel('Number of Candidates')
                plt.title('Applicants per Job')
                plt.tight_layout()
                plt.savefig(buf, format='png')
                buf.seek(0)
                counts_chart = base64.b64encode(buf.getvalue()).decode()
                plt.close()

            # For the "Screen candidates" selector we need hr_jobs (id + title)
            # Normalize to a small dict
            selector_jobs = [{"id": int(j["id"]), "title": j["title"]} for j in hr_jobs]

            return render_template(
                'hr_dashboard.html',
                hr_jobs=selector_jobs,
                applicants_table=rows,
                counts_chart=counts_chart
            )


        @app.route('/hr/home', methods=['GET', 'POST'])
        def hr_home():
            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))

            # Company profile
            profile = CompanyProfile.query.filter_by(hr_user_id=session['user_id']).first()
            if not profile:
                profile = CompanyProfile(hr_user_id=session['user_id'])
                db.session.add(profile)
                db.session.commit()

            if request.method == 'POST':
                profile.name = (request.form.get('company_name') or profile.name).strip()
                profile.description = (request.form.get('company_description') or profile.description).strip()
                db.session.commit()
                flash("Company profile saved.", "success")
                return redirect(url_for('hr_home'))

            # ✅ Read the HR's posted jobs from posted.csv
            hr_id = str(session['user_id'])
            posted_jobs = get_posted_jobs(hr_id=str(session['user_id']))

            return render_template('hr_home.html', profile=profile, posted_jobs=posted_jobs)
        
        def normalize_posted_csv():
            posted_csv = app.config['POSTED_CSV']
            if not os.path.isfile(posted_csv):
                return
            data = get_posted_jobs(hr_id=None)  # already robust
            # Rewrite with the canonical 6-column header
            with open(posted_csv, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['hr_id','job_id','title','description','skills','deadline'])
                writer.writeheader()
                for r in data:
                    writer.writerow(r)


        # def get_posted_jobs(hr_id: str | None = None):
        #     """Read posted.csv; optionally filter by hr_id; fill missing description/skills from jobs.csv by job_id."""
        #     posted_csv = app.config['POSTED_CSV']
        #     if not os.path.isfile(posted_csv):
        #         return []

        #     try:
        #         df = pd.read_csv(posted_csv)
        #     except Exception as e:
        #         print("Error reading posted.csv:", e)
        #         return []

        #     # Clean columns
        #     df = df.loc[:, ~df.columns.astype(str).str.startswith('Unnamed')]
        #     for col in ['hr_id', 'job_id', 'title', 'description', 'skills', 'deadline']:
        #         if col not in df.columns:
        #             df[col] = '' if col != 'job_id' else -1

        #     # Types
        #     with pd.option_context('mode.chained_assignment', None):
        #         df['job_id'] = pd.to_numeric(df['job_id'], errors='coerce').fillna(-1).astype(int)
        #         df['hr_id']  = df['hr_id'].astype(str)

        #     # Optional filter by HR
        #     if hr_id is not None:
        #         df = df[df['hr_id'] == str(hr_id)]

        #     # --- Fill missing description/skills from jobs.csv by job_id ---
        #     jobs_csv = app.config['JOBS_CSV']
        #     if os.path.isfile(jobs_csv):
        #         try:
        #             jdf = pd.read_csv(jobs_csv)
        #             jdf = jdf.loc[:, ~jdf.columns.astype(str).str.startswith('Unnamed')]
        #         except Exception as e:
        #             print("Error reading jobs.csv in get_posted_jobs:", e)
        #             jdf = None

        #         if jdf is not None:
        #             # Build lookup maps by row index (job_id == index assigned at post time)
        #             desc_map   = {i: str(jdf.at[i, 'description']) if 'description' in jdf.columns else '' for i in jdf.index}
        #             skills_map = {i: str(jdf.at[i, 'skills'])       if 'skills' in jdf.columns else '' for i in jdf.index}

        #             missing_desc = df['description'].astype(str).str.strip().eq('')
        #             missing_skls = df['skills'].astype(str).str.strip().eq('')

        #             df.loc[missing_desc, 'description'] = df.loc[missing_desc, 'job_id'].map(desc_map).fillna('')
        #             df.loc[missing_skls, 'skills']      = df.loc[missing_skls, 'job_id'].map(skills_map).fillna('')

        #     return df.to_dict('records')

        def get_posted_jobs(hr_id: str | None = None):
            """
            Read posted.csv with mixed row shapes (legacy 4 cols or new 6 cols).
            Returns a list of dicts with keys: hr_id, job_id, title, description, skills, deadline.
            """
            posted_csv = app.config['POSTED_CSV']
            if not os.path.isfile(posted_csv):
                return []

            rows = []
            try:
                with open(posted_csv, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    # Try to detect header; if the first row contains any non-numeric in job_id position,
                    # we treat it as header and skip it.
                    header = next(reader, None)
                    def looks_like_header(h):
                        if not h: 
                            return False
                        # legacy header 4 cols or new 6 cols
                        maybe = [s.strip().lower() for s in h]
                        return 'hr_id' in maybe and 'job_id' in maybe and 'title' in maybe
                    if header and not looks_like_header(header):
                        # first row is actually data; put it back into the iteration
                        reader = iter([header] + list(reader))

                    for row in reader:
                        if not row or all(part.strip() == '' for part in row):
                            continue
                        # New format: 6 columns: hr_id, job_id, title, description, skills, deadline
                        if len(row) >= 6:
                            hr, jid, title, desc, sk, dl = row[:6]
                        # Legacy format: 4 columns: hr_id, job_id, title, deadline
                        elif len(row) >= 4:
                            hr, jid, title, dl = row[:4]
                            desc, sk = '', ''
                        else:
                            # malformed row; skip
                            continue

                        if hr_id is not None and str(hr).strip() != str(hr_id):
                            continue

                        try:
                            jid = int(jid)
                        except Exception:
                            # bad id; skip
                            continue

                        rows.append({
                            'hr_id': str(hr).strip(),
                            'job_id': jid,
                            'title': title,
                            'description': desc,
                            'skills': sk,
                            'deadline': dl
                        })
            except Exception as e:
                print("Error reading posted.csv robustly:", e)
                return []

            return rows

        @app.route('/hr/notify', methods=['POST'])
        def hr_notify():
            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))

            to_user_id = request.form.get('to_user_id')
            job_id = request.form.get('job_id')
            message = (request.form.get('message') or '').strip()

            if not to_user_id or not message:
                flash("Message is required.", "danger")
                return redirect(url_for('hr_dashboard'))

            notif = Notification(
                to_user_id=int(to_user_id),
                from_hr_id=session['user_id'],
                job_id=int(job_id) if job_id else None,
                message=message,
                status='unread'
            )
            db.session.add(notif)
            db.session.commit()
            flash("Notification sent to candidate.", "success")
            return redirect(url_for('hr_dashboard'))

        @app.route('/hr/screen_candidates/<int:job_id>')
        def screen_candidates(job_id):
            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))

            jobs = get_jobs()
            if job_id >= len(jobs):
                flash(f"Invalid job ID: {job_id}", "danger")
                return redirect(url_for('hr_dashboard'))

            selected_job = jobs[job_id]
            job_skills = str(selected_job.get('skills', '')).split(',') if pd.notna(selected_job.get('skills')) else []
            jd_info = {
                'skills': job_skills,
                'experience': selected_job.get('experience', ''),
                'education': selected_job.get('education', ''),
                'description': selected_job.get('description', '')
            }

            applicants = get_applicants_for_job(job_id)
            applicant_rows = []
            for applicant in applicants:
                resume_file = applicant['resume_filename']
                user_id = applicant['user_id']
                rpath = os.path.join(resumes_dir, resume_file)
                resume_info = resume_parser.parse_resume_file(rpath)
                score, feedback = job_matcher.match_resume_to_jd(resume_info, jd_info)
                applicant_rows.append({
                    'user_id': user_id,
                    'resume_filename': resume_file,
                    'score': score,
                    'feedback': feedback
                })
            applicant_rows.sort(key=lambda x: x['score'], reverse=True)

            return render_template('screen_candidates.html', job=selected_job, applicants=applicant_rows)

        @app.route('/logout')
        def logout():
            session.clear()
            flash('You have been successfully logged out.', 'info')
            return redirect(url_for('auth.login'))

        @app.route('/user/notifications')
        def user_notifications():
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in as a User to access notifications.", "warning")
                return redirect(url_for('auth.login'))

            uid = session['user_id']
            notifs = Notification.query.filter_by(to_user_id=uid).order_by(Notification.created_at.desc()).all()
            return render_template('user_notifications.html', notifs=notifs)

        @app.route('/user/apply/<int:job_id>', methods=['POST'])
        def apply_for_job(job_id):
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in to apply for jobs.", "warning")
                return redirect(url_for('auth.login'))

            user_id = session['user_id']
            jobs = get_jobs()
            if job_id >= len(jobs):
                flash("Invalid job selected.", "danger")
                return redirect(url_for('user_dashboard'))

            # Find user's resume filename
            user_resume_filename = None
            for fname in os.listdir(resumes_dir):
                if f"user_{user_id}_" in fname:
                    user_resume_filename = fname
                    break

            if not user_resume_filename:
                flash("Please upload your resume first.", "danger")
                return redirect(url_for('user_dashboard'))

            applied_jobs = get_user_applications(user_id)
            if job_id in applied_jobs:
                flash("You have already applied for this job.", "info")
            else:
                record_application(user_id, job_id, user_resume_filename)
                flash("Successfully applied for the job!", "success")

            return redirect(url_for('user_dashboard'))
        

        # ---------------------run once(for formatting jobs.csv file)-------------------
        # def normalize_jobs_csv():
        #     jobs = get_jobs()  # uses robust loader above
        #     jobs_csv = app.config['JOBS_CSV']
        #     if not jobs:
        #         return
        #     # Keep canonical order
        #     cols = ['title', 'description', 'skills', 'deadline', 'apply_url', 'hr_id']
        #     df = pd.DataFrame(jobs)[cols]
        #     df.to_csv(jobs_csv, index=False)  # writes a clean, consistent file
        #     print("jobs.csv normalized with", len(df), "rows.")

    return app


# -------------------setup_database-------------------
def setup_database(app):
    """Create database tables and initial users."""
    with app.app_context():
        db.create_all()
        
        if not User.query.filter_by(username='test_user').first():
            test_user = User(username='test_user', role='User')
            test_user.set_password('test_password')
            db.session.add(test_user)
            print("Created initial 'test_user'.")

        if not User.query.filter_by(username='test_hr').first():
            test_hr = User(username='test_hr', role='HR')
            test_hr.set_password('hr_password')
            db.session.add(test_hr)
            print("Created initial 'test_hr'.")

        db.session.commit()

if __name__ == '__main__':
    app = create_app()
    setup_database(app)
    app.run(debug=True)


        
        


