# Student Dashboard - Complete Testing Guide

## 📋 Pre-Testing Checklist

Before you start testing, ensure:
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Database server running (MySQL/MariaDB or SQLite)
- [ ] Migration script executed
- [ ] Backend server started

---

## 🚀 Step-by-Step Testing Process

### Step 1: Database Setup & Migration

#### Option A: MySQL/MariaDB

```bash
# Check if MySQL is running
mysql -u root -p -e "SELECT 1;"

# Run the migration
mysql -u root -p keepai < migrate_student_dashboard.sql

# Verify tables were created
mysql -u root -p -e "USE keepai; SHOW TABLES;"
```

**Expected Output:**
```
+---------------------------+
| Tables_in_keepai          |
+---------------------------+
| documents                 |
| student_preferences       |  ← NEW
| student_stats             |
| users                     |
| workspace_documents       |  ← NEW
| workspaces                |  ← NEW
+---------------------------+
```

#### Option B: SQLite (Automatic)

```bash
# SQLite will auto-create tables on first run
# Just verify the database file exists after starting backend
dir data\keepai.db
```

**Verify Role Column Added:**
```bash
mysql -u root -p -e "USE keepai; DESCRIBE users;"
```

Should see `role` column with default value 'student'.

---

### Step 2: Start the Backend

```bash
# Navigate to project directory
cd c:\xampp\htdocs\keepAI_app

# Start the FastAPI server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Expected Console Output:**
```
🚀 Starting KeepAI Training-Enhanced System...
[KeepAI] Connected to MariaDB / MySQL database: 'keepai' at localhost:3306
✅ KeepAI Ready!
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Health Check:**
```bash
# Test basic API connection
curl http://127.0.0.1:8000/

# Expected response:
# {"message":"KeepAI Training-Enhanced API","version":"1.0.0",...}
```

---

### Step 3: Test API Endpoints (Without UI)

#### Test 1: Health Check
```bash
curl http://127.0.0.1:8000/api/health
```
**Expected:** `{"status":"healthy",...}`

#### Test 2: Login and Get Token
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"arnel\",\"password\":\"password123\"}"
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "student_arnel",
    "username": "arnel",
    "email": "arnel.gubi@university.edu",
    "full_name": "Arnel Gubi",
    "student_id": "BSIT 412"
  },
  "stats": {...}
}
```

**Save the token for next tests:**
```bash
# Linux/Mac
export TOKEN="your_token_here"

# Windows PowerShell
$TOKEN="your_token_here"
```

#### Test 3: List Workspaces (Should be empty or have default)
```bash
# Linux/Mac
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/workspaces

# Windows PowerShell
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/workspaces
```

**Expected:** 
```json
{
  "workspaces": [
    {
      "id": "workspace_default_arnel",
      "name": "My Main Workspace",
      "description": "Default study workspace for all courses",
      "color": "#4f46e5",
      "icon": "📚",
      "document_count": 0
    }
  ]
}
```

#### Test 4: Create Workspace
```bash
# Linux/Mac
curl -X POST http://127.0.0.1:8000/api/workspaces \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Workspace","description":"Testing workspace creation","color":"#059669","icon":"💻"}'

# Windows PowerShell (use Invoke-RestMethod)
$headers = @{ "Authorization" = "Bearer $TOKEN"; "Content-Type" = "application/json" }
$body = '{"name":"Test Workspace","description":"Testing workspace creation","color":"#059669","icon":"💻"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/workspaces" -Method POST -Headers $headers -Body $body
```

**Expected:** Returns the created workspace object with an ID.

#### Test 5: Get Student Preferences
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/workspaces/preferences/me
```

**Expected:**
```json
{
  "preferences": {
    "user_id": "student_arnel",
    "theme": "light",
    "ai_tutor_mode": "balanced",
    "show_citations": true,
    "enable_notifications": true,
    "default_workspace_id": null,
    "preferences": {
      "language": "en",
      "timezone": "UTC",
      "study_reminder": true
    }
  }
}
```

#### Test 6: Update Preferences
```bash
curl -X PUT http://127.0.0.1:8000/api/workspaces/preferences/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ai_tutor_mode":"socratic","show_citations":false}'
```

**Expected:** Returns updated preferences.

---

### Step 4: Test Student Dashboard UI

#### Open the Dashboard

**Method 1: Direct File Open**
1. Open Windows Explorer
2. Navigate to `c:\xampp\htdocs\keepAI_app`
3. Double-click `student_dashboard.html`

**Method 2: Local Server (Recommended)**
```bash
# Option A: Python HTTP Server
cd c:\xampp\htdocs\keepAI_app
python -m http.server 8080

# Then open: http://localhost:8080/student_dashboard.html
```

**Method 3: VS Code Live Server**
1. Right-click `student_dashboard.html` in VS Code
2. Select "Open with Live Server"

#### Test 7: Login Flow

1. **Open browser console** (F12) to see any errors
2. **Login with demo credentials:**
   - Username: `arnel`
   - Password: `password123`

**What to Check:**
- ✅ Login form accepts credentials
- ✅ Token is stored in localStorage (check in console: `localStorage.getItem('access_token')`)
- ✅ Redirects to dashboard after login
- ✅ User name displays in top-right ("Arnel Gubi")
- ✅ User avatar shows initials ("AG")

**Console Check:**
```javascript
// Open browser console (F12) and type:
localStorage.getItem('access_token')
// Should return a JWT token string
```

---

### Step 5: Test Workspace Management

#### Test 8: View Workspaces

**What to Check:**
- ✅ "My Workspaces" page loads
- ✅ See default workspace "My Main Workspace"
- ✅ If you created test workspace via API, it should appear
- ✅ Workspace cards show: icon, name, description, document count

**Expected View:**
```
┌─────────────────────┐
│ 📚                  │ ← Icon
│ My Main Workspace   │ ← Name
│ Default study...    │ ← Description
│ 📄 0 documents      │ ← Count
└─────────────────────┘
```

#### Test 9: Create Workspace via UI

1. **Click "Create New Workspace" button**

**What to Check:**
- ✅ Modal dialog opens
- ✅ Form has: Name, Description, Color picker, Icon picker
- ✅ Color picker shows 6 colors
- ✅ Icon picker shows 8 icons
- ✅ Default selections (Blue color, 📚 icon)

2. **Fill out the form:**
   - Name: "Database Systems"
   - Description: "CS 401 - Fall 2024"
   - Color: Click Green (#059669)
   - Icon: Click 💻 (Computer)

3. **Click "Create Workspace"**

**What to Check:**
- ✅ Modal closes
- ✅ Success toast appears ("Workspace created successfully!")
- ✅ New workspace card appears in grid
- ✅ Card shows correct color, icon, name
- ✅ Document count shows 0

**Browser Console Check:**
```javascript
// Should see successful POST request
// Network tab → Look for: POST /api/workspaces (Status: 201)
```

#### Test 10: Create Multiple Workspaces

Create 3-4 more workspaces with different colors and icons:

| Name | Color | Icon | Description |
|------|-------|------|-------------|
| Algorithms | Green | 📊 | CS 302 |
| Web Dev | Purple | 🌐 | CS 410 |
| Machine Learning | Orange | 🤖 | CS 501 |

**What to Check:**
- ✅ All workspaces appear in grid
- ✅ Each has unique color
- ✅ Grid layout is responsive
- ✅ No duplicate workspace IDs

#### Test 11: Edit Workspace

1. **Hover over a workspace card**
2. **Click the edit icon (pencil)**

**Expected:** Edit modal opens (coming soon notification for now)

#### Test 12: Delete Workspace

1. **Click the delete icon (trash) on a test workspace**
2. **Confirm deletion in the dialog**

**What to Check:**
- ✅ Confirmation dialog appears
- ✅ Workspace card disappears after confirmation
- ✅ Success toast shows
- ✅ Other workspaces remain

**Console Check:**
```javascript
// Network tab → Look for: DELETE /api/workspaces/{id} (Status: 200)
```

#### Test 13: Empty State

1. **Delete all workspaces** (leave no workspaces)

**What to Check:**
- ✅ Empty state appears
- ✅ Shows icon and message
- ✅ Suggests creating first workspace
- ✅ Create button still works

---

### Step 6: Test Student Settings

#### Test 14: Navigate to Settings

1. **Click "Student Settings" in sidebar**

**What to Check:**
- ✅ Settings page loads
- ✅ Page title changes to "Student Settings"
- ✅ Settings panel displays
- ✅ All setting sections visible:
  - Appearance
  - AI Tutor Settings
  - Notifications

#### Test 15: Change Theme

1. **Find "Theme" dropdown**
2. **Change from "Light" to "Dark"**
3. **Click "Save Settings"**

**What to Check:**
- ✅ Dropdown shows current selection
- ✅ Can select Dark/Auto
- ✅ Save button is clickable
- ✅ Success toast appears
- ✅ Refresh page → setting persists

**Console Check:**
```javascript
// Network tab → Look for: PUT /api/workspaces/preferences/me
```

#### Test 16: Change AI Tutor Mode

1. **Find "Tutor Mode" dropdown**
2. **Try each option:**
   - Socratic
   - Balanced
   - Direct
   - Academic

3. **Save after each change**

**What to Check:**
- ✅ All 4 modes available
- ✅ Descriptions shown
- ✅ Changes save successfully
- ✅ Settings persist after refresh

#### Test 17: Toggle Citations

1. **Find "Show Citations" toggle**
2. **Click to turn OFF**
3. **Click "Save Settings"**
4. **Refresh page**
5. **Toggle back ON**
6. **Save again**

**What to Check:**
- ✅ Toggle switches smoothly
- ✅ Visual feedback (color change)
- ✅ State persists after save
- ✅ Refresh maintains state

#### Test 18: Toggle Notifications

Same process as Test 17 for notifications toggle.

#### Test 19: Settings Persistence

1. **Change multiple settings:**
   - Theme: Dark
   - Tutor Mode: Socratic
   - Citations: OFF
   - Notifications: ON

2. **Click "Save Settings"**
3. **Close browser completely**
4. **Reopen student_dashboard.html**
5. **Login again**
6. **Go to Settings**

**What to Check:**
- ✅ ALL settings preserved
- ✅ Theme dropdown shows "Dark"
- ✅ Tutor mode shows "Socratic"
- ✅ Citations toggle is OFF
- ✅ Notifications toggle is ON

---

### Step 7: Test Navigation

#### Test 20: Sidebar Navigation

Click each navigation item and verify:

| Page | Expected Behavior |
|------|-------------------|
| My Workspaces | Shows workspace grid |
| Dashboard | Placeholder message |
| Library | Placeholder message |
| AI Tutor | Placeholder message |
| Summaries | Placeholder message |
| Quizzes | Placeholder message |
| Student Settings | Shows settings panel |

**What to Check:**
- ✅ Active page highlighted in sidebar
- ✅ Page title updates in topbar
- ✅ Page subtitle updates
- ✅ Content area changes
- ✅ No console errors

#### Test 21: Refresh Behavior

1. **Navigate to Workspaces page**
2. **Refresh browser (F5)**

**What to Check:**
- ✅ Still logged in (token persists)
- ✅ Workspaces page still active
- ✅ Workspaces load successfully

---

### Step 8: Test Authentication & Security

#### Test 22: Logout and Re-login

1. **Clear localStorage:**
```javascript
// In browser console:
localStorage.removeItem('access_token')
```

2. **Refresh page**

**What to Check:**
- ✅ Redirects to login (or shows auth required)
- ✅ Cannot access workspaces without token
- ✅ API returns 401 Unauthorized

3. **Login again with credentials**

**What to Check:**
- ✅ Can login successfully
- ✅ Token restored
- ✅ Workspaces load

#### Test 23: Invalid Token

1. **Set invalid token:**
```javascript
// In browser console:
localStorage.setItem('access_token', 'invalid_token_12345')
```

2. **Try to load workspaces**

**What to Check:**
- ✅ API returns 401 error
- ✅ Appropriate error handling
- ✅ User sees error message

#### Test 24: Cross-User Access

**Setup:** Create a second user (if possible)

1. **Login as User 1**
2. **Create a workspace, note its ID**
3. **Logout**
4. **Login as User 2**
5. **Try to access User 1's workspace via API:**
```bash
curl -H "Authorization: Bearer $USER2_TOKEN" \
  http://127.0.0.1:8000/api/workspaces/{user1_workspace_id}
```

**What to Check:**
- ✅ Returns 403 Forbidden
- ✅ User 2 cannot see User 1's workspaces
- ✅ Data isolation enforced

---

### Step 9: Test Error Handling

#### Test 25: Empty Workspace Name

1. **Click "Create New Workspace"**
2. **Leave name empty**
3. **Try to create**

**What to Check:**
- ✅ Error toast appears
- ✅ Message: "Please enter a workspace name"
- ✅ Modal stays open
- ✅ No API call made

#### Test 26: Backend Offline

1. **Stop the backend server (Ctrl+C)**
2. **Try to create a workspace**

**What to Check:**
- ✅ Error toast appears
- ✅ Network error handled gracefully
- ✅ No browser crash
- ✅ Console shows connection error

3. **Restart backend**
4. **Try again**

**What to Check:**
- ✅ Works after backend restarts
- ✅ System recovers gracefully

#### Test 27: Network Timeout

Simulate slow network and verify loading states.

---

### Step 10: Test Responsive Design

#### Test 28: Different Screen Sizes

Test in browser DevTools (F12 → Device Toolbar):

**Desktop (1920x1080):**
- ✅ Sidebar visible
- ✅ Grid shows 3-4 columns
- ✅ All elements properly spaced

**Tablet (768x1024):**
- ✅ Layout adjusts
- ✅ Grid shows 2 columns
- ✅ Sidebar may collapse (if implemented)

**Mobile (375x667):**
- ✅ Single column layout
- ✅ Touch-friendly buttons
- ✅ Modal fits screen

---

## 🎯 Complete Testing Checklist

### Database ✅
- [ ] Migration runs successfully
- [ ] 3 new tables created
- [ ] Role column added to users
- [ ] Default data inserted

### Backend API ✅
- [ ] Server starts without errors
- [ ] Health endpoint works
- [ ] Auth endpoint works (login)
- [ ] Workspaces endpoints work (CRUD)
- [ ] Preferences endpoints work
- [ ] JWT authentication enforced
- [ ] User isolation works

### Frontend UI ✅
- [ ] Page loads without errors
- [ ] Login flow works
- [ ] Token stored correctly
- [ ] Workspaces display
- [ ] Create workspace modal works
- [ ] Color picker works
- [ ] Icon picker works
- [ ] Delete workspace works
- [ ] Settings page loads
- [ ] All settings save correctly
- [ ] Navigation works
- [ ] Toast notifications appear
- [ ] Empty states display

### Security ✅
- [ ] Cannot access without auth
- [ ] Invalid tokens rejected
- [ ] Users can't see other's data
- [ ] SQL injection prevented
- [ ] XSS prevention works

### User Experience ✅
- [ ] Intuitive navigation
- [ ] Clear error messages
- [ ] Success confirmations
- [ ] Responsive design
- [ ] Fast loading
- [ ] No console errors

---

## 🐛 Common Issues & Solutions

### Issue: "Cannot connect to server"
**Solution:** Backend not running. Start with:
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Issue: "Workspaces not loading"
**Solution:** 
- Check token in localStorage
- Verify migration ran
- Check browser console for errors

### Issue: "401 Unauthorized"
**Solution:**
- Token expired, login again
- Check Authorization header format
- Verify token is correct

### Issue: "Table doesn't exist"
**Solution:**
- Run migration script
- Check database connection
- Verify SQL executed successfully

### Issue: "CORS error"
**Solution:**
- Backend CORS middleware configured (already in main.py)
- Check backend URL matches frontend

---

## 📊 Performance Testing

### Load Test (Optional)

Test with multiple workspaces:

```bash
# Create 50 workspaces
for i in {1..50}
do
  curl -X POST http://127.0.0.1:8000/api/workspaces \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"Workspace $i\",\"color\":\"#4f46e5\",\"icon\":\"📚\"}"
done
```

**What to Check:**
- ✅ Grid displays all workspaces
- ✅ Page loads in < 2 seconds
- ✅ Scrolling is smooth
- ✅ No memory leaks

---

## ✅ Test Results Template

```markdown
## Test Results - [Date]

### Environment
- OS: Windows/Mac/Linux
- Browser: Chrome/Firefox/Safari [Version]
- Backend: Python [Version]
- Database: MySQL/SQLite

### Test Summary
- Total Tests: 28
- Passed: ___
- Failed: ___
- Skipped: ___

### Failed Tests
1. Test #X - Issue description
   - Expected: ...
   - Actual: ...
   - Fix needed: ...

### Notes
- Performance observations
- UX feedback
- Suggestions for improvement
```

---

## 🎓 Testing Best Practices

1. **Test in Order**: Follow the steps sequentially
2. **Check Console**: Keep F12 DevTools open
3. **Network Tab**: Monitor API calls
4. **Document Issues**: Note any problems
5. **Test Variations**: Try edge cases
6. **Multiple Browsers**: Test in Chrome, Firefox, Edge
7. **Clean State**: Clear localStorage between major tests

---

## 📞 Need Help?

If tests fail:
1. Check backend logs
2. Review browser console
3. Verify database schema
4. Confirm API endpoints
5. Check STUDENT_DASHBOARD_README.md troubleshooting

---

**Happy Testing! 🧪✅**
