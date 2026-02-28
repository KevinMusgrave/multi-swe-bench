import logging
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from multi_swe_bench.harness.dataset import (
    Dataset,
    LOGSTASH_RSPEC_COMPLIANCE_TEST,
)
from multi_swe_bench.harness.pull_request import Base
from multi_swe_bench.harness.test_result import Test, TestResult, TestStatus

BASE_TEST = "org.logstash.BaseTest > baseTest"
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


def _build_dataset(
    *,
    org: str,
    repo: str,
    number: int,
    p2p_names: list[str],
    f2p_names: list[str],
) -> Dataset:
    all_names = set(p2p_names) | set(f2p_names)
    run_result = build_test_result(passed=all_names)
    failed_in_test_patch = set(f2p_names)
    passed_in_test_patch = set(p2p_names) - failed_in_test_patch
    test_result = build_test_result(
        passed=passed_in_test_patch,
        failed=failed_in_test_patch,
    )
    fix_result = build_test_result(passed=all_names)

    return Dataset(
        org=org,
        repo=repo,
        number=number,
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
            name: Test(TestStatus.PASS, TestStatus.PASS, TestStatus.PASS)
            for name in p2p_names
        },
        f2p_tests={
            name: Test(TestStatus.PASS, TestStatus.FAIL, TestStatus.PASS)
            for name in f2p_names
        },
        s2p_tests={},
        n2p_tests={},
        run_result=run_result,
        test_patch_result=test_result,
        fix_patch_result=fix_result,
    )


def _get_run_evaluation_types():
    module_name = "multi_swe_bench.harness.run_evaluation"
    if module_name in sys.modules:
        module = sys.modules[module_name]
    else:
        with patch("docker.from_env", return_value=Mock()):
            module = importlib.import_module(module_name)
    return module.CliArgs, module.Patch


def _build_cli_args(workdir: Path, dataset: Dataset, fix_patch_run_cmd: str):
    CliArgs, Patch = _get_run_evaluation_types()
    args = object.__new__(CliArgs)
    args.workdir = workdir
    args.patch_files = ["dummy.patch.jsonl"]
    args.dataset_files = ["dummy.dataset.jsonl"]
    args.fix_patch_run_cmd = fix_patch_run_cmd
    args.human_mode = True
    args.global_env = None
    args.timeout = 60
    logger = logging.getLogger("test_required_tests_wiring")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    args._logger = logger
    args._dataset = {dataset.id: dataset}
    args._patches = {
        dataset.id: Patch(
            org=dataset.org,
            repo=dataset.repo,
            number=dataset.number,
            fix_patch="diff --git a/file b/file\n",
        )
    }
    return args


class _DummyImage:
    def __init__(self, number: int):
        self._number = number

    def workdir(self) -> str:
        return f"pr-{self._number}"

    def fix_patch_path(self) -> str:
        return "/home/fix.patch"

    def image_full_name(self) -> str:
        return "dummy-image"


class _DummyInstance:
    def __init__(self, pr: Dataset):
        self.pr = pr
        self._image = _DummyImage(pr.number)
        self.required_tests_seen: list[str] | None = None
        self.fix_patch_run_cmd_seen: str | None = None

    def dependency(self) -> _DummyImage:
        return self._image

    def name(self) -> str:
        return self._image.image_full_name()

    def fix_patch_run_with_required_tests(
        self, required_tests: list[str], fix_patch_run_cmd: str = ""
    ) -> str:
        self.required_tests_seen = required_tests
        self.fix_patch_run_cmd_seen = fix_patch_run_cmd
        return "echo run-fix"


class RequiredTestsWiringTests(unittest.TestCase):
    def test_run_instance_uses_filtered_required_tests_for_logstash(self):
        dataset = _build_dataset(
            org="elastic",
            repo="logstash",
            number=11,
            p2p_names=[BASE_TEST, LOGSTASH_RSPEC_COMPLIANCE_TEST, TASK_NAME],
            f2p_names=[REAL_FIX, TASK_NAME],
        )
        expected_required_tests = sorted(
            set(dataset.p2p_tests.keys()) | set(dataset.f2p_tests.keys())
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            args = _build_cli_args(Path(temp_dir), dataset, fix_patch_run_cmd="")
            instance = _DummyInstance(dataset)

            with patch(
                "multi_swe_bench.harness.run_evaluation.docker_util.run",
                return_value=("ok", False),
            ) as docker_run:
                args.run_instance(instance)

            self.assertEqual(expected_required_tests, instance.required_tests_seen)
            self.assertNotIn(
                LOGSTASH_RSPEC_COMPLIANCE_TEST, instance.required_tests_seen
            )
            self.assertNotIn(TASK_NAME, instance.required_tests_seen)

            docker_run.assert_called_once()
            self.assertEqual("echo run-fix", docker_run.call_args.args[1])
            self.assertEqual("", instance.fix_patch_run_cmd_seen)

            instance_dir = (
                Path(temp_dir)
                / "elastic"
                / "logstash"
                / "evals"
                / f"pr-{dataset.number}"
            )
            fix_patch_file = instance_dir / "fix.patch"
            self.assertTrue(fix_patch_file.exists())
            self.assertEqual("diff --git a/file b/file\n", fix_patch_file.read_text())

    def test_run_instance_uses_union_and_dedup_for_non_logstash(self):
        p2p_names = ["z.test > keepAlive", "a.test > alpha"]
        f2p_names = ["a.test > alpha", "b.test > beta"]
        dataset = _build_dataset(
            org="acme",
            repo="service",
            number=12,
            p2p_names=p2p_names,
            f2p_names=f2p_names,
        )
        expected_required_tests = sorted(set(p2p_names) | set(f2p_names))

        with tempfile.TemporaryDirectory() as temp_dir:
            args = _build_cli_args(
                Path(temp_dir), dataset, fix_patch_run_cmd="custom-fix-cmd"
            )
            instance = _DummyInstance(dataset)

            with patch(
                "multi_swe_bench.harness.run_evaluation.docker_util.run",
                return_value=("ok", False),
            ) as docker_run:
                args.run_instance(instance)

            self.assertEqual(expected_required_tests, instance.required_tests_seen)
            self.assertEqual("custom-fix-cmd", instance.fix_patch_run_cmd_seen)
            docker_run.assert_called_once()
            self.assertEqual("echo run-fix", docker_run.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
