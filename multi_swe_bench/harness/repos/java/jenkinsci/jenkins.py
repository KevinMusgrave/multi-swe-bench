import re
import textwrap
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


class JenkinsImageBase(Image):
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
ENV MAVEN_OPTS="-Xmx8g -XX:MaxPermSize=1g -Xss4m"
ENV JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8"
WORKDIR /home/
RUN apt-get update && apt-get install -y git openjdk-17-jdk wget unzip curl procps
# Install Maven 3.9.6
RUN wget https://dlcdn.apache.org/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz && \
    tar -xzf apache-maven-3.9.6-bin.tar.gz -C /opt && \
    ln -s /opt/apache-maven-3.9.6/bin/mvn /usr/bin/mvn && \
    rm apache-maven-3.9.6-bin.tar.gz

# Configure Maven settings
RUN mkdir -p /root/.m2 && \
    echo '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0" \
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" \
    xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 \
    https://maven.apache.org/xsd/settings-1.0.0.xsd"> \
    <mirrors> \
        <mirror> \
            <id>central-secure</id> \
            <url>https://repo.maven.apache.org/maven2</url> \
            <mirrorOf>central</mirrorOf> \
        </mirror> \
    </mirrors> \
    <profiles> \
        <profile> \
            <id>jenkins-default</id> \
            <properties> \
                <maven.test.failure.ignore>true</maven.test.failure.ignore> \
            </properties> \
        </profile> \
    </profiles> \
    <activeProfiles> \
        <activeProfile>jenkins-default</activeProfile> \
    </activeProfiles> \
</settings>' > /root/.m2/settings.xml

{code}

{self.clear_env}

"""


class JenkinsImageDefault(Image):
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
        return JenkinsImageBase(self.pr, self._config)

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

# First, just compile without running tests
mvn clean install -DskipTests -Dmaven.javadoc.skip=true -Denforcer.skip=true || true

# Then run tests for the specific modules affected by the PR
if [[ -f "/home/test.patch" ]]; then
    # Extract module names from the test patch
    MODULES=$(grep -o "diff --git [^ ]* [^ ]*" /home/test.patch | awk '{{print $3}}' | grep -o "^[^/]*" | sort -u | tr '\n' ',')
    if [[ -n "$MODULES" ]]; then
        echo "Running tests for modules: $MODULES"
        mvn test -pl "$MODULES" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true || true
    else
        # Fallback to running specific modules that are commonly affected
        echo "No specific modules found in patch, running tests for war and test modules"
        mvn test -pl "war,test" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true || true
    fi
else
    # Fallback to running specific modules that are commonly affected
    echo "No test patch found, running tests for war and test modules"
    mvn test -pl "war,test" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true || true
fi
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

# Print Java and Maven versions for debugging
java -version
mvn --version

# First, just compile without running tests
echo "Building Jenkins without tests..."
mvn clean install -DskipTests -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -T 1C

# Then run tests for the specific modules affected by the PR
if [[ -f "/home/test.patch" ]]; then
    # Extract module names from the test patch
    MODULES=$(grep -o "diff --git [^ ]* [^ ]*" /home/test.patch | awk '{{print $3}}' | grep -o "^[^/]*" | sort -u | tr '\n' ',')
    if [[ -n "$MODULES" ]]; then
        echo "Running tests for modules: $MODULES"
        mvn test -pl "$MODULES" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
    else
        # Fallback to running specific modules that are commonly affected
        echo "No specific modules found in patch, running tests for war and test modules"
        mvn test -pl "war,test" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
    fi
else
    # Fallback to running specific modules that are commonly affected
    echo "No test patch found, running tests for war and test modules"
    mvn test -pl "war,test" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
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

# Print Java and Maven versions for debugging
java -version
mvn --version

# Apply the test patch
echo "Applying test patch..."
git apply --whitespace=nowarn /home/test.patch

# First, just compile without running tests
echo "Building Jenkins with test patch without running tests..."
mvn clean install -DskipTests -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -T 1C

# Then run tests for the specific modules affected by the PR
# Extract module names from the test patch
MODULES=$(grep -o "diff --git [^ ]* [^ ]*" /home/test.patch | awk '{{print $3}}' | grep -o "^[^/]*" | sort -u | tr '\n' ',')
if [[ -n "$MODULES" ]]; then
    echo "Running tests for modules: $MODULES"
    mvn test -pl "$MODULES" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
else
    # Fallback to running specific modules that are commonly affected
    echo "No specific modules found in patch, running tests for war and test modules"
    mvn test -pl "war,test" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
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

# Print Java and Maven versions for debugging
java -version
mvn --version

# Apply both patches
echo "Applying test and fix patches..."
git apply --whitespace=nowarn /home/test.patch /home/fix.patch

# First, just compile without running tests
echo "Building Jenkins with test and fix patches without running tests..."
mvn clean install -DskipTests -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -T 1C

# Then run tests for the specific modules affected by the PR
# Extract module names from the test patch and fix patch
TEST_MODULES=$(grep -o "diff --git [^ ]* [^ ]*" /home/test.patch | awk '{{print $3}}' | grep -o "^[^/]*" | sort -u)
FIX_MODULES=$(grep -o "diff --git [^ ]* [^ ]*" /home/fix.patch | awk '{{print $3}}' | grep -o "^[^/]*" | sort -u)
MODULES=$(echo "$TEST_MODULES $FIX_MODULES" | tr ' ' '\n' | sort -u | tr '\n' ',')

if [[ -n "$MODULES" ]]; then
    echo "Running tests for modules: $MODULES"
    mvn test -pl "$MODULES" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
else
    # Fallback to running specific modules that are commonly affected
    echo "No specific modules found in patches, running tests for war and test modules"
    mvn test -pl "war,test" -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dspotbugs.skip=true -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dsurefire.useFile=false -Dsurefire.rerunFailingTestsCount=2
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


@Instance.register("jenkinsci", "jenkins")
class Jenkins(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return JenkinsImageDefault(self.pr, self._config)

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

        # Look for individual test methods (more specific than class-level results)
        individual_test_failures = re.findall(r"([a-zA-Z0-9_$.]+(?:\.[a-zA-Z0-9_$]+)+)\(([a-zA-Z0-9_$.]+)\)  Time elapsed: [0-9.]+ sec  <<< (FAILURE|ERROR)!", test_log)
        for test_method, test_class, _ in individual_test_failures:
            failed_tests.add(f"{test_class}#{test_method}")

        # Look for individual test successes
        individual_test_successes = re.findall(r"([a-zA-Z0-9_$.]+(?:\.[a-zA-Z0-9_$]+)+)\(([a-zA-Z0-9_$.]+)\)  Time elapsed: [0-9.]+ sec(?! <<< )", test_log)
        for test_method, test_class in individual_test_successes:
            if f"{test_class}#{test_method}" not in failed_tests:
                passed_tests.add(f"{test_class}#{test_method}")

        # Regular expressions to match test results
        re_pass_tests = [
            # Standard Maven test output
            re.compile(r"Running\s+(.+?)\s*\n(?:(?!Tests run:).*\n)*Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+),\s*Time elapsed:\s*[\d.]+\s*sec"),
            # Alternative format sometimes used
            re.compile(r"Running\s+(.+?)\s*\nTests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)")
        ]
        
        re_fail_tests = [
            # Standard Maven failure output
            re.compile(r"Running (.+?)\nTests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+), Time elapsed: [\d\.]+ sec +<<< FAILURE!"),
            # Alternative failure format
            re.compile(r"Running (.+?)\nTests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+).*<<< FAILURE!")
        ]
        
        # Look for summary results
        summary_match = re.search(r"Results :\s*\n\s*Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", test_log)
        if summary_match:
            total_run = int(summary_match.group(1))
            total_failures = int(summary_match.group(2))
            total_errors = int(summary_match.group(3))
            total_skipped = int(summary_match.group(4))
            
            # If we have a summary but no detailed test results, create a placeholder
            if total_run > 0 and len(passed_tests) == 0 and len(failed_tests) == 0 and len(skipped_tests) == 0:
                if total_failures > 0 or total_errors > 0:
                    failed_tests.add("JenkinsTests")
                if total_run - total_failures - total_errors - total_skipped > 0:
                    passed_tests.add("JenkinsTests")
                if total_skipped > 0:
                    skipped_tests.add("JenkinsTests")

        # Process detailed test results at class level
        for re_pass_test in re_pass_tests:
            tests = re_pass_test.findall(test_log, re.MULTILINE)
            for test in tests:
                test_name = test[0]
                tests_run = int(test[1])
                failures = int(test[2])
                errors = int(test[3])
                skipped = int(test[4])
                
                # Only add if we don't have more specific test methods already
                if not any(test_id.startswith(f"{test_name}#") for test_id in passed_tests.union(failed_tests)):
                    if tests_run > 0 and failures == 0 and errors == 0 and skipped != tests_run:
                        passed_tests.add(test_name)
                    elif failures > 0 or errors > 0:
                        failed_tests.add(test_name)
                    elif skipped == tests_run:
                        skipped_tests.add(test_name)

        for re_fail_test in re_fail_tests:
            tests = re_fail_test.findall(test_log, re.MULTILINE)
            for test in tests:
                test_name = test[0]
                # Only add if we don't have more specific test methods already
                if not any(test_id.startswith(f"{test_name}#") for test_id in failed_tests):
                    failed_tests.add(test_name)
                
        # Look for individual test failures in error messages
        individual_failures = re.findall(r"(?:Failure|Error) in (.+?)(?::|$)", test_log)
        for failure in individual_failures:
            failure = failure.strip()
            # Only add if we don't have this test already
            if failure not in failed_tests and not any(test_id.startswith(f"{failure}#") for test_id in failed_tests):
                failed_tests.add(failure)
            
        # If we have no test results at all but the build completed, add a placeholder
        if len(passed_tests) == 0 and len(failed_tests) == 0 and len(skipped_tests) == 0:
            if "BUILD SUCCESS" in test_log:
                passed_tests.add("JenkinsTests")
            elif "BUILD FAILURE" in test_log:
                failed_tests.add("JenkinsTests")

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )