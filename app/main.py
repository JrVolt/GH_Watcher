import os
import io
import requests
from datetime import datetime
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.orm import declarative_base, sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from jinja2 import Environment, FileSystemLoader

DATABASE_URL = "sqlite:///./data/data.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPOS = [r.strip() for r in os.getenv("REPOS", "").split(",") if r.strip()]

class Traffic(Base):
    __tablename__ = "traffic"
    id = Column(Integer, primary_key=True)
    repo = Column(String, index=True)
    date = Column(Date, index=True)
    clones = Column(Integer)
    unique_clones = Column(Integer)
    views = Column(Integer)
    unique_views = Column(Integer)

Base.metadata.create_all(bind=engine)

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# def fetch_and_store():
#     db = SessionLocal()
#     for repo in REPOS:
#         clones_url = f"https://api.github.com/repos/{repo}/traffic/clones"
#         views_url = f"https://api.github.com/repos/{repo}/traffic/views"
#         ref_url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"

#         clones_data = requests.get(clones_url, headers=headers).json()
#         views_data = requests.get(views_url, headers=headers).json()

#         for c in clones_data.get("clones", []):
#             date = datetime.fromisoformat(c["timestamp"].replace("Z","")).date()
#             exists = db.query(Traffic).filter_by(repo=repo, date=date).first()
#             if exists:
#                 continue

#             v_match = next((v for v in views_data.get("views", []) if v["timestamp"].startswith(str(date))), None)

#             db.add(Traffic(
#                 repo=repo,
#                 date=date,
#                 clones=c["count"],
#                 unique_clones=c["uniques"],
#                 views=v_match["count"] if v_match else 0,
#                 unique_views=v_match["uniques"] if v_match else 0
#             ))

#     db.commit()
#     db.close()

def fetch_and_store():
    db = SessionLocal()
    for repo in REPOS:
        try:
            clones_url = f"https://api.github.com/repos/{repo}/traffic/clones"
            views_url = f"https://api.github.com/repos/{repo}/traffic/views"

            clones_data = requests.get(clones_url, headers=headers).json()
            views_data = requests.get(views_url, headers=headers).json()
            
            print(f"[{repo}] Clones response: {clones_data}")
            print(f"[{repo}] Views response: {views_data}")

            for c in clones_data.get("clones", []):
                date = datetime.fromisoformat(c["timestamp"].replace("Z","")).date()
                exists = db.query(Traffic).filter_by(repo=repo, date=date).first()
                if exists:
                    continue

                v_match = next((v for v in views_data.get("views", []) if v["timestamp"].startswith(str(date))), None)

                db.add(Traffic(
                    repo=repo,
                    date=date,
                    clones=c["count"],
                    unique_clones=c["uniques"],
                    views=v_match["count"] if v_match else 0,
                    unique_views=v_match["uniques"] if v_match else 0
                ))
                print(f"Added {repo} {date}: clones={c['count']}")

            db.commit()
        except Exception as e:
            print(f"Error fetching {repo}: {e}")
    
    db.close()

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_store, "interval", hours=24)
scheduler.start()

app = FastAPI()
templates = Environment(loader=FileSystemLoader("app/templates"))

@app.get("/", response_class=HTMLResponse)
def index():
    return templates.get_template("index.html").render(repos=REPOS)

@app.get("/data")
def get_data(repo: str, start: str, end: str):
    db = SessionLocal()
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()

    records = db.query(Traffic).filter(
        Traffic.repo == repo,
        Traffic.date >= start_date,
        Traffic.date <= end_date
    ).all()

    # Create dict of existing records
    data_dict = {r.date: r for r in records}
    
    # Fill missing dates with zeros
    result = []
    current = start_date
    while current <= end_date:
        if current in data_dict:
            r = data_dict[current]
            result.append({
                "date": str(r.date),
                "clones": r.clones,
                "unique_clones": r.unique_clones,
                "views": r.views,
                "unique_views": r.unique_views
            })
        else:
            result.append({
                "date": str(current),
                "clones": 0,
                "unique_clones": 0,
                "views": 0,
                "unique_views": 0
            })
        current += timedelta(days=1)
    
    db.close()
    return result

@app.get("/referrers")
def get_referrers(repo: str):
    url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"
    data = requests.get(url, headers=headers).json()
    return JSONResponse(content=data)

@app.get("/popular-paths")
def get_popular_paths(repo: str):
    url = f"https://api.github.com/repos/{repo}/traffic/popular/paths"
    data = requests.get(url, headers=headers).json()
    return JSONResponse(content=data)

@app.post("/fetch-now")
def fetch_now():
    try:
        fetch_and_store()
        return {"status": "fetched"}
    except Exception as e:
        return {"error": str(e), "status": "failed"}

@app.get("/export")
def export_pdf(repo: str, start: str, end: str):
    db = SessionLocal()
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()

    records = db.query(Traffic).filter(
        Traffic.repo == repo,
        Traffic.date >= start_date,
        Traffic.date <= end_date
    ).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("GitHub Traffic Report", styles["Title"]))
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph(f"Repository: {repo}", styles["Normal"]))
    elements.append(Paragraph(f"Period: {start} - {end}", styles["Normal"]))
    elements.append(Spacer(1, 0.5 * inch))

    table_data = [["Date","Clones","Unique Clones","Views","Unique Views"]]
    for r in records:
        table_data.append([str(r.date), r.clones, r.unique_clones, r.views, r.unique_views])

    table = Table(table_data)
    table.setStyle([("BACKGROUND",(0,0),(-1,0),colors.grey),
                    ("GRID",(0,0),(-1,-1),1,colors.black)])

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    db.close()

    return StreamingResponse(buffer, media_type="application/pdf",
        headers={"Content-Disposition":"attachment; filename=report.pdf"})