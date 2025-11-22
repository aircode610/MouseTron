# Setup Guide

## Directory Structure

```
MouseTron/
├── agent/              # LangGraph agent code
├── data/               # Persistent data (database files)
│   └── tools_database.db
├── services/           # Python services
│   ├── tools_receiver.py
│   └── view_tools_db.py
├── server.py           # Main HTTP server (started by C#)
└── MouseTronPlugin/    # C# Loupedeck plugin
```

## Services Overview

### 1. Main Server (`server.py`)
- Started automatically by C# plugin
- Listens on a dynamically assigned port
- Handles agent execution requests
- POSTs tool names to tools receiver after agent finishes

### 2. Tools Receiver Service (`services/tools_receiver.py`)
- Started automatically by C# plugin
- Listens on port 8081 (or finds free port)
- Receives tool names POST requests
- Saves to SQLite database in `data/tools_database.db`

## Database Persistence

The SQLite database (`data/tools_database.db`) is **persistent**:
- ✅ Survives service restarts
- ✅ Survives plugin reloads
- ✅ Survives system reboots
- ✅ Data is never automatically deleted

The database stores all tool execution history, allowing you to:
- Track which tools are used most frequently
- Analyze tool usage patterns
- Build historical records

## How It Works

1. **Plugin Loads** → C# starts both services:
   - Tools receiver service (port 8081)
   - Main server (dynamic port)

2. **Agent Execution** → When agent finishes:
   - Tool names extracted from agent state
   - POSTed to `http://localhost:8081/api/tools`
   - Saved to database

3. **Viewing Data** → Use utility script:
   ```bash
   python services/view_tools_db.py
   ```

## Manual Service Management

### Start Tools Receiver Manually
```bash
python services/tools_receiver.py
```

### View Database
```bash
python services/view_tools_db.py
python services/view_tools_db.py --all  # View all entries
```

### View Recent Executions via API
```bash
curl http://localhost:8081/api/tools/recent
curl http://localhost:8081/api/tools/recent?limit=5
```

## Environment Variables

The C# plugin automatically sets:
- `TOOLS_POST_URL` - URL where server.py should POST tool names

You can override this in your `.env` file if needed.

## Troubleshooting

### Connection Refused Error
If you see "Connection refused" when posting tool names:
- Ensure tools receiver service is running
- Check that port 8081 is not blocked
- Verify the service started successfully (check C# plugin logs)

### Database Not Found
The database is created automatically on first run. If you see errors:
- Ensure `data/` directory exists and is writable
- Check file permissions

### Port Conflicts
If port 8081 is in use:
- The service will automatically find another free port
- Check C# plugin logs for the actual port used
- The `TOOLS_POST_URL` environment variable is set automatically

