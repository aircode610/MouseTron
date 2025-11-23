# MouseTron

MouseTron is an intelligent task automation system that combines a LangGraph-based agent, a Logitech Loupedeck plugin, and an Efficient Memory Algorithm (EMA) to learn from user interactions and automate repetitive tasks.

## Project Overview

MouseTron consists of three main components:

1. **Agent** - A LangGraph-based agent that breaks down tasks into steps and executes them using MCP (Model Context Protocol) tools
2. **Logitech Plugin (C#)** - A Loupedeck plugin that tracks text selection, sends commands to the server, and displays recommendations
3. **EMA Algorithm** - An Efficient Memory Algorithm that finds patterns in user interactions and generates personalized recommendations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Logitech Loupedeck Plugin (C#)           │
│  - Tracks selected text from applications                    │
│  - Sends commands to Python server                          │
│  - Displays recommendations from EMA                         │
│  - Manages server lifecycle                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP POST/GET
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Server (server.py)                 │
│  - Receives commands from plugin                            │
│  - Orchestrates agent execution                             │
│  - Updates EMA with tool usage patterns                     │
│  - Generates recommendations                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                            │
        ▼                            ▼
┌──────────────┐            ┌──────────────────┐
│   Agent      │            │   EMA Algorithm   │
│ (agent.py)   │            │    (EMA.py)      │
│              │            │                  │
│ - Plans      │            │ - Tracks patterns│
│ - Executes   │            │ - Generates      │
│ - Uses MCPs  │            │   recommendations│
└──────────────┘            └──────────────────┘
```

---

## Component 1: Agent System

### Overview

The agent system (`agent/`) is a LangGraph-based intelligent agent that:
- Breaks down natural language commands into executable steps
- Executes tasks using Zapier MCP (Model Context Protocol) tools
- Maintains execution context across steps
- Validates plans before execution

### Key Files

- **`agent/agent.py`** - Main agent implementation with LangGraph workflow
- **`agent/main.py`** - Entry point for testing the agent
- **`agent/graph.py`** - Exposes the graph for LangGraph Studio

### How It Works

1. **Tool Discovery** (`fetch_tools`):
   - Queries the Zapier MCP server to discover available tools
   - Caches tool schemas for planning and execution
   - Falls back to local tool definitions if MCP is unavailable

2. **Command Summarization** (`summarize_command`):
   - Analyzes long or unclear commands
   - Extracts actionable tasks from conversations
   - Preserves important details (dates, emails, names)

3. **Planning Phase** (`plan_phase`):
   - Analyzes the command and available tools
   - Creates a step-by-step execution plan
   - Each step includes:
     - `id`: Sequential step number
     - `description`: Human-readable description
     - `tool_name`: Exact tool name to execute
     - `tool_args`: Parameters for the tool
     - `status`: Execution status (pending/in_progress/completed/failed)

4. **Plan Validation** (`validate_plan`):
   - Checks for missing intermediate steps
   - Verifies tool names match available tools
   - Ensures logical flow between steps
   - Can trigger replanning if issues are found

5. **Execution Phase** (`execute_phase`):
   - Executes each step sequentially
   - Updates step status as execution progresses
   - Passes results from previous steps as context to subsequent steps
   - Stops execution if any step fails

### Features

- **Tool Name Detection**: Automatically detects when commands contain explicit tool names
- **Context Summarization**: Reduces token usage by summarizing large execution contexts
- **Structured Output Extraction**: Extracts JSON data from tool responses for use in subsequent steps
- **LangSmith Tracing**: All operations are automatically traced for observability

### Example Workflow

**Input**: "create a meeting for tuesday 13:00 and send the link to example@gmail.com"

**Plan**:
1. Create calendar event for Tuesday 13:00 → `zapier_google_calendar_create_event`
2. Get meeting link from created event → `zapier_google_calendar_get_event`
3. Send email with meeting link → `zapier_gmail_send_email`

**Execution**: Each step executes sequentially, with step 2 using the event ID from step 1, and step 3 using the link from step 2.

---

## Component 2: Logitech Plugin (C#)

### Overview

The Logitech plugin (`MouseTronPlugin/`) is a Loupedeck plugin written in C# that:
- Tracks text selection from any application
- Sends selected text and application context to the Python server
- Displays recommendations from the EMA algorithm
- Manages the Python server lifecycle

### Key Files

- **`MouseTronPlugin/src/MouseTronPlugin.cs`** - Main plugin class
- **`MouseTronPlugin/src/Services/ServerManagementService.cs`** - Manages Python server process
- **`MouseTronPlugin/src/Services/StepsPollingService.cs`** - Polls server for execution status
- **`MouseTronPlugin/src/Actions/SendTextAction.cs`** - Sends selected text to server
- **`MouseTronPlugin/src/Actions/FirstRecentAction.cs`** - Displays most recent recommendation
- **`MouseTronPlugin/src/Actions/FirstMostUsedAction.cs`** - Displays most used recommendation

### How It Works

1. **Server Management**:
   - Automatically starts `server.py` when plugin loads
   - Finds Python executable (checks virtual environment first, then system Python)
   - Finds a free port and starts the server
   - Monitors server health and restarts if needed
   - Stops server when plugin unloads

2. **Text Selection Tracking**:
   - `SendTextAction`: User selects text and triggers the action
   - Copies selected text using platform-specific methods (AppleScript on macOS, PowerShell on Windows)
   - Gets current application name
   - Sends POST request to server with:
     ```json
     {
       "selectedText": "selected text here",
       "applicationName": "Chrome",
       "input": "optional user feedback"
     }
     ```

3. **Recommendation Display**:
   - `FirstRecentAction`: Reads `recommendations/recent_tool_single_1.json`
   - `FirstMostUsedAction`: Reads `recommendations/stable_tools_combo_1.json`
   - Updates action display names and descriptions dynamically
   - Allows users to execute recommended actions with additional input

4. **Status Polling**:
   - `StepsPollingService`: Polls `/api/steps` endpoint every 2 seconds
   - Displays current execution status in plugin notifications
   - Shows step-by-step progress as agent executes

### Platform Support

- **macOS**: Uses AppleScript for text selection and clipboard operations
- **Windows**: Uses PowerShell for text selection and clipboard operations
- **Cross-platform**: Server management works on both platforms

---

## Component 3: EMA Algorithm

### Overview

The EMA (Efficient Memory Algorithm) (`EMA.py`) is a pattern recognition system that:
- Tracks tool usage patterns from agent executions
- Identifies frequently used tool combinations
- Generates personalized recommendations based on:
  - Recent usage patterns (last k blocks)
  - Stable patterns from frequency table
  - Recently used single tools

### Key Concepts

- **Blocks**: A sequence of tools executed together (e.g., "zapier_gmail_send_email, zapier_google_calendar_create_event")
- **Subsequences**: Ordered subsets of tools from a block (maintains order but allows skipping)
- **Frequency Table**: Tracks how often each subsequence appears across all blocks
- **Recent Blocks**: Last k blocks (default: 10) for short-term pattern recognition
- **Estimation Function**: Combines frequency and recency to prioritize patterns

### Parameters

- **k**: Number of recent blocks to track (default: 10)
- **t**: Maximum size of frequency table (default: 50)
- **nr**: Number of recommendations from recent blocks (default: 2)
- **nf**: Number of recommendations from frequency table (default: 5)
- **ns**: Number of single tool recommendations (default: 5)

### How It Works

1. **Block Addition**:
   - When agent completes execution, tool names are extracted
   - Tools are converted to a comma-separated block string
   - Block is added to recent blocks (deque with maxlen=k)
   - All subsequences are generated and tracked

2. **Subsequence Generation**:
   - For block [A, B, C], generates: [A], [B], [C], [A,B], [A,C], [B,C], [A,B,C]
   - Maintains order but allows skipping elements
   - Tracks both single tools and combinations

3. **Frequency Tracking**:
   - Updates frequency table for all subsequences across all blocks
   - Tracks frequency count and last usage index
   - Uses estimation function for eviction when table exceeds size t

4. **Recommendation Generation**:
   - **Recent Recommendations** (`pick_from_recent`):
     - Analyzes subsequences from last k blocks
     - Sorts by frequency × length (prioritizes longer, frequent patterns)
     - Returns top nr recommendations
   
   - **Stable Recommendations** (`pick_from_frequency`):
     - Analyzes all subsequences in frequency table
     - Sorts by frequency × length
     - Returns top nf recommendations
   
   - **Single Tool Recommendations** (`get_recent_single_tools`):
     - Tracks recently used individual tools
     - Returns ns most recently used tools

5. **Persistence**:
   - Saves all containers to JSON files in `containers/` directory:
     - `name_to_number.json` - Tool name to number mapping
     - `number_to_name.json` - Reverse mapping
     - `recent_blocks.json` - Recent k blocks
     - `frequency_table.json` - Frequency table
     - `all_blocks.json` - All blocks ever processed
     - `recent_single_tools.json` - Recently used single tools
   - Loads containers on initialization for persistence across sessions

### Recommendation Files

EMA generates JSON files in `recommendations/` directory:
- `recent_tools_combo_1.json` to `recent_tools_combo_{nr}.json` - Recent tool combinations
- `recent_tool_single_1.json` to `recent_tool_single_{ns}.json` - Recent single tools
- `stable_tools_combo_1.json` to `stable_tools_combo_{nf}.json` - Stable tool combinations

Each file contains:
```json
[
  {
    "tool_name": "zapier_gmail_send_email",
    "description": "Send an email message"
  }
]
```

---

## Setup Instructions

### Prerequisites

1. **Python 3.8+** with pip
2. **Node.js** and npm (for Electron popup)
3. **.NET 8.0 SDK** (for building the C# plugin)
4. **Logitech Loupedeck** device and Logi Plugin Service installed
5. **API Keys**:
   - Anthropic API key (for Claude API)
   - Zapier Authorization Token (for MCP tools)
   - LangSmith API key (optional, for tracing)

### Step 1: Python Environment Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd MouseTron
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Create `.env` file** in the project root:
   ```bash
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ZAPIER_AUTHORIZATION_TOKEN=your_zapier_authorization_token_here
   LANGSMITH_TRACING=true
   LANGSMITH_API_KEY=your_langsmith_api_key_here
   LANGSMITH_PROJECT=MouseTron
   ```

   **Note**: Get your LangSmith API key from [https://smith.langchain.com](https://smith.langchain.com)

### Step 2: Build the C# Plugin

1. **Install .NET 8.0 SDK**:
   - Download from [https://dotnet.microsoft.com/download](https://dotnet.microsoft.com/download)

2. **Build the plugin**:
   ```bash
   cd MouseTronPlugin
   dotnet build
   ```

   The build process will:
   - Compile the plugin DLL
   - Copy package files
   - Create a plugin link file in the Logi Plugin Service directory
   - Attempt to reload the plugin automatically

3. **Verify plugin installation**:
   - Open Logi Plugin Service
   - Check that "MouseTron" plugin appears in the list
   - Plugin should automatically start the Python server on load

### Step 3: Electron Popup Setup (Optional)

The Electron popup provides a UI for viewing agent execution status.

1. **Navigate to electron-popup directory**:
   ```bash
   cd electron-popup
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **The popup will be launched automatically** by the server when a request is received.

### Step 4: Initialize EMA with Showcase Patterns (Optional)

If you have a `dataset/recommendation_showcase_patterns.txt` file with example patterns:

1. **The server will automatically load patterns** on startup if the file exists
2. **Patterns should be one per line**, comma-separated tool names:
   ```
   zapier_gmail_send_email, zapier_google_calendar_create_event
   zapier_slack_send_message
   zapier_gmail_send_email, zapier_google_drive_create_file
   ```

### Step 5: Verify Installation

1. **Start the server manually** (for testing):
   ```bash
   python server.py -p 8080
   ```

2. **Check that the server starts** and shows:
   ```
   Listening on http://localhost:8080
   EMA initialized successfully
   ```

3. **Test the agent**:
   ```bash
   python agent/main.py
   ```

4. **In Logi Plugin Service**:
   - Verify MouseTron plugin is loaded
   - Check that actions are available:
     - "Send Text"
     - "Most Recent Action"
     - "Most Used Action"

---

## Usage

### Using the Plugin

1. **Select text** in any application (browser, email, chat, etc.)
2. **Press the "Send Text" action** on your Loupedeck device
3. **Optionally provide feedback** in the popup dialog (e.g., "meeting duration is 1 hour")
4. **Agent executes** the task step-by-step
5. **View progress** in plugin notifications or Electron popup

### Using Recommendations

1. **Most Recent Action**: Shows the most recently used tool/pattern
   - Press the action button
   - Enter additional context if needed
   - Agent executes with the recommended tool

2. **Most Used Action**: Shows the most frequently used stable pattern
   - Press the action button
   - Enter additional context if needed
   - Agent executes with the recommended pattern

### Direct API Usage

You can also interact with the server directly via HTTP:

**Send a command**:
```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "selectedText": "create a meeting for tomorrow at 2pm",
    "applicationName": "Chrome",
    "input": "meeting duration is 1 hour"
  }'
```

**Check execution status**:
```bash
curl http://localhost:8080/api/steps
```

---

## Configuration

### Server Configuration

Server configuration is done via command-line arguments:

```bash
python server.py -p 8080  # Specify port (default: 8080)
```

### Plugin Configuration

Plugin settings can be configured in Logi Plugin Service:
- `PostUrl`: Custom POST endpoint URL
- `GetUrl`: Custom GET endpoint URL for steps
- `PollingInterval`: Polling interval in milliseconds (default: 2000)
- `InputPostUrl`: Custom POST endpoint for input actions

### EMA Configuration

EMA parameters can be adjusted in `server.py`:

```python
_ema = EMA(
    k=10,   # Recent blocks to track
    t=50,   # Max frequency table size
    nr=2,   # Recent recommendations
    nf=5,   # Stable recommendations
    ns=5    # Single tool recommendations
)
```

---

## File Structure

```
MouseTron/
├── agent/                      # Agent system
│   ├── agent.py               # Main agent implementation
│   ├── main.py                # Entry point
│   ├── graph.py               # LangGraph export
│   └── studio/                # LangGraph Studio config
├── MouseTronPlugin/           # C# Loupedeck plugin
│   ├── src/
│   │   ├── MouseTronPlugin.cs
│   │   ├── Actions/           # Plugin actions
│   │   ├── Services/          # Server management
│   │   └── Helpers/           # Utility classes
│   └── package/               # Plugin metadata
├── containers/                 # EMA persistence files
│   ├── name_to_number.json
│   ├── frequency_table.json
│   └── ...
├── recommendations/            # Generated recommendations
│   ├── recent_tools_combo_1.json
│   ├── stable_tools_combo_1.json
│   └── ...
├── dataset/                   # Tool definitions and patterns
│   ├── zapier_tools.json
│   └── recommendation_showcase_patterns.txt
├── electron-popup/            # Electron UI for status
├── EMA.py                     # EMA algorithm
├── server.py                   # HTTP server
├── requirements.txt           # Python dependencies
└── README.md                   # This file
```

---

## Troubleshooting

### Server Won't Start

1. **Check Python installation**:
   ```bash
   python --version  # Should be 3.8+
   ```

2. **Check virtual environment** (if using):
   ```bash
   which python  # Should point to venv
   ```

3. **Check environment variables**:
   ```bash
   echo $ANTHROPIC_API_KEY
   echo $ZAPIER_AUTHORIZATION_TOKEN
   ```

4. **Check server logs**:
   - macOS: `~/Library/Application Support/Logi/LogiPluginService/Logs/plugin_logs/MouseTron.log`
   - Windows: `%LOCALAPPDATA%\Logi\LogiPluginService\Logs\plugin_logs\MouseTron.log`

### Plugin Not Loading

1. **Check .NET SDK**:
   ```bash
   dotnet --version  # Should be 8.0+
   ```

2. **Rebuild plugin**:
   ```bash
   cd MouseTronPlugin
   dotnet clean
   dotnet build
   ```

3. **Check plugin link file**:
   - macOS: `~/Library/Application Support/Logi/LogiPluginService/Plugins/MouseTronPlugin.link`
   - Windows: `%LOCALAPPDATA%\Logi\LogiPluginService\Plugins\MouseTronPlugin.link`

### Agent Not Executing

1. **Check MCP connection**:
   - Verify Zapier authorization token is correct
   - Check Anthropic API key is valid

2. **Check tool discovery**:
   - Look for "Fetched X tools" message in logs
   - Verify `dataset/zapier_tools.json` exists as fallback

3. **Check LangSmith** (if using):
   - Verify API key is correct
   - Check project name matches `LANGSMITH_PROJECT`

### EMA Not Generating Recommendations

1. **Check containers directory**:
   ```bash
   ls containers/  # Should contain JSON files
   ```

2. **Check recommendations directory**:
   ```bash
   ls recommendations/  # Should contain JSON files after first execution
   ```

3. **Verify tool names are being extracted**:
   - Check server logs for "Extracted X tool names"
   - Verify agent is completing successfully

---

## Development

### Running Tests

```bash
# Test agent directly
python agent/main.py

# Test server
python server.py -p 8080

# Test EMA
python EMA.py
```

### LangGraph Studio

Visualize and debug the agent workflow:

```bash
langgraph dev
```

Then open [http://localhost:8123](http://localhost:8123)

### Adding New Actions

1. Create a new class in `MouseTronPlugin/src/Actions/`
2. Inherit from `PluginDynamicCommand`
3. Implement `RunCommand` method
4. Register in `MouseTronApplication.cs`

---

## License

[Add your license here]

---

## Contributing

[Add contribution guidelines here]
