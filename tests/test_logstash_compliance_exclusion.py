import unittest

from multi_swe_bench.harness.dataset import (
    Dataset,
    LOGSTASH_RSPEC_COMPLIANCE_TEST,
)
from multi_swe_bench.harness.pull_request import Base
from multi_swe_bench.harness.report import Report
from multi_swe_bench.harness.test_result import Test, TestResult, TestStatus


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


def build_base_dataset(*, org: str, repo: str):
    run_result = build_test_result(passed={"base-test"})
    test_result = build_test_result(passed={"base-test"})
    fix_result = build_test_result(passed={"base-test"})

    return Dataset(
        org=org,
        repo=repo,
        number=1,
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
        p2p_tests={
            "base-test": Test(TestStatus.PASS, TestStatus.PASS, TestStatus.PASS),
            LOGSTASH_RSPEC_COMPLIANCE_TEST: Test(
                TestStatus.PASS, TestStatus.PASS, TestStatus.FAIL
            ),
        },
        f2p_tests={},
        s2p_tests={},
        n2p_tests={},
        run_result=run_result,
        test_patch_result=test_result,
        fix_patch_result=fix_result,
    )


class LogstashComplianceExclusionTests(unittest.TestCase):
    def test_dataset_removes_logstash_compliance_from_p2p(self):
        dataset = build_base_dataset(org="elastic", repo="logstash")
        self.assertNotIn(LOGSTASH_RSPEC_COMPLIANCE_TEST, dataset.p2p_tests)
        self.assertIn("base-test", dataset.p2p_tests)

    def test_dataset_keeps_compliance_for_other_repos(self):
        dataset = build_base_dataset(org="acme", repo="service")
        self.assertIn(LOGSTASH_RSPEC_COMPLIANCE_TEST, dataset.p2p_tests)

    def test_report_ignores_logstash_compliance_regression(self):
        # Without the logstash-specific exclusion, this should fail due to
        # PASS->FAIL on rspecTests[compliance]. With the exclusion, a real
        # f2p fix keeps the report valid.
        run_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, "stable-pass"}
        )
        test_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, "stable-pass"},
            failed={"real-fix"},
        )
        fix_result = build_test_result(
            passed={"stable-pass", "real-fix"},
            failed={LOGSTASH_RSPEC_COMPLIANCE_TEST},
        )

        report = Report(
            org="elastic",
            repo="logstash",
            number=2,
            run_result=run_result,
            test_patch_result=test_result,
            fix_patch_result=fix_result,
        )

        self.assertTrue(report.valid)
        self.assertEqual("", report.error_msg)
        self.assertIn("real-fix", report.fixed_tests)
        self.assertNotIn(LOGSTASH_RSPEC_COMPLIANCE_TEST, report.p2p_tests)

    def test_report_still_flags_non_logstash_regression(self):
        run_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, "stable-pass"}
        )
        test_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, "stable-pass"},
            failed={"real-fix"},
        )
        fix_result = build_test_result(
            passed={"stable-pass", "real-fix"},
            failed={LOGSTASH_RSPEC_COMPLIANCE_TEST},
        )

        report = Report(
            org="acme",
            repo="service",
            number=2,
            run_result=run_result,
            test_patch_result=test_result,
            fix_patch_result=fix_result,
        )

        self.assertFalse(report.valid)
        self.assertIn("Before applying the fix patch", report.error_msg)
        self.assertIn(LOGSTASH_RSPEC_COMPLIANCE_TEST, report.error_msg)


if __name__ == "__main__":
    unittest.main()
