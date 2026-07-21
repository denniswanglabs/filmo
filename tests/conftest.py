"""Shared pytest fixtures for the filmo test suite.

ISOLATION — restore process-global ``os.environ`` around every test.

Several unit tests (and the product code they exercise) mutate ``os.environ``
as a side effect. The decisive offender is ``build_runner.run()``, which stamps
``WS_PREMIUM_MENU=1`` (plus ``PRODUCER_PACE`` / ``HERMES_STYLE`` /
``HERMES_BRAIN`` / ``WS_WALKTHROUGH_NATIVE`` / a default ``PRODUCER_COST_STUB``)
into the environment and never restores them — fine for the real worker, which
is a fresh process per build, but poison inside a single shared pytest process.
``tests/test_build_runner_failure.py::TestRunEndToEnd`` calls ``build_runner.run()``,
so the leaked ``WS_PREMIUM_MENU=1`` flowed into every later-collected test:

  * ``test_orchestrator*`` — orchestrate() shells out to producer.py, which
    inherits the env and takes the premium-menu path -> scene ``decision`` comes
    back as the tier ``'standard'`` instead of approve/downgrade/decline.
  * ``test_producer`` — cmd_estimate() takes the premium price-floor path
    (price floored to 500 instead of the computed value; margin==1 no longer
    yields a null price).

``test_pricing`` was immune only because its own ``setUp`` pops
``WS_PREMIUM_MENU`` — which is exactly why it never appeared in the failing set.

This autouse, function-scoped fixture snapshots the environment before each test
and restores it afterwards (in place, preserving the mapping identity), so no
test can leak env state into the next one. It fixes the CLASS of env-var
cross-contamination rather than patching each leak site. pytest applies autouse
fixtures around ``unittest.TestCase`` methods too, so it covers the whole suite.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _restore_os_environ():
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        # Restore exactly: drop keys a test added, put back any it changed or
        # removed. clear()+update mutates the existing mapping in place so any
        # reference already captured elsewhere still sees the restored values.
        os.environ.clear()
        os.environ.update(snapshot)
