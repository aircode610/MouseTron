# LangGraph Studio Setup

This directory contains the configuration for LangGraph Studio, which allows you to visualize and debug your agent.

## Setup

1. Make sure you have installed all dependencies:
   ```bash
   pip install -r ../../requirements.txt
   ```

2. Ensure your `.env` file is in the project root (`../../.env`) with:
   - `ANTHROPIC_API_KEY`
   - `ZAPIER_AUTHORIZATION_TOKEN`
   - `LANGSMITH_TRACING=true`
   - `LANGSMITH_API_KEY`
   - `LANGSMITH_PROJECT`

## Running LangGraph Studio

From this directory (`agent/studio`), run:

```bash
langgraph dev
```

Or if you're using Safari (which blocks localhost):

```bash
langgraph dev --tunnel
```

## Accessing the Studio

Once the server starts, you'll see a URL in the terminal output like:
```
LangGraph Studio Web UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

Open this URL in your browser to interact with your agent.

## Testing the Agent

In LangGraph Studio, you can:
- Visualize the graph structure
- Test the agent with different commands
- Debug step-by-step execution
- View state transitions
- Inspect tool calls and responses

Example initial state to test:
```json
{
  "command": "create a meeting for tuesday 13:00 and send the link to example@gmail.com",
  "plan": [],
  "current_step_id": null,
  "completed": false,
  "final_result": null,
  "available_tools": null,
  "execution_context": {},
  "validation_feedback": null,
  "planning_iterations": 0
}
```

