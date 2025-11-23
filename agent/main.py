"""Main entry point for the agent."""
from agent import LangGraphAgent


def main():
    """Run the agent with a command."""
    # Example: Simulating data from Logitech plugin
    # In real usage, this would come from the plugin
    command_data = {
        "command": """

        Sara — 10:14 AM
Hey! Quick task for you — could you put together a brief report on how RAG is being used in education research?

Amirali — 10:15 AM
Sure, I can do that. Any specific angle you want me to focus on?

Sara — 10:16 AM
Let’s keep it simple for now

Amirali — 10:16 AM
Got it. When do you need it?

Sara — 10:17 AM
Today if possible. And once you draft it, could you share it with me on Google Docs?

Amirali — 10:17 AM
Absolutely — I’ll work on it now and send you the doc link as soon as it’s ready.

Sara — 10:18 AM
Perfect, thanks!

        """,
        "feedback": "sara's email address is aircode610@gmail.com",  # User's additional feedback
        "app": "Chrome"  # App where the text was selected
    }
    
    # Extract the data
    command = command_data.get("command", "")
    feedback = command_data.get("feedback")
    app = command_data.get("app")
    
    if not command:
        print("No command provided!")
        return
    
    # Initialize and run the agent
    agent = LangGraphAgent()
    result = agent.run(command, feedback=feedback, app=app)
    
    # Print final state
    print(f"\n{'='*50}")
    print(f"Final Status: {'Completed' if result.get('completed') else 'Failed'}")
    if result.get('final_result'):
        print(f"Result: {result['final_result']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

