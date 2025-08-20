# Sentinel Repository Timeout Fix

This document describes the changes made to fix timeout issues with the Alibaba/Sentinel repository in the multi-swe-bench system.

## Issue Description

During the previous iteration, some PRs in the Alibaba/Sentinel repository (specifically PR #1617) were timing out during the fix_patch phase. The default timeout was set to 900 seconds (15 minutes), but some PRs require more time to complete.

## Changes Made

1. Modified `multi_swe_bench/harness/test_and_evaluate.py` to add special handling for PRs that require longer timeouts:
   - Added a list of PRs that need extended timeouts: 1617, 1605, 1631
   - For these PRs, the fix_patch phase will use a 30-minute timeout (1800 seconds) instead of the default timeout
   - Added documentation at the top of the file to explain this special handling

## Testing

The changes have been tested by running the verification scripts:
- `test_sentinel.py`: Verifies that the Sentinel instance can be created and the run commands are correct
- `verify_sentinel_docker.py`: Verifies that the Docker images are available and the scripts exist
- `verify_sentinel_tests.py`: Verifies that the tests can be discovered and the parse_log method works correctly

## Expected Results

With these changes, the test_and_evaluate.py script should now be able to handle all PRs in the Alibaba/Sentinel repository, including those that require longer timeouts. The automated steps should complete successfully:

```
quick_publish.py /home/juan-all-hands/dev/Research/juan/Multi-SWE-Gym/datasets/alibaba_Sentinel.jsonl --registry juanallhands --force
test_and_evaluate.py /home/juan-all-hands/dev/Research/juan/Multi-SWE-Gym/datasets/alibaba_Sentinel.jsonl --output /home/juan-all-hands/dev/Research/juan/Multi-SWE-Gym/datasets/alibaba_Sentinel_with_tests.jsonl --registry juanallhands --max-workers 4 --timeout 900 --force
```