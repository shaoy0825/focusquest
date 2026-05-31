import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path(os.getenv("FOCUSQUEST_DB_PATH", Path(__file__).resolve().parent.parent / "focusquest.db"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nickname TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  avatar_base64 TEXT DEFAULT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL DEFAULT 1,
  title TEXT NOT NULL,
  is_main INTEGER NOT NULL DEFAULT 0,
  parent_id INTEGER,
  deadline TEXT,
  priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('high','medium','low')),
  est_minutes INTEGER NOT NULL DEFAULT 0,
  xp INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('todo','done')) DEFAULT 'todo',
  created_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE TABLE IF NOT EXISTS focus_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL DEFAULT 1,
  planned_minutes INTEGER NOT NULL,
  actual_minutes INTEGER NOT NULL,
  distracted INTEGER NOT NULL CHECK(distracted IN (0,1)),
  distraction_minutes INTEGER NOT NULL DEFAULT 0,
  distraction_reason TEXT,
  earned_xp INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS xp_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL,
  amount INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
"""

def now_str():
  return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _ensure_schema(conn):
  conn.executescript(SCHEMA_SQL)

@contextmanager
def get_conn():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  conn.execute("PRAGMA foreign_keys = ON;")
  _ensure_schema(conn)
  try:
    yield conn
    conn.commit()
  finally:
    conn.close()

def init_db():
  DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  with get_conn() as conn:
    _ensure_schema(conn)

def _hash(pw):
  return hashlib.sha256(("focusquest_salt:" + pw).encode()).hexdigest()

# ─── users ───

def create_user(nickname, password):
  try:
    with get_conn() as conn:
      cur = conn.execute("INSERT INTO users(nickname,password_hash,created_at) VALUES (?,?,?)",
                         (nickname, _hash(password), now_str()))
      row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)
  except Exception:
    return None

def verify_user(nickname, password):
  with get_conn() as conn:
    row = conn.execute("SELECT * FROM users WHERE nickname=? AND password_hash=?",
                       (nickname, _hash(password))).fetchone()
  return dict(row) if row else None

def update_avatar(user_id, base64):
  with get_conn() as conn:
    conn.execute("UPDATE users SET avatar_base64=? WHERE id=?", (base64, user_id))

# ─── tasks ───

def _row_to_task(row):
  return {"id":row["id"],"user_id":row["user_id"],"title":row["title"],"is_main":row["is_main"],
          "parent_id":row["parent_id"],"deadline":row["deadline"],"priority":row["priority"],
          "est_minutes":row["est_minutes"],"xp":row["xp"],"status":row["status"],
          "created_at":row["created_at"],"completed_at":row["completed_at"]}

def create_main_task(*, user_id, title, deadline, priority):
  t = now_str()
  with get_conn() as conn:
    cur = conn.execute(
      "INSERT INTO tasks(user_id,title,is_main,parent_id,deadline,priority,est_minutes,xp,status,created_at) VALUES (?,?,1,NULL,?,?,0,100,'todo',?)",
      (user_id, title, deadline, priority, t))
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone()
  return _row_to_task(row)

def create_sub_task(*, parent_id, title, est_minutes):
  t = now_str()
  with get_conn() as conn:
    parent = conn.execute("SELECT user_id FROM tasks WHERE id=?", (parent_id,)).fetchone()
    uid = parent["user_id"] if parent else 1
    cur = conn.execute(
      "INSERT INTO tasks(user_id,title,is_main,parent_id,deadline,priority,est_minutes,xp,status,created_at) VALUES (?,?,0,?,NULL,'medium',?,20,'todo',?)",
      (uid, title, parent_id, est_minutes, t))
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone()
  return _row_to_task(row)

def delete_main_task(task_id):
  with get_conn() as conn:
    conn.execute("DELETE FROM tasks WHERE parent_id=?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

def list_main_tasks_with_subs(user_id):
  with get_conn() as conn:
    mains = conn.execute(
      "SELECT * FROM tasks WHERE is_main=1 AND user_id=? ORDER BY datetime(created_at) DESC,id DESC", (user_id,)).fetchall()
  result = []
  for m in mains:
    main = _row_to_task(m)
    with get_conn() as conn:
      subs = conn.execute("SELECT * FROM tasks WHERE parent_id=? ORDER BY datetime(created_at) ASC", (m["id"],)).fetchall()
    main["subtasks"] = [_row_to_task(s) for s in subs]
    result.append(main)
  return result

def complete_task(task_id):
  ct = now_str()
  with get_conn() as conn:
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row or row["status"] == "done":
      return _row_to_task(row) if row else None, 0
    conn.execute("UPDATE tasks SET status='done',completed_at=? WHERE id=?", (ct, task_id))
    updated = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
  earned = 100 if updated["is_main"] else 20
  uid = updated["user_id"]
  _add_xp_event(uid, "task", earned)
  if not updated["is_main"] and updated["parent_id"] is not None:
    pid = updated["parent_id"]
    with get_conn() as conn:
      remaining = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE parent_id=? AND status='todo'", (pid,)).fetchone()["c"]
    if int(remaining) == 0:
      _complete_main_auto(pid)
  return _row_to_task(updated), earned

def _complete_main_auto(task_id):
  ct = now_str()
  with get_conn() as conn:
    row = conn.execute("SELECT * FROM tasks WHERE id=? AND is_main=1", (task_id,)).fetchone()
    if not row or row["status"] == "done":
      return
    conn.execute("UPDATE tasks SET status='done',completed_at=? WHERE id=?", (ct, task_id))
  _add_xp_event(row["user_id"], "task", 100)

def _add_xp_event(user_id, source, amount):
  with get_conn() as conn:
    conn.execute("INSERT INTO xp_events(user_id,source,amount,created_at) VALUES (?,?,?,?)",
                 (user_id, source, amount, now_str()))

def get_xp_total(user_id):
  with get_conn() as conn:
    r = conn.execute("SELECT COALESCE(SUM(amount),0) AS t FROM xp_events WHERE user_id=?", (user_id,)).fetchone()
  return int(r["t"])

# ─── focus ───

def create_focus_session(*, user_id, planned_minutes, actual_minutes, distracted, distraction_minutes, distraction_reason, earned_xp):
  t = now_str()
  with get_conn() as conn:
    conn.execute(
      "INSERT INTO focus_sessions(user_id,planned_minutes,actual_minutes,distracted,distraction_minutes,distraction_reason,earned_xp,started_at,ended_at) VALUES (?,?,?,?,?,?,?,?,?)",
      (user_id, planned_minutes, actual_minutes, 1 if distracted else 0,
       distraction_minutes, distraction_reason, earned_xp, t, t))
  _add_xp_event(user_id, "focus", earned_xp)

# ─── stats ───

def today_done_count(user_id):
  d = date.today().isoformat()
  with get_conn() as conn:
    r = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE user_id=? AND date(completed_at)=? AND status='done'", (user_id, d)).fetchone()
  return int(r["c"])

def today_focus_stats(user_id):
  d = date.today().isoformat()
  with get_conn() as conn:
    f = conn.execute("SELECT COALESCE(SUM(actual_minutes),0) AS m FROM focus_sessions WHERE user_id=? AND date(ended_at)=?", (user_id, d)).fetchone()["m"]
    dist = conn.execute("SELECT COALESCE(SUM(CASE WHEN distracted=1 THEN 1 ELSE 0 END),0) AS c FROM focus_sessions WHERE user_id=? AND date(ended_at)=?", (user_id, d)).fetchone()["c"]
  return int(f), int(f), int(dist)

def total_focus_minutes(user_id):
  with get_conn() as conn:
    r = conn.execute("SELECT COALESCE(SUM(actual_minutes),0) AS m FROM focus_sessions WHERE user_id=?", (user_id,)).fetchone()
  return int(r["m"])

def total_tasks_done(user_id):
  with get_conn() as conn:
    r = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE user_id=? AND status='done'", (user_id,)).fetchone()
  return int(r["c"])

def main_task_counts(user_id):
  with get_conn() as conn:
    t = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE user_id=? AND is_main=1", (user_id,)).fetchone()["c"]
    d = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE user_id=? AND is_main=1 AND status='done'", (user_id,)).fetchone()["c"]
  return int(t), int(d)

def boss_task(user_id):
  with get_conn() as conn:
    row = conn.execute("SELECT * FROM tasks WHERE user_id=? AND is_main=1 AND priority='high' AND status='todo' ORDER BY datetime(created_at) ASC LIMIT 1", (user_id,)).fetchone()
    if not row:
      row = conn.execute("SELECT * FROM tasks WHERE user_id=? AND is_main=1 AND status='todo' ORDER BY datetime(created_at) ASC LIMIT 1", (user_id,)).fetchone()
  return _row_to_task(row) if row else None

def streak_days(user_id):
  with get_conn() as conn:
    rows = conn.execute("SELECT DISTINCT date(completed_at) AS d FROM tasks WHERE user_id=? AND completed_at IS NOT NULL ORDER BY d DESC", (user_id,)).fetchall()
  days = set(r["d"] for r in rows if r["d"])
  cur = date.today()
  streak = 0
  while cur.isoformat() in days:
    streak += 1
    cur -= timedelta(days=1)
  return streak

def total_distractions(user_id):
  with get_conn() as conn:
    r = conn.execute("SELECT COALESCE(SUM(CASE WHEN distracted=1 THEN 1 ELSE 0 END),0) AS c FROM focus_sessions WHERE user_id=?", (user_id,)).fetchone()
  return int(r["c"])

def last7days_points(user_id):
  end = date.today()
  start = end - timedelta(days=6)
  with get_conn() as conn:
    tasks_r = conn.execute("SELECT date(completed_at) AS d, COUNT(*) AS c FROM tasks WHERE user_id=? AND completed_at IS NOT NULL AND date(completed_at) BETWEEN ? AND ? GROUP BY d", (user_id, start.isoformat(), end.isoformat())).fetchall()
    focus_r = conn.execute("SELECT date(ended_at) AS d, COALESCE(SUM(actual_minutes),0) AS fm, COALESCE(SUM(CASE WHEN distracted=1 THEN 1 ELSE 0 END),0) AS dc FROM focus_sessions WHERE user_id=? AND date(ended_at) BETWEEN ? AND ? GROUP BY d", (user_id, start.isoformat(), end.isoformat())).fetchall()
    xp_r = conn.execute("SELECT date(created_at) AS d, COALESCE(SUM(amount),0) AS xp FROM xp_events WHERE user_id=? AND date(created_at) BETWEEN ? AND ? GROUP BY d", (user_id, start.isoformat(), end.isoformat())).fetchall()
  tm = {r["d"]: int(r["c"]) for r in tasks_r if r["d"]}
  fm = {r["d"]: (int(r["fm"]), int(r["dc"])) for r in focus_r if r["d"]}
  xm = {r["d"]: int(r["xp"]) for r in xp_r if r["d"]}
  points = []
  cur = start
  for _ in range(7):
    d = cur.isoformat()
    fv, dv = fm.get(d, (0, 0))
    points.append({"date": d, "tasks_done": tm.get(d, 0), "focus_minutes": fv, "distraction_count": dv, "xp_earned": xm.get(d, 0)})
    cur += timedelta(days=1)
  return points

def top_distraction_reasons(user_id, limit=5):
  with get_conn() as conn:
    rows = conn.execute("SELECT distraction_reason, COUNT(*) AS cnt FROM focus_sessions WHERE user_id=? AND distracted=1 AND distraction_reason IS NOT NULL AND distraction_reason!='' GROUP BY distraction_reason ORDER BY cnt DESC LIMIT ?", (user_id, limit)).fetchall()
  return [{"reason": r["distraction_reason"], "count": int(r["cnt"])} for r in rows]
