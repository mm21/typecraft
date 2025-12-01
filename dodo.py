import subprocess
import sys

from doit.task import Task


def task_format() -> Task:
    """
    Run formatters.
    """

    autoflake_args = [
        "autoflake",
        ".",
    ]

    isort_args = [
        "isort",
        ".",
    ]

    docformatter_args = [
        "docformatter",
        ".",
    ]

    black_args = [
        "black",
        ".",
    ]

    toml_sort_args = [
        "toml-sort",
        "-i",
        "pyproject.toml",
    ]

    return Task(
        "format",
        actions=[
            (_run, (autoflake_args,)),
            (_run, (isort_args,)),
            (_run, (docformatter_args, {0, 3})),
            (_run, (black_args,)),
            (_run, (toml_sort_args,)),
        ],
        targets=[],
        file_dep=[],
    )


def _run(cmd: list[str], expect_rc: int | set[int] = 0):
    expect_rcs = expect_rc if isinstance(expect_rc, set) else set((expect_rc,))
    print(f"=== Running: {cmd[0]}")
    rc = subprocess.call(cmd)
    if not rc in expect_rcs:
        sys.exit(f"docformatter failed: rc={rc}, cmd={cmd}")
