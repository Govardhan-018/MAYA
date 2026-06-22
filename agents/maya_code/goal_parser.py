"""v2 Goal Parser — parse natural language into structured goal with scope estimate.

One LLM call refines the goal, estimates complexity (S/M/L/XL), identifies
key files likely to be involved, and lists acceptance criteria.
"""

from __future__ import annotations

from agents.maya_code.contracts import (
    LLMGoalParseResponse,
    ParsedGoal,
    ProjectAnalysis,
    ScopeEstimate,
)
from agents.maya_code.models import LLMError, call_llm_structured


_GOAL_PARSER_SYSTEM = """\
Estimate the scope of a coding task. Respond with ONLY JSON:

{"refined": "clear description of goal", "scope": "M", "key_files": ["path/to/file"], "acceptance_criteria": ["criterion 1"]}

Scope values:
- "S" = 1-3 files, simple (bug fix, config change)
- "M" = 4-10 files, one feature
- "L" = 11-30 files, multi-module feature
- "XL" = 30+ files, full project or major rewrite

key_files = existing files from the project that will be read or modified.
acceptance_criteria = 3-5 conditions for when the goal is done.
"""


def parse_goal(goal: str, analysis: ProjectAnalysis) -> ParsedGoal:
    """Parse a raw goal string into a structured ``ParsedGoal``."""
    file_tree_preview = "\n".join(analysis.file_tree[:100])
    user_prompt = (
        f"## User Goal\n{goal}\n\n"
        f"## Project Type\n{analysis.project_type}\n\n"
        f"## Languages\n{', '.join(analysis.languages[:10])}\n\n"
        f"## Frameworks\n{', '.join(analysis.frameworks[:10])}\n\n"
        f"## Entry Points\n{', '.join(analysis.entry_points[:10])}\n\n"
        f"## File Tree\n{file_tree_preview}\n\n"
        f"## Dependency Files\n{', '.join(analysis.dependency_files[:10])}"
    )

    try:
        resp, _ = call_llm_structured(
            _GOAL_PARSER_SYSTEM, user_prompt, LLMGoalParseResponse
        )

        scope_str = resp.scope.upper().strip()
        try:
            scope = ScopeEstimate(scope_str)
        except ValueError:
            scope = ScopeEstimate.M

        return ParsedGoal(
            raw=goal,
            refined=resp.refined,
            scope=scope,
            key_files=resp.key_files[:20],
            acceptance_criteria=resp.acceptance_criteria[:10],
        )
    except LLMError:
        return ParsedGoal(
            raw=goal,
            refined=goal,
            scope=ScopeEstimate.M,
        )
