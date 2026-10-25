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

### Production Deployment

The frontend is static HTML. `vercel.json` runs `node scripts/build-frontend.mjs`, which reads `VITE_API_URL` at build time, writes it into the shared frontend config, and outputs the deployable site to `dist/`. The FastAPI frontend routes serve these built assets when available. Vercel's `VERCEL_GIT_COMMIT_SHA` is used as the app version and service-worker cache version, so each new commit deployment shows students and admins a one-time update notice with a reload action. Local builds fall back to `http://localhost:8000`; deployment builds require an HTTPS `VITE_API_URL`.

1. Use the Neon project `keepai-userdb` in AWS US West 2 (Oregon) for persistent PostgreSQL storage. Set its pooled connection string as the Render `DATABASE_URL` secret; never commit the URL.
2. Configure Render with `DB_TYPE=postgres` and the Neon `DATABASE_URL`, then redeploy. PostgreSQL stores accounts, extracted study text, and embeddings across free-service restarts. The original uploaded file itself is not retained; re-upload it if you need the original file again.
3. In Vercel, set `VITE_API_URL` to the Render backend origin (for example, `https://keep-ai-api.onrender.com`, without `/api`), then redeploy. Vercel builds fail intentionally if this variable is missing.
4. Keep `ALLOWED_ORIGINS` on Render set to `https://keep-ai-app.vercel.app` and any local development origins needed. Separate origins with commas. The backend also permits the project's stable `keep-ai-app` and `keep-ai-app-git-main` Vercel aliases for admin sign-in; set `ALLOWED_ORIGIN_REGEX` if these Vercel aliases change. Per-deployment preview URLs are intentionally not trusted with production login.
5. Configure the Google OAuth web client from `GOOGLE_OAUTH_CLIENT_ID` with `https://keep-ai-app.vercel.app` and any stable Vercel sign-in alias under **Authorized JavaScript origins**. The Google client ID is public; never expose or commit its client secret. Google sign-in verifies ID tokens with Google before linking or creating accounts.

`requirements.txt` pins backend dependencies and includes the PostgreSQL driver. Local development continues to use SQLite by default; hosted PostgreSQL is selected with `DB_TYPE=postgres` and `DATABASE_URL`.
Accounts previously written to the Render free service's temporary SQLite file are not automatically migrated. Users may need to register again once after PostgreSQL is connected.
If `DB_TYPE=mysql` or `DB_TYPE=mariadb` is configured locally, start MySQL in the XAMPP Control Panel before signing in. When that database is unavailable, the backend may fall back to SQLite for other operations, but admin sign-in reports the database outage instead of rejecting credentials against a different database.

KeepAI is distributed as a web app that can be installed from a supported browser.

### Push notifications

Students and admins can opt in per device from the dashboard notification area. Admin announcements are sent to opted-in devices even when KeepAI is not open; they remain available in the in-app announcements list as well. Push is supported by browsers that implement the Web Push API and requires HTTPS (localhost is allowed for development). On iOS, users need a home-screen-installed web app and a supported iOS version.

The backend derives a stable, domain-separated VAPID key pair from the required `JWT_SECRET_KEY`, so no additional Render secret setup is needed for push. Optionally set `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` together to provide a dedicated key pair, and set `VAPID_SUBJECT` to your application contact. Keep any private key secret and never put it in frontend variables or source control. Use the same pair for every backend instance. If you rotate `JWT_SECRET_KEY` while using the derived pair, devices will need to subscribe again.

To create a dedicated P-256 VAPID pair:

```bash
python -c "import base64; from py_vapid import Vapid; from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat; v=Vapid(); v.generate_keys(); e=lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode(); print('VAPID_PUBLIC_KEY='+e(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))); print('VAPID_PRIVATE_KEY='+e(v.private_key.private_numbers().private_value.to_bytes(32, 'big')))"
```

Configure the generated URL-safe base64 public and private values in the backend environment (for example, Render). New subscriptions are stored per user and device; users can disable each device separately.

AI Tutor conversations are saved to the configured database under the signed-in student's account. Students can reopen individual conversations, delete a chat, or clear all saved chat history from the Chat History panel. The Clear Chat action starts a fresh conversation without removing saved history.

Local database and document files under `data/` are ignored and no longer tracked in the current Git tree; local copies remain on disk. Earlier commits still contain those files, so sanitize Git history if this repository is public or those files contained private data.

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
- **🗂️ Workspace Organization** - Create workspaces with preset or custom course categories
- **⚙️ Student Settings** - Customize AI tutor mode, theme, and preferences
- **🎨 Personalization** - Automatically match professional icons to custom workspace categories
- **📣 App Announcements and Push Alerts** - Admins can publish update-required, maintenance, and general notices to all users; users can opt in to receive browser push notifications per device.
- Admin announcements are published from **Admin Dashboard → Announcements**; they appear in the in-app notification list and are pushed to subscribed devices, including when KeepAI is closed.
- **📚 Document Collections** - Organize materials by course or subject
- **🔒 Student-Only Access** - Focused interface without admin distractions

### Admin Dashboard Features
- **⚙️ Admin Settings** - Update the administrator password, choose a light/dark/system theme, manage push notifications, control new student registration, and enable system maintenance mode.
- Student registration changes are enforced by the API for password and Google sign-ups; existing student accounts can still sign in.
- Maintenance mode pauses public/student pages and non-admin API access while keeping the admin portal available. Disabling it publishes a service-restored announcement and sends push notifications to subscribed devices when configured.

### Core Functionality
- **📚 Document Library** - Upload and organize PDF materials
- **🤔 AI Tutor** - Ask questions about your documents with RAG
- **📝 Smart Summaries** - Generate structured study notes
- **🎯 Practice Quizzes** - Generate identification, multiple-choice, true/false, fill-in-the-blank, and matching questions; mix formats and set a custom count for each (up to 100 total).
- **📋 Study Planner** - Organize study sessions
- **📊 Progress Tracking** - Monitor learning activity

Study progress is tied to the signed-in account and stored in the configured database. Active study time is estimated from visible-page interaction while signed in; quiz averages are calculated only from completed quizzes, and older accounts start building their activity history after this feature is deployed.

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

Quiz questions are generated from the selected document and expose a source excerpt for verification. If the AI cannot provide enough answers supported by that document, generation fails instead of filling the quiz with unrelated questions.

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
