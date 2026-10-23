#   Engineering Assessment Prototype

A small full-stack task routing application built with FastAPI, SQLite, and vanilla JavaScript. It is an assessment prototype, not a production-ready service.

## Features

- Create tasks with expertise, description, and priority.
- Route tasks asynchronously to active contributors with matching expertise.
- Simulate the assessment's 5–20 second routing response and a 20% unresolved-request rate.
- See task status, assignee, creation time, and priority.
- Operator actions: retry unresolved/unassigned tasks, complete or cancel tasks, decline assignments, and manually reassign to a matching contributor.
- Persistent SQLite storage, assignment history, and audit events.
- Add contributors through the UI.
- Basic API test.

## Requirements

- Python 3.10+
- pip

## Run locally

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000.

The database `task_router.db` is created beside `app.py`. To use a different location, set `TASK_ROUTER_DB`.

## Run tests

```bash
pytest -q
```

The routing simulation uses random timing and outcomes. To make the random sequence repeatable during a demo, set `ROUTER_RANDOM_SEED=7` before starting the server. This makes the pseudo-random sequence repeatable, but exact outcomes can still depend on task timing.

## Routing and recovery decisions

1. A task is created with status `queued`; a background routing coroutine changes it to `routing`.
2. After 5–20 seconds, the simulated router either returns a result or remains unresolved. An unresolved result is surfaced as `unresolved` rather than silently hanging forever.
3. Eligible contributors must be active and share at least one expertise tag with the task. A contributor with more matching tags ranks first; ties use contributor ID for deterministic ordering.
4. Only one active assignment is allowed per task. Previous active assignments are ended before a replacement is created.
5. If no eligible contributor exists, the task becomes `unassigned`.
6. A declined assignment becomes `unassigned`, and an operator can retry routing or reassign manually.
7. Manual reassignment validates that the contributor is active and has matching expertise.
8. `completed` and `cancelled` are terminal statuses in this prototype. Each important transition is appended to the event log.
9. The browser refreshes task state periodically, so an operator can see asynchronous completion after refresh.

## Intentional omissions and trade-offs

- Local SQLite and a single-process FastAPI background task are used for easy setup; a production service should use a durable queue/worker, database transactions/locking designed for concurrent workers, and deployment-level monitoring.
- Authentication, authorization, role management, and contributor acceptance workflows are not implemented.
- Contributor availability, workload balancing, deadlines/SLA, notifications, and pagination are omitted.
- The router is a deterministic rule-based simulation, not an AI recommendation engine. It does not call external services.
- The UI is intentionally compact and uses browser prompts/alerts for some feedback.
- The random 20% unresolved simulation represents the assessment's stuck-request scenario. It marks the task `unresolved` so operators can take action rather than leaving an invisible pending request.
- There is no automatic stale-request timeout worker or durable job record; the demo coroutine updates the task directly. A production implementation should persist routing-request IDs and lease/timeout metadata.

## Suggested manual verification

1. Create a task requiring `data analysis`; it should route to a matching contributor after a short delay unless the simulated request is unresolved.
2. Create a task requiring `quantum gardening`; it should become `unassigned`.
3. Click **Retry** on an unresolved/unassigned task.
4. Open **History** and inspect events.
5. On an assigned task, click **Decline**, then retry.
6. Use **History** to manually reassign to a contributor who shares the required expertise.
7. Complete or cancel a task and verify the status and event log.

## Assessment submission checklist

Do not submit this project as finished until you have run it, tested the important paths, and can explain the code yourself.

- [ ] Push this project to a repository you own and paste the repository link into the submission.
- [ ] Record a walkthrough of at most 10 minutes. Show normal routing, unresolved/retry, decline/recovery, manual reassignment, and event history.
- [ ] Attach the real exports from your AI coding-agent sessions. Do not fabricate agent logs.
- [ ] Complete the session map template below with your actual sessions and corrections.
- [ ] Review the repository for secrets, local database files, virtual environments, and build outputs before uploading.

## Session map template (fill with your real work)

- Initial planning/decomposition: [session/tool and what was decided]
- Most important correction/change of direction: [session and what changed]
- Final testing/verification: [session and tests performed]
