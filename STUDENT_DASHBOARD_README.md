# Student Dashboard - KeepAI

## Overview

The Student Dashboard is a dedicated interface for students to manage their learning workspace, organize course materials, and customize their AI tutoring experience.

## Features

### 🗂️ Workspace Management
- **Create Multiple Workspaces**: Organize materials by course, subject, or semester
- **Custom Organization**: Choose colors and icons for easy identification
- **Document Collections**: Group related documents within each workspace
- **Workspace Switching**: Quick access to different study areas

### ⚙️ Student Settings (Student-Only)
- **Appearance Preferences**: Light, dark, or auto theme
- **AI Tutor Customization**: 
  - Socratic mode (question-based learning)
  - Balanced mode (mixed approach)
  - Direct answers mode
  - Deep academic mode
- **Citation Control**: Toggle showing source references
- **Notification Preferences**: Manage study reminders

### 📚 Integrated Tools
All original KeepAI features accessible from the student dashboard:
- AI Tutor with RAG
- Smart Summaries
- Practice Quizzes
- Flashcards
- Study Planner
- Progress Tracking

## Access Control

### Student Dashboard
- **URL**: `student_dashboard.html`
- **Access**: Requires student authentication
- **Features**: Full workspace and settings management
- **Restrictions**: Student-specific features only

### Admin Portal
- **URL**: `index.html` (with admin mode)
- **Access**: Admin credentials required
- **Features**: System settings, user management, AI configuration
- **Separation**: Admin functions not visible to students

## Database Schema

### New Tables Added

#### 1. Workspaces Table
```sql
CREATE TABLE workspaces (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    color VARCHAR(32) DEFAULT '#4f46e5',
    icon VARCHAR(64) DEFAULT '📚',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### 2. Student Preferences Table
```sql
CREATE TABLE student_preferences (
    user_id VARCHAR(64) PRIMARY KEY,
    theme VARCHAR(32) DEFAULT 'light',
    ai_tutor_mode VARCHAR(32) DEFAULT 'balanced',
    show_citations TINYINT(1) DEFAULT 1,
    enable_notifications TINYINT(1) DEFAULT 1,
    default_workspace_id VARCHAR(64) NULL,
    preferences LONGTEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### 3. Workspace Documents Junction Table
```sql
CREATE TABLE workspace_documents (
    workspace_id VARCHAR(64) NOT NULL,
    document_id VARCHAR(64) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, document_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
```

#### 4. Updated Users Table
Added `role` column:
```sql
ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'student';
```

## API Endpoints

### Workspace Management

#### List Workspaces
```http
GET /api/workspaces
Authorization: Bearer <token>
```

#### Create Workspace
```http
POST /api/workspaces
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Database Systems",
  "description": "CS 401 - Fall 2024",
  "color": "#4f46e5",
  "icon": "📚"
}
```

#### Get Workspace
```http
GET /api/workspaces/{workspace_id}
Authorization: Bearer <token>
```

#### Update Workspace
```http
PUT /api/workspaces/{workspace_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description",
  "color": "#059669",
  "icon": "💻"
}
```

#### Delete Workspace
```http
DELETE /api/workspaces/{workspace_id}
Authorization: Bearer <token>
```

### Workspace Documents

#### Get Workspace Documents
```http
GET /api/workspaces/{workspace_id}/documents
Authorization: Bearer <token>
```

#### Add Document to Workspace
```http
POST /api/workspaces/{workspace_id}/documents
Authorization: Bearer <token>
Content-Type: application/json

{
  "document_id": "doc_abc123"
}
```

#### Remove Document from Workspace
```http
DELETE /api/workspaces/{workspace_id}/documents/{document_id}
Authorization: Bearer <token>
```

### Student Preferences

#### Get My Preferences
```http
GET /api/workspaces/preferences/me
Authorization: Bearer <token>
```

#### Update My Preferences
```http
PUT /api/workspaces/preferences/me
Authorization: Bearer <token>
Content-Type: application/json

{
  "theme": "dark",
  "ai_tutor_mode": "socratic",
  "show_citations": true,
  "enable_notifications": true,
  "preferences": {
    "language": "en",
    "timezone": "UTC"
  }
}
```

## Setup Instructions

### 1. Database Migration
Run the updated schema to add new tables:
```bash
mysql -u root -p keepai < database_schema.sql
```

Or manually execute the new table definitions from `database_schema.sql`.

### 2. Backend Setup
The workspace router is already integrated. Restart the FastAPI server:
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Access the Student Dashboard
1. Open `student_dashboard.html` in your browser
2. Login with student credentials
3. Start creating workspaces and organizing materials

## Student Settings Options

### Theme Options
- **Light**: Default bright theme
- **Dark**: Dark mode (coming soon)
- **Auto**: Follows system preference (coming soon)

### AI Tutor Modes
- **Socratic**: AI asks questions to guide learning
- **Balanced**: Mix of questions and direct answers
- **Direct**: Straightforward explanations
- **Academic**: Deep, technical explanations with formal language

### Additional Preferences
- **Show Citations**: Display source references in AI responses
- **Enable Notifications**: Receive study reminders
- **Default Workspace**: Set which workspace opens by default

## Security & Privacy

### Authentication Required
- All workspace endpoints require valid JWT token
- Students can only access their own workspaces
- Cross-user access is prevented

### Data Isolation
- Each student's workspaces are isolated
- Documents are scoped to user ID
- Settings are per-user

## Future Enhancements

### Planned Features
- [ ] Workspace templates
- [ ] Shared workspaces (collaboration)
- [ ] Workspace export/import
- [ ] Workspace analytics
- [ ] Custom workspace themes
- [ ] Mobile-responsive enhancements
- [ ] Workspace search and filtering
- [ ] Document tagging within workspaces
- [ ] Workspace archiving

## Usage Examples

### Creating a Workspace for a Course
1. Click "Create New Workspace"
2. Name it after your course (e.g., "Database Systems CS 401")
3. Choose a color and icon to identify it
4. Add your syllabus, lecture notes, and readings
5. Use the AI Tutor within that workspace context

### Organizing Multiple Courses
- **Workspace 1**: Database Systems (Blue, 💻)
- **Workspace 2**: Algorithms (Green, 📊)
- **Workspace 3**: Web Development (Purple, 🌐)
- **Workspace 4**: Machine Learning (Orange, 🤖)

### Customizing Your Learning Experience
1. Go to Student Settings
2. Choose your preferred AI tutor mode
3. Enable/disable citations based on your needs
4. Set up study notifications
5. Select your theme preference

## Troubleshooting

### Workspaces Not Loading
- Check if you're logged in (token in localStorage)
- Verify backend is running on port 8000
- Check browser console for errors

### Settings Not Saving
- Ensure you have a valid authentication token
- Check API connection
- Verify database schema includes `student_preferences` table

### Cannot Create Workspace
- Ensure workspace name is not empty
- Check API endpoint is accessible
- Verify database permissions

## Technical Stack

### Frontend
- Pure HTML/CSS/JavaScript
- No framework dependencies
- Responsive design
- Modern CSS Grid/Flexbox

### Backend
- FastAPI Python framework
- Pydantic validation
- JWT authentication
- RESTful API design

### Database
- MySQL/MariaDB or SQLite
- Foreign key relationships
- Cascading deletes for data integrity

## Support

For issues or questions:
1. Check this documentation
2. Review API error messages
3. Check backend logs
4. Consult main README.md for general setup

---

**KeepAI Student Dashboard** - Empowering students to organize and optimize their learning journey with AI assistance.
