# Zapier Tools Dataset Scripts

This directory contains scripts for fetching and processing Zapier MCP tools.

## Scripts

### `get_zapier_tools.py`

Fetches all available tools from the Zapier MCP API and saves them to JSON files.

**Usage:**
```bash
python dataset/get_zapier_tools.py
```

**Requirements:**
- `ZAPIER_AUTHORIZATION_TOKEN` environment variable (or in `.env` file)
- Optional: `ANTHROPIC_API_KEY` for fallback method

**Output:**
- `zapier_tools.json` - Full tool definitions with all metadata
- `zapier_tools_simplified.json` - Simplified version with names, descriptions, and input schemas

**Features:**
- Tries multiple MCP protocol methods
- Handles both JSON and SSE (Server-Sent Events) responses
- Falls back to Anthropic API method if direct API fails
- Groups and displays tools by category

### `extract_tool_names.py`

Extracts tool names from the JSON file and saves them to a text file, one name per line.

**Usage:**
```bash
python dataset/extract_tool_names.py
```

**Default behavior:**
- Reads from `zapier_tools.json` (checks dataset directory if not found in current dir)
- Saves to `dataset/zapier_tool_names.txt`

**Custom usage:**
```python
from extract_tool_names import extract_tool_names

# Custom input/output files
extract_tool_names("input.json", "output.txt")
```

## Setup

Make sure you have the required dependencies installed:

```bash
pip install requests anthropic python-dotenv
```

Set up your `.env` file in the project root:

```bash
ZAPIER_AUTHORIZATION_TOKEN=your_token_here
ANTHROPIC_API_KEY=your_key_here  # Optional, for fallback method
```

## Workflow

1. Run `get_zapier_tools.py` to fetch the latest tools from Zapier
2. Run `extract_tool_names.py` to extract just the tool names for easy reference

