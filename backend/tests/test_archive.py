"""Safe unpacking (EDGE_CASES E-42): every unsafe archive is refused whole, and nothing is
written anywhere (`expand` works in memory; names are labels and never become paths)."""

import io
import zipfile

import pytest

from app.intake import archive
from app.intake.archive import ArchiveError, Limits, expand

PDF = b"%PDF-1.4 minimal"


def make_zip(entries: dict[str, bytes], *, compress: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def refused(parts: list[tuple[str, bytes]], code: str, limits: Limits | None = None) -> None:
    with pytest.raises(ArchiveError) as e:
        expand(parts, limits)
    assert e.value.code == code, e.value.message


def test_loose_files_and_folder_paths_become_members_named_by_their_base_name() -> None:
    out = expand([("a.pdf", PDF), ("docs/sub/b.jpg", b"\xff\xd8\xff x"), ("c.PNG", b"x")])
    assert [m.label for m in out.members] == ["a.pdf", "b.jpg", "c.PNG"]
    assert out.members[1].path == "docs/sub/b.jpg" and not out.skipped


def test_a_zip_is_unpacked_and_junk_is_skipped_quietly() -> None:
    z = make_zip({
        "case/pan.pdf": PDF, "__MACOSX/case/._pan.pdf": b"x", "case/.DS_Store": b"x",
        "case/Thumbs.db": b"x", "case/._aadhaar.jpg": b"x", "case/aadhaar.jpg": b"\xff\xd8\xff",
        "case/notes.txt": b"hello", "case/": b"",
    })  # fmt: skip
    out = expand([("bundle.zip", z)])
    assert sorted(m.label for m in out.members) == ["aadhaar.jpg", "pan.pdf"]
    assert out.junk == 4  # the four junk files; the folder entry is not a file
    assert [(s.label, s.code) for s in out.skipped] == [("notes.txt", "bad_type")]


@pytest.mark.parametrize("name", ["../evil.pdf", "a/../../evil.pdf", "/etc/passwd.pdf",
                                  "C:/x.pdf", "..\\evil.pdf", "a\\..\\..\\evil.pdf"])  # fmt: skip
def test_a_path_outside_the_folder_refuses_the_whole_zip(name: str) -> None:
    refused([("z.zip", make_zip({"ok.pdf": PDF, name: PDF}))], "unsafe_path")


def test_a_loose_file_name_with_a_traversal_is_refused_too() -> None:
    refused([("../../x.pdf", PDF)], "unsafe_path")


def test_a_symbolic_link_refuses_the_zip() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        link = zipfile.ZipInfo("shortcut.pdf")
        link.external_attr = 0o120777 << 16  # a symlink entry
        zf.writestr(link, "/etc/passwd")
        zf.writestr("ok.pdf", PDF)
    refused([("z.zip", buf.getvalue())], "symlink")


def test_a_password_protected_zip_is_refused() -> None:
    raw = bytearray(make_zip({"secret.pdf": PDF}))
    raw[raw.index(b"PK\x03\x04") + 6] |= 0x1  # "encrypted" bit, local header...
    raw[raw.index(b"PK\x01\x02") + 8] |= 0x1  # ...and central directory
    refused([("z.zip", bytes(raw))], "password_protected")


def test_a_zip_bomb_is_stopped_while_reading_not_after() -> None:
    bomb = make_zip({"big.pdf": b"\0" * (6 * 1024 * 1024)})  # ~6 KB compressed
    assert len(bomb) < 20_000
    refused([("bomb.zip", bomb)], "zip_bomb", Limits(max_member_bytes=50 * 1024 * 1024))


def test_the_byte_budgets_hold_even_when_the_header_lies() -> None:
    z = make_zip({"a.pdf": b"x" * 400_000, "b.pdf": b"y" * 400_000})
    refused([("z.zip", z)], "too_large", Limits(max_total_bytes=500_000))
    refused([("z.zip", z)], "member_too_large", Limits(max_member_bytes=100_000))


def test_one_nested_zip_is_allowed_two_levels_are_not() -> None:
    inner = make_zip({"p.pdf": PDF})
    outer = make_zip({"inner.zip": inner, "q.pdf": PDF})
    assert sorted(m.label for m in expand([("outer.zip", outer)]).members) == ["p.pdf", "q.pdf"]
    deep = make_zip({"mid.zip": make_zip({"inner.zip": inner})})
    refused([("deep.zip", deep)], "nested_zip")


def test_too_many_files_refuses_everything() -> None:
    z = make_zip({f"f{i}.pdf": PDF for i in range(6)})
    refused([("z.zip", z)], "too_many_files", Limits(max_files=5))
    refused([(f"f{i}.pdf", PDF) for i in range(6)], "too_many_files", Limits(max_files=5))
    # the count covers a zip and the loose files sent with it
    refused([("z.zip", make_zip({"a.pdf": PDF, "b.pdf": PDF})), ("c.pdf", PDF), ("d.pdf", PDF)],
            "too_many_files", Limits(max_files=3))  # fmt: skip


def test_a_broken_zip_is_a_plain_refusal() -> None:
    refused([("z.zip", b"PK\x03\x04 not really")], "bad_zip")


def test_junk_names_are_recognised_in_any_spelling() -> None:
    for name in ("__MACOSX/x.pdf", "a/.DS_Store", "THUMBS.DB", "x/._y.pdf", "Desktop.ini"):
        assert archive.is_junk(name), name
    assert not archive.is_junk("a/payslip.pdf")
