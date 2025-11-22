"""Extract tool names from zapier_tools.json and save to a file."""
import json
import os


def extract_tool_names(input_file: str = "zapier_tools.json", output_file: str = "zapier_tool_names.txt"):
    """
    Extract tool names from JSON file and save to a text file, one name per line.
    
    Args:
        input_file: Path to the input JSON file
        output_file: Path to the output text file
    """
    # If input file doesn't exist in current dir, try dataset directory
    if not os.path.exists(input_file):
        dataset_input = os.path.join("dataset", input_file)
        if os.path.exists(dataset_input):
            input_file = dataset_input
    
    # If output file path is relative, save in dataset directory
    if not os.path.dirname(output_file):
        output_file = os.path.join("dataset", output_file)
    
    try:
        # Read the JSON file
        with open(input_file, "r", encoding="utf-8") as f:
            tools = json.load(f)
        
        # Extract names
        names = []
        for tool in tools:
            if "name" in tool:
                names.append(tool["name"])
        
        # Write to output file, one name per line
        with open(output_file, "w", encoding="utf-8") as f:
            for name in names:
                f.write(f"{name}\n")
        
        print(f"✓ Extracted {len(names)} tool names from {input_file}")
        print(f"✓ Saved to {output_file}")
        
        return names
        
    except FileNotFoundError:
        print(f"✗ Error: File '{input_file}' not found")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in '{input_file}': {e}")
        return []
    except Exception as e:
        print(f"✗ Error: {e}")
        return []


if __name__ == "__main__":
    extract_tool_names()

