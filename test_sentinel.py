#!/usr/bin/env python3

import json
import sys
from multi_swe_bench.harness.pull_request import PullRequest
from multi_swe_bench.harness.image import Config
from multi_swe_bench.harness.repos.java.alibaba.sentinel import Sentinel

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
    
    print(f'Instance created successfully: {instance}')
    print(f'PR: {instance.pr}')
    print(f'Run command: {instance.run()}')
    print(f'Test patch run command: {instance.test_patch_run()}')
    print(f'Fix patch run command: {instance.fix_patch_run()}')
    
    return 0

if __name__ == "__main__":
    sys.exit(main())