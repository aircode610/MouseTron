"""LangGraph agent with planning and execution phases."""
import os
import json
import re
import anthropic
from typing import Dict, Any, List, Optional, TypedDict, Annotated
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langsmith import traceable

load_dotenv(override=True)  # override=True ensures env vars are loaded even if already set


# Define state as TypedDict for LangGraph
class AgentState(TypedDict):
    """The state of the agent throughout execution."""
    command: str  # The selected text/command from the user
    feedback: Optional[str]  # Additional user feedback/context
    app: Optional[str]  # The app name where the command came from (e.g., "Slack", "Email")
    plan: List[Dict[str, Any]]
    current_step_id: Optional[int]
    completed: bool
    final_result: Optional[str]
    execution_context: Dict[str, Any]
    validation_feedback: Optional[str]  # Feedback from validation node
    planning_iterations: int  # Track how many times we've planned


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
    
    def _get_system_prompt(self, app: Optional[str] = None) -> str:
        """Generate system prompt with optional app context."""
        base_prompt = """You are an intelligent assistant that helps users execute tasks based on text they select from their applications. 

Your role:
- You receive a command (selected text) and optional feedback from the user
- You plan and execute the task step-by-step using available MCP tools
- You consider the context of where the command came from (the application)
- You combine the command and feedback to understand the complete intent
- You execute tasks efficiently and accurately"""

        # Add app context if provided (let LLM interpret the app context)
        if app:
            base_prompt += f"""

Context: The command came from the application "{app}". Consider the typical use case and context of this application when interpreting the command and planning the execution."""
        
        return base_prompt
    
    @traceable(name="plan_phase")
    def plan_phase(self, state: AgentState) -> AgentState:
        """Phase 1: Plan the steps needed to accomplish the command."""
        validation_feedback = state.get("validation_feedback")
        iteration = state.get("planning_iterations", 0) + 1
        command = state.get("command", "")
        feedback = state.get("feedback")
        app = state.get("app")
        
        # Get system prompt with app context
        system_prompt = self._get_system_prompt(app)
        
        # Build planning prompt with feedback if this is a refinement
        validation_section = ""
        if validation_feedback:
            validation_section = f"""

IMPORTANT: Previous validation found issues with the plan. Please address these:
{validation_feedback}

Revise the plan to fix these issues."""
        
        # Combine command and feedback
        user_input = command
        if feedback:
            user_input = f"Command: {command}\n\nAdditional feedback/context: {feedback}"
        
        planning_prompt = f"""{system_prompt}

Task to execute:
{user_input}
{validation_section}

You have access to MCP tools via the Zapier MCP server. The tool schemas (names, descriptions, parameters) are automatically available to you.

CRITICAL: Break down the task into ALL necessary intermediate steps. For example:
- If creating a meeting and sending a link, you need: 1) Create meeting, 2) Get/retrieve the meeting link, 3) Send email with link
- Don't skip steps that require getting information from a previous step's result
- Each step should produce output that can be used by subsequent steps

Based on the available tools above, plan the steps. Each step should:
1. Be specific and actionable
2. Use a single tool call per step
3. Be broken down enough that one tool call can accomplish it
4. Reference the exact tool name from the available tools list
5. Include ALL intermediate steps (e.g., getting a link after creating something, retrieving data before using it)

Return a JSON list of steps, each with:
- id: sequential number starting from 1
- description: what this step does (be very specific)
- tool_name: the exact name of the tool to use (from the available tools list, or null if unsure)
- tool_args: the arguments for the tool (if known, otherwise null)
- status: "pending"

Example format for "create meeting and send link":
[
  {{"id": 1, "description": "Create a calendar event for Tuesday at 13:00", "tool_name": "create_calendar_event", "tool_args": {{"date": "tuesday", "time": "13:00"}}, "status": "pending"}},
  {{"id": 2, "description": "Retrieve the meeting link from the created calendar event", "tool_name": "get_calendar_event_link", "tool_args": {{"event_id": "from_step_1"}}, "status": "pending"}},
  {{"id": 3, "description": "Send email to example@gmail.com with the meeting link", "tool_name": "send_email", "tool_args": {{"to": "example@gmail.com", "subject": "Meeting Link", "body": "Link from step 2"}}, "status": "pending"}}
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
                state["planning_iterations"] = iteration
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
        state["planning_iterations"] = iteration
        return state
        
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
                state["planning_iterations"] = iteration
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
        state["planning_iterations"] = iteration
        return state
    
    def _extract_tool_results(self, response) -> Dict[str, Any]:
        """Extract structured tool results from Anthropic MCP response."""
        tool_results = {}
        
        # Check if response has content blocks
        if hasattr(response, 'content') and response.content:
            for block in response.content:
                # Check for tool use blocks with results
                if hasattr(block, 'type') and block.type == 'tool_use':
                    tool_id = getattr(block, 'id', None)
                    tool_name = getattr(block, 'name', None)
                    if tool_id and tool_name:
                        tool_results[tool_name] = {
                            "id": tool_id,
                            "name": tool_name,
                            "input": getattr(block, 'input', {})
                        }
        
        # Also check for tool result blocks in the response
        # The MCP response might have tool results embedded
        return tool_results
    
    def _extract_structured_output(self, response) -> Optional[Dict[str, Any]]:
        """Extract structured output from MCP tool response."""
        # The MCP tools return structured JSON in the response
        # Check multiple places where the data might be
        structured_output = None
        
        if not hasattr(response, 'content') or not response.content:
            return None
        
        # First, check all text blocks for JSON
        for block in response.content:
            if hasattr(block, 'type'):
                # Check text blocks for JSON
                if block.type == 'text' and hasattr(block, 'text'):
                    text = block.text
                    # Try to extract JSON objects from the text
                    # Look for JSON objects (could be nested)
                    json_matches = re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
                    for match in json_matches:
                        try:
                            parsed = json.loads(match.group())
                            if isinstance(parsed, dict) and len(parsed) > 0:
                                # Prefer larger/more complete JSON objects
                                if not structured_output or len(str(parsed)) > len(str(structured_output)):
                                    structured_output = parsed
                        except:
                            continue
                
                # Check for tool_result blocks (MCP tool results)
                elif block.type == 'tool_result' and hasattr(block, 'content'):
                    content = block.content
                    if isinstance(content, list):
                        for item in content:
                            if hasattr(item, 'text'):
                                try:
                                    parsed = json.loads(item.text)
                                    if isinstance(parsed, dict):
                                        structured_output = parsed
                                        break
                                except:
                                    pass
                    elif isinstance(content, str):
                        try:
                            parsed = json.loads(content)
                            if isinstance(parsed, dict):
                                structured_output = parsed
                        except:
                            pass
        
        return structured_output
    
    @traceable(name="execute_step")
    def execute_step(self, step: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """Execute a single step using the MCP tools."""
        # Update step status
        step["status"] = "in_progress"
        
        # Get system prompt with app context
        app = state.get("app")
        system_prompt = self._get_system_prompt(app)
        
        # Build the execution prompt
        context = state.get("execution_context", {})
        
        # Build comprehensive context string with structured data
        context_str = ""
        if context:
            context_parts = []
            for key, value in context.items():
                if isinstance(value, dict) and "structured_output" in value:
                    # Include both summary and structured data in a clear format
                    summary = value.get('summary', 'N/A')
                    structured = value.get('structured_output')
                    description = value.get('description', '')
                    
                    context_part = f"{key} ({description}):\n"
                    context_part += f"  Summary: {summary}\n"
                    if structured:
                        context_part += f"  Full Structured Output (use this data in your tool calls):\n{json.dumps(structured, indent=4)}"
                    else:
                        context_part += f"  Structured Output: Not available"
                    context_parts.append(context_part)
                else:
                    context_parts.append(f"{key}: {value}")
            
            if context_parts:
                context_str = f"\n\n=== CONTEXT FROM PREVIOUS STEPS ===\n{chr(10).join(context_parts)}\n=== END CONTEXT ===\n"
        
        execution_prompt = f"""Execute this step: {step['description']}

You have access to MCP tools via the Zapier MCP server. The tool schemas are automatically available to you.

{context_str}

Use the appropriate tool from the available tools above to accomplish this step. 
- If a tool_name was specified in the plan, use that exact tool
- If you need information from previous steps, use the structured output data provided in the context above
- Extract specific values from the structured output (e.g., htmlLink, hangoutLink, id, event details, etc.) to use in this step
- Make sure to use the correct tool name and provide all required parameters

IMPORTANT: After the tool executes, the response will include structured data. Please include that full structured output in your response so it can be used by subsequent steps.

Format your response as:
Summary: [brief description of what was done]
Structured Output: [the full JSON/structured data returned by the tool]
"""
        
        try:
            response = self.client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": execution_prompt}
                ],
                mcp_servers=self.mcp_servers,
                betas=["mcp-client-2025-04-04"],
            )
            
            # Extract text summary from all text blocks
            result_text_parts = []
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                    result_text_parts.append(block.text)
            result_text = "\n".join(result_text_parts) if result_text_parts else ""
            
            # Try to extract structured output from the response
            structured_output = self._extract_structured_output(response)
            
            # If we found structured output, also try to extract it from the text as fallback
            if not structured_output and result_text:
                # Look for JSON in the text (more comprehensive search)
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result_text, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, dict) and len(parsed) > 0:
                            structured_output = parsed
                    except:
                        pass
            
            # Store both summary and structured output
            step["result"] = result_text
            step["structured_output"] = structured_output
            step["status"] = "completed"
            
        except Exception as e:
            step["status"] = "failed"
            step["error"] = str(e)
            step["structured_output"] = None
        
        return step
    
    @traceable(name="validate_plan")
    def validate_plan(self, state: AgentState) -> AgentState:
        """Validate the plan for missing steps, ambiguous items, and completeness."""
        plan = state.get("plan", [])
        command = state.get("command", "")
        feedback = state.get("feedback")
        app = state.get("app")
        
        if not plan:
            state["validation_feedback"] = "Plan is empty. Please create a plan with at least one step."
            return state
        
        # Get system prompt with app context
        system_prompt = self._get_system_prompt(app)
        
        # Build validation prompt
        plan_summary = "\n".join([
            f"Step {s['id']}: {s.get('description', 'N/A')} (tool: {s.get('tool_name', 'unspecified')})"
            for s in plan
        ])
        
        user_input = command
        if feedback:
            user_input = f"Command: {command}\nAdditional feedback: {feedback}"
        
        validation_prompt = f"""Review this plan for the task: "{user_input}"

Current plan:
{plan_summary}

You have access to MCP tools via the Zapier MCP server. The tool schemas are automatically available to you.

Check for:
1. Missing intermediate steps (e.g., if creating something and then using its result, is there a step to retrieve/get that result?)
2. Ambiguous steps that need more detail
3. Steps that reference data from previous steps but don't show how to get that data
4. Missing tool assignments
5. Logical gaps between steps

If the plan is complete and all steps are clear, respond with: "APPROVED"

If there are issues, respond with specific feedback in this format:
ISSUES FOUND:
- [Issue 1: specific problem and what step is affected]
- [Issue 2: specific problem and what step is affected]
- [Suggestion: what should be added or changed]

Be thorough - catch missing intermediate steps like getting a link after creating a meeting, retrieving data before using it, etc.
"""
        
        try:
            response = self.client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": validation_prompt}
                ],
                mcp_servers=self.mcp_servers,
                betas=["mcp-client-2025-04-04"],
            )
            
            validation_result = response.content[0].text.strip()
            
            if "APPROVED" in validation_result.upper():
                state["validation_feedback"] = None
                print("✓ Plan validated and approved")
            else:
                state["validation_feedback"] = validation_result
                print(f"⚠ Validation found issues (iteration {state.get('planning_iterations', 0)}):")
                print(validation_result[:200] + "..." if len(validation_result) > 200 else validation_result)
            
        except Exception as e:
            print(f"Warning: Validation failed: {e}")
            # If validation fails, approve by default to avoid infinite loops
            state["validation_feedback"] = None
        
        return state
    
    def should_replan(self, state: AgentState) -> str:
        """Determine if we should replan or proceed to execution."""
        # Check if validation approved the plan
        if state.get("validation_feedback") is None:
            return "execute"
        
        # Check if we've exceeded max iterations
        iterations = state.get("planning_iterations", 0)
        if iterations >= 4:
            print(f"⚠ Max planning iterations ({iterations}) reached. Proceeding with current plan.")
            return "execute"
        
        # Otherwise, replan
        return "plan"
    
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
                
                # Add result to context for next steps (include both summary and structured output)
                if step.get("result") or step.get("structured_output"):
                    context[f"step_{step['id']}"] = {
                        "summary": step.get("result", ""),
                        "structured_output": step.get("structured_output"),
                        "description": step.get("description", "")
                    }
                
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
        """Build the LangGraph workflow graph with validation loop."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("plan", self.plan_phase)
        workflow.add_node("validate", self.validate_plan)
        workflow.add_node("execute", self.execute_phase)
        
        # Define the flow: plan -> validate -> (replan or execute) -> end
        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "validate")
        
        # Conditional edge: validate -> replan (if issues) or execute (if approved)
        workflow.add_conditional_edges(
            "validate",
            self.should_replan,
            {
                "plan": "plan",  # Go back to planning if issues found
                "execute": "execute"  # Proceed to execution if approved
            }
        )
        workflow.add_edge("execute", END)
        
        return workflow.compile()
    
    @traceable(name="run_agent")
    def run(self, command: str, feedback: Optional[str] = None, app: Optional[str] = None) -> AgentState:
        """Run the full agent workflow: plan -> validate -> execute.
        
        Args:
            command: The selected text/command from the user
            feedback: Additional user feedback/context (e.g., meeting duration)
            app: The app name where the command came from (e.g., "Slack", "Email")
        """
        # Initialize state
        initial_state: AgentState = {
            "command": command,
            "feedback": feedback,
            "app": app,
            "plan": [],
            "current_step_id": None,
            "completed": False,
            "final_result": None,
            "execution_context": {},
            "validation_feedback": None,
            "planning_iterations": 0
        }
        
        # Run the graph - it will handle plan -> validate -> (replan if needed) -> execute
        print("Running agent workflow...")
        print("Phase 1: Planning and validation...")
        state = self.graph.invoke(initial_state)
        
        print(f"\nFinal plan with {len(state['plan'])} steps:")
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
                result_preview = step["result"][:150] if len(step["result"]) > 150 else step["result"]
                print(f"     Summary: {result_preview}...")
            if step.get("structured_output"):
                # Show key fields from structured output
                struct = step["structured_output"]
                if isinstance(struct, dict):
                    # Extract important fields like links, IDs, etc.
                    important_fields = {}
                    for key in ["htmlLink", "hangoutLink", "id", "link", "url", "event_id", "meeting_link"]:
                        if key in struct:
                            important_fields[key] = struct[key]
                    if important_fields:
                        print(f"     Key Data: {json.dumps(important_fields, indent=6)}")
                    else:
                        # Show first few keys if no important fields found
                        keys = list(struct.keys())[:3]
                        print(f"     Structured Output Available: {', '.join(keys)}...")
            if step.get("error"):
                print(f"     Error: {step['error']}")
        
        if state.get("final_result"):
            print(f"\nFinal Status: {state['final_result']}")
        
        return state
