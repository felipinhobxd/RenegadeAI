# RenegadeAI

Autonomous AI agent for **Pokemon Renegade Platinum** running in **melonDS**.

> This repository does not include the game ROM, copyrighted game assets, BIOS/firmware files, or emulator binaries. You must provide your own legally obtained copy of the game and melonDS installation.

## Goal

Build an agent that can eventually complete Renegade Platinum autonomously while:

- controlling melonDS;
- observing the game state;
- making battle and overworld decisions;
- optimizing teams, moves, held items, and routes;
- recording every run and battle;
- learning from successful and failed decisions;
- reusing learned strategies in future attempts.

## Architecture

```text
melonDS
  |
  +-- desktop adapter (keyboard + screenshots)  <-- works with stock melonDS
  +-- memory adapter (future / experimental scripting bridge)
  |
perception -> state model -> planner -> action -> memory/learning
```

The project intentionally starts with a stock-melonDS-compatible adapter. Native Lua scripting for melonDS is still experimental upstream, so the emulator integration is abstracted behind an adapter and can be upgraded later without rewriting the agent.

## Current milestone

**Milestone 0: Agent foundation**

- [ ] melonDS desktop control
- [ ] screenshot capture
- [ ] normalized action model
- [ ] persistent experience database
- [ ] battle decision engine foundation
- [ ] CLI diagnostics
- [ ] tests

Next milestones will add screen-state recognition, Pokemon/team knowledge, battle simulation, overworld navigation, save-state training, and self-improving policy optimization.

## Development

The implementation is Python 3.11+ and is designed to run beside melonDS.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
renegade-ai doctor
```

See the project documentation and CLI help as the agent grows.
