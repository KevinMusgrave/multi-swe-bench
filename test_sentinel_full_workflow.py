#!/usr/bin/env python3

import json
import sys
import os
import subprocess
from pathlib import Path

def run_command(command, timeout=None):
    """Run a command and return the output."""
    print(f"Running command: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        print(f"Command succeeded with output:\n{result.stdout}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command failed with error:\n{e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds")
        return None

def main():
    # Create a small test dataset with just one instance
    with open('/home/juan-all-hands/dev/Research/juan/Multi-SWE-Gym/datasets/alibaba_Sentinel.jsonl', 'r') as f:
        data = json.loads(f.readline())
    
    # Create a temporary file with just this instance
    temp_file = Path('/home/juan-all-hands/dev/multi-swe-bench-fork/test_sentinel_single_instance.jsonl')
    with open(temp_file, 'w') as f:
        f.write(json.dumps(data) + '\n')
    
    # Create a temporary output file
    temp_output = Path('/home/juan-all-hands/dev/multi-swe-bench-fork/test_sentinel_single_results.jsonl')
    
    # Run quick_publish.py
    print("\n=== Running quick_publish.py ===\n")
    quick_publish_cmd = f"cd /home/juan-all-hands/dev/multi-swe-bench-fork && python -m multi_swe_bench.harness.quick_publish {temp_file} --registry mswebench --force"
    if not run_command(quick_publish_cmd, timeout=600):
        print("quick_publish.py failed")
        return 1
    
    # Run test_and_evaluate.py
    print("\n=== Running test_and_evaluate.py ===\n")
    test_evaluate_cmd = f"cd /home/juan-all-hands/dev/multi-swe-bench-fork && python -m multi_swe_bench.harness.test_and_evaluate {temp_file} --output {temp_output} --registry mswebench --timeout 1800 --log-level DEBUG"
    if not run_command(test_evaluate_cmd, timeout=3600):
        print("test_and_evaluate.py failed")
        return 1
    
    # Check the results
    print("\n=== Checking results ===\n")
    if temp_output.exists():
        with open(temp_output, 'r') as f:
            result_data = json.loads(f.readline())
        
        print(f"Results for PR #{result_data['number']}:")
        print(f"Run result: {result_data.get('run_result', {}).get('passed_count', 0)} passed, {result_data.get('run_result', {}).get('failed_count', 0)} failed")
        print(f"Test patch result: {result_data.get('test_patch_result', {}).get('passed_count', 0)} passed, {result_data.get('test_patch_result', {}).get('failed_count', 0)} failed")
        print(f"Fix patch result: {result_data.get('fix_patch_result', {}).get('passed_count', 0)} passed, {result_data.get('fix_patch_result', {}).get('failed_count', 0)} failed")
        
        # Check if any tests passed
        if (result_data.get('run_result', {}).get('passed_count', 0) > 0 or
            result_data.get('test_patch_result', {}).get('passed_count', 0) > 0 or
            result_data.get('fix_patch_result', {}).get('passed_count', 0) > 0):
            print("\n✅ Success! At least one phase has passing tests.")
        else:
            print("\n❌ Failure! No tests passed in any phase.")
            return 1
    else:
        print(f"Results file not found: {temp_output}")
        return 1
    
    print("\nFull workflow test completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())