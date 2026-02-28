import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JAVA_REPOS_DIR = REPO_ROOT / "multi_swe_bench" / "harness" / "repos" / "java"

OLD_PATTERNS = (
    "mvn clean test -Dstyle.color=never || true",
    "mvn clean test -fn || true",
    "mvn clean test -fae || true",
    "mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false || true",
    "mvn clean test -Dsurefire.useFile=false -Dmaven.test.skip=false -DfailIfNoTests=false || true",
    "./mvnw -V --no-transfer-progress -Pgen-javadoc -Pgen-dokka clean package -Dsurefire.useFile=false -Dmaven.test.skip=false -DfailIfNoTests=false || true",
)


class MavenPrepareWarmupTests(unittest.TestCase):
    def test_old_maven_warmup_commands_removed(self):
        offenders = []
        for path in JAVA_REPOS_DIR.rglob("*.py"):
            text = path.read_text()
            if any(pattern in text for pattern in OLD_PATTERNS):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual([], offenders)

    def test_new_maven_warmup_command_exists(self):
        holders = []
        for path in JAVA_REPOS_DIR.rglob("*.py"):
            text = path.read_text()
            if "mvn clean test-compile" in text or "maven.test.skip=true" in text:
                holders.append(str(path.relative_to(REPO_ROOT)))
        self.assertNotEqual([], holders)


if __name__ == "__main__":
    unittest.main()
