from http.server import BaseHTTPRequestHandler, HTTPServer
import click
import os
from datetime import datetime

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

        # Send simple response
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK\n")

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
