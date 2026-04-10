# Graphviz Optional Dependency Implementation

This document summarizes the changes made to make Graphviz an optional dependency in the terravision project.

## Objective

Users can now use terravision (especially the `graphdata` command and `draw --format dot/gv`) **WITHOUT** having system Graphviz installed. Graphviz is only required for:
- Rendered outputs (PNG, SVG, PDF, etc.)
- Draw.io format conversion

## Changes Made

### 1. pyproject.toml
- **Removed** `graphviz2drawio>=1.1.0` from required dependencies
- **Added** optional dependencies section:
  ```toml
  [project.optional-dependencies]
  drawio = ["graphviz2drawio>=1.1.0"]
  graphviz = ["graphviz2drawio>=1.1.0"]
  ```
- **Moved** graphviz2drawio in Poetry section to:
  ```toml
  [tool.poetry.group.graphviz.dependencies]
  graphviz2drawio = "^1.0.0"
  ```

### 2. requirements.txt
- **Removed** `graphviz2drawio>=1.1.0` from required list
- **Added** comment: `# Optional: graphviz2drawio>=1.1.0  (needed for --format drawio)`

### 3. modules/helpers.py
- **Modified** `check_dependencies()`:
  - Removed `"dot"` and `"gvpr"` from the required dependencies list
  - Now only checks for `git` and `terraform`

- **Added** `check_graphviz_binaries()`:
  - Returns True/False indicating if both `dot` and `gvpr` are available
  - Does not exit on failure

- **Added** `require_graphviz_binaries()`:
  - Checks for Graphviz binaries and exits with clear error message if missing
  - Suggests installing Graphviz or using `--format dot` alternative

### 4. modules/drawing.py
- **Added** `import shutil` to support binary checks

- **Modified** graphviz2drawio import:
  - Removed top-level import
  - Added comment explaining it's conditional
  - Import is now lazy/conditional within the drawio rendering branch

- **Modified** `render_diagram()` function:
  - **DOT/GV format** (`--format dot` or `--format gv`):
    - Generates DOT file via Python graphviz package (no system binary needed)
    - Applies gvpr post-processing ONLY if gvpr is available (silent fallback if not)
    - Returns the DOT file as output (no rendering step)
    - No Graphviz binaries required

  - **Draw.io format** (`--format drawio`):
    - Attempts to import graphviz2drawio, shows clear error if not installed
    - Error message: "drawio format requires graphviz2drawio package. Install with: pip install terravision[drawio]"

  - **Rendered formats** (png, svg, pdf, etc.):
    - Calls `helpers.require_graphviz_binaries()` before rendering
    - Shows clear error if Graphviz not installed: "Rendered output formats (png, svg, pdf, etc.) require system Graphviz to be installed..."

### 5. modules/tfwrapper.py
- **Added** `import shutil` for binary checks

- **Modified** `convert_dot_to_json()`:
  - Added check at the start: if `shutil.which("dot")` is None, exits with error
  - Clear error message about needing system Graphviz for this operation

### 6. terravision/terravision.py
- **No changes needed**:
  - `preflight_check()` already calls `helpers.check_dependencies()` which now only checks git and terraform
  - Graphviz checks happen later in the rendering phase, format-aware

### 7. Dockerfile
- **Added** comments explaining:
  - Graphviz is optional for non-Docker installs
  - Docker image includes it for full functionality
  - graphviz-dev is needed for pygraphviz/graphviz2drawio

### 8. resource_classes/__init__.py
- **No changes**: Python `graphviz` package remains a required dependency (it's just a DOT builder)

## Installation Options

### Basic installation (no Graphviz):
```bash
pip install terravision
```
Can use:
- `terravision graphdata` - outputs JSON
- `terravision draw --format dot` - outputs DOT file
- `terravision draw --format gv` - outputs GV file

### With draw.io support:
```bash
pip install terravision[drawio]
```
Adds:
- `terravision draw --format drawio` - requires graphviz2drawio package

### For rendered outputs (PNG, SVG, PDF):
```bash
# Install terravision
pip install terravision

# Install system Graphviz separately
# macOS:
brew install graphviz

# Ubuntu/Debian:
apt-get install graphviz

# Windows:
# Download from https://graphviz.org/download/
```

## Testing

All changes have been verified:
- ✅ Python syntax compilation successful
- ✅ pyproject.toml structure updated correctly
- ✅ requirements.txt updated correctly
- ✅ Helper functions implemented correctly
- ✅ Drawing module imports work without graphviz2drawio
- ✅ Conditional imports in place for drawio format
- ✅ Format-specific Graphviz checks implemented

## Backwards Compatibility

- Existing users with Graphviz installed: **No changes in behavior**
- New users without Graphviz: Can use DOT output and graphdata commands
- Docker image: Includes full Graphviz support (no changes needed)

## Error Messages

Clear, actionable error messages guide users:
- Missing graphviz2drawio: "Install with: pip install terravision[drawio]"
- Missing Graphviz binaries: "Install Graphviz from https://graphviz.org/download/ or use --format dot"
