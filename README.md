# Tres Comas Scrum

Three autonomous LLM agents (CEO, Coder, Tester) running Scrum sprints to build a Python agentic framework from scratch, without human intervention.

Tres Comas. Three agents. Three commas. This is a test project.

## How it works

- **CEO** manages the backlog, plans sprints, reviews deliveries
- **Coder** implements tickets and delivers code in XML format
- **Tester** inspects the codebase every N sprints and generates feedback stories
- Each ticket is tested in an isolated sandbox (bwrap) before being applied
- The system retries up to 3 times per ticket on failure

## Requirements

- **Linux only** — sandbox execution uses `bwrap` (bubblewrap), not available on Windows/macOS
- Python 3.10+
- [OpenRouter](https://openrouter.ai) API key
- `bwrap` (bubblewrap) — `sudo apt install bubblewrap`

```bash
pip install -r requirements.txt
```

## Setup

```bash
cp .env.example .env

OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=your_openrouter_model_here
DB_PATH=state.db
```

## Run

```bash
python main.py
```

The system runs autonomously until the CEO decides the framework is complete (`framework_complete: true`).

Generated code is written to `output/`.

## Output structure

```
output/
  framework/      # generated source files
  tests/          # generated test files
  docs/           # generated documentation
```

## State

Everything is stored in `state.db` (SQLite) — backlog, sprint history, agent message history.

To reset a ticket and requeue it:

```python
import sqlite3, json
conn = sqlite3.connect("state.db")
# move ticket from done back to backlog
```

## Limitations

- The Coder has no memory between tickets (stateless by design)
- Tests run in isolation — imports from `framework/` are stripped and inlined
- Long files (200+ lines) sometimes get truncated by the model
- Pydantic V2 warnings in generated code are expected and harmless

## License

MIT
