"""The LangGraph pipeline (ARCHITECTURE.md section 3).

    supervisor -> extraction -> gate_E -> kyc -> gate_K -+- stop ---------------> decision
                                                          +- ok -> policy || risk -> gate_PR -> decision
    decision -> await_officer (pause) -> END          (a fix-type stop ends at `decision` instead)

The edges are fixed; gates are code. A hard fail routes straight to the Decision agent, which
writes a short report. A node that raises is retried once, then the stage is marked `unverified`
with code-written output where that is possible. State is checkpointed in Postgres after every
node, so a killed process resumes where it stopped. Nothing in this graph computes a score: the
rules engine does, once, in `extraction`, and every later node reads that result.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents import evals, store
from app.agents.assemble import extract
from app.agents.decision import run_decision
from app.agents.kyc import KycResult, run_kyc_agent
from app.agents.policy import PROMPT_VERSION as POLICY_PROMPT_VERSION
from app.agents.policy import run_policy_agent
from app.agents.report import Report
from app.agents.results import checks_for
from app.agents.risk import RiskResult, run_risk_agent
from app.agents.runtime import AgentContext
from app.agents.state import RESET, EvalRecord, Flag, LLMCallRecord, PipelineState
from app.agents.submission import DocumentRef, Submission
from app.agents.supervisor import CasePlan, run_supervisor
from app.rag.schemas import PolicyResult
from app.scoring.engine import score_case
from app.scoring.models import CaseInput, ScoreReport

Update = dict[str, Any]
Node = Callable[[PipelineState], Awaitable[Any]]
NO_RETRY = (asyncio.CancelledError, KeyboardInterrupt, SystemExit)


def _dump(items: list[Any]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json") for i in items]


def _case(state: PipelineState) -> UUID:
    return UUID(state["case_uuid"])


def _score(state: PipelineState) -> ScoreReport:
    return ScoreReport.model_validate(state["score"])


def _input(state: PipelineState) -> CaseInput:
    return CaseInput.model_validate(state["case_input"])


def _flags(state: PipelineState) -> list[Flag]:
    return [Flag.model_validate(f) for f in state.get("flags", [])]


def build_graph(ctx: AgentContext, checkpointer: BaseCheckpointSaver[str] | None) -> Any:
    rs = ctx.ruleset

    def guarded(
        stage: str,
        fn: Node,
        fallback: Callable[[PipelineState, Exception], Awaitable[Update]] | None = None,
    ) -> Node:
        """Run a node; on an error try once more; then use the stage's code-only fallback."""

        async def run(state: PipelineState) -> Update:
            if ctx.crash_before == stage:  # test hook: die between nodes, checkpoint already saved
                ctx.crash_action()
            last: Exception | None = None
            for _ in range(2):
                try:
                    update: Update = await fn(state)
                    return update
                except NO_RETRY:
                    raise
                except Exception as exc:  # noqa: BLE001 - one retry, then fall back or fail loudly
                    last = exc
            if fallback is None or last is None:
                raise last  # type: ignore[misc]
            out = await fallback(state, last)
            out.setdefault("stage_status", {})[stage] = "unverified"
            return out

        return run

    # ---------------------------------------------------------------- supervisor
    async def supervisor(state: PipelineState) -> Update:
        sub = Submission.model_validate(state["submission"])
        plan, calls = await run_supervisor(ctx, sub)
        with ctx.engine.begin() as conn:
            store.update_case(conn, _case(state), "running")
            store.audit(conn, "pipeline_started", state["case_uuid"], {"case_id": sub.case_id})
        return {
            "plan": plan.model_dump(mode="json"),
            "status": "running",
            "stop": None,
            "llm_calls": _dump(calls),
            "stage_status": {"supervisor": "unverified" if plan.unverified else "passed"},
        }

    # ---------------------------------------------------------------- extraction
    async def extraction(state: PipelineState) -> Update:
        sub = Submission.model_validate(state["submission"])
        ex = await extract(ctx, sub)
        score = score_case(ex.case_input, rs)  # the one scoring run: later nodes read it
        plan = CasePlan.model_validate(state["plan"])
        plan.missing = ex.output.shortfalls
        pts, mx = score.stage_scores["documents"], score.stage_max["documents"]
        stopped = score.stopped_stage == "extraction"
        status = "unverified" if ex.output.unreadable else ("failed" if stopped else "passed")
        with ctx.engine.begin() as conn:
            store.save_documents(conn, _case(state), sub, ex.output.documents, ex.case_input)
            store.save_stage(
                conn, _case(state), "extraction", status=status, score=pts, max_score=mx,
                hard_fail=stopped, fail_class=score.stop_class if stopped else None,
                findings=_dump(ex.flags), model=ex.calls[-1].model if ex.calls else None, prompt_version=1,
                fallback_used=any(c.fallback_used for c in ex.calls),
                checks=checks_for(score, ("documents",)),
            )  # fmt: skip
        docs = [d.model_dump(mode="json") for d in ex.output.documents]
        return {
            "plan": plan.model_dump(mode="json"),
            "extraction": ex.output.model_dump(mode="json"),
            "case_input": ex.case_input.model_dump(mode="json"),
            "score": score.model_dump(mode="json"),
            "flags": [RESET, *_dump(ex.flags)],
            "llm_calls": _dump(ex.calls),
            "evals": _dump(evals.extraction_evals(docs, ex.case_input)),
            "stage_status": {"extraction": status},
        }

    # ---------------------------------------------------------------- gates (code only)
    def gate_for(stopping: tuple[str, ...], agent: str | None = None) -> Node:
        """Hard-fail check from the code's score. If the agent's own hard-fail flag disagrees with
        the code, the code value wins and the mismatch is logged (AGENTS.md gate rules)."""

        async def gate(state: PipelineState) -> Update:
            score = _score(state)
            stopped = score.stopped_stage in stopping
            out: Update = {"stop": {"stage": score.stopped_stage, "class": score.stop_class,
                                    "reason": "hard fail"} if stopped else None}  # fmt: skip
            result: dict[str, Any] | None = state.get(agent) if agent else None  # type: ignore[assignment]
            if result is not None and bool(result.get("hard_fail")) != (
                score.stopped_stage == agent
            ):
                out["evals"] = [EvalRecord(stage=str(agent), metric="hard_fail_mismatch",
                                           value=0.0).model_dump(mode="json")]  # fmt: skip
            return out

        return gate

    # ---------------------------------------------------------------- kyc
    async def kyc(state: PipelineState) -> Update:
        inp, score = _input(state), _score(state)
        result, calls = await run_kyc_agent(ctx, inp, score)
        status = "failed" if result.hard_fail else ("unverified" if result.unverified else "passed")
        with ctx.engine.begin() as conn:
            store.save_stage(
                conn, _case(state), "kyc", status=status, score=result.score, max_score=result.max_score,
                hard_fail=result.hard_fail, fail_class=result.fail_class,
                findings=[n for n in result.notes], model=result.model,
                prompt_version=result.prompt_version, retries=result.retries,
                fallback_used=result.fallback_used, checks=result.checks,
            )  # fmt: skip
        return {
            "kyc": result.model_dump(mode="json"),
            "llm_calls": _dump(calls),
            "evals": _dump(evals.kyc_evals(result, inp, score, rs)),
            "stage_status": {"kyc": status},
        }

    async def kyc_fallback(state: PipelineState, exc: Exception) -> Update:
        quiet = replace(ctx, router=None)
        result, _ = await run_kyc_agent(quiet, _input(state), _score(state))
        result.unverified = True
        result.issues = [f"agent error ({type(exc).__name__})"]
        with ctx.engine.begin() as conn:
            store.save_stage(conn, _case(state), "kyc", status="unverified", score=result.score,
                             max_score=result.max_score, hard_fail=result.hard_fail,
                             fail_class=result.fail_class, checks=result.checks)  # fmt: skip
        return {"kyc": result.model_dump(mode="json")}

    # ---------------------------------------------------------------- policy
    async def policy(state: PipelineState) -> Update:
        score = _score(state)
        if score.stopped_stage == "risk":  # a hard fail in Risk ends the run: Policy is not run
            return {"stage_status": {"policy": "skipped"}}
        inp = _input(state)
        with ctx.engine.connect() as conn:
            retriever = ctx.retriever_factory(conn) if ctx.retriever_factory else None
            result = await run_policy_agent(conn, ctx.router, inp, score, rs, retriever=retriever)
        status = "unverified" if result.unverified else "passed"
        calls = (
            [LLMCallRecord(stage="policy", role="policy", model=result.model or "", tokens_in=result.tokens_in,
                           tokens_out=result.tokens_out, cost_usd=result.cost_usd,
                           latency_ms=result.latency_ms, fallback_used=result.fallback_used)]
            if result.model else []
        )  # fmt: skip
        with ctx.engine.begin() as conn:
            store.save_stage(
                conn, _case(state), "policy", status=status, score=result.score,
                max_score=score.stage_max["policy"], findings=_dump(result.fit_findings),
                model=result.model, prompt_version=POLICY_PROMPT_VERSION, retries=result.retries,
                fallback_used=result.fallback_used, checks=checks_for(score, ("policy",)),
            )  # fmt: skip
        return {
            "policy": result.model_dump(mode="json"),
            "llm_calls": _dump(calls),
            "evals": _dump(evals.policy_evals(result)),
            "stage_status": {"policy": status},
        }

    async def policy_fallback(state: PipelineState, exc: Exception) -> Update:
        score = _score(state)
        result = PolicyResult(
            clauses=[], precedent_matches=[], fit_findings=[], unverified=True,
            score=score.stage_scores.get("policy"), grounding_issues=[f"agent error ({type(exc).__name__})"],
        )  # fmt: skip
        with ctx.engine.begin() as conn:
            store.save_stage(conn, _case(state), "policy", status="unverified", score=result.score,
                             max_score=score.stage_max["policy"], checks=checks_for(score, ("policy",)))  # fmt: skip
        return {"policy": result.model_dump(mode="json")}

    # ---------------------------------------------------------------- risk
    async def risk(state: PipelineState) -> Update:
        inp, score = _input(state), _score(state)
        result, calls = await run_risk_agent(ctx, inp, score)
        status = "failed" if result.hard_fail else ("unverified" if result.unverified else "passed")
        with ctx.engine.begin() as conn:
            store.save_stage(
                conn, _case(state), "risk", status=status,
                score=round(result.income_score + result.behaviour_score, 2),
                max_score=round(result.income_max + result.behaviour_max, 2),
                hard_fail=result.hard_fail, fail_class=result.fail_class, findings=_dump(result.flags),
                model=result.model, prompt_version=result.prompt_version, retries=result.retries,
                fallback_used=result.fallback_used, checks=result.checks,
            )  # fmt: skip
        return {
            "risk": result.model_dump(mode="json"),
            "llm_calls": _dump(calls),
            "evals": _dump(evals.risk_evals(result)),
            "stage_status": {"risk": status},
        }

    async def risk_fallback(state: PipelineState, exc: Exception) -> Update:
        quiet = replace(ctx, router=None)
        result, _ = await run_risk_agent(quiet, _input(state), _score(state))
        result.unverified = True
        result.issues = [f"agent error ({type(exc).__name__})"]
        with ctx.engine.begin() as conn:
            store.save_stage(conn, _case(state), "risk", status="unverified",
                             score=round(result.income_score + result.behaviour_score, 2),
                             max_score=round(result.income_max + result.behaviour_max, 2),
                             hard_fail=result.hard_fail, fail_class=result.fail_class, checks=result.checks)  # fmt: skip
        return {"risk": result.model_dump(mode="json")}

    # ---------------------------------------------------------------- decision
    async def decision(state: PipelineState) -> Update:
        score = _score(state)
        kyc_r = KycResult.model_validate(state["kyc"]) if state.get("kyc") else None
        risk_r = RiskResult.model_validate(state["risk"]) if state.get("risk") else None
        pol_r = PolicyResult.model_validate(state["policy"]) if state.get("policy") else None
        plan = CasePlan.model_validate(state["plan"])
        flags = _flags(state)
        ext = state["extraction"]
        unverified = [{"stage": s, "reason": why} for s, why in [
            ("supervisor", "the briefing was written by code") if plan.unverified else ("", ""),
            ("extraction", f"unreadable: {', '.join(ext['unreadable'])}") if ext["unreadable"] else ("", ""),
            ("kyc", "explanations unavailable") if kyc_r and kyc_r.unverified else ("", ""),
            ("risk", "explanations unavailable") if risk_r and risk_r.unverified else ("", ""),
            ("policy", "findings not grounded; code-written findings shown") if pol_r and pol_r.unverified else ("", ""),
        ] if s]  # fmt: skip
        models = {"supervisor": plan.model, "kyc": kyc_r.model if kyc_r else None,
                  "risk": risk_r.model if risk_r else None, "policy": pol_r.model if pol_r else None}  # fmt: skip
        prompts = {"supervisor": plan.prompt_version, "extraction": 1, "kyc": kyc_r.prompt_version if kyc_r else 0,
                   "risk": risk_r.prompt_version if risk_r else 0, "policy": POLICY_PROMPT_VERSION}  # fmt: skip
        with ctx.engine.connect() as conn:
            report, asked, meta = await run_decision(
                ctx, conn, score, kyc=kyc_r, risk=risk_r, policy=pol_r, flags=flags,
                applicants=[{"role": a["role"], "name": a["full_name"]}
                            for a in Submission.model_validate(state["submission"]).application["applicants"]],
                documents=ext["documents"], models=models, prompts=prompts, unverified=unverified,
            )  # fmt: skip
        if asked.unverified:
            why = "; ".join(asked.issues)[:200]
            report.unverified.append(
                {"stage": "decision", "reason": f"summary written by code ({why})"}
            )
        models["decision"] = asked.model
        report.versions["models"] = models
        new_evals = evals.decision_evals(
            report, score, set(meta["known_ids"]) | {c.clause_id for c in report.citations}
        )
        if meta["needs_judge"] and ctx.judge_inconclusive:
            new_evals.append(
                await evals.judge_claim(
                    ctx, "decision", report.summary, report.model_dump_json()[:3000]
                )
            )
        status = "stopped" if report.status == "stopped" else "awaiting_confirmation"
        stage_status = "unverified" if asked.unverified else "passed"
        all_calls = [
            LLMCallRecord.model_validate(c) for c in state.get("llm_calls", [])
        ] + asked.calls
        all_evals = [EvalRecord.model_validate(e) for e in state.get("evals", [])] + new_evals
        run_no = int(state.get("run_no", 1))
        with ctx.engine.begin() as conn:
            store.save_stage(
                conn, _case(state), "decision", status=stage_status, score=report.total_score, max_score=100,
                hard_fail=False, findings=[{"summary_source": report.summary_source}],
                model=asked.model, prompt_version=meta["version"], retries=asked.retries,
                fallback_used=asked.fallback_used,
            )  # fmt: skip
            store.save_logs(conn, _case(state), all_calls, all_evals)
            store.save_report(conn, _case(state), run_no, report)
            store.update_case(conn, _case(state), status, report)
            store.audit(conn, "pipeline_finished", state["case_uuid"],
                        {"status": status, "recommendation": report.recommendation})  # fmt: skip
        return {
            "report": report.model_dump(mode="json"),
            "status": status,
            "llm_calls": _dump(asked.calls),
            "evals": _dump(new_evals),
            "stage_status": {"decision": stage_status},
        }

    # ---------------------------------------------------------------- the human step
    async def await_officer(state: PipelineState) -> Update:
        """Pause here. The run resumes with the officer's confirm or override (two clicks, a
        written reason for an override); the API in Stage 6 supplies the values."""
        report = Report.model_validate(state["report"])
        answer = interrupt({"case_id": state["case_id"], "recommendation": report.recommendation_text,
                            "awaiting": report.awaiting})  # fmt: skip
        action = answer["action"]
        final = check_officer_answer(answer, report.recommendation)
        status = "confirmed" if action == "confirm" else "overridden"
        with ctx.engine.begin() as conn:
            if answer.get("officer_id"):
                store.record_officer_action(
                    conn, _case(state), UUID(str(answer["officer_id"])), action=action,
                    original=report.recommendation, final=final, reason=answer.get("reason"),
                )  # fmt: skip
            store.update_case(conn, _case(state), status, report)
            store.audit(conn, f"officer_{action}", state["case_uuid"], {"final": final})
        return {"officer": {"action": action, "final_decision": final, "reason": answer.get("reason")},
                "status": status}  # fmt: skip

    g: Any = StateGraph(PipelineState)  # langgraph's overloads are too strict for plain async nodes
    g.add_node("supervisor", guarded("supervisor", supervisor))
    g.add_node("extraction", guarded("extraction", extraction))
    g.add_node("gate_E", gate_for(("extraction",)))
    g.add_node("kyc", guarded("kyc", kyc, kyc_fallback))
    g.add_node("gate_K", gate_for(("extraction", "kyc"), "kyc"))
    g.add_node("policy", guarded("policy", policy, policy_fallback))
    g.add_node("risk", guarded("risk", risk, risk_fallback))
    g.add_node("gate_PR", gate_for(("extraction", "kyc", "risk"), "risk"))
    g.add_node("decision", guarded("decision", decision))
    g.add_node("await_officer", await_officer)

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "extraction")
    g.add_edge("extraction", "gate_E")
    g.add_conditional_edges("gate_E", lambda s: "decision" if s.get("stop") else "kyc",
                            ["decision", "kyc"])  # fmt: skip
    g.add_edge("kyc", "gate_K")
    g.add_conditional_edges("gate_K", lambda s: ["decision"] if s.get("stop") else ["policy", "risk"],
                            ["decision", "policy", "risk"])  # fmt: skip
    g.add_edge(["policy", "risk"], "gate_PR")
    g.add_edge("gate_PR", "decision")
    g.add_conditional_edges("decision", lambda s: "await_officer" if s.get("status") == "awaiting_confirmation" else END,
                            ["await_officer", END])  # fmt: skip
    g.add_edge("await_officer", END)
    return g.compile(checkpointer=checkpointer)


def check_officer_answer(answer: dict[str, Any], recommendation: str) -> str:
    """The officer's final decision, or ValueError. Checked before the graph is resumed: a value
    that failed inside the paused node would be replayed on every later resume."""
    action = answer.get("action")
    if action not in ("confirm", "override") or answer.get("second_click") is not True:
        raise ValueError("an officer action needs action=confirm|override and a second click")
    if action == "confirm":
        return recommendation
    if not str(answer.get("reason") or "").strip():
        raise ValueError("an override needs a written reason")
    final = str(answer.get("final_decision") or "")
    if final not in ("approve", "refer", "reject"):
        raise ValueError("an override needs final_decision approve|refer|reject")
    return final


class Pipeline:
    """Start, resume, correct and confirm cases. One thread per case (`thread_id` = cases.id)."""

    def __init__(self, ctx: AgentContext, checkpointer: BaseCheckpointSaver[str] | None) -> None:
        self.ctx = ctx
        self.checkpointer = checkpointer
        self.graph = build_graph(ctx, checkpointer)

    @staticmethod
    def _cfg(case_uuid: UUID | str) -> Any:
        return {"configurable": {"thread_id": str(case_uuid)}, "recursion_limit": 40}

    async def start(self, sub: Submission, case_uuid: UUID) -> PipelineState:
        init: PipelineState = {
            "case_id": sub.case_id,
            "case_uuid": str(case_uuid),
            "submission": sub.model_dump(mode="json"),
            "status": "running",
            "run_no": 1,
            "flags": [],
            "llm_calls": [],
            "evals": [],
            "stage_status": {},
        }
        return cast(PipelineState, await self.graph.ainvoke(init, self._cfg(case_uuid)))

    async def resume(self, case_uuid: UUID | str) -> PipelineState:
        """Continue from the last checkpoint (after a crash, or after `resume_after_fix`)."""
        return cast(PipelineState, await self.graph.ainvoke(None, self._cfg(case_uuid)))

    async def snapshot(self, case_uuid: UUID | str) -> Any:
        return await self.graph.aget_state(self._cfg(case_uuid))

    async def resume_after_fix(
        self, case_uuid: UUID | str, replace_docs: list[DocumentRef] | None = None,
        application: dict[str, Any] | None = None,
    ) -> PipelineState:  # fmt: skip
        """A fix-type stop: the officer corrected the form or replaced files. Everything derived
        from them is stale, so the run re-enters at Extraction with the same case and thread."""
        snap = await self.snapshot(case_uuid)
        values = snap.values
        if not values.get("stop") or values["stop"].get("class") != "fix":
            raise ValueError("only a case stopped for a correction can be resumed this way")
        sub = Submission.model_validate(values["submission"])
        if application:
            sub.application = application
        if replace_docs:
            names = {(d.role, d.name) for d in replace_docs}
            sub.documents = [
                d for d in sub.documents if (d.role, d.name) not in names
            ] + replace_docs
        update: Update = {
            "submission": sub.model_dump(mode="json"), "stop": None, "status": "running",
            "run_no": int(values.get("run_no", 1)) + 1, "report": None, "kyc": None, "risk": None,
            "policy": None, "stage_status": {k: "pending" for k in ("extraction", "kyc", "policy", "risk", "decision")},
        }  # fmt: skip
        await self.graph.aupdate_state(self._cfg(case_uuid), update, as_node="supervisor")
        return cast(PipelineState, await self.graph.ainvoke(None, self._cfg(case_uuid)))

    async def officer_action(
        self, case_uuid: UUID | str, *, action: str, second_click: bool, reason: str | None = None,
        final_decision: str | None = None, officer_id: UUID | str | None = None,
    ) -> PipelineState:  # fmt: skip
        values = (await self.snapshot(case_uuid)).values
        if not values.get("report") or values.get("status") != "awaiting_confirmation":
            raise ValueError("this case is not awaiting an officer")
        answer = {"action": action, "second_click": second_click, "reason": reason,
                  "final_decision": final_decision, "officer_id": str(officer_id) if officer_id else None}  # fmt: skip
        check_officer_answer(answer, values["report"]["recommendation"])
        return cast(
            PipelineState, await self.graph.ainvoke(Command(resume=answer), self._cfg(case_uuid))
        )
