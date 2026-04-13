# Orchestrator Repo Setup (GitHub-only fallback)

Use a separate GitHub repository as a scheduler and dispatch events to this repo.

## 1) Prepare token in orchestrator repo

Create secret `TARGET_REPO_PAT` in the orchestrator repository with a fine-grained token that can access:

- Repository: `tranducthao243/ffdatareport`
- Permissions:
  - Actions: Read and write
  - Contents: Read
  - Metadata: Read

## 2) Add dispatch workflows in orchestrator repo

Copy these files into the orchestrator repo `.github/workflows/`:

- `docs/orchestrator/ffvn-dispatch-fetch.yml`
- `docs/orchestrator/ffvn-dispatch-send.yml`

## 3) Verify target repo accepts dispatch events

This repository now listens to:

- `repository_dispatch` with event type `ffvn-fetch`
- `repository_dispatch` with event type `ffvn-send`

## 4) Test manually from orchestrator workflow

Run both workflows with `workflow_dispatch` to validate:

- Fetch dispatch can trigger `FFVN Daily Fetch (Scheduled)`
- Send dispatch can trigger `FFVN Daily Send (Scheduled)`

