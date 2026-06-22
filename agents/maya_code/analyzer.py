"""Project analyzer — detects type, languages, test runners, structure.

Combines heuristic file-system scanning with an optional LLM pass for
deeper analysis.  The heuristic pass is always run first so the LLM gets
real project state injected, not hallucinated context.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agents.maya_code.contracts import LLMAnalysisResponse, ProjectAnalysis

# ── extension → language mapping ──────────────────────────────────────────────
_EXT_LANG: dict[str, str] = {
    ".py": "Python", ".pyw": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".h": "C/C++", ".hpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".r": "R", ".R": "R",
    ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
}

# ── indicator files → project type / framework ───────────────────────────────
_INDICATORS: list[tuple[str, str, str]] = [
    ("package.json",     "node",    "Node.js"),
    ("tsconfig.json",    "node",    "TypeScript"),
    ("requirements.txt", "python",  "Python"),
    ("setup.py",         "python",  "Python"),
    ("pyproject.toml",   "python",  "Python"),
    ("Pipfile",          "python",  "Python"),
    ("Cargo.toml",       "rust",    "Rust"),
    ("go.mod",           "go",      "Go"),
    ("pom.xml",          "java",    "Java/Maven"),
    ("build.gradle",     "java",    "Java/Gradle"),
    ("Gemfile",          "ruby",    "Ruby"),
    ("composer.json",    "php",     "PHP"),
    ("Makefile",         "make",    "Make"),
    ("CMakeLists.txt",   "cmake",   "CMake"),
    (".sln",             "dotnet",  ".NET"),
    ("mix.exs",          "elixir",  "Elixir"),
]

_TEST_RUNNERS: dict[str, tuple[str, str]] = {
    "python":  ("pytest", "pytest"),
    "node":    ("jest",   "npx jest"),
    "rust":    ("cargo",  "cargo test"),
    "go":      ("go",     "go test ./..."),
    "java":    ("maven",  "mvn test"),
    "ruby":    ("rspec",  "bundle exec rspec"),
    "dotnet":  ("dotnet", "dotnet test"),
}

_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "env", ".env", ".tox", "dist", "build", ".next",
    "target", ".idea", ".vscode", ".maya_checkpoints",
})

MAX_TREE_FILES: int = 300
MAX_TREE_DEPTH: int = 4


def analyze_project(project_root: Path) -> ProjectAnalysis:
    """Heuristic scan of the project at *project_root*."""
    languages: set[str] = set()
    frameworks: list[str] = []
    dep_files: list[str] = []
    entry_points: list[str] = []
    file_tree: list[str] = []
    project_type = "unknown"
    build_tool: str | None = None
    test_runner: str | None = None
    test_command: str | None = None

    for indicator_file, ptype, fw in _INDICATORS:
        if (project_root / indicator_file).exists():
            project_type = ptype
            if fw not in frameworks:
                frameworks.append(fw)
            dep_files.append(indicator_file)

    count = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        rel_dir = os.path.relpath(dirpath, project_root)
        depth = rel_dir.count(os.sep) if rel_dir != "." else 0
        if depth > MAX_TREE_DEPTH:
            dirnames.clear()
            continue

        for fname in filenames:
            count += 1
            if count > MAX_TREE_FILES:
                break
            rel = os.path.join(rel_dir, fname) if rel_dir != "." else fname
            file_tree.append(rel.replace("\\", "/"))

            ext = os.path.splitext(fname)[1].lower()
            lang = _EXT_LANG.get(ext)
            if lang:
                languages.add(lang)

            if fname in ("main.py", "app.py", "index.js", "index.ts", "main.go", "main.rs", "Main.java"):
                entry_points.append(rel.replace("\\", "/"))

        if count > MAX_TREE_FILES:
            break

    if project_type in _TEST_RUNNERS:
        test_runner, test_command = _TEST_RUNNERS[project_type]

    if (project_root / "Makefile").exists():
        build_tool = "make"
    elif (project_root / "CMakeLists.txt").exists():
        build_tool = "cmake"

    return ProjectAnalysis(
        project_type=project_type,
        languages=sorted(languages),
        frameworks=frameworks,
        build_tool=build_tool,
        test_runner=test_runner,
        test_command=test_command,
        entry_points=entry_points,
        file_tree=sorted(file_tree)[:MAX_TREE_FILES],
        dependency_files=dep_files,
    )


def format_analysis_for_llm(analysis: ProjectAnalysis) -> str:
    """Format project analysis as compact text for LLM context injection."""
    lines = [
        f"Project type: {analysis.project_type}",
        f"Languages: {', '.join(analysis.languages) or 'unknown'}",
        f"Frameworks: {', '.join(analysis.frameworks) or 'none detected'}",
    ]
    if analysis.build_tool:
        lines.append(f"Build tool: {analysis.build_tool}")
    if analysis.test_runner:
        lines.append(f"Test runner: {analysis.test_runner} ({analysis.test_command})")
    if analysis.entry_points:
        lines.append(f"Entry points: {', '.join(analysis.entry_points[:5])}")
    if analysis.dependency_files:
        lines.append(f"Dependency files: {', '.join(analysis.dependency_files)}")
    lines.append(f"File tree ({len(analysis.file_tree)} files):")
    for f in analysis.file_tree[:60]:
        lines.append(f"  {f}")
    if len(analysis.file_tree) > 60:
        lines.append(f"  ... and {len(analysis.file_tree) - 60} more")
    return "\n".join(lines)
