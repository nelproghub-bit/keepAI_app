# KeepAI - AI-Powered Learning Workspace

A comprehensive learning assistant that supports multiple AI providers for maximum flexibility. Upload documents, ask questions, generate summaries, create quizzes, and organize your study materials.

## 🎓 New: Dedicated Student Dashboard

KeepAI now includes a **complete student portal** with registration, login, and dashboard!

- **Student Portal**: `student_portal.html` - Register & login with beautiful UI
- **Student Dashboard**: `student_dashboard.html` - Organize courses, customize AI tutor, manage preferences
- **Admin Portal**: `index.html` - System configuration and user management

[📖 Student Portal Guide](STUDENT_PORTAL_GUIDE.md) | [📖 Dashboard Quick Start](STUDENT_QUICK_START.md) | [📚 Full Documentation](STUDENT_DASHBOARD_README.md)

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run database migration (for student dashboard):**
   ```bash
   # If using MySQL/MariaDB
   mysql -u root -p keepai < migrate_student_dashboard.sql
   
   # SQLite users: tables will be created automatically
   ```

3. **Start the backend:**
   ```bash
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Choose your interface:**
   - **Students**: Open `student_portal.html` (register or login)
   - **Admins**: Open `index.html` (system configuration)
   - Or use a local server like VS Code Live Server

### Frontend API URL

The frontend is served as static HTML, so it cannot read `VITE_API_URL` directly through Vite's `import.meta.env`. The shared frontend configuration reads `window.VITE_API_URL` when the hosting environment injects it before `assets/js/config.js` loads. Set it to the backend origin (for example, `https://api.example.com`, without `/api`). If the backend is available from the same origin through a reverse proxy, no override is needed.

5. **For Students - Register:**
   - Click "Register Student" tab
   - Fill out the form (name, email, username, password)
   - See success confirmation modal 🎉
   - Sign in and start learning!

6. **For Students - Demo Login:**
   - Username: `arnel`
   - Password: `password123`

7. **Configure AI provider (Admins only):**
   - Admins: Go to Settings in `index.html`
   - See [AI_SETUP.md](AI_SETUP.md) for detailed configuration

## 🤖 AI Provider Support

KeepAI works with multiple AI providers:

- **🏠 Ollama (Local)** - Privacy-focused, runs on your machine
- **🌐 OpenAI** - GPT models via API
- **🧠 Anthropic Claude** - Advanced reasoning capabilities  
- **✨ Google Gemini** - Google's latest AI models

Choose the provider that best fits your needs for privacy, cost, and performance.

## ✨ Features

### Student Dashboard Features (NEW!)
- **🗂️ Workspace Organization** - Create separate workspaces for different courses
- **⚙️ Student Settings** - Customize AI tutor mode, theme, and preferences
- **🎨 Personalization** - Choose colors and icons for your workspaces
- **📚 Document Collections** - Organize materials by course or subject
- **🔒 Student-Only Access** - Focused interface without admin distractions

### Core Functionality
- **📚 Document Library** - Upload and organize PDF materials
- **🤔 AI Tutor** - Ask questions about your documents with RAG
- **📝 Smart Summaries** - Generate structured study notes
- **🎯 Practice Quizzes** - Create multiple-choice exams
- **📋 Study Planner** - Organize study sessions
- **📊 Progress Tracking** - Monitor learning activity

### AI-Powered Features
- **Document Q&A** - Get answers grounded in your materials
- **Intelligent Summarization** - Extract key concepts automatically
- **Quiz Generation** - Create practice questions from content
- **Multi-Provider Support** - Switch between AI services seamlessly
- **Local Privacy Option** - Keep data private with Ollama

### Interface Features
- **Responsive Design** - Works on desktop and mobile
- **Real-time Status** - Monitor AI connection health
- **Multiple Learning Modes** - Flashcards, quizzes, summaries
- **Session Persistence** - Save progress locally

## 🛠️ Setup Options

### Option 1: Local AI with Ollama (Recommended)
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull models
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text

# No additional configuration needed!
```

### Option 2: Cloud AI Providers
Create a `.env` file and add your API key:
```env
# For OpenAI
AI_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here

# For Anthropic
AI_PROVIDER=anthropic  
ANTHROPIC_API_KEY=your_api_key_here

# For Google Gemini
AI_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
```

## 📁 API Endpoints

The backend provides these REST endpoints:

- `GET /api/health` - Service health check
- `GET /api/ai-status` - AI provider status and configuration
- `POST /api/documents/upload` - Upload and index documents
- `POST /api/tutor/ask` - Ask questions with RAG
- `POST /api/learning/summary` - Generate summaries
- `POST /api/learning/quiz` - Generate practice quizzes

## 🔧 Configuration

### Environment Variables
```env
# AI Provider (ollama, openai, anthropic, gemini)
AI_PROVIDER=ollama

# Ollama Settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text

# Storage
CHROMA_PATH=./data/chroma
```

### Frontend Settings
- **API URL**: Backend endpoint (default: http://127.0.0.1:8000/api)
- **Student ID**: Demo user identifier (prototype only)

## 🏗️ Architecture

```
Frontend (HTML/JS) → FastAPI Backend → AI Provider
                                    ↓
                   Document Storage (ChromaDB/File-based)
```

- **Frontend**: Single-page app with responsive design
- **Backend**: FastAPI with modular router structure
- **AI Layer**: Abstracted service supporting multiple providers
- **Storage**: Vector database for document retrieval

## 🚦 Current Status

**Working Features:**
- ✅ Multiple AI provider support
- ✅ Document upload and text extraction
- ✅ Question answering with document context
- ✅ Summary generation
- ✅ Quiz creation and scoring
- ✅ Study planning and progress tracking
- ✅ Responsive web interface

**In Development:**
- 🔄 Enhanced vector embeddings for all providers
- 🔄 DOCX/PPTX document support
- 🔄 Advanced flashcard generation
- 🔄 User authentication system
- 🔄 Cloud deployment configurations

## 📋 Requirements

- **Python**: 3.8+ 
- **Backend**: FastAPI, Uvicorn, Requests
- **AI**: One of Ollama, OpenAI, Anthropic, or Gemini
- **Storage**: File system (ChromaDB optional)
- **Frontend**: Modern web browser

## 🔐 Privacy & Security

- **Local AI**: With Ollama, all processing stays on your machine
- **API Keys**: Stored securely in environment variables
- **Document Data**: Processed locally or sent to chosen AI provider
- **User Data**: Demo mode only - implement authentication for production

## 📖 Documentation

- [AI Setup Guide](AI_SETUP.md) - Detailed AI provider configuration
- [.env.example](.env.example) - Environment configuration template

## 🤝 Contributing

This is a learning assistant prototype. Areas for contribution:
- Additional AI provider integrations
- Enhanced document processing
- Mobile app development
- Advanced learning analytics
- Production deployment guides

## 📄 License

Open source project for educational purposes. Check individual AI provider terms for commercial use.

---

**KeepAI** - Making AI-powered learning accessible to everyone, with the privacy and provider choice you deserve.
