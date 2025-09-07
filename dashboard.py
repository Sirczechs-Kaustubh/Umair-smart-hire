# --- Begin: dashboard.py ---
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

PRIMARY = '#6ea8fe'
ACCENT = '#9d86ff'
TEXT = '#dbe4ff'
GRID = 'rgba(255,255,255,0.2)'
BG = '#0b1220'

def _style_axes(ax):
    ax.set_facecolor('none')
    for spine in ax.spines.values():
        spine.set_color((1,1,1,0.2))
    ax.tick_params(colors=TEXT)
    ax.yaxis.label.set_color(TEXT)
    ax.xaxis.label.set_color(TEXT)
    ax.title.set_color(TEXT)
    ax.grid(axis='y', alpha=0.25, linestyle='--')

def generate_hr_stats(matched_percentages):
    # Dark-themed histogram with mean indicator
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=140)
    ax.hist(matched_percentages, bins=min(10, max(3, int(len(matched_percentages) ** 0.5) + 2)),
            color=PRIMARY, edgecolor='white', alpha=0.9)
    if matched_percentages:
        mu = sum(matched_percentages) / len(matched_percentages)
        ax.axvline(mu, color=ACCENT, linestyle='--', linewidth=1.5)
        ax.text(mu, ax.get_ylim()[1]*0.9, f"mean {mu:.0f}%", color=ACCENT, ha='center', va='top', fontsize=9)
    ax.set_xlabel('Match Percentage')
    ax.set_ylabel('Candidates')
    ax.set_title('Resume–JD Match Distribution')
    _style_axes(ax)
    fig.patch.set_alpha(0)  # transparent background
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True)
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode()
    plt.close()
    return img_str

def generate_user_progress_chart(applied_jobs, completed_courses):
    # Donut chart with dark theme
    fig, ax = plt.subplots(figsize=(4.8, 4.0), dpi=140)
    vals = [max(applied_jobs, 0), max(completed_courses, 0)]
    labels = ['Jobs Applied', 'Courses Completed']
    colors = [PRIMARY, ACCENT]
    if sum(vals) == 0:
        vals = [1]
        labels = ['No activity']
        colors = ['#253049']
    wedges, _texts, autotexts = ax.pie(vals, labels=labels, colors=colors,
                                      autopct='%1.0f%%', pctdistance=0.75,
                                      textprops={'color': TEXT})
    centre_circle = plt.Circle((0, 0), 0.55, fc=BG)
    fig.gca().add_artist(centre_circle)
    for a in autotexts:
        a.set_color('#0b1220')
        a.set_fontweight('bold')
    ax.set_aspect('equal')
    fig.patch.set_alpha(0)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True)
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode()
    plt.close()
    return img_str
# --- End: dashboard.py ---
