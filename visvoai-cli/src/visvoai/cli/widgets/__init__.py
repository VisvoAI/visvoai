"""Reusable visvoai TUI widgets. Each component owns its styling (DEFAULT_CSS)."""

from visvoai.cli.widgets.conversation import (
    Assistant,
    Thinking,
    TurnFooter,
    UserMsg,
    WorkingIndicator,
)
from visvoai.cli.widgets.welcome import Welcome, WelcomeBanner
from visvoai.cli.widgets.citation import Citation
from visvoai.cli.widgets.diff import CleanDiff
from visvoai.cli.widgets.error import ErrorBlock
from visvoai.cli.widgets.file_creation import FileCreation
from visvoai.cli.widgets.form import Form
from visvoai.cli.widgets.free_text import FreeText
from visvoai.cli.widgets.output import ShowMore, ToolOutput
from visvoai.cli.widgets.output_toolbar import (
    OutputToolbar,
    SearchInput,
    SearchRow,
    find_first_failure,
)
from visvoai.cli.widgets.mermaid_card import MermaidCard
from visvoai.cli.widgets.plan import Plan
from visvoai.cli.widgets.read_chain import ReadChainGroup
from visvoai.cli.widgets.reconciliation import ReconciliationBlock
from visvoai.cli.widgets.streaming_output import StreamingOutput
from visvoai.cli.widgets.selection import Selection
from visvoai.cli.widgets.severity_output import SeverityOutput, WarningFold, classify
from visvoai.cli.widgets.structure_tree import StructureTree, TreeRow
from visvoai.cli.widgets.status import StatusBar
from visvoai.cli.widgets.system_note import CompactionMarker, SystemNote
from visvoai.cli.widgets.tool_row import (
    ToolErrorBody,
    ToolGroup,
    ToolNode,
    ToolRow,
    verb_for,
)

__all__ = [
    "Welcome",
    "WelcomeBanner",
    "UserMsg",
    "Assistant",
    "Thinking",
    "TurnFooter",
    "WorkingIndicator",
    "ToolRow",
    "ToolNode",
    "ToolGroup",
    "ToolErrorBody",
    "verb_for",
    "CleanDiff",
    "ErrorBlock",
    "Citation",
    "FileCreation",
    "StructureTree",
    "TreeRow",
    "ToolOutput",
    "ShowMore",
    "OutputToolbar",
    "SearchInput",
    "SearchRow",
    "find_first_failure",
    "StreamingOutput",
    "MermaidCard",
    "Plan",
    "ReadChainGroup",
    "ReconciliationBlock",
    "Selection",
    "SeverityOutput",
    "WarningFold",
    "classify",
    "Form",
    "FreeText",
    "StatusBar",
    "SystemNote",
    "CompactionMarker",
]
