"""Main entry point for the agent."""
from agent import LangGraphAgent


def main():
    """Run the agent with a command."""
    # Example command
    command_data = {
        "text": "create a meeting for tuesday 13:00 and send the link to aircode610@gmail.com"
    }
    
    # Extract the command text
    command = command_data.get("text", "")
    
    if not command:
        print("No command provided!")
        return
    
    # Initialize and run the agent
    agent = LangGraphAgent()
    result = agent.run(command)
    
    # Print final state
    print(f"\n{'='*50}")
    print(f"Final Status: {'Completed' if result.get('completed') else 'Failed'}")
    if result.get('final_result'):
        print(f"Result: {result['final_result']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

