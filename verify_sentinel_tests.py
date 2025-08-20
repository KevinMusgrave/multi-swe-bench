#!/usr/bin/env python3

import subprocess
import sys
import json
import re
from multi_swe_bench.harness.repos.java.alibaba.sentinel import Sentinel
from multi_swe_bench.harness.pull_request import PullRequest
from multi_swe_bench.harness.image import Config

def run_docker_command(image_name, command, timeout=300):
    """Run a command in a Docker container and return the output."""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", image_name, "bash", "-c", command],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running Docker command: {e}")
        print(f"STDERR: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds")
        return None

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
    
    # Use the mswebench image for PR #1042
    image_name = "mswebench/alibaba_m_sentinel:pr-1042"
    
    # Run the test command to see what tests are discovered
    print(f"Running test discovery in Docker container: {image_name}")
    
    # First, run a simple test to see if Maven works
    print("\nVerifying Maven works...")
    output = run_docker_command(image_name, "cd /home/Sentinel && mvn -version")
    if output:
        print("Maven works! Version info:")
        print(output)
    else:
        print("Failed to run Maven")
        return 1
    
    # Run a test list command to see what tests are available
    print("\nListing available tests...")
    output = run_docker_command(
        image_name, 
        "cd /home/Sentinel && find . -name '*Test.java' | grep -v 'target' | sort",
        timeout=60
    )
    if output:
        print("Available tests:")
        test_files = output.strip().split('\n')
        for test_file in test_files[:10]:  # Show first 10 tests
            print(f"  {test_file}")
        if len(test_files) > 10:
            print(f"  ... and {len(test_files) - 10} more")
    else:
        print("Failed to list tests")
        return 1
    
    # Skip running tests as they take too long
    print("\nSkipping test execution as it takes too long...")
    print("Instead, we'll test the parse_log method directly with sample test output.")
    
    # Test the parse_log method of the Sentinel instance
    print("\nTesting parse_log method...")
    test_log = """
    [INFO] -------------------------------------------------------
    [INFO]  T E S T S
    [INFO] -------------------------------------------------------
    [INFO] Running com.alibaba.csp.sentinel.dashboard.controller.gateway.GatewayApiControllerTest
    [INFO] Tests run: 5, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 1.234 s - in com.alibaba.csp.sentinel.dashboard.controller.gateway.GatewayApiControllerTest
    [INFO] Running com.alibaba.csp.sentinel.dashboard.controller.gateway.GatewayFlowRuleControllerTest
    [INFO] Tests run: 3, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.987 s - in com.alibaba.csp.sentinel.dashboard.controller.gateway.GatewayFlowRuleControllerTest
    [INFO] 
    [INFO] Results:
    [INFO] 
    [INFO] Tests run: 8, Failures: 1, Errors: 0, Skipped: 0
    """
    
    test_result = instance.parse_log(test_log)
    print("Parsed test results:")
    print(f"Passed tests: {test_result.passed_tests}")
    print(f"Failed tests: {test_result.failed_tests}")
    print(f"Skipped tests: {test_result.skipped_tests}")
    print(f"Passed count: {test_result.passed_count}")
    print(f"Failed count: {test_result.failed_count}")
    print(f"Skipped count: {test_result.skipped_count}")
    
    print("\nAll verification steps completed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())