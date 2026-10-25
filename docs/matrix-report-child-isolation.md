# Physical matrix report ownership

While validating the offline prerequisite for open issue #5, an actual native
Linux/Python 3.12 run exposed a separate CI evidence problem: child pytest
processes inherited `CI_MATRIX_REPORT_PATH`. Existing matrix unit tests exercise
mocked OS/version combinations and expected failures, so their mock reporters
appended to the physical runner's JSONL file. A successful native run produced
169 mixed rows even though its uncaptured outer log had seven genuine rows.
Those mock rows cannot prove that another OS or Python version actually ran.

`scripts/run_test_matrix.py` now removes that one reserved output-path setting
from every child environment, including pytest-version and preflight children.
Case variants are also removed because Windows environment names are case
insensitive. Other settings, explicit empty environments, commands and exit codes
are preserved. The parent retains its path and emits each actual M1–M6 result
and ALL aggregate, including real failures. Child tests can still create their
own temporary reports explicitly. This prevents accidental receipt contamination;
it is not a sandbox, protection from hostile filesystem access, or authenticated
execution attestation.

The original #3 research and #4 best-version repair issues are **closed**, with
their source changes already merged. This follow-up does not reopen them or
change prompt selection. It preserves the nine declared native OS/Python jobs,
the actual runtime/version mismatch rejection, and the fail-closed
`test-matrix-required` job-status aggregate. It neither filters stored rows after
execution nor removes any existing test. Research #5 remains inactive.

Focused regression controls run the real existing mocked matrix tests in a child
pytest process and require only the parent's real records to reach its report.
A real deliberately failing temporary child must still produce a nonzero parent
receipt. Additional controls cover all spawn paths, parent/environment ownership,
case variants and explicit empty environments.

```sh
python -m pytest tests/test_matrix_report_isolation.py -q -o addopts=
python scripts/run_test_matrix.py --platform Linux --python-version 3.12
```

The latter command must match the physical host. A local Linux/Python 3.12 pass
does not establish the other eight native cells or the hosted required aggregate.
Each new candidate needs its own exact-head CI evidence; earlier merged contracts
or closed issue status do not certify a new run. No provider calls, credentials,
model canaries, historical evidence rewrites or release authority are added.
