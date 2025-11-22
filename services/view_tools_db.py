"""Utility script to view tool executions from the SQLite database."""
import sqlite3
import json
from pathlib import Path
import click

DB_FILE = Path(__file__).parent.parent / "data" / "tools_database.db"


@click.command()
@click.option('-l', '--limit', default=20, help='Number of recent executions to show (default: 20)')
@click.option('--all', is_flag=True, help='Show all executions')
def main(limit, all):
    """View tool executions from the database."""
    if not DB_FILE.exists():
        print(f"Database not found at: {DB_FILE.absolute()}")
        print("Run tools_receiver.py first to create the database.")
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        if all:
            cursor.execute("""
                SELECT id, timestamp, steps, step_count, created_at
                FROM tool_executions
                ORDER BY timestamp DESC
            """)
        else:
            cursor.execute("""
                SELECT id, timestamp, steps, step_count, created_at
                FROM tool_executions
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            print("No tool executions found in database.")
            return
        
        print(f"\n{'='*80}")
        print(f"Tool Executions Database ({len(results)} {'total' if all else 'recent'} entries)")
        print(f"{'='*80}\n")
        
        for row in results:
            exec_id, timestamp, steps_json, step_count, created_at = row
            steps = json.loads(steps_json)
            
            print(f"ID: {exec_id}")
            print(f"Created: {created_at}")
            print(f"Timestamp: {timestamp}")
            print(f"Step Count: {step_count}")
            print(f"Tools: {', '.join(steps)}")
            print(f"{'-'*80}\n")
        
        # Show summary statistics
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tool_executions")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT steps) FROM tool_executions")
        unique_combinations = cursor.fetchone()[0]
        
        # Get most common tool
        cursor.execute("""
            SELECT steps, COUNT(*) as count
            FROM tool_executions
            GROUP BY steps
            ORDER BY count DESC
            LIMIT 1
        """)
        most_common = cursor.fetchone()
        conn.close()
        
        print(f"\n{'='*80}")
        print(f"Statistics:")
        print(f"  Total Executions: {total_count}")
        print(f"  Unique Tool Combinations: {unique_combinations}")
        if most_common:
            most_common_steps = json.loads(most_common[0])
            print(f"  Most Common: {', '.join(most_common_steps)} ({most_common[1]} times)")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"Error reading database: {e}")


if __name__ == "__main__":
    main()

