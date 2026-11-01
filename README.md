# Loan Pre-Underwriting Copilot

A copilot for banks and NBFCs. A loan officer uploads an applicant's documents. A LangGraph multi-agent pipeline checks them stage by stage, scores the case in code, and writes a report with a recommendation and policy citations. A human confirms every case.

Capstone project. Synthetic data only. No real personal data.

## Status

Stage 1 (foundation and synthetic data) built; awaiting review. Next: Stage 2 (intake and parsers).

## Documents

Start with [CLAUDE.md](CLAUDE.md), then see [docs/](docs/):

- [PRD](docs/PRD.md): what we are building and why
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md): 8 stages with exit tests
- [Architecture](docs/ARCHITECTURE.md) and [diagrams](docs/diagrams/)

## Stack

React + JavaScript + CSS, FastAPI, LangGraph, LiteLLM, Postgres with pgvector, Langfuse, Docker Compose.
