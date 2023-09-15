import os
import random
import re
import sys
import time

from test import support
from test.support import os_helper

from .cmdline import _parse_args, Namespace
from .findtests import findtests, split_test_packages, list_cases
from .logger import Logger
from .result import State
from .runtests import RunTests, HuntRefleak
from .setup import setup_process, setup_test_dir
from .single import run_single_test, PROGRESS_MIN_TIME
from .pgo import setup_pgo_tests
from .results import TestResults
from .utils import (
    StrPath, StrJSON, TestName, TestList, TestTuple, FilterTuple,
    strip_py_suffix, count, format_duration,
    printlist, get_temp_dir, get_work_dir, exit_timeout,
    display_header, cleanup_temp_dir)


class Regrtest:
    """Execute a test suite.

    This also parses command-line options and modifies its behavior
    accordingly.

    tests -- a list of strings containing test names (optional)
    testdir -- the directory in which to look for tests (optional)

    Users other than the Python test suite will certainly want to
    specify testdir; if it's omitted, the directory containing the
    Python test suite is searched for.

    If the tests argument is omitted, the tests listed on the
    command-line will be used.  If that's empty, too, then all *.py
    files beginning with test_ will be used.

    The other default arguments (verbose, quiet, exclude,
    single, randomize, use_resources, trace, coverdir,
    print_slow, and random_seed) allow programmers calling main()
    directly to set the values that would normally be set by flags
    on the command line.
    """
    def __init__(self, ns: Namespace):
        # Log verbosity
        self.verbose: int = int(ns.verbose)
        self.quiet: bool = ns.quiet
        self.pgo: bool = ns.pgo
        self.pgo_extended: bool = ns.pgo_extended

        # Test results
        self.results: TestResults = TestResults()
        self.first_state: str | None = None

        # Logger
        self.logger = Logger(self.results, self.quiet, self.pgo)

        # Actions
        self.want_header: bool = ns.header
        self.want_list_tests: bool = ns.list_tests
        self.want_list_cases: bool = ns.list_cases
        self.want_wait: bool = ns.wait
        self.want_cleanup: bool = ns.cleanup
        self.want_rerun: bool = ns.rerun
        self.want_run_leaks: bool = ns.runleaks

        # Select tests
        if ns.match_tests:
            self.match_tests: FilterTuple | None = tuple(ns.match_tests)
        else:
            self.match_tests = None
        if ns.ignore_tests:
            self.ignore_tests: FilterTuple | None = tuple(ns.ignore_tests)
        else:
            self.ignore_tests = None
        self.exclude: bool = ns.exclude
        self.fromfile: StrPath | None = ns.fromfile
        self.starting_test: TestName | None = ns.start
        self.cmdline_args: TestList = ns.args

        # Workers
        if ns.use_mp is None:
            num_workers = 0  # run sequentially
        elif ns.use_mp <= 0:
            num_workers = -1  # use the number of CPUs
        else:
            num_workers = ns.use_mp
        self.num_workers: int = num_workers
        self.worker_json: StrJSON | None = ns.worker_json

        # Options to run tests
        self.fail_fast: bool = ns.failfast
        self.fail_env_changed: bool = ns.fail_env_changed
        self.fail_rerun: bool = ns.fail_rerun
        self.forever: bool = ns.forever
        self.randomize: bool = ns.randomize
        self.random_seed: int | None = ns.random_seed
        self.output_on_failure: bool = ns.verbose3
        self.timeout: float | None = ns.timeout
        if ns.huntrleaks:
            warmups, runs, filename = ns.huntrleaks
            filename = os.path.abspath(filename)
            self.hunt_refleak: HuntRefleak | None = HuntRefleak(warmups, runs, filename)
        else:
            self.hunt_refleak = None
        self.test_dir: StrPath | None = ns.testdir
        self.junit_filename: StrPath | None = ns.xmlpath
        self.memory_limit: str | None = ns.memlimit
        self.gc_threshold: int | None = ns.threshold
        self.use_resources: tuple[str, ...] = tuple(ns.use_resources)
        if ns.python:
            self.python_cmd: tuple[str, ...] | None = tuple(ns.python)
        else:
            self.python_cmd = None
        self.coverage: bool = ns.trace
        self.coverage_dir: StrPath | None = ns.coverdir
        self.tmp_dir: StrPath | None = ns.tempdir

        # tests
        self.first_runtests: RunTests | None = None

        # used by --slowest
        self.print_slowest: bool = ns.print_slow

        # used to display the progress bar "[ 3/100]"
        self.start_time = time.perf_counter()

        # used by --single
        self.single_test_run: bool = ns.single
        self.next_single_test: TestName | None = None
        self.next_single_filename: StrPath | None = None

    def log(self, line=''):
        self.logger.log(line)

    def find_tests(self, tests: TestList | None = None) -> tuple[TestTuple, TestList | None]:
        if self.single_test_run:
            self.next_single_filename = os.path.join(self.tmp_dir, 'pynexttest')
            try:
                with open(self.next_single_filename, 'r') as fp:
                    next_test = fp.read().strip()
                    tests = [next_test]
            except OSError:
                pass

        if self.fromfile:
            tests = []
            # regex to match 'test_builtin' in line:
            # '0:00:00 [  4/400] test_builtin -- test_dict took 1 sec'
            regex = re.compile(r'\btest_[a-zA-Z0-9_]+\b')
            with open(os.path.join(os_helper.SAVEDCWD, self.fromfile)) as fp:
                for line in fp:
                    line = line.split('#', 1)[0]
                    line = line.strip()
                    match = regex.search(line)
                    if match is not None:
                        tests.append(match.group())

        strip_py_suffix(tests)

        if self.pgo:
            # add default PGO tests if no tests are specified
            setup_pgo_tests(self.cmdline_args, self.pgo_extended)

        exclude_tests = set()
        if self.exclude:
            for arg in self.cmdline_args:
                exclude_tests.add(arg)
            self.cmdline_args = []

        alltests = findtests(testdir=self.test_dir,
                             exclude=exclude_tests)

        if not self.fromfile:
            selected = tests or self.cmdline_args
            if selected:
                selected = split_test_packages(selected)
            else:
                selected = alltests
        else:
            selected = tests

        if self.single_test_run:
            selected = selected[:1]
            try:
                pos = alltests.index(selected[0])
                self.next_single_test = alltests[pos + 1]
            except IndexError:
                pass

        # Remove all the selected tests that precede start if it's set.
        if self.starting_test:
            try:
                del selected[:selected.index(self.starting_test)]
            except ValueError:
                print(f"Cannot find starting test: {self.starting_test}")
                sys.exit(1)

        if self.randomize:
            if self.random_seed is None:
                self.random_seed = random.randrange(100_000_000)
            random.seed(self.random_seed)
            random.shuffle(selected)

        return (tuple(selected), tests)

    @staticmethod
    def list_tests(tests: TestTuple):
        for name in tests:
            print(name)

    def _rerun_failed_tests(self, runtests: RunTests):
        # Configure the runner to re-run tests
        if self.num_workers == 0:
            # Always run tests in fresh processes to have more deterministic
            # initial state. Don't re-run tests in parallel but limit to a
            # single worker process to have side effects (on the system load
            # and timings) between tests.
            self.num_workers = 1

        tests, match_tests_dict = self.results.prepare_rerun()

        # Re-run failed tests
        self.log(f"Re-running {len(tests)} failed tests in verbose mode in subprocesses")
        runtests = runtests.copy(
            tests=tests,
            rerun=True,
            verbose=True,
            forever=False,
            fail_fast=False,
            match_tests_dict=match_tests_dict,
            output_on_failure=False)
        self.logger.set_tests(runtests)
        self._run_tests_mp(runtests, self.num_workers)
        return runtests

    def rerun_failed_tests(self, runtests: RunTests):
        if self.python_cmd:
            # Temp patch for https://github.com/python/cpython/issues/94052
            self.log(
                "Re-running failed tests is not supported with --python "
                "host runner option."
            )
            return

        self.first_state = self.get_state()

        print()
        rerun_runtests = self._rerun_failed_tests(runtests)

        if self.results.bad:
            print(count(len(self.results.bad), 'test'), "failed again:")
            printlist(self.results.bad)

        self.display_result(rerun_runtests)

    def display_result(self, runtests):
        # If running the test suite for PGO then no one cares about results.
        if runtests.pgo:
            return

        state = self.get_state()
        print()
        print(f"== Tests result: {state} ==")

        self.results.display_result(runtests.tests,
                                    self.quiet, self.print_slowest)

    def run_test(self, test_name: TestName, runtests: RunTests, tracer):
        if tracer is not None:
            # If we're tracing code coverage, then we don't exit with status
            # if on a false return value from main.
            cmd = ('result = run_single_test(test_name, runtests)')
            namespace = dict(locals())
            tracer.runctx(cmd, globals=globals(), locals=namespace)
            result = namespace['result']
        else:
            result = run_single_test(test_name, runtests)

        self.results.accumulate_result(result, runtests)

        return result

    def run_tests_sequentially(self, runtests):
        if self.coverage:
            import trace
            tracer = trace.Trace(trace=False, count=True)
        else:
            tracer = None

        save_modules = sys.modules.keys()

        jobs = runtests.get_jobs()
        if jobs is not None:
            tests = count(jobs, 'test')
        else:
            tests = 'tests'
        msg = f"Run {tests} sequentially"
        if runtests.timeout:
            msg += " (timeout: %s)" % format_duration(runtests.timeout)
        self.log(msg)

        previous_test = None
        tests_iter = runtests.iter_tests()
        for test_index, test_name in enumerate(tests_iter, 1):
            start_time = time.perf_counter()

            text = test_name
            if previous_test:
                text = '%s -- %s' % (text, previous_test)
            self.logger.display_progress(test_index, text)

            result = self.run_test(test_name, runtests, tracer)

            # Unload the newly imported modules (best effort finalization)
            for module in sys.modules.keys():
                if module not in save_modules and module.startswith("test."):
                    support.unload(module)

            if result.must_stop(self.fail_fast, self.fail_env_changed):
                break

            previous_test = str(result)
            test_time = time.perf_counter() - start_time
            if test_time >= PROGRESS_MIN_TIME:
                previous_test = "%s in %s" % (previous_test, format_duration(test_time))
            elif result.state == State.PASSED:
                # be quiet: say nothing if the test passed shortly
                previous_test = None

        if previous_test:
            print(previous_test)

        return tracer

    def get_state(self):
        state = self.results.get_state(self.fail_env_changed)
        if self.first_state:
            state = f'{self.first_state} then {state}'
        return state

    def _run_tests_mp(self, runtests: RunTests, num_workers: int) -> None:
        from .run_workers import RunWorkers
        RunWorkers(num_workers, runtests, self.logger, self.results).run()

    def finalize_tests(self, tracer):
        if self.next_single_filename:
            if self.next_single_test:
                with open(self.next_single_filename, 'w') as fp:
                    fp.write(self.next_single_test + '\n')
            else:
                os.unlink(self.next_single_filename)

        if tracer is not None:
            results = tracer.results()
            results.write_results(show_missing=True, summary=True,
                                  coverdir=self.coverage_dir)

        if self.want_run_leaks:
            os.system("leaks %d" % os.getpid())

        if self.junit_filename:
            self.results.write_junit(self.junit_filename)

    def display_summary(self):
        duration = time.perf_counter() - self.logger.start_time
        filtered = bool(self.match_tests) or bool(self.ignore_tests)

        # Total duration
        print()
        print("Total duration: %s" % format_duration(duration))

        self.results.display_summary(self.first_runtests, filtered)

        # Result
        state = self.get_state()
        print(f"Result: {state}")

    def create_run_tests(self, tests: TestTuple):
        return RunTests(
            tests,
            fail_fast=self.fail_fast,
            fail_env_changed=self.fail_env_changed,
            match_tests=self.match_tests,
            ignore_tests=self.ignore_tests,
            match_tests_dict=None,
            rerun=False,
            forever=self.forever,
            pgo=self.pgo,
            pgo_extended=self.pgo_extended,
            output_on_failure=self.output_on_failure,
            timeout=self.timeout,
            verbose=self.verbose,
            quiet=self.quiet,
            hunt_refleak=self.hunt_refleak,
            test_dir=self.test_dir,
            use_junit=(self.junit_filename is not None),
            memory_limit=self.memory_limit,
            gc_threshold=self.gc_threshold,
            use_resources=self.use_resources,
            python_cmd=self.python_cmd,
            randomize=self.randomize,
            random_seed=self.random_seed,
            json_file=None,
        )

    def _run_tests(self, selected: TestTuple, tests: TestList | None) -> int:
        if self.hunt_refleak and self.hunt_refleak.warmups < 3:
            msg = ("WARNING: Running tests with --huntrleaks/-R and "
                   "less than 3 warmup repetitions can give false positives!")
            print(msg, file=sys.stdout, flush=True)

        if self.num_workers < 0:
            # Use all CPUs + 2 extra worker processes for tests
            # that like to sleep
            self.num_workers = (os.cpu_count() or 1) + 2

        # For a partial run, we do not need to clutter the output.
        if (self.want_header
            or not(self.pgo or self.quiet or self.single_test_run
                   or tests or self.cmdline_args)):
            display_header()

        if self.randomize:
            print("Using random seed", self.random_seed)

        runtests = self.create_run_tests(selected)
        self.first_runtests = runtests
        self.logger.set_tests(runtests)

        setup_process()

        self.logger.start_load_tracker()
        try:
            if self.num_workers:
                self._run_tests_mp(runtests, self.num_workers)
                tracer = None
            else:
                tracer = self.run_tests_sequentially(runtests)

            self.display_result(runtests)

            if self.want_rerun and self.results.need_rerun():
                self.rerun_failed_tests(runtests)
        finally:
            self.logger.stop_load_tracker()

        self.display_summary()
        self.finalize_tests(tracer)

        return self.results.get_exitcode(self.fail_env_changed,
                                         self.fail_rerun)

    def run_tests(self, selected: TestTuple, tests: TestList | None) -> int:
        os.makedirs(self.tmp_dir, exist_ok=True)
        work_dir = get_work_dir(self.tmp_dir)

        # Put a timeout on Python exit
        with exit_timeout():
            # Run the tests in a context manager that temporarily changes the
            # CWD to a temporary and writable directory. If it's not possible
            # to create or change the CWD, the original CWD will be used.
            # The original CWD is available from os_helper.SAVEDCWD.
            with os_helper.temp_cwd(work_dir, quiet=True):
                # When using multiprocessing, worker processes will use
                # work_dir as their parent temporary directory. So when the
                # main process exit, it removes also subdirectories of worker
                # processes.
                return self._run_tests(selected, tests)

    def main(self, tests: TestList | None = None):
        if self.junit_filename and not os.path.isabs(self.junit_filename):
            self.junit_filename = os.path.abspath(self.junit_filename)

        strip_py_suffix(self.cmdline_args)

        self.tmp_dir = get_temp_dir(self.tmp_dir)

        if self.want_cleanup:
            cleanup_temp_dir(self.tmp_dir)
            sys.exit(0)

        if self.want_wait:
            input("Press any key to continue...")

        setup_test_dir(self.test_dir)
        selected, tests = self.find_tests(tests)

        exitcode = 0
        if self.want_list_tests:
            self.list_tests(selected)
        elif self.want_list_cases:
            list_cases(selected,
                       match_tests=self.match_tests,
                       ignore_tests=self.ignore_tests,
                       test_dir=self.test_dir)
        else:
            exitcode = self.run_tests(selected, tests)

        sys.exit(exitcode)


def main(tests=None, **kwargs):
    """Run the Python suite."""
    ns = _parse_args(sys.argv[1:], **kwargs)
    Regrtest(ns).main(tests=tests)
