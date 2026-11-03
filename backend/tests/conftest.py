import pytest


def pytest_addoption(parser):
    parser.addoption("--fail-on-skip", action="store_true", help="Fail if a selected test is skipped or xfailed.")


def pytest_configure(config):
    if config.getoption("--fail-on-skip"):
        config.pluginmanager.register(FailOnSkip())


class FailOnSkip:
    def __init__(self):
        self.skipped = set()

    def record(self, report):
        if report.skipped:
            self.skipped.add(report.nodeid)

    pytest_collectreport = record
    pytest_runtest_logreport = record

    def pytest_sessionfinish(self, session, exitstatus):
        if self.skipped and exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
            reporter = session.config.pluginmanager.get_plugin("terminalreporter")
            if reporter is not None:
                reporter.write_line("Skipped or xfailed tests: " + ", ".join(sorted(self.skipped)))
