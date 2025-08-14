#!/usr/bin/env python3

import json
import sys
import subprocess
from pathlib import Path

def main():
    # Read the dataset
    dataset_path = Path("/home/juan-all-hands/dev/multi-swe-bench-fork/multi_swe_bench/collect/experiment_2/dataset2_.jsonl")
    
    if not dataset_path.exists():
        print(f"Dataset file not found: {dataset_path}")
        sys.exit(1)
    
    # Parse the dataset and extract PR numbers
    prs_to_build = []
    with open(dataset_path, 'r') as f:
        for line in f:
            data = json.loads(line.strip())
            org = data['org']
            repo = data['repo']
            pr_number = data['number']
            
            # Check if image already exists
            image_name = f"mswebench/{org}_m_{repo}:pr-{pr_number}"
            result = subprocess.run(['docker', 'images', '-q', image_name], 
                                  capture_output=True, text=True)
            
            if not result.stdout.strip():
                print(f"Need to build image for {org}/{repo} PR #{pr_number}")
                prs_to_build.append((org, repo, pr_number))
            else:
                print(f"Image already exists for {org}/{repo} PR #{pr_number}")
    
    if not prs_to_build:
        print("All images already exist!")
        return
    
    # Create a temporary dataset file with only the missing PRs
    temp_dataset = Path("/tmp/missing_prs.jsonl")
    with open(dataset_path, 'r') as input_file, open(temp_dataset, 'w') as output_file:
        for line in input_file:
            data = json.loads(line.strip())
            if (data['org'], data['repo'], data['number']) in prs_to_build:
                output_file.write(line)
    
    print(f"Building {len(prs_to_build)} missing images...")
    
    # Create workdir, log dir, and repo dir
    workdir = Path("/tmp/mswebench_workdir")
    workdir.mkdir(exist_ok=True)
    logdir = Path("/tmp/mswebench_logs")
    logdir.mkdir(exist_ok=True)
    repodir = Path("/tmp/mswebench_repos")
    repodir.mkdir(exist_ok=True)
    
    # Run the build command
    cmd = [
        'python', '-m', 'multi_swe_bench.harness.build_dataset',
        '--raw_dataset_files', str(temp_dataset),
        '--mode', 'image',
        '--workdir', str(workdir),
        '--log_dir', str(logdir),
        '--repo_dir', str(repodir),
        '--max_workers_build_image', '4',
        '--log_level', 'INFO'
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    
    # Change to the repository root directory
    repo_root = Path("/home/juan-all-hands/dev/multi-swe-bench-fork")
    result = subprocess.run(cmd, cwd=repo_root)
    
    # Clean up temp file
    temp_dataset.unlink()
    
    if result.returncode == 0:
        print("Successfully built all missing images!")
    else:
        print(f"Build failed with return code: {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()