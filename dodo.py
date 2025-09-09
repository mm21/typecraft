from doit.task import Task


def task_format() -> Task:
    """
    Run formatters.
    """

    autoflake_args = [
        "autoflake",
        "--remove-all-unused-imports",
        "--remove-unused-variables",
        "-i",
        "-r",
        ".",
    ]

    isort_args = [
        "isort",
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
            " ".join(autoflake_args),
            " ".join(isort_args),
            " ".join(black_args),
            " ".join(toml_sort_args),
        ],
        targets=[],
        file_dep=[],
    )
