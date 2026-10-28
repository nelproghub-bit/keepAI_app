# 🚀 Admin Dashboard - Quick Start

## Get Started in 3 Steps

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Open Admin Dashboard
Open this file in your browser:
```
admin_dashboard.html
```

Or use a local server:
```bash
python -m http.server 8080
```
Then visit: `http://localhost:8080/admin_dashboard.html`

### Step 3: Start Server with One Click
1. Click the **"Start Server"** button
2. Watch the logs as server starts
3. Status turns **Green ✅** when online
4. Your backend is ready!

---

## 🎯 What You Can Do

### Server Control
- ✅ **Start Server** - Automatic startup
- ✅ **Stop Server** - Graceful shutdown  
- ✅ **Check Status** - Real-time status
- ✅ **View Logs** - Server activity

### Monitoring
- Real-time status (updates every 5 sec)
- Server endpoint: `http://127.0.0.1:8000`
- API docs: `http://localhost:8000/docs`
- System stats: CPU, memory, process info

### Management
- User management
- System settings
- Debug mode toggle
- AI provider selection

---

## ✨ Features

### Automatic Startup
- Detects if server already running
- Starts FastAPI on port 8000
- Shows progress in logs
- Auto-checks every 5 seconds

### Professional Design
- Modern sidebar navigation
- Real-time status badges
- Pulsing online/offline indicators
- Color-coded alerts
- Responsive on mobile

### Cross-Platform
- Windows ✅
- Linux ✅
- macOS ✅

---

## 📖 Full Documentation

See **ADMIN_DASHBOARD_GUIDE.md** for:
- Detailed feature explanations
- Troubleshooting guide
- API endpoint documentation
- Security considerations
- Best practices

---

## 🆘 Troubleshooting

### Server won't start?
1. Check Python: `python --version`
2. Check port 8000: `netstat -ano | findstr :8000`
3. Install psutil: `pip install psutil`
4. Try manual: `python -m uvicorn app.main:app --reload`

### Status shows offline?
1. Click "Check Status" button
2. Refresh the page (F5)
3. Check browser console (F12)
4. Verify port 8000 is available

### Need more help?
- Open browser console (F12) for errors
- Check admin dashboard logs
- Read ADMIN_DASHBOARD_GUIDE.md

---

## 🔗 Important Endpoints

When server is online:
- **API Base**: `http://127.0.0.1:8000/api`
- **API Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/health`
- **Admin Status**: `http://127.0.0.1:8000/api/admin/server/status`

---

**Ready?** Open `admin_dashboard.html` and click "Start Server"! 🎉
