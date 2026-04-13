from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import datetime

DB = "lsniaca_strefa.db"

app = FastAPI(title="Lśniąca Strefa API")


def connect():
    return sqlite3.connect(DB)


# --- MODELE WEJŚCIA / WYJŚCIA ---


class LoginRequest(BaseModel):
    employee_id: int


class LoginResponse(BaseModel):
    employee_id: int
    name: str


class ObjectOut(BaseModel):
    id: int
    name: str
    client: str
    billing_type: str


class TaskOut(BaseModel):
    id: int
    object_id: Optional[int]
    object_name: Optional[str]
    title: str
    description: Optional[str]
    priority: Optional[str]
    deadline: Optional[str]
    status: str


class AttendanceStartRequest(BaseModel):
    employee_id: int
    object_id: int
    lat: Optional[float] = None
    lon: Optional[float] = None


class AttendanceEndRequest(BaseModel):
    employee_id: int
    lat: Optional[float] = None
    lon: Optional[float] = None


class ChecklistItemStatus(BaseModel):
    item_name: str
    done: bool


class ChecklistSubmitRequest(BaseModel):
    employee_id: int
    object_id: int
    items: List[ChecklistItemStatus]


class IssueCreateRequest(BaseModel):
    employee_id: int
    object_id: int
    description: str
    photo_path: Optional[str] = None


class DashboardOut(BaseModel):
    year: int
    month: int
    total_revenue: float
    total_cost: float
    total_margin: float
    total_margin_pct: float
    open_tasks: int
    open_issues: int
    active_workers: int


# --- POMOCNICZE ---


def calc_month_report(year: int, month: int):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT id, name, billing_type, monthly_rate, ryczalt
        FROM objects
        WHERE active = 1
    """)
    objects = c.fetchall()

    c.execute("""
        SELECT object_id, invoice_sent, invoice_paid, checklist_done
        FROM invoices
        WHERE year = ? AND month = ?
    """, (year, month))
    inv_rows = c.fetchall()
    inv_map = {r[0]: (r[1], r[2], r[3]) for r in inv_rows}

    report = []
    total_revenue = 0.0
    total_cost = 0.0

    for obj in objects:
        obj_id, name, billing_type, rate, ryczalt = obj

        c.execute("""
            SELECT SUM(h.hours), SUM(h.hours * e.hourly_rate)
            FROM hours h
            JOIN employees e ON h.employee_id = e.id
            WHERE h.object_id = ?
              AND strftime('%Y-%m', h.date) = ?
        """, (obj_id, f"{year}-{month:02d}"))

        hours_sum, cost_sum = c.fetchone()
        hours_sum = hours_sum or 0
        cost_sum = cost_sum or 0

        c.execute("""
            SELECT COUNT(DISTINCT date)
            FROM hours
            WHERE object_id = ?
              AND strftime('%Y-%m', date) = ?
        """, (obj_id, f"{year}-{month:02d}"))
        cleanings = c.fetchone()[0] or 0

        if billing_type == "sprzatanie":
            revenue = cleanings * (rate or 0)
        elif billing_type == "ryczalt":
            revenue = ryczalt or 0
        elif billing_type == "jednorazowe":
            revenue = (rate or 0) if cleanings > 0 else 0
        else:
            revenue = 0

        margin = revenue - cost_sum
        margin_pct = (margin / revenue * 100) if revenue > 0 else 0

        inv = inv_map.get(obj_id, (0, 0, 0))
        invoice_sent = bool(inv[0])
        invoice_paid = bool(inv[1])
        checklist_done = bool(inv[2])

        report.append({
            "object_id": obj_id,
            "object": name,
            "billing_type": billing_type,
            "cleanings": cleanings,
            "hours": hours_sum,
            "revenue": revenue,
            "cost": cost_sum,
            "margin": margin,
            "margin_pct": margin_pct,
            "invoice_sent": invoice_sent,
            "invoice_paid": invoice_paid,
            "checklist_done": checklist_done
        })

        total_revenue += revenue
        total_cost += cost_sum

    conn.close()

    total_margin = total_revenue - total_cost
    total_margin_pct = (total_margin / total_revenue * 100) if total_revenue > 0 else 0

    return report, total_revenue, total_cost, total_margin, total_margin_pct


# --- ENDPOINTY ---


@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    conn = connect()
    c = conn.cursor()

    c.execute("SELECT id, name FROM employees WHERE id = ? AND active = 1", (req.employee_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Nieprawidłowy pracownik lub nieaktywny.")

    return LoginResponse(employee_id=row[0], name=row[1])


@app.get("/employee/{employee_id}/objects", response_model=List[ObjectOut])
def get_employee_objects(employee_id: int):
    conn = connect()
    c = conn.cursor()

    # Na razie: wszystkie aktywne obiekty (później można dodać przypisania)
    c.execute("""
        SELECT id, name, client, billing_type
        FROM objects
        WHERE active = 1
    """)
    rows = c.fetchall()
    conn.close()

    return [
        ObjectOut(
            id=r[0],
            name=r[1],
            client=r[2],
            billing_type=r[3]
        )
        for r in rows
    ]


@app.get("/employee/{employee_id}/tasks", response_model=List[TaskOut])
def get_employee_tasks(employee_id: int):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT t.id, t.object_id, o.name, t.title, t.description,
               t.priority, t.deadline, t.status
        FROM tasks t
        LEFT JOIN objects o ON t.object_id = o.id
        WHERE t.employee_id = ? OR t.employee_id IS NULL
        ORDER BY t.status, t.priority DESC, t.deadline
    """, (employee_id,))
    rows = c.fetchall()
    conn.close()

    return [
        TaskOut(
            id=r[0],
            object_id=r[1],
            object_name=r[2],
            title=r[3],
            description=r[4],
            priority=r[5],
            deadline=r[6],
            status=r[7]
        )
        for r in rows
    ]


@app.post("/attendance/start")
def api_start_attendance(req: AttendanceStartRequest):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT id FROM attendance
        WHERE employee_id = ? AND end_time IS NULL
    """, (req.employee_id,))
    row = c.fetchone()

    if row:
        conn.close()
        raise HTTPException(status_code=400, detail="Pracownik ma już aktywną obecność.")

    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        INSERT INTO attendance (employee_id, object_id, start_time, start_lat, start_lon)
        VALUES (?, ?, ?, ?, ?)
    """, (req.employee_id, req.object_id, start_time, req.lat, req.lon))

    conn.commit()
    conn.close()

    return {"status": "ok", "start_time": start_time}


@app.post("/attendance/end")
def api_end_attendance(req: AttendanceEndRequest):
    conn = connect()
    c = conn.cursor()

    c.execute("""
        SELECT id FROM attendance
        WHERE employee_id = ? AND end_time IS NULL
    """, (req.employee_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Brak aktywnej obecności.")

    att_id = row[0]
    end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        UPDATE attendance
        SET end_time = ?, end_lat = ?, end_lon = ?
        WHERE id = ?
    """, (end_time, req.lat, req.lon, att_id))

    conn.commit()
    conn.close()

    return {"status": "ok", "end_time": end_time}


@app.post("/checklist/submit")
def api_submit_checklist(req: ChecklistSubmitRequest):
    conn = connect()
    c = conn.cursor()

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    for item in req.items:
        status = "DONE" if item.done else "NOT_DONE"
        c.execute("""
            INSERT INTO checklist_results (object_id, employee_id, date, item_name, status)
            VALUES (?, ?, ?, ?, ?)
        """, (req.object_id, req.employee_id, today, item.item_name, status))

    conn.commit()
    conn.close()

    return {"status": "ok", "date": today}


@app.post("/issues")
def api_create_issue(req: IssueCreateRequest):
    conn = connect()
    c = conn.cursor()

    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        INSERT INTO issues (object_id, employee_id, description, photo_path, status, created_at, resolved_at)
        VALUES (?, ?, ?, ?, 'OPEN', ?, NULL)
    """, (req.object_id, req.employee_id, req.description, req.photo_path, created_at))

    conn.commit()
    conn.close()

    return {"status": "ok", "created_at": created_at}


@app.get("/dashboard", response_model=DashboardOut)
def api_dashboard():
    today = datetime.datetime.today()
    year = today.year
    month = today.month

    report, total_rev, total_cost, total_margin, total_margin_pct = calc_month_report(year, month)

    conn = connect()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM tasks WHERE status = 'OPEN'")
    open_tasks = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM issues WHERE status = 'OPEN'")
    open_issues = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM attendance WHERE end_time IS NULL")
    active_workers = c.fetchone()[0]

    conn.close()

    return DashboardOut(
        year=year,
        month=month,
        total_revenue=total_rev,
        total_cost=total_cost,
        total_margin=total_margin,
        total_margin_pct=total_margin_pct,
        open_tasks=open_tasks,
        open_issues=open_issues,
        active_workers=active_workers
    )
