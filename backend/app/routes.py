from dataclasses import dataclass
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import db as db

# ═══════════════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════════════

class SubTaskCreate(BaseModel):
  title: str
  est_minutes: int = 0

class MainTaskCreate(BaseModel):
  title: str
  deadline: Optional[str] = None
  priority: str = "medium"
  subtasks: List[SubTaskCreate] = []

class TaskOut(BaseModel):
  id: int
  user_id: int = 1
  title: str
  is_main: int
  parent_id: Optional[int] = None
  deadline: Optional[str] = None
  priority: str
  est_minutes: int
  xp: int
  status: str
  created_at: str
  completed_at: Optional[str] = None

class MainTaskWithSubs(TaskOut):
  subtasks: List[TaskOut] = []

class TaskCompleteResponse(BaseModel):
  task: TaskOut
  earned_xp: int
  xp_total: int
  level: int

class FocusSessionCreateRequest(BaseModel):
  planned_minutes: int
  actual_minutes: int
  distracted: bool = False
  distraction_minutes: int = 0
  distraction_reason: Optional[str] = None

class FocusSessionCreateResponse(BaseModel):
  earned_xp: int
  xp_total: int
  level: int

class LevelProgressOut(BaseModel):
  current_level_xp_floor: int
  next_level_xp_floor: int
  into_level_xp: int
  needed_in_level_xp: int

class DashboardResponse(BaseModel):
  done_today: int
  focus_today: int
  distractions_today: int
  level: int
  xp_total: int
  level_progress: LevelProgressOut
  streak_days: int
  total_focus_minutes: int
  total_tasks_done: int
  main_total: int
  main_done: int
  completion_rate: float
  boss_task: Optional[dict] = None
  points_7days: List[dict]
  top_distractions: List[dict]

class ProfileResponse(BaseModel):
  xp_total: int
  level: int
  streak_days: int
  total_focus_minutes: int
  total_tasks_done: int
  total_distractions: int
  level_progress: LevelProgressOut

class RegisterRequest(BaseModel):
  nickname: str
  password: str

class LoginRequest(BaseModel):
  nickname: str
  password: str

class AuthResponse(BaseModel):
  user_id: int
  nickname: str
  avatar_base64: Optional[str] = None
  xp_total: int = 0
  level: int = 1
  streak_days: int = 0

class AvatarUpdateRequest(BaseModel):
  user_id: int
  avatar_base64: str


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LevelProgress:
  level: int
  current_level_xp_floor: int
  next_level_xp_floor: int
  into_level_xp: int
  needed_in_level_xp: int

THRESHOLDS = [
  (1, 0),
  (2, 100),
  (3, 300),
  (4, 600),
  (5, 1000),
  (6, 1500),
  (7, 2200),
  (8, 3000),
]

def get_level_progress(xp_total: int) -> LevelProgress:
  xp = max(0, int(xp_total))
  sorted_thresholds = sorted(THRESHOLDS, key=lambda x: x[1])
  current_level, current_floor = sorted_thresholds[0]
  for level, floor in sorted_thresholds:
    if xp >= floor:
      current_level, current_floor = level, floor
  idx = next((i for i, (lvl, _) in enumerate(sorted_thresholds) if lvl == current_level), 0)
  if idx + 1 < len(sorted_thresholds):
    next_floor = sorted_thresholds[idx + 1][1]
  else:
    next_floor = current_floor + 500
  into = xp - current_floor
  needed = max(1, next_floor - current_floor)
  return LevelProgress(
    level=current_level,
    current_level_xp_floor=current_floor,
    next_level_xp_floor=next_floor,
    into_level_xp=into,
    needed_in_level_xp=needed,
  )


# ═══════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home():
  return r"""<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FocusQuest</title>
<style>
:root{--bg:#f0f4f8;--card:#fff;--text:#1a202c;--muted:#94a3b8;--blue:#3b82f6;--green:#10b981;--red:#ef4444;--amber:#f59e0b;--purple:#8b5cf6;--border:#edf2f7;--shadow:0 1px 3px rgba(0,0,0,.04)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;background:var(--bg);color:var(--text);overflow:hidden;height:100vh}
/* ── Auth Overlay ── */
.auth-overlay{position:fixed;inset:0;z-index:1000;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;align-items:center;justify-content:center;transition:opacity .3s}
.auth-overlay.hidden{opacity:0;pointer-events:none}
.auth-card{background:#fff;border-radius:24px;padding:40px;width:100%;max-width:400px;box-shadow:0 20px 60px rgba(0,0,0,.2);text-align:center}
.auth-card h1{font-size:28px;font-weight:900;margin-bottom:4px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.auth-card .sub{color:#94a3b8;font-size:14px;margin-bottom:28px}
.auth-tabs{display:flex;margin-bottom:24px;background:#f1f5f9;border-radius:12px;padding:4px}
.auth-tab{flex:1;padding:10px;border-radius:10px;font-weight:700;font-size:14px;cursor:pointer;transition:all .15s;color:#64748b;border:0;background:transparent}
.auth-tab.active{background:#fff;color:#1a202c;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.auth-input{width:100%;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;font-size:15px;margin-bottom:12px;outline:none;transition:border-color .15s}
.auth-input:focus{border-color:#3b82f6}
.auth-btn{width:100%;border:0;border-radius:12px;padding:14px;font-weight:700;font-size:15px;cursor:pointer;transition:all .15s;background:#3b82f6;color:#fff;margin-top:8px}
.auth-btn:hover{background:#2563eb}
.auth-btn:disabled{opacity:.6;cursor:not-allowed}
.auth-err{color:#ef4444;font-size:13px;margin-top:8px;min-height:20px}
/* ── Layout ── */
.layout{display:flex;height:100vh}
.sidebar{width:220px;background:#fff;border-right:1px solid var(--border);padding:24px 16px;display:flex;flex-direction:column;gap:2px;z-index:10;box-shadow:2px 0 8px rgba(0,0,0,.02);flex-shrink:0}
.sidebar .brand{font-size:22px;font-weight:900;margin-bottom:20px;padding:0 8px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
/* user pill in sidebar */
.user-pill{display:flex;align-items:center;gap:10px;padding:10px 14px;margin-bottom:16px;cursor:pointer;border-radius:12px;transition:all .15s;border:1px solid transparent}
.user-pill:hover{background:#f8fafc;border-color:#edf2f7}
.user-avatar{width:36px;height:36px;border-radius:50%;object-fit:cover;flex-shrink:0;background:#e2e8f0}
.user-avatar.default{display:flex;align-items:center;justify-content:center;font-size:16px;color:#64748b;background:linear-gradient(135deg,#dbeafe,#ede9fe)}
.user-name{font-weight:700;font-size:14px;color:#1a202c;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav-item{padding:10px 14px;border-radius:10px;color:#4a5568;font-weight:600;font-size:14px;cursor:pointer;transition:all .15s;display:flex;align-items:center;gap:10px}
.nav-item:hover{background:#f1f5f9;color:#1a202c}
.nav-item.active{background:#eff6ff;color:#2563eb}
.main{flex:1;overflow-y:auto;padding:32px;max-width:1100px;margin:0 auto;width:100%}
.card{background:var(--card);border-radius:20px;padding:24px;box-shadow:var(--shadow);border:1px solid var(--border);margin-bottom:20px;transition:transform .15s,box-shadow .15s}
.card:hover{box-shadow:0 4px 12px rgba(0,0,0,.06)}
.card-title{font-size:17px;font-weight:800;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.stat-box{background:linear-gradient(135deg,#f8fafc,#fff);border-radius:16px;padding:22px 18px;text-align:center;border:1px solid var(--border);transition:transform .2s,box-shadow .2s;position:relative;overflow:hidden}
.stat-box::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:16px 16px 0 0}
.stat-box:nth-child(1)::before{background:#3b82f6}
.stat-box:nth-child(2)::before{background:#10b981}
.stat-box:nth-child(3)::before{background:#ef4444}
.stat-box:nth-child(4)::before{background:#8b5cf6}
.stat-box:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.08)}
.stat-value{font-size:34px;font-weight:900;color:var(--text);margin-bottom:6px}
.stat-label{font-size:11px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.8px}
.pill{display:inline-block;font-size:11px;padding:3px 10px;border-radius:999px;font-weight:700}
.boss-card{background:linear-gradient(135deg,#fef3c7,#fef9c3);border:2px solid #f59e0b;border-radius:18px;padding:22px 28px;display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;animation:bossPulse 2s infinite}
@keyframes bossPulse{0%,100%{box-shadow:0 0 0 0 rgba(245,158,11,.4)}50%{box-shadow:0 0 0 10px rgba(245,158,11,0)}}
.btn{border:0;border-radius:12px;padding:10px 20px;font-weight:700;font-size:14px;cursor:pointer;transition:all .15s;font-family:inherit}
.btn.primary{background:var(--blue);color:#fff}
.btn.primary:hover{background:#2563eb;transform:translateY(-1px);box-shadow:0 4px 12px rgba(59,130,246,.3)}
.btn.good{background:var(--green);color:#fff}
.btn.good:hover{background:#059669;transform:translateY(-1px);box-shadow:0 4px 12px rgba(16,185,129,.3)}
.btn.danger{background:var(--red);color:#fff}
.btn.danger:hover{background:#dc2626}
.btn.ghost{background:#f1f5f9;color:#475569}
.btn.ghost:hover{background:#e2e8f0}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none!important;box-shadow:none!important}
.btn-sm{padding:6px 14px;font-size:12px;border-radius:8px}
input,select,textarea{width:100%;border:1px solid #e2e8f0;border-radius:12px;padding:12px 16px;font-size:14px;font-family:inherit;outline:none;transition:border-color .15s;background:#fff}
input:focus,select:focus,textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.col{display:flex;flex-direction:column;gap:12px}
.view-section{display:none}
.view-section.active{display:block;animation:fadeIn .3s}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.muted{color:var(--muted);font-size:13px}
h2{font-size:28px;font-weight:900;margin-bottom:28px;letter-spacing:-.5px}
/* tasks tree */
.tree-item{border:1px solid var(--border);border-radius:14px;margin-bottom:10px;overflow:hidden;background:#fff;transition:box-shadow .15s}
.tree-item:hover{box-shadow:0 2px 8px rgba(0,0,0,.04)}
.tree-main{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;font-weight:700;transition:background .15s}
.tree-main:hover{background:#fafbfc}
.tree-main.high{border-left:5px solid var(--red)}
.tree-main.medium{border-left:5px solid var(--amber)}
.tree-main.low{border-left:5px solid var(--green)}
.tree-subs{padding:0 20px 16px 36px;display:none;border-top:1px dashed var(--border);background:#fafbfc}
.tree-subs.open{display:block}
.sub-row{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-radius:10px;margin-top:6px;background:#fff;border:1px solid #f1f5f9;transition:all .15s}
.sub-row:hover{border-color:#e2e8f0}
.sub-row.done{opacity:.55;text-decoration:line-through}
.progress-bar{width:100%;height:10px;background:#edf2f7;border-radius:999px;overflow:hidden}
.progress-fill{height:100%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);border-radius:999px;transition:width .4s ease}
/* timer */
.timer-display{font-size:80px;font-weight:900;font-variant-numeric:tabular-nums;text-align:center;margin:8px 0;letter-spacing:-2px;background:linear-gradient(135deg,#1a202c,#4a5568);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.timer-controls{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
/* modal */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:200;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.modal-bg.open{display:flex}
.modal{background:#fff;border-radius:24px;padding:36px;max-width:460px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2)}
.modal h3{font-size:22px;font-weight:800;margin-bottom:24px}
/* achievement */
.ach-row{display:flex;align-items:center;gap:14px;padding:14px 0;border-bottom:1px solid var(--border)}
.ach-row:last-child{border-bottom:0}
.ach-icon{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0}
.toast{position:fixed;top:24px;right:24px;background:#1a202c;color:#fff;padding:14px 24px;border-radius:14px;font-weight:700;font-size:14px;z-index:300;animation:slideIn .3s;display:none;box-shadow:0 8px 32px rgba(0,0,0,.2)}
.toast.open{display:block}
@keyframes slideIn{from{opacity:0;transform:translateX(24px)}to{opacity:1;transform:translateX(0)}}
/* avatar upload modal */
.avatar-options{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.avatar-opt{display:flex;flex-direction:column;align-items:center;gap:8px;padding:20px;border:2px dashed #e2e8f0;border-radius:16px;cursor:pointer;transition:all .15s;text-align:center}
.avatar-opt:hover{border-color:#3b82f6;background:#f8fafc}
.avatar-opt .icon{font-size:32px}
.avatar-opt .label{font-weight:700;font-size:13px;color:#475569}
.camera-feed{width:100%;border-radius:12px;margin-bottom:12px;display:none}
.camera-capture-btn{display:none}
/* ── Bottom Nav (mobile) ── */
.bottom-nav{display:none;position:fixed;bottom:0;left:0;right:0;height:64px;background:#fff;border-top:1px solid var(--border);z-index:50;justify-content:space-around;align-items:center;padding-bottom:env(safe-area-inset-bottom,0);box-shadow:0 -2px 10px rgba(0,0,0,.04)}
.bottom-nav .bn-item{display:flex;flex-direction:column;align-items:center;gap:3px;padding:6px 0;color:#94a3b8;font-size:10px;font-weight:700;cursor:pointer;transition:color .15s;border:0;background:none;min-width:60px}
.bottom-nav .bn-item .bn-icon{font-size:20px;line-height:1}
.bottom-nav .bn-item.active{color:#2563eb}
/* ── MOBILE RESPONSIVE ── */
@media(max-width:768px){
  body{overflow-x:hidden}
  .layout{flex-direction:column}
  .sidebar{display:none!important}
  .mobile-header{display:flex!important}
  .bottom-nav{display:flex}
  .main{padding:16px;padding-bottom:80px;max-width:100%}
  h2{font-size:22px;margin-bottom:18px}
  .grid-4{grid-template-columns:repeat(2,1fr);gap:10px}
  .grid-2{grid-template-columns:1fr;gap:12px}
  .stat-box{padding:16px 12px}
  .stat-value{font-size:26px}
  .stat-label{font-size:10px}
  .card{padding:16px;border-radius:14px;margin-bottom:14px}
  .card-title{font-size:15px;margin-bottom:12px}
  .timer-display{font-size:52px;letter-spacing:-1px}
  .timer-controls{gap:8px}
  .timer-controls .btn{padding:10px 18px!important;font-size:14px!important}
  .boss-card{flex-direction:column;text-align:center;gap:10px;padding:16px 20px}
  .tree-main{flex-direction:column;align-items:flex-start;gap:10px;padding:12px 14px}
  .tree-main .row{width:100%;justify-content:flex-end}
  .tree-subs{padding:0 12px 12px 24px}
  .auth-card{margin:0 16px;padding:28px 20px}
  .auth-card h1{font-size:24px}
  .modal{padding:24px;margin:0 12px}
  .toast{left:12px;right:12px;top:auto;bottom:80px;text-align:center}
  .row{gap:8px}
  .btn{padding:8px 14px;font-size:13px}
  .btn-sm{padding:5px 10px;font-size:11px}
  input,select{padding:10px 12px;font-size:13px}
 }
</style>
</head>
<body>

<!-- AUTH OVERLAY -->
<div class="auth-overlay" id="auth-overlay">
  <div class="auth-card">
    <h1>FocusQuest</h1>
    <div class="sub">AI ADHD Survival Dashboard</div>
    <div class="auth-tabs">
      <button class="auth-tab active" id="tab-login" onclick="switchAuthTab('login')">登录</button>
      <button class="auth-tab" id="tab-register" onclick="switchAuthTab('register')">注册</button>
    </div>
    <div id="login-form">
      <input class="auth-input" id="login-nickname" placeholder="昵称" autocomplete="username">
      <input class="auth-input" id="login-password" type="password" placeholder="密码" autocomplete="current-password">
      <button class="auth-btn" id="login-btn" onclick="doLogin()">登录</button>
    </div>
    <div id="register-form" style="display:none">
      <input class="auth-input" id="reg-nickname" placeholder="昵称" autocomplete="username">
      <input class="auth-input" id="reg-password" type="password" placeholder="密码（至少3位）" autocomplete="new-password">
      <button class="auth-btn" id="reg-btn" onclick="doRegister()">注册</button>
    </div>
    <div class="auth-err" id="auth-err"></div>
  </div>
</div>

<!-- MAIN APP -->
<div class="layout" id="app-layout" style="display:none">
  <div class="sidebar">
    <div class="brand">FocusQuest</div>
    <div class="user-pill" onclick="document.getElementById('avatar-modal').classList.add('open')">
      <img class="user-avatar" id="sidebar-avatar" src="" style="display:none" onerror="this.style.display='none';document.getElementById('sidebar-avatar-default').style.display='flex'">
      <div class="user-avatar default" id="sidebar-avatar-default">😊</div>
      <span class="user-name" id="sidebar-nickname">用户</span>
    </div>
    <a class="nav-item active" onclick="switchView('dashboard')">📊 Dashboard</a>
    <a class="nav-item" onclick="switchView('tasks')">📋 Tasks</a>
    <a class="nav-item" onclick="switchView('focus')">⏱️ Focus Mode</a>
    <a class="nav-item" onclick="switchView('profile')">👤 Profile</a>
    <div style="flex:1"></div>
    <a class="nav-item" style="color:#ef4444" onclick="doLogout()">🚪 退出</a>
  </div>
  <div class="main">
    <!-- Mobile Header -->
    <div class="mobile-header" style="display:none;align-items:center;justify-content:space-between;padding:0 4px 14px;gap:12px">
      <div style="font-size:20px;font-weight:900;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent">FocusQuest</div>
      <div style="display:flex;align-items:center;gap:8px">
        <div class="user-pill" style="margin:0;padding:6px 10px" onclick="document.getElementById('avatar-modal').classList.add('open')">
          <img class="user-avatar" id="mh-avatar" src="" style="display:none;width:32px;height:32px" onerror="this.style.display='none';document.getElementById('mh-avatar-default').style.display='flex'">
          <div class="user-avatar default" id="mh-avatar-default" style="width:32px;height:32px;font-size:14px">😊</div>
          <span class="user-name" id="mh-nickname" style="font-size:13px">用户</span>
        </div>
        <span style="color:#ef4444;font-weight:700;font-size:13px;cursor:pointer" onclick="doLogout()">退出</span>
      </div>
    </div>

    <!-- DASHBOARD -->
    <div id="view-dashboard" class="view-section active"><h2>今日概览</h2>
      <div id="boss-area"></div>
      <div class="grid-4" style="margin-bottom:24px">
        <div class="stat-box"><div class="stat-value" id="d-done">--</div><div class="stat-label">今日完成任务</div></div>
        <div class="stat-box"><div class="stat-value" id="d-focus">--</div><div class="stat-label">今日专注时间</div></div>
        <div class="stat-box"><div class="stat-value" style="color:#ef4444" id="d-distract">--</div><div class="stat-label">今日分心次数</div></div>
        <div class="stat-box"><div class="stat-value" style="color:#8b5cf6" id="d-level">--</div><div class="stat-label">当前等级</div></div>
      </div>
      <div class="grid-2" style="margin-bottom:24px">
        <div class="card"><div class="card-title">📈 任务进度</div><canvas id="ring-chart" width="200" height="200" style="display:block;margin:0 auto"></canvas><div style="text-align:center;margin-top:10px;font-weight:700"><span id="main-done-num">0</span> / <span id="main-total-num">0</span> 主任务</div></div>
        <div class="card"><div class="card-title">🔥 专注趋势（近7天）</div><canvas id="focus-line" width="400" height="180" style="width:100%"></canvas></div>
      </div>
      <div class="grid-2" style="margin-bottom:24px">
        <div class="card"><div class="card-title">⚡ 分心次数（近7天）</div><canvas id="dist-bar" width="400" height="180" style="width:100%"></canvas></div>
        <div class="card"><div class="card-title">⭐ XP增长（近7天）</div><canvas id="xp-line" width="400" height="180" style="width:100%"></canvas></div>
      </div>
      <div class="grid-2" style="margin-bottom:24px">
        <div class="card"><div class="card-title">🏆 成就</div>
          <div class="ach-row"><div class="ach-icon" style="background:#fef3c7">🔥</div><div><div style="font-weight:700"><span id="a-streak">0</span> 天</div><div class="muted">连续打卡</div></div></div>
          <div class="ach-row"><div class="ach-icon" style="background:#dbeafe">⏱️</div><div><div style="font-weight:700"><span id="a-focus">0</span> 分钟</div><div class="muted">累计专注</div></div></div>
          <div class="ach-row"><div class="ach-icon" style="background:#d1fae5">✅</div><div><div style="font-weight:700"><span id="a-tasks">0</span> 个</div><div class="muted">累计完成任务</div></div></div>
        </div>
        <div class="card"><div class="card-title">⚠️ 最常见分心原因</div><div id="top-distractions"><div class="muted">暂无数据</div></div></div>
      </div>
    </div>

    <!-- TASKS -->
    <div id="view-tasks" class="view-section"><h2>任务管理</h2>
      <div class="card" style="margin-bottom:24px"><div class="card-title">✨ 创建主任务</div>
        <div class="col" style="gap:10px">
          <input id="main-title" placeholder="任务名称，例如：完成毕业论文">
          <div class="row">
            <input id="main-deadline" type="date" style="flex:1">
            <select id="main-priority" style="flex:1"><option value="high">高优先级</option><option value="medium" selected>中优先级</option><option value="low">低优先级</option></select>
          </div>
          <div id="sub-inputs"></div>
          <div class="row">
            <button class="btn ghost" onclick="addSubInput()">+ 添加分支任务</button>
            <button class="btn primary" style="margin-left:auto" onclick="createMainTask()">创建主任务</button>
          </div>
          <div id="task-create-msg" class="muted"></div>
        </div>
      </div>
      <div id="tasks-tree"><div class="muted" style="text-align:center;padding:40px">加载中...</div></div>
    </div>

    <!-- FOCUS MODE -->
    <div id="view-focus" class="view-section"><h2>专注模式</h2>
      <div class="card" style="text-align:center;padding:40px">
        <div class="row" style="justify-content:center;gap:12px;margin-bottom:32px">
          <button class="btn ghost duration-btn" data-min="15">15分钟</button>
          <button class="btn primary duration-btn" data-min="25">25分钟</button>
          <button class="btn ghost duration-btn" data-min="45">45分钟</button>
          <button class="btn ghost duration-btn" data-min="60">60分钟</button>
        </div>
        <div class="timer-display" id="timer-display">25:00</div>
        <div class="timer-controls">
          <button class="btn primary" id="btn-start" onclick="timerStart()" style="padding:14px 36px;font-size:16px">▶ 开始</button>
          <button class="btn ghost" id="btn-pause" onclick="timerPause()" disabled style="padding:14px 24px">⏸ 暂停</button>
          <button class="btn ghost" id="btn-resume" onclick="timerResume()" style="display:none;padding:14px 24px">▶ 继续</button>
          <button class="btn ghost" id="btn-reset" onclick="timerReset()" style="padding:14px 24px">↺ 重置</button>
        </div>
        <div style="margin-top:36px;border-top:1px solid var(--border);padding-top:28px">
          <button class="btn danger" onclick="openDistractionModal()">⚠️ 我刚刚分心了</button>
        </div>
      </div>
    </div>

    <!-- PROFILE -->
    <div id="view-profile" class="view-section"><h2>个人主页</h2>
      <div class="card" style="text-align:center;padding:44px">
        <div style="position:relative;display:inline-block;cursor:pointer" onclick="document.getElementById('avatar-modal').classList.add('open')">
          <img id="p-avatar-img" style="width:100px;height:100px;border-radius:50%;object-fit:cover;display:none;border:3px solid #3b82f6" onerror="this.style.display='none';document.getElementById('p-avatar-default').style.display='flex'">
          <div id="p-avatar-default" class="user-avatar default" style="width:100px;height:100px;font-size:36px;border-radius:50%;border:3px solid #3b82f6">😊</div>
          <div style="position:absolute;bottom:4px;right:4px;background:#3b82f6;color:#fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:14px;cursor:pointer">📷</div>
        </div>
        <div style="font-size:24px;font-weight:900;margin:16px 0 4px" id="p-nickname">--</div>
        <div style="font-size:36px;font-weight:900;color:var(--purple)" id="p-level">Lv.1</div>
        <div style="font-size:20px;font-weight:800;margin-bottom:16px" id="p-xp">0 XP</div>
        <div class="progress-bar" style="max-width:320px;margin:8px auto 4px"><div class="progress-fill" id="p-progress" style="width:0%"></div></div>
        <div class="muted" id="p-xp-label">0 / 100 XP</div>
      </div>
      <div class="grid-2" style="margin-top:20px">
        <div class="stat-box"><div class="stat-value" id="p-streak">0</div><div class="stat-label">连续打卡天数</div></div>
        <div class="stat-box"><div class="stat-value" id="p-focus">0</div><div class="stat-label">累计专注（分钟）</div></div>
        <div class="stat-box"><div class="stat-value" id="p-tasks">0</div><div class="stat-label">累计完成任务</div></div>
        <div class="stat-box"><div class="stat-value" style="color:#ef4444" id="p-distractions">0</div><div class="stat-label">累计分心次数</div></div>
      </div>
    </div>
  </div>
</div>

<!-- BOTTOM NAV (mobile) -->
<div class="bottom-nav" id="bottom-nav">
  <button class="bn-item active" onclick="switchView('dashboard')"><span class="bn-icon">📊</span>Dashboard</button>
  <button class="bn-item" onclick="switchView('tasks')"><span class="bn-icon">📋</span>Tasks</button>
  <button class="bn-item" onclick="switchView('focus')"><span class="bn-icon">⏱️</span>Focus</button>
  <button class="bn-item" onclick="switchView('profile')"><span class="bn-icon">👤</span>Profile</button>
</div>

<!-- DISTRACTION MODAL -->
<div class="modal-bg" id="distraction-modal">
  <div class="modal"><h3>记录分心</h3>
    <div class="col" style="gap:16px">
      <div><label style="font-weight:700;display:block;margin-bottom:8px;font-size:14px">分心时长</label>
        <select id="dist-minutes"><option value="1">1 分钟 (-2 XP)</option><option value="3">3 分钟 (-5 XP)</option><option value="5">5 分钟 (-10 XP)</option><option value="10">10 分钟 (-20 XP)</option><option value="15">15 分钟 (-30 XP)</option></select></div>
      <div><label style="font-weight:700;display:block;margin-bottom:8px;font-size:14px">分心原因</label>
        <select id="dist-reason"><option value="刷短视频">刷短视频</option><option value="微信聊天">微信聊天</option><option value="淘宝">淘宝</option><option value="看新闻">看新闻</option><option value="发呆">发呆</option><option value="其他">其他</option></select></div>
      <div class="row" style="justify-content:flex-end;gap:10px;margin-top:8px">
        <button class="btn ghost" onclick="document.getElementById('distraction-modal').classList.remove('open')">取消</button>
        <button class="btn danger" onclick="recordDistraction()">确认分心</button>
      </div>
    </div>
  </div>
</div>

<!-- AVATAR MODAL -->
<div class="modal-bg" id="avatar-modal">
  <div class="modal"><h3>设置头像</h3>
    <div class="avatar-options">
      <div class="avatar-opt" onclick="document.getElementById('avatar-file').click()">
        <div class="icon">📁</div><div class="label">上传本地照片</div>
        <input type="file" id="avatar-file" accept="image/*" style="display:none" onchange="handleAvatarFile(this)">
      </div>
      <div class="avatar-opt" onclick="startCamera()">
        <div class="icon">📸</div><div class="label">使用摄像头拍照</div>
      </div>
    </div>
    <video id="camera-feed" class="camera-feed" autoplay playsinline></video>
    <canvas id="camera-canvas" style="display:none"></canvas>
    <button class="btn primary camera-capture-btn" id="camera-capture-btn" onclick="capturePhoto()" style="width:100%;margin-top:12px">📷 拍照</button>
    <div class="row" style="justify-content:flex-end;gap:10px;margin-top:16px">
      <button class="btn ghost" onclick="closeAvatarModal()">取消</button>
      <button class="btn danger" style="font-size:12px" onclick="removeAvatar()">移除头像</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
// ─── STATE ───────────────────────────────────────────────────────────────
let currentUser = null; // {user_id, nickname, avatar_base64}
let authMode = 'login';

function getUserId(){return currentUser?currentUser.user_id:null}

// ─── AUTH ────────────────────────────────────────────────────────────────
function switchAuthTab(mode){
  authMode = mode;
  document.getElementById('tab-login').classList.toggle('active', mode==='login');
  document.getElementById('tab-register').classList.toggle('active', mode==='register');
  document.getElementById('login-form').style.display = mode==='login'?'block':'none';
  document.getElementById('register-form').style.display = mode==='register'?'block':'none';
  document.getElementById('auth-err').textContent='';
}
function authErr(msg){document.getElementById('auth-err').textContent=msg}

async function doLogin(){
  authErr('');
  const n=document.getElementById('login-nickname').value.trim();
  const p=document.getElementById('login-password').value;
  if(!n||!p)return authErr('请填写昵称和密码');
  const btn=document.getElementById('login-btn');btn.disabled=true;btn.textContent='登录中...';
  try{
    const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nickname:n,password:p})});
    if(!r.ok){const e=await r.json();throw new Error(e.detail||'登录失败')}
    const data=await r.json();
    currentUser=data;
    localStorage.setItem('fq_user',JSON.stringify(data));
    showApp();
  }catch(e){authErr(e.message)}
  finally{btn.disabled=false;btn.textContent='登录'}
}
async function doRegister(){
  authErr('');
  const n=document.getElementById('reg-nickname').value.trim();
  const p=document.getElementById('reg-password').value;
  if(!n||!p)return authErr('请填写昵称和密码');
  if(p.length<3)return authErr('密码至少3位');
  const btn=document.getElementById('reg-btn');btn.disabled=true;btn.textContent='注册中...';
  try{
    const r=await fetch('/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nickname:n,password:p})});
    if(!r.ok){const e=await r.json();throw new Error(e.detail||'注册失败')}
    const data=await r.json();
    currentUser=data;
    localStorage.setItem('fq_user',JSON.stringify(data));
    showApp();
  }catch(e){authErr(e.message)}
  finally{btn.disabled=false;btn.textContent='注册'}
}
function showApp(){
  document.getElementById('auth-overlay').classList.add('hidden');
  document.getElementById('app-layout').style.display='flex';
  updateUserUI();
  refreshDashboard();refreshTasks();refreshProfile();
}
function updateUserUI(){
  if(!currentUser)return;
  document.getElementById('sidebar-nickname').textContent=currentUser.nickname;
  document.getElementById('p-nickname').textContent=currentUser.nickname;
  document.getElementById('mh-nickname').textContent=currentUser.nickname;
  if(currentUser.avatar_base64){
    document.getElementById('sidebar-avatar').src=currentUser.avatar_base64;
    document.getElementById('sidebar-avatar').style.display='block';
    document.getElementById('sidebar-avatar-default').style.display='none';
    document.getElementById('mh-avatar').src=currentUser.avatar_base64;
    document.getElementById('mh-avatar').style.display='block';
    document.getElementById('mh-avatar-default').style.display='none';
    document.getElementById('p-avatar-img').src=currentUser.avatar_base64;
    document.getElementById('p-avatar-img').style.display='block';
    document.getElementById('p-avatar-default').style.display='none';
  }
}
function doLogout(){
  localStorage.removeItem('fq_user');
  currentUser=null;
  document.getElementById('auth-overlay').classList.remove('hidden');
  document.getElementById('app-layout').style.display='none';
  document.getElementById('login-nickname').value='';
  document.getElementById('login-password').value='';
}
// try restore session
(function(){
  const saved=localStorage.getItem('fq_user');
  if(saved){
    currentUser=JSON.parse(saved);
    showApp();
  }
})();

// ─── NAVIGATION ──────────────────────────────────────────────────────────
function switchView(v){
  document.querySelectorAll('.view-section').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(e=>{e.classList.remove('active');if(e.textContent.toLowerCase().includes(v)&&!e.textContent.includes('退出'))e.classList.add('active')});
  document.querySelectorAll('.bn-item').forEach(e=>{e.classList.remove('active');if((e.textContent||'').toLowerCase().includes(v))e.classList.add('active')});
  document.getElementById('view-'+v).classList.add('active');
  if(v==='dashboard')refreshDashboard();
  if(v==='tasks')refreshTasks();
  if(v==='profile')refreshProfile();
}

// ─── API wrapper ─────────────────────────────────────────────────────────
async function api(path,init){
  const headers={'Content-Type':'application/json'};
  if(currentUser)headers['X-User-Id']=String(currentUser.user_id);
  const r=await fetch(path,Object.assign({headers},init||{}));
  if(!r.ok){const t=await r.text();throw new Error(t)}
  return r.json();
}

// ─── TOAST ───────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg){
  const t=document.getElementById('toast');t.textContent=msg;t.classList.add('open');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('open'),2800);
}

// ─── DASHBOARD ───────────────────────────────────────────────────────────
async function refreshDashboard(){
  if(!currentUser)return;
  try{
    const d=await api('/dashboard');
    document.getElementById('d-done').textContent=d.done_today;
    document.getElementById('d-focus').textContent=d.focus_today+'min';
    document.getElementById('d-distract').textContent=d.distractions_today;
    document.getElementById('d-level').textContent='Lv.'+d.level;
    document.getElementById('main-done-num').textContent=d.main_done;
    document.getElementById('main-total-num').textContent=d.main_total;
    document.getElementById('a-streak').textContent=d.streak_days;
    document.getElementById('a-focus').textContent=d.total_focus_minutes;
    document.getElementById('a-tasks').textContent=d.total_tasks_done;

    const bossArea=document.getElementById('boss-area');
    if(d.boss_task){
      bossArea.innerHTML='<div class="boss-card"><div><div style="font-size:11px;color:#92400e;font-weight:700;letter-spacing:1px">🔥 BOSS 任务</div><div style="font-weight:800;font-size:17px;color:#78350f;margin-top:2px">'+d.boss_task.title+'</div><div class="muted" style="color:#a16207;margin-top:2px">优先级最高 · 未完成 · +100 XP</div></div><span class="pill" style="background:#fef3c7;color:#a16207;font-size:13px;padding:6px 14px">+100 XP</span></div>';
    }else{bossArea.innerHTML=''}

    drawRing(d.main_done,d.main_total);
    const pts=d.points_7days||[];
    drawLine('focus-line',pts.map(p=>p.focus_minutes),pts.map(p=>p.date.slice(5)),'#3b82f6');
    drawBar('dist-bar',pts.map(p=>p.distraction_count),pts.map(p=>p.date.slice(5)),'#ef4444');
    drawLine('xp-line',pts.map(p=>p.xp_earned),pts.map(p=>p.date.slice(5)),'#10b981');

    const td=d.top_distractions||[];
    const tdEl=document.getElementById('top-distractions');
    if(td.length===0){tdEl.innerHTML='<div class="muted" style="padding:20px;text-align:center">暂无数据</div>'}
    else{tdEl.innerHTML=td.map((x,i)=>'<div class="row" style="justify-content:space-between;padding:10px 0;border-bottom:1px solid #f1f5f9"><span style="font-weight:600;font-size:14px">'+(i+1)+'. '+x.reason+'</span><span style="color:#ef4444;font-weight:700">'+x.count+'次</span></div>').join('')}
  }catch(e){console.error(e)}
}
function drawRing(done,total){
  const c=document.getElementById('ring-chart');if(!c)return;
  const ctx=c.getContext('2d');ctx.clearRect(0,0,200,200);
  const cx=100,cy=100,r=70,lw=18;
  ctx.beginPath();ctx.arc(cx,cy,r-lw/2,0,Math.PI*2);ctx.strokeStyle='#edf2f7';ctx.lineWidth=lw;ctx.stroke();
  if(total>0){
    const pct=Math.min(done/total,1);
    const grad=ctx.createLinearGradient(cx-r,cy,cx+r,cy);grad.addColorStop(0,'#3b82f6');grad.addColorStop(1,'#8b5cf6');
    ctx.beginPath();ctx.arc(cx,cy,r-lw/2,-Math.PI/2,-Math.PI/2+pct*Math.PI*2);
    ctx.strokeStyle=grad;ctx.lineWidth=lw;ctx.lineCap='round';ctx.stroke();
  }
  ctx.fillStyle='#1a202c';ctx.font='bold 28px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText(total>0?Math.round(done/total*100)+'%':'0%',cx,cy-4);
  ctx.fillStyle='#94a3b8';ctx.font='12px sans-serif';ctx.fillText('完成率',cx,cy+24);
}
function drawLine(id,vals,labels,color){
  const c=document.getElementById(id);if(!c)return;
  c.width=c.clientWidth*2;c.height=c.clientHeight*2;
  const ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);
  const pad=45,W=c.width-pad*2,H=c.height-pad*2;
  const max=Math.max(...vals,1);
  ctx.strokeStyle=color;ctx.lineWidth=3;ctx.lineJoin='round';ctx.lineCap='round';
  ctx.beginPath();
  vals.forEach((v,i)=>{
    const x=pad+(W/(vals.length-1||1))*i;
    const y=pad+H-(v/max)*H;
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  });
  ctx.stroke();
  vals.forEach((v,i)=>{
    const x=pad+(W/(vals.length-1||1))*i;
    const y=pad+H-(v/max)*H;
    ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fillStyle='#fff';ctx.fill();
    ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
  });
  ctx.fillStyle='#94a3b8';ctx.font='11px sans-serif';ctx.textAlign='center';
  labels.forEach((l,i)=>{const x=pad+(W/(labels.length-1||1))*i;ctx.fillText(l,x,c.height-8)});
}
function drawBar(id,vals,labels,color){
  const c=document.getElementById(id);if(!c)return;
  c.width=c.clientWidth*2;c.height=c.clientHeight*2;
  const ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);
  const pad=45,W=c.width-pad*2,H=c.height-pad*2;
  const max=Math.max(...vals,1);
  const barW=Math.min((W/vals.length)*.55,32);
  vals.forEach((v,i)=>{
    const x=pad+(W/vals.length)*i+(W/vals.length-barW)/2;
    const h=(v/max)*H;
    const grad=ctx.createLinearGradient(x,pad+H,x,pad+H-h);
    grad.addColorStop(0,color);grad.addColorStop(1,color+'88');
    ctx.fillStyle=grad;ctx.beginPath();roundRect(ctx,x,pad+H-h,barW,h,6,6,0,0);ctx.fill();
  });
  ctx.fillStyle='#94a3b8';ctx.font='11px sans-serif';ctx.textAlign='center';
  labels.forEach((l,i)=>{const x=pad+(W/labels.length)*i+W/labels.length/2;ctx.fillText(l,x,c.height-8)});
}
function roundRect(ctx,x,y,w,h,tl,tr,bl,br){
  ctx.beginPath();ctx.moveTo(x+tl,y);ctx.lineTo(x+w-tr,y);ctx.quadraticCurveTo(x+w,y,x+w,y+tr);
  ctx.lineTo(x+w,y+h-br);ctx.quadraticCurveTo(x+w,y+h,x+w-br,y+h);
  ctx.lineTo(x+bl,y+h);ctx.quadraticCurveTo(x,y+h,x,y+h-bl);
  ctx.lineTo(x,y+tl);ctx.quadraticCurveTo(x,y,x+tl,y);ctx.closePath();
}

// ─── TASKS ───────────────────────────────────────────────────────────────
let subInputCount=0;
function addSubInput(){
  subInputCount++;
  const d=document.createElement('div');d.className='row';d.id='sub-row-'+subInputCount;
  d.innerHTML='<input placeholder="分支任务名称" id="sub-title-'+subInputCount+'" style="flex:2"><input placeholder="预计耗时(分钟)" type="number" value="20" id="sub-time-'+subInputCount+'" style="flex:1"><button class="btn danger btn-sm" onclick="document.getElementById(\'sub-row-'+subInputCount+'\').remove()">✕</button>';
  document.getElementById('sub-inputs').appendChild(d);
}
async function createMainTask(){
  const title=document.getElementById('main-title').value.trim();
  if(!title)return toast('请输入任务名称');
  const deadline=document.getElementById('main-deadline').value||null;
  const priority=document.getElementById('main-priority').value;
  const subs=[];
  for(let i=1;i<=subInputCount;i++){
    const st=document.getElementById('sub-title-'+i);
    const sm=document.getElementById('sub-time-'+i);
    if(st&&st.value.trim())subs.push({title:st.value.trim(),est_minutes:parseInt(sm?.value)||0});
  }
  try{
    const r=await api('/tasks/create',{method:'POST',body:JSON.stringify({title,deadline,priority,subtasks:subs})});
    document.getElementById('main-title').value='';
    document.getElementById('main-deadline').value='';
    document.getElementById('sub-inputs').innerHTML='';
    subInputCount=0;
    document.getElementById('task-create-msg').textContent='';
    toast('✅ 主任务创建成功！');
    refreshTasks();refreshDashboard();
  }catch(e){document.getElementById('task-create-msg').textContent='错误: '+String(e.message||e)}
}
async function addSubToMain(mainId){
  const title=prompt('分支任务名称：');if(!title)return;
  const mins=parseInt(prompt('预计耗时(分钟)：','20'))||20;
  try{await api('/tasks/'+mainId+'/subtasks/create',{method:'POST',body:JSON.stringify({title,est_minutes:mins})});refreshTasks();toast('分支任务已添加')}catch(e){toast(e.message)}
}
async function completeTask(id){
  try{const r=await api('/tasks/'+id+'/complete',{method:'POST'});toast('🎉 完成！+'+r.earned_xp+' XP');refreshTasks();refreshDashboard();}catch(e){toast(e.message)}
}
async function deleteTask(id){
  if(!confirm('确定删除此任务及其分支？'))return;
  try{await api('/tasks/'+id+'/delete',{method:'DELETE'});refreshTasks();refreshDashboard();toast('任务已删除')}catch(e){toast(e.message)}
}
function toggleTree(id){
  const el=document.getElementById('subs-'+id);
  const arrow=document.getElementById('arrow-'+id);
  if(el){el.classList.toggle('open');if(arrow)arrow.textContent=el.classList.contains('open')?'▼':'▶'}
}
async function refreshTasks(){
  if(!currentUser)return;
  try{
    const list=await api('/tasks');
    const el=document.getElementById('tasks-tree');
    if(list.length===0){el.innerHTML='<div class="card" style="text-align:center;padding:48px;color:#94a3b8"><div style="font-size:48px;margin-bottom:12px">📋</div><div style="font-weight:700;font-size:16px">还没有任务</div><div class="muted" style="margin-top:4px">创建你的第一个主任务吧！</div></div>';return}
    el.innerHTML=list.map(t=>{
      const subs=t.subtasks||[];
      const doneSubs=subs.filter(s=>s.status==='done').length;
      const priorityClass=t.priority||'medium';
      const hasSubs=subs.length>0;
      return '<div class="tree-item"><div class="tree-main '+priorityClass+'" style="'+(t.status==='done'?'opacity:.55;text-decoration:line-through':'')+'"><div style="display:flex;align-items:center;gap:10px;flex:1;cursor:'+(hasSubs?'pointer':'default')+'" onclick="'+(hasSubs?'toggleTree('+t.id+')':'')+'">'+(hasSubs?'<span id="arrow-'+t.id+'" style="font-size:12px;color:#94a3b8">▶</span>':'')+'<span style="font-size:15px">'+t.title+'</span>'+(t.deadline?'<span class="pill">📅 '+t.deadline+'</span>':'')+'<span class="pill" style="background:'+(t.priority==='high'?'#fee2e2;color:#991b1b':t.priority==='medium'?'#fef3c7;color:#92400e':'#d1fae5;color:#065f46')+'">'+(t.priority==='high'?'高':t.priority==='medium'?'中':'低')+'</span>'+(hasSubs?'<span class="pill" style="background:#e0e7ff;color:#1d4ed8">'+doneSubs+'/'+subs.length+' 分支</span>':'')+'</div><div class="row" style="gap:8px">'+(t.status==='todo'?'<button class="btn good btn-sm" onclick="completeTask('+t.id+')">完成 +100XP</button>':'<span style="color:#10b981;font-weight:700;font-size:18px">✓</span>')+'<button class="btn ghost btn-sm" onclick="addSubToMain('+t.id+')">+分支</button><button class="btn danger btn-sm" onclick="deleteTask('+t.id+')">删除</button></div></div>'+(hasSubs?'<div class="tree-subs" id="subs-'+t.id+'">'+subs.map(s=>'<div class="sub-row'+(s.status==='done'?' done':'')+'"><span>├ '+s.title+'</span><div class="row" style="gap:8px"><span class="muted">⏱️ '+s.est_minutes+'min</span>'+(s.status==='todo'?'<button class="btn good btn-sm" onclick="completeTask('+s.id+')">完成 +20XP</button>':'<span style="color:#10b981;font-weight:700">✓</span>')+'</div></div>').join('')+'</div>':'')+'</div>';
    }).join('');
  }catch(e){console.error(e)}
}

// ─── FOCUS MODE ──────────────────────────────────────────────────────────
let timerSeconds=25*60,timerRunning=false,timerPaused=false,timerInterval=null;
let chosenDuration=25;
document.querySelectorAll('.duration-btn').forEach(b=>{b.addEventListener('click',function(){document.querySelectorAll('.duration-btn').forEach(x=>x.className='btn ghost duration-btn');this.className='btn primary duration-btn';chosenDuration=parseInt(this.dataset.min);timerReset()})});
function timerDisp(){const m=Math.floor(timerSeconds/60),s=timerSeconds%60;return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')}
function updateTimerUI(){document.getElementById('timer-display').textContent=timerDisp()}
function timerStart(){if(timerRunning)return;timerRunning=true;timerPaused=false;document.getElementById('btn-start').disabled=true;document.getElementById('btn-pause').disabled=false;document.getElementById('btn-resume').style.display='none';document.getElementById('btn-pause').style.display='inline-block';timerInterval=setInterval(()=>{if(timerSeconds<=0){timerComplete();return}timerSeconds--;updateTimerUI()},1000)}
function timerPause(){if(!timerRunning||timerPaused)return;timerPaused=true;clearInterval(timerInterval);document.getElementById('btn-pause').style.display='none';document.getElementById('btn-resume').style.display='inline-block'}
function timerResume(){if(!timerPaused)return;timerPaused=false;document.getElementById('btn-pause').style.display='inline-block';document.getElementById('btn-resume').style.display='none';timerInterval=setInterval(()=>{if(timerSeconds<=0){timerComplete();return}timerSeconds--;updateTimerUI()},1000)}
function timerReset(){timerRunning=false;timerPaused=false;clearInterval(timerInterval);timerSeconds=chosenDuration*60;updateTimerUI();document.getElementById('btn-start').disabled=false;document.getElementById('btn-pause').disabled=true;document.getElementById('btn-resume').style.display='none';document.getElementById('btn-pause').style.display='inline-block'}
async function timerComplete(){clearInterval(timerInterval);timerRunning=false;timerPaused=false;timerSeconds=chosenDuration*60;updateTimerUI();document.getElementById('btn-start').disabled=false;document.getElementById('btn-pause').disabled=true;document.getElementById('btn-resume').style.display='none';document.getElementById('btn-pause').style.display='inline-block';try{const r=await api('/focus_sessions',{method:'POST',body:JSON.stringify({planned_minutes:chosenDuration,actual_minutes:chosenDuration,distracted:false,distraction_minutes:0,distraction_reason:null})});toast('🎉 专注完成！+'+r.earned_xp+' XP (总 '+r.xp_total+' XP, Lv.'+r.level+')');if(document.getElementById('view-dashboard').classList.contains('active'))refreshDashboard()}catch(e){toast(e.message)}}
function openDistractionModal(){document.getElementById('distraction-modal').classList.add('open')}
async function recordDistraction(){const mins=parseInt(document.getElementById('dist-minutes').value);const reason=document.getElementById('dist-reason').value;document.getElementById('distraction-modal').classList.remove('open');const penalties={1:2,3:5,5:10,10:20,15:30};const penalty=penalties[mins]||5;try{const r=await api('/focus_sessions',{method:'POST',body:JSON.stringify({planned_minutes:chosenDuration,actual_minutes:chosenDuration,distracted:true,distraction_minutes:mins,distraction_reason:reason})});toast('分心已记录：'+mins+'分钟 · '+reason+' · 惩罚 -'+penalty+' XP');if(document.getElementById('view-dashboard').classList.contains('active'))refreshDashboard()}catch(e){toast(e.message)}}
updateTimerUI();

// ─── PROFILE ─────────────────────────────────────────────────────────────
async function refreshProfile(){
  if(!currentUser)return;
  try{
    const p=await api('/profile');
    updateUserUI();
    document.getElementById('p-level').textContent='Lv.'+p.level;
    document.getElementById('p-xp').textContent=p.xp_total+' XP';
    document.getElementById('p-streak').textContent=p.streak_days;
    document.getElementById('p-focus').textContent=p.total_focus_minutes;
    document.getElementById('p-tasks').textContent=p.total_tasks_done;
    document.getElementById('p-distractions').textContent=p.total_distractions;
    const pp=p.level_progress;
    const pct=pp.needed_in_level_xp>0?(pp.into_level_xp/pp.needed_in_level_xp)*100:100;
    document.getElementById('p-progress').style.width=Math.min(pct,100)+'%';
    document.getElementById('p-xp-label').textContent=pp.into_level_xp+' / '+pp.needed_in_level_xp+' XP';
  }catch(e){console.error(e)}
}

// ─── AVATAR ──────────────────────────────────────────────────────────────
function closeAvatarModal(){
  document.getElementById('avatar-modal').classList.remove('open');
  stopCamera();
}
function handleAvatarFile(input){
  const file=input.files[0];if(!file)return;
  const reader=new FileReader();
  reader.onload=function(e){
    uploadAvatar(e.target.result);
  };
  reader.readAsDataURL(file);
}
let cameraStream=null;
async function startCamera(){
  try{
    const video=document.getElementById('camera-feed');
    cameraStream=await navigator.mediaDevices.getUserMedia({video:{width:320,height:320}});
    video.srcObject=cameraStream;
    video.style.display='block';
    document.getElementById('camera-capture-btn').style.display='block';
  }catch(e){toast('无法访问摄像头：'+e.message)}
}
function stopCamera(){
  if(cameraStream){cameraStream.getTracks().forEach(t=>t.stop());cameraStream=null}
  document.getElementById('camera-feed').style.display='none';
  document.getElementById('camera-capture-btn').style.display='none';
}
function capturePhoto(){
  const video=document.getElementById('camera-feed');
  const canvas=document.getElementById('camera-canvas');
  canvas.width=video.videoWidth||320;canvas.height=video.videoHeight||320;
  canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
  const base64=canvas.toDataURL('image/jpeg',0.85);
  stopCamera();
  uploadAvatar(base64);
}
async function uploadAvatar(base64){
  if(!currentUser)return;
  try{
    const r=await fetch('/auth/avatar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:currentUser.user_id,avatar_base64:base64})});
    if(!r.ok)throw new Error(await r.text());
    currentUser.avatar_base64=base64;
    localStorage.setItem('fq_user',JSON.stringify(currentUser));
    updateUserUI();
    closeAvatarModal();
    toast('头像已更新！');
  }catch(e){toast('上传失败：'+e.message)}
}
async function removeAvatar(){
  if(!currentUser||!confirm('确定移除头像？'))return;
  try{
    await fetch('/auth/avatar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:currentUser.user_id,avatar_base64:''})});
    currentUser.avatar_base64=null;
    localStorage.setItem('fq_user',JSON.stringify(currentUser));
    document.getElementById('sidebar-avatar').style.display='none';
    document.getElementById('sidebar-avatar-default').style.display='flex';
    document.getElementById('p-avatar-img').style.display='none';
    document.getElementById('p-avatar-default').style.display='flex';
    closeAvatarModal();
    toast('头像已移除');
  }catch(e){toast(e.message)}
}

// ─── ENTER KEY ───────────────────────────────────────────────────────────
document.addEventListener('keydown',function(e){
  if(e.key==='Enter'){
    if(!document.getElementById('app-layout').style.display||document.getElementById('app-layout').style.display==='none'){
      if(authMode==='login')doLogin();else doRegister();
    }
  }
});
</script>
</body>
</html>
"""


# ─── AUTH API ─────────────────────────────────────────────────────────────


@router.post("/auth/register")
def register(payload: RegisterRequest):
  if not payload.nickname.strip() or len(payload.nickname.strip()) < 2:
    raise HTTPException(status_code=400, detail="昵称至少2个字符")
  if len(payload.password) < 3:
    raise HTTPException(status_code=400, detail="密码至少3位")
  user = db.create_user(payload.nickname.strip(), payload.password)
  if not user:
    raise HTTPException(status_code=409, detail="昵称已被使用")
  return {
    "user_id": user["id"],
    "nickname": user["nickname"],
    "avatar_base64": user.get("avatar_base64"),
    "xp_total": 0,
    "level": 1,
    "streak_days": 0,
  }


@router.post("/auth/login")
def login(payload: LoginRequest):
  user = db.verify_user(payload.nickname.strip(), payload.password)
  if not user:
    raise HTTPException(status_code=401, detail="昵称或密码错误")
  xp_total = db.get_xp_total(user["id"])
  progress = get_level_progress(xp_total)
  streak = db.streak_days(user["id"])
  return {
    "user_id": user["id"],
    "nickname": user["nickname"],
    "avatar_base64": user.get("avatar_base64"),
    "xp_total": xp_total,
    "level": progress.level,
    "streak_days": streak,
  }


@router.post("/auth/avatar")
def update_avatar_route(payload: AvatarUpdateRequest):
  db.update_avatar(payload.user_id, payload.avatar_base64)
  return {"ok": True}


# ─── USER-ID HELPER ───────────────────────────────────────────────────────


def _uid(x_user_id: str = Header(None)) -> int:
  if not x_user_id:
    raise HTTPException(status_code=401, detail="请先登录")
  return int(x_user_id)


# ─── TASKS API ────────────────────────────────────────────────────────────


@router.post("/tasks/create", response_model=MainTaskWithSubs)
def create_task(payload: MainTaskCreate, user_id: int = Header(None, alias="X-User-Id")):
  uid = _uid(user_id)
  main = db.create_main_task(user_id=uid, title=payload.title, deadline=payload.deadline, priority=payload.priority)
  subs = []
  for st in payload.subtasks:
    sub = db.create_sub_task(parent_id=main["id"], title=st.title, est_minutes=st.est_minutes)
    subs.append(sub)
  main["subtasks"] = subs
  return main


@router.get("/tasks", response_model=list[MainTaskWithSubs])
def get_tasks(user_id: str = Header(None, alias="X-User-Id")):
  uid = _uid(user_id)
  return db.list_main_tasks_with_subs(uid)


@router.post("/tasks/{main_id}/subtasks/create", response_model=TaskOut)
def create_subtask(main_id: int, payload: SubTaskCreate):
  return db.create_sub_task(parent_id=main_id, title=payload.title, est_minutes=payload.est_minutes)


@router.post("/tasks/{task_id}/complete", response_model=TaskCompleteResponse)
def complete_task(task_id: int):
  res = db.complete_task(task_id)
  if not res:
    raise HTTPException(status_code=404, detail="task not found")
  task, earned = res
  uid = task["user_id"]
  xp_total = db.get_xp_total(uid)
  progress = get_level_progress(xp_total)
  return {"task": task, "earned_xp": earned, "xp_total": xp_total, "level": progress.level}


@router.delete("/tasks/{task_id}/delete")
def delete_task(task_id: int):
  db.delete_main_task(task_id)
  return {"ok": True}


# ─── FOCUS API ────────────────────────────────────────────────────────────


@router.post("/focus_sessions", response_model=FocusSessionCreateResponse)
def create_focus_session(payload: FocusSessionCreateRequest, user_id: str = Header(None, alias="X-User-Id")):
  uid = _uid(user_id)
  planned = max(1, int(payload.planned_minutes))
  actual = max(1, int(payload.actual_minutes))
  dist = bool(payload.distracted)
  dist_mins = int(payload.distraction_minutes)
  earned = planned
  if dist:
    penalties = {1: 2, 3: 5, 5: 10, 10: 20, 15: 30}
    penalty = penalties.get(dist_mins, 5)
    earned = max(0, planned - penalty)
  db.create_focus_session(
    user_id=uid, planned_minutes=planned, actual_minutes=actual,
    distracted=dist, distraction_minutes=dist_mins,
    distraction_reason=payload.distraction_reason if dist else None, earned_xp=earned,
  )
  xp_total = db.get_xp_total(uid)
  progress = get_level_progress(xp_total)
  return {"earned_xp": earned, "xp_total": xp_total, "level": progress.level}


# ─── DASHBOARD API ────────────────────────────────────────────────────────


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(user_id: str = Header(None, alias="X-User-Id")):
  uid = _uid(user_id)
  done_today = db.today_done_count(uid)
  focus_today, _, dist_today = db.today_focus_stats(uid)
  xp_total = db.get_xp_total(uid)
  progress = get_level_progress(xp_total)
  main_total, main_done = db.main_task_counts(uid)
  completion_rate = (main_done / main_total) if main_total else 0.0
  points = db.last7days_points(uid)
  top_dist = db.top_distraction_reasons(uid, 5)
  boss = db.boss_task(uid)
  return {
    "done_today": done_today,
    "focus_today": int(focus_today),
    "distractions_today": int(dist_today),
    "level": progress.level,
    "xp_total": xp_total,
    "level_progress": {
      "current_level_xp_floor": progress.current_level_xp_floor,
      "next_level_xp_floor": progress.next_level_xp_floor,
      "into_level_xp": progress.into_level_xp,
      "needed_in_level_xp": progress.needed_in_level_xp,
    },
    "streak_days": db.streak_days(uid),
    "total_focus_minutes": db.total_focus_minutes(uid),
    "total_tasks_done": db.total_tasks_done(uid),
    "main_total": main_total, "main_done": main_done, "completion_rate": completion_rate,
    "boss_task": boss, "points_7days": points, "top_distractions": top_dist,
  }


@router.get("/profile", response_model=ProfileResponse)
def get_profile(user_id: str = Header(None, alias="X-User-Id")):
  uid = _uid(user_id)
  xp_total = db.get_xp_total(uid)
  progress = get_level_progress(xp_total)
  return {
    "xp_total": xp_total, "level": progress.level,
    "streak_days": db.streak_days(uid),
    "total_focus_minutes": db.total_focus_minutes(uid),
    "total_tasks_done": db.total_tasks_done(uid),
    "total_distractions": db.total_distractions(uid),
    "level_progress": {
      "current_level_xp_floor": progress.current_level_xp_floor,
      "next_level_xp_floor": progress.next_level_xp_floor,
      "into_level_xp": progress.into_level_xp,
      "needed_in_level_xp": progress.needed_in_level_xp,
    },
  }


@router.get("/health")
def health():
  return {"ok": True}
