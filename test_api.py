"""
Automated API Testing Script for Student Dashboard
Run this after starting the backend to verify all endpoints work
"""
import requests
import json
import time
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

API_BASE = "http://127.0.0.1:8000/api"
TEST_USER = {"identifier": "arnel", "password": "password123"}

class TestRunner:
    def __init__(self):
        self.token = None
        self.passed = 0
        self.failed = 0
        self.test_workspace_id = None
        
    def print_header(self, text):
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}{text}")
        print(f"{Fore.CYAN}{'='*60}")
    
    def print_test(self, name):
        print(f"\n{Fore.YELLOW}Testing: {name}")
    
    def print_success(self, message):
        print(f"{Fore.GREEN}✓ {message}")
        self.passed += 1
    
    def print_error(self, message):
        print(f"{Fore.RED}✗ {message}")
        self.failed += 1
    
    def print_info(self, message):
        print(f"{Fore.BLUE}ℹ {message}")
    
    def test_health(self):
        """Test 1: Health Check"""
        self.print_test("Health Check")
        try:
            response = requests.get(f"{API_BASE}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.print_success(f"Health check passed: {data.get('status', 'unknown')}")
                return True
            else:
                self.print_error(f"Health check failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"Health check error: {str(e)}")
            return False
    
    def test_login(self):
        """Test 2: Authentication"""
        self.print_test("User Login")
        try:
            response = requests.post(
                f"{API_BASE}/auth/login",
                json=TEST_USER,
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                user = data.get("user", {})
                self.print_success(f"Login successful for user: {user.get('full_name', 'Unknown')}")
                self.print_info(f"Token: {self.token[:30]}...")
                return True
            else:
                self.print_error(f"Login failed with status {response.status_code}")
                self.print_error(f"Response: {response.text}")
                return False
        except Exception as e:
            self.print_error(f"Login error: {str(e)}")
            return False
    
    def test_list_workspaces(self):
        """Test 3: List Workspaces"""
        self.print_test("List Workspaces")
        if not self.token:
            self.print_error("No auth token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.get(f"{API_BASE}/workspaces", headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                workspaces = data.get("workspaces", [])
                self.print_success(f"Found {len(workspaces)} workspace(s)")
                for ws in workspaces:
                    self.print_info(f"  - {ws['icon']} {ws['name']} ({ws.get('document_count', 0)} docs)")
                return True
            else:
                self.print_error(f"List workspaces failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"List workspaces error: {str(e)}")
            return False
    
    def test_create_workspace(self):
        """Test 4: Create Workspace"""
        self.print_test("Create Workspace")
        if not self.token:
            self.print_error("No auth token available")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            workspace_data = {
                "name": "API Test Workspace",
                "description": "Created by automated test script",
                "color": "#059669",
                "icon": "🧪"
            }
            
            response = requests.post(
                f"{API_BASE}/workspaces",
                headers=headers,
                json=workspace_data,
                timeout=5
            )
            
            if response.status_code == 201:
                data = response.json()
                workspace = data.get("workspace", {})
                self.test_workspace_id = workspace.get("id")
                self.print_success(f"Created workspace: {workspace.get('name')}")
                self.print_info(f"Workspace ID: {self.test_workspace_id}")
                return True
            else:
                self.print_error(f"Create workspace failed with status {response.status_code}")
                self.print_error(f"Response: {response.text}")
                return False
        except Exception as e:
            self.print_error(f"Create workspace error: {str(e)}")
            return False
    
    def test_get_workspace(self):
        """Test 5: Get Workspace Details"""
        self.print_test("Get Workspace Details")
        if not self.token or not self.test_workspace_id:
            self.print_error("No workspace ID available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.get(
                f"{API_BASE}/workspaces/{self.test_workspace_id}",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                workspace = data.get("workspace", {})
                self.print_success(f"Retrieved workspace: {workspace.get('name')}")
                self.print_info(f"Color: {workspace.get('color')}, Icon: {workspace.get('icon')}")
                return True
            else:
                self.print_error(f"Get workspace failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"Get workspace error: {str(e)}")
            return False
    
    def test_update_workspace(self):
        """Test 6: Update Workspace"""
        self.print_test("Update Workspace")
        if not self.token or not self.test_workspace_id:
            self.print_error("No workspace ID available")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            update_data = {
                "name": "Updated Test Workspace",
                "color": "#e11d48"
            }
            
            response = requests.put(
                f"{API_BASE}/workspaces/{self.test_workspace_id}",
                headers=headers,
                json=update_data,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                workspace = data.get("workspace", {})
                self.print_success(f"Updated workspace to: {workspace.get('name')}")
                return True
            else:
                self.print_error(f"Update workspace failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"Update workspace error: {str(e)}")
            return False
    
    def test_get_preferences(self):
        """Test 7: Get Student Preferences"""
        self.print_test("Get Student Preferences")
        if not self.token:
            self.print_error("No auth token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.get(
                f"{API_BASE}/workspaces/preferences/me",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                prefs = data.get("preferences", {})
                self.print_success("Retrieved student preferences")
                self.print_info(f"Theme: {prefs.get('theme')}")
                self.print_info(f"AI Tutor Mode: {prefs.get('ai_tutor_mode')}")
                self.print_info(f"Show Citations: {prefs.get('show_citations')}")
                return True
            else:
                self.print_error(f"Get preferences failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"Get preferences error: {str(e)}")
            return False
    
    def test_update_preferences(self):
        """Test 8: Update Student Preferences"""
        self.print_test("Update Student Preferences")
        if not self.token:
            self.print_error("No auth token available")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            update_data = {
                "ai_tutor_mode": "socratic",
                "show_citations": False
            }
            
            response = requests.put(
                f"{API_BASE}/workspaces/preferences/me",
                headers=headers,
                json=update_data,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                prefs = data.get("preferences", {})
                self.print_success("Updated preferences successfully")
                self.print_info(f"New AI Tutor Mode: {prefs.get('ai_tutor_mode')}")
                self.print_info(f"Show Citations: {prefs.get('show_citations')}")
                return True
            else:
                self.print_error(f"Update preferences failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"Update preferences error: {str(e)}")
            return False
    
    def test_delete_workspace(self):
        """Test 9: Delete Workspace"""
        self.print_test("Delete Workspace")
        if not self.token or not self.test_workspace_id:
            self.print_error("No workspace ID available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.delete(
                f"{API_BASE}/workspaces/{self.test_workspace_id}",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                self.print_success("Deleted test workspace successfully")
                return True
            else:
                self.print_error(f"Delete workspace failed with status {response.status_code}")
                return False
        except Exception as e:
            self.print_error(f"Delete workspace error: {str(e)}")
            return False
    
    def test_unauthorized_access(self):
        """Test 10: Unauthorized Access (No Token)"""
        self.print_test("Unauthorized Access Prevention")
        try:
            response = requests.get(f"{API_BASE}/workspaces", timeout=5)
            
            if response.status_code == 401 or response.status_code == 403:
                self.print_success("Unauthorized access correctly blocked")
                return True
            else:
                self.print_error(f"Security issue: Got status {response.status_code} instead of 401/403")
                return False
        except Exception as e:
            self.print_error(f"Unauthorized test error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        self.print_header("KeepAI Student Dashboard - API Tests")
        self.print_info(f"Testing against: {API_BASE}")
        self.print_info(f"Test user: {TEST_USER['identifier']}")
        
        # Run tests
        tests = [
            self.test_health,
            self.test_login,
            self.test_list_workspaces,
            self.test_create_workspace,
            self.test_get_workspace,
            self.test_update_workspace,
            self.test_get_preferences,
            self.test_update_preferences,
            self.test_delete_workspace,
            self.test_unauthorized_access,
        ]
        
        for test in tests:
            test()
            time.sleep(0.5)  # Small delay between tests
        
        # Print summary
        self.print_header("Test Summary")
        total = self.passed + self.failed
        print(f"\n{Fore.WHITE}Total Tests: {total}")
        print(f"{Fore.GREEN}Passed: {self.passed}")
        print(f"{Fore.RED}Failed: {self.failed}")
        
        if self.failed == 0:
            print(f"\n{Fore.GREEN}{Style.BRIGHT}🎉 All tests passed! Student Dashboard API is working correctly.")
        else:
            print(f"\n{Fore.RED}{Style.BRIGHT}⚠️  Some tests failed. Please review the errors above.")
        
        success_rate = (self.passed / total * 100) if total > 0 else 0
        print(f"\n{Fore.CYAN}Success Rate: {success_rate:.1f}%\n")

def main():
    """Main entry point"""
    print(f"{Fore.CYAN}Starting Student Dashboard API Tests...")
    print(f"{Fore.YELLOW}Make sure the backend server is running on http://127.0.0.1:8000\n")
    
    try:
        runner = TestRunner()
        runner.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Tests interrupted by user.")
    except Exception as e:
        print(f"\n{Fore.RED}Fatal error: {str(e)}")

if __name__ == "__main__":
    # Check if colorama is installed
    try:
        import colorama
    except ImportError:
        print("Installing colorama for colored output...")
        import subprocess
        subprocess.check_call(["pip", "install", "colorama"])
        import colorama
        colorama.init(autoreset=True)
    
    main()
