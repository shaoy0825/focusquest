# FocusQuest — AI ADHD Survival Dashboard

一个帮助 ADHD 人群提升专注力和任务管理效率的单页生产力工具。

🔗 **公开访问**: [https://focusquest-1pbj.onrender.com](https://focusquest-1pbj.onrender.com)

---

## 功能特性

### 🔐 用户系统
- 昵称 + 密码注册 / 登录
- 头像上传（本地照片 / 摄像头拍照）
- 浏览器端 session 持久化

### 📋 任务管理
- **主任务** + **分支子任务** 树形结构
- 支持优先级（高 / 中 / 低）和截止日期
- 点击展开/折叠子任务、一键完成、一键删除
- 完成主任务 +100 XP，完成子任务 +20 XP
- 所有子任务完成后自动完成主任务

### ⏱️ 专注模式
- 预设时长：15 / 25 / 45 / 60 分钟
- 播放 / 暂停 / 继续 / 重置
- 完成后自动获得 XP
- **分心记录**：记录分心时长和原因（刷短视频、微信等），自动扣减 XP

### 📊 Dashboard 仪表盘
- 今日概览：完成任务数、专注时间、分心次数、当前等级
- **Boss 任务**提醒（最高优先级未完成任务）
- Canvas 绘制的图表：任务进度环形图、专注趋势折线图、分心柱状图、XP 增长折线图
- 成就展示：连续打卡、累计专注、累计完成任务
- 最常见分心原因排行

### 🎮 等级系统
- Lv.1 → Lv.8，通过完成专注和任务获取 XP
- XP 阈值：0 / 100 / 300 / 600 / 1000 / 1500 / 2200 / 3000
- 分心惩罚：1~15 分钟分别扣 2~30 XP
- 进度条可视化升级进度

### 👤 个人主页
- 等级、XP、进度条
- 连续打卡天数、累计专注分钟、累计完成任务、累计分心次数

### 📱 响应式设计
- 桌面端：左侧导航栏
- 移动端（≤768px）：底部导航栏，适配手机布局

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python + FastAPI |
| 数据库 | SQLite |
| 前端 | 内嵌 HTML/CSS/JS（零框架，Canvas 绘图） |
| 部署 | Render |

---

## 项目结构

```
FocusQuest/
├── requirements.txt          # 根目录依赖
├── render.yaml               # Render 部署配置
├── .gitignore
├── README.md
└── backend/
    ├── requirements.txt      # 后端依赖
    └── app/
        ├── main.py           # FastAPI 应用入口
        ├── routes.py         # 所有路由（模型 + 等级 + HTML + API）
        └── db.py             # 数据库（Schema + CRUD + 统计）
```

---

## 本地运行

### 前提条件
- Python 3.10+

### 安装与启动

拿到项目文件夹后，在终端中依次执行以下命令：

```bash
# 1. 进入项目文件夹
cd FocusQuest

# 2. 安装依赖
pip install -r requirements.txt

# 3. 进入 backend 目录并启动服务器
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 **http://localhost:8000** 即可使用。

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 前端页面 |
| `POST` | `/auth/register` | 用户注册 |
| `POST` | `/auth/login` | 用户登录 |
| `POST` | `/auth/avatar` | 更新头像 |
| `POST` | `/tasks/create` | 创建主任务（含子任务） |
| `GET` | `/tasks` | 获取任务列表 |
| `POST` | `/tasks/{id}/complete` | 完成任务 |
| `DELETE` | `/tasks/{id}/delete` | 删除任务 |
| `POST` | `/tasks/{main_id}/subtasks/create` | 添加子任务 |
| `POST` | `/focus_sessions` | 记录专注（含分心） |
| `GET` | `/dashboard` | 仪表盘数据 |
| `GET` | `/profile` | 个人主页数据 |
| `GET` | `/health` | 健康检查 |

---

> ⚠️ 免费 Render 实例 15 分钟无访问会自动休眠，下次首次访问约需 30 秒冷启动。
