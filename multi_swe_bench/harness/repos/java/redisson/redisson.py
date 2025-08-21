import re
import textwrap
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


class RedissonImageBase(Image):
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
        return "ubuntu:24.04"

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
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV MAVEN_OPTS="-Xmx2048m"
WORKDIR /home/
RUN apt-get update && apt-get install -y git openjdk-21-jdk maven redis-server

# Configure Maven to use a local repository to speed up builds
RUN mkdir -p /root/.m2 && echo '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd"><localRepository>/home/.m2/repository</localRepository></settings>' > /root/.m2/settings.xml

{code}

{self.clear_env}

"""


class RedissonImageDefault(Image):
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
        return RedissonImageBase(self.pr, self._config)

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
                "prepare.sh",
                """#!/bin/bash
set -e

cd /home/{pr.repo}
git reset --hard
bash /home/check_git_changes.sh
git checkout {pr.base.sha}
bash /home/check_git_changes.sh

# Install Redis for testing
apt-get update && apt-get install -y redis-server
service redis-server start

# Set Java environment
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Update pom.xml to use Java 21
if [ -f pom.xml ]; then
    # Update maven.compiler.source and maven.compiler.target properties
    sed -i 's/<maven.compiler.source>.*<\/maven.compiler.source>/<maven.compiler.source>21<\/maven.compiler.source>/g' pom.xml
    sed -i 's/<maven.compiler.target>.*<\/maven.compiler.target>/<maven.compiler.target>21<\/maven.compiler.target>/g' pom.xml
    
    # If properties don't exist, add them
    if ! grep -q "<maven.compiler.source>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.source>21</maven.compiler.source>' pom.xml
    fi
    if ! grep -q "<maven.compiler.target>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.target>21</maven.compiler.target>' pom.xml
    fi
    
    # If properties section doesn't exist, add it
    if ! grep -q "<properties>" pom.xml; then
        sed -i '/<project/a \    <properties>\n        <maven.compiler.source>21</maven.compiler.source>\n        <maven.compiler.target>21</maven.compiler.target>\n    </properties>' pom.xml
    fi
fi

# Compile the project without running tests to make sure everything is set up correctly
mvn clean compile -Dmaven.test.skip=true || true

# Extract test class names from the test patch for later use
grep -o -E "class [A-Za-z0-9]+" /home/test.patch | grep -v "class Path" | cut -d' ' -f2 | sort -u > /home/test_classes.txt
""".format(
                    pr=self.pr,
                ),
            ),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
set -e

cd /home/{pr.repo}
service redis-server start
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Update pom.xml to use Java 21
if [ -f pom.xml ]; then
    # Update maven.compiler.source and maven.compiler.target properties
    sed -i 's/<maven.compiler.source>.*<\/maven.compiler.source>/<maven.compiler.source>21<\/maven.compiler.source>/g' pom.xml
    sed -i 's/<maven.compiler.target>.*<\/maven.compiler.target>/<maven.compiler.target>21<\/maven.compiler.target>/g' pom.xml
    
    # If properties don't exist, add them
    if ! grep -q "<maven.compiler.source>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.source>21</maven.compiler.source>' pom.xml
    fi
    if ! grep -q "<maven.compiler.target>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.target>21</maven.compiler.target>' pom.xml
    fi
    
    # If properties section doesn't exist, add it
    if ! grep -q "<properties>" pom.xml; then
        sed -i '/<project/a \    <properties>\n        <maven.compiler.source>21</maven.compiler.source>\n        <maven.compiler.target>21</maven.compiler.target>\n    </properties>' pom.xml
    fi
fi

# Run only the specific test class that's modified in the test patch
# Extract test class names from the test patch
TEST_CLASSES=$(grep -o -E "class [A-Za-z0-9]+" /home/test.patch | grep -v "class Path" | cut -d' ' -f2 | sort -u)

if [ -n "$TEST_CLASSES" ]; then
    echo "Running specific test classes: $TEST_CLASSES"
    for TEST_CLASS in $TEST_CLASSES; do
        mvn test -Dtest=$TEST_CLASS -DfailIfNoTests=false
    done
else
    # Fallback to running all tests if no specific test class is found
    echo "No specific test classes found, running all tests"
    mvn test -Dmaven.test.skip=false -DfailIfNoTests=false
fi
""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
set -e

cd /home/{pr.repo}
service redis-server start
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Update pom.xml to use Java 21
if [ -f pom.xml ]; then
    # Update maven.compiler.source and maven.compiler.target properties
    sed -i 's/<maven.compiler.source>.*<\/maven.compiler.source>/<maven.compiler.source>21<\/maven.compiler.source>/g' pom.xml
    sed -i 's/<maven.compiler.target>.*<\/maven.compiler.target>/<maven.compiler.target>21<\/maven.compiler.target>/g' pom.xml
    
    # If properties don't exist, add them
    if ! grep -q "<maven.compiler.source>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.source>21</maven.compiler.source>' pom.xml
    fi
    if ! grep -q "<maven.compiler.target>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.target>21</maven.compiler.target>' pom.xml
    fi
    
    # If properties section doesn't exist, add it
    if ! grep -q "<properties>" pom.xml; then
        sed -i '/<project/a \    <properties>\n        <maven.compiler.source>21</maven.compiler.source>\n        <maven.compiler.target>21</maven.compiler.target>\n    </properties>' pom.xml
    fi
fi

git apply --whitespace=nowarn /home/test.patch

# Run only the specific test class that's modified in the test patch
# Extract test class names from the test patch
TEST_CLASSES=$(grep -o -E "class [A-Za-z0-9]+" /home/test.patch | grep -v "class Path" | cut -d' ' -f2 | sort -u)

if [ -n "$TEST_CLASSES" ]; then
    echo "Running specific test classes: $TEST_CLASSES"
    for TEST_CLASS in $TEST_CLASSES; do
        mvn test -Dtest=$TEST_CLASS -DfailIfNoTests=false
    done
else
    # Fallback to running all tests if no specific test class is found
    echo "No specific test classes found, running all tests"
    mvn test -Dmaven.test.skip=false -DfailIfNoTests=false
fi
""".format(
                    pr=self.pr
                ),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
set -e

cd /home/{pr.repo}
service redis-server start
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

# Update pom.xml to use Java 21
if [ -f pom.xml ]; then
    # Update maven.compiler.source and maven.compiler.target properties
    sed -i 's/<maven.compiler.source>.*<\/maven.compiler.source>/<maven.compiler.source>21<\/maven.compiler.source>/g' pom.xml
    sed -i 's/<maven.compiler.target>.*<\/maven.compiler.target>/<maven.compiler.target>21<\/maven.compiler.target>/g' pom.xml
    
    # If properties don't exist, add them
    if ! grep -q "<maven.compiler.source>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.source>21</maven.compiler.source>' pom.xml
    fi
    if ! grep -q "<maven.compiler.target>" pom.xml; then
        sed -i '/<properties>/a \        <maven.compiler.target>21</maven.compiler.target>' pom.xml
    fi
    
    # If properties section doesn't exist, add it
    if ! grep -q "<properties>" pom.xml; then
        sed -i '/<project/a \    <properties>\n        <maven.compiler.source>21</maven.compiler.source>\n        <maven.compiler.target>21</maven.compiler.target>\n    </properties>' pom.xml
    fi
fi

git apply --whitespace=nowarn /home/test.patch /home/fix.patch

# Run only the specific test class that's modified in the test patch
# Extract test class names from the test patch
TEST_CLASSES=$(grep -o -E "class [A-Za-z0-9]+" /home/test.patch | grep -v "class Path" | cut -d' ' -f2 | sort -u)

if [ -n "$TEST_CLASSES" ]; then
    echo "Running specific test classes: $TEST_CLASSES"
    for TEST_CLASS in $TEST_CLASSES; do
        mvn test -Dtest=$TEST_CLASS -DfailIfNoTests=false
    done
else
    # Fallback to running all tests if no specific test class is found
    echo "No specific test classes found, running all tests"
    mvn test -Dmaven.test.skip=false -DfailIfNoTests=false
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


@Instance.register("redisson", "redisson")
class Redisson(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return RedissonImageDefault(self.pr, self._config)

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

    def parse_test_results(self, output: str) -> TestResult:
        # Extract test results from Maven output
        passed_tests = set()
        failed_tests = set()
        skipped_tests = set()
        
        # Check if the build was successful
        build_success = "BUILD SUCCESS" in output
        
        # Check for compilation errors
        compilation_error = "Fatal error compiling" in output
        if compilation_error:
            failed_tests.add("Compilation error detected")
            return TestResult(
                passed_count=0,
                failed_count=1,
                skipped_count=0,
                passed_tests=list(passed_tests),
                failed_tests=list(failed_tests),
                skipped_tests=list(skipped_tests)
            )
        
        # Pattern to match test results in Maven output
        test_pattern = re.compile(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)")
        
        # Pattern to match individual test failures
        test_failure_pattern = re.compile(r"Failed tests:\s+(.+?)(?=\n\n|\Z)", re.DOTALL)
        # Pattern to match individual test errors
        test_error_pattern = re.compile(r"Tests in error:\s+(.+?)(?=\n\n|\Z)", re.DOTALL)
        
        # Pattern to match test class names
        test_class_pattern = re.compile(r"Running ([\w\.]+)")
        
        # Find all test classes that were run
        test_classes = set()
        for match in test_class_pattern.finditer(output):
            test_class = match.group(1)
            test_classes.add(test_class)
        
        # Find all test results
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        
        for match in test_pattern.finditer(output):
            total_tests = int(match.group(1))
            failures = int(match.group(2))
            errors = int(match.group(3))
            skipped_count = int(match.group(4))
            
            # Calculate passed tests
            passed_count = total_tests - failures - errors - skipped_count
            total_passed += passed_count
            total_failed += failures + errors
            total_skipped += skipped_count
            
            # If there are failures, extract the specific test names
            if failures > 0:
                failure_matches = list(test_failure_pattern.finditer(output))
                if failure_matches:
                    for failure_match in failure_matches:
                        failure_text = failure_match.group(1)
                        # Extract individual test names
                        for line in failure_text.strip().split('\n'):
                            line = line.strip()
                            if line and not line.startswith('['):
                                # Extract just the test name from lines like "ClassName.methodName:45 expected:<true> but was:<false>"
                                test_name = line.split(':')[0] if ':' in line else line
                                failed_tests.add(test_name)
                else:
                    # If we can't find specific test names, use a placeholder
                    failed_tests.add(f"Failed tests: {failures}")
            
            # If there are errors, extract the specific test names
            if errors > 0:
                error_matches = list(test_error_pattern.finditer(output))
                if error_matches:
                    for error_match in error_matches:
                        error_text = error_match.group(1)
                        # Extract individual test names
                        for line in error_text.strip().split('\n'):
                            line = line.strip()
                            if line and not line.startswith('['):
                                # Extract just the test name from lines like "ClassName.methodName:45 NullPointerException"
                                test_name = line.split(':')[0] if ':' in line else line
                                failed_tests.add(test_name)
                else:
                    # If we can't find specific test names, use a placeholder
                    failed_tests.add(f"Error tests: {errors}")
        
        # If we have test classes but no specific test results, add them as passed tests
        if build_success and test_classes and not failed_tests:
            for test_class in test_classes:
                passed_tests.add(f"{test_class} passed")
        elif total_passed > 0:
            passed_tests.add(f"Passed tests: {total_passed}")
        
        # Add skipped tests count
        if total_skipped > 0:
            skipped_tests.add(f"Skipped tests: {total_skipped}")
        
        # If there are no test results at all but the build was successful, consider it a pass
        if not passed_tests and not failed_tests and not skipped_tests and build_success:
            passed_tests.add("Build successful, no test results found")
        
        # If there are no test results and the build failed, consider it a failure
        if not passed_tests and not failed_tests and not skipped_tests and not build_success:
            failed_tests.add("Build failed, no test results found")

        return TestResult(
            passed_count=total_passed if total_passed > 0 else len(passed_tests),
            failed_count=total_failed if total_failed > 0 else len(failed_tests),
            skipped_count=total_skipped if total_skipped > 0 else len(skipped_tests),
            passed_tests=list(passed_tests),
            failed_tests=list(failed_tests),
            skipped_tests=list(skipped_tests),
        )