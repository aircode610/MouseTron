"""Service to receive tool names POST requests and save them to SQLite database."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path
import click

# Database file path - store in data directory for persistence
DB_FILE = Path(__file__).parent.parent / "data" / "tools_database.db"


def init_database():
    """Initialize the SQLite database with tools table."""
    # Ensure data directory exists
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            steps TEXT NOT NULL,
            step_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    # Create index on timestamp for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp 
        ON tool_executions(timestamp)
    """)
    
    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_FILE.absolute()}")


def save_tool_names(tool_names):
    """Save tool names to SQLite database."""
    if not tool_names:
        print("No tool names to save")
        return False
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Get current timestamp
        timestamp = datetime.now().isoformat()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Convert list to JSON string for storage
        steps_json = json.dumps(tool_names)
        step_count = len(tool_names)
        
        # Insert into database
        cursor.execute("""
            INSERT INTO tool_executions (timestamp, steps, step_count, created_at)
            VALUES (?, ?, ?, ?)
        """, (timestamp, steps_json, step_count, created_at))
        
        conn.commit()
        conn.close()
        
        print(f"Saved {step_count} tool names to database: {tool_names}")
        return True
        
    except Exception as e:
        print(f"Error saving to database: {e}")
        return False


def get_recent_executions(limit=10):
    """Get recent tool executions from database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, timestamp, steps, step_count, created_at
            FROM tool_executions
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        executions = []
        for row in results:
            executions.append({
                "id": row[0],
                "timestamp": row[1],
                "steps": json.loads(row[2]),
                "step_count": row[3],
                "created_at": row[4]
            })
        
        return executions
        
    except Exception as e:
        print(f"Error reading from database: {e}")
        return []


class ToolsReceiverHandler(BaseHTTPRequestHandler):
    """HTTP handler for receiving tool names POST requests."""
    
    def do_POST(self):
        """Handle POST requests with tool names."""
        if self.path != "/api/tools":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        
        # Get content length
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        
        print(f"\n=== POST request received at /api/tools ===")
        print(f"Body: {body.decode('utf-8')}")
        
        try:
            # Parse JSON
            data = json.loads(body.decode('utf-8'))
            tool_names = data.get("steps", [])
            
            if not tool_names:
                response_message = "No tool names provided"
                response_status = 400
            else:
                # Save to database
                success = save_tool_names(tool_names)
                
                if success:
                    response_message = f"Successfully saved {len(tool_names)} tool names"
                    response_status = 200
                else:
                    response_message = "Error saving to database"
                    response_status = 500
            
            # Send response
            self.send_response(response_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            response_data = json.dumps({
                "status": "success" if response_status == 200 else "error",
                "message": response_message,
                "tool_count": len(tool_names) if tool_names else 0
            })
            self.wfile.write(response_data.encode("utf-8"))
            
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_response = json.dumps({"status": "error", "message": "Invalid JSON"})
            self.wfile.write(error_response.encode("utf-8"))
            
        except Exception as e:
            print(f"Error processing request: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_response = json.dumps({"status": "error", "message": str(e)})
            self.wfile.write(error_response.encode("utf-8"))
    
    def do_GET(self):
        """Handle GET requests - return recent executions."""
        if self.path == "/api/tools" or self.path == "/api/tools/recent":
            try:
                # Get limit from query parameter
                limit = 10
                if "?" in self.path:
                    query_params = self.path.split("?")[1]
                    for param in query_params.split("&"):
                        if param.startswith("limit="):
                            limit = int(param.split("=")[1])
                
                executions = get_recent_executions(limit=limit)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response_data = json.dumps(executions, indent=2)
                self.wfile.write(response_data.encode("utf-8"))
                
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                error_response = json.dumps({"status": "error", "message": str(e)})
                self.wfile.write(error_response.encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        return


@click.command()
@click.option('-p', '--port', default=8081, type=int, help='Port to listen on (default: 8081)')
@click.option('-h', '--host', default='localhost', help='Host to bind to (default: localhost)')
def main(port, host):
    """Start the tools receiver service."""
    # Initialize database
    init_database()
    
    # Start server
    server = HTTPServer((host, port), ToolsReceiverHandler)
    print(f"Tools receiver service listening on http://{host}:{port}")
    print(f"Database location: {DB_FILE.absolute()}")
    print(f"\nEndpoints:")
    print(f"  POST http://{host}:{port}/api/tools - Receive tool names")
    print(f"  GET  http://{host}:{port}/api/tools/recent - Get recent executions")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    main()

