#!/usr/bin/env python3

import subprocess
import sys
import json

def run_docker_command(image_name, command):
    """Run a command in a Docker container and return the output."""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", image_name, "bash", "-c", command],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running Docker command: {e}")
        print(f"STDERR: {e.stderr}")
        return None

def main():
    # Use the mswebench image for PR #1042
    image_name = "mswebench/alibaba_m_sentinel:pr-1042"
    
    # Verify the Docker image exists
    print(f"Verifying Docker image: {image_name}")
    try:
        result = subprocess.run(
            ["docker", "images", image_name, "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True,
            text=True,
            check=True
        )
        if not result.stdout.strip():
            print(f"Error: Docker image {image_name} not found")
            return 1
        print(f"Docker image found: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"Error checking Docker image: {e}")
        return 1
    
    # Run a simple command to verify the container works
    print("\nRunning a simple command in the container...")
    output = run_docker_command(image_name, "ls -la /home/Sentinel")
    if output:
        print("Container works! Output of ls -la /home/Sentinel:")
        print(output)
    else:
        print("Failed to run command in container")
        return 1
    
    # Verify the run.sh script exists
    print("\nVerifying run.sh script exists...")
    output = run_docker_command(image_name, "cat /home/run.sh")
    if output:
        print("run.sh script exists:")
        print(output)
    else:
        print("Failed to find run.sh script")
        return 1
    
    # Verify the test-run.sh script exists
    print("\nVerifying test-run.sh script exists...")
    output = run_docker_command(image_name, "cat /home/test-run.sh")
    if output:
        print("test-run.sh script exists:")
        print(output)
    else:
        print("Failed to find test-run.sh script")
        return 1
    
    # Verify the fix-run.sh script exists
    print("\nVerifying fix-run.sh script exists...")
    output = run_docker_command(image_name, "cat /home/fix-run.sh")
    if output:
        print("fix-run.sh script exists:")
        print(output)
    else:
        print("Failed to find fix-run.sh script")
        return 1
    
    print("\nAll verification steps passed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())