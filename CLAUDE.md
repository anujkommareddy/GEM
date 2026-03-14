# GEM

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

### Workflow

- **Planning phase**: Use `/plan-ceo-review` then `/plan-eng-review`
- **Implementation**: Standard Claude Code workflow
- **Review cycle**: Use `/review` for paranoid quality checks
- **Shipping**: `/ship` handles release hygiene automatically
- **Testing**: `/qa` validates without manual clicking
- **Reflection**: `/retro` provides data-driven team insights
