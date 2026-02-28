import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JAVA_REPOS_DIR = REPO_ROOT / "multi_swe_bench" / "harness" / "repos" / "java"
OLD = "./gradlew clean test --continue || true"
NEW = "./gradlew --no-daemon clean testClasses || true"
EXPECTED_FILES = {
    "multi_swe_bench/harness/repos/java/elastic/logstash.py",
    "multi_swe_bench/harness/repos/java/googlecontainertools/jib.py",
    "multi_swe_bench/harness/repos/java/junitteam/junit5.py",
    "multi_swe_bench/harness/repos/java/spotbugs/spotbugs.py",
}


class GradlePrepareWarmupTests(unittest.TestCase):
    def test_old_prepare_warmup_command_removed(self):
        offenders = []
        for path in JAVA_REPOS_DIR.rglob("*.py"):
            if OLD in path.read_text():
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual([], offenders)

    def test_new_prepare_warmup_command_only_in_expected_files(self):
        holders = set()
        for path in JAVA_REPOS_DIR.rglob("*.py"):
            if NEW in path.read_text():
                holders.add(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(EXPECTED_FILES, holders)


if __name__ == "__main__":
    unittest.main()
