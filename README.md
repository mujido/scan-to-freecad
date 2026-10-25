# scan-to-freecad

A Claude Code plugin that reverse-engineers a 3D-scanned physical part into a parametric FreeCAD PartDesign model. It takes a point cloud or mesh (PLY, ASC, XYZ, PCD, STL), optionally with photos and a reference STEP, and produces a spreadsheet-driven, fully constrained feature tree. An optional 3D-print-ready variant is included.

## Requirements

- **An AI agent that supports skills and MCP servers** (for example Claude Desktop, Claude Code, or Cursor). The skill reads scan files and runs FreeCAD's Python, so the agent needs file and shell access.
- **FreeCAD 1.x**, with its bundled Python (numpy, scipy, matplotlib included).
- **[FreeCAD MCP Bridge](https://github.com/CREATeNG/freecad-mcp-bridge)**. This is the FreeCAD addon plus its MCP connector, and it is what the skill uses to run code inside a live FreeCAD session. Install it before using this skill. The analysis scripts also run without it, as plain FreeCAD Python commands.

## Install

### Option 1: Claude Code plugin

This option is for Claude Code only. Type these commands in a Claude Code session:

```
/plugin marketplace add mujido/scan-to-freecad
/plugin install scan-to-freecad@scan-to-freecad
```

Update later with `/plugin marketplace update scan-to-freecad`.

### Option 2: Manual copy

Clone the repo and copy the skill folder into your agent's skills directory. For Claude Code, that is `~/.claude/skills/`:

```bash
git clone https://github.com/mujido/scan-to-freecad.git
cp -r scan-to-freecad/plugins/scan-to-freecad/skills/scan-to-freecad ~/.claude/skills/
```

On Windows, the Claude Code path is `%USERPROFILE%\.claude\skills\`. Other agents keep skills elsewhere, so check their documentation.

## What it does

1. **Load and align** the scan, and check mirror symmetry.
2. **Inventory features** from depth renders and cross-sections.
3. **Measure** holes, faces, bores and draft with region-based plane, cylinder and circle fits.
4. **Build** a FreeCAD model from one script: a `Params` spreadsheet of tunable knobs, plus named PartDesign features.
5. **Verify** the model against the scan with deviation maps and section overlays.
6. **Optionally** make a print-ready variant and check overhangs for the print orientation.

## Running the scripts

Run them as separate processes with FreeCAD's interpreter, not inside the GUI:

```bash
"C:\Program Files\FreeCAD 1.0\bin\python.exe" -I scripts/pcload.py --help
```

Every script prints its own `--help`. See `SKILL.md` for the full workflow and script table.

## Repository layout

| Path | Contents |
|---|---|
| `.claude-plugin/marketplace.json` | Marketplace catalog used by `/plugin marketplace add` |
| `plugins/scan-to-freecad/` | The plugin: manifest and skill |
| `plugins/scan-to-freecad/skills/scan-to-freecad/SKILL.md` | Skill definition and workflow (read by Claude) |
| `plugins/scan-to-freecad/skills/scan-to-freecad/scripts/` | Analysis and FreeCAD helper scripts |
| `plugins/scan-to-freecad/skills/scan-to-freecad/references/` | FreeCAD API pitfalls and printability notes |

## Verify your results

Check the output against your own measurements before relying on it, especially for functional surfaces and print fit.

## License

[MIT](LICENSE)
