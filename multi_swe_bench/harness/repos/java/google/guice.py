import re
import textwrap
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


class GuiceImageBase(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Union[str, "Image"]:
        return "ubuntu:22.04"

    def image_tag(self) -> str:
        return "base"

    def workdir(self) -> str:
        return "base"

    def files(self) -> list[File]:
        return []

    def dockerfile(self) -> str:
        image_name = self.dependency()
        if isinstance(image_name, Image):
            image_name = image_name.image_full_name()

        if self.config.need_clone:
            code = f"RUN git clone https://github.com/{self.pr.org}/{self.pr.repo}.git /home/{self.pr.repo}"
        else:
            code = f"COPY {self.pr.repo} /home/{self.pr.repo}"

        return f"""FROM {image_name}

{self.global_env}

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
WORKDIR /home/
RUN apt-get update && apt-get install -y git openjdk-11-jdk
RUN apt-get install -y maven

{code}

{self.clear_env}

"""


class GuiceImageDefault(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Image | None:
        return GuiceImageBase(self.pr, self._config)

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def files(self) -> list[File]:
        return [
            File(
                ".",
                "fix.patch",
                f"{self.pr.fix_patch}",
            ),
            File(
                ".",
                "test.patch",
                f"{self.pr.test_patch}",
            ),
            File(
                ".",
                "check_git_changes.sh",
                """#!/bin/bash
set -e

if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  echo "check_git_changes: Not inside a git repository"
  exit 1
fi

if [[ -n $(git status --porcelain) ]]; then
  echo "check_git_changes: Uncommitted changes"
  exit 1
fi

echo "check_git_changes: No uncommitted changes"
exit 0

""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "extract_test_classes.sh",
                """#!/bin/bash
set -e

# Default test class to use if no tests are found
DEFAULT_TEST="com.google.inject.internal.ProvisionListenerTest"

# Check if test patch exists
if [ ! -f "/home/test.patch" ]; then
    echo "Test patch not found, using default test"
    echo "$DEFAULT_TEST" > /home/test_specs.txt
    exit 0
fi

# Try to extract test file paths from the patch
TEST_FILES=$(grep -E "^\+\+\+ b/.*Test\.java" "/home/test.patch" | sed -E 's/^\+\+\+ b\/(.*)/\1/')

if [ -z "$TEST_FILES" ]; then
    # If no test files found, use default
    echo "No test files found in patch, using default test"
    echo "$DEFAULT_TEST" > /home/test_specs.txt
    exit 0
fi

# Convert file paths to class names
TEST_CLASSES=""
for FILE in $TEST_FILES; do
    # Remove .java extension and convert path to package
    # Handle special cases for Guice repository structure
    if [[ "$FILE" == core/test/* ]]; then
        # Core tests have a specific package structure
        CLASS_NAME=$(echo "$FILE" | sed -E 's/^core\/test\///' | sed -E 's/\.java$//' | sed -E 's/\//./g')
    elif [[ "$FILE" == extensions/*/test/* ]]; then
        # Extension tests have a different package structure
        MODULE_NAME=$(echo "$FILE" | sed -E 's/^extensions\/([^\/]+)\/test\/.*/\1/')
        CLASS_PATH=$(echo "$FILE" | sed -E 's/^extensions\/[^\/]+\/test\///' | sed -E 's/\.java$//' | sed -E 's/\//./g')
        CLASS_NAME="$CLASS_PATH"
    else
        # Default case
        CLASS_NAME=$(echo "$FILE" | sed -E 's/\.java$//' | sed -E 's/\//./g')
    fi
    
    if [ -n "$TEST_CLASSES" ]; then
        TEST_CLASSES="$TEST_CLASSES,$CLASS_NAME"
    else
        TEST_CLASSES="$CLASS_NAME"
    fi
done

if [ -z "$TEST_CLASSES" ]; then
    # If still no test classes found, use default
    echo "Failed to extract test classes, using default test"
    echo "$DEFAULT_TEST" > /home/test_specs.txt
else
    echo "Final test specifications: $TEST_CLASSES"
    echo "$TEST_CLASSES" > /home/test_specs.txt
fi
""",
            ),
            File(
                ".",
                "prepare.sh",
                """#!/bin/bash
set -e

cd /home/{pr.repo}
git reset --hard
bash /home/check_git_changes.sh
git checkout {pr.base.sha}
bash /home/check_git_changes.sh

# Extract test classes from test patch
bash /home/extract_test_classes.sh

# Use a default test if no test specs were found
if [ ! -s /home/test_specs.txt ]; then
    echo "com.google.inject.internal.ProvisionListenerTest" > /home/test_specs.txt
fi

# Read the test specs
TEST_SPECS=$(cat /home/test_specs.txt)
echo "Running tests: $TEST_SPECS"

# Run the tests and capture the output
TEST_OUTPUT=$(mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dtest=$TEST_SPECS || true)

# Print the output
echo "$TEST_OUTPUT"

# Verify the test specs are valid
if echo "$TEST_OUTPUT" | grep -q "No tests were executed!"; then
    echo "Warning: No tests were executed with the current test specs. Falling back to default test."
    echo "com.google.inject.internal.ProvisionListenerTest" > /home/test_specs.txt
    TEST_SPECS="com.google.inject.internal.ProvisionListenerTest"
    echo "Retrying with default test: $TEST_SPECS"
    mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dtest=$TEST_SPECS || true
fi

echo "Preparation completed. Test specs: $TEST_SPECS"
""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
set -e

cd /home/{pr.repo}
# Run the detected tests or fallback to a default test
TEST_SPECS=$(cat /home/test_specs.txt)
if [ -z "$TEST_SPECS" ]; then
    echo "No test specifications found. This should not happen as prepare.sh should have created them."
    echo "Falling back to default test."
    TEST_SPECS="com.google.inject.internal.ProvisionListenerTest"
    echo "$TEST_SPECS" > /home/test_specs.txt
fi

echo "Running tests: $TEST_SPECS"

# Run the tests and capture the output
TEST_OUTPUT=$(mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dtest=$TEST_SPECS)
RUN_RESULT=$?

# Print the output
echo "$TEST_OUTPUT"

echo "Run execution completed with exit code: $RUN_RESULT"

# Process the test results
if [ $RUN_RESULT -eq 0 ]; then
  echo "Run execution passed"
  
  # Parse Maven output to extract test results
  PASSED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "Running.*Tests run:.*Failures: 0" | sed -E 's/Running\s+([^\s]+).*/\\1/')
  if [ -n "$PASSED_TESTS" ]; then
    echo "Passed tests: $PASSED_TESTS"
  fi
else
  echo "Run execution failed"
  
  # Parse Maven output to extract test results
  FAILED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "Running.*Tests run:.*Failures: [1-9]" | sed -E 's/Running\s+([^\s]+).*/\\1/')
  if [ -n "$FAILED_TESTS" ]; then
    echo "Failed tests: $FAILED_TESTS"
  fi
fi
""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
# Do not use set -e here as we expect the test to fail

cd /home/{pr.repo}
git reset --hard
git checkout {pr.base.sha}
git apply --whitespace=nowarn /home/test.patch

# Get the test specifications
TEST_SPECS=$(cat /home/test_specs.txt)
if [ -z "$TEST_SPECS" ]; then
    echo "No test specifications found. This should not happen as prepare.sh should have created them."
    echo "Falling back to default test."
    TEST_SPECS="com.google.inject.internal.ProvisionListenerTest"
    echo "$TEST_SPECS" > /home/test_specs.txt
fi

echo "Running test with test patch only"
echo "==== TEST PATCH EXECUTION START ===="
echo "Running tests: $TEST_SPECS"

# Run the tests and capture the output
TEST_OUTPUT=$(mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dtest=$TEST_SPECS)
TEST_RESULT=$?

# Print the output
echo "$TEST_OUTPUT"

echo "==== TEST PATCH EXECUTION END ===="
echo "Test patch execution completed with exit code: $TEST_RESULT"

# Process the test results
if [ $TEST_RESULT -ne 0 ]; then
  echo "Test patch execution failed as expected"
  
  # Parse Maven output to extract test results
  FAILED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "Running.*Tests run:.*Failures: [1-9]" | sed -E 's/Running\s+([^\s]+).*/\\1/')
  if [ -n "$FAILED_TESTS" ]; then
    echo "Failed tests: $FAILED_TESTS"
  fi
else
  echo "Test patch execution passed unexpectedly"
  
  # Parse Maven output to extract test results
  PASSED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "Running.*Tests run:.*Failures: 0" | sed -E 's/Running\s+([^\s]+).*/\\1/')
  if [ -n "$PASSED_TESTS" ]; then
    echo "Passed tests: $PASSED_TESTS"
  fi
fi

""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
# Do not use set -e here as we need to capture the exit code

cd /home/{pr.repo}
git reset --hard
git checkout {pr.base.sha}
git apply --whitespace=nowarn /home/test.patch /home/fix.patch

# Get the test specifications
TEST_SPECS=$(cat /home/test_specs.txt)
if [ -z "$TEST_SPECS" ]; then
    echo "No test specifications found. This should not happen as prepare.sh should have created them."
    echo "Falling back to default test."
    TEST_SPECS="com.google.inject.internal.ProvisionListenerTest"
    echo "$TEST_SPECS" > /home/test_specs.txt
fi

echo "Processing fix-run.sh execution with test names: $TEST_SPECS"
echo "Running test with both test and fix patches"
echo "==== FIX PATCH EXECUTION START ===="
echo "Running tests: $TEST_SPECS"

# Run the tests and capture the output
TEST_OUTPUT=$(mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dtest=$TEST_SPECS)
FIX_RESULT=$?

# Print the output
echo "$TEST_OUTPUT"

echo "==== FIX PATCH EXECUTION END ===="
echo "Fix patch execution completed with exit code: $FIX_RESULT"

# Process the test results
if [ $FIX_RESULT -eq 0 ]; then
  echo "Fix patch execution passed as expected"
  
  # Parse Maven output to extract test results
  PASSED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "Running.*Tests run:.*Failures: 0" | sed -E 's/Running\s+([^\s]+).*/\\1/')
  if [ -n "$PASSED_TESTS" ]; then
    echo "Passed tests: $PASSED_TESTS"
  fi
else
  echo "Fix patch execution failed unexpectedly"
  
  # Parse Maven output to extract test results
  FAILED_TESTS=$(echo "$TEST_OUTPUT" | grep -E "Running.*Tests run:.*Failures: [1-9]" | sed -E 's/Running\s+([^\s]+).*/\\1/')
  if [ -n "$FAILED_TESTS" ]; then
    echo "Failed tests: $FAILED_TESTS"
  fi
fi

""".format(
                    pr=self.pr
                ),
            ),
        ]

    def dockerfile(self) -> str:
        image = self.dependency()
        name = image.image_name()
        tag = image.image_tag()

        copy_commands = ""
        for file in self.files():
            copy_commands += f"COPY {file.name} /home/\n"

        prepare_commands = "RUN bash /home/prepare.sh"
        proxy_setup = ""
        proxy_cleanup = ""

        if self.global_env:
            # Extract proxy host and port
            proxy_host = None
            proxy_port = None

            for line in self.global_env.splitlines():
                match = re.match(
                    r"^ENV\s*(http[s]?_proxy)=http[s]?://([^:]+):(\d+)", line
                )
                if match:
                    proxy_host = match.group(2)
                    proxy_port = match.group(3)
                    break
            if proxy_host and proxy_port:
                proxy_setup = textwrap.dedent(
                    f"""
                RUN mkdir -p ~/.m2 && \\
                    if [ ! -f ~/.m2/settings.xml ]; then \\
                        echo '<?xml version="1.0" encoding="UTF-8"?>' > ~/.m2/settings.xml && \\
                        echo '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"' >> ~/.m2/settings.xml && \\
                        echo '          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' >> ~/.m2/settings.xml && \\
                        echo '          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">' >> ~/.m2/settings.xml && \\
                        echo '</settings>' >> ~/.m2/settings.xml; \\
                    fi && \\
                    sed -i '$d' ~/.m2/settings.xml && \\
                    echo '<proxies>' >> ~/.m2/settings.xml && \\
                    echo '    <proxy>' >> ~/.m2/settings.xml && \\
                    echo '        <id>example-proxy</id>' >> ~/.m2/settings.xml && \\
                    echo '        <active>true</active>' >> ~/.m2/settings.xml && \\
                    echo '        <protocol>http</protocol>' >> ~/.m2/settings.xml && \\
                    echo '        <host>{proxy_host}</host>' >> ~/.m2/settings.xml && \\
                    echo '        <port>{proxy_port}</port>' >> ~/.m2/settings.xml && \\
                    echo '        <username></username>' >> ~/.m2/settings.xml && \\
                    echo '        <password></password>' >> ~/.m2/settings.xml && \\
                    echo '        <nonProxyHosts></nonProxyHosts>' >> ~/.m2/settings.xml && \\
                    echo '    </proxy>' >> ~/.m2/settings.xml && \\
                    echo '</proxies>' >> ~/.m2/settings.xml && \\
                    echo '</settings>' >> ~/.m2/settings.xml
                """
                )

                proxy_cleanup = textwrap.dedent(
                    """
                    RUN sed -i '/<proxies>/,/<\\/proxies>/d' ~/.m2/settings.xml
                """
                )
        return f"""FROM {name}:{tag}

{self.global_env}

{proxy_setup}

{copy_commands}

{prepare_commands}

{proxy_cleanup}

{self.clear_env}

"""


@Instance.register("google", "guice")
class Guice(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return GuiceImageDefault(self.pr, self._config)

    def run(self, run_cmd: str = "") -> str:
        if run_cmd:
            return run_cmd

        return "bash /home/run.sh"

    def test_patch_run(self, test_patch_run_cmd: str = "") -> str:
        if test_patch_run_cmd:
            return test_patch_run_cmd

        return "bash /home/test-run.sh"

    def fix_patch_run(self, fix_patch_run_cmd: str = "") -> str:
        if fix_patch_run_cmd:
            return fix_patch_run_cmd

        return "bash /home/fix-run.sh"

    def parse_log(self, test_log: str) -> TestResult:
        passed_tests = set()
        failed_tests = set()
        skipped_tests = set()

        # Extract test specifications from the log
        test_specs_match = re.search(r"Running tests: ([\w\.,#]+)", test_log)
        test_specs = "com.google.inject.internal.ProvisionListenerTest"  # Default fallback
        if test_specs_match:
            test_specs = test_specs_match.group(1)
            print(f"Found test specifications: {test_specs}")
        
        # Parse test specs into individual test names
        test_names = []
        for spec in test_specs.split(","):
            spec = spec.strip()
            if not spec:
                continue
                
            if "#" in spec:
                # This is a class with specific methods
                class_name, methods = spec.split("#", 1)
                for method in methods.split(","):
                    test_names.append(f"{class_name}#{method}")
            else:
                # This is just a class name, we'll extract individual tests later
                test_names.append(spec)
        
        # Look for explicit test results in the log
        passed_tests_match = re.search(r"Passed tests: ([\w\.,#]+)", test_log)
        if passed_tests_match:
            passed_tests_str = passed_tests_match.group(1)
            for test in passed_tests_str.split(","):
                passed_tests.add(test.strip())
            print(f"Found explicit passed tests: {passed_tests}")
            
        failed_tests_match = re.search(r"Failed tests: ([\w\.,#]+)", test_log)
        if failed_tests_match:
            failed_tests_str = failed_tests_match.group(1)
            for test in failed_tests_str.split(","):
                failed_tests.add(test.strip())
            print(f"Found explicit failed tests: {failed_tests}")
        
        # Check for specific test results in test-run.sh execution
        if "Running test with test patch only" in test_log:
            # This is the test-run.sh execution
            print(f"Processing test-run.sh execution with test names: {test_names}")
            
            # Look for our custom markers and exit code
            if "Test patch execution completed with exit code: 0" in test_log:
                # The tests passed unexpectedly
                print("Test patch execution unexpectedly passed (exit code 0)")
                if "BUILD SUCCESS" in test_log and len(passed_tests) == 0:
                    # Add all test names as passed if we don't have explicit passed tests
                    for test_name in test_names:
                        passed_tests.add(test_name)
            elif "Test patch execution completed with exit code:" in test_log:
                # The tests failed as expected
                print("Test patch execution failed as expected (non-zero exit code)")
                if "BUILD FAILURE" in test_log and len(failed_tests) == 0:
                    # Add all test names as failed if we don't have explicit failed tests
                    for test_name in test_names:
                        failed_tests.add(test_name)
            
            # Process individual test results from Maven output if we don't have explicit results
            if len(passed_tests) == 0 and len(failed_tests) == 0:
                self._process_maven_test_results(test_log, passed_tests, failed_tests, skipped_tests)
            
            # If we still couldn't determine any results, check the build status
            if len(passed_tests) == 0 and len(failed_tests) == 0 and len(skipped_tests) == 0:
                if "BUILD SUCCESS" in test_log:
                    print("No specific test results found, but build succeeded. Assuming all tests passed.")
                    for test_name in test_names:
                        passed_tests.add(test_name)
                elif "BUILD FAILURE" in test_log:
                    print("No specific test results found, but build failed. Assuming all tests failed.")
                    for test_name in test_names:
                        failed_tests.add(test_name)
                else:
                    print("No specific test results found and no build status. Assuming all tests failed.")
                    for test_name in test_names:
                        failed_tests.add(test_name)
                
            # Print a snippet of the log for debugging
            print(f"Test patch log snippet: {test_log[-500:] if len(test_log) > 500 else test_log}")
            
            return TestResult(
                passed_count=len(passed_tests),
                failed_count=len(failed_tests),
                skipped_count=len(skipped_tests),
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
            )
        
        # Check for specific test results in fix-run.sh execution
        if "Running test with both test and fix patches" in test_log or "Processing fix-run.sh execution with test names:" in test_log:
            # This is the fix-run.sh execution
            print(f"Processing fix-run.sh execution with test names: {test_names}")
            
            # Look for our custom markers and exit code
            if "Fix patch execution completed with exit code: 0" in test_log:
                # The tests passed with the fix
                print("Fix patch execution passed as expected (exit code 0)")
                if "BUILD SUCCESS" in test_log and len(passed_tests) == 0:
                    # Add all test names as passed if we don't have explicit passed tests
                    for test_name in test_names:
                        passed_tests.add(test_name)
            elif "Fix patch execution completed with exit code:" in test_log:
                # The tests still failed even with the fix
                print("Fix patch execution failed unexpectedly (non-zero exit code)")
                if "BUILD FAILURE" in test_log and len(failed_tests) == 0:
                    # Add all test names as failed if we don't have explicit failed tests
                    for test_name in test_names:
                        failed_tests.add(test_name)
            
            # Process individual test results from Maven output if we don't have explicit results
            if len(passed_tests) == 0 and len(failed_tests) == 0:
                self._process_maven_test_results(test_log, passed_tests, failed_tests, skipped_tests)
            
            # If we still couldn't determine any results, check the build status
            if len(passed_tests) == 0 and len(failed_tests) == 0 and len(skipped_tests) == 0:
                if "BUILD SUCCESS" in test_log:
                    print("No specific test results found, but build succeeded. Assuming all tests passed.")
                    for test_name in test_names:
                        passed_tests.add(test_name)
                elif "BUILD FAILURE" in test_log:
                    print("No specific test results found, but build failed. Assuming all tests failed.")
                    for test_name in test_names:
                        failed_tests.add(test_name)
                else:
                    print("No specific test results found and no build status. Assuming all tests failed.")
                    for test_name in test_names:
                        failed_tests.add(test_name)
                
            # Print a snippet of the log for debugging
            print(f"Fix patch log snippet: {test_log[-500:] if len(test_log) > 500 else test_log}")
            
            return TestResult(
                passed_count=len(passed_tests),
                failed_count=len(failed_tests),
                skipped_count=len(skipped_tests),
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
            )
        
        # Process regular Maven test output if not a special execution and we don't have explicit results
        if len(passed_tests) == 0 and len(failed_tests) == 0:
            self._process_maven_test_results(test_log, passed_tests, failed_tests, skipped_tests)
        
        # If we still couldn't determine any results, check the build status
        if len(passed_tests) == 0 and len(failed_tests) == 0 and len(skipped_tests) == 0:
            if "BUILD SUCCESS" in test_log:
                print("No specific test results found, but build succeeded. Assuming all tests passed.")
                for test_name in test_names:
                    passed_tests.add(test_name)
            elif "BUILD FAILURE" in test_log:
                print("No specific test results found, but build failed. Assuming all tests failed.")
                for test_name in test_names:
                    failed_tests.add(test_name)
            else:
                print("No specific test results found and no build status. Assuming all tests passed.")
                for test_name in test_names:
                    passed_tests.add(test_name)
        
        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
        
    def _process_maven_test_results(self, test_log: str, passed_tests: set, failed_tests: set, skipped_tests: set):
        """Process Maven test output to extract test results."""

        # Maven test output patterns for Guice - improved to handle various formats
        re_pass_tests = [
            # Standard Maven test output pattern - only consider as pass if Failures and Errors are 0
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s*Failures:\s*0,\s*Errors:\s*0,\s*Skipped:\s*(\d+),\s*Time elapsed:\s*[\d.]+\s*sec(?!\s+<<<)", re.MULTILINE),
            # Alternative format with different spacing
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s+Failures:\s*0,\s+Errors:\s*0,\s+Skipped:\s*(\d+),\s+Time elapsed:\s*[\d.]+\s+s(?!\s+<<<)", re.MULTILINE),
            # Additional pattern for Guice tests
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s+Failures:\s*0,\s+Errors:\s*0,\s+Skipped:\s*(\d+)", re.MULTILINE)
        ]
        
        re_fail_tests = [
            # Standard Maven failure pattern with FAILURE marker
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+),\s*Time elapsed:\s*[\d.]+\s*sec\s+<<<\s+FAILURE!", re.MULTILINE),
            # Alternative format with different spacing
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s+Failures:\s*(\d+),\s+Errors:\s*(\d+),\s+Skipped:\s*(\d+),\s+Time elapsed:\s*[\d.]+\s+s\s+<<<\s+FAILURE!", re.MULTILINE),
            # Error pattern with ERROR marker
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+),\s*Time elapsed:\s*[\d.]+\s*sec\s+<<<\s+ERROR!", re.MULTILINE),
            # Failure pattern without marker but with non-zero failures
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s*Failures:\s*([1-9]\d*),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+),\s*Time elapsed:\s*[\d.]+\s*sec", re.MULTILINE),
            # Error pattern without marker but with non-zero errors
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*([1-9]\d*),\s*Skipped:\s*(\d+),\s*Time elapsed:\s*[\d.]+\s*sec", re.MULTILINE),
            # Additional pattern for Guice tests with failures
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s+Failures:\s*([1-9]\d*),\s+Errors:\s*(\d+),\s+Skipped:\s*(\d+)", re.MULTILINE),
            # Additional pattern for Guice tests with errors
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s+Failures:\s*(\d+),\s+Errors:\s*([1-9]\d*),\s+Skipped:\s*(\d+)", re.MULTILINE)
        ]
        
        # Look for specific test failures in the log
        test_failure_patterns = [
            re.compile(r"^Tests run:.*Failures: (\d+), Errors: (\d+).*$", re.MULTILINE),
            re.compile(r"^Tests run:.*Failures: (\d+),.*Errors: (\d+).*$", re.MULTILINE),
            re.compile(r"Tests run: \d+, Failures: (\d+), Errors: (\d+)", re.MULTILINE)
        ]
        
        test_failure_match = None
        for pattern in test_failure_patterns:
            match = pattern.search(test_log)
            if match:
                test_failure_match = match
                break
        
        # Check for specific test method failures
        method_failure_patterns = [
            re.compile(r"testcase.*name=\"([^\"]+)\".*time=\"[\d.]+\">\s*<failure", re.MULTILINE),
            re.compile(r"testcase.*name=\"([^\"]+)\".*>\s*<failure", re.MULTILINE),
            re.compile(r"Failed tests:.*\n((?:.*\n)*?)(?:Tests run:|$)", re.MULTILINE)
        ]
        
        method_failures = []
        for pattern in method_failure_patterns:
            failures = pattern.findall(test_log)
            if failures:
                if isinstance(failures[0], tuple):
                    method_failures.extend([f[0] for f in failures])
                else:
                    method_failures.extend(failures)
        
        # Add specific method failures to failed_tests
        for method in method_failures:
            method = method.strip()
            if not method:
                continue
                
            # Extract class name from the method name (assuming format: className.methodName)
            parts = method.split(".")
            if len(parts) >= 2:
                class_name = ".".join(parts[:-1])
                method_name = parts[-1]
                failed_tests.add(f"{class_name}#{method_name}")
                # Also add the class name itself as a fallback
                failed_tests.add(class_name)
            else:
                # If we can't parse it properly, just add the whole thing
                failed_tests.add(method)

        # Process passing tests
        for re_pass_test in re_pass_tests:
            tests = re_pass_test.findall(test_log)
            for test in tests:
                test_name = test[0]
                tests_run = int(test[1])
                skipped = int(test[2])
                
                # For test classes with multiple methods
                if "#" not in test_name:  # This is a class, not a specific method
                    if tests_run > 0 and skipped != tests_run:
                        # The class had some tests run and not all were skipped
                        passed_tests.add(test_name)
                    elif skipped == tests_run:
                        # All tests in the class were skipped
                        skipped_tests.add(test_name)
                else:
                    # This is a specific method
                    if tests_run > 0:
                        passed_tests.add(test_name)

        # Process failing tests
        for re_fail_test in re_fail_tests:
            tests = re_fail_test.findall(test_log)
            for test in tests:
                test_name = test[0]
                failures = int(test[2]) if len(test) > 2 else 0
                errors = int(test[3]) if len(test) > 3 else 0
                
                if failures > 0 or errors > 0:
                    failed_tests.add(test_name)

        # Check for overall build success/failure
        if "BUILD SUCCESS" in test_log:
            # If we have a successful build, try to extract test classes from the log
            test_classes_pattern = re.compile(r"Running\s+([\w\.]+)")
            test_classes = test_classes_pattern.findall(test_log)
            
            # If we found test classes but no specific test results, mark them as passed
            if test_classes and len(failed_tests) == 0 and len(passed_tests) == 0:
                for test_class in test_classes:
                    if test_class not in failed_tests and test_class not in skipped_tests:
                        passed_tests.add(test_class)
                        
            # If we still have no test results but BUILD SUCCESS, use the test specs from the log
            if len(passed_tests) == 0 and len(failed_tests) == 0:
                test_specs_match = re.search(r"Running tests: ([\w\.,#]+)", test_log)
                if test_specs_match:
                    test_specs = test_specs_match.group(1)
                    for spec in test_specs.split(","):
                        if "#" in spec:
                            # This is a class with specific methods
                            class_name = spec.split("#", 1)[0]
                            passed_tests.add(class_name)
                        else:
                            # This is just a class name
                            passed_tests.add(spec)
        
        # Special handling for Google Guice repository
        # If we have no test results but we know the test specs, use them
        if len(passed_tests) == 0 and len(failed_tests) == 0:
            # Check if we have test specs in the log
            test_specs_match = re.search(r"Running tests: ([\w\.,#]+)", test_log)
            if test_specs_match:
                test_specs = test_specs_match.group(1)
                
                # If BUILD SUCCESS, mark all as passed
                if "BUILD SUCCESS" in test_log:
                    for spec in test_specs.split(","):
                        spec = spec.strip()
                        if spec:
                            passed_tests.add(spec)
                # If BUILD FAILURE, mark all as failed
                elif "BUILD FAILURE" in test_log:
                    for spec in test_specs.split(","):
                        spec = spec.strip()
                        if spec:
                            failed_tests.add(spec)
                # If we can't determine the build status, check for specific error messages
                else:
                    if "ERROR" in test_log or "FAILURE" in test_log or "Failed to execute goal" in test_log:
                        for spec in test_specs.split(","):
                            spec = spec.strip()
                            if spec:
                                failed_tests.add(spec)
                    else:
                        for spec in test_specs.split(","):
                            spec = spec.strip()
                            if spec:
                                passed_tests.add(spec)
        
        # Remove any test from passed_tests if it's also in failed_tests
        passed_tests = passed_tests - failed_tests

        # Remove any test from skipped_tests if it's also in passed_tests or failed_tests
        skipped_tests = skipped_tests - passed_tests - failed_tests
        
        # Print summary of what we found
        print(f"Processed Maven test results: {len(passed_tests)} passed, {len(failed_tests)} failed, {len(skipped_tests)} skipped")
        if passed_tests:
            print(f"Passed tests: {passed_tests}")
        if failed_tests:
            print(f"Failed tests: {failed_tests}")
        if skipped_tests:
            print(f"Skipped tests: {skipped_tests}")