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
