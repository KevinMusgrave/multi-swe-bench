import unittest

from multi_swe_bench.harness.dataset import Dataset
from multi_swe_bench.harness.image import Config
from multi_swe_bench.harness.pull_request import Base
from multi_swe_bench.harness.repos.java.elastic.logstash import Logstash
from multi_swe_bench.harness.test_result import TestResult


def build_test_result(*, passed=None, failed=None, skipped=None):
    passed = set(passed or [])
    failed = set(failed or [])
    skipped = set(skipped or [])
    return TestResult(
        passed_count=len(passed),
        failed_count=len(failed),
        skipped_count=len(skipped),
        passed_tests=passed,
        failed_tests=failed,
        skipped_tests=skipped,
    )


def build_logstash_dataset() -> Dataset:
    test_name = "org.logstash.StableTest > stablePass"
    run_result = build_test_result(passed={test_name})
    test_result = build_test_result(passed={test_name})
    fix_result = build_test_result(passed={test_name})

    return Dataset(
        org="elastic",
        repo="logstash",
        number=99,
        state="open",
        title="t",
        body="",
        base=Base(label="", ref="", sha=""),
        resolved_issues=[],
        fix_patch="",
        test_patch="",
        tag="",
        number_interval="",
        lang="java",
        fixed_tests={},
        p2p_tests={},
        f2p_tests={},
        s2p_tests={},
        n2p_tests={},
        run_result=run_result,
        test_patch_result=test_result,
        fix_patch_result=fix_result,
    )


class LogstashRequiredTestCommandTests(unittest.TestCase):
    def test_builds_targeted_fix_command_from_required_tests(self):
        dataset = build_logstash_dataset()
        instance = Logstash(
            dataset,
            Config(need_clone=False, global_env=None, clear_env=False),
        )
        required_tests = [
            "org.logstash.StableTest > stablePass",
            "org.logstash.OtherTest > handlesValue[1]",
            "logstash-core:compileJava",  # should be ignored
        ]

        command = instance.fix_patch_run_with_required_tests(
            required_tests,
            fix_patch_run_cmd="",
        )

        self.assertIn("patch --batch --fuzz=5", command)
        self.assertIn("--tests", command)
        self.assertIn("org.logstash.StableTest.stablePass", command)
        self.assertIn("org.logstash.OtherTest.handlesValue[1]", command)
        self.assertNotIn("logstash-core:compileJava", command)

    def test_falls_back_when_no_required_test_cases(self):
        dataset = build_logstash_dataset()
        instance = Logstash(
            dataset,
            Config(need_clone=False, global_env=None, clear_env=False),
        )

        fallback = instance.fix_patch_run_with_required_tests(
            ["logstash-core:compileJava"],
            fix_patch_run_cmd="custom-command",
        )
        self.assertEqual("custom-command", fallback)


if __name__ == "__main__":
    unittest.main()
