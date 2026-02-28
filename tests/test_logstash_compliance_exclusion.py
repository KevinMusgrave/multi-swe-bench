import unittest

from multi_swe_bench.harness.dataset import (
    Dataset,
    LOGSTASH_RSPEC_COMPLIANCE_TEST,
)
from multi_swe_bench.harness.pull_request import Base
from multi_swe_bench.harness.report import Report
from multi_swe_bench.harness.test_result import Test, TestResult, TestStatus

BASE_TEST = "org.logstash.BaseTest > baseTest"
STABLE_PASS = "org.logstash.StableTest > stablePass"
REAL_FIX = "org.logstash.RealFixTest > fixesBug"
TASK_NAME = "logstash-core:compileJava"


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
    run_result = build_test_result(passed={BASE_TEST})
    test_result = build_test_result(passed={BASE_TEST})
    fix_result = build_test_result(passed={BASE_TEST})

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
            BASE_TEST: Test(TestStatus.PASS, TestStatus.PASS, TestStatus.PASS),
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
        self.assertIn(BASE_TEST, dataset.p2p_tests)

    def test_dataset_keeps_compliance_for_other_repos(self):
        dataset = build_base_dataset(org="acme", repo="service")
        self.assertIn(LOGSTASH_RSPEC_COMPLIANCE_TEST, dataset.p2p_tests)

    def test_report_ignores_logstash_compliance_regression(self):
        # Without the logstash-specific exclusion, this should fail due to
        # PASS->FAIL on rspecTests[compliance]. With the exclusion, a real
        # f2p fix keeps the report valid.
        run_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, STABLE_PASS}
        )
        test_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, STABLE_PASS},
            failed={REAL_FIX},
        )
        fix_result = build_test_result(
            passed={STABLE_PASS, REAL_FIX},
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
        self.assertIn(REAL_FIX, report.fixed_tests)
        self.assertNotIn(LOGSTASH_RSPEC_COMPLIANCE_TEST, report.p2p_tests)

    def test_report_still_flags_non_logstash_regression(self):
        run_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, STABLE_PASS}
        )
        test_result = build_test_result(
            passed={LOGSTASH_RSPEC_COMPLIANCE_TEST, STABLE_PASS},
            failed={REAL_FIX},
        )
        fix_result = build_test_result(
            passed={STABLE_PASS, REAL_FIX},
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

    def test_report_ignores_logstash_task_regression(self):
        run_result = build_test_result(passed={TASK_NAME, STABLE_PASS})
        test_result = build_test_result(
            passed={TASK_NAME, STABLE_PASS},
            failed={REAL_FIX},
        )
        fix_result = build_test_result(
            passed={STABLE_PASS, REAL_FIX},
            failed={TASK_NAME},
        )

        report = Report(
            org="elastic",
            repo="logstash",
            number=4,
            run_result=run_result,
            test_patch_result=test_result,
            fix_patch_result=fix_result,
        )

        self.assertTrue(report.valid)
        self.assertEqual("", report.error_msg)
        self.assertNotIn(TASK_NAME, report.p2p_tests)
        self.assertIn(REAL_FIX, report.fixed_tests)

    def test_report_still_flags_non_logstash_task_regression(self):
        run_result = build_test_result(passed={TASK_NAME, STABLE_PASS})
        test_result = build_test_result(
            passed={TASK_NAME, STABLE_PASS},
            failed={REAL_FIX},
        )
        fix_result = build_test_result(
            passed={STABLE_PASS, REAL_FIX},
            failed={TASK_NAME},
        )

        report = Report(
            org="acme",
            repo="service",
            number=4,
            run_result=run_result,
            test_patch_result=test_result,
            fix_patch_result=fix_result,
        )

        self.assertFalse(report.valid)
        self.assertIn("Before applying the fix patch", report.error_msg)
        self.assertIn(TASK_NAME, report.error_msg)

    def test_dataset_filters_non_test_entries_for_logstash(self):
        run_result = build_test_result(passed={BASE_TEST, TASK_NAME})
        test_result = build_test_result(passed={BASE_TEST, TASK_NAME})
        fix_result = build_test_result(passed={BASE_TEST, TASK_NAME})

        dataset = Dataset(
            org="elastic",
            repo="logstash",
            number=3,
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
            fixed_tests={
                BASE_TEST: Test(TestStatus.PASS, TestStatus.FAIL, TestStatus.PASS),
                TASK_NAME: Test(TestStatus.PASS, TestStatus.PASS, TestStatus.PASS),
            },
            p2p_tests={
                BASE_TEST: Test(TestStatus.PASS, TestStatus.PASS, TestStatus.PASS),
                TASK_NAME: Test(TestStatus.PASS, TestStatus.PASS, TestStatus.PASS),
            },
            f2p_tests={
                BASE_TEST: Test(TestStatus.PASS, TestStatus.FAIL, TestStatus.PASS),
                TASK_NAME: Test(TestStatus.PASS, TestStatus.FAIL, TestStatus.PASS),
            },
            s2p_tests={TASK_NAME: Test(TestStatus.PASS, TestStatus.SKIP, TestStatus.PASS)},
            n2p_tests={TASK_NAME: Test(TestStatus.PASS, TestStatus.NONE, TestStatus.PASS)},
            run_result=run_result,
            test_patch_result=test_result,
            fix_patch_result=fix_result,
        )

        self.assertIn(BASE_TEST, dataset.p2p_tests)
        self.assertNotIn(TASK_NAME, dataset.p2p_tests)
        self.assertNotIn(TASK_NAME, dataset.f2p_tests)
        self.assertNotIn(TASK_NAME, dataset.s2p_tests)
        self.assertNotIn(TASK_NAME, dataset.n2p_tests)
        self.assertNotIn(TASK_NAME, dataset.fixed_tests)


if __name__ == "__main__":
    unittest.main()
