#!/usr/bin/env python3
"""
Quick Publish Script for Multi-SWE-bench Docker Images

A simplified wrapper around batch_build_and_publish.py for common use cases.

Usage:
    # Publish to Docker Hub (mswebench organization)
    python quick_publish.py instances.jsonl

    # Publish to custom registry
    python quick_publish.py instances.jsonl --registry myregistry.com/mswebench

    # Just build locally (no push)
    python quick_publish.py instances.jsonl --no-push
"""

import argparse
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Quick publish Multi-SWE-bench Docker images",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'input_file',
        type=Path,
        help='Input JSONL file with harnessed instances'
    )
    
    parser.add_argument(
        '--registry',
        type=str,
        default='mswebench',
        help='Docker registry (default: mswebench for Docker Hub)'
    )
    
    parser.add_argument(
        '--no-push',
        action='store_true',
        help='Only build locally, do not push to registry'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of concurrent workers (default: 4)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force rebuild even if images exist'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it'
    )
    
    args = parser.parse_args()
    
    # Build command for batch_build_and_publish.py (in same directory)
    script_dir = Path(__file__).parent
    batch_script = script_dir / 'batch_build_and_publish.py'
    cmd = [
        'python', str(batch_script),
        '--input', str(args.input_file),
        '--registry', args.registry,
        '--max-workers', str(args.workers),
        '--update-lists'
    ]
    
    if not args.no_push:
        cmd.append('--push')
    
    if args.force:
        cmd.append('--force-build')
    
    if args.dry_run:
        cmd.append('--dry-run')
    
    print(f"Running: {' '.join(cmd)}")
    
    # Execute the command
    try:
        result = subprocess.run(cmd, check=True)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\n❌ Process interrupted by user")
        sys.exit(1)

if __name__ == "__main__":
    main()