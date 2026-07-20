from dataclasses import replace

from pyprojkit import DocConfig, ProjectConfig, PythonVersions, ToolsConfig

config = ProjectConfig(
    package="typecraft",
    python=PythonVersions(3, (12, 13)),
    tools=replace(ToolsConfig.default(), doc=DocConfig(mkinit=None)),
)
