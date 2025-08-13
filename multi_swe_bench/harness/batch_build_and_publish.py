#!/usr/bin/env python3
"""
Batch Build and Publish Docker Images for Multi-SWE-bench

This script takes a JSONL file with new harnessed instances and:
1. Builds Docker images for each instance
2. Publishes them to a specified registry
3. Updates image list files
4. Provides comprehensive logging and error handling

Usage:
    python batch_build_and_publish.py \
        --input instances.jsonl \
        --registry myregistry.com/mswebench \
        --max-workers 4 \
        --push \
        --update-lists
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'batch_build_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class Instance:
    """Represents a Multi-SWE-bench instance"""
    org: str
    repo: str
    number: int
    data: Dict
    
    @property
    def image_name(self) -> str:
        return f"{self.org}_m_{self.repo}".lower()
    
    @property
    def image_tag(self) -> str:
        return f"pr-{self.number}"
    
    @property
    def instance_id(self) -> str:
        return f"{self.org}__{self.repo}-{self.number}"

class DockerImageBuilder:
    """Handles building and publishing Docker images"""
    
    def __init__(self, registry: str, workdir: Path, max_workers: int = 4):
        self.registry = registry.rstrip('/')
        self.workdir = workdir
        self.max_workers = max_workers
        self.repo_root = Path("/home/juan-all-hands/dev/multi-swe-bench-fork")
        
        # Create required directories
        self.build_workdir = workdir / "build"
        self.log_dir = workdir / "logs"
        self.repo_dir = workdir / "repos"
        
        for dir_path in [self.build_workdir, self.log_dir, self.repo_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def load_instances(self, jsonl_file: Path) -> List[Instance]:
        """Load instances from JSONL file"""
        instances = []
        
        logger.info(f"Loading instances from {jsonl_file}")
        
        try:
            with open(jsonl_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # Validate required fields
                        required_fields = ['org', 'repo', 'number']
                        missing_fields = [field for field in required_fields if field not in data]
                        
                        if missing_fields:
                            logger.warning(f"Line {line_num}: Missing required fields: {missing_fields}")
                            continue
                        
                        instance = Instance(
                            org=data['org'],
                            repo=data['repo'],
                            number=data['number'],
                            data=data
                        )
                        instances.append(instance)
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Line {line_num}: Invalid JSON - {e}")
                        continue
                        
        except FileNotFoundError:
            logger.error(f"Input file not found: {jsonl_file}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error loading instances: {e}")
            sys.exit(1)
        
        logger.info(f"Loaded {len(instances)} instances")
        return instances
    
    def get_full_image_name(self, instance: Instance) -> str:
        """Get the full image name including registry"""
        return f"{self.registry}/{instance.image_name}:{instance.image_tag}"
    
    def check_image_exists_locally(self, image_name: str) -> bool:
        """Check if image exists locally"""
        try:
            result = subprocess.run(
                ['docker', 'images', '-q', image_name],
                capture_output=True,
                text=True,
                check=True
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
    
    def check_image_exists_remotely(self, image_name: str) -> bool:
        """Check if image exists in remote registry"""
        try:
            result = subprocess.run(
                ['docker', 'manifest', 'inspect', image_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    
    def build_single_image(self, instance: Instance, force_build: bool = False, skip_commit_hash_check: bool = False) -> Tuple[bool, str]:
        """Build a single Docker image"""
        full_image_name = self.get_full_image_name(instance)
        
        logger.info(f"🔨 Building image for {instance.instance_id}")
        
        # Check if image already exists
        if not force_build and self.check_image_exists_locally(full_image_name):
            logger.info(f"⏭️  Image {full_image_name} already exists locally, skipping build")
            return True, f"Image already exists: {full_image_name}"
        
        # Create temporary dataset file for this instance
        temp_dataset = self.workdir / f"temp_{instance.instance_id}.jsonl"
        
        try:
            with open(temp_dataset, 'w') as f:
                f.write(json.dumps(instance.data) + '\n')
            
            # Build command
            cmd = [
                '/home/juan-all-hands/micromamba/bin/python', '-m', 'multi_swe_bench.harness.build_dataset',
                '--raw_dataset_files', str(temp_dataset),
                '--mode', 'image',
                '--workdir', str(self.build_workdir),
                '--log_dir', str(self.log_dir),
                '--repo_dir', str(self.repo_dir),
                '--max_workers_build_image', '1',
                '--log_level', 'INFO'
            ]
            
            if skip_commit_hash_check:
                cmd.append('--skip_commit_hash_check')
            
            logger.debug(f"Build command: {' '.join(cmd)}")
            
            # Set up environment with PYTHONPATH
            env = os.environ.copy()
            env['PYTHONPATH'] = str(self.repo_root)
            
            # Run build
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout
                env=env
            )
            
            if result.returncode == 0:
                logger.debug(f"Build command stdout: {result.stdout}")
                logger.debug(f"Build command stderr: {result.stderr}")
                
                # Tag the image with our registry name
                local_image = f"mswebench/{instance.image_name}:{instance.image_tag}"
                
                # Check if the image actually exists
                if not self.check_image_exists_locally(local_image):
                    error_msg = f"Build reported success but image {local_image} does not exist locally"
                    logger.error(f"❌ {instance.instance_id}: {error_msg}")
                    logger.debug(f"Build stdout: {result.stdout}")
                    logger.debug(f"Build stderr: {result.stderr}")
                    return False, error_msg
                
                if local_image != full_image_name:
                    tag_result = subprocess.run(
                        ['docker', 'tag', local_image, full_image_name],
                        capture_output=True,
                        text=True
                    )
                    
                    if tag_result.returncode != 0:
                        error_msg = f"Failed to tag image: {tag_result.stderr}"
                        logger.error(f"❌ {instance.instance_id}: {error_msg}")
                        return False, error_msg
                
                logger.info(f"✅ {instance.instance_id}: Build successful")
                return True, f"Build successful: {full_image_name}"
            else:
                error_msg = f"Build failed: {result.stderr}"
                logger.error(f"❌ {instance.instance_id}: {error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "Build timed out after 30 minutes"
            logger.error(f"❌ {instance.instance_id}: {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Build error: {str(e)}"
            logger.error(f"❌ {instance.instance_id}: {error_msg}")
            return False, error_msg
        finally:
            # Clean up temp file
            if temp_dataset.exists():
                temp_dataset.unlink()
    
    async def push_single_image(self, instance: Instance, max_retries: int = 3) -> Tuple[bool, str]:
        """Push a single Docker image with retry logic"""
        full_image_name = self.get_full_image_name(instance)
        
        logger.info(f"🚀 Pushing image for {instance.instance_id}")
        
        # Check if image exists remotely
        if self.check_image_exists_remotely(full_image_name):
            logger.info(f"⏭️  Image {full_image_name} already exists remotely, skipping push")
            return True, f"Image already exists remotely: {full_image_name}"
        
        push_cmd = f"docker push {full_image_name}"
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 {instance.instance_id}: Push attempt {attempt + 1}/{max_retries}")
                
                result = subprocess.run(
                    push_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout
                )
                
                if result.returncode == 0:
                    logger.info(f"✅ {instance.instance_id}: Push successful")
                    return True, f"Push successful: {full_image_name}"
                else:
                    logger.warning(f"⚠️  {instance.instance_id}: Push attempt {attempt + 1} failed: {result.stderr}")
                    if attempt < max_retries - 1:
                        logger.info(f"🔄 {instance.instance_id}: Retrying in 30 seconds...")
                        await asyncio.sleep(30)
                    else:
                        error_msg = f"All {max_retries} push attempts failed: {result.stderr}"
                        logger.error(f"❌ {instance.instance_id}: {error_msg}")
                        return False, error_msg
                        
            except subprocess.TimeoutExpired:
                logger.warning(f"⏰ {instance.instance_id}: Push attempt {attempt + 1} timed out")
                if attempt < max_retries - 1:
                    logger.info(f"🔄 {instance.instance_id}: Retrying in 30 seconds...")
                    await asyncio.sleep(30)
                else:
                    error_msg = f"All push attempts timed out"
                    logger.error(f"❌ {instance.instance_id}: {error_msg}")
                    return False, error_msg
            except Exception as e:
                logger.warning(f"⚠️  {instance.instance_id}: Push attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"🔄 {instance.instance_id}: Retrying in 30 seconds...")
                    await asyncio.sleep(30)
                else:
                    error_msg = f"All push attempts failed: {str(e)}"
                    logger.error(f"❌ {instance.instance_id}: {error_msg}")
                    return False, error_msg
        
        return False, "Unknown push error"
    
    def build_images(self, instances: List[Instance], force_build: bool = False, skip_commit_hash_check: bool = False) -> Dict[str, Tuple[bool, str]]:
        """Build all images using thread pool"""
        logger.info(f"🔨 Building {len(instances)} images with {self.max_workers} workers")
        
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all build tasks
            future_to_instance = {
                executor.submit(self.build_single_image, instance, force_build, skip_commit_hash_check): instance
                for instance in instances
            }
            
            # Process completed builds
            for future in as_completed(future_to_instance):
                instance = future_to_instance[future]
                try:
                    success, message = future.result()
                    results[instance.instance_id] = (success, message)
                except Exception as e:
                    error_msg = f"Build exception: {str(e)}"
                    logger.error(f"❌ {instance.instance_id}: {error_msg}")
                    results[instance.instance_id] = (False, error_msg)
        
        # Summary
        successful_builds = sum(1 for success, _ in results.values() if success)
        logger.info(f"🔨 Build Summary: {successful_builds}/{len(instances)} successful")
        
        return results
    
    async def push_images(self, instances: List[Instance]) -> Dict[str, Tuple[bool, str]]:
        """Push all images asynchronously"""
        logger.info(f"🚀 Pushing {len(instances)} images")
        
        # Create semaphore to limit concurrent pushes
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def push_with_semaphore(instance):
            async with semaphore:
                return await self.push_single_image(instance)
        
        # Create tasks for all pushes
        tasks = [push_with_semaphore(instance) for instance in instances]
        
        # Wait for all pushes to complete
        results = {}
        for i, task in enumerate(asyncio.as_completed(tasks)):
            instance = instances[i]
            try:
                success, message = await task
                results[instance.instance_id] = (success, message)
            except Exception as e:
                error_msg = f"Push exception: {str(e)}"
                logger.error(f"❌ {instance.instance_id}: {error_msg}")
                results[instance.instance_id] = (False, error_msg)
        
        # Summary
        successful_pushes = sum(1 for success, _ in results.values() if success)
        logger.info(f"🚀 Push Summary: {successful_pushes}/{len(instances)} successful")
        
        return results
    
    def update_image_lists(self, instances: List[Instance], list_files: List[str]) -> bool:
        """Update image list files with new images"""
        logger.info(f"📝 Updating image lists: {list_files}")
        
        try:
            for list_file in list_files:
                list_path = Path(list_file)
                
                if not list_path.exists():
                    logger.warning(f"Image list file not found: {list_path}")
                    continue
                
                # Read existing images
                with open(list_path, 'r') as f:
                    existing_images = set(f.read().splitlines())
                
                # Add new images
                new_images = set()
                for instance in instances:
                    full_image_name = self.get_full_image_name(instance)
                    if full_image_name not in existing_images:
                        new_images.add(full_image_name)
                
                if new_images:
                    # Append new images
                    all_images = existing_images | new_images
                    sorted_images = sorted(all_images)
                    
                    with open(list_path, 'w') as f:
                        f.write('\n'.join(sorted_images) + '\n')
                    
                    logger.info(f"✅ Added {len(new_images)} new images to {list_file}")
                else:
                    logger.info(f"ℹ️  No new images to add to {list_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating image lists: {e}")
            return False
    
    def generate_summary_report(self, instances: List[Instance], 
                              build_results: Dict[str, Tuple[bool, str]], 
                              push_results: Optional[Dict[str, Tuple[bool, str]]] = None) -> str:
        """Generate a summary report"""
        report_lines = [
            "=" * 80,
            "BATCH BUILD AND PUBLISH SUMMARY REPORT",
            "=" * 80,
            f"Timestamp: {datetime.now().isoformat()}",
            f"Registry: {self.registry}",
            f"Total Instances: {len(instances)}",
            "",
            "BUILD RESULTS:",
            "-" * 40
        ]
        
        successful_builds = 0
        for instance in instances:
            instance_id = instance.instance_id
            success, message = build_results.get(instance_id, (False, "No result"))
            status = "✅ SUCCESS" if success else "❌ FAILED"
            report_lines.append(f"{status} {instance_id}: {message}")
            if success:
                successful_builds += 1
        
        report_lines.extend([
            "",
            f"Build Summary: {successful_builds}/{len(instances)} successful",
            ""
        ])
        
        if push_results:
            report_lines.extend([
                "PUSH RESULTS:",
                "-" * 40
            ])
            
            successful_pushes = 0
            for instance in instances:
                instance_id = instance.instance_id
                success, message = push_results.get(instance_id, (False, "No result"))
                status = "✅ SUCCESS" if success else "❌ FAILED"
                report_lines.append(f"{status} {instance_id}: {message}")
                if success:
                    successful_pushes += 1
            
            report_lines.extend([
                "",
                f"Push Summary: {successful_pushes}/{len(instances)} successful",
                ""
            ])
        
        report_lines.extend([
            "DOCKER PULL COMMANDS:",
            "-" * 40
        ])
        
        for instance in instances:
            full_image_name = self.get_full_image_name(instance)
            report_lines.append(f"docker pull {full_image_name}")
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)

def check_prerequisites():
    """Check if all prerequisites are met"""
    logger.info("🔍 Checking prerequisites...")
    
    # Check Docker
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True, check=True)
        logger.info(f"✅ Docker: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("❌ Docker not found or not accessible")
        return False
    
    # Check Docker daemon
    try:
        subprocess.run(['docker', 'info'], capture_output=True, text=True, check=True)
        logger.info("✅ Docker daemon is running")
    except subprocess.CalledProcessError:
        logger.error("❌ Docker daemon is not running")
        return False
    
    # Check Multi-SWE-bench module
    try:
        import multi_swe_bench
        logger.info("✅ Multi-SWE-bench module available")
    except ImportError:
        logger.error("❌ Multi-SWE-bench module not found")
        return False
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Batch build and publish Docker images for Multi-SWE-bench instances",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build and push to Docker Hub
  python batch_build_and_publish.py --input instances.jsonl --registry mswebench --push

  # Build and push to custom registry
  python batch_build_and_publish.py --input instances.jsonl --registry myregistry.com/mswebench --push

  # Only build locally (no push)
  python batch_build_and_publish.py --input instances.jsonl --registry mswebench

  # Build, push, and update image lists
  python batch_build_and_publish.py --input instances.jsonl --registry mswebench --push --update-lists
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        type=Path,
        required=True,
        help='Input JSONL file with harnessed instances'
    )
    
    parser.add_argument(
        '--registry', '-r',
        type=str,
        required=True,
        help='Docker registry (e.g., "mswebench" for Docker Hub or "myregistry.com/mswebench")'
    )
    
    parser.add_argument(
        '--workdir', '-w',
        type=Path,
        default=Path('/tmp/batch_build_workdir'),
        help='Working directory for builds (default: /tmp/batch_build_workdir)'
    )
    
    parser.add_argument(
        '--max-workers',
        type=int,
        default=4,
        help='Maximum number of concurrent workers (default: 4)'
    )
    
    parser.add_argument(
        '--push',
        action='store_true',
        help='Push images to registry after building'
    )
    
    parser.add_argument(
        '--force-build',
        action='store_true',
        help='Force rebuild even if image exists locally'
    )
    
    parser.add_argument(
        '--update-lists',
        action='store_true',
        help='Update image list files with new images'
    )
    
    parser.add_argument(
        '--list-files',
        nargs='*',
        default=['scripts/images_verified.txt'],
        help='Image list files to update (default: scripts/images_verified.txt)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--skip-commit-hash-check',
        action='store_true',
        help='Skip commit hash validation during build'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check prerequisites
    if not check_prerequisites():
        logger.error("❌ Prerequisites not met")
        sys.exit(1)
    
    # Create builder
    builder = DockerImageBuilder(
        registry=args.registry,
        workdir=args.workdir,
        max_workers=args.max_workers
    )
    
    # Load instances
    instances = builder.load_instances(args.input)
    
    if not instances:
        logger.error("❌ No valid instances found")
        sys.exit(1)
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No actual builds or pushes will be performed")
        for instance in instances:
            full_image_name = builder.get_full_image_name(instance)
            logger.info(f"Would build and push: {full_image_name}")
        sys.exit(0)
    
    # Build images
    logger.info(f"🚀 Starting batch build and publish process for {len(instances)} instances")
    start_time = time.time()
    
    build_results = builder.build_images(instances, force_build=args.force_build, skip_commit_hash_check=args.skip_commit_hash_check)
    
    # Filter successful builds for pushing
    successful_instances = [
        instance for instance in instances
        if build_results.get(instance.instance_id, (False, ""))[0]
    ]
    
    push_results = None
    if args.push and successful_instances:
        push_results = asyncio.run(builder.push_images(successful_instances))
    
    # Update image lists
    if args.update_lists and successful_instances:
        if args.push:
            # Only update lists if we successfully pushed
            successful_push_instances = [
                instance for instance in successful_instances
                if push_results and push_results.get(instance.instance_id, (False, ""))[0]
            ]
            if successful_push_instances:
                builder.update_image_lists(successful_push_instances, args.list_files)
        else:
            # Update lists with built images (even if not pushed)
            builder.update_image_lists(successful_instances, args.list_files)
    
    # Generate and save report
    report = builder.generate_summary_report(instances, build_results, push_results)
    
    report_file = args.workdir / f"summary_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(report)
    logger.info(f"📄 Full report saved to: {report_file}")
    
    # Final summary
    total_time = time.time() - start_time
    logger.info(f"⏱️  Total execution time: {total_time:.2f} seconds")
    
    # Exit with appropriate code
    failed_builds = sum(1 for success, _ in build_results.values() if not success)
    failed_pushes = 0
    if push_results:
        failed_pushes = sum(1 for success, _ in push_results.values() if not success)
    
    if failed_builds > 0 or failed_pushes > 0:
        logger.warning(f"⚠️  Process completed with {failed_builds} build failures and {failed_pushes} push failures")
        sys.exit(1)
    else:
        logger.info("🎉 All operations completed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()