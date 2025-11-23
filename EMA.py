#!/usr/bin/env python3
"""
EMA - Efficient Memory Algorithm
Maps pattern names to numbers, tracks k recent blocks, generates subsequences,
and recommends: 
- nr most frequent subsequences from recent k blocks,
- nf most stable patterns from frequency table (outside recent k),
- ns most recently used single tools.
"""

from collections import defaultdict, deque
from itertools import combinations
import json
import ast
from pathlib import Path


class EMA:
    def __init__(self, k=10, t=50, nr=2, nf=5, ns=5, containers_dir=None):
        """
        Initialize EMA with:
        - k: number of recent blocks to track
        - t: maximum size of frequency table (for subsequences)
        - nr: number of subsequences to pick from recent blocks
        - nf: number of subsequences to pick from frequency table
        - ns: number of single tools to track from recent usage
        - containers_dir: directory path to load/save containers from/to (Path or str)
        - name_to_number: mapping from pattern names to numbers
        - number_to_name: reverse mapping
        - recent_blocks: deque to store last k blocks (as number sequences)
        - frequency_table: dict mapping subsequence -> {'frequency': int, 'last_usage': int}
        - recent_subsequences: track subsequences from recent k blocks
        - recent_single_tools: deque to track recently used single tools (pattern names)
        """
        self.k = k
        self.t = t
        self.nr = nr
        self.nf = nf
        self.ns = ns
        self.containers_dir = Path(containers_dir) if containers_dir else None
        
        # Initialize containers
        self.name_to_number = {}
        self.number_to_name = {}
        self.next_number = 1
        self.recent_blocks = deque(maxlen=k)
        self.frequency_table = {}  # subsequence -> {'frequency': int, 'last_usage': int}
        self.all_blocks = []  # Store all blocks for frequency tracking
        self.current_block_index = 0  # Track current position in all_blocks
        self.recent_subsequences = deque(maxlen=k)  # Track subsequences from recent k blocks
        self.recent_single_tools = deque(maxlen=ns * 10)  # Track more than ns to handle duplicates
        
        # Load from JSON files if containers_dir is provided and files exist
        if self.containers_dir:
            self.load_containers()
    
    def get_number_for_name(self, name):
        """Get number for a pattern name, creating mapping if needed."""
        if name not in self.name_to_number:
            self.name_to_number[name] = self.next_number
            self.number_to_name[self.next_number] = name
            self.next_number += 1
        return self.name_to_number[name]
    
    def block_to_sequence(self, block):
        """Convert a block (list of pattern names) to number sequence."""
        return tuple(self.get_number_for_name(name.strip()) 
                    for name in block.split(',') if name.strip())
    
    def generate_subsequences(self, sequence, min_length=1):
        """
        Generate all ordered subsequences (ordered subsets) of length >= min_length.
        Maintains order but allows skipping elements in between.
        For example, from [A, B, C] with min_length=1 generates: [A], [B], [C], [A,B], [A,C], [B,C], [A,B,C]
        """
        subsequences = []
        n = len(sequence)
        
        # Generate all ordered subsequences of length >= min_length
        for length in range(min_length, n + 1):
            # Generate all combinations of indices of this length
            for indices in combinations(range(n), length):
                # Extract subsequence maintaining order (indices are already sorted)
                subsequence = tuple(sequence[i] for i in indices)
                subsequences.append(subsequence)
        
        return subsequences
    
    def sequence_to_names(self, sequence):
        """Convert a number sequence back to pattern names."""
        return ', '.join(self.number_to_name[num] for num in sequence)
    
    def add_block(self, block):
        """Add a block to the system."""
        sequence = self.block_to_sequence(block)
        if not sequence:
            return
        
        # Store block
        self.all_blocks.append(block)
        self.current_block_index = len(self.all_blocks) - 1
        
        # Add to recent blocks (deque automatically maintains maxlen)
        self.recent_blocks.append(sequence)
        
        # Track single tools from this block (maintain recency order)
        # Extract tool names from block
        tool_names = [name.strip() for name in block.split(',') if name.strip()]
        for tool_name in tool_names:
            # Remove old occurrence if exists (to maintain recency)
            if tool_name in self.recent_single_tools:
                self.recent_single_tools.remove(tool_name)
            # Add to end (most recent)
            self.recent_single_tools.append(tool_name)
        
        # Generate subsequences from this block
        subsequences = self.generate_subsequences(sequence)
        
        # Track subsequences from recent k blocks
        self.recent_subsequences.append(subsequences)
        
        # Update frequency table (for subsequences outside recent k)
        self._update_frequency_table()
        
        # Evict entries if frequency table exceeds max size t
        if len(self.frequency_table) > self.t:
            self._evict_from_frequency_table()
    
    def _update_frequency_table(self):
        """Update frequency table for all subsequences across all blocks (entire time)."""
        # Get all subsequences from recent k blocks (for filtering when picking)
        recent_subseq_set = set()
        for subsequences in self.recent_subsequences:
            recent_subseq_set.update(subsequences)
        
        # Count frequency and track last usage for ALL subsequences from ALL blocks
        # This stores frequency for each pattern for entire time
        new_frequency_table = {}
        for i, block in enumerate(self.all_blocks):
            sequence = self.block_to_sequence(block)
            subsequences = self.generate_subsequences(sequence)
            
            for subsequence in subsequences:
                # Track ALL subsequences (not just those outside recent k)
                # This gives us full frequency history
                if subsequence not in new_frequency_table:
                    new_frequency_table[subsequence] = {'frequency': 0, 'last_usage': i}
                new_frequency_table[subsequence]['frequency'] += 1
                new_frequency_table[subsequence]['last_usage'] = max(
                    new_frequency_table[subsequence]['last_usage'], i
                )
        
        self.frequency_table = new_frequency_table
    
    def get_recent_subsequences(self):
        """Get all subsequences from recent k blocks and count frequencies."""
        subsequence_freq = defaultdict(int)
        
        for subsequences in self.recent_subsequences:
            for subsequence in subsequences:
                subsequence_freq[subsequence] += 1
        
        return subsequence_freq
    
    def pick_from_recent(self, n=None):
        """
        Pick n subsequences from recently used (last k blocks).
        Sorted by frequency * length to prioritize longer subsequences.
        If n is None, uses self.nr.
        """
        if n is None:
            n = self.nr
        
        # Get all subsequences from recent k blocks with their frequencies
        subsequence_freq = self.get_recent_subsequences()
        
        if not subsequence_freq:
            return []
        
        # Sort by frequency * length (descending), then by sequence (for consistency)
        sorted_items = sorted(
            subsequence_freq.items(),
            key=lambda x: (-x[1] * len(x[0]), x[0])  # frequency * length
        )
        
        # Return top n
        top_n = sorted_items[:n]
        return [
            {
                'sequence': seq,
                'names': self.sequence_to_names(seq),
                'frequency': freq,
                'length': len(seq),
                'score': freq * len(seq)  # frequency * length
            }
            for seq, freq in top_n
        ]
    
    def estimation_function(self, frequency, last_usage, current_index):
        """
        Estimation function that combines frequency and recency.
        Higher score = better to keep.
        
        Formula: frequency * recency_weight
        recency_weight = 1 / (1 + age) where age = current_index - last_usage
        This gives higher weight to more recent usage.
        """
        age = current_index - last_usage
        recency_weight = 1.0 / (1.0 + age)  # Decay with age
        return frequency * recency_weight
    
    def _evict_from_frequency_table(self):
        """
        Evict subsequences from frequency table based on estimation function.
        Removes subsequences with lowest estimation scores.
        """
        if len(self.frequency_table) <= self.t:
            return
        
        # Calculate estimation score for each subsequence
        entries_with_scores = []
        for subsequence, data in self.frequency_table.items():
            score = self.estimation_function(
                data['frequency'],
                data['last_usage'],
                self.current_block_index
            )
            entries_with_scores.append((subsequence, data, score))
        
        # Sort by estimation score (ascending - lowest scores first)
        entries_with_scores.sort(key=lambda x: (x[2], x[0]))
        
        # Calculate how many to remove
        num_to_remove = len(self.frequency_table) - self.t
        
        # Remove entries with lowest scores
        removed_subsequences = []
        for i in range(num_to_remove):
            subsequence, data, score = entries_with_scores[i]
            removed_subsequences.append(subsequence)
            del self.frequency_table[subsequence]
        
        return removed_subsequences
    
    def pick_from_frequency(self, n=None):
        """
        Pick n most stable subsequences from frequency table (can include recent k blocks).
        Sorted by frequency * length to prioritize longer subsequences.
        Uses estimation function for eviction, but picks by frequency * length score.
        If n is None, uses self.nf.
        """
        if n is None:
            n = self.nf
        
        # Update frequency table first to ensure it's current
        self._update_frequency_table()
        
        # Evict entries if frequency table exceeds max size t
        if len(self.frequency_table) > self.t:
            self._evict_from_frequency_table()
        
        if not self.frequency_table:
            return []
        
        # Use all items from frequency table (no filtering - can include recent k blocks)
        all_items = list(self.frequency_table.items())
        
        if not all_items:
            return []
        
        # Sort by frequency * length (descending), then by subsequence (for consistency)
        sorted_items = sorted(
            all_items,
            key=lambda x: (-x[1]['frequency'] * len(x[0]), x[0])  # frequency * length
        )
        
        # Return top n
        top_n = sorted_items[:n]
        return [
            {
                'sequence': subsequence,
                'names': self.sequence_to_names(subsequence),
                'frequency': data['frequency'],
                'length': len(subsequence),
                'score': data['frequency'] * len(subsequence),  # frequency * length
                'last_usage': data['last_usage']
            }
            for subsequence, data in top_n
        ]
    
    def get_recent_single_tools(self, n=None):
        """
        Get n most recently used single tools.
        Returns the last n tools from recent_single_tools (most recent first).
        If n is None, uses self.ns.
        """
        if n is None:
            n = self.ns
        
        # Get the last n tools (most recent are at the end of deque)
        # Convert to list and take last n, then reverse to show most recent first
        tools_list = list(self.recent_single_tools)
        recent_n = tools_list[-n:] if len(tools_list) >= n else tools_list
        recent_n.reverse()  # Most recent first
        
        return recent_n
    
    def get_selections(self):
        """
        Get nr subsequences from recent blocks, nf from frequency table, and ns single tools.
        """
        # Update frequency table first
        self._update_frequency_table()
        
        # Evict entries if frequency table exceeds max size t
        if len(self.frequency_table) > self.t:
            self._evict_from_frequency_table()
        
        recent_selections = self.pick_from_recent()
        frequency_selections = self.pick_from_frequency()
        single_tools = self.get_recent_single_tools()
        
        return {
            'from_recent': recent_selections,
            'from_frequency': frequency_selections,
            'single_tools': single_tools
        }
    
    def save_containers(self, containers_dir=None):
        """
        Save all containers to JSON files in the specified directory.
        If containers_dir is None, uses self.containers_dir.
        """
        if containers_dir:
            save_dir = Path(containers_dir)
        elif self.containers_dir:
            save_dir = self.containers_dir
        else:
            raise ValueError("No containers directory specified")
        
        # Create directory if it doesn't exist
        save_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Save name_to_number mapping
            with open(save_dir / "name_to_number.json", "w", encoding="utf-8") as f:
                json.dump(self.name_to_number, f, indent=2)
            
            # Save number_to_name mapping
            with open(save_dir / "number_to_name.json", "w", encoding="utf-8") as f:
                json.dump(self.number_to_name, f, indent=2)
            
            # Save next_number
            with open(save_dir / "next_number.json", "w", encoding="utf-8") as f:
                json.dump(self.next_number, f, indent=2)
            
            # Save recent_blocks (convert deque of tuples to list of lists)
            recent_blocks_list = [list(block) for block in self.recent_blocks]
            with open(save_dir / "recent_blocks.json", "w", encoding="utf-8") as f:
                json.dump(recent_blocks_list, f, indent=2)
            
            # Save frequency_table (convert tuple keys to lists for JSON)
            frequency_table_serialized = {}
            for key, value in self.frequency_table.items():
                key_list = list(key)  # Convert tuple to list for JSON
                frequency_table_serialized[str(key_list)] = value  # Use string representation as key
            with open(save_dir / "frequency_table.json", "w", encoding="utf-8") as f:
                json.dump(frequency_table_serialized, f, indent=2)
            
            # Save all_blocks
            with open(save_dir / "all_blocks.json", "w", encoding="utf-8") as f:
                json.dump(self.all_blocks, f, indent=2)
            
            # Save current_block_index
            with open(save_dir / "current_block_index.json", "w", encoding="utf-8") as f:
                json.dump(self.current_block_index, f, indent=2)
            
            # Save recent_subsequences (convert deque of lists of tuples to list of lists of lists)
            recent_subsequences_serialized = []
            for subsequences in self.recent_subsequences:
                subsequences_list = [list(subseq) for subseq in subsequences]
                recent_subsequences_serialized.append(subsequences_list)
            with open(save_dir / "recent_subsequences.json", "w", encoding="utf-8") as f:
                json.dump(recent_subsequences_serialized, f, indent=2)
            
            # Save recent_single_tools (convert deque to list)
            with open(save_dir / "recent_single_tools.json", "w", encoding="utf-8") as f:
                json.dump(list(self.recent_single_tools), f, indent=2)
            
            # Save configuration parameters
            config = {
                "k": self.k,
                "t": self.t,
                "nr": self.nr,
                "nf": self.nf,
                "ns": self.ns
            }
            with open(save_dir / "config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving containers: {e}")
            return False
    
    def load_containers(self, containers_dir=None):
        """
        Load all containers from JSON files in the specified directory.
        If containers_dir is None, uses self.containers_dir.
        """
        if containers_dir:
            load_dir = Path(containers_dir)
        elif self.containers_dir:
            load_dir = self.containers_dir
        else:
            return False
        
        if not load_dir.exists():
            return False
        
        try:
            # Load name_to_number mapping
            name_to_number_file = load_dir / "name_to_number.json"
            if name_to_number_file.exists():
                with open(name_to_number_file, "r", encoding="utf-8") as f:
                    self.name_to_number = json.load(f)
            
            # Load number_to_name mapping (convert keys to int)
            number_to_name_file = load_dir / "number_to_name.json"
            if number_to_name_file.exists():
                with open(number_to_name_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.number_to_name = {int(k): v for k, v in loaded.items()}
            
            # Load next_number
            next_number_file = load_dir / "next_number.json"
            if next_number_file.exists():
                with open(next_number_file, "r", encoding="utf-8") as f:
                    self.next_number = json.load(f)
            
            # Load recent_blocks (convert lists back to tuples)
            recent_blocks_file = load_dir / "recent_blocks.json"
            if recent_blocks_file.exists():
                with open(recent_blocks_file, "r", encoding="utf-8") as f:
                    recent_blocks_list = json.load(f)
                    self.recent_blocks = deque([tuple(block) for block in recent_blocks_list], maxlen=self.k)
            
            # Load frequency_table (convert list keys back to tuples)
            frequency_table_file = load_dir / "frequency_table.json"
            if frequency_table_file.exists():
                with open(frequency_table_file, "r", encoding="utf-8") as f:
                    frequency_table_serialized = json.load(f)
                    self.frequency_table = {}
                    for key_str, value in frequency_table_serialized.items():
                        # Convert string representation "[1, 2, 3]" back to tuple
                        try:
                            key_list = ast.literal_eval(key_str)  # Safely evaluate string to list
                            key_tuple = tuple(key_list)
                        except (ValueError, SyntaxError):
                            # Fallback: try parsing as string representation
                            key_str = key_str.strip()
                            if key_str.startswith("[") and key_str.endswith("]"):
                                key_str = key_str[1:-1]
                            if key_str:
                                key_tuple = tuple(int(x.strip()) for x in key_str.split(",") if x.strip())
                            else:
                                key_tuple = tuple()
                        self.frequency_table[key_tuple] = value
            
            # Load all_blocks
            all_blocks_file = load_dir / "all_blocks.json"
            if all_blocks_file.exists():
                with open(all_blocks_file, "r", encoding="utf-8") as f:
                    self.all_blocks = json.load(f)
            
            # Load current_block_index
            current_block_index_file = load_dir / "current_block_index.json"
            if current_block_index_file.exists():
                with open(current_block_index_file, "r", encoding="utf-8") as f:
                    self.current_block_index = json.load(f)
            
            # Load recent_subsequences (convert lists back to tuples)
            recent_subsequences_file = load_dir / "recent_subsequences.json"
            if recent_subsequences_file.exists():
                with open(recent_subsequences_file, "r", encoding="utf-8") as f:
                    recent_subsequences_serialized = json.load(f)
                    self.recent_subsequences = deque(maxlen=self.k)
                    for subsequences_list in recent_subsequences_serialized:
                        subsequences_tuples = [tuple(subseq) for subseq in subsequences_list]
                        self.recent_subsequences.append(subsequences_tuples)
            
            # Load recent_single_tools (convert list back to deque)
            recent_single_tools_file = load_dir / "recent_single_tools.json"
            if recent_single_tools_file.exists():
                with open(recent_single_tools_file, "r", encoding="utf-8") as f:
                    tools_list = json.load(f)
                    self.recent_single_tools = deque(tools_list, maxlen=self.ns * 10)
            
            return True
        except Exception as e:
            print(f"Error loading containers: {e}")
            return False


def load_patterns(filename='use_case_patterns.txt'):
    """Load pattern blocks from file, skipping empty lines and separators."""
    blocks = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and separator lines (just dashes)
                if line and line != '-':
                    blocks.append(line)
        return blocks
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        return []


def main():
    # Initialize EMA with k=10 (last 10 blocks), t=50 (max frequency table size),
    # nr=5 (number from recent), nf=5 (number from frequency table), ns=5 (number of single tools)
    ema = EMA(k=10, t=50, nr=5, nf=5, ns=5)
    
    # Load pattern blocks from file
    blocks = load_patterns('recommendation_showcase_patterns.txt')
    
    if not blocks:
        print("No blocks loaded. Exiting.")
        return
    
    print(f"Loaded {len(blocks)} blocks from recommendation_showcase_patterns.txt")
    print(f"Initializing EMA with k={ema.k} (recent blocks), t={ema.t} (frequency table size)")
    print(f"nr={ema.nr} (from recent), nf={ema.nf} (from frequency table), ns={ema.ns} (single tools)\n")
    
    # Add all blocks to EMA
    for block in blocks:
        ema.add_block(block)
    
    print(f"Total unique pattern names: {len(ema.name_to_number)}")
    print(f"Recent blocks tracked: {len(ema.recent_blocks)}\n")
    
    # Get selections
    selections = ema.get_selections()
    
    print("=" * 80)
    print("RECOMMENDATIONS:")
    print("=" * 80)
    
    print(f"\n{ema.nr} Most Frequent Subsequences from Recent {ema.k} Blocks:")
    print("-" * 80)
    if selections['from_recent']:
        for i, item in enumerate(selections['from_recent'], 1):
            print(f"{i}. {item['names']}")
            print(f"   Frequency: {item['frequency']}, Length: {item['length']}, Score: {item['score']} (frequency * length)")
            print(f"   Sequence: {item['sequence']}")
            print()
    else:
        print("No subsequences found.")
    
    print(f"\n{ema.nf} Most Stable Subsequences from Frequency Table (outside recent {ema.k}):")
    print("-" * 80)
    if selections['from_frequency']:
        for i, item in enumerate(selections['from_frequency'], 1):
            print(f"{i}. {item['names']}")
            print(f"   Frequency: {item['frequency']}, Length: {item['length']}, Score: {item['score']} (frequency * length)")
            print(f"   Last usage index: {item['last_usage']}, Sequence: {item['sequence']}")
            print()
    else:
        print("No subsequences found in frequency table.")
    
    print(f"\n{ema.ns} Most Recently Used Single Tools:")
    print("-" * 80)
    if selections['single_tools']:
        for i, tool_name in enumerate(selections['single_tools'], 1):
            print(f"{i}. {tool_name}")
    else:
        print("No single tools found.")
    
    print("=" * 80)
    print(f"Total blocks processed: {len(ema.all_blocks)}")
    print(f"Blocks in recent history: {len(ema.recent_blocks)}")
    print(f"Subsequences in frequency table: {len(ema.frequency_table)} (max: {ema.t})")
    print(f"Single tools tracked: {len(ema.recent_single_tools)}")
    print("=" * 80)


if __name__ == '__main__':
    main()
