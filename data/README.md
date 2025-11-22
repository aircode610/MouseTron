# Data Directory

This directory stores persistent data files.

## Files

- **`tools_database.db`** - SQLite database containing tool execution history

## Database Schema

The `tool_executions` table stores:
- `id`: Auto-incrementing primary key
- `timestamp`: ISO timestamp
- `steps`: JSON array of tool names
- `step_count`: Number of tools executed
- `created_at`: Human-readable timestamp

## Persistence

The database file persists across service restarts and plugin reloads. Data is never automatically deleted, allowing you to build a historical record of tool usage.

