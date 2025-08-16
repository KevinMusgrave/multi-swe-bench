# Force Logic Changes for test_and_evaluate.py

## Problem
Previously, when using the `--force` flag with `test_and_evaluate.py`, the script would clear the entire output file, removing ALL previously processed instances, not just the ones being reprocessed in the current run.

## Solution
Modified the force logic to be selective:

1. **Before**: `--force` cleared the entire output file and reprocessed all instances in the input
2. **After**: `--force` only overwrites instances that are present in the current input file, preserving results for other instances

## Changes Made

### 1. New Function: `load_and_filter_existing_results()`
- Loads existing results from the output file
- Filters out instances that are being reprocessed (present in current input)
- Returns only the results that should be preserved

### 2. Modified Force Logic in `main()`
- When `--force` is enabled:
  - Extracts instance IDs from current input file
  - Loads and filters existing results to preserve non-overlapping instances
  - Rewrites output file with only preserved results (or clears if none to preserve)
  - Processes all instances from current input (no skipping)

### 3. Updated Help Text
- Changed help text to clarify the new selective behavior
- Updated examples to show the new use case

## Benefits

1. **Selective Reprocessing**: Only reprocess specific instances without losing other results
2. **Incremental Workflows**: Can add new instances to existing result files safely
3. **Error Recovery**: Can reprocess failed instances without losing successful ones
4. **Batch Processing**: Can process different subsets of instances in separate runs

## Example Usage

```bash
# Initial run with 100 instances
python test_and_evaluate.py --input all_instances.jsonl --output results.jsonl

# Later, reprocess only 5 specific instances (preserves the other 95 results)
python test_and_evaluate.py --input failed_instances.jsonl --output results.jsonl --force
```

## Backward Compatibility
- Non-force behavior remains unchanged
- Force behavior is more intelligent but achieves the same end result when reprocessing the same input file
- All other command-line options work the same way

## Testing
- Created and ran unit tests to verify the filtering logic works correctly
- Verified that preserved instances remain intact while target instances are removed for reprocessing