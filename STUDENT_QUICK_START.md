# Student Dashboard - Quick Start Guide

## 🚀 Getting Started in 3 Minutes

### Step 1: Run the Migration (One-time setup)

If you already have KeepAI running, add the new student dashboard tables:

```bash
# Using MySQL/MariaDB
mysql -u root -p keepai < migrate_student_dashboard.sql

# Or if using SQLite, the tables will be created automatically on first run
```

### Step 2: Start the Backend

```bash
# Make sure you're in the project directory
cd c:\xampp\htdocs\keepAI_app

# Start the FastAPI server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

You should see:
```
🚀 Starting KeepAI Training-Enhanced System...
[KeepAI] Connected to database
✅ KeepAI Ready!
```

### Step 3: Open Student Dashboard

1. Open your web browser
2. Navigate to: `file:///c:/xampp/htdocs/keepAI_app/student_dashboard.html`
   
   Or use a local server:
   - VS Code: Right-click `student_dashboard.html` → "Open with Live Server"
   - Python: `python -m http.server 8080` then visit `http://localhost:8080/student_dashboard.html`

### Step 4: Login

**Demo Credentials:**
- Username: `arnel`
- Password: `password123`

Or create a new account using the registration form.

---

## 📚 What You Can Do

### Create Your First Workspace

1. Click **"Create New Workspace"**
2. Name it after your course (e.g., "Database Systems")
3. Choose a color and icon
4. Click **"Create Workspace"**

### Organize Multiple Courses

Create separate workspaces for each course:
- **Database Systems** (Blue, 💻)
- **Algorithms** (Green, 📊)
- **Web Development** (Purple, 🌐)

### Customize Your Settings

1. Click **"Student Settings"** in the sidebar
2. Choose your AI tutor mode:
   - **Socratic**: Learn through questions
   - **Balanced**: Mix of questions and answers
   - **Direct**: Straight answers
   - **Academic**: Deep technical explanations
3. Toggle citations on/off
4. Enable study notifications
5. Click **"Save Settings"**

---

## 🎯 Key Features

### ✅ Student-Only Features
- ✅ Create and manage multiple workspaces
- ✅ Customize AI tutor behavior
- ✅ Personal learning preferences
- ✅ Theme customization
- ✅ Document organization by workspace

### ❌ What Students DON'T Have Access To
- ❌ System-wide AI configuration
- ❌ User management
- ❌ Database settings
- ❌ Admin console

---

## 🔧 Troubleshooting

### "Cannot connect to server"
**Solution:** Make sure the backend is running on port 8000
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### "Workspaces not loading"
**Solution:** 
1. Check you're logged in (you should see your name in top right)
2. Open browser console (F12) and check for errors
3. Verify migration script was run successfully

### "Settings not saving"
**Solution:**
1. Make sure `student_preferences` table exists in database
2. Check backend logs for any errors
3. Verify you're authenticated

### "Cannot create workspace"
**Solution:**
1. Workspace name cannot be empty
2. Check API connection (backend must be running)
3. Verify JWT token is valid (try logging out and back in)

---

## 📖 Next Steps

### Upload Documents
1. Go to **"Library"** section (coming soon in student dashboard)
2. Upload your course PDFs
3. Assign documents to specific workspaces

### Use AI Tutor
1. Go to **"AI Tutor"** section
2. Select a workspace (context)
3. Ask questions about your materials

### Generate Study Materials
- **Summaries**: Automatic note generation
- **Quizzes**: Practice exams from your content
- **Flashcards**: Memorization aids

---

## 🆘 Need Help?

### Check These Resources:
1. [STUDENT_DASHBOARD_README.md](STUDENT_DASHBOARD_README.md) - Full documentation
2. [README.md](README.md) - General KeepAI documentation
3. [AI_SETUP.md](AI_SETUP.md) - AI configuration guide

### Common Issues:

**Q: Where did the admin features go?**
A: Student dashboard is separate! Admin features are in `index.html` with admin credentials.

**Q: Can I use both dashboards?**
A: Yes! Students use `student_dashboard.html`, admins use `index.html` (admin mode).

**Q: How do I switch between workspaces?**
A: Click on any workspace card to open it (feature coming soon).

**Q: Can I delete a workspace?**
A: Yes, click the trash icon on the workspace card. This won't delete your documents, only removes them from that workspace.

---

## 🎓 Pro Tips

### Organize by Semester
Create workspaces like:
- "Fall 2024 - Database Systems"
- "Fall 2024 - Algorithms"
- "Spring 2025 - Machine Learning"

### Use Colors Strategically
- 🔵 Blue: Computer Science courses
- 🟢 Green: Math courses
- 🟣 Purple: Programming courses
- 🟠 Orange: Theory courses

### Customize AI Behavior
- Use **Socratic mode** when you want to think deeply
- Use **Direct mode** when you need quick answers
- Use **Academic mode** for exam preparation

### Stay Organized
- Keep related documents in the same workspace
- Use descriptive workspace names
- Update descriptions with course info

---

## 🌟 What's Different from Regular KeepAI?

### Regular KeepAI (index.html)
- Single interface for all users
- Admin controls mixed with student tools
- No workspace organization
- Basic settings

### Student Dashboard (student_dashboard.html)
- ✨ **Dedicated student interface**
- ✨ **Workspace organization**
- ✨ **Student-specific settings**
- ✨ **Customizable AI tutor**
- ✨ **Clean, focused UI**
- ✨ **No admin distractions**

---

**You're all set!** Start creating workspaces and organizing your study materials. 🎉
