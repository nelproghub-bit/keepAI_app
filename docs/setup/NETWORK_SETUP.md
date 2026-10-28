# 🌐 Network Access Setup Guide

## Problem
You're getting server errors when accessing the application from different devices (phones, tablets, other computers).

## Quick Setup

1. Start the backend with `start_backend.bat` or `start_server.bat`. Both bind
   to all interfaces on port 8000 so other devices can connect.
2. Open the student pages through XAMPP using the server computer's address,
   for example `http://192.168.18.68/keepAI_app/student_portal.html`.
3. The student portal and dashboard use the page's hostname for the API. When
   opened as a local file, they use `127.0.0.1` instead.

Do not hardcode a particular LAN IP in the student pages. If the server's IP
changes, keep using the current address to open the page; the API hostname will
follow automatically.

---

## Windows Firewall (Important!)

If another device cannot open `http://<server-ip>:8000/api/health`, allow
inbound TCP port 8000 for the Wi-Fi's current Windows network profile, limited
to **LocalSubnet**. Use **Private** for a trusted home/school network. If Windows
shows the Wi-Fi as **Public**, keep it Public on an untrusted network and create
the scoped rule for the Public profile instead:

1. Open Windows Defender Firewall with Advanced Security (`wf.msc`).
2. Add an inbound Port rule for TCP port `8000`.
3. Allow the connection only on the profile currently shown for the Wi-Fi.
4. In the rule's Scope tab, set Remote IP address to **Local subnet**.

For the current **Public** Wi-Fi profile, an administrator can create the
equivalent scoped rule from an elevated PowerShell window:

```powershell
New-NetFirewallRule -DisplayName "KeepAI Backend - LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Public
```

---

## Access from Other Devices

### On your phone/tablet:
```
http://192.168.18.68/keepAI_app/student_portal.html
```

### Requirements:
- ✅ Both devices on same WiFi network
- ✅ Server running (start_backend.bat)
- ✅ Student portal opened from the server computer's LAN address (not as a local file)
- ✅ Firewall configured

---

## Testing

### Step 1: Test Server is Accessible
On another device, open browser and go to:
```
http://192.168.18.68:8000/docs
```

If you see API documentation → Server is accessible! ✅

### Step 2: Test Student Portal
```
http://192.168.18.68/keepAI_app/student_portal.html
```

---

## Troubleshooting

### Error: "Connection Refused"
- ✅ Make sure server is running
- ✅ Check firewall settings
- ✅ Verify both devices on same network

### Error: "CORS Policy"
Already configured in FastAPI! Should work automatically.

### Server IP Changed?
Your IP might change if you restart router. To find new IP:
```
ipconfig
```
Look for "IPv4 Address" (192.168.x.x)

---

## Production Deployment

For permanent multi-device access, consider:

1. **Set Static IP** on server computer
2. **Use Cloud Hosting** (Heroku, AWS, Azure)
3. **Use Local DNS** (router configuration)
4. **Set up HTTPS** for secure access

---

## Current Status

✅ `start_backend.bat` enables network access (`0.0.0.0:8000`)
✅ `start_server.bat` also enables network access and uses the project virtual environment
✅ Student portal and dashboard select the API host from the page URL
⚠️ Replace `192.168.18.68` in these examples with the server's current IP
⚠️ Firewall needs configuration

After completing the steps, start the server and test! 🚀
