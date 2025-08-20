#!/usr/bin/env python3
"""
Test and Evaluation Script for Multi-SWE-bench

This script takes a JSONL file of instances, loads their Docker images,
runs tests (baseline, test patch, fix patch), and outputs comprehensive
test results with transition categorizations (f2p, p2p, s2p, n2p).

Usage:
    python test_and_evaluate.py --input instances.jsonl --output results.jsonl [options]

Note:
    Special handling has been added for certain PRs (1617, 1605, 1631) that require
    longer timeouts for the fix_patch phase. These PRs will use a 30-minute timeout
    instead of the default timeout specified by the --timeout parameter.
    
    Additionally, all PRs from the alibaba/Sentinel repository will use a 30-minute
    timeout for all phases to ensure tests have enough time to complete.
"""

import argparse
import asyncio
import json
import logging
import tempfile
import time
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from multi_swe_bench.harness.dataset import Dataset
from multi_swe_bench.harness.image import Config
from multi_swe_bench.harness.instance import Instance
from multi_swe_bench.harness.pull_request import PullRequest
from multi_swe_bench.harness.report import generate_report
from multi_swe_bench.harness.test_result import Test, TestResult, TestStatus
from multi_swe_bench.utils import docker_util

# Import repository classes to register them
import multi_swe_bench.harness.repos.java.alibaba.sentinel
import multi_swe_bench.harness.repos.java.google.gson
import multi_swe_bench.harness.repos.java.google.guava
import multi_swe_bench.harness.repos.java.google.guice
import multi_swe_bench.harness.repos.java.seleniumhq.selenium
import multi_swe_bench.harness.repos.java.test.repo


class TestEvaluator:
    """Handles test execution and evaluation for Multi-SWE-bench instances."""
    
    def __init__(self, max_workers: int = 4, timeout: int = 1800, registry: str = ""):
        self.max_workers = max_workers
        self.timeout = timeout
        self.registry = registry
        self.logger = logging.getLogger(__name__)
        
        # Create temp directory for logs
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_eval_"))
        self.logger.info(f"Using temp directory: {self.temp_dir}")
    
    def cleanup(self):
        """Clean up temporary files and orphaned Docker containers."""
        import shutil
        
        # Clean up orphaned containers
        try:
            cleaned_count = docker_util.cleanup_orphaned_containers(max_age_hours=0.5)
            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} orphaned Docker containers")
        except Exception as e:
            self.logger.warning(f"Failed to clean up orphaned containers: {e}")
        
        # Clean up temp directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.logger.info(f"Cleaned up temp directory: {self.temp_dir}")
    
    def get_image_name(self, instance_data: dict) -> str:
        """Generate Docker image name for an instance."""
        org = instance_data['org']
        repo = instance_data['repo']
        number = instance_data['number']
        
        if self.registry:
            return f"{self.registry}/{org}_m_{repo}:pr-{number}".lower()
        else:
            # Check if the image exists with mswebench prefix first
            mswebench_name = f"mswebench/{org}_m_{repo}:pr-{number}".lower()
            if docker_util.exists(mswebench_name):
                return mswebench_name
            return f"{org}_m_{repo}:pr-{number}".lower()
    
    def check_image_exists(self, image_name: str) -> bool:
        """Check if Docker image exists locally."""
        return docker_util.exists(image_name)
    
    def run_test_phase(self, instance: Instance, image_name: str, phase: str) -> TestResult:
        """
        Run a specific test phase (run, test_patch, fix_patch).
        
        Args:
            instance: Multi-SWE-bench instance
            image_name: Docker image name
            phase: One of 'run', 'test_patch', 'fix_patch'
        
        Returns:
            TestResult object with parsed test results
        """
        self.logger.info(f"Running {phase} phase for {instance.pr.org}/{instance.pr.repo}#{instance.pr.number}")
        
        # Determine the command to run based on phase
        if phase == "run":
            command = instance.run()
        elif phase == "test_patch":
            command = instance.test_patch_run()
        elif phase == "fix_patch":
            command = instance.fix_patch_run()
        else:
            raise ValueError(f"Unknown phase: {phase}")
        
        # Create log file for this phase
        log_file = self.temp_dir / f"{instance.pr.org}_{instance.pr.repo}_{instance.pr.number}_{phase}.log"
        
        # Use extended timeout for Sentinel repository
        timeout = self.timeout
        if instance.pr.org == "alibaba" and instance.pr.repo == "Sentinel":
            # Use a longer timeout for Sentinel repository (30 minutes)
            extended_timeout = 1800  # 30 minutes
            if extended_timeout > timeout:
                self.logger.info(f"Using extended timeout of {extended_timeout}s for Sentinel repository")
                timeout = extended_timeout
        try:
            # Run the command in Docker container
            output = docker_util.run(
                image_full_name=image_name,
                run_command=command,
                output_path=log_file,
                timeout=timeout
            )
            
            # Parse the log output using instance's parser
            test_result = instance.parse_log(output)
            
            self.logger.info(f"✅ {phase} phase completed: {test_result.passed_count} passed, "
                           f"{test_result.failed_count} failed, {test_result.skipped_count} skipped")
            
            return test_result
            
        except TimeoutError as e:
            self.logger.error(f"⏰ {phase} phase timed out after {self.timeout}s: {str(e)}")
            # Return empty test result on timeout
            return TestResult(
                passed_count=0,
                failed_count=0,
                skipped_count=0,
                passed_tests=set(),
                failed_tests=set(),
                skipped_tests=set()
            )
        except Exception as e:
            self.logger.error(f"❌ {phase} phase failed: {str(e)}")
            # Return empty test result on failure
            return TestResult(
                passed_count=0,
                failed_count=0,
                skipped_count=0,
                passed_tests=set(),
                failed_tests=set(),
                skipped_tests=set()
            )
    
    def categorize_test_transitions(self, run_result: TestResult, test_patch_result: TestResult, 
                                  fix_patch_result: TestResult) -> Dict[str, Dict[str, Test]]:
        """
        Categorize test transitions based on results from different phases.
        
        Returns:
            Dictionary with categorized tests: f2p_tests, p2p_tests, s2p_tests, n2p_tests, fixed_tests
        """
        # Get all test names from all phases
        all_tests = set()
        all_tests.update(run_result.passed_tests)
        all_tests.update(run_result.failed_tests)
        all_tests.update(run_result.skipped_tests)
        all_tests.update(test_patch_result.passed_tests)
        all_tests.update(test_patch_result.failed_tests)
        all_tests.update(test_patch_result.skipped_tests)
        all_tests.update(fix_patch_result.passed_tests)
        all_tests.update(fix_patch_result.failed_tests)
        all_tests.update(fix_patch_result.skipped_tests)
        
        # Initialize categories
        f2p_tests = {}  # fail to pass
        p2p_tests = {}  # pass to pass
        s2p_tests = {}  # skip to pass
        n2p_tests = {}  # none to pass (new tests)
        fixed_tests = {}  # tests that were fixed
        
        for test_name in all_tests:
            # Determine status in each phase
            run_status = self._get_test_status(test_name, run_result)
            test_status = self._get_test_status(test_name, test_patch_result)
            fix_status = self._get_test_status(test_name, fix_patch_result)
            
            test_obj = Test(run=run_status, test=test_status, fix=fix_status)
            
            # Categorize based on transitions from test_patch to fix_patch
            if fix_status == TestStatus.PASS:
                if test_status == TestStatus.FAIL:
                    f2p_tests[test_name] = test_obj
                elif test_status == TestStatus.PASS:
                    p2p_tests[test_name] = test_obj
                elif test_status == TestStatus.SKIP:
                    s2p_tests[test_name] = test_obj
                elif test_status == TestStatus.NONE:
                    n2p_tests[test_name] = test_obj
            
            # A test is "fixed" if it failed in test_patch but passes in fix_patch
            if test_status == TestStatus.FAIL and fix_status == TestStatus.PASS:
                fixed_tests[test_name] = test_obj
        
        return {
            "f2p_tests": f2p_tests,
            "p2p_tests": p2p_tests,
            "s2p_tests": s2p_tests,
            "n2p_tests": n2p_tests,
            "fixed_tests": fixed_tests
        }
    
    def _get_test_status(self, test_name: str, test_result: TestResult) -> TestStatus:
        """Get the status of a specific test from test results."""
        if test_name in test_result.passed_tests:
            return TestStatus.PASS
        elif test_name in test_result.failed_tests:
            return TestStatus.FAIL
        elif test_name in test_result.skipped_tests:
            return TestStatus.SKIP
        else:
            return TestStatus.NONE
    
    def process_instance(self, instance_data: dict) -> dict:
        """
        Process a single instance: run tests and generate results.
        
        Args:
            instance_data: Dictionary containing instance data
            
        Returns:
            Dictionary with test results and categorizations
        """
        org = instance_data['org']
        repo = instance_data['repo']
        number = instance_data['number']
        
        self.logger.info(f"🔍 Processing {org}/{repo}#{number}")
        
        # Create instance object
        pr = PullRequest.from_dict(instance_data)
        config = Config(need_clone=False, global_env=None, clear_env=False)
        instance = Instance.create(pr, config)
        
        # Get image name
        image_name = self.get_image_name(instance_data)
        
        # Check if image exists
        if not self.check_image_exists(image_name):
            self.logger.error(f"❌ Docker image not found: {image_name}")
            return self._create_error_result(instance_data, f"Docker image not found: {image_name}")
        
        self.logger.info(f"✅ Found Docker image: {image_name}")
        
        try:
            # Run all three test phases
            run_result = self.run_test_phase(instance, image_name, "run")
            test_patch_result = self.run_test_phase(instance, image_name, "test_patch")
            fix_patch_result = self.run_test_phase(instance, image_name, "fix_patch")
            
            # Categorize test transitions
            categories = self.categorize_test_transitions(run_result, test_patch_result, fix_patch_result)
            
            # Create result dictionary
            result = dict(instance_data)  # Start with original data
            result.update({
                "run_result": {
                    "passed_count": run_result.passed_count,
                    "failed_count": run_result.failed_count,
                    "skipped_count": run_result.skipped_count,
                    "passed_tests": list(run_result.passed_tests),
                    "failed_tests": list(run_result.failed_tests),
                    "skipped_tests": list(run_result.skipped_tests)
                },
                "test_patch_result": {
                    "passed_count": test_patch_result.passed_count,
                    "failed_count": test_patch_result.failed_count,
                    "skipped_count": test_patch_result.skipped_count,
                    "passed_tests": list(test_patch_result.passed_tests),
                    "failed_tests": list(test_patch_result.failed_tests),
                    "skipped_tests": list(test_patch_result.skipped_tests)
                },
                "fix_patch_result": {
                    "passed_count": fix_patch_result.passed_count,
                    "failed_count": fix_patch_result.failed_count,
                    "skipped_count": fix_patch_result.skipped_count,
                    "passed_tests": list(fix_patch_result.passed_tests),
                    "failed_tests": list(fix_patch_result.failed_tests),
                    "skipped_tests": list(fix_patch_result.skipped_tests)
                },
                "f2p_tests": {k: asdict(v) for k, v in categories["f2p_tests"].items()},
                "p2p_tests": {k: asdict(v) for k, v in categories["p2p_tests"].items()},
                "s2p_tests": {k: asdict(v) for k, v in categories["s2p_tests"].items()},
                "n2p_tests": {k: asdict(v) for k, v in categories["n2p_tests"].items()},
                "fixed_tests": {k: asdict(v) for k, v in categories["fixed_tests"].items()}
            })
            
            self.logger.info(f"✅ {org}/{repo}#{number}: "
                           f"Fixed {len(categories['fixed_tests'])} tests, "
                           f"F2P: {len(categories['f2p_tests'])}, "
                           f"P2P: {len(categories['p2p_tests'])}, "
                           f"S2P: {len(categories['s2p_tests'])}, "
                           f"N2P: {len(categories['n2p_tests'])}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Error processing {org}/{repo}#{number}: {str(e)}")
            return self._create_error_result(instance_data, str(e))
    
    def _create_error_result(self, instance_data: dict, error_msg: str) -> dict:
        """Create an error result for a failed instance."""
        result = dict(instance_data)
        result.update({
            "error": error_msg,
            "run_result": {
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "passed_tests": [],
                "failed_tests": [],
                "skipped_tests": []
            },
            "test_patch_result": {
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "passed_tests": [],
                "failed_tests": [],
                "skipped_tests": []
            },
            "fix_patch_result": {
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "passed_tests": [],
                "failed_tests": [],
                "skipped_tests": []
            },
            "f2p_tests": {},
            "p2p_tests": {},
            "s2p_tests": {},
            "n2p_tests": {},
            "fixed_tests": {}
        })
        return result
    
    def process_instances(self, instances: List[dict], output_file: Path, processed_ids: Set[str]) -> List[dict]:
        """
        Process multiple instances in parallel with progressive output.
        
        Args:
            instances: List of instance dictionaries
            output_file: Path to output file for progressive saving
            processed_ids: Set of already processed instance IDs to skip
            
        Returns:
            List of processed results
        """
        results = []
        
        # Filter out already processed instances
        remaining_instances = [
            instance for instance in instances 
            if instance.get('instance_id') not in processed_ids
        ]
        
        if len(remaining_instances) < len(instances):
            skipped = len(instances) - len(remaining_instances)
            self.logger.info(f"⏭️  Skipping {skipped} already processed instances")
        
        if not remaining_instances:
            self.logger.info("✅ All instances already processed!")
            return results
        
        self.logger.info(f"🔄 Processing {len(remaining_instances)} remaining instances...")
        
        if self.max_workers == 1:
            # Sequential processing with progressive output
            for i, instance in enumerate(remaining_instances, 1):
                self.logger.info(f"📝 Processing {i}/{len(remaining_instances)}: {instance.get('instance_id', 'unknown')}")
                result = self.process_instance(instance)
                results.append(result)
                # Save immediately after processing each instance
                append_result(result, output_file)
                self.logger.info(f"💾 Saved result for {instance.get('instance_id', 'unknown')}")
        else:
            # Parallel processing with progressive output
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_instance = {
                    executor.submit(self.process_instance, instance): instance 
                    for instance in remaining_instances
                }
                
                completed = 0
                total = len(remaining_instances)
                
                for future in as_completed(future_to_instance):
                    instance = future_to_instance[future]
                    completed += 1
                    
                    try:
                        result = future.result()
                        results.append(result)
                        # Save immediately after processing each instance
                        append_result(result, output_file)
                        self.logger.info(f"💾 Saved result for {instance.get('instance_id', 'unknown')} ({completed}/{total})")
                    except Exception as e:
                        self.logger.error(f"❌ Exception processing instance: {e}")
                        error_result = self._create_error_result(instance, str(e))
                        results.append(error_result)
                        # Save error result too
                        append_result(error_result, output_file)
                        self.logger.info(f"💾 Saved error result for {instance.get('instance_id', 'unknown')} ({completed}/{total})")
        
        return results

    def process_instances_batch(self, instances: List[dict]) -> List[dict]:
        """
        Process multiple instances in parallel (old behavior - no progressive output).
        
        Args:
            instances: List of instance dictionaries
            
        Returns:
            List of processed results
        """
        results = []
        
        if self.max_workers == 1:
            # Sequential processing
            for instance in instances:
                result = self.process_instance(instance)
                results.append(result)
        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_instance = {
                    executor.submit(self.process_instance, instance): instance 
                    for instance in instances
                }
                
                for future in as_completed(future_to_instance):
                    instance = future_to_instance[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        self.logger.error(f"❌ Exception processing instance: {e}")
                        error_result = self._create_error_result(instance, str(e))
                        results.append(error_result)
        
        return results


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def load_instances(input_file: Path) -> List[dict]:
    """Load instances from JSONL file."""
    instances = []
    line_num = 0
    with open(input_file, 'r') as f:
        for line in f:
            line_num += 1
            line = line.strip()
            if line:
                try:
                    instances.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logging.getLogger(__name__).error(f"JSON decode error on line {line_num}: {e}")
                    logging.getLogger(__name__).error(f"Line content (first 100 chars): {repr(line[:100])}")
                    raise
    return instances


def json_serializer(obj):
    """Custom JSON serializer for non-serializable objects."""
    if hasattr(obj, 'value'):  # Enum objects
        return obj.value
    elif isinstance(obj, set):  # Set objects
        return list(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def load_existing_results(output_file: Path) -> Set[str]:
    """Load existing results and return set of processed instance IDs."""
    processed_ids = set()
    if output_file.exists():
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        result = json.loads(line)
                        if 'instance_id' in result:
                            processed_ids.add(result['instance_id'])
        except (json.JSONDecodeError, IOError) as e:
            logging.getLogger(__name__).warning(f"⚠️  Could not load existing results: {e}")
    return processed_ids


def load_and_filter_existing_results(output_file: Path, current_instance_ids: Set[str]) -> List[dict]:
    """
    Load existing results and filter out instances that are being reprocessed.
    
    Args:
        output_file: Path to existing results file
        current_instance_ids: Set of instance IDs being processed in current run
        
    Returns:
        List of existing results that should be preserved
    """
    preserved_results = []
    if output_file.exists():
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        result = json.loads(line)
                        instance_id = result.get('instance_id')
                        # Only preserve results for instances not being reprocessed
                        if instance_id and instance_id not in current_instance_ids:
                            preserved_results.append(result)
        except (json.JSONDecodeError, IOError) as e:
            logging.getLogger(__name__).warning(f"⚠️  Could not load existing results: {e}")
    return preserved_results


def append_result(result: dict, output_file: Path):
    """Append a single result to the output file."""
    with open(output_file, 'a') as f:
        f.write(json.dumps(result, default=json_serializer) + '\n')


def save_results(results: List[dict], output_file: Path):
    """Save results to JSONL file."""
    with open(output_file, 'w') as f:
        for result in results:
            f.write(json.dumps(result, default=json_serializer) + '\n')


def main():
    parser = argparse.ArgumentParser(
        description="Test and evaluate Multi-SWE-bench instances",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with progressive output (default)
  python test_and_evaluate.py --input instances.jsonl --output results.jsonl
  
  # With custom registry and parallel processing
  python test_and_evaluate.py --input instances.jsonl --output results.jsonl \\
    --registry mswebench --max-workers 4
  
  # Resume processing (skips already completed instances)
  python test_and_evaluate.py --input instances.jsonl --output results.jsonl
  
  # Disable progressive output (old batch behavior)
  python test_and_evaluate.py --input instances.jsonl --output results.jsonl \\
    --no-progressive
  
  # Sequential processing with debug logging
  python test_and_evaluate.py --input instances.jsonl --output results.jsonl \\
    --max-workers 1 --log-level DEBUG
  
  # Process only first 5 instances
  python test_and_evaluate.py --input instances.jsonl --output results.jsonl \\
    --limit 5
  
  # Force reprocessing of instances in input file (preserves other results)
  python test_and_evaluate.py --input new_instances.jsonl --output results.jsonl \\
    --force

Features:
  - Progressive output: Results are saved as each instance completes
  - Resume capability: Automatically skips already processed instances
  - Parallel processing: Configurable number of worker threads
  - Error handling: Graceful handling of failed instances
  - Limit processing: Process only first N instances with --limit
  - Selective force reprocessing: Only reprocess instances in current input file
        """
    )
    
    parser.add_argument(
        "input",
        type=Path,
        help="Input JSONL file containing instances"
    )
    
    parser.add_argument(
        "--output", "-o", 
        type=Path,
        default="test_results.jsonl",
        help="Output JSONL file for results"
    )
    
    parser.add_argument(
        "--registry",
        type=str,
        default="",
        help="Docker registry prefix (e.g., 'mswebench')"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of parallel workers (default: 4, use 1 for sequential)"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout for each test phase in seconds (default: 1800)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--no-progressive",
        action="store_true",
        help="Disable progressive output (save all results at end instead of as they complete)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N instances from the input file"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing of instances in current input file, preserving results for other instances"
    )
    
    parser.add_argument(
        "--path-to-dataset",
        type=Path,
        help="Path to dataset (optional)"
    )

    parser.add_argument(
        "--path-to-dataset-with-tests",
        type=Path,
        help="Path to dataset with tests (optional)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    # Validate input file
    if not args.input.exists():
        # Try to find the file in the parent directory
        parent_path = Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), args.input))
        if parent_path.exists():
            logger.info(f"Found input file at: {parent_path}")
            args.input = parent_path
        else:
            logger.error(f"Input file not found: {args.input}")
            logger.error(f"Also checked: {parent_path}")
            return 1
    
    # Create output directory if needed
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"🚀 Starting test and evaluation process")
    logger.info(f"📁 Input: {args.input}")
    logger.info(f"📁 Output: {args.output}")
    
    if args.path_to_dataset:
        logger.info(f"📁 Dataset: {args.path_to_dataset}")
        # Validate dataset file
        if not args.path_to_dataset.exists():
            # Try to find the file in the parent directory
            parent_path = Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), args.path_to_dataset))
            if parent_path.exists():
                logger.info(f"Found dataset at: {parent_path}")
                args.path_to_dataset = parent_path
            else:
                logger.error(f"Dataset file not found: {args.path_to_dataset}")
                logger.error(f"Also checked: {parent_path}")
                return 1
    
    if args.path_to_dataset_with_tests:
        logger.info(f"📁 Dataset with tests: {args.path_to_dataset_with_tests}")
        # Validate dataset with tests file
        if not args.path_to_dataset_with_tests.exists():
            # Try to find the file in the parent directory
            parent_path = Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), args.path_to_dataset_with_tests))
            if parent_path.exists():
                logger.info(f"Found dataset with tests at: {parent_path}")
                args.path_to_dataset_with_tests = parent_path
            else:
                logger.error(f"Dataset with tests file not found: {args.path_to_dataset_with_tests}")
                logger.error(f"Also checked: {parent_path}")
                return 1
    logger.info(f"🐳 Registry: {args.registry or 'default'}")
    logger.info(f"👥 Workers: {args.max_workers}")
    logger.info(f"⏱️  Timeout: {args.timeout}s")
    
    start_time = time.time()
    
    try:
        # Load instances
        logger.info("📖 Loading instances...")
        instances = load_instances(args.input)
        logger.info(f"✅ Loaded {len(instances)} instances")
        
        # Load dataset with tests if provided
        if args.path_to_dataset_with_tests:
            logger.info("📖 Loading dataset with tests...")
            test_instances = load_instances(args.path_to_dataset_with_tests)
            logger.info(f"✅ Loaded {len(test_instances)} test instances")
            
            # Merge test data into instances
            for instance in instances:
                instance_id = instance.get('instance_id')
                for test_instance in test_instances:
                    if test_instance.get('instance_id') == instance_id:
                        # Merge test data
                        if 'test_patch' in test_instance:
                            instance['test_patch'] = test_instance['test_patch']
                        logger.info(f"✅ Added test data for instance {instance_id}")
        
        # Apply limit if specified
        if args.limit:
            instances = instances[:args.limit]
            logger.info(f"🔢 Limiting to first {args.limit} instances")
        
        # Clean up any orphaned containers from previous runs
        logger.info("🧹 Cleaning up orphaned containers from previous runs...")
        try:
            cleaned_count = docker_util.cleanup_orphaned_containers(max_age_hours=1)
            if cleaned_count > 0:
                logger.info(f"✅ Cleaned up {cleaned_count} orphaned containers")
        except Exception as e:
            logger.warning(f"⚠️  Failed to clean up orphaned containers: {e}")
        
        # Create evaluator
        evaluator = TestEvaluator(
            max_workers=args.max_workers,
            timeout=args.timeout,
            registry=args.registry
        )
        
        try:
            if args.no_progressive:
                # Use old behavior: process all, then save all
                logger.info("🔄 Processing instances (batch mode)...")
                results = evaluator.process_instances_batch(instances)
                
                # Save results
                logger.info("💾 Saving results...")
                save_results(results, args.output)
                processed_ids = set()  # No previously processed instances in batch mode
            else:
                # Load existing results to skip already processed instances (unless force is enabled)
                if args.force:
                    logger.info("🔄 Force mode enabled - will reprocess instances in current input")
                    
                    # Get instance IDs from current input
                    current_instance_ids = set()
                    for instance in instances:
                        if 'instance_id' in instance:
                            current_instance_ids.add(instance['instance_id'])
                    
                    # Load existing results and preserve those not being reprocessed
                    preserved_results = load_and_filter_existing_results(args.output, current_instance_ids)
                    
                    if preserved_results:
                        logger.info(f"📋 Preserving {len(preserved_results)} existing results not in current input")
                        # Rewrite output file with only preserved results
                        save_results(preserved_results, args.output)
                    else:
                        # No results to preserve, clear the file
                        if args.output.exists():
                            logger.info(f"🗑️  Clearing existing output file: {args.output}")
                            args.output.unlink()
                    
                    # Don't skip any instances from current input (force reprocessing)
                    processed_ids = set()
                else:
                    logger.info("🔍 Checking for existing results...")
                    processed_ids = load_existing_results(args.output)
                    if processed_ids:
                        logger.info(f"📋 Found {len(processed_ids)} already processed instances")
                
                # Process instances with progressive output
                results = evaluator.process_instances(instances, args.output, processed_ids)
            
            # Print summary
            total_time = time.time() - start_time
            successful = len([r for r in results if "error" not in r])
            failed = len(results) - successful
            
            # Count total results (including previously processed ones)
            total_processed = len(processed_ids) + len(results)
            total_successful = successful
            total_failed = failed
            
            # If we have existing results, we need to count them too
            if processed_ids:
                # Count successful/failed from existing results
                if args.output.exists():
                    with open(args.output, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                result = json.loads(line)
                                if result.get('instance_id') in processed_ids:
                                    if "error" not in result:
                                        total_successful += 1
                                    else:
                                        total_failed += 1
            
            logger.info("=" * 80)
            logger.info("📊 EVALUATION SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total instances: {len(instances)}")
            logger.info(f"Previously processed: {len(processed_ids)}")
            logger.info(f"Newly processed: {len(results)}")
            logger.info(f"Total successful: {total_successful}")
            logger.info(f"Total failed: {total_failed}")
            logger.info(f"Total time: {total_time:.2f}s")
            if len(results) > 0:
                logger.info(f"Average time per new instance: {total_time/len(results):.2f}s")
            logger.info(f"Results saved to: {args.output}")
            
            if total_failed > 0:
                logger.warning(f"⚠️  {total_failed} instances failed processing")
                return 1
            else:
                logger.info("🎉 All instances processed successfully!")
                return 0
                
        finally:
            evaluator.cleanup()
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
