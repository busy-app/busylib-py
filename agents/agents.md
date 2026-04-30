Language & communication
- Always respond in Russian
- Follow the repository language for comments and docstrings


Python version & general style
- Use Python 3.13+ code style
- Follow modern Python syntax and conventions


Typing
- Use modern typing with built-in generics and | unions
- Avoid unnecessary imports from typing
- Avoid Any; prefer TypeVar and ParamSpec when possible


Libraries & data models
- Use pydantic v2 and pydantic_settings
- Do not use dataclasses


Formatting
- Format long function arguments in columns right after (
- Format comprehensions in 2–3 lines
(expr … / for … in … / if …)


Documentation
- Every function must have a multiline docstring describing its idea and common logic


Planning
- For each feature, maintain plans/<feature>.md
- Keep the plan in sync with user input:
- add new requirements and constraints
- remove canceled ones
- update changed ones
- The plan file is the source of truth for the current agreed scope
- During implementation, mark plan items as implemented (Done)


Execution workflow
- Implement only one plan item per iteration
- For each implemented item:
- write tests covering it
- run ./.venv/bin/pytest -q and ensure it passes
- After finishing the single item, ask for continuation and briefly state what you’ll implement next
- If the user reports a bug/error, add a regression test for it when it makes sense (and keep it passing)