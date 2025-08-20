#!/usr/bin/env python3

import json
import sys
import os
from pathlib import Path
from multi_swe_bench.harness.test_and_evaluate import main as test_and_evaluate_main

def main():
    # Create a small test dataset with just one instance
    with open('/home/juan-all-hands/dev/Research/juan/Multi-SWE-Gym/datasets/alibaba_Sentinel.jsonl', 'r') as f:
        data = json.loads(f.readline())
    
    # Create a temporary file with just this instance
    temp_file = Path('/home/juan-all-hands/dev/multi-swe-bench-fork/test_sentinel_instance.jsonl')
    with open(temp_file, 'w') as f:
        f.write(json.dumps(data) + '\n')
    
    # Set up arguments for test_and_evaluate_main
    sys.argv = [
        'test_and_evaluate.py',
        str(temp_file),
        '--output', '/home/juan-all-hands/dev/multi-swe-bench-fork/test_sentinel_results.jsonl',
        '--limit', '1',
        '--log-level', 'DEBUG'
    ]
    
    # Run the test_and_evaluate_main function
    try:
        test_and_evaluate_main()
        print("Test and evaluate completed successfully")
    except Exception as e:
        print(f"Error running test_and_evaluate: {e}")
    
    # Clean up the temporary file
    if temp_file.exists():
        os.remove(temp_file)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())