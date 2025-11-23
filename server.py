from http.server import BaseHTTPRequestHandler, HTTPServer
import click
import os
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file BEFORE importing agent
from dotenv import load_dotenv

# Get the directory where server.py is located
server_dir = Path(__file__).parent
env_path = server_dir / ".env"

# Print debug info about .env file
print(f"DEBUG: server.py location: {Path(__file__).absolute()}")
print(f"DEBUG: Looking for .env at: {env_path.absolute()}")
print(f"DEBUG: .env exists: {env_path.exists()}")

# Load .env file with explicit path
if env_path.exists():
    print(f"DEBUG: Loading .env from {env_path}")

    # Read the file manually to see what's in it
    with open(env_path, 'r') as f:
        content = f.read()
        print(f"DEBUG: .env file content (first 200 chars):")
        print(repr(content[:200]))

    load_dotenv(dotenv_path=env_path, override=True)
    print(f"DEBUG: Loaded .env from {env_path}")
else:
    print(f"ERROR: .env file not found at {env_path}")
    # Try to load from current working directory as fallback
    load_dotenv()

# Add agent directory to path
agent_dir = Path(__file__).parent / "agent"
sys.path.insert(0, str(agent_dir))

from agent import LangGraphAgent

# Import EMA
from EMA import EMA

HOST = "localhost"  # listen on all interfaces

# Log file path
LOG_FILE = os.path.expanduser("~/Library/Application Support/Logi/LogiPluginService/Logs/plugin_logs/MouseTron.log")


def ensure_log_directory():
    """Ensure the log directory exists."""
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)


def log_to_file(message):
    """Append a message to the log file with timestamp."""
    ensure_log_directory()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {message}\n")


# Print environment variable to verify it's loaded
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
zapier_token = os.getenv("ZAPIER_AUTHORIZATION_TOKEN")
print(f"DEBUG: ANTHROPIC_API_KEY loaded: {anthropic_key[:20] + '...' if anthropic_key else 'None'}")
print(f"DEBUG: ZAPIER_AUTHORIZATION_TOKEN loaded: {zapier_token[:20] + '...' if zapier_token else 'None'}")

# Print all environment variables that start with ANTHROPIC or ZAPIER
print("DEBUG: All ANTHROPIC/ZAPIER env vars:")
for key, value in os.environ.items():
    if 'ANTHROPIC' in key or 'ZAPIER' in key:
        print(f"  {key}: {value[:20] if value else 'None'}...")

log_to_file(f"DEBUG: .env path: {env_path.absolute()}")
log_to_file(f"DEBUG: .env exists: {env_path.exists()}")
log_to_file(f"DEBUG: ANTHROPIC_API_KEY loaded: {anthropic_key[:20] + '...' if anthropic_key else 'None'}")
log_to_file(f"DEBUG: ZAPIER_AUTHORIZATION_TOKEN loaded: {zapier_token[:20] + '...' if zapier_token else 'None'}")

# Initialize agent once at module level - MUST be declared before get_agent() is defined
_agent = None

# Initialize EMA once at module level
_ema = None


def get_agent():
    """Get or initialize the agent instance."""
    global _agent
    if _agent is None:
        try:
            _agent = LangGraphAgent()
            print("Agent initialized successfully")
            log_to_file("Agent initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize agent: {e}")
            log_to_file(f"ERROR: Failed to initialize agent: {e}")
    return _agent


def get_ema():
    """Get or initialize the EMA instance."""
    global _ema
    if _ema is None:
        try:
            # Create containers directory
            containers_dir = server_dir / "containers"
            containers_dir.mkdir(exist_ok=True)
            
            # Initialize EMA with containers directory
            _ema = EMA(k=10, t=50, nr=2, nf=5, ns=5, containers_dir=containers_dir)
            print("EMA initialized successfully")
            log_to_file("EMA initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize EMA: {e}")
            log_to_file(f"ERROR: Failed to initialize EMA: {e}")
    return _ema


def load_showcase_patterns():
    """Load pattern blocks from recommendation_showcase_patterns.txt and populate EMA containers."""
    try:
        ema = get_ema()
        if not ema:
            log_to_file("ERROR: EMA not initialized, cannot load showcase patterns")
            print("ERROR: EMA not initialized, cannot load showcase patterns")
            return False
        
        patterns_file = server_dir / "recommendation_showcase_patterns.txt"
        
        if not patterns_file.exists():
            log_to_file(f"Warning: Showcase patterns file not found at {patterns_file}")
            print(f"Warning: Showcase patterns file not found at {patterns_file}")
            return False
        
        # Load pattern blocks from file, skipping empty lines and separators
        blocks = []
        with open(patterns_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and separator lines (just dashes)
                if line and line != '-':
                    blocks.append(line)
        
        if not blocks:
            log_to_file("No blocks found in showcase patterns file")
            print("No blocks found in showcase patterns file")
            return False
        
        log_to_file(f"Loading {len(blocks)} blocks from showcase patterns file")
        print(f"Loading {len(blocks)} blocks from showcase patterns file...")
        
        # Add all blocks to EMA
        for block in blocks:
            ema.add_block(block)
        
        # Save EMA containers to JSON files
        save_success = ema.save_containers()
        if save_success:
            log_to_file(f"Successfully loaded {len(blocks)} showcase patterns into EMA containers")
            print(f"✓ Successfully loaded {len(blocks)} showcase patterns into EMA containers")
        else:
            log_to_file("Warning: Patterns loaded but failed to save containers")
            print("Warning: Patterns loaded but failed to save containers")
        
        # Generate recommendations after loading patterns (regardless of save status)
        generate_recommendations()
        
        return save_success
            
    except Exception as e:
        error_msg = f"Error loading showcase patterns: {str(e)}"
        log_to_file(f"ERROR: {error_msg}")
        print(f"ERROR: {error_msg}")
        return False


# Thread-safe storage for current agent state
_agent_state_lock = threading.Lock()
_current_agent_state = None
_agent_running = False

def get_current_steps():
    """Get current step statuses in a thread-safe way."""
    with _agent_state_lock:
        if _current_agent_state is None:
            return []
        
        plan = _current_agent_state.get("plan", [])
        steps = []
        for step in plan:
            steps.append({
                "step": step.get("description", "Unknown"),
                "status": step.get("status", "pending")
            })
        return steps


def set_agent_state(state):
    """Update the current agent state in a thread-safe way."""
    global _current_agent_state, _agent_running
    with _agent_state_lock:
        _current_agent_state = state
        _agent_running = state is not None


def clear_agent_state():
    """Clear the agent state when execution completes."""
    global _current_agent_state, _agent_running
    with _agent_state_lock:
        # Keep the final state for a bit, but mark as not running
        _agent_running = False


def extract_tool_names_from_state(state):
    """Extract tool names from completed steps in order."""
    if not state or "plan" not in state:
        return []
    
    tool_names = []
    plan = state.get("plan", [])
    
    # Sort by step ID to maintain order
    sorted_steps = sorted(plan, key=lambda x: x.get("id", 0))
    
    for step in sorted_steps:
        # Get tool name from the step
        tool_name = step.get("tool_name")
        
        # Only include steps that were actually executed (completed or failed)
        status = step.get("status", "pending")
        if status in ["completed", "failed", "in_progress"] and tool_name:
            # Clean up tool name (remove any prefixes/suffixes if needed)
            tool_name_clean = tool_name.strip()
            if tool_name_clean:
                # Allow duplicates since same tool can be called multiple times
                tool_names.append(tool_name_clean)
    
    return tool_names


def load_tool_descriptions():
    """Load tool descriptions from zapier_tools.json into a dictionary."""
    tools_file = server_dir / "dataset" / "zapier_tools.json"
    tool_descriptions = {}
    
    try:
        if tools_file.exists():
            with open(tools_file, "r", encoding="utf-8") as f:
                tools = json.load(f)
                for tool in tools:
                    tool_name = tool.get("name", "")
                    description = tool.get("description", "")
                    tool_descriptions[tool_name] = description
        else:
            log_to_file(f"Warning: zapier_tools.json not found at {tools_file}")
            print(f"Warning: zapier_tools.json not found at {tools_file}")
    except Exception as e:
        log_to_file(f"ERROR loading tool descriptions: {str(e)}")
        print(f"ERROR loading tool descriptions: {str(e)}")
    
    return tool_descriptions


def remove_zapier_prefix(tool_name):
    """Remove 'zapier_' prefix from tool name if present."""
    if tool_name.startswith("zapier_"):
        return tool_name[7:]  # Remove "zapier_" (7 characters)
    return tool_name


def get_tool_description(tool_name, tool_descriptions):
    """Get tool description, handling zapier_ prefix removal."""
    # Remove prefix for lookup
    lookup_name = remove_zapier_prefix(tool_name)
    return tool_descriptions.get(lookup_name, f"No description available for {tool_name}")


def generate_recommendations():
    """Generate recommendation JSON files from EMA pick functions."""
    try:
        ema = get_ema()
        if not ema:
            log_to_file("ERROR: EMA not initialized for recommendations")
            print("ERROR: EMA not initialized for recommendations")
            return False
        
        # Load tool descriptions
        tool_descriptions = load_tool_descriptions()
        
        # Create recommendations directory
        recommendations_dir = server_dir / "recommendations"
        recommendations_dir.mkdir(exist_ok=True)
        
        # Generate recent tools combo files (nr files) using pick_from_recent()
        recent_selections = ema.pick_from_recent()
        for i, selection in enumerate(recent_selections, 1):
            tool_names = selection.get("names", "").split(", ")
            recommendations = []
            
            for tool_name in tool_names:
                tool_name = tool_name.strip()
                if tool_name:
                    description = get_tool_description(tool_name, tool_descriptions)
                    recommendations.append({
                        "tool_name": tool_name,
                        "description": description
                    })
            
            if recommendations:
                filename = recommendations_dir / f"recent_tools_combo_{i}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(recommendations, f, indent=2)
                log_to_file(f"Generated {filename}")
        
        # Generate recent tool single files (ns files) using get_recent_single_tools()
        single_tools = ema.get_recent_single_tools()
        for i, tool_name in enumerate(single_tools, 1):
            if tool_name:
                description = get_tool_description(tool_name, tool_descriptions)
                recommendation = [{
                    "tool_name": tool_name,
                    "description": description
                }]
                
                filename = recommendations_dir / f"recent_tool_single_{i}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(recommendation, f, indent=2)
                log_to_file(f"Generated {filename}")
        
        # Generate stable tools combo files (nf files) using pick_from_frequency()
        frequency_selections = ema.pick_from_frequency()
        for i, selection in enumerate(frequency_selections, 1):
            tool_names = selection.get("names", "").split(", ")
            recommendations = []
            
            for tool_name in tool_names:
                tool_name = tool_name.strip()
                if tool_name:
                    description = get_tool_description(tool_name, tool_descriptions)
                    recommendations.append({
                        "tool_name": tool_name,
                        "description": description
                    })
            
            if recommendations:
                filename = recommendations_dir / f"stable_tools_combo_{i}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(recommendations, f, indent=2)
                log_to_file(f"Generated {filename}")
        
        print(f"✓ Generated recommendation files in {recommendations_dir}")
        log_to_file(f"Generated recommendation files successfully")
        return True
        
    except Exception as e:
        error_msg = f"Error generating recommendations: {str(e)}"
        log_to_file(f"ERROR: {error_msg}")
        print(f"ERROR: {error_msg}")
        return False


def update_ema_containers(tool_names):
    """Update EMA containers directly with tool names and save to JSON files."""
    if not tool_names:
        log_to_file("No tool names to update EMA with")
        print("No tool names to update EMA with")
        return False
    
    try:
        ema = get_ema()
        if not ema:
            log_to_file("ERROR: EMA not initialized")
            print("ERROR: EMA not initialized")
            return False
        
        # Convert steps list to a comma-separated block string
        block = ", ".join(tool_names)
        
        # Add block to EMA
        ema.add_block(block)
        
        # Save EMA containers to JSON files
        if ema.save_containers():
            log_to_file(f"Updated EMA with {len(tool_names)} tools and saved containers: {tool_names}")
            print(f"✓ Updated EMA with {len(tool_names)} tools and saved containers")
            
            # Generate recommendations after updating EMA
            generate_recommendations()
            
            return True
        else:
            log_to_file(f"Warning: EMA updated but failed to save containers")
            print(f"Warning: EMA updated but failed to save containers")
            return False
            
    except Exception as e:
        error_msg = f"Error updating EMA containers: {str(e)}"
        log_to_file(f"ERROR: {error_msg}")
        print(f"ERROR: {error_msg}")
        return False


def run_agent_async(command, feedback, app):
    """Run the agent in a background thread with streaming state updates."""
    def agent_runner():
        global _current_agent_state
        try:
            agent = get_agent()
            if agent is None:
                set_agent_state(None)
                return
            
            # Initialize state to show planning phase
            initial_state = {
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
            set_agent_state(initial_state)
            
            # Use streaming to get intermediate states
            # This allows us to update the state as the agent progresses
            final_state = None
            for state_update in agent.graph.stream(initial_state):
                # state_update is a dict with node names as keys
                # The last update contains the final state
                for node_name, state in state_update.items():
                    # Update state after each node execution
                    set_agent_state(state)
                    final_state = state
                    
                    # Log progress
                    if "plan" in state and state["plan"]:
                        plan_steps = len(state["plan"])
                        print(f"Agent progress: {node_name} - {plan_steps} steps planned")
            
            # Ensure final state is set
            if final_state:
                set_agent_state(final_state)
                
                # Extract and update EMA containers with tool names after agent finishes
                tool_names = extract_tool_names_from_state(final_state)
                if tool_names:
                    log_to_file(f"Agent finished. Extracted {len(tool_names)} tool names: {tool_names}")
                    print(f"\n=== Agent finished. Extracted {len(tool_names)} tool names ===")
                    update_ema_containers(tool_names)
                else:
                    log_to_file("Agent finished but no tool names found in completed steps")
                    print("Agent finished but no tool names found in completed steps")
            
            # Keep state for a few seconds, then clear
            import time
            time.sleep(5)  # Keep final state visible for 5 seconds
            clear_agent_state()
            
        except Exception as e:
            error_state = {
                "command": command,
                "feedback": feedback,
                "app": app,
                "plan": [{"id": 1, "description": "Error occurred", "status": "failed", "error": str(e)}],
                "completed": False,
                "final_result": f"Error: {str(e)}"
            }
            set_agent_state(error_state)
            log_to_file(f"ERROR in agent thread: {e}")
            print(f"ERROR in agent thread: {e}")
            import time
            time.sleep(5)  # Show error for 5 seconds
            clear_agent_state()
    
    thread = threading.Thread(target=agent_runner, daemon=True)
    thread.start()
    return thread



class SimpleRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Get content length (how many bytes to read)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''

        # Print request info
        print("=== POST request received ===")
        print(f"Path: {self.path}")
        print("Headers:")
        print(self.headers)
        print("Body (raw):", body)

        body_decoded = None
        try:
            body_decoded = body.decode("utf-8")
            print("Body (decoded):", body_decoded)
        except UnicodeDecodeError:
            body_decoded = "<binary data>"
            print("Body is not valid UTF-8 text")

        # Log to file
        log_to_file("=== POST request received ===")
        log_to_file(f"Path: {self.path}")
        log_to_file(f"Headers: {dict(self.headers)}")
        log_to_file(f"Body: {body_decoded}")
        log_to_file("")  # Empty line for separation

        # Try to parse JSON and check request type
        response_message = "OK"
        response_status = 200
        
        # Get agent instance for Format 2 requests
        agent = get_agent()
        
        if body_decoded and body_decoded != "<binary data>":
            try:
                data = json.loads(body_decoded)
                
                # Check if this is a tools POST (has 'steps' field) - typically at /api/tools
                if "steps" in data or self.path == "/api/tools":
                    # This is a POST with tool names (for manual updates or backward compatibility)
                    steps = data.get("steps", [])
                    log_to_file(f"Received tool names POST at {self.path}: {json.dumps(data, indent=2)}")
                    print(f"\n=== Received tool names POST ===")
                    print(f"Path: {self.path}")
                    print(f"Steps: {steps}")
                    
                    # Save tool names to a text file
                    try:
                        # Save to dataset/agent_tool_names.txt (relative to server.py location)
                        dataset_dir = server_dir / "dataset"
                        dataset_dir.mkdir(exist_ok=True)  # Create directory if it doesn't exist
                        tools_file = dataset_dir / "agent_tool_names.txt"
                        
                        # Write tool names, one per line
                        with open(tools_file, "w", encoding="utf-8") as f:
                            for tool_name in steps:
                                f.write(f"{tool_name}\n")
                        
                        print(f"✓ Saved {len(steps)} tool names to {tools_file}")
                        log_to_file(f"Saved {len(steps)} tool names to {tools_file}")
                        response_message = f"Received and saved {len(steps)} tool names to {tools_file.name}"
                    except Exception as save_error:
                        error_msg = f"Error saving tool names: {str(save_error)}"
                        print(f"ERROR: {error_msg}")
                        log_to_file(f"ERROR: {error_msg}")
                        response_message = f"Received {len(steps)} tool names but failed to save: {str(save_error)}"
                    
                    # Update EMA containers directly
                    if update_ema_containers(steps):
                        response_message += f" | EMA containers updated and saved"
                    
                    log_to_file(f"Tool names received: {steps}")
                
                # Check if this is Format 2 (has 'input' field)
                elif "input" in data and agent is not None:
                    selected_text = data.get("selectedText", "")
                    application_name = data.get("applicationName", "Unknown")
                    user_input = data.get("input", "")
                    
                    print(f"\n=== Format 2 POST detected ===")
                    print(f"Command: {selected_text[:100]}...")
                    print(f"App: {application_name}")
                    print(f"Feedback: {user_input}")
                    print(f"Running agent...\n")
                    
                    log_to_file("=== Format 2 POST - Running agent ===")
                    log_to_file(f"Command: {selected_text}")
                    log_to_file(f"App: {application_name}")
                    log_to_file(f"Feedback: {user_input}")
                    
                    try:
                        # Run the agent in a background thread
                        run_agent_async(selected_text, user_input, application_name)
                        response_message = "Agent started. Check /api/steps for status."
                        log_to_file("Agent started in background thread")
                        print(f"\n=== Agent started in background ===")
                        
                    except Exception as e:
                        error_msg = f"Error starting agent: {str(e)}"
                        print(f"\n=== ERROR: {error_msg} ===")
                        log_to_file(f"ERROR: {error_msg}")
                        response_message = f"Error: {str(e)}"
                        response_status = 500
                
                elif "input" in data and agent is None:
                    response_message = "Agent not initialized. Check server logs."
                    response_status = 500
                    log_to_file("ERROR: Format 2 POST received but agent is not initialized")                    
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON: {e}")
                log_to_file(f"Failed to parse JSON: {e}")
                response_message = "Invalid JSON in request body"
                response_status = 400
            except Exception as e:
                print(f"Unexpected error processing request: {e}")
                log_to_file(f"Unexpected error: {e}")
                response_message = f"Error: {str(e)}"
                response_status = 500

        # Send response
        self.send_response(response_status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(response_message.encode("utf-8"))

    def do_GET(self):
        """Handle GET requests, specifically /api/steps for step status."""
        if self.path == "/api/steps":
            try:
                steps = get_current_steps()
                response_data = json.dumps(steps, indent=2)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response_data.encode("utf-8"))
                
            except Exception as e:
                error_msg = f"Error getting steps: {str(e)}"
                print(f"ERROR in GET /api/steps: {e}")
                log_to_file(f"ERROR in GET /api/steps: {e}")
                
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                error_response = json.dumps({"error": error_msg})
                self.wfile.write(error_response.encode("utf-8"))
        else:
            # Return 404 for other GET requests
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    # Optional: silence default logging to avoid duplicates
    def log_message(self, format, *args):
        return


@click.command()
@click.option('-p', '--port', default=8080, type=int, help='Port to listen on')
@click.option('--load-showcase', is_flag=True, default=False, help='Load showcase patterns into EMA containers on startup')
def main(port, load_showcase):
    # Initialize EMA first
    get_ema()
    
    # Load showcase patterns if enabled
    if load_showcase:
        load_showcase_patterns()
    else:
        # Check environment variable as alternative
        if os.getenv("LOAD_SHOWCASE_PATTERNS", "").lower() in ("true", "1", "yes"):
            load_showcase_patterns()
    
    server = HTTPServer((HOST, port), SimpleRequestHandler)
    print(f"Listening on http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
