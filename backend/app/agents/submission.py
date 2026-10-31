"""What a loan officer hands the pipeline: the application form and the uploaded files.

`Submission` holds paths, not bytes, so state stays small and a resume re-reads the same files.
The Stage 6 API builds one from the case tables; the command line builds one from a case folder.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

Role = Literal["primary", "co"]
ALLOWED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}


class DocumentRef(BaseModel):
    role: Role
    path: str
    name: str  # original file name: a label for messages, never used to decide anything


class Submission(BaseModel):
    case_id: str
    application: dict[str, Any]
    documents: list[DocumentRef]

    @property
    def loan_type(self) -> str:
        return str(self.application["loan_type"])

    def applicant(self, role: Role) -> dict[str, Any] | None:
        return next((a for a in self.application["applicants"] if a["role"] == role), None)


def load_case_dir(case_dir: Path) -> Submission:
    """A generated case folder: application.json plus documents/<primary|co>/<files>."""
    application = json.loads((case_dir / "application.json").read_text())
    docs: list[DocumentRef] = []
    for role in ("primary", "co"):
        folder = case_dir / "documents" / role
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in ALLOWED_SUFFIXES:
                docs.append(DocumentRef(role=role, path=str(f), name=f.name))
    return Submission(case_id=application["case_id"], application=application, documents=docs)
