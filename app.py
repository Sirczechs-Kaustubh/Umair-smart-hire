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
from dotenv import load_dotenv
load_dotenv()

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

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__)
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecret')

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    os.makedirs(data_dir, exist_ok=True)
    RESUMES_FOLDER = os.path.join(data_dir, 'resumes')
    JOBS_FOLDER = os.path.join(data_dir, 'jobs')
    os.makedirs(RESUMES_FOLDER, exist_ok=True)
    os.makedirs(JOBS_FOLDER, exist_ok=True)

    db_path = os.path.join(data_dir, 'smarthire.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    app.register_blueprint(auth_bp)

    def get_jobs():
        """Reads jobs from CSV and adds a unique ID to each."""
        try:
            jobs_path = os.path.join(data_dir, 'jobs.csv')
            if not os.path.exists(jobs_path):
                return []
            
            jobs_df = pd.read_csv(jobs_path)
            jobs_df['id'] = jobs_df.index
            return jobs_df.to_dict('records')
        except Exception as e:
            print(f"Error reading or processing jobs.csv: {e}")
            return []

    with app.app_context():
        
        @app.route('/')
        def index():
            return render_template('index.html')

        @app.route('/user/upload_resume', methods=['GET', 'POST'])
        def upload_resume():
            if 'user_id' not in session or session.get('role') != 'User':
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login'))
            if request.method == 'POST':
                file = request.files.get('resume_file')
                if file:
                    filename = f"user_{session['user_id']}_{file.filename}"
                    path = os.path.join(RESUMES_FOLDER, filename)
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
                # --- Logic for Skill Gap and Recommendations ---
                first_job_skills = str(jobs[0].get('skills', '')).split(',') if pd.notna(jobs[0].get('skills')) else []
                resume_skills = resume_info.get('skills', [])
                skill_gap_report = skill_gap.find_skill_gap(resume_skills, first_job_skills)
                course_recs = course_recommender.recommend_courses(skill_gap_report)

                # --- CHANGE 1: Pass the apply_url to the template ---
                # Loop through all jobs for the matching report
                for job in jobs:
                    jd_inf = {
                        'skills': str(job.get('skills', '')).split(',') if pd.notna(job.get('skills')) else [],
                        'experience': job.get('experience', ''),
                        'education': job.get('education', '')
                    }
                    score, feedback = job_matcher.match_resume_to_jd(resume_info, jd_inf)
                    # Add all job info, including the new apply_url, to the job_matches list
                    job_matches.append({
                        'title': job.get('title', 'N/A'), 
                        'score': score, 
                        'feedback': feedback,
                        'apply_url': job.get('apply_url', '#') # Pass the URL to the template
                    })
                
                progress_chart = dashboard.generate_user_progress_chart(len(job_matches), len(course_recs))

            applied_jobs = get_user_applications(session['user_id'])
            return render_template('user_dashboard.html',
                                  skill_gap=skill_gap_report,
                                  course_recs=course_recs,
                                  job_matches=job_matches,
                                  progress_chart=progress_chart,
                                  applied_jobs=applied_jobs)

        # --- THIS FUNCTION IS NOW CORRECTED ---
        @app.route('/hr/post_job', methods=['GET', 'POST'])
        def post_job():
            if request.method == 'GET':
                return redirect(url_for('hr_dashboard'))

            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))
            
            # --- CHANGE 2: Get the new 'apply_url' from the form ---
            title = request.form.get('title')
            description = request.form.get('description')
            skills = request.form.get('skills')
            deadline = request.form.get('deadline')
            apply_url = request.form.get('apply_url') # Get the new field

            if not all([title, description, skills, deadline, apply_url]):
                flash("All fields are required to post a job.", "danger")
                return redirect(url_for('hr_dashboard'))
            
            # Add the new field to the DataFrame when creating the new job record
            df = pd.DataFrame([{'title': title, 'description': description, 'skills': skills, 'deadline': deadline, 'apply_url': apply_url}])
            jobs_path = os.path.join(data_dir, 'jobs.csv')
            
            # Append to the CSV file; write header only if the file doesn't exist
            df.to_csv(jobs_path, mode='a', header=not os.path.exists(jobs_path), index=False)
            
            flash('Job posted successfully.', 'success')
            return redirect(url_for('hr_dashboard'))

        @app.route('/hr/dashboard')
        def hr_dashboard():
            if 'user_id' not in session or session.get('role') != 'HR':
                flash("Please log in as an HR user to access this page.", "warning")
                return redirect(url_for('auth.login'))
            
            jobs = get_jobs()
            import random
            match_percentages = [random.randint(40, 100) for _ in range(20)]
            match_chart = dashboard.generate_hr_stats(match_percentages)
            
            return render_template('hr_dashboard.html', jobs=jobs, match_chart=match_chart)

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

            # Only process resumes of users who applied for this job
            applicants = get_applicants_for_job(job_id)
            resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'resumes')
            applicant_rows = []
            for applicant in applicants:
                resume_file = applicant['resume_filename']
                user_id = applicant['user_id']
                resume_path = os.path.join(resumes_dir, resume_file)
                resume_info = resume_parser.parse_resume_file(resume_path)
                score, feedback = job_matcher.match_resume_to_jd(resume_info, jd_info)
                applicant_rows.append({
                    'user_id': user_id,
                    'resume_filename': resume_file,
                    'score': score,
                    'feedback': feedback
                })
            applicant_rows.sort(key=lambda x: x['score'], reverse=True)

            return render_template(
                'screen_candidates.html',
                job=selected_job,
                applicants=applicant_rows
            )

        @app.route('/logout')
        def logout():
            session.clear()
            flash('You have been successfully logged out.', 'info')
            return redirect(url_for('auth.login'))

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
            resumes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'resumes')
            user_resume_filename = None
            for fname in os.listdir(resumes_dir):
                if f"user_{user_id}_" in fname:
                    user_resume_filename = fname
                    break

            if not user_resume_filename:
                flash("Please upload your resume first.", "danger")
                return redirect(url_for('user_dashboard'))

            # Record application only if not already applied
            applied_jobs = get_user_applications(user_id)
            if job_id in applied_jobs:
                flash("You have already applied for this job.", "info")
            else:
                record_application(user_id, job_id, user_resume_filename)
                flash("Successfully applied for the job!", "success")

            # Open the application URL in a new tab (JS handles it), redirect back
            return redirect(url_for('user_dashboard'))

    return app

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


        
        


