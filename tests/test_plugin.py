import pytest

TEST_FILE = """
    from pytest_ratchet import Finding

    def test_dead_code(ratchet):
        ratchet.check("vulture", [
            Finding(kind="unused-function", key="a.py::function::f",
                    message="unused function", line=3),
        ])
"""


def test_green_run_prints_summary(pytester):
    pytester.makefile(
        ".toml",
        **{
            "ratchet-baseline": (
                '[vulture]\n[[vulture.entry]]\nkey = "a.py::function::f"\nreason = "kept"\n'
            )
        },
    )
    pytester.makepyfile(TEST_FILE)
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*ratchet*", "section [[]vulture[]]: 1 entry OK"])


def test_new_finding_fails_the_test(pytester):
    pytester.makepyfile(TEST_FILE)  # no baseline file at all
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*RATCHET: 1 problem in section [[]vulture[]]*",
            "*NEW*",
            "*a.py::function::f*",
            "*run `ratchet init`*",
        ]
    )


def test_stale_entry_fails_the_test(pytester):
    pytester.makefile(
        ".toml",
        **{
            "ratchet-baseline": (
                '[vulture]\n'
                '[[vulture.entry]]\nkey = "a.py::function::f"\nreason = "kept"\n'
                '[[vulture.entry]]\nkey = "b.py::function::gone"\nreason = "TODO"\n'
            )
        },
    )
    pytester.makepyfile(TEST_FILE)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*STALE*", "*b.py::function::gone*", '*reason was: "TODO"*'])


def test_malformed_baseline_fails_the_test(pytester):
    pytester.makefile(
        ".toml",
        **{"ratchet-baseline": '[vulture]\n[[vulture.entry]]\nkey = "k"\nreasn = "typo"\n'},
    )
    pytester.makepyfile(TEST_FILE)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*malformed baseline*", "*unknown fields*reasn*"])


def test_strict_todo_ini_option(pytester):
    pytester.makefile(
        ".toml",
        **{
            "ratchet-baseline": (
                '[vulture]\n[[vulture.entry]]\nkey = "a.py::function::f"\nreason = "TODO"\n'
            )
        },
    )
    pytester.makeini("[pytest]\nratchet_strict_todo = true\n")
    pytester.makepyfile(TEST_FILE)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*strict_todo is enabled*"])


def test_custom_baseline_path(pytester):
    pytester.makefile(
        ".toml",
        **{
            "custom-name": (
                '[vulture]\n[[vulture.entry]]\nkey = "a.py::function::f"\nreason = "kept"\n'
            )
        },
    )
    pytester.makeini("[pytest]\nratchet_baseline = custom-name.toml\n")
    pytester.makepyfile(TEST_FILE)
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


# --- v0.2: ticket tracker via ini -------------------------------------------

TRACKER_STUB = """
    ANSWERS = {}
    TIMEOUTS = []

    class Stub:
        def is_open(self, ticket_id):
            return ANSWERS.get(ticket_id)
        def explain(self, ticket_id):
            return "stubbed"

    def make(timeout=None):
        TIMEOUTS.append(timeout)
        return Stub()

    def make_without_timeout():
        return Stub()

    not_a_factory = 42
"""

TICKET_BASELINE = (
    '[vulture]\n[[vulture.entry]]\nkey = "a.py::function::f"\n'
    'reason = "DAC-1: waiting for the parser"\n'
)


def _ticket_project(pytester, answers: str, ini_extra: str = "", factory: str = "tracker_stub:make"):
    pytester.makepyfile(tracker_stub=TRACKER_STUB.replace("ANSWERS = {}", f"ANSWERS = {answers}"))
    pytester.syspathinsert()
    pytester.makefile(".toml", **{"ratchet-baseline": TICKET_BASELINE})
    pytester.makeini(f"[pytest]\nratchet_ticket_tracker = {factory}\n{ini_extra}")
    pytester.makepyfile(test_guard=TEST_FILE)


def test_ticket_open_is_green_and_summarised(pytester):
    _ticket_project(pytester, "{'DAC-1': True}")
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["section [[]vulture[]]: 1 entry OK, 1 ticket checked"])


def test_ticket_closed_fails_the_test(pytester):
    _ticket_project(pytester, "{'DAC-1': False}")
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        ["*CLOSED_TICKET*reopen the ticket*", "*a.py::function::f   DAC-1 is closed (stubbed)*"]
    )


def test_ticket_unknown_is_visible_but_green_by_default(pytester):
    _ticket_project(pytester, "{}")
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*1 ticket checked (1 unresolved)*"])


def test_ticket_unknown_is_red_under_strict_ini(pytester):
    _ticket_project(pytester, "{}", ini_extra="ratchet_ticket_strict = true\n")
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*UNRESOLVED_TICKET (strict_tickets is enabled*", "*DAC-1   (stubbed)*"])


def test_ticket_timeout_ini_reaches_factories_that_accept_it(pytester):
    _ticket_project(pytester, "{'DAC-1': True}", ini_extra="ratchet_ticket_timeout = 3\n")
    pytester.makepyfile(
        test_zz_timeout="""
        import tracker_stub
        def test_timeout_recorded():
            assert tracker_stub.TIMEOUTS == [3.0]
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=2)


def test_ticket_factory_without_timeout_parameter_is_fine(pytester):
    _ticket_project(pytester, "{'DAC-1': True}", factory="tracker_stub:make_without_timeout")
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def test_ticket_pattern_ini(pytester):
    # A different id shape than the default (which would not match "GH12").
    # Note: '#' cannot be used here — it starts a comment in ini files.
    _ticket_project(pytester, "{'GH12': False}", ini_extra="ratchet_ticket_pattern = GH\\d+\n")
    pytester.makefile(
        ".toml",
        **{"ratchet-baseline": '[vulture]\n[[vulture.entry]]\nkey = "a.py::function::f"\nreason = "GH12: gh"\n'},
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*GH12 is closed*"])


@pytest.mark.parametrize(
    "factory,expected",
    [
        ("tracker_stub", "*must be 'module:callable'*"),
        ("no_such_module:make", "*cannot import ticket tracker module 'no_such_module'*"),
        ("tracker_stub:missing", "*has no attribute 'missing'*"),
        ("tracker_stub:not_a_factory", "*has no is_open(ticket_id) method*"),
    ],
)
def test_ticket_tracker_misconfiguration_fails_loudly(pytester, factory, expected):
    _ticket_project(pytester, "{}", factory=factory)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([expected])
