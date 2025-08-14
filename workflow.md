# Multi-SWE-bench Data Collection Workflow

This document provides a comprehensive workflow for agents to collect more instances and create datasets similar to `multi_swe_bench/collect/example.jsonl`.

## Overview

Multi-SWE-bench is a multilingual benchmark for evaluating LLMs in real-world code issue resolution. The data collection process involves finding GitHub repositories, extracting pull requests that resolve issues, and creating structured datasets with code patches and test results.

## Prerequisites

### 1. Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Ensure Docker is installed for evaluation
docker --version
```

### 2. GitHub API Tokens
- Obtain GitHub Personal Access Tokens for API access
- Store tokens in a file or provide as command-line arguments
- Multiple tokens recommended for higher rate limits

### 3. Required Tools
- `jq` for JSON processing
- `git` for repository operations
- `docker` for containerized evaluation

## Workflow Steps

### Step 1: Repository Discovery

#### Option A: Crawl Repositories by Language
Use `crawl_repos.py` to discover popular repositories in specific programming languages:

```bash
python multi_swe_bench/collect/crawl_repos.py \
    --language java \
    --min_stars 1000 \
    --max_results 500 \
    --output csv \
    --token <your_github_token> \
    --output_dir ./repo_lists
```

**Parameters:**
- `--language`: Programming language (java, typescript, javascript, go, rust, c, cpp)
- `--min_stars`: Minimum star count for repositories
- `--max_results`: Maximum number of repositories to fetch
- `--output`: Output format (csv or console)
- `--token`: GitHub API token
- `--output_dir`: Directory to save CSV files

**Output:** CSV file with repository names, stars, forks, descriptions, and URLs.

#### Option B: Manual Repository Selection
Create a CSV file with repository names in the format:
```csv
Name
org1/repo1
org2/repo2
```

### Step 2: Single Repository Processing

For processing individual repositories, use `get_pipeline.py`:

```bash
python multi_swe_bench/collect/get_pipeline.py \
    --out_dir ./output \
    --tokens <token1> <token2> \
    --org alibaba \
    --repo fastjson2 \
    --delay-on-error 300 \
    --retry-attempts 3 \
    --skip-commit-message false
```

**Parameters:**
- `--out_dir`: Output directory for processed data
- `--tokens`: GitHub API tokens (multiple tokens for better rate limits)
- `--org`: GitHub organization name
- `--repo`: Repository name
- `--delay-on-error`: Delay in seconds before retrying on error
- `--retry-attempts`: Number of retry attempts
- `--skip-commit-message`: Skip commit message processing

**Pipeline Steps:**
1. **Get All PRs**: Fetches all pull requests from the repository
2. **Filter PRs**: Filters for closed PRs that resolve issues
3. **Get Related Issues**: Retrieves issues referenced by the PRs
4. **Merge Data**: Combines PR and issue information
5. **Build Dataset**: Downloads patches and creates final dataset

### Step 3: Batch Repository Processing

For processing multiple repositories from a CSV file, use `get_from_repos_pipeline.py`:

```bash
python multi_swe_bench/collect/get_from_repos_pipeline.py \
    --csv_file ./repo_lists/github_java_repos_20250725_120000.csv \
    --out_dir ./batch_output \
    --max_workers 4 \
    --distribute round \
    --tokens <token1> <token2> <token3> \
    --delay-on-error 300 \
    --retry-attempts 3
```

**Parameters:**
- `--csv_file`: Path to CSV file with repository names
- `--out_dir`: Base output directory
- `--max_workers`: Maximum concurrent processes
- `--distribute`: Distribution strategy (round or chunk)
- `--tokens`: Multiple GitHub API tokens
- `--delay-on-error`: Error retry delay
- `--retry-attempts`: Number of retry attempts

**Distribution Strategies:**
- `round`: Round-robin distribution of repositories among tokens
- `chunk`: Equal chunks distribution among tokens

### Step 4: Data Quality Validation

After processing, validate the collected data:

#### Check Output Structure
```bash
# Verify output directory structure
ls -la ./output/org__repo/

# Expected files:
# - org__repo_prs.jsonl (all PRs)
# - org__repo_filtered_prs.jsonl (filtered PRs)
# - org__repo_filtered_prs_with_issues.jsonl (PRs with issues)
# - org__repo_dataset.jsonl (final dataset)
```

#### Validate Data Format
```bash
# Check final dataset format
head -1 ./output/org__repo/org__repo_dataset.jsonl | jq .

# Verify required fields:
# - org, repo, number, state, title, body
# - base (label, ref, sha)
# - resolved_issues (array with number, title, body)
# - fix_patch, test_patch
# - fixed_tests, failed_tests, skipped_tests
# - instance_id
```

#### Quality Metrics
```bash
# Count total instances
wc -l ./output/org__repo/org__repo_dataset.jsonl

# Check for instances with both fix and test patches
jq 'select(.fix_patch != null and .test_patch != null)' ./output/org__repo/org__repo_dataset.jsonl | wc -l

# Verify test results exist
jq 'select(.fixed_tests != null)' ./output/org__repo/org__repo_dataset.jsonl | wc -l
```

### Step 5: Dataset Consolidation

Combine datasets from multiple repositories:

```bash
# Create consolidated dataset
mkdir -p ./final_dataset

# Combine all datasets
find ./batch_output -name "*_dataset.jsonl" -exec cat {} \; > ./final_dataset/multi_swe_bench_new.jsonl

# Count total instances
wc -l ./final_dataset/multi_swe_bench_new.jsonl

# Validate consolidated dataset
head -5 ./final_dataset/multi_swe_bench_new.jsonl | jq .
```

## Data Schema

Each instance in the final dataset should contain:

```json
{
  "org": "string",                    // GitHub organization
  "repo": "string",                   // Repository name
  "number": "integer",                // PR number
  "state": "string",                  // PR state (should be "closed")
  "title": "string",                  // PR title
  "body": "string",                   // PR description
  "base": {                           // Base branch information
    "label": "string",                // Branch label
    "ref": "string",                  // Branch reference
    "sha": "string"                   // Commit SHA
  },
  "resolved_issues": [                // Array of resolved issues
    {
      "number": "integer",            // Issue number
      "title": "string",              // Issue title
      "body": "string"                // Issue description
    }
  ],
  "fix_patch": "string",              // Git diff for the fix
  "test_patch": "string",             // Git diff for tests
  "fixed_tests": {                    // Test results after fix
    "test_class_name": {
      "run": "PASS|FAIL",
      "test": "PASS|FAIL|NONE",
      "fix": "PASS|FAIL"
    }
  },
  "failed_tests": ["string"],         // List of failed test names
  "skipped_tests": ["string"],        // List of skipped test names
  "instance_id": "string"             // Unique identifier (org__repo-number)
}
```

## Best Practices

### 1. Repository Selection
- Focus on active repositories with recent commits
- Prefer repositories with good test coverage
- Select repositories from different domains/use cases
- Consider language-specific popular frameworks and libraries

### 2. Rate Limiting
- Use multiple GitHub tokens to increase rate limits
- Implement proper delays between requests
- Monitor rate limit headers in API responses
- Use exponential backoff for retries

### 3. Error Handling
- Log all errors with context information
- Implement retry mechanisms for transient failures
- Skip repositories that consistently fail
- Validate data at each pipeline step

### 4. Data Quality
- Filter for PRs that actually resolve issues
- Ensure patches contain meaningful code changes
- Verify test patches exist and are relevant
- Remove duplicate instances across repositories

### 5. Storage and Organization
- Use consistent directory naming conventions
- Keep intermediate files for debugging
- Implement checkpointing for long-running processes
- Compress large datasets for storage efficiency

## Troubleshooting

### Common Issues

#### 1. API Rate Limiting
```bash
# Error: API rate limit exceeded
# Solution: Add more tokens or increase delays
--tokens token1 token2 token3 --delay-on-error 600
```

#### 2. Missing Patches
```bash
# Error: fix_patch or test_patch is null
# Check: PR actually contains code changes
jq 'select(.fix_patch == null)' dataset.jsonl
```

#### 3. Empty Test Results
```bash
# Error: fixed_tests is empty
# Check: Repository has proper test infrastructure
# Verify: Docker environment can run tests
```

#### 4. Memory Issues
```bash
# Error: Out of memory during processing
# Solution: Process repositories in smaller batches
--max_workers 2  # Reduce concurrent processes
```

### Debugging Commands

```bash
# Check API token validity
curl -H "Authorization: token <your_token>" https://api.github.com/rate_limit

# Validate JSON format
jq empty dataset.jsonl  # Should produce no output if valid

# Check for duplicate instances
jq -r '.instance_id' dataset.jsonl | sort | uniq -d

# Analyze patch sizes
jq -r '.fix_patch | length' dataset.jsonl | sort -n | tail -10
```

## Performance Optimization

### 1. Parallel Processing
- Use multiple workers for batch processing
- Distribute repositories across different tokens
- Process different languages simultaneously

### 2. Caching
- Cache API responses to avoid redundant requests
- Store intermediate results for resumability
- Use local git clones for patch extraction

### 3. Filtering
- Apply early filtering to reduce processing overhead
- Skip repositories with insufficient activity
- Filter out PRs without proper issue references

## Output Validation Checklist

Before finalizing the dataset, ensure:

- [ ] All instances have required fields
- [ ] Instance IDs are unique across the dataset
- [ ] Fix patches contain actual code changes
- [ ] Test patches are present and relevant
- [ ] Test results are properly formatted
- [ ] No sensitive information is included
- [ ] Dataset size is reasonable for intended use
- [ ] Data distribution across languages is balanced

## Next Steps

After collecting the dataset:

1. **Evaluation Setup**: Prepare Docker environments for testing
2. **Baseline Testing**: Run existing models on the new dataset
3. **Quality Assessment**: Manual review of sample instances
4. **Documentation**: Update dataset documentation and metadata
5. **Publication**: Share dataset with the community

## Support and Resources

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Refer to existing Multi-SWE-bench documentation
- **Community**: Join Discord for discussions and support
- **Examples**: Study existing datasets for reference patterns

---

This workflow provides a comprehensive guide for collecting high-quality Multi-SWE-bench instances. Follow the steps systematically and validate data quality at each stage to ensure the resulting dataset meets the benchmark standards.