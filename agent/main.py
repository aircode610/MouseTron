"""Main entry point for the agent."""
from agent import LangGraphAgent


def main():
    """Run the agent with a command."""
    # Example: Simulating data from Logitech plugin
    # In real usage, this would come from the plugin
    command_data = {
        "command": """ tavily_search google_docs_create_document_from_text gmail_send_email
        """,
        "feedback": "do a research about munich and write the report in google docs and send the email to bigdenzill@gmail.com",  # User's additional feedback
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

