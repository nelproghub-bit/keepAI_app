# KeepAI Admin Dashboard Guide

## Overview

The Admin Dashboard (`admin_dashboard.html`) provides system administrators with comprehensive control and monitoring capabilities for the KeepAI platform, including server startup/shutdown automation.

## Accessing the Admin Dashboard

1. Open `admin_dashboard.html` in your web browser
2. The dashboard will automatically check server status

**URL:** `file:///path/to/keepAI_app/admin_dashboard.html`

Or host it locally:
```bash
python -m http.server 8080
# Then visit: http://localhost:8080/admin_dashboard.html
```

## Features

### 1. **Dashboard Overview**
- Server status indicator
- Database connection status
- Quick system statistics
- Real-time health monitoring

### 2. **Server Control Panel**
The main feature for automatic server startup/shutdown:

#### **Start Server Button**
- Automatically launches the backend server
- Starts FastAPI on `http://127.0.0.1:8000`
- Real-time status monitoring
- Automatic checking every 5 seconds
- Detailed logging of startup process

#### **Stop Server Button**
- Gracefully terminates the backend process
- Provides confirmation feedback
- Updates status in real-time

#### **Check Status Button**
- Manual server status verification
- Immediate response feedback

#### **Server Logs**
- Real-time server activity logs
- Startup/shutdown progress tracking
- Error reporting
- Formatted output for easy reading

### 3. **User Management**
- View all registered users
- See user roles (student/admin)
- Account creation dates
- Edit user accounts

### 4. **Admin Settings**
Configure system parameters:
- Server host (127.0.0.1)
- Server port (8000)
- AI provider selection (Ollama, OpenAI, Claude)
- Debug mode toggle
- Settings persistence

## How Server Startup Works

### Automatic Startup Process

1. **Click "Start Server" Button**
   - Backend API checks if server is already running
   - If offline, initiates startup sequence

2. **Server Initialization**
   - Detects Python environment (.venv or system Python)
   - Executes: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
   - On Windows: Opens new command prompt window
   - On Linux/Mac: Runs in background

3. **Status Monitoring**
   - Admin dashboard checks `/api/health` every second
   - Shows real-time progress in logs
   - Updates status badge when server comes online
   - Maximum wait: 30 seconds

4. **Success Notification**
   - Green success alert when server is online
   - Server endpoint displayed: `http://127.0.0.1:8000`
   - API becomes accessible at `/api/*` endpoints

### Automatic Status Checking

- Dashboard checks server status every 5 seconds
- Updates in real-time without manual refresh
- Automatic detection of server crashes
- Status indicators:
  - **Online** (Green): Server running and responding
  - **Offline** (Red): Server not responding or crashed

## Technical Requirements

### Backend Dependencies

Ensure these packages are installed:
```bash
pip install -r requirements.txt
```

Key packages required:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `psutil` - Process monitoring
- `python-multipart` - File upload support
- `python-dotenv` - Environment configuration

### System Requirements

- Python 3.8+
- 4GB RAM minimum
- Windows, Linux, or macOS
- Administrator/elevated privileges recommended for server control

## API Endpoints (Backend)

The admin dashboard communicates with these endpoints:

### Server Management
```
GET  /api/admin/server/status    - Get current server status
POST /api/admin/server/start     - Start the server
POST /api/admin/server/stop      - Stop the server
POST /api/admin/server/restart   - Restart the server
GET  /api/admin/system/info      - Get system information
```

### Admin Panel
```
GET  /api/admin/health           - Admin panel health check
GET  /api/admin/users            - List all users
```

## Troubleshooting

### Server Won't Start

**Problem:** "Server startup timeout" or stays offline

**Solutions:**
1. Check if Python is installed: `python --version`
2. Verify virtual environment: `.venv/Scripts/activate` (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Check port 8000 isn't already in use:
   ```bash
   netstat -an | grep 8000  # Linux/Mac
   netstat -ano | findstr :8000  # Windows
   ```
5. Try manual startup: `python -m uvicorn app.main:app --reload`

### Admin Dashboard Doesn't Load

**Problem:** Blank page or errors in console

**Solutions:**
1. Open browser console (F12) and check for errors
2. Verify file path is correct
3. Ensure all image/icon files are accessible
4. Clear browser cache (Ctrl+Shift+Delete)

### Server Starts but Dashboard Shows Offline

**Problem:** Server responds to manual check but dashboard shows offline

**Solutions:**
1. Refresh the admin dashboard (F5)
2. Click "Check Status" button manually
3. Verify CORS is enabled in backend (should be by default)
4. Check browser console for network errors

### Permission Denied Errors

**Problem:** "Access denied" when starting server

**Solutions:**
1. Run browser/terminal as administrator
2. On Windows: Right-click Command Prompt → "Run as administrator"
3. Check file permissions in project directory
4. Try manual startup to see detailed error

## Best Practices

### For Production Environments

1. **Use process managers** like:
   - `systemd` on Linux
   - `Windows Service` on Windows
   - `supervisor` on any platform

2. **Never run with `--reload`** in production
   - Use production command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

3. **Set environment variables** properly
   - Create `.env` file with production settings
   - Set `ENVIRONMENT=production`

4. **Enable logging** for monitoring
   - Direct output to log files
   - Set up log rotation
   - Monitor error logs regularly

### For Development

1. Use `--reload` flag (already configured)
2. Keep admin dashboard open for monitoring
3. Enable debug mode for detailed logs
4. Check logs frequently for errors

## Security Considerations

⚠️ **Important:** The admin dashboard currently has no authentication. For production use:

1. **Add authentication** - Implement login for admin access
2. **Restrict IP access** - Only allow admin from specific IPs
3. **Use HTTPS** - Don't run admin dashboard over HTTP in production
4. **Token validation** - Validate authorization tokens for all admin requests
5. **Activity logging** - Log all admin actions for audit trail

## File Locations

```
keepAI_app/
├── admin_dashboard.html          # Admin interface
├── app/
│   ├── main.py                   # Main app (updated with admin router)
│   └── routers/
│       └── admin.py              # Admin API endpoints
├── start_backend.bat             # Windows startup script
├── start_server.ps1              # PowerShell startup script
└── requirements.txt              # Dependencies (includes psutil)
```

## Updates and Maintenance

### Adding New Admin Features

To extend the admin dashboard:

1. Add new HTML section in `admin_dashboard.html`
2. Create corresponding API endpoint in `app/routers/admin.py`
3. Add JavaScript function to handle communication
4. Update navigation menu

### Monitoring Dashboard

To add system monitoring:

1. API endpoint `/api/admin/system/info` already provides:
   - CPU usage
   - Memory usage
   - Disk usage
   - Process count

2. JavaScript can call this every few seconds for real-time graphs

## Support and Documentation

- **Backend Docs:** `http://localhost:8000/docs` (when server is running)
- **Health Check:** `http://localhost:8000/api/health`
- **API Base:** `http://localhost:8000/api`

## Changelog

### Version 1.0 (Current)
- ✅ Server start/stop automation
- ✅ Real-time status monitoring
- ✅ System information dashboard
- ✅ User management interface
- ✅ Admin settings panel
- ✅ Server logs viewer
- ✅ Automatic status checking (5-second interval)
- ✅ Cross-platform support (Windows, Linux, macOS)
