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
    available_tools: Optional[List[Dict[str, Any]]]  # List of available tools with schemas


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
    
    @traceable(name="fetch_tools")
    def fetch_tools(self, state: AgentState) -> AgentState:
        """Fetch available tools from MCP server and store in state."""
        # Check if tools are already fetched
        if state.get("available_tools"):
            print("✓ Tools already fetched, using cached tools")
            return state
        
        print("Fetching available tools from MCP server...")
        
        try:
            # Use a prompt that asks Claude to list all available tools
            # The MCP server will provide tool schemas automatically
            prompt = """List all available MCP tools from the Zapier server. 

For each tool, provide a JSON object with:
- name: the exact tool name (string)
- description: what the tool does (string)
- inputSchema: an object with "properties" (object mapping parameter names to their schemas) and "required" (array of required parameter names)

Return ONLY a JSON array in this exact format:
[
  {
    "name": "tool_name_here",
    "description": "What this tool does",
    "inputSchema": {
      "properties": {
        "param1": {"type": "string", "description": "param description"},
        "param2": {"type": "number", "description": "param description"}
      },
      "required": ["param1"]
    }
  },
  ...
]

Do not include any text before or after the JSON array."""
            
            response = self.client.beta.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=8000,
                system="You are a helpful assistant that lists available MCP tools. Return only valid JSON arrays with tool information.",
                messages=[{"role": "user", "content": prompt}],
                mcp_servers=self.mcp_servers,
                betas=["mcp-client-2025-04-04"],
            )
            
            # Extract text response
            text_content = ""
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                    text_content += block.text
            
            # Try to parse JSON from response
            json_match = re.search(r'\[.*\]', text_content, re.DOTALL)
            if json_match:
                try:
                    tools = json.loads(json_match.group())
                    state["available_tools"] = tools
                    print(f"✓ Fetched {len(tools)} tools")
                    return state
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse tools JSON: {e}")
            
            # Fallback: try to extract tool information from text
            # Look for tool use blocks in the response
            tools = []
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'tool_use':
                    tool_info = {
                        "name": getattr(block, 'name', ''),
                        "description": f"Tool: {getattr(block, 'name', '')}",
                        "inputSchema": getattr(block, 'input', {})
                    }
                    tools.append(tool_info)
            
            if tools:
                state["available_tools"] = tools
                print(f"✓ Extracted {len(tools)} tools from response")
                return state
            
            # If we can't extract tools, create a minimal list
            print("⚠ Could not extract tools from response, using empty list")
            state["available_tools"] = []
            
        except Exception as e:
            print(f"Warning: Failed to fetch tools: {e}. Continuing without tool list.")
            state["available_tools"] = []
        
        return state
    
    def _format_tools_for_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """Format tools list into a readable string for prompts."""
        if not tools:
            return "No tools available."
        
        formatted = "Available Tools:\n"
        for i, tool in enumerate(tools, 1):
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            input_schema = tool.get("inputSchema", {})
            
            formatted += f"\n{i}. {name}\n"
            formatted += f"   Description: {description}\n"
            
            # Add input schema info
            if input_schema:
                properties = input_schema.get("properties", {})
                required = input_schema.get("required", [])
                if properties:
                    formatted += f"   Parameters:\n"
                    for param_name, param_info in properties.items():
                        param_type = param_info.get("type", "string")
                        param_desc = param_info.get("description", "")
                        is_required = param_name in required
                        req_marker = " (required)" if is_required else " (optional)"
                        formatted += f"     - {param_name} ({param_type}){req_marker}: {param_desc}\n"
        
        return formatted
    
    def _get_system_prompt(self, app: Optional[str] = None, planning_mode: bool = False) -> str:
        """Generate system prompt with optional app context.
        
        Args:
            app: The app name where the command came from
            planning_mode: If True, adds instructions to prevent tool execution during planning
        """
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
        
        # Add planning mode restrictions
        if planning_mode:
            base_prompt += """

CRITICAL RESTRICTION: You are in PLANNING MODE. You can see available tools and their schemas to understand what tools exist and what parameters they require, but you MUST NOT execute any tools. Only use tool information to create a plan. Tool execution will happen in a separate execution phase."""
        
        return base_prompt
    
    @traceable(name="summarize_command")
    def summarize_command(self, state: AgentState) -> AgentState:
        """Summarize long or unclear commands into clear, actionable commands."""
        command = state.get("command", "")
        feedback = state.get("feedback")
        app = state.get("app")
        
        # Combine command and feedback
        full_input = command
        if feedback:
            full_input = f"{command}\n\nAdditional context: {feedback}"
        
        # Check if summarization is needed (long text or unclear)
        # Use a simple heuristic: if command is very long (>500 chars) or seems like a conversation
        needs_summarization = (
            len(command) > 500 or 
            command.count('\n') > 5 or
            command.count('?') > 3 or  # Multiple questions might indicate a conversation
            (feedback and len(feedback) > 200)
        )
        
        if not needs_summarization:
            print(f"Command is clear and concise (length: {len(command)} chars), no summarization needed.")
            return state
        
        print(f"Summarizing command (length: {len(command)} chars, newlines: {command.count(chr(10))}, questions: {command.count('?')})...")
        
        # Get system prompt
        system_prompt = self._get_system_prompt(app)
        
        summarization_prompt = f"""Extract a clear, actionable command from this selected text:

{full_input}

Guidelines:
- Extract the main task from conversations/chats
- Keep clear commands as-is (just clean up)
- Preserve important details (dates, times, emails, names)
- Output only the command, no explanations
"""
        
        try:
            # Use regular messages API (not beta) since we don't need MCP tools for summarization
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Using cheaper model for summarization
                max_tokens=500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": summarization_prompt}
                ],
            )
            
            # Extract text from response (handle both text blocks and direct text)
            summarized_command = ""
            if hasattr(response, 'content') and response.content:
                for block in response.content:
                    if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                        summarized_command += block.text
                    elif hasattr(block, 'text'):  # Fallback for direct text attribute
                        summarized_command += block.text
            
            if not summarized_command:
                raise ValueError("No text content in response")
            
            summarized_command = summarized_command.strip()
            # Clean up the command (remove quotes if wrapped)
            if summarized_command.startswith('"') and summarized_command.endswith('"'):
                summarized_command = summarized_command[1:-1]
            if summarized_command.startswith("'") and summarized_command.endswith("'"):
                summarized_command = summarized_command[1:-1]
            
            print(f"Summarized command: {summarized_command[:100]}...")
            # Update the command in state - this will be used for all subsequent phases
            state["command"] = summarized_command
            print(f"✓ Command updated in state (length: {len(summarized_command)} chars)")
            
        except Exception as e:
            print(f"Warning: Summarization failed: {e}. Using original command.")
            # Keep original command if summarization fails
        
        return state
    
    @traceable(name="summarize_context")
    def summarize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize the execution context to reduce token usage when it gets large."""
        # Calculate total size of context
        context_str = json.dumps(context, indent=2)
        context_size = len(context_str)
        
        # Only summarize if context is getting large (>2000 chars)
        if context_size < 2000:
            return context
        
        print(f"Context is large ({context_size} chars), summarizing with cheaper model...")
        
        # Build a summary prompt
        context_summary_prompt = f"""Summarize this execution context, preserving all critical information needed for subsequent steps:

{context_str}

Guidelines:
- Preserve all structured data (IDs, links, keys, values) that might be needed for tool calls
- Keep summaries concise but complete
- Maintain references between steps (e.g., "step_1 result used in step_2")
- Output a JSON object with the same structure but summarized content
"""
        
        try:
            # Use regular messages API (not beta) since we don't need MCP tools for summarization
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",  # Using cheaper model for context summarization
                max_tokens=2000,
                system="You are a helpful assistant that summarizes execution context while preserving all critical data.",
                messages=[
                    {"role": "user", "content": context_summary_prompt}
                ],
            )
            
            # Extract text from response (handle both text blocks and direct text)
            summary_text = ""
            if hasattr(response, 'content') and response.content:
                for block in response.content:
                    if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                        summary_text += block.text
                    elif hasattr(block, 'text'):  # Fallback for direct text attribute
                        summary_text += block.text
            
            if not summary_text:
                raise ValueError("No text content in response")
            
            summary_text = summary_text.strip()
            
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', summary_text, re.DOTALL)
            if json_match:
                try:
                    summarized_context = json.loads(json_match.group())
                    print(f"✓ Context summarized: {len(context)} items -> {len(json.dumps(summarized_context))} chars")
                    return summarized_context
                except Exception as e:
                    print(f"Warning: Failed to parse summarized context JSON: {e}")
            
            # Fallback: create a simplified context structure
            summarized = {}
            for key, value in context.items():
                if isinstance(value, dict):
                    # Keep structured output but summarize text
                    summarized[key] = {
                        "summary": value.get("summary", "")[:200] + "..." if len(value.get("summary", "")) > 200 else value.get("summary", ""),
                        "structured_output": value.get("structured_output"),  # Keep full structured data
                        "description": value.get("description", "")
                    }
                else:
                    summarized[key] = str(value)[:200] + "..." if len(str(value)) > 200 else value
            
            return summarized
            
        except Exception as e:
            print(f"Warning: Context summarization failed: {e}. Using original context.")
            return context
    
    @traceable(name="plan_phase")
    def plan_phase(self, state: AgentState) -> AgentState:
        """Phase 1: Plan the steps needed to accomplish the command."""
        validation_feedback = state.get("validation_feedback")
        iteration = state.get("planning_iterations", 0) + 1
        command = state.get("command", "")
        feedback = state.get("feedback")
        app = state.get("app")
        
        # Get system prompt with app context and planning mode restrictions
        system_prompt = self._get_system_prompt(app, planning_mode=True)
        
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
        
        # Get available tools from state
        available_tools = state.get("available_tools", [])
        tools_info = self._format_tools_for_prompt(available_tools)
        
        planning_prompt = f"""Task: {user_input}
{validation_section}

CRITICAL: You are in PLANNING MODE. You can see available tools and their schemas below, but you MUST NOT execute any tools. Only use tool information to create a plan.

{tools_info}

CRITICAL: Include ALL intermediate steps. Example: "create meeting and send link" needs:
1. Create meeting
2. Get meeting link (from step 1 result)
3. Send email with link

IMPORTANT: Every step MUST have a tool_name. Do NOT create steps without tools (like "compose email" or "prepare message"). 
- If you need to compose text, include it directly in the tool_args of the tool that will use it
- All steps should execute a tool - there are no preparatory steps without tools
- If a tool needs text content, provide it in the tool_args, don't create a separate step
- Use exact tool names from the list above

Each step should:
- Be specific and actionable
- Use one tool call
- Reference exact tool name from the available tools list above
- Include intermediate steps (getting data from previous results)
- ALWAYS have a tool_name (never null)

Return JSON list with:
- id: sequential number
- description: specific step description
- tool_name: exact tool name (REQUIRED - never null, must match a tool from the list above)
- tool_args: tool arguments (or null)
- status: "pending"

Example:
[
  {{"id": 1, "description": "Create calendar event for Tuesday 13:00", "tool_name": "zapier_google_calendar_create_event", "tool_args": {{"date": "tuesday", "time": "13:00"}}, "status": "pending"}},
  {{"id": 2, "description": "Get meeting link from created event", "tool_name": "zapier_google_calendar_get_event", "tool_args": {{"event_id": "from_step_1"}}, "status": "pending"}},
  {{"id": 3, "description": "Send email with meeting link", "tool_name": "zapier_gmail_send_email", "tool_args": {{"to": "example@gmail.com", "body": "Link from step 2"}}, "status": "pending"}}
]

Plan steps for: "{command}"
"""
        
        # Use regular messages API (no MCP) since we're providing tools in the prompt
        response = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": planning_prompt}],
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
        
        # Check if this step has a tool to execute
        tool_name = step.get("tool_name")
        has_tool = tool_name and tool_name.strip()
        
        # Get system prompt with app context
        app = state.get("app")
        system_prompt = self._get_system_prompt(app)
        
        # Build the execution prompt
        context = state.get("execution_context", {})
        
        # Add feedback to context if available (important info might be there)
        feedback = state.get("feedback")
        command = state.get("command", "")
        
        # Build comprehensive context string with structured data
        context_str = ""
        # Add original command and feedback at the start
        if feedback:
            context_str += f"\n=== ORIGINAL CONTEXT ===\nCommand: {command}\nFeedback: {feedback}\n=== END ORIGINAL CONTEXT ===\n"
        elif command:
            context_str += f"\n=== ORIGINAL COMMAND ===\n{command}\n=== END ORIGINAL COMMAND ===\n"
        
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
        
        # Build execution prompt based on whether step has a tool
        if has_tool:
            execution_prompt = f"""EXECUTE: {step['description']}

{context_str}

CRITICAL: You are in EXECUTION MODE. This step requires executing the tool: {tool_name}

Instructions:
- Execute the tool: {tool_name}
- Use the tool arguments from the plan: {json.dumps(step.get('tool_args', {}), indent=2)}
- Extract data from previous steps' structured output (e.g., htmlLink, hangoutLink, id) if needed
- Provide all required tool parameters
- Execute the tool call now

Response format:
Summary: [what was done]
Structured Output: [full JSON/structured data from tool]
"""
        else:
            # Step without tool - just provide a summary, no tool execution
            execution_prompt = f"""Complete this step: {step['description']}

{context_str}

CRITICAL: This step does NOT require a tool execution. It is a preparatory or informational step.

Instructions:
- Provide a brief summary of what this step accomplishes
- Do NOT call any tools
- This step is likely preparing information for a subsequent tool-based step

Response format:
Summary: [brief description of what this step accomplishes]
"""
        
        try:
            if has_tool:
                # Use beta API with tools for steps that require tool execution
                response = self.client.beta.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=2000,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": execution_prompt}
                    ],
                    mcp_servers=self.mcp_servers,
                    betas=["mcp-client-2025-04-04"],
                )
            else:
                # Use regular API without tools for steps that don't require tool execution
                response = self.client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=500,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": execution_prompt}
                    ],
                )
            
            # Extract text summary from all text blocks
            result_text_parts = []
            for block in response.content:
                if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                    result_text_parts.append(block.text)
            result_text = "\n".join(result_text_parts) if result_text_parts else ""
            
            # Try to extract structured output from the response (only for tool-based steps)
            structured_output = None
            if has_tool:
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
        
        # Get system prompt with app context and planning mode restrictions
        system_prompt = self._get_system_prompt(app, planning_mode=True)
        
        # Build validation prompt
        plan_summary = "\n".join([
            f"Step {s['id']}: {s.get('description', 'N/A')} (tool: {s.get('tool_name', 'unspecified')})"
            for s in plan
        ])
        
        user_input = command
        if feedback:
            user_input = f"Command: {command}\nAdditional feedback: {feedback}"
        
        # Get available tools from state
        available_tools = state.get("available_tools", [])
        tools_info = self._format_tools_for_prompt(available_tools)
        
        validation_prompt = f"""Review this plan for: "{user_input}"

Plan:
{plan_summary}

CRITICAL: You are in VALIDATION MODE. You can see available tools and their schemas below to verify the plan uses correct tools, but you MUST NOT execute any tools. Only review and provide feedback.

{tools_info}

Use the tools list above to verify:
- The tool names in the plan are correct (must match exactly)
- The tool parameters make sense (check required fields)
- The plan is logically sound

Check for:
1. Missing intermediate steps (e.g., getting a link after creating something)
2. Ambiguous or unclear steps
3. Steps referencing data without showing how to get it
4. Missing tool assignments
5. Logical gaps
6. Incorrect tool names (verify against available tools list above)
7. Steps without tool_name (all steps must have a tool)

If approved, respond: "APPROVED"

If issues found, respond:
ISSUES FOUND:
- [Issue 1: specific problem and affected step]
- [Issue 2: specific problem and affected step]
- [Suggestion: what to add/change]
"""
        
        try:
            # Use regular messages API (no MCP) since we're providing tools in the prompt
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": validation_prompt}
                ],
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
        if iterations >= 3:
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
                    
                    # Summarize context if it's getting large (after each addition)
                    context = self.summarize_context(context)
                
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
        workflow.add_node("fetch_tools", self.fetch_tools)
        workflow.add_node("summarize", self.summarize_command)
        workflow.add_node("plan", self.plan_phase)
        workflow.add_node("validate", self.validate_plan)
        workflow.add_node("execute", self.execute_phase)
        
        # Define the flow: fetch_tools -> summarize -> plan -> validate -> (replan or execute) -> end
        workflow.set_entry_point("fetch_tools")
        workflow.add_edge("fetch_tools", "summarize")
        workflow.add_edge("summarize", "plan")
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
            "planning_iterations": 0,
            "available_tools": None  # Will be fetched in fetch_tools node
        }
        
        # Run the graph - it will handle fetch_tools -> summarize -> plan -> validate -> (replan if needed) -> execute
        print("Running agent workflow...")
        print("Phase 0: Fetching available tools...")
        print("Phase 1: Summarizing command (if needed)...")
        print("Phase 2: Planning and validation...")
        state = self.graph.invoke(initial_state)
        
        print(f"\nFinal plan with {len(state['plan'])} steps:")
        for step in state["plan"]:
            print(f"  {step['id']}. {step['description']}")
        
        print("\nPhase 3: Execution completed")
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
