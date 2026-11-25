"""Recovered security helpers with portable relative-path validation.

The original implementation is retained in security.pyc. Load it explicitly so
its validators, error classes, redaction and request gates stay unchanged, then
extend only the relative-path policy in reviewable source. Keep security.pyc:
this facade still requires the release's CPython 3.14 runtime.
"""
from importlib.machinery import SourcelessFileLoader as _BytecodeLoader
from pathlib import Path as _Path

# Execute only the repository's fixed, recovered bytecode in its original module
# namespace. Existing helpers and ApiError retain their public qualified names
# and share the same globals used by the other recovered backend modules.
_loader = _BytecodeLoader(__name__, str(_Path(__file__).with_suffix(".pyc")))
exec(_loader.get_code(__name__), globals())
_RecoveredPathPolicy = PathPolicy


class PathPolicy(_RecoveredPathPolicy):
    def resolve_relative(self, base, relative):
        # Paths arrive from clients and models on either OS. A backslash must
        # not hide '..' or an absolute path from POSIX's native path parser.
        # The recovered policy still checks invalid input, drive/UNC paths,
        # realpath (including symlinks), and confinement to the working folder.
        if isinstance(relative, str):
            relative = relative.replace("\\", "/")
        return super().resolve_relative(base, relative)
