"""
Install or emit the Windows Task Scheduler entry for the nightly delta lane.

What it does for the operator:
  Generates a Windows Task Scheduler XML file that runs
  scripts/run_nightly_delta.py every day at a configured time. Optionally
  registers that task on this machine via `schtasks /create`.

  Running without --install just writes the XML (safe, read-only to your
  system). Running WITH --install actually creates or replaces the task.

When to run it:
  - Once, when setting up a new workstation for nightly ingests
  - Again, after changing the configured task name or start time
  - To emit a portable XML you can install by hand or on another box

Inputs:
  --config        Active runtime config YAML path.
  --python-exe    Full path to the venv Python used to run the task.
  --task-name     Override the configured Task Scheduler task name.
  --start-time    Override the configured daily start time (HH:MM).
  --emit-xml      Where to write the generated XML (default: under config/).
  --install       Call `schtasks /create` to register the task.
  --force         Pass `/f` to schtasks to replace an existing same-named task.

Outputs: the XML file on disk, and (with --install) a scheduled task on
this machine. Exit 0 on success; otherwise the schtasks return code.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import load_config


def _task_xml(*, task_name: str, start_time: str, python_exe: Path, config_path: Path) -> str:
    """Build the Windows Task Scheduler XML body (UTF-16) for the nightly delta task."""
    return dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-16"?>
        <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <RegistrationInfo>
            <Description>{task_name} - detect source delta, mirror locally, run CorpusForge pipeline on the mirrored delta.</Description>
          </RegistrationInfo>
          <Triggers>
            <CalendarTrigger>
              <StartBoundary>2026-04-09T{start_time}:00</StartBoundary>
              <Enabled>true</Enabled>
              <ScheduleByDay>
                <DaysInterval>1</DaysInterval>
              </ScheduleByDay>
            </CalendarTrigger>
          </Triggers>
          <Principals>
            <Principal id="Author">
              <LogonType>InteractiveToken</LogonType>
              <RunLevel>LeastPrivilege</RunLevel>
            </Principal>
          </Principals>
          <Settings>
            <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
            <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
            <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
            <AllowHardTerminate>true</AllowHardTerminate>
            <StartWhenAvailable>true</StartWhenAvailable>
            <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
            <AllowStartOnDemand>true</AllowStartOnDemand>
            <Enabled>true</Enabled>
            <Hidden>false</Hidden>
            <ExecutionTimeLimit>PT8H</ExecutionTimeLimit>
            <Priority>7</Priority>
          </Settings>
          <Actions Context="Author">
            <Exec>
              <Command>{python_exe}</Command>
              <Arguments>scripts\\run_nightly_delta.py --config {config_path}</Arguments>
              <WorkingDirectory>{PROJECT_ROOT}</WorkingDirectory>
            </Exec>
          </Actions>
        </Task>
        """
    )


def main() -> int:
    """Parse CLI flags, write the task XML, and (if requested) register it with Windows Task Scheduler."""
    parser = argparse.ArgumentParser(description="Install the CorpusForge nightly delta scheduled task.")
    parser.add_argument("--config", default="config/config.yaml", help="Active runtime config path.")
    parser.add_argument("--python-exe", default=str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"))
    parser.add_argument("--task-name", default=None, help="Override the configured task name.")
    parser.add_argument("--start-time", default=None, help="Override the configured task start time (HH:MM).")
    parser.add_argument("--emit-xml", default=str(PROJECT_ROOT / "config" / "nightly_delta_task.generated.xml"))
    parser.add_argument("--install", action="store_true", help="Install the task with schtasks after emitting XML.")
    parser.add_argument("--force", action="store_true", help="Replace an existing task of the same name.")
    args = parser.parse_args()

    config = load_config(args.config)
    task_name = args.task_name or config.nightly_delta.task_name
    start_time = args.start_time or config.nightly_delta.task_start_time
    python_exe = Path(args.python_exe).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()

    xml_path = Path(args.emit_xml).resolve()
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    xml_payload = _task_xml(
        task_name=task_name,
        start_time=start_time,
        python_exe=python_exe,
        config_path=config_path,
    )
    xml_path.write_text(xml_payload, encoding="utf-16")
    print(f"Task XML written to: {xml_path}")

    if not args.install:
        return 0

    command = [
        "schtasks",
        "/create",
        "/tn",
        task_name,
        "/xml",
        str(xml_path),
    ]
    if args.force:
        command.append("/f")

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    print(result.stdout.strip() or f"Installed scheduled task: {task_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
