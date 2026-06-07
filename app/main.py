import os
import io
import requests
from requests.exceptions import RequestException
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Date, func, desc
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

REPOS = [r.strip() for r in os.getenv("REPOS", "").split(",") if r.strip()]


def get_github_headers():
    headers = {
        "Accept": "application/vnd.github+json"
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

class Traffic(Base):
    __tablename__ = "traffic"
    id = Column(Integer, primary_key=True)
    repo = Column(String, index=True)
    date = Column(Date, index=True)
    clones = Column(Integer)
    unique_clones = Column(Integer)
    views = Column(Integer)
    unique_views = Column(Integer)

class ReferrerTraffic(Base):
    __tablename__ = "referrer_traffic"
    id = Column(Integer, primary_key=True)
    repo = Column(String, index=True)
    date = Column(Date, index=True)
    referrer = Column(String)
    count = Column(Integer)
    uniques = Column(Integer)

class PathTraffic(Base):
    __tablename__ = "path_traffic"
    id = Column(Integer, primary_key=True)
    repo = Column(String, index=True)
    date = Column(Date, index=True)
    path = Column(String)
    count = Column(Integer)
    uniques = Column(Integer)

Base.metadata.create_all(bind=engine)

def fetch_and_store():
    db = SessionLocal()
    for repo in REPOS:
        try:
            clones_url = f"https://api.github.com/repos/{repo}/traffic/clones"
            views_url = f"https://api.github.com/repos/{repo}/traffic/views"
            referrers_url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"
            paths_url = f"https://api.github.com/repos/{repo}/traffic/popular/paths"

            clones_resp = requests.get(clones_url, headers=get_github_headers())
            views_resp = requests.get(views_url, headers=get_github_headers())
            referrers_resp = requests.get(referrers_url, headers=get_github_headers())
            paths_resp = requests.get(paths_url, headers=get_github_headers())

            clones_data = clones_resp.json() if clones_resp.ok else None
            views_data = views_resp.json() if views_resp.ok else None
            referrers_data = referrers_resp.json() if referrers_resp.ok else None
            paths_data = paths_resp.json() if paths_resp.ok else None

            print(f"[{repo}] Clones status {clones_resp.status_code}: {clones_data}")
            print(f"[{repo}] Views status {views_resp.status_code}: {views_data}")
            print(f"[{repo}] Referrers status {referrers_resp.status_code}: {referrers_data}")
            print(f"[{repo}] Paths status {paths_resp.status_code}: {paths_data}")

            if clones_data is None or views_data is None:
                print(f"Skipping clone/view store for {repo} because GitHub traffic API returned an error.")
            else:
                for c in clones_data.get("clones", []):
                    date = datetime.fromisoformat(c["timestamp"].replace("Z", "")).date()
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

            fetch_date = datetime.utcnow().date()
            if not db.query(ReferrerTraffic).filter_by(repo=repo, date=fetch_date).first():
                if referrers_data is not None:
                    for r in referrers_data.get("referrers", []):
                        db.add(ReferrerTraffic(
                            repo=repo,
                            date=fetch_date,
                            referrer=r.get("referrer"),
                            count=r.get("count", 0),
                            uniques=r.get("uniques", 0)
                        ))
                if paths_data is not None:
                    for p in paths_data.get("paths", []):
                        db.add(PathTraffic(
                            repo=repo,
                            date=fetch_date,
                            path=p.get("path"),
                            count=p.get("count", 0),
                            uniques=p.get("uniques", 0)
                        ))
                db.commit()
        except Exception as e:
            print(f"Error fetching {repo}: {e}")
    db.close()

UPDATE_HOURS = int(os.getenv("UPDATE_HOURS", "24"))
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_store, "interval", hours=UPDATE_HOURS)
scheduler.start()

# Fetch data immediately on startup
try:
    fetch_and_store()
except Exception as e:
    print(f"Initial fetch failed: {e}")

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

templates = Environment(loader=FileSystemLoader("app/templates"))

def require_github_token():
    if not os.getenv("GITHUB_TOKEN"):
        raise HTTPException(status_code=401, detail="GITHUB_TOKEN is required to fetch GitHub traffic data.")


def get_repo_overviews():
    db = SessionLocal()
    rows = db.query(
        Traffic.repo,
        func.coalesce(func.sum(Traffic.clones), 0).label("total_clones"),
        func.coalesce(func.sum(Traffic.views), 0).label("total_views"),
        func.min(Traffic.date).label("first_date"),
        func.max(Traffic.date).label("latest_date")
    ).group_by(Traffic.repo).all()

    overviews = []
    for row in rows:
        latest = None
        if row.latest_date:
            latest = db.query(Traffic).filter(Traffic.repo == row.repo, Traffic.date == row.latest_date).first()
        best_day = db.query(Traffic).filter(Traffic.repo == row.repo).order_by(desc(Traffic.clones)).first()
        day_count = 0
        if row.first_date and row.latest_date:
            day_count = (row.latest_date - row.first_date).days + 1
        overviews.append({
            "repo": row.repo,
            "total_clones": int(row.total_clones),
            "total_views": int(row.total_views),
            "first_date": str(row.first_date) if row.first_date else None,
            "days_tracked": int(day_count),
            "latest_clones": int(latest.clones) if latest else 0,
            "latest_views": int(latest.views) if latest else 0,
            "best_clones": f"{best_day.date} ({best_day.clones})" if best_day else "—"
        })
    db.close()
    return overviews

@app.get("/", response_class=HTMLResponse)
def index():
    return templates.get_template("index.html").render(repo_summaries=get_repo_overviews())

def get_repo_date_range(repo: str):
    db = SessionLocal()
    first_date = db.query(func.min(Traffic.date)).filter(Traffic.repo == repo).scalar()
    latest_date = db.query(func.max(Traffic.date)).filter(Traffic.repo == repo).scalar()
    db.close()
    return first_date, latest_date


@app.get("/repo", response_class=HTMLResponse)
def repo_dashboard(repo: str = None):
    selected_repo = repo if repo in REPOS else (REPOS[0] if REPOS else "")
    first_date, latest_date = (None, None)
    if selected_repo:
        first_date, latest_date = get_repo_date_range(selected_repo)
    return templates.get_template("dashboard.html").render(
        repos=REPOS,
        selected_repo=selected_repo,
        has_github_token=bool(os.getenv("GITHUB_TOKEN")),
        repo_first_date=str(first_date) if first_date else "",
        repo_latest_date=str(latest_date) if latest_date else "",
        static_version=int(datetime.utcnow().timestamp())
    )

@app.get("/config")
def get_config():
    db = SessionLocal()
    repo_data = []
    for repo in REPOS:
        traffic_count = db.query(func.count(Traffic.id)).filter(Traffic.repo == repo).scalar()
        referrer_count = db.query(func.count(ReferrerTraffic.id)).filter(ReferrerTraffic.repo == repo).scalar()
        path_count = db.query(func.count(PathTraffic.id)).filter(PathTraffic.repo == repo).scalar()
        first_date = db.query(func.min(Traffic.date)).filter(Traffic.repo == repo).scalar()
        latest_date = db.query(func.max(Traffic.date)).filter(Traffic.repo == repo).scalar()
        repo_data.append({
            "repo": repo,
            "traffic_rows": int(traffic_count or 0),
            "referrer_rows": int(referrer_count or 0),
            "path_rows": int(path_count or 0),
            "first_date": str(first_date) if first_date else None,
            "latest_date": str(latest_date) if latest_date else None
        })
    db.close()
    return {
        "repo_count": len(REPOS),
        "repos": REPOS,
        "has_github_token": bool(os.getenv("GITHUB_TOKEN")),
        "repo_data": repo_data
    }

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

    data_dict = {r.date: r for r in records}
    
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

@app.get("/summary")
def get_summary(repo: str, start: str, end: str):
    db = SessionLocal()
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()

    range_totals = db.query(
        func.coalesce(func.sum(Traffic.clones), 0),
        func.coalesce(func.sum(Traffic.views), 0)
    ).filter(
        Traffic.repo == repo,
        Traffic.date >= start_date,
        Traffic.date <= end_date
    ).one()

    global_totals = db.query(
        func.coalesce(func.sum(Traffic.clones), 0),
        func.coalesce(func.sum(Traffic.views), 0)
    ).filter(Traffic.repo == repo).one()

    first_date = db.query(func.min(Traffic.date)).filter(Traffic.repo == repo).scalar()
    latest_date = db.query(func.max(Traffic.date)).filter(Traffic.repo == repo).scalar()
    best_day = db.query(Traffic.date, Traffic.clones).filter(
        Traffic.repo == repo,
        Traffic.date >= start_date,
        Traffic.date <= end_date
    ).order_by(desc(Traffic.clones)).first()
    db.close()

    tracked_days = 0
    if first_date and latest_date:
        tracked_days = (latest_date - first_date).days + 1

    return {
        "range": {
            "clones": int(range_totals[0]),
            "views": int(range_totals[1])
        },
        "global": {
            "clones": int(global_totals[0]),
            "views": int(global_totals[1])
        },
        "first_date": str(first_date) if first_date else None,
        "tracked_days": tracked_days,
        "best_day": {
            "date": str(best_day[0]) if best_day else None,
            "clones": int(best_day[1]) if best_day else 0
        }
    }


def fetch_github_list(url):
    try:
        response = requests.get(url, headers=get_github_headers())
    except RequestException as exc:
        print(f"[fetch_github_list] request failed for {url}: {exc}")
        return None

    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        print(f"[fetch_github_list] invalid JSON from {url}, status={response.status_code}, body={text[:200]}")
        return None

    if not response.ok:
        print(f"[fetch_github_list] {url} failed: {response.status_code}, response={data}")
        return None

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data

    print(f"[fetch_github_list] unexpected JSON format from {url}: {type(data).__name__}")
    return None

@app.get("/referrers")
def get_referrers(repo: str, start: str = None, end: str = None):
    db = SessionLocal()
    query = db.query(
        ReferrerTraffic.referrer,
        func.coalesce(func.sum(ReferrerTraffic.count), 0).label("count"),
        func.coalesce(func.sum(ReferrerTraffic.uniques), 0).label("uniques")
    ).filter(ReferrerTraffic.repo == repo)

    if start and end:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        query = query.filter(
            ReferrerTraffic.date >= start_date,
            ReferrerTraffic.date <= end_date
        )

    rows = query.group_by(ReferrerTraffic.referrer).order_by(desc("count")).all()
    if rows:
        result = [
            {"referrer": r.referrer, "count": int(r.count), "uniques": int(r.uniques)}
            for r in rows
        ]
        db.close()
        return result

    if not os.getenv("GITHUB_TOKEN"):
        db.close()
        require_github_token()

    url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"
    data = fetch_github_list(url)
    if data is None:
        db.close()
        raise HTTPException(status_code=502, detail="GitHub referrer fetch failed. Check GITHUB_TOKEN and repo permissions.")

    referrers = data if isinstance(data, list) else data.get("referrers", [])
    fetch_date = datetime.utcnow().date()
    if not db.query(ReferrerTraffic).filter_by(repo=repo, date=fetch_date).first():
        for r in referrers:
            db.add(ReferrerTraffic(
                repo=repo,
                date=fetch_date,
                referrer=r.get("referrer"),
                count=r.get("count", 0),
                uniques=r.get("uniques", 0)
            ))
        db.commit()
    db.close()
    return [
        {"referrer": r.get("referrer"), "count": r.get("count", 0), "uniques": r.get("uniques", 0)}
        for r in referrers
    ]

@app.get("/popular-paths")
def get_popular_paths(repo: str, start: str = None, end: str = None):
    db = SessionLocal()
    query = db.query(
        PathTraffic.path,
        func.coalesce(func.sum(PathTraffic.count), 0).label("count"),
        func.coalesce(func.sum(PathTraffic.uniques), 0).label("uniques")
    ).filter(PathTraffic.repo == repo)

    if start and end:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
        query = query.filter(
            PathTraffic.date >= start_date,
            PathTraffic.date <= end_date
        )

    rows = query.group_by(PathTraffic.path).order_by(desc("count")).all()
    if rows:
        result = [
            {"path": r.path, "count": int(r.count), "uniques": int(r.uniques)}
            for r in rows
        ]
        db.close()
        return result

    if not os.getenv("GITHUB_TOKEN"):
        db.close()
        require_github_token()

    url = f"https://api.github.com/repos/{repo}/traffic/popular/paths"
    data = fetch_github_list(url)
    if data is None:
        db.close()
        raise HTTPException(status_code=502, detail="GitHub path fetch failed. Check GITHUB_TOKEN and repo permissions.")

    paths = data if isinstance(data, list) else data.get("paths", [])
    fetch_date = datetime.utcnow().date()
    if not db.query(PathTraffic).filter_by(repo=repo, date=fetch_date).first():
        for p in paths:
            db.add(PathTraffic(
                repo=repo,
                date=fetch_date,
                path=p.get("path"),
                count=p.get("count", 0),
                uniques=p.get("uniques", 0)
            ))
        db.commit()
    db.close()
    return [
        {"path": p.get("path"), "count": p.get("count", 0), "uniques": p.get("uniques", 0)}
        for p in paths
    ]

@app.post("/fetch-now")
def fetch_now():
    try:
        fetch_and_store()
        return {"status": "fetched"}
    except Exception as e:
        return {"error": str(e), "status": "failed"}
