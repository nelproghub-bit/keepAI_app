# KeepAI - AI Integration Setup Guide

KeepAI now supports multiple AI providers for maximum flexibility and choice. Choose the option that works best for your needs.

## Quick Start

1. **Start the backend server:**
   ```bash
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Open the web interface:**
   - Open `index.html` in your browser or use a local server
   - Go to Settings to test your AI connection

## AI Provider Options

### Option 1: Ollama (Recommended - Local & Private)

**Advantages:**
- Complete privacy - all processing stays local
- No API costs
- Works offline
- Open source models

**Setup:**
1. Install Ollama from https://ollama.ai/
2. Pull a chat model: `ollama pull qwen2.5-coder:7b`
3. Pull an embedding model: `ollama pull nomic-embed-text`
4. The app will automatically detect and use Ollama

**Configuration in `.env`:**
```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

### Option 2: OpenAI API

**Advantages:**
- High-quality GPT models
- Fast response times
- Reliable service

**Setup:**
1. Get API key from https://platform.openai.com/api-keys
2. Update `.env` file:
```env
AI_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-3.5-turbo
```

### Option 3: Anthropic Claude

**Advantages:**
- Large context windows
- Excellent reasoning capabilities
- Safety-focused

**Setup:**
1. Get API key from https://console.anthropic.com/
2. Update `.env` file:
```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-3-haiku-20240307
```

### Option 4: Google Gemini (Active)

**Advantages:**
- High speed and accuracy
- Cloud-hosted (no local GPU/RAM requirement)
- Full vector embeddings and streaming support

**Setup:**
1. Get API key from Google AI Studio
2. Update `.env` file:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_EMBED_MODEL=gemini-embedding-2
GEMINI_PROJECT_ID=705469087575
```

## Features by Provider

| Feature | Gemini | Ollama | OpenAI | Anthropic |
|---------|--------|--------|---------|-----------|
| Chat/Q&A | ✅ | ✅ | ✅ | ✅ |
| Summaries | ✅ | ✅ | ✅ | ✅ |
| Quizzes | ✅ | ✅ | ✅ | ✅ |
| Document Embeddings | ✅ | ✅ | ❌* | ❌* |
| Privacy | Cloud | Local | Cloud | Cloud |
| Cost | Free/Pay | Free | Pay-per-use | Pay-per-use |

*Note: Embeddings for document retrieval work with Google Gemini and Ollama. Other providers fall back to keyword retrieval.

## Troubleshooting

### "Could not connect to the KeepAI API"
- Make sure the FastAPI server is running on port 8000
- Check the API URL in Settings matches your server

### "Ollama unavailable"
- Install Ollama from https://ollama.ai/
- Make sure it's running: `ollama list`
- Pull required models: `ollama pull qwen2.5-coder:7b`

### "API key not configured"
- Add your API key to the `.env` file
- Restart the backend server after changes

### Server won't start
- Install dependencies: `pip install -r requirements.txt`
- Check Python version (3.8+ required)
- Make sure port 8000 is not in use

## Model Recommendations

### For Ollama (Local):
- **Small/Fast:** `qwen2.5-coder:1.5b`
- **Balanced:** `qwen2.5-coder:7b` (recommended)
- **Large/Accurate:** `qwen2.5-coder:32b`

### For OpenAI:
- **Cost-effective:** `gpt-3.5-turbo`
- **High-quality:** `gpt-4o-mini`
- **Latest:** `gpt-4o`

### For Anthropic:
- **Fast:** `claude-3-haiku-20240307`
- **Balanced:** `claude-3-5-sonnet-20241022`
- **Advanced:** `claude-3-5-sonnet-20241022`

### For Gemini:
- **Fast:** `gemini-1.5-flash`
- **Advanced:** `gemini-1.5-pro`

## Security Notes

- API keys are stored in environment variables only
- Local Ollama provides the best privacy
- Cloud APIs send data to external services
- Use `.env` file for sensitive configuration
- Never commit API keys to version control