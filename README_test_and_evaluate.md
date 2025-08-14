# Test and Evaluate Script

This script processes Multi-SWE-bench instances by running Docker containers, executing tests, applying patches, and categorizing test transitions.

## Features

- **Complete Test Workflow**: Runs three phases (run, test_patch, fix_patch) for each instance
- **Test Transition Analysis**: Categorizes tests into F2P (Fail-to-Pass), P2P (Pass-to-Pass), S2P (Skip-to-Pass), N2P (None-to-Pass), etc.
- **Docker Integration**: Automatically finds and uses appropriate Docker images
- **Parallel Processing**: Configurable number of workers for concurrent processing
- **Comprehensive Logging**: Detailed progress tracking with emoji indicators
- **Error Handling**: Graceful handling of missing images, timeouts, and other errors
- **JSON Output**: Results saved in JSONL format with complete test details

## Usage

```bash
# Basic usage
python test_and_evaluate.py instances.jsonl --registry mswebench

# With custom output file and parallel processing
python test_and_evaluate.py instances.jsonl --output results.jsonl --registry mswebench --max-workers 4

# Sequential processing with debug logging
python test_and_evaluate.py instances.jsonl --max-workers 1 --log-level DEBUG --timeout 600
```

## Output Format

Each result includes:
- **Instance metadata**: org, repo, number, title, body, patches
- **Test results**: Detailed counts and lists for each phase (run, test_patch, fix_patch)
- **Transition analysis**: F2P, P2P, S2P, N2P tests with specific test names
- **Fixed tests**: Summary of tests that were fixed by the patch

## Example Output

```json
{
  "org": "google",
  "repo": "gson", 
  "number": 2043,
  "run_result": {
    "passed_count": 9,
    "failed_count": 0,
    "skipped_count": 0,
    "passed_tests": ["com.google.gson.GsonBuilderTest", ...],
    "failed_tests": [],
    "skipped_tests": []
  },
  "test_patch_result": { ... },
  "fix_patch_result": { ... },
  "f2p_tests": {},
  "p2p_tests": {},
  "s2p_tests": {},
  "n2p_tests": {},
  "fixed_tests": {}
}
```

## Requirements

- Docker with Multi-SWE-bench images
- Python 3.8+ with required dependencies
- Multi-SWE-bench harness installed

## Test Transition Categories

- **F2P (Fail-to-Pass)**: Tests that failed initially but passed after applying the fix
- **P2P (Pass-to-Pass)**: Tests that passed both before and after the fix
- **S2P (Skip-to-Pass)**: Tests that were skipped initially but passed after the fix
- **N2P (None-to-Pass)**: Tests that had no result initially but passed after the fix
- **P2F (Pass-to-Fail)**: Tests that passed initially but failed after the fix
- **F2F (Fail-to-Fail)**: Tests that failed both before and after the fix