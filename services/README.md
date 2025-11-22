# Services Directory

This directory contains Python services that run alongside the main server.

## Files

- **`tools_receiver.py`** - Service that receives tool names POST requests and saves them to SQLite database
- **`view_tools_db.py`** - Utility script to view tool executions from the database

## Tools Receiver Service

The tools receiver service:
- Listens on port 8081 (configurable)
- Receives POST requests at `/api/tools` with tool names
- Saves tool executions to `../data/tools_database.db`
- Provides GET endpoint at `/api/tools/recent` to view recent executions

### Starting Manually

```bash
python services/tools_receiver.py
```

Or with custom port:
```bash
python services/tools_receiver.py -p 8082
```

### Viewing Database

```bash
python services/view_tools_db.py
```

Or view all entries:
```bash
python services/view_tools_db.py --all
```

## Database Location

The database is stored in `data/tools_database.db` for persistence. The database persists across service restarts.

## Auto-Start

The tools receiver service is automatically started by the C# plugin when the plugin loads, just like the main server.

