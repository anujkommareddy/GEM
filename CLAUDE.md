# GEM — Generative Entertainment Machine

Concept-to-clips pipeline for AI-generated films and videos.

## Running GEM

```bash
bun run gem              # Start the pipeline
ANTHROPIC_API_KEY=...    # Required for concept development & planning
HF_CREDENTIALS=...      # Required for image & video generation (Higgsfield)
```

## Pipeline Stages

1. **Develop** — Iterate on concept with AI until the idea is sharp
2. **Plan** — Break concept into scenes and shots with visual descriptions
3. **Look Dev** — Generate and approve starting images for each shot
4. **Prompt Review** — Review and approve exact video prompts per shot
5. **Generate** — Run video generation, get organized clips

## Project Structure

```
src/
├── cli.ts                # Entry point
├── types.ts              # Project, Scene, Shot types
├── project.ts            # Save/load project state
├── ui.ts                 # Terminal UI helpers
├── pipeline/
│   ├── develop.ts        # Stage 1: concept development
│   ├── plan.ts           # Stage 2: scene/shot planning
│   ├── look-dev.ts       # Stage 3: image generation + approval
│   ├── prompt-review.ts  # Stage 4: video prompt review
│   └── generate.ts       # Stage 5: video generation
└── models/
    └── higgsfield.ts     # Higgsfield API client (images + video)
```

Projects are saved as JSON in `projects/<name>/project.json` with generated media in `projects/<name>/output/`.

## gstack

Use `/browse` for all web browsing — never use MCP Claude-in-Chrome tools.

### Available skills

| Skill | Role | Purpose |
|-------|------|---------|
| `/plan-ceo-review` | Founder/CEO | Rethink problems to find the 10-star product within requests |
| `/plan-eng-review` | Tech Lead | Lock in architecture, data flow, diagrams, edge cases, tests |
| `/review` | Staff Engineer | Identify production-breaking bugs that pass CI |
| `/ship` | Release Engineer | Sync main, test, resolve reviews, push, open PR |
| `/browse` | QA Engineer | Give Claude eyes via persistent browser automation |
| `/qa` | QA Lead | Systematic testing with diff analysis and multiple modes |
| `/setup-browser-cookies` | Session Manager | Import browser cookies for authenticated page testing |
| `/retro` | Engineering Manager | Team-aware retrospectives with per-person feedback |
