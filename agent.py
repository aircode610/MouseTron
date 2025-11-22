"""LangGraph agent with planning and execution phases."""
import os
import json
import re
import anthropic
from typing import Dict, Any, List, Optional, TypedDict, Annotated
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langsmith import traceable

# Load environment variables from .env file
from pathlib import Path
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)  # override=True ensures env vars are loaded even if already set


# Define state as TypedDict for LangGraph
class AgentState(TypedDict):
    """The state of the agent throughout execution."""
    command: str
    plan: List[Dict[str, Any]]
    current_step_id: Optional[int]
    completed: bool
    final_result: Optional[str]
    available_tools: Optional[str]
    execution_context: Dict[str, Any]


class LangGraphAgent:
    """Agent that plans and executes tasks step by step using LangGraph."""
    
    def __init__(self, api_key: Optional[str] = None, authorization_token: Optional[str] = None):
        """Initialize the agent with Anthropic client."""
        # Get API key from parameter or environment
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key or not api_key.strip():
            raise ValueError(
                "ANTHROPIC_API_KEY must be provided either as parameter or environment variable. "
                f"Current value: {repr(api_key)}"
            )
        
        # Strip whitespace in case there's any
        api_key = api_key.strip()
        
        # Get authorization token from parameter or environment
        auth_token = authorization_token or os.environ.get("ZAPIER_AUTHORIZATION_TOKEN")
        if not auth_token or not auth_token.strip():
            raise ValueError(
                "ZAPIER_AUTHORIZATION_TOKEN must be provided either as parameter or environment variable. "
                f"Current value: {repr(auth_token)}"
            )
        
        # Strip whitespace
        auth_token = auth_token.strip()
        
        self.client = anthropic.Anthropic(api_key=api_key)
        self.mcp_servers = [
            {
                "type": "url",
                "url": "https://mcp.zapier.com/api/mcp/mcp",
                "name": "zapier",
                "authorization_token": auth_token,
            }
        ]
        self.graph = self._build_graph()
    
    @traceable(name="discover_tools")
    def discover_tools(self, state: AgentState) -> AgentState:
        """Discover available tools from MCP servers and return structured information."""
        if state.get("available_tools"):
            return state
        
        print("Discovering available tools...")
        try:
            # Ask for tools in a structured format
            response = self.client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=3000,
                messages=[{
                    "role": "user", 
                    "content": """What tools do you have available from the MCP servers? 

Please provide a detailed list with:
- Tool name
- Description of what the tool does
- Required parameters/arguments
- Example usage

Format the response clearly so it can be used for planning and execution."""
                }],
                mcp_servers=self.mcp_servers,
                betas=["mcp-client-2025-04-04"],
            )
            
            tools_info = response.content[0].text
            state["available_tools"] = tools_info
            return state
        except Exception as e:
            print(f"Warning: Could not discover tools: {e}")
            state["available_tools"] = "Tools discovery failed. Proceeding with general tool knowledge."
            return state
    
    @traceable(name="plan_phase")
    def plan_phase(self, state: AgentState) -> AgentState:
        """Phase 1: Plan the steps needed to accomplish the command."""
        tools_info = state.get("available_tools") or "Tools information not available."
        
        planning_prompt = f"""You need to break down this command into clear, executable steps: "{state['command']}"

Available tools from MCP servers:
{tools_info}

Based on the available tools above, plan the steps. Each step should:
1. Be specific and actionable
2. Use a single tool call per step
3. Be broken down enough that one tool call can accomplish it
4. Reference the exact tool name from the available tools list

Return a JSON list of steps, each with:
- id: sequential number starting from 1
- description: what this step does
- tool_name: the exact name of the tool to use (from the available tools list, or null if unsure)
- tool_args: the arguments for the tool (if known, otherwise null)
- status: "pending"

Example format:
[
  {{"id": 1, "description": "Create a calendar event for Tuesday at 13:00", "tool_name": "create_calendar_event", "tool_args": {{"date": "tuesday", "time": "13:00"}}, "status": "pending"}},
  {{"id": 2, "description": "Send email to example@gmail.com with the meeting link", "tool_name": "send_email", "tool_args": {{"to": "example@gmail.com", "subject": "Meeting Link"}}, "status": "pending"}}
]

Now plan the steps for: "{state['command']}"
"""
        
        response = self.client.beta.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": planning_prompt}],
            mcp_servers=self.mcp_servers,
            betas=["mcp-client-2025-04-04"],
        )
        
        # Extract the plan from the response
        plan_text = response.content[0].text
        
        # Parse the JSON plan
        json_match = re.search(r'\[.*\]', plan_text, re.DOTALL)
        if json_match:
            try:
                steps_data = json.loads(json_match.group())
                # Ensure all steps have status
                for step in steps_data:
                    if "status" not in step:
                        step["status"] = "pending"
                state["plan"] = steps_data
                return state
            except Exception as e:
                print(f"Error parsing JSON plan: {e}")
        
        # Fallback: create steps from description if JSON parsing fails
        lines = plan_text.split('\n')
        steps = []
        step_id = 1
        for line in lines:
            if re.match(r'^\d+[\.\)]', line.strip()):
                desc = re.sub(r'^\d+[\.\)]\s*', '', line.strip())
                steps.append({
                    "id": step_id,
                    "description": desc,
                    "status": "pending",
                    "tool_name": None,
                    "tool_args": None
                })
                step_id += 1
        
        state["plan"] = steps if steps else [{"id": 1, "description": state["command"], "status": "pending", "tool_name": None, "tool_args": None}]
        return state
    
    @traceable(name="execute_step")
    def execute_step(self, step: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """Execute a single step using the MCP tools."""
        # Update step status
        step["status"] = "in_progress"
        
        # Build the execution prompt with tools information
        tools_info = state.get("available_tools") or "Tools information not available."
        context = state.get("execution_context", {})
        context_str = ""
        if context:
            context_str = f"\n\nContext from previous steps: {json.dumps(context, indent=2)}"
        
        execution_prompt = f"""Execute this step: {step['description']}

Available tools from MCP servers:
{tools_info}

{context_str}

Use the appropriate tool from the available tools above to accomplish this step. 
- If a tool_name was specified in the plan, use that exact tool
- If you need information from previous steps, use the context provided
- Make sure to use the correct tool name and provide all required parameters

Return a brief summary of what was done and any important results (like meeting links, confirmation numbers, etc.).
"""
        
        try:
            response = self.client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": execution_prompt}],
                mcp_servers=self.mcp_servers,
                betas=["mcp-client-2025-04-04"],
            )
            
            result_text = response.content[0].text
            step["result"] = result_text
            step["status"] = "completed"
            
        except Exception as e:
            step["status"] = "failed"
            step["error"] = str(e)
        
        return step
    
    @traceable(name="execute_phase")
    def execute_phase(self, state: AgentState) -> AgentState:
        """Phase 2: Execute the plan step by step."""
        if "execution_context" not in state:
            state["execution_context"] = {}
        
        context = state["execution_context"]
        
        for step in state["plan"]:
            if step.get("status") == "pending":
                state["current_step_id"] = step["id"]
                step = self.execute_step(step, state)
                
                # Update the step in the plan
                for i, s in enumerate(state["plan"]):
                    if s["id"] == step["id"]:
                        state["plan"][i] = step
                        break
                
                # Add result to context for next steps
                if step.get("result"):
                    context[f"step_{step['id']}"] = step["result"]
                
                # If step failed, stop execution
                if step.get("status") == "failed":
                    break
        
        state["execution_context"] = context
        
        # Check if all steps are completed
        state["completed"] = all(s.get("status") == "completed" for s in state["plan"])
        
        if state["completed"]:
            state["final_result"] = "All steps completed successfully."
        elif any(s.get("status") == "failed" for s in state["plan"]):
            failed_steps = [s for s in state["plan"] if s.get("status") == "failed"]
            state["final_result"] = f"Execution failed at step {failed_steps[0]['id']}: {failed_steps[0].get('error', 'Unknown error')}"
        
        return state
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow graph."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("discover_tools", self.discover_tools)
        workflow.add_node("plan", self.plan_phase)
        workflow.add_node("execute", self.execute_phase)
        
        # Define the flow: discover -> plan -> execute -> end
        workflow.set_entry_point("discover_tools")
        workflow.add_edge("discover_tools", "plan")
        workflow.add_edge("plan", "execute")
        workflow.add_edge("execute", END)
        
        return workflow.compile()
    
    @traceable(name="run_agent")
    def run(self, command: str) -> AgentState:
        """Run the full agent workflow: discover tools -> plan -> execute."""
        # Initialize state
        initial_state: AgentState = {
            "command": command,
            "plan": [],
            "current_step_id": None,
            "completed": False,
            "final_result": None,
            "available_tools": None,
            "execution_context": {}
        }
        
        # Run the graph - it will handle discover_tools -> plan -> execute
        print("Running agent workflow...")
        print("Phase 1: Discovering tools and planning...")
        state = self.graph.invoke(initial_state)
        
        print(f"\nCreated {len(state['plan'])} steps:")
        for step in state["plan"]:
            print(f"  {step['id']}. {step['description']}")
        
        print("\nPhase 2: Execution completed")
        print("\nExecution Results:")
        for step in state["plan"]:
            status_icon = {
                "completed": "✓",
                "failed": "✗",
                "in_progress": "→",
                "pending": "○"
            }.get(step.get("status"), "?")
            print(f"  {status_icon} Step {step['id']}: {step['description']}")
            if step.get("result"):
                result_preview = step["result"][:100] if len(step["result"]) > 100 else step["result"]
                print(f"     Result: {result_preview}...")
            if step.get("error"):
                print(f"     Error: {step['error']}")
        
        if state.get("final_result"):
            print(f"\nFinal Status: {state['final_result']}")
        
        return state
