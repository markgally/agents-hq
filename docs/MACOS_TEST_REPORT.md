# Mac installation validation — 2026-11-26

Environment: Apple Silicon Mac, macOS 27.0.1, private CPython 3.14.10.

## Mac-specific regression checks

```bash
.runtime/python/bin/python3 -m unittest tests.test_macos_launcher -v
```

**13 tests passed.** Checks cover:

- Fresh app copy with executable permission repair, installation pointers, and
  Applications/Desktop shortcuts from a path containing spaces and an apostrophe.
- Dock pin creation, relocation, duplicate removal, preservation of unrelated
  entries/order, and avoiding a Dock restart when the existing pin is correct.
- Real `defaults` property-list serialization against a temporary domain;
  the user's real Dock is not changed by tests.
- A checksum-rejected download leaving an existing private runtime intact.
- Refusing to stop unrelated listeners or processes after PID reuse.
- A real isolated server starting without a terminal, reopening without creating
  a second server, stopping only its owned process, and restarting immediately.
- The installed `.app` launched through macOS LaunchServices actually starting a
  fresh background server, rather than merely accepting an `open` request.

The private runtime was downloaded by `macos/bootstrap.sh` and its pinned SHA-256
was verified before extraction. Apple Silicon execution was tested here. The
Intel download URL and digest were checked against the same upstream release,
but an Intel Mac was not available for execution testing.

Shell syntax checks, Python compilation, and `git diff --check` passed. App and
command entry points are tracked as executable files; runtime downloads and local
installation pointers are excluded from git.

## Initial backend suite (before the relative-path fix)

```bash
.runtime/python/bin/python3 -m unittest discover -s tests -v
```

**124 tests ran: 123 passed, 1 failed.** The failure is the existing
`test_security.PathPolicyTests.test_traversal_and_outside_paths_are_rejected`
assertion for the Windows-style string `..\outside\other.txt` on macOS. Running
that same test against an exported, unchanged `origin/main` at `68530b4` reproduced
the failure. The recovered security bytecode and that test are unchanged by the
Mac installation fix.

The prior lifecycle-event test passed in this run. No claim is made that its
previous timing-dependent failure was fixed by these installation changes.

Windows launchers and the recovered backend bytecode are unchanged. Linux retains its direct Python entry point and a console fallback in `start.command`. Brief generation, read-aloud integrations,
agent state, authentication, and source records are outside this change.

## Follow-up: relative-path portability fixed

The remaining assertion is resolved by the source facade in `agent_hq/security.py`:
relative backslashes are normalized before the recovered policy's existing
absolute-path, drive/UNC, realpath and working-folder boundary checks. The original
`security.pyc` remains unchanged and required.

Validation after this fix:

- **29 security tests passed**, including the original failing assertion,
  Windows/mixed-separator escapes, valid nested paths and symlink escapes.
- **127 tests passed** in the complete backend and Mac regression suite:
  `.runtime/python/bin/python3 -m unittest discover -s tests -v`.

The three added tests cover valid separator variants, portable escape rejection,
and invalid path inputs. Existing symlink and HTTP attachment tests also check
backslash/mixed-separator escapes. The earlier 124-test result above is retained
as the pre-fix baseline, not the current result.
