"""Script to fetch all tools from Zapier MCP API."""
import os
import json
import requests
import anthropic
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

load_dotenv()


def get_zapier_tools(authorization_token: str = None) -> List[Dict[str, Any]]:
    """
    Fetch all available tools from Zapier MCP API.
    
    Args:
        authorization_token: Zapier authorization token. If not provided, 
                            will try to get from ZAPIER_AUTHORIZATION_TOKEN env var.
    
    Returns:
        List of tool definitions from Zapier MCP.
    """
    # Get authorization token
    if not authorization_token:
        authorization_token = os.environ.get("ZAPIER_AUTHORIZATION_TOKEN")
    
    if not authorization_token:
        raise ValueError(
            "ZAPIER_AUTHORIZATION_TOKEN must be provided either as parameter "
            "or environment variable"
        )
    
    authorization_token = authorization_token.strip()
    
    # Zapier MCP endpoint
    mcp_url = "https://mcp.zapier.com/api/mcp/mcp"
    
    # Try different MCP protocol methods
    methods_to_try = [
        "tools/list",
        "list_tools",
        "tools/list_tools",
        "mcp/tools/list",
    ]
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {authorization_token}"
    }
    
    print(f"Fetching tools from Zapier MCP API...")
    print(f"Endpoint: {mcp_url}")
    
    # Try each method until one works
    last_error = None
    for method in methods_to_try:
        print(f"\nTrying method: {method}")
        
        # MCP uses JSON-RPC protocol
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {}
        }
    
        try:
            response = requests.post(
                mcp_url,
                json=payload,
                headers=headers,
                timeout=30,
                stream=True  # Enable streaming for SSE
            )
            
            # Print response details for debugging
            print(f"  Status Code: {response.status_code}")
            print(f"  Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
            
            if response.status_code != 200:
                error_text = response.text[:300] if hasattr(response, 'text') else str(response.content[:300])
                print(f"  Error Response: {error_text}")
                last_error = f"HTTP {response.status_code}: {error_text[:200]}"
                continue
            
            # Check if response is SSE (text/event-stream) or JSON
            content_type = response.headers.get('Content-Type', '')
            
            if 'text/event-stream' in content_type or 'event-stream' in content_type:
                # Handle SSE response
                print(f"  Detected SSE stream, parsing...")
                result = None
                for line in response.iter_lines(decode_unicode=True):
                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove 'data: ' prefix
                        if data_str.strip():
                            try:
                                event_data = json.loads(data_str)
                                # Look for the final result
                                if "result" in event_data:
                                    result = event_data
                                    break
                                elif "error" in event_data:
                                    error_msg = event_data["error"]
                                    if isinstance(error_msg, dict):
                                        error_msg = f"{error_msg.get('code', 'Unknown')}: {error_msg.get('message', 'Unknown error')}"
                                    print(f"  JSON-RPC Error in SSE: {error_msg}")
                                    last_error = f"JSON-RPC Error: {error_msg}"
                                    result = None
                                    break
                            except json.JSONDecodeError:
                                continue
                
                if not result:
                    last_error = "No valid JSON-RPC response in SSE stream"
                    continue
            else:
                # Handle regular JSON response
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    # Try to parse as text first
                    text = response.text
                    print(f"  Response text (first 500 chars): {text[:500]}")
                    last_error = "Response is not valid JSON"
                    continue
            
            # Check for JSON-RPC errors
            if result and "error" in result:
                error_msg = result["error"]
                if isinstance(error_msg, dict):
                    error_msg = f"{error_msg.get('code', 'Unknown')}: {error_msg.get('message', 'Unknown error')}"
                print(f"  JSON-RPC Error: {error_msg}")
                last_error = f"JSON-RPC Error: {error_msg}"
                continue
            
            if not result:
                last_error = "No result in response"
                continue
            
            # Extract tools from response - try multiple possible structures
            tools = []
            
            # Structure 1: result.tools
            if "result" in result:
                result_data = result["result"]
                if isinstance(result_data, dict):
                    if "tools" in result_data:
                        tools = result_data["tools"]
                    elif "items" in result_data:
                        tools = result_data["items"]
                elif isinstance(result_data, list):
                    tools = result_data
            
            # Structure 2: direct tools array
            if not tools and "tools" in result:
                tools = result["tools"]
            
            # Structure 3: check if result itself is the tools array
            if not tools and isinstance(result.get("result"), list):
                tools = result["result"]
            
            if tools:
                print(f"  ✓ Success! Found {len(tools)} tools")
                return tools
            else:
                print(f"  ⚠ No tools found in response structure")
                print(f"  Response structure: {json.dumps(result, indent=2)[:300]}...")
                last_error = "No tools found in response"
                
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            if hasattr(e.response, 'text'):
                error_detail = f": {e.response.text[:200]}"
            last_error = f"HTTP Error {e.response.status_code}{error_detail}"
            print(f"  {last_error}")
            continue
        except requests.exceptions.RequestException as e:
            last_error = f"Request Exception: {e}"
            print(f"  {last_error}")
            continue
        except json.JSONDecodeError as e:
            last_error = f"JSON Decode Error: {e}"
            print(f"  {last_error}")
            continue
    
    # If all methods failed
    raise Exception(f"All methods failed. Last error: {last_error}")


def get_zapier_tools_via_anthropic(
    api_key: Optional[str] = None,
    authorization_token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch tools using Anthropic API with MCP integration.
    This method uses the same approach as the agent.
    
    Args:
        api_key: Anthropic API key
        authorization_token: Zapier authorization token
    
    Returns:
        List of tool definitions
    """
    # Get API keys
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not authorization_token:
        authorization_token = os.environ.get("ZAPIER_AUTHORIZATION_TOKEN")
    
    if not api_key or not authorization_token:
        raise ValueError("Both ANTHROPIC_API_KEY and ZAPIER_AUTHORIZATION_TOKEN are required")
    
    api_key = api_key.strip()
    authorization_token = authorization_token.strip()
    
    # Initialize Anthropic client
    client = anthropic.Anthropic(api_key=api_key)
    
    # Configure MCP server (same as agent.py)
    mcp_servers = [
        {
            "type": "url",
            "url": "https://mcp.zapier.com/api/mcp/mcp",
            "name": "zapier",
            "authorization_token": authorization_token,
        }
    ]
    
    print("Fetching tools via Anthropic API with MCP...")
    
    # Use a prompt that asks Claude to list all available tools
    prompt = """Please list all available MCP tools from the Zapier server. 
Return a JSON array with tool names and descriptions."""
    
    try:
        response = client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",  # Using a valid Claude model
            max_tokens=4000,
            system="You are a helpful assistant that lists available MCP tools.",
            messages=[{"role": "user", "content": prompt}],
            mcp_servers=mcp_servers,
            betas=["mcp-client-2025-04-04"],
        )
        
        # Extract text response
        text_content = ""
        for block in response.content:
            if hasattr(block, 'type') and block.type == 'text' and hasattr(block, 'text'):
                text_content += block.text
        
        # Try to parse JSON from response
        import re
        json_match = re.search(r'\[.*\]', text_content, re.DOTALL)
        if json_match:
            try:
                tools = json.loads(json_match.group())
                return tools
            except:
                pass
        
        # If no JSON found, return empty (we'll need to parse differently)
        print("⚠ Could not extract tools from Anthropic response")
        print(f"Response: {text_content[:500]}...")
        return []
        
    except Exception as e:
        raise Exception(f"Failed to fetch tools via Anthropic API: {e}")


def save_tools_to_file(tools: List[Dict[str, Any]], filename: str = "zapier_tools.json"):
    """Save tools to a JSON file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved {len(tools)} tools to {filename}")


def print_tools_summary(tools: List[Dict[str, Any]]):
    """Print a summary of the tools."""
    print(f"\n{'='*60}")
    print(f"Found {len(tools)} tools from Zapier MCP")
    print(f"{'='*60}\n")
    
    # Group tools by category if available
    categories = {}
    for tool in tools:
        name = tool.get("name", "Unknown")
        description = tool.get("description", "No description")
        
        # Try to extract category from name (e.g., "gmail_send_email" -> "gmail")
        category = "Other"
        if "_" in name:
            category = name.split("_")[0].title()
        
        if category not in categories:
            categories[category] = []
        
        categories[category].append({
            "name": name,
            "description": description[:100] + "..." if len(description) > 100 else description
        })
    
    # Print by category
    for category, tool_list in sorted(categories.items()):
        print(f"\n{category} ({len(tool_list)} tools):")
        print("-" * 60)
        for tool in sorted(tool_list, key=lambda x: x["name"]):
            print(f"  • {tool['name']}")
            if tool['description']:
                print(f"    {tool['description']}")
    
    print(f"\n{'='*60}")


def main():
    """Main function to fetch and display Zapier tools."""
    try:
        # Try direct MCP API first
        print("Attempting method 1: Direct MCP API call...")
        tools = None
        try:
            tools = get_zapier_tools()
        except Exception as e:
            print(f"Method 1 failed: {e}\n")
            print("Attempting method 2: Via Anthropic API with MCP...")
            try:
                tools = get_zapier_tools_via_anthropic()
            except Exception as e2:
                print(f"Method 2 also failed: {e2}")
                raise Exception(f"Both methods failed. Method 1: {e}. Method 2: {e2}")
        
        if not tools:
            print("⚠ No tools found. Check your authorization token and API access.")
            return
        
        # Print summary
        print_tools_summary(tools)
        
        # Save to file
        save_tools_to_file(tools)
        
        # Also save a simplified version with just names and descriptions
        simplified = [
            {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "inputSchema": tool.get("inputSchema", {})
            }
            for tool in tools
        ]
        save_tools_to_file(simplified, "zapier_tools_simplified.json")
        
        print("\n✓ Done!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

