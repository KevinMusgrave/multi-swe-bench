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
WORKDIR /home/
RUN apt-get update && apt-get install -y git openjdk-21-jdk
RUN apt-get install -y maven

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

# Run tests to make sure everything is set up correctly
mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false || true
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
mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false
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
git apply --whitespace=nowarn /home/test.patch
mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false

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
git apply --whitespace=nowarn /home/test.patch /home/fix.patch
mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false

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

        # Pattern to match test results in Maven output
        test_pattern = re.compile(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)")
        
        # Pattern to match individual test failures
        test_failure_pattern = re.compile(r"Failed tests:\s+(.+?)(?=\n\n|\Z)", re.DOTALL)
        # Pattern to match individual test errors
        test_error_pattern = re.compile(r"Tests in error:\s+(.+?)(?=\n\n|\Z)", re.DOTALL)
        
        # Find all test results
        for match in test_pattern.finditer(output):
            total_tests = int(match.group(1))
            failures = int(match.group(2))
            errors = int(match.group(3))
            skipped_count = int(match.group(4))
            
            # Calculate passed tests
            passed_count = total_tests - failures - errors - skipped_count
            
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
                    
            # If we still don't have any failed tests but there are failures or errors, check for individual error lines
            if (failures > 0 or errors > 0) and not failed_tests:
                error_lines = re.findall(r"\[ERROR\]\s+(.+?)\n", output)
                for line in error_lines:
                    if ":" in line and not line.startswith("Tests") and not line.startswith("Failed tests") and not line.startswith("Error tests"):
                        test_name = line.split(':')[0].strip()
                        if test_name and not test_name.startswith('['):
                            failed_tests.add(test_name)
            
            # For skipped tests, we don't have individual names, so we'll use a placeholder
            if skipped_count > 0:
                skipped_tests.add(f"Skipped tests: {skipped_count}")
            
            # For passed tests, if we don't have individual names, we'll use a placeholder
            if passed_count > 0:
                passed_tests.add(f"Passed tests: {passed_count}")

        # If we have a successful build with no failures, consider all tests as passed
        if "BUILD SUCCESS" in output and not failed_tests:
            # Extract the total number of tests
            total_tests_match = re.search(r"Tests run: (\d+), Failures: 0, Errors: 0", output)
            if total_tests_match:
                total_tests = int(total_tests_match.group(1))
                passed_tests.add(f"All {total_tests} tests passed")

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )