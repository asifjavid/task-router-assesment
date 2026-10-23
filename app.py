from datetime import datetime, timezone
from pathlib import Path
import asyncio, random, sqlite3, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = os.getenv("TASK_ROUTER_DB", str(Path(__file__).with_name("task_router.db")))
RANDOM_SEED = os.getenv("ROUTER_RANDOM_SEED")
if RANDOM_SEED:
    random.seed(int(RANDOM_SEED))

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def log_event(con, task_id, event_type, detail):
    con.execute(
        "INSERT INTO events(task_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
        (task_id, event_type, detail, now())
    )

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            expertise TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            expertise TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            active_assignment_id INTEGER,
            routing_attempts INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            contributor_id INTEGER NOT NULL REFERENCES contributors(id),
            status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            ended_at TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id),
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        count = con.execute("SELECT COUNT(*) FROM contributors").fetchone()[0]
        if count == 0:
            con.executemany(
                "INSERT INTO contributors(name, expertise, active) VALUES (?, ?, 1)",
                [
                    ("Asha Sharma", "finance,data analysis"),
                    ("Rohan Mehta", "healthcare,operations"),
                    ("Mina Khan", "data analysis,operations"),
                    ("Dev Patel", "finance,operations"),
                ],
            )
        con.commit()

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title="Task Router", version="1.0.0", lifespan=lifespan)
static_dir = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    expertise: str = Field(min_length=2, max_length=60)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")

class Intervention(BaseModel):
    contributor_id: int | None = None
    action: str = Field(pattern="^(reassign|cancel|complete|retry)$")
    note: str = Field(default="Operator intervention", max_length=500)

class ContributorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    expertise: str = Field(min_length=2, max_length=200)

@app.get("/", response_class=HTMLResponse)
def home():
    return (static_dir / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"ok": True, "service": "task-router"}

@app.get("/api/contributors")
def contributors():
    with connect() as con:
        rows = con.execute("SELECT * FROM contributors ORDER BY name").fetchall()
        return [dict(r) for r in rows]

@app.post("/api/contributors")
def add_contributor(data: ContributorCreate):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO contributors(name, expertise, active) VALUES (?, ?, 1)",
            (data.name.strip(), data.expertise.lower().strip())
        )
        con.commit()
        return dict(con.execute("SELECT * FROM contributors WHERE id=?", (cur.lastrowid,)).fetchone())

def matching_contributors(con, expertise, exclude_ids=None):
    exclude_ids = exclude_ids or []
    rows = con.execute("SELECT * FROM contributors WHERE active=1 ORDER BY id").fetchall()
    target = {x.strip().lower() for x in expertise.split(",") if x.strip()}
    matches = []
    for row in rows:
        skills = {x.strip().lower() for x in row["expertise"].split(",") if x.strip()}
        if target & skills and row["id"] not in exclude_ids:
            matches.append((len(target & skills), row))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [r for _, r in matches]

@app.post("/api/tasks")
async def create_task(data: TaskCreate):
    stamp = now()
    with connect() as con:
        cur = con.execute(
            """INSERT INTO tasks(title, description, expertise, priority, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
            (data.title.strip(), data.description.strip(), data.expertise.lower().strip(), data.priority, stamp, stamp)
        )
        task_id = cur.lastrowid
        log_event(con, task_id, "task_created", f"Created task '{data.title.strip()}' requiring {data.expertise.lower().strip()}.")
        con.commit()
    # Routing is intentionally asynchronous; the UI can refresh to see the result.
    asyncio.create_task(route_task(task_id))
    return {"id": task_id, "status": "queued", "message": "Task created; routing started."}

async def route_task(task_id):
    # Simulate a real routing engine's 5–20 second response and occasional unresolved request.
    with connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task["status"] in ("cancelled", "completed"):
            return
        con.execute("UPDATE tasks SET status='routing', updated_at=?, routing_attempts=routing_attempts+1 WHERE id=?", (now(), task_id))
        log_event(con, task_id, "routing_started", "Routing request started.")
        con.commit()
        attempt = task["routing_attempts"] + 1

    await asyncio.sleep(random.randint(5, 20))
    # 20% of routing requests remain unresolved, represented explicitly as timed_out.
    if random.random() < 0.20:
        with connect() as con:
            task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if task and task["status"] == "routing":
                con.execute("UPDATE tasks SET status='unresolved', updated_at=? WHERE id=?", (now(), task_id))
                log_event(con, task_id, "routing_unresolved", "No response from routing engine; operator review or retry required.")
                con.commit()
        return

    with connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task["status"] != "routing":
            return
        assigned_ids = [
            r["contributor_id"] for r in con.execute(
                "SELECT contributor_id FROM assignments WHERE task_id=? AND status IN ('active','completed')",
                (task_id,)
            ).fetchall()
        ]
        matches = matching_contributors(con, task["expertise"], assigned_ids)
        if not matches:
            con.execute("UPDATE tasks SET status='unassigned', updated_at=? WHERE id=?", (now(), task_id))
            log_event(con, task_id, "no_match", f"No active contributor matched expertise '{task['expertise']}'.")
        else:
            chosen = matches[0]
            # End any active assignment first to enforce at most one active assignee.
            con.execute("UPDATE assignments SET status='superseded', ended_at=? WHERE task_id=? AND status='active'", (now(), task_id))
            cur = con.execute(
                """INSERT INTO assignments(task_id, contributor_id, status, reason, created_at)
                   VALUES (?, ?, 'active', 'Automatic expertise match', ?)""",
                (task_id, chosen["id"], now())
            )
            con.execute(
                "UPDATE tasks SET status='assigned', active_assignment_id=?, updated_at=? WHERE id=?",
                (cur.lastrowid, now(), task_id)
            )
            log_event(con, task_id, "assigned", f"Automatically assigned to {chosen['name']} (expertise match).")
        con.commit()

@app.get("/api/tasks")
def list_tasks():
    with connect() as con:
        rows = con.execute("""
            SELECT t.*, c.name AS assignee_name, a.status AS assignment_status
            FROM tasks t
            LEFT JOIN assignments a ON a.id=t.active_assignment_id
            LEFT JOIN contributors c ON c.id=a.contributor_id
            ORDER BY t.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    with connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        assignments = con.execute("""
            SELECT a.*, c.name AS contributor_name, c.expertise
            FROM assignments a JOIN contributors c ON c.id=a.contributor_id
            WHERE a.task_id=? ORDER BY a.created_at DESC
        """, (task_id,)).fetchall()
        events = con.execute("SELECT * FROM events WHERE task_id=? ORDER BY created_at DESC, id DESC", (task_id,)).fetchall()
        return {"task": dict(task), "assignments": [dict(r) for r in assignments], "events": [dict(r) for r in events]}

@app.post("/api/tasks/{task_id}/intervene")
async def intervene(task_id: int, data: Intervention):
    with connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        if data.action == "cancel":
            con.execute("UPDATE assignments SET status='cancelled', ended_at=? WHERE task_id=? AND status='active'", (now(), task_id))
            con.execute("UPDATE tasks SET status='cancelled', active_assignment_id=NULL, updated_at=? WHERE id=?", (now(), task_id))
            log_event(con, task_id, "operator_cancelled", data.note)
        elif data.action == "complete":
            if not task["active_assignment_id"]:
                raise HTTPException(409, "Cannot complete a task without an active assignment.")
            con.execute("UPDATE assignments SET status='completed', ended_at=? WHERE id=?", (now(), task["active_assignment_id"]))
            con.execute("UPDATE tasks SET status='completed', active_assignment_id=NULL, updated_at=? WHERE id=?", (now(), task_id))
            log_event(con, task_id, "operator_completed", data.note)
        elif data.action == "reassign":
            if data.contributor_id is None:
                raise HTTPException(400, "contributor_id is required for reassignment.")
            contributor = con.execute("SELECT * FROM contributors WHERE id=? AND active=1", (data.contributor_id,)).fetchone()
            if not contributor:
                raise HTTPException(404, "Active contributor not found.")
            task_skills = {x.strip().lower() for x in task["expertise"].split(",")}
            person_skills = {x.strip().lower() for x in contributor["expertise"].split(",")}
            if not (task_skills & person_skills):
                raise HTTPException(400, "Contributor does not match the task's expertise.")
            con.execute("UPDATE assignments SET status='superseded', ended_at=? WHERE task_id=? AND status='active'", (now(), task_id))
            cur = con.execute(
                "INSERT INTO assignments(task_id, contributor_id, status, reason, created_at) VALUES (?, ?, 'active', ?, ?)",
                (task_id, contributor["id"], "Manual operator reassignment", now())
            )
            con.execute("UPDATE tasks SET status='assigned', active_assignment_id=?, updated_at=? WHERE id=?", (cur.lastrowid, now(), task_id))
            log_event(con, task_id, "operator_reassigned", f"{data.note}. Assigned to {contributor['name']}.")
        elif data.action == "retry":
            if task["status"] not in ("unresolved", "unassigned", "failed", "queued"):
                raise HTTPException(409, "Retry is only available for unresolved, unassigned, failed, or queued tasks.")
            con.execute("UPDATE tasks SET status='queued', updated_at=? WHERE id=?", (now(), task_id))
            log_event(con, task_id, "operator_retry", data.note)
            con.commit()
            asyncio.create_task(route_task(task_id))
            return {"ok": True, "message": "Routing retry started."}
        con.commit()
        return {"ok": True, "message": f"Action '{data.action}' applied."}

@app.post("/api/tasks/{task_id}/decline")
def decline_assignment(task_id: int):
    with connect() as con:
        task = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        if not task["active_assignment_id"]:
            raise HTTPException(409, "Task has no active assignment.")
        assignment = con.execute("SELECT * FROM assignments WHERE id=?", (task["active_assignment_id"],)).fetchone()
        if not assignment or assignment["status"] != "active":
            raise HTTPException(409, "No active assignment to decline.")
        con.execute("UPDATE assignments SET status='declined', ended_at=? WHERE id=?", (now(), assignment["id"]))
        con.execute("UPDATE tasks SET status='unassigned', active_assignment_id=NULL, updated_at=? WHERE id=?", (now(), task_id))
        log_event(con, task_id, "assignment_declined", f"Contributor {assignment['contributor_id']} declined; task can be retried.")
        con.commit()
    return {"ok": True, "message": "Assignment declined. Retry routing or reassign manually."}
