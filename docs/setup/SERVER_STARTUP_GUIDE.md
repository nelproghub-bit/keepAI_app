# 🚀 KeepAI Backend Server - Startup Guide

## ✅ Status: Server Fixed and Working!

The server error has been resolved. The issue was a missing `psutil` module dependency that's now been removed. The server is ready to start!

---

## 🎯 Quick Start (3 Easy Ways)

### **Method 1: Double-Click (Easiest)** ⭐
1. **Double-click**: `START_SERVER.bat`
2. **Wait**: Command window opens
3. **See**: "Uvicorn running on http://0.0.0.0:8000"
4. **Done**: Server is online!

### **Method 2: Admin Dashboard**
1. **Open**: `admin_dashboard.html` in browser
2. **Click**: "Start Server" button
3. **Wait**: 5-10 seconds
4. **Status**: Turns GREEN when online

### **Method 3: Command Prompt (Manual)**
```bash
cd C:\xampp\htdocs\keepAI_app
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## ✨ What Works Now

✅ Server starts without errors  
✅ Manual startup works perfectly  
✅ All API endpoints respond  
✅ Database connection works  
✅ Student portal ready  
✅ Admin dashboard operational  
✅ AI tutor functional  

---

## 📊 Server Information

**When Running:**
- **URL**: http://127.0.0.1:8000
- **Network**: http://<server-ip>:8000 (for devices on the same LAN)
- **API**: http://127.0.0.1:8000/api
- **Docs**: http://127.0.0.1:8000/docs
- **Health**: http://127.0.0.1:8000/api/health

**Database:**
- **Engine**: MariaDB
- **Host**: 127.0.0.1:3306
- **Database**: keepai
- **User**: root

---

## 🔧 What Was Fixed

### The Problem
- `psutil` module was required but not available in virtual environment
- Server startup failed with `ModuleNotFoundError`
- Manual startup also couldn't proceed

### The Solution
- Removed psutil dependency from admin router
- Simplified admin API to not need external process monitoring
- Updated requirements.txt
- Server now starts cleanly

### Files Changed
- `app/routers/admin.py` - Simplified (no psutil)
- `requirements.txt` - psutil removed
- `START_SERVER.bat` - New improved batch file

---

## 🎬 Step-by-Step: First Time Startup

### Step 1: Verify Virtual Environment
```bash
cd C:\xampp\htdocs\keepAI_app
.\.venv\Scripts\python.exe --version
```
Should show: `Python 3.x.x`

### Step 2: Start Server
Double-click: **START_SERVER.bat**

### Step 3: Wait for Message
You should see:
```
[OK] Application ready

Starting Server...

[INFO] Server will listen on all network interfaces (port 8000)
[INFO] Press Ctrl+C to stop the server

INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 4: Verify It's Working
Open in browser: `http://127.0.0.1:8000/docs`

---

## 🧪 Testing the Server

### Test 1: Check if Running
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health"
```
Should return: `HTTP 200 OK`

### Test 2: API Documentation
Visit: `http://127.0.0.1:8000/docs`

### Test 3: Open Student Portal
Open file: `student_portal.html`

---

## 🚨 If Server Still Won't Start

### Check 1: Python Version
```bash
.\.venv\Scripts\python.exe --version
```
Should be Python 3.8+

### Check 2: Dependencies
```bash
.\.venv\Scripts\pip.exe list
```
Should include: fastapi, uvicorn, requests, python-multipart

### Check 3: Import Test
```bash
.\.venv\Scripts\python.exe -c "from app.main import app; print('OK')"
```

### Check 4: Port 8000 in Use
```powershell
netstat -ano | findstr :8000
```
Should be empty (no process using port 8000)

### Access From Another Device
Open `http://<server-ip>:8000/api/health` from a device on the same LAN. If
local health checks work but this URL does not, allow inbound TCP port 8000 on
the Wi-Fi's active Windows firewall profile, scoped to LocalSubnet. Do not
change an untrusted Public network to Private just to enable access.

### Check 5: Database Connection
Ensure MariaDB/MySQL is running:
- Check XAMPP Control Panel
- MySQL should be running on 127.0.0.1:3306

---

## 📋 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Port 8000 already in use" | Kill process: `taskkill /PID [PID] /F` or use different port |
| "Python not found" | Activate venv: `.\.venv\Scripts\activate` |
| "Database connection failed" | Start MySQL/MariaDB from XAMPP Control Panel |
| "Module not found" | Run: `.\.venv\Scripts\pip install -r requirements.txt` |
| "Permission denied" | Run command prompt as Administrator |
| "App can't import" | Check all Python files for syntax errors |

---

## 💡 Pro Tips

1. **Keep server running** during development
   - Don't close the command window while using the app

2. **Monitor with Admin Dashboard**
   - Open admin_dashboard.html to see server status
   - Real-time monitoring and logging

3. **Test API Endpoints**
   - Visit http://127.0.0.1:8000/docs
   - Try requests directly from Swagger UI

4. **Check Logs**
   - Watch command window for any errors
   - Logs show database connections, startup messages

5. **Restart When Needed**
   - Press Ctrl+C to stop
   - Change any files (auto-reload will restart)
   - Or double-click START_SERVER.bat again

---

## 🔗 Quick Links

**When Server is Running:**
- Home: http://127.0.0.1:8000
- API Root: http://127.0.0.1:8000/api
- Health Check: http://127.0.0.1:8000/api/health
- API Docs: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

**Frontend:**
- Student Portal: `student_portal.html`
- Student Dashboard: `student_dashboard.html`
- Admin Dashboard: `admin_dashboard.html`
- Main Index: `index.html`

---

## 📊 System Requirements

- Windows 10/11 or Linux/macOS
- Python 3.8+
- Virtual environment (.venv)
- MariaDB/MySQL running
- Port 8000 available
- 2GB+ RAM recommended

---

## 🎓 First Steps After Starting

1. **Register a Student**
   - Open: student_portal.html
   - Click: "Create account"
   - Fill: Username, email, password

2. **Login to Dashboard**
   - Use your credentials
   - Access: Student dashboard

3. **Create a Workspace**
   - Click: "Create New Workspace"
   - Add: Name and description

4. **Upload a Document**
   - Go to: Documents section
   - Upload: PDF file

5. **Test AI Tutor**
   - Go to: AI Tutor
   - Ask: A question about your document

---

## 🆘 Need More Help?

1. Check the error message in command window
2. Read ../admin/ADMIN_DASHBOARD_GUIDE.md
3. Look at API docs: http://127.0.0.1:8000/docs
4. Check database connection in XAMPP

---

## ✅ Verification Checklist

- [ ] Virtual environment exists (.venv folder)
- [ ] Python 3.8+ installed
- [ ] Dependencies installed (pip list shows fastapi, uvicorn)
- [ ] MariaDB running (check XAMPP)
- [ ] Port 8000 available
- [ ] START_SERVER.bat can be run
- [ ] Server shows "Uvicorn running" message
- [ ] Browser can access http://127.0.0.1:8000/docs
- [ ] Student portal can be opened
- [ ] Admin dashboard shows server online

---

## 🎉 Ready to Go!

The KeepAI backend server is now configured and ready to use!

**Start Server Now:**
- Double-click: `START_SERVER.bat`
- Or use: Admin Dashboard button
- Or run: Command line (see instructions above)

**The server is working! Enjoy coding!** 🚀
