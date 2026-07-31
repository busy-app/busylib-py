from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from busylib.client import AsyncBusyBar

from examples.setup.prompts import Prompt, SetupAborted, SetupCancelled
from examples.setup.steps import SetupStep, StepStatus, default_steps

logger = logging.getLogger(__name__)

MARK_DONE = "[x]"
MARK_PENDING = "[ ]"
MARK_UNKNOWN = "[?]"


@dataclass
class StepReport:
    """
    A step paired with the status that was read from the device.
    """

    step: SetupStep
    status: StepStatus | None
    error: str | None = None

    @property
    def done(self) -> bool:
        """
        True when the device already satisfies this step.
        """
        return self.status is not None and self.status.done

    def render(self) -> str:
        """
        Render one checklist line.
        """
        if self.error is not None:
            return (
                f"  {MARK_UNKNOWN} {self.step.title:<14} could not read ({self.error})"
            )
        assert self.status is not None
        mark = MARK_DONE if self.status.done else MARK_PENDING
        return f"  {mark} {self.step.title:<14} {self.status.summary}"


async def collect_status(
    client: AsyncBusyBar,
    steps: list[SetupStep] | None = None,
) -> list[StepReport]:
    """
    Read the current state of every step.

    Steps are probed concurrently and a failure is reported per step rather
    than aborting the whole checklist, so one unreachable endpoint doesn't
    hide the rest of the setup state.
    """
    step_list = steps if steps is not None else default_steps()
    results = await asyncio.gather(
        *(step.status(client) for step in step_list),
        return_exceptions=True,
    )

    reports: list[StepReport] = []
    for step, result in zip(step_list, results):
        if isinstance(result, BaseException):
            logger.warning("setup: reading %s failed: %s", step.key, result)
            reports.append(StepReport(step=step, status=None, error=str(result)))
        else:
            reports.append(StepReport(step=step, status=result))
    return reports


async def run_setup(
    client: AsyncBusyBar,
    prompt: Prompt,
    *,
    steps: list[SetupStep] | None = None,
    only: str | None = None,
    redo: bool = False,
) -> list[StepReport]:
    """
    Show the checklist and walk the user through whatever is still pending.

    Steps the device already satisfies are shown as done and skipped, unless
    `redo` is set. `only` restricts the run to a single step key.
    """
    reports = await collect_status(client, steps)

    prompt.info("BUSY Bar setup")
    for report in reports:
        prompt.info(report.render())

    pending = [r for r in reports if not r.done or redo]
    if only is not None:
        pending = [r for r in pending if r.step.key == only]
        if not pending:
            prompt.info(f"Nothing to do for step {only!r}.")
            return reports

    if not pending:
        prompt.info("Everything is set up already.")
        return reports

    for report in pending:
        prompt.info(f"--- {report.step.title} ---")
        try:
            await report.step.run(client, prompt)
        except SetupCancelled:
            # A step declined itself; carry on with the remaining ones.
            prompt.info(f"Skipped {report.step.title}.")
        except SetupAborted:
            # The user asked to leave, so don't immediately prompt again
            # for the next step - propagate and let the caller exit.
            prompt.info("Setup cancelled.")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("setup: step %s failed", report.step.key)
            prompt.info(f"{report.step.title} failed: {exc}")

    return await collect_status(client, steps)
