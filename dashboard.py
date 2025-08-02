# --- Begin: dashboard.py ---
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

def generate_hr_stats(matched_percentages):
    plt.figure()
    plt.hist(matched_percentages, bins=10)
    plt.xlabel('Match Percentage')
    plt.ylabel('Number of Candidates')
    plt.title('Resume-JD Match Distribution')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode()
    plt.close()
    return img_str

def generate_user_progress_chart(applied_jobs, completed_courses):
    plt.figure()
    plt.pie([applied_jobs, completed_courses], labels=['Jobs Applied', 'Courses Completed'], autopct='%1.1f%%')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode()
    plt.close()
    return img_str
# --- End: dashboard.py ---