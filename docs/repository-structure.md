# Repository Structure

This project follows the shared monorepo conventions.

## Top-level boundaries

- `services/`: only product services owned by the team.
- `shared/`: reusable libraries and shared contracts used across services.
- `playground/`: experiments, prototypes, and simulator-based testing of ideas.

## Placement rules

- Production code that is specific to one service belongs in `services/`.
- Generic SDKs, protocol models, and cross-service contracts belong in `shared/`.
- Any unstable or exploratory implementation belongs in `playground/` until ready.

## Migration notes

- When moving modules, keep public API contracts backward-compatible where possible.
- Update docs and examples together with moves to avoid stale paths.
- Keep tests close to code in each boundary to preserve ownership.
