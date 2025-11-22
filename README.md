# LangGraph Agent with MCP

A LangGraph-based agent that plans and executes tasks step-by-step using Anthropic's Claude API with Zapier MCP tools. Includes LangSmith tracing for observability.

## Features

- **LangGraph Workflow**: Uses LangGraph for stateful, graph-based agent orchestration
- **Planning Phase**: Breaks down commands into executable steps
- **Execution Phase**: Runs steps sequentially, updating status as it goes
- **MCP Integration**: Uses Zapier MCP tools via Anthropic API
- **LangSmith Tracing**: Full observability with automatic tracing of all agent operations

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root with your credentials:
```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ZAPIER_AUTHORIZATION_TOKEN=your_zapier_authorization_token_here
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=MouseTron
```

Or set environment variables:
```bash
export ANTHROPIC_API_KEY=your_api_key_here
export ZAPIER_AUTHORIZATION_TOKEN=your_zapier_token_here
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=your_langsmith_api_key_here
export LANGSMITH_PROJECT=MouseTron
```

On Windows:
```powershell
$env:ANTHROPIC_API_KEY="your_api_key_here"
$env:ZAPIER_AUTHORIZATION_TOKEN="your_zapier_token_here"
$env:LANGSMITH_TRACING="true"
$env:LANGSMITH_API_KEY="your_langsmith_api_key_here"
$env:LANGSMITH_PROJECT="MouseTron"
```

**Note**: Get your LangSmith API key from [https://smith.langchain.com](https://smith.langchain.com)

## Usage

Run the agent with a command:

```python
from agent import LangGraphAgent

agent = LangGraphAgent()
result = agent.run("create a meeting for tuesday 13:00 and send the link to example@gmail.com")
```

Or use the main script:

```bash
python main.py
```

## How It Works

The agent uses LangGraph to orchestrate a three-node workflow:

1. **Discover Tools**: Queries the MCP server to discover available tools
2. **Planning Phase**: The agent analyzes the command and breaks it down into specific, actionable steps
3. **Execution Phase**: Each step is executed one by one:
   - Step status is updated (pending → in_progress → completed/failed)
   - Results from each step are passed as context to subsequent steps
   - Execution stops if any step fails

All operations are automatically traced in LangSmith for debugging and monitoring.

## Example

Input:
```json
{"text": "create a meeting for tuesday 13:00 and send the link to example@gmail.com"}
```

The agent will:
1. Plan steps (e.g., "Create calendar event", "Send email with link")
2. Execute each step sequentially
3. Update step statuses and collect results

