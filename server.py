from http.server import BaseHTTPRequestHandler, HTTPServer
import click
import os
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

# Add agent directory to path
agent_dir = Path(__file__).parent / "agent"
sys.path.insert(0, str(agent_dir))

from agent import LangGraphAgent

HOST = "localhost"   # listen on all interfaces

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


# Initialize agent once at module level
_agent = None

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

        # Try to parse JSON and check if it's Format 2 (has 'input' field)
        response_message = "OK"
        response_status = 200
        
        if body_decoded and body_decoded != "<binary data>":
            try:
                data = json.loads(body_decoded)
                
                # Check if this is Format 2 (has 'input' field)
                agent = get_agent()
                if "input" in data and agent is not None:
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
def main(port):
    server = HTTPServer((HOST, port), SimpleRequestHandler)
    print(f"Listening on http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
