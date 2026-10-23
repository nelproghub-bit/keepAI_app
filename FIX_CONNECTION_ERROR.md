# Fix: "Connection error. Please make sure the backend server is running"

## 🔴 Error Message

```
⚠️ Connection error. Please make sure the backend server 
   is running on port 8000. Run: start_backend.bat
```

## ✅ Quick Fix (3 Steps)

### Step 1: Start the Backend Server

**Option A: Double-click the batch file**
```
📁 In File Explorer, double-click:
   start_backend.bat
```

**Option B: Run from Command Prompt**
```bash
cd c:\xampp\htdocs\keepAI_app
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Option C: Run from PowerShell**
```powershell
cd c:\xampp\htdocs\keepAI_app
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Step 2: Wait for Success Message

You should see:
```
🚀 Starting KeepAI Training-Enhanced System...
[KeepAI] Connected to database
✅ KeepAI Ready!
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### Step 3: Refresh Your Browser

Go back to `student_portal.html` and try again!

---

## 🔍 Verify Backend is Running

### Method 1: Open in Browser
```
http://127.0.0.1:8000/api/health
```

**Should show:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Method 2: Use Curl (Command Prompt)
```bash
curl http://127.0.0.1:8000/api/health
```

### Method 3: Check the Terminal
Look for:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

## 🐛 Common Issues

### Issue 1: "Python is not installed"

**Error:**
```
'python' is not recognized as an internal or external command
```

**Solution:**
1. Download Python from https://www.python.org/downloads/
2. Install Python 3.8 or higher
3. ✅ Check "Add Python to PATH" during installation
4. Restart Command Prompt
5. Try again

**Verify:**
```bash
python --version
```

Should show: `Python 3.x.x`

---

### Issue 2: "Port 8000 is already in use"

**Error:**
```
OSError: [Errno 48] Address already in use
```

**Solution A: Close existing server**
- Find the terminal window with the server
- Press `Ctrl+C` to stop it
- Try starting again

**Solution B: Kill the process (Windows)**
```bash
# Find process using port 8000
netstat -ano | findstr :8000

# Kill it (replace XXXX with PID)
taskkill /PID XXXX /F
```

**Solution C: Use different port**
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Then update `student_portal.html`:
```javascript
const API_BASE = 'http://127.0.0.1:8001/api';
```

---

### Issue 3: "ModuleNotFoundError: No module named 'fastapi'"

**Error:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution: Install dependencies**
```bash
cd c:\xampp\htdocs\keepAI_app
pip install -r requirements.txt
```

Wait for installation to complete, then try again.

---

### Issue 4: Database Connection Error

**Error:**
```
❌ MySQL/MariaDB connection error
```

**Solution A: Using SQLite (Easiest)**
1. The app will automatically use SQLite if MySQL fails
2. No additional setup needed
3. Database file: `data/keepai.db`

**Solution B: Start MySQL/MariaDB**
```bash
# Using XAMPP
1. Open XAMPP Control Panel
2. Click "Start" next to MySQL
3. Wait for green "Running" status
4. Try starting backend again
```

**Solution C: Run migration**
```bash
mysql -u root -p keepai < database_schema.sql
mysql -u root -p keepai < migrate_student_dashboard.sql
```

---

## 📋 Complete Startup Checklist

**Before using student portal:**

1. ✅ Python installed and in PATH
   ```bash
   python --version
   ```

2. ✅ Dependencies installed
   ```bash
   pip install -r requirements.txt
   ```

3. ✅ Database ready (MySQL or SQLite)
   - MySQL: XAMPP started
   - SQLite: Automatic

4. ✅ Migration run (first time only)
   ```bash
   mysql -u root -p keepai < database_schema.sql
   mysql -u root -p keepai < migrate_student_dashboard.sql
   ```

5. ✅ Backend server started
   ```bash
   Double-click: start_backend.bat
   OR
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. ✅ Backend health check passes
   ```
   Open: http://127.0.0.1:8000/api/health
   ```

7. ✅ Open student portal
   ```
   Open: student_portal.html
   ```

---

## 🎯 Step-by-Step First Time Setup

### For Absolute Beginners

**1. Check Python**
```bash
# Open Command Prompt (Win+R, type 'cmd', Enter)
python --version
```

If you see `Python 3.x.x` → Good! Continue to step 2.
If not → Install Python from python.org

**2. Navigate to Project**
```bash
cd c:\xampp\htdocs\keepAI_app
```

**3. Install Dependencies**
```bash
pip install -r requirements.txt
```

Wait 1-2 minutes for installation.

**4. Start Backend**
```bash
# Just double-click this file in File Explorer:
start_backend.bat
```

A black window will open with text.

**5. Look for Success Message**
```
✅ KeepAI Ready!
```

**6. Open Student Portal**
```
Right-click student_portal.html → Open with → Chrome/Firefox
```

**7. Try Registration**
Fill the form and submit. It should work now!

---

## 🔄 Every Time Workflow

**Each time you want to use the portal:**

1. **Start Backend** (if not already running)
   ```
   Double-click: start_backend.bat
   ```

2. **Wait for "Ready" message**
   ```
   ✅ KeepAI Ready!
   ```

3. **Open Portal**
   ```
   Open: student_portal.html
   ```

4. **Use Normally**
   - Register students
   - Sign in
   - Create workspaces

5. **When Done**
   - Close browser
   - In backend terminal: Press Ctrl+C
   - Close terminal window

---

## 🧪 Test Backend Connection

**Quick Test Script** (Save as `test_connection.py`):

```python
import requests

print("Testing backend connection...")

try:
    response = requests.get('http://127.0.0.1:8000/api/health', timeout=5)
    if response.status_code == 200:
        print("✅ Backend is running!")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ Backend returned status {response.status_code}")
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to backend")
    print("Solution: Start backend with start_backend.bat")
except Exception as e:
    print(f"❌ Error: {e}")
```

**Run:**
```bash
python test_connection.py
```

---

## 💡 Pro Tips

### Tip 1: Keep Backend Running
Don't close the terminal window while using the portal. The backend needs to stay running.

### Tip 2: Check Backend Terminal
If something fails, look at the backend terminal for error messages.

### Tip 3: Use Two Windows
- **Window 1**: Backend terminal (running server)
- **Window 2**: Browser (student portal)

### Tip 4: Bookmark Health Check
```
http://127.0.0.1:8000/api/health
```

Keep this open in a tab to quickly check if backend is running.

### Tip 5: Auto-start on Windows Boot (Optional)
1. Create shortcut to `start_backend.bat`
2. Press `Win+R`, type `shell:startup`, Enter
3. Move shortcut to Startup folder
4. Backend will start when Windows starts

---

## 📞 Still Not Working?

### Check These:

1. **Firewall blocking port 8000?**
   - Windows Defender → Allow Python
   - Add exception for port 8000

2. **Antivirus blocking?**
   - Temporarily disable
   - Add project folder to exclusions

3. **Wrong directory?**
   ```bash
   # Make sure you're in the right place:
   cd c:\xampp\htdocs\keepAI_app
   dir
   # Should see: app/ folder, requirements.txt, etc.
   ```

4. **Python virtual environment issues?**
   ```bash
   # If using venv:
   .venv\Scripts\activate
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. **Check backend logs**
   - Read terminal output carefully
   - Look for red ERROR messages
   - Share error messages if asking for help

---

## ✅ Success Indicators

**You know it's working when:**

✅ Terminal shows: "✅ KeepAI Ready!"
✅ Health check URL returns JSON
✅ No connection errors in portal
✅ Registration form submits successfully
✅ Login works
✅ Dashboard loads

---

## 🎓 Video Tutorial (Conceptual Steps)

1. 📁 Open File Explorer → Navigate to project
2. 🖱️ Double-click `start_backend.bat`
3. ⏳ Wait for "KeepAI Ready!" message
4. 🌐 Open `student_portal.html` in browser
5. ✏️ Fill registration form
6. ✅ See success message
7. 🔐 Sign in
8. 🎉 Use dashboard!

---

## 📚 Related Files

- **start_backend.bat** - One-click backend startup
- **requirements.txt** - Python dependencies
- **app/main.py** - Backend entry point
- **.env** - Configuration (optional)

---

## 🆘 Emergency Restart

**If everything is broken:**

```bash
# 1. Stop everything
Ctrl+C in all terminals
Close all browsers

# 2. Restart fresh
cd c:\xampp\htdocs\keepAI_app
pip install -r requirements.txt --force-reinstall
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 3. Open portal
Open student_portal.html in new browser window

# 4. Try again
```

---

**Problem solved!** Your backend just needs to be running. Double-click `start_backend.bat` and you're good to go! 🚀
