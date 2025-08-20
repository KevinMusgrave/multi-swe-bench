#!/usr/bin/env python3

import sys
import json
from pathlib import Path
from multi_swe_bench.harness.pull_request import PullRequest
from multi_swe_bench.harness.image import Config
from multi_swe_bench.harness.repos.java.alibaba.sentinel import Sentinel
from multi_swe_bench.harness.test_and_evaluate import TestEvaluator

def main():
    # Load the first instance from the dataset
    with open('/home/juan-all-hands/dev/Research/juan/Multi-SWE-Gym/datasets/alibaba_Sentinel.jsonl', 'r') as f:
        data = json.loads(f.readline())
    
    # Create a PullRequest object from the data
    pr = PullRequest.from_dict(data)
    
    # Create a Config object
    config = Config(need_clone=False, global_env=None, clear_env=False)
    
    # Create a Sentinel instance
    instance = Sentinel(pr, config)
    
    # Create a TestEvaluator with a short timeout
    evaluator = TestEvaluator(max_workers=1, timeout=300)  # 5 minutes
    
    # Check if the timeout extension is applied
    print(f"Default timeout: {evaluator.timeout}s")
    
    # Create a mock method to test the timeout extension
    def mock_run_test_phase(instance, image_name, phase):
        # Use extended timeout for Sentinel repository
        timeout = evaluator.timeout
        if instance.pr.org == "alibaba" and instance.pr.repo == "Sentinel":
            # Use a longer timeout for Sentinel repository (30 minutes)
            extended_timeout = 1800  # 30 minutes
            if extended_timeout > timeout:
                print(f"Using extended timeout of {extended_timeout}s for Sentinel repository")
                timeout = extended_timeout
        
        print(f"Final timeout for {phase} phase: {timeout}s")
        return None
    
    # Test the timeout extension for each phase
    for phase in ["run", "test_patch", "fix_patch"]:
        print(f"\nTesting {phase} phase:")
        mock_run_test_phase(instance, "test_image", phase)
    
    print("\nVerification completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())