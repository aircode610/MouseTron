"""Expose the LangGraph agent graph for LangGraph Studio."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path to import agent
sys.path.insert(0, str(Path(__file__).parent))

from agent import LangGraphAgent, AgentState

# Load environment variables from project root
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
else:
    # Fallback to current directory
    load_dotenv(override=True)

# Initialize the agent and get the graph
agent = LangGraphAgent()
graph = agent.graph

# Export for LangGraph Studio
__all__ = ["graph", "AgentState"]

