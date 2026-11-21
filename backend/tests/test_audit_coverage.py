"""Stage 11 security pass: every route that changes something writes an audit row, or says why
not. A new write route fails here until it audits or is added to one of the two lists below."""

import importlib
import inspect

from fastapi.routing import APIRoute

from app.api.main import create_app

# The audit row is written by the code the route calls: (module, the action it writes).
DELEGATED: dict[str, tuple[str, str]] = {
    "auth.logout": ("app.api.auth", '"logout"'),
    "intake.confirm_bundle": ("app.api.ingest", '"bundle_split_confirmed"'),
    "cases.submit_case": ("app.api.cases", '"case_submitted"'),
    "cases.resume_case": ("app.api.cases", '"case_resumed_after_fix"'),
    "cases.confirm_case": ("app.agents.graph", 'f"officer_{action}"'),
    "cases.override_case": ("app.agents.graph", 'f"officer_{action}"'),
    "ai_control.save_config": ("app.api.ai_control", '"ai_config_changed"'),
    "ai_control.rollback_config": ("app.api.ai_control", '"ai_config_changed"'),
    "ai_control.publish_draft": ("app.api.ai_control", '"ai_prompt_published"'),
    "ai_control.rollback_prompt": ("app.api.ai_control", '"ai_prompt_published"'),
    "knowledge.save_draft": ("app.rag.policy_store", '"policy_draft_saved"'),
    "knowledge.start_draft": ("app.rag.policy_store", '"policy_draft_saved"'),
    "knowledge.edit_clause": ("app.rag.policy_store", '"policy_draft_saved"'),
    "knowledge.restore_version": ("app.rag.policy_store", '"policy_draft_saved"'),
    "knowledge.discard_draft": ("app.rag.policy_store", '"policy_draft_discarded"'),
    "knowledge.publish": ("app.rag.policy_store", '"policy_published"'),
    "knowledge.retire_version": ("app.rag.policy_store", '"policy_retired"'),
    "knowledge.reindex_now": ("app.rag.index", "'policy_reindex'"),
    "knowledge.reconfirm": ("app.learning.maintenance", '"precedent_reconfirmed"'),
    "knowledge.retire_learning": ("app.learning.maintenance", '"precedent_retired"'),
}

# No audit row by design: a person's own state, previews and checks that change nothing others
# rely on, and a prompt's working draft (testing and publishing it are audited).
NOT_AUDITED = {
    "auth.ping",
    "notifications.mark_read",
    "notifications.read_all",
    "knowledge.check_text",
    "knowledge.convert_file",
    "knowledge.legacy_import",
    "knowledge.retrieval_check",
    "knowledge.evaluate_index",
    "ai_control.save_draft",
    "ai_control.discard_draft",
}


def _write_routes() -> dict[str, APIRoute]:
    app = create_app()
    out: dict[str, APIRoute] = {}
    for inc in app.routes:
        router = getattr(inc, "original_router", None)
        for r in getattr(router, "routes", [inc]):
            if isinstance(r, APIRoute) and r.methods & {"POST", "PUT", "PATCH", "DELETE"}:
                out[f"{r.endpoint.__module__.rsplit('.', 1)[-1]}.{r.endpoint.__name__}"] = r
    return out


def test_every_write_route_writes_an_audit_row_or_says_why_not() -> None:
    routes = _write_routes()
    assert len(routes) > 50  # the walk found the routers
    unexplained = sorted(
        name for name, r in routes.items()
        if "audit" not in inspect.getsource(r.endpoint) and name not in DELEGATED and name not in NOT_AUDITED
    )  # fmt: skip
    assert unexplained == [], f"write routes with no audit row and no reason: {unexplained}"
    for name, (module, action) in DELEGATED.items():
        assert name in routes, f"{name} is listed but is no longer a write route"
        assert action in inspect.getsource(importlib.import_module(module)), (name, action)
    assert not (NOT_AUDITED - set(routes)), "a listed route no longer exists"
