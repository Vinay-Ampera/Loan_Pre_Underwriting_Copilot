"""Safe unpacking of what an officer or an applicant uploads in one go (EDGE_CASES E-42,
SECURITY.md section 6): a zip, the files of a browser folder, or many loose files.

Nothing here writes to disk. `expand` turns the uploaded parts into `Member`s (a label and bytes)
in memory, enforcing every limit while it reads, and the caller then runs the normal upload
checks on each member and stores the accepted ones under generated names. Names are labels only
and never become a path, so an unsafe name cannot write anywhere; unsafe archives are refused
anyway, whole, so that nothing partial is kept.

Refused (`ArchiveError`, the whole upload): a path outside the folder (`..`, absolute, drive
letter, backslash tricks), a symbolic link, a password-protected zip, a zip inside a zip inside a
zip (one nesting level is allowed), more files than the limit, a member or total that grows past
its byte budget while being read, a compression ratio no real document has (a zip bomb).
Skipped quietly: `__MACOSX`, `.DS_Store`, `Thumbs.db`, `desktop.ini`, `._*` resource forks and
folder entries. Allowed extensions only; anything else is reported as skipped with a reason so
the inventory can show it as rejected.
"""

import io
import stat
import zipfile
from dataclasses import dataclass, field

from app.intake.upload import ALLOWED_EXTENSIONS

JUNK_DIRS = {"__macosx", ".git", ".svn"}
JUNK_FILES = {".ds_store", "thumbs.db", "desktop.ini"}
ZIP_MAGIC = b"PK\x03\x04"
CHUNK = 64 * 1024


class ArchiveError(Exception):
    """The upload breaks a safety limit. `message` is plain language for the person uploading."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Limits:
    max_files: int = 60  # members across the whole upload, nested zips included
    max_member_bytes: int = 10 * 1024 * 1024  # one inner file
    max_total_bytes: int = 60 * 1024 * 1024  # everything unpacked, nested zips included
    max_ratio: int = 40  # unpacked bytes per compressed byte, for members past `ratio_floor`
    ratio_floor: int = 1024 * 1024  # tiny members may compress well; only big ones are judged
    max_depth: int = 1  # a zip inside a zip is one level


@dataclass
class Member:
    label: str  # base name, metadata only
    path: str  # the name as sent (folder/sub/file.pdf), for display
    data: bytes


@dataclass
class Skipped:
    label: str
    code: str  # bad_type
    message: str


@dataclass
class Expanded:
    members: list[Member] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    junk: int = 0  # silently dropped names, counted for the audit row


@dataclass
class _Budget:
    limits: Limits
    files: int = 0
    total: int = 0

    def add_file(self) -> None:
        self.files += 1
        if self.files > self.limits.max_files:
            raise ArchiveError(
                "too_many_files",
                f"The upload has more than {self.limits.max_files} files. Send fewer files at a time.",
            )

    def add_bytes(self, n: int) -> None:
        self.total += n
        if self.total > self.limits.max_total_bytes:
            raise ArchiveError(
                "too_large", "The upload is larger than the size limit for one case."
            )


def _segments(name: str) -> list[str]:
    return [s for s in name.replace("\\", "/").split("/") if s not in ("", ".")]


def is_junk(name: str) -> bool:
    parts = _segments(name)
    if not parts:
        return True
    low = [p.lower() for p in parts]
    return (
        any(p in JUNK_DIRS for p in low[:-1])
        or low[-1] in JUNK_FILES
        or low[-1].startswith("._")  # macOS resource fork
    )


def _unsafe_path(name: str) -> bool:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):  # absolute or a drive letter
        return True
    return ".." in _segments(raw) or "\x00" in name


def _ext(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return "." + base.rsplit(".", 1)[-1].lower() if "." in base else ""


def looks_like_zip(name: str, data: bytes) -> bool:
    return _ext(name) == ".zip" or data[:4] == ZIP_MAGIC


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget: _Budget) -> bytes:
    """Read one member in chunks, stopping as soon as a byte or ratio limit is crossed. The
    declared sizes in the zip header are not trusted."""
    limits = budget.limits
    out = bytearray()
    with zf.open(info) as src:
        while chunk := src.read(CHUNK):
            out += chunk
            if len(out) > limits.max_member_bytes:
                raise ArchiveError(
                    "member_too_large",
                    "A file inside the zip is larger than the size limit for one file.",
                )
            if len(out) > limits.ratio_floor and len(out) > limits.max_ratio * max(
                info.compress_size, 1
            ):
                raise ArchiveError(
                    "zip_bomb", "This zip looks like a compression bomb and was refused."
                )
            budget.add_bytes(len(chunk))
    return bytes(out)


def _walk_zip(data: bytes, depth: int, budget: _Budget, into: Expanded) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        raise ArchiveError("bad_zip", "The zip file could not be opened.") from None
    with zf:
        infos = zf.infolist()
        # judge the whole listing before reading anything: an unsafe zip writes nothing
        for info in infos:
            if _unsafe_path(info.filename):
                raise ArchiveError(
                    "unsafe_path", "The zip contains a path outside its folder and was refused."
                )
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveError(
                    "symlink", "The zip contains a shortcut (symbolic link) and was refused."
                )
            if info.flag_bits & 0x1:
                raise ArchiveError(
                    "password_protected",
                    "This zip is password protected. Remove the password and upload it again.",
                )
        files = [i for i in infos if not i.is_dir() and not is_junk(i.filename)]
        into.junk += sum(1 for i in infos if not i.is_dir()) - len(files)
        if len(files) + budget.files > budget.limits.max_files:
            raise ArchiveError(
                "too_many_files",
                f"The zip has more than {budget.limits.max_files} files. Send fewer files at a time.",
            )
        if sum(i.file_size for i in files) + budget.total > budget.limits.max_total_bytes:
            raise ArchiveError(
                "too_large", "The upload is larger than the size limit for one case."
            )
        for info in files:
            label = _segments(info.filename)[-1][:200]
            if _ext(info.filename) == ".zip":
                if depth >= budget.limits.max_depth:
                    raise ArchiveError(
                        "nested_zip",
                        "A zip inside a zip inside a zip is not accepted. Unpack the inner one.",
                    )
                _walk_zip(_read_member(zf, info, budget), depth + 1, budget, into)
                continue
            if _ext(info.filename) not in ALLOWED_EXTENSIONS:
                into.skipped.append(
                    Skipped(label, "bad_type", "Only PDF, JPG and PNG files are accepted.")
                )
                continue
            budget.add_file()
            into.members.append(Member(label, info.filename, _read_member(zf, info, budget)))


def expand(parts: list[tuple[str, bytes]], limits: Limits | None = None) -> Expanded:
    """`parts` are (name as sent, bytes). A folder upload sends relative paths as names."""
    budget = _Budget(limits or Limits())
    out = Expanded()
    for name, data in parts:
        if _unsafe_path(name):
            raise ArchiveError(
                "unsafe_path", "A file name contains a path outside its folder and was refused."
            )
        if is_junk(name):
            out.junk += 1
            continue
        if looks_like_zip(name, data) and _ext(name) == ".zip":
            budget.add_bytes(0)
            _walk_zip(data, 0, budget, out)
            continue
        label = _segments(name)[-1][:200]
        if _ext(name) not in ALLOWED_EXTENSIONS:
            out.skipped.append(
                Skipped(label, "bad_type", "Only PDF, JPG and PNG files are accepted.")
            )
            continue
        budget.add_file()
        budget.add_bytes(len(data))
        out.members.append(Member(label, name, data))
    return out
