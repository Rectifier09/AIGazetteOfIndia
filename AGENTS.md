# AGENTS.md — AIGazetteOfIndia

This project's working rules for AI agents. The Obsidian vault documentation
convention is defined globally at `~/.config/opencode/AGENTS.md` ("Global
Convention: Obsidian Vault Documentation") and loaded automatically in
opencode sessions. This file adds project-specific notes; base it on
`~/Workspace/OpenCode_Experiments/AGENTS.md` (the canonical template) if it
needs rebuilding.

## Vault: this project already has a folder

- Vault project folder: `~/Workspace/Vault/Projects/AIGazetteOfIndia`
- Purpose of this repo: _TBD — fill in once scoped._

## Rules inherited from the global convention (summary)

1. If a project's folder is missing under `Vault/Projects/`, scaffold it:
   ```bash
   cd ~/Workspace/Vault && ./new-project.sh "Project Name"
   ```
2. Commit context to the **right** vault file as you work:
   - Session activity → `Sessions/YYYY-MM-DD.md` (or the root `Build-Log.md`
     once this project is in a phased build — see `Sessions/README.md`)
   - A decision + why → `Decisions/`
   - Architecture rationale / plans → `Architecture/` or `Architecture/plans/`
   - Visual/voice choices → `Brand & UI Guidelines/`
   - A mistake/gotcha → `Past Mistakes & Lessons/`
   - Keep the overview note's Status current after milestones.
3. Write as you go, don't batch.
4. Mirror structure from the template — never hand-build a new vault folder
   tree.

## Project-specific notes

- Repo currently empty (initialized, no commits) as of 2026-09-05.
