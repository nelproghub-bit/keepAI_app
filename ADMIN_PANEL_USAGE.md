# Admin Panel - Server Control Usage Guide

## 🎯 Quick Start

### Open Admin Panel
```
File → Open → admin_panel.html
```

### What You'll See
```
┌─────────────────────────────────────────┐
│ ⚙️  KeepAI Admin Panel                  │
│ Server management and system control   │
└─────────────────────────────────────────┘

Status: Offline (Red dot pulsing)
http://127.0.0.1:8000

[Start] [Stop] [Restart] [Check Status]

Logs:
[10:30:00] System initialized
```

---

## 🎮 Control Buttons

### 1. START SERVER (Green) ▶️
**Click this to:**
- Launch the backend server
- Opens new command window
- Starts FastAPI on port 8000

**What happens:**
```
Click → New window opens → Server starts → Status turns green
```

**Logs show:**
```
[10:30:45] Starting server... (info)
[10:30:46] Server startup initiated. New window should open. (success)
[10:30:50] Status: ONLINE - Server is running (info)
```

**Time to online:** 3-5 seconds

---

### 2. STOP SERVER (Red) ⏹️
**Click this to:**
- Gracefully shut down server
- Saves state safely
- Cleans up resources

**What happens:**
```
Click → Server signals shutdown → Status turns red → Port closes
```

**Logs show:**
```
[10:35:20] Stopping server... (warning)
[10:35:22] Server stop signal sent. Shutting down... (success)
```

**Time to offline:** 1-2 seconds

---

### 3. RESTART SERVER (Orange) 🔄
**Click this to:**
- Stop then start server
- Full reboot sequence
- Same as Stop + Start

**What happens:**
```
Click → Stops server → Waits 2 seconds → Starts server → Comes online
```

**Logs show:**
```
[10:40:00] Restarting server... (warning)
[10:40:02] Server stop signal sent. (success)
[10:40:04] Server startup initiated. (success)
[10:40:09] Status: ONLINE - Server is running (info)
```

**Time to complete:** ~10 seconds

---

### 4. CHECK STATUS (Blue) ✓
**Click this to:**
- Manually verify server status
- Update status badge
- See if server is responding

**What happens:**
```
Click → Queries server → Shows result → Updates badge
```

**Logs show:**
```
[10:45:00] Status: ONLINE - Server is running and responding (info)
```

**Time to check:** < 1 second

---

## 📊 Status Indicators

### Visual Cues

**Online (Green)**
```
🟢 Status: Online
   Uptime: 0:05:30
   [Status dot pulsing green]
```
✅ Server is responding  
✅ API is accessible  
✅ All systems ready  

**Offline (Red)**
```
🔴 Status: Offline
   Uptime: --:--:--
   [Status dot pulsing red]
```
❌ Server not responding  
❌ API not accessible  
❌ Cannot process requests  

---

## 📝 Reading the Logs

### Log Format
```
[HH:MM:SS] message (type)
```

### Message Types

**Info** (Blue text)
```
[10:30:00] System initialized (info)
[10:30:05] Status check performed (info)
```
ℹ️ Informational messages

**Success** (Green text)
```
[10:30:15] Server startup initiated. New window should open. (success)
[10:30:20] Status: ONLINE - Server is running (success)
```
✅ Operation completed successfully

**Warning** (Orange text)
```
[10:35:00] Stopping server... (warning)
[10:40:00] Restarting server... (warning)
```
⚠️ Action in progress

**Error** (Red text)
```
[10:45:00] Failed to start server: Port already in use (error)
[10:45:05] Error: Connection timeout (error)
```
❌ Something went wrong

---

## 🔄 Automatic Updates

### Auto Refresh
- Status checked every 5 seconds
- No manual action needed
- Updates happen in background

**What auto-updates:**
- Server status badge
- Online/Offline indicator
- Uptime display
- Status message

---

## 📊 System Statistics

### Cards Shown
1. **Current Status**
   - Online / Offline display

2. **Uptime**
   - Time server has been running
   - Format: HH:MM:SS

3. **Database**
   - Connection status
   - Should show "Connected"

---

## 🚀 Common Workflows

### Workflow 1: Fresh Start
```
1. Open admin_panel.html
2. Status shows: Offline (Red)
3. Click: "Start Server"
4. Wait: 3-5 seconds
5. Status shows: Online (Green)
6. Done!
```

### Workflow 2: Restart Server
```
1. Click: "Restart Server"
2. Status shows: Offline briefly
3. Wait: ~10 seconds
4. Status shows: Online (Green)
5. Done!
```

### Workflow 3: Stop Server
```
1. Click: "Stop Server"
2. Logs show: "Server stop signal sent"
3. Status shows: Offline (Red)
4. Done!
```

### Workflow 4: Monitor Status
```
1. Keep admin_panel.html open
2. Watch status badge
3. Monitor logs for activity
4. Auto-updates every 5 seconds
```

---

## 🆘 Troubleshooting

### Issue: "Port already in use"
**Solution:**
- Stop existing server first
- Or change port (advanced)
- Use: `netstat -ano | findstr :8000`

### Issue: Status shows Offline after clicking Start
**Solution:**
- Wait 5-10 seconds for server to boot
- Click "Check Status" button
- Check new command window is open
- Look for "Uvicorn running" message

### Issue: Buttons don't respond
**Solution:**
- Refresh browser (F5)
- Try "Check Status" first
- Verify API is accessible
- Check browser console (F12)

### Issue: Server won't start
**Solution:**
- Start manually: `START_SERVER.bat`
- Check port 8000 availability
- Verify virtual environment exists
- Check error in new command window

---

## 📱 Mobile / Tablet View

Buttons stack vertically on smaller screens:
```
[Start Server]
[Stop Server]
[Restart Server]
[Check Status]
```

All functionality remains the same!

---

## 💾 Data Persistence

**Auto-saved data:**
- Logs persist until refresh
- Status updates in real-time
- No data loss on disconnect

**Note:** Logs clear on page refresh

---

## 🔐 Security Notes

- Admin panel has no authentication (add for production)
- Uses local API calls only
- No external network access
- Logs may contain sensitive info

---

## ⚡ Performance

- Status checks: < 1 second
- Server start: 3-5 seconds
- Server stop: 1-2 seconds
- Restart: ~10 seconds
- Auto-refresh: Every 5 seconds

---

## 📞 Support Tips

1. **Keep admin panel open** during development
2. **Watch the logs** for any errors
3. **Auto-refresh** reduces need for manual checks
4. **Use Check Status** to verify anytime
5. **Refer to docs** at http://localhost:8000/docs when online

---

## ✅ Verification Checklist

- [ ] Admin panel opens in browser
- [ ] Status shows "Offline" initially
- [ ] "Start Server" button is clickable
- [ ] New command window opens when starting
- [ ] Status changes to "Online" after start
- [ ] Logs show server startup messages
- [ ] "Check Status" shows current state
- [ ] "Stop Server" gracefully shuts down
- [ ] Auto-refresh works every 5 seconds

---

**Happy server managing! 🚀**

For issues, check the server logs in the command window or browser console (F12).
