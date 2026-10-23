"""
Student Workspace Service
Manages student workspaces, preferences, and workspace-document relationships
"""
import json
import uuid
from typing import List, Dict, Any, Optional
from app.core.database import get_connection

class WorkspaceService:
    
    def create_workspace(self, user_id: str, name: str, description: str = "", 
                        color: str = "#4f46e5", icon: str = "📚",
                        category: Optional[str] = None) -> Dict[str, Any]:
        """Create a new workspace for a student"""
        workspace_id = f"workspace_{uuid.uuid4().hex[:12]}"
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO workspaces (id, user_id, name, category, description, color, icon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (workspace_id, user_id, name, category, description, color, icon))
        
        conn.commit()
        conn.close()
        
        return self.get_workspace(workspace_id)
    
    def get_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get workspace by ID"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_id, name, category, description, color, icon, is_active, created_at, updated_at
            FROM workspaces
            WHERE id = ?
        """, (workspace_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return dict(row) if hasattr(row, 'keys') else {
            "id": row[0], "user_id": row[1], "name": row[2], "category": row[3],
            "description": row[4], "color": row[5], "icon": row[6], "is_active": row[7],
            "created_at": str(row[8]), "updated_at": str(row[9])
        }
    
    def list_user_workspaces(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all workspaces for a student"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT w.id, w.user_id, w.name, w.category, w.description, w.color, w.icon,
                   w.is_active, w.created_at, w.updated_at,
                   COUNT(wd.document_id) as document_count
            FROM workspaces w
            LEFT JOIN workspace_documents wd ON w.id = wd.workspace_id
            WHERE w.user_id = ?
            GROUP BY w.id
            ORDER BY w.created_at DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        workspaces = []
        for row in rows:
            if hasattr(row, 'keys'):
                workspaces.append(dict(row))
            else:
                workspaces.append({
                    "id": row[0], "user_id": row[1], "name": row[2], "category": row[3],
                    "description": row[4], "color": row[5], "icon": row[6], "is_active": row[7],
                    "created_at": str(row[8]), "updated_at": str(row[9]),
                    "document_count": row[10]
                })
        
        return workspaces
    
    def update_workspace(self, workspace_id: str, name: Optional[str] = None,
                        description: Optional[str] = None, color: Optional[str] = None,
                        icon: Optional[str] = None, is_active: Optional[bool] = None,
                        category: Optional[str] = None) -> Dict[str, Any]:
        """Update workspace details"""
        conn = get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if color is not None:
            updates.append("color = ?")
            params.append(color)
        if icon is not None:
            updates.append("icon = ?")
            params.append(icon)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        
        if updates:
            params.append(workspace_id)
            cursor.execute(f"""
                UPDATE workspaces
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            
            conn.commit()
        
        conn.close()
        return self.get_workspace(workspace_id)
    
    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def add_document_to_workspace(self, workspace_id: str, document_id: str) -> bool:
        """Add a document to a workspace"""
        conn = get_connection()
        cursor = conn.cursor()

        relation_id = f"wsdoc_{uuid.uuid4().hex[:12]}"

        try:
            cursor.execute("""
                INSERT INTO workspace_documents (id, workspace_id, document_id)
                VALUES (?, ?, ?)
            """, (relation_id, workspace_id, document_id))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.close()
            print(f"Error adding document to workspace: {e}")
            return False
    
    def remove_document_from_workspace(self, workspace_id: str, document_id: str) -> bool:
        """Remove a document from a workspace"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM workspace_documents
            WHERE workspace_id = ? AND document_id = ?
        """, (workspace_id, document_id))
        
        removed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return removed
    
    def get_workspace_documents(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Get all documents in a workspace"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT d.id, d.user_id, d.filename, d.chunks_indexed, 
                   d.char_count, d.page_count, d.created_at
            FROM documents d
            INNER JOIN workspace_documents wd ON d.id = wd.document_id
            WHERE wd.workspace_id = ?
            ORDER BY wd.added_at DESC
        """, (workspace_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        documents = []
        for row in rows:
            if hasattr(row, 'keys'):
                documents.append(dict(row))
            else:
                documents.append({
                    "id": row[0], "user_id": row[1], "filename": row[2],
                    "chunks_indexed": row[3], "char_count": row[4],
                    "page_count": row[5], "created_at": str(row[6])
                })
        
        return documents
    
    def get_student_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get student preferences"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id, theme, ai_tutor_mode, show_citations, 
                   enable_notifications, default_workspace_id, preferences
            FROM student_preferences
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            # Create default preferences
            return self.create_default_preferences(user_id)
        
        if hasattr(row, 'keys'):
            prefs = dict(row)
        else:
            prefs = {
                "user_id": row[0], "theme": row[1], "ai_tutor_mode": row[2],
                "show_citations": bool(row[3]), "enable_notifications": bool(row[4]),
                "default_workspace_id": row[5], "preferences": row[6]
            }
        
        # Parse JSON preferences if present
        if prefs.get("preferences"):
            try:
                prefs["preferences"] = json.loads(prefs["preferences"])
            except:
                prefs["preferences"] = {}
        else:
            prefs["preferences"] = {}
        
        return prefs
    
    def create_default_preferences(self, user_id: str) -> Dict[str, Any]:
        """Create default preferences for a new student"""
        conn = get_connection()
        cursor = conn.cursor()
        
        default_prefs = {
            "language": "en",
            "timezone": "UTC",
            "study_reminder": True
        }
        
        cursor.execute("""
            INSERT INTO student_preferences 
            (user_id, theme, ai_tutor_mode, show_citations, enable_notifications, preferences)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, 'light', 'balanced', 1, 1, json.dumps(default_prefs)))
        
        conn.commit()
        conn.close()
        
        return self.get_student_preferences(user_id)
    
    def update_student_preferences(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Update student preferences"""
        conn = get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        allowed_fields = ['theme', 'ai_tutor_mode', 'show_citations', 
                         'enable_notifications', 'default_workspace_id']
        
        for field in allowed_fields:
            if field in kwargs:
                updates.append(f"{field} = ?")
                params.append(kwargs[field])
        
        # Handle custom preferences JSON
        if 'preferences' in kwargs:
            updates.append("preferences = ?")
            params.append(json.dumps(kwargs['preferences']))
        
        if updates:
            params.append(user_id)
            cursor.execute(f"""
                UPDATE student_preferences
                SET {', '.join(updates)}
                WHERE user_id = ?
            """, params)
            
            conn.commit()
        
        conn.close()
        return self.get_student_preferences(user_id)

workspace_service = WorkspaceService()
