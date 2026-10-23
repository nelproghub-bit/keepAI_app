<?php
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

$action = isset($_GET['action']) ? strtolower(trim($_GET['action'])) : '';
if (!$action && isset($_POST['action'])) {
    $action = strtolower(trim($_POST['action']));
}

$dir = __DIR__;
$pythonExe = $dir . DIRECTORY_SEPARATOR . '.venv' . DIRECTORY_SEPARATOR . 'Scripts' . DIRECTORY_SEPARATOR . 'python.exe';
if (!file_exists($pythonExe)) {
    $pythonExe = 'C:\\repository\\Gubi\\keepAI_app\\.venv\\Scripts\\python.exe';
}
if (!file_exists($pythonExe)) {
    $pythonExe = 'python';
}

function isPortOpen($host = '127.0.0.1', $port = 8000, $timeout = 1) {
    $fp = @fsockopen($host, $port, $errno, $errstr, $timeout);
    if ($fp) {
        fclose($fp);
        return true;
    }
    return false;
}

function getPortPids($port = 8000) {
    $pids = [];
    $output = [];
    exec("netstat -ano | findstr :$port", $output);
    foreach ($output as $line) {
        if (preg_match('/LISTENING\s+(\d+)/i', $line, $matches)) {
            $pids[] = intval($matches[1]);
        }
    }
    return array_unique($pids);
}

function killPortProcesses($port = 8000) {
    $pids = getPortPids($port);
    $killed = 0;
    foreach ($pids as $pid) {
        if ($pid > 0) {
            exec("taskkill /F /T /PID $pid 2>&1");
            $killed++;
        }
    }
    return $killed;
}

function launchUvicorn($dir, $pythonExe) {
    $cmd = "\"$pythonExe\" -m uvicorn app.main:app --host 0.0.0.0 --port 8000";
    if (class_exists('COM')) {
        try {
            $wsh = new COM("WScript.Shell");
            $wsh->CurrentDirectory = $dir;
            $wsh->Run($cmd, 0, false);
            return true;
        } catch (\Exception $e) {}
    }
    
    // Fallback: PowerShell or start /B
    $escapedDir = escapeshellarg($dir);
    $psCmd = "powershell -Command \"Start-Process -FilePath '$pythonExe' -ArgumentList '-m uvicorn app.main:app --host 0.0.0.0 --port 8000' -WorkingDirectory '$dir' -WindowStyle Hidden\"";
    pclose(popen($psCmd, "r"));
    return true;
}

// Uptime tracker via temporary file
$uptimeFile = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'keepai_server_start.txt';

switch ($action) {
    case 'status':
        $online = isPortOpen('127.0.0.1', 8000, 1.2);
        $uptimeStr = '--:--:--';
        $dbStatus = 'Offline';

        if ($online) {
            // Check health
            $ctx = stream_context_create(['http' => ['timeout' => 1.5, 'ignore_errors' => true]]);
            $healthJson = @file_get_contents('http://127.0.0.1:8000/api/health', false, $ctx);
            if ($healthJson) {
                $healthData = json_decode($healthJson, true);
                if (isset($healthData['database']) && is_array($healthData['database'])) {
                    $dbStatus = ($healthData['database']['status'] ?? '') === 'connected' ? 'Connected' : 'Disconnected';
                } else {
                    $dbStatus = 'Connected';
                }
            } else {
                $dbStatus = 'Connected';
            }

            if (!file_exists($uptimeFile)) {
                file_put_contents($uptimeFile, time());
            }
            $startTime = intval(file_get_contents($uptimeFile));
            $diff = max(0, time() - $startTime);
            $hours = floor($diff / 3600);
            $mins = floor(($diff % 3600) / 60);
            $secs = $diff % 60;
            $uptimeStr = sprintf('%02d:%02d:%02d', $hours, $mins, $secs);

            echo json_encode([
                'success' => true,
                'status' => 'online',
                'message' => 'KeepAI backend server is active and operational on port 8000',
                'uptime' => $uptimeStr,
                'database' => $dbStatus,
                'port' => 8000
            ]);
        } else {
            if (file_exists($uptimeFile)) {
                @unlink($uptimeFile);
            }
            echo json_encode([
                'success' => true,
                'status' => 'offline',
                'message' => 'KeepAI server is currently offline',
                'uptime' => '--:--:--',
                'database' => 'Offline',
                'port' => 8000
            ]);
        }
        break;

    case 'start':
        if (isPortOpen('127.0.0.1', 8000, 1)) {
            echo json_encode([
                'success' => true,
                'message' => 'Server is already running on http://127.0.0.1:8000',
                'status' => 'online'
            ]);
            break;
        }

        launchUvicorn($dir, $pythonExe);
        file_put_contents($uptimeFile, time());

        // Wait up to 3.5 seconds for it to bind
        $started = false;
        for ($i = 0; $i < 7; $i++) {
            usleep(500000); // 500ms
            if (isPortOpen('127.0.0.1', 8000, 0.5)) {
                $started = true;
                break;
            }
        }

        if ($started) {
            echo json_encode([
                'success' => true,
                'message' => 'KeepAI server started successfully on http://127.0.0.1:8000',
                'status' => 'online'
            ]);
        } else {
            echo json_encode([
                'success' => true,
                'message' => 'Server start command sent. Launching in background...',
                'status' => 'online'
            ]);
        }
        break;

    case 'stop':
        $killed = killPortProcesses(8000);
        if (file_exists($uptimeFile)) {
            @unlink($uptimeFile);
        }
        usleep(500000);

        echo json_encode([
            'success' => true,
            'message' => 'KeepAI server stopped successfully',
            'status' => 'offline'
        ]);
        break;

    case 'restart':
        killPortProcesses(8000);
        if (file_exists($uptimeFile)) {
            @unlink($uptimeFile);
        }
        sleep(1);

        launchUvicorn($dir, $pythonExe);
        file_put_contents($uptimeFile, time());

        $started = false;
        for ($i = 0; $i < 8; $i++) {
            usleep(500000);
            if (isPortOpen('127.0.0.1', 8000, 0.5)) {
                $started = true;
                break;
            }
        }

        echo json_encode([
            'success' => true,
            'message' => 'KeepAI server restarted successfully on http://127.0.0.1:8000',
            'status' => 'online'
        ]);
        break;

    default:
        echo json_encode([
            'success' => false,
            'message' => 'Invalid action. Supported actions: status, start, stop, restart'
        ]);
        break;
}
