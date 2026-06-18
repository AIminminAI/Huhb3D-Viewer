# Huhb3D — 3D Geometry Analyzer MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()

> An MCP Server that lets AI agents (Claude, Cursor, ChatGPT) analyze 3D models through natural language. Check mesh quality, detect defects, verify 3D printability, and generate geometry reports.

---

## What This Does

Ask your AI assistant about any 3D model:

```
You: "Check if this STL file is printable on my FDM printer"
Claude: *calls check_3d_printability tool* -> "Your model has 2 issues: 
  1. Not watertight (3 holes found) - CRITICAL
  2. Wall thickness 0.4mm is below FDM minimum 0.8mm - WARNING"

You: "What's wrong with this mesh?"
Claude: *calls detect_defects tool* -> "Found 4 defects: 
  - 12 degenerate faces (zero area) 
  - 3 non-manifold edges
  - 1 flipped normal
  - 2 disconnected components"
```

This is a **3D model quality inspector for AI agents**, not a CAD tool.

---

## Quick Start

### Install

```bash
pip install huhb3d-mcp
```

### Configure with Claude Desktop

Add to your Claude Desktop config (`~/AppData/Roaming/Claude/claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "huhb3d": {
      "command": "uvx",
      "args": ["huhb3d-mcp"]
    }
  }
}
```

### Configure with Cursor

Add to your Cursor MCP settings:

```json
{
  "mcpServers": {
    "huhb3d": {
      "command": "uvx",
      "args": ["huhb3d-mcp"]
    }
  }
}
```

### Use

Just talk to your AI assistant about 3D files:

- "Analyze this STL file: C:/models/part.stl"
- "Is this mesh watertight?"
- "Check if this model is 3D printable"
- "Compare these two meshes"
- "Generate a quality report for this model"

---

## Available Tools

| Tool | What it does |
|------|-------------|
| **analyze_mesh** | Multi-type mesh analysis: watertight, volume, surface area, bounding box, euler number, thickness, defects |
| **check_3d_printability** | 3D print suitability check for FDM or SLA printers |
| **compute_geometry** | Compute geometry metrics: volume, centroid, inertia, principal axes, convex hull, compactness |
| **detect_defects** | Find mesh defects: non-manifold edges, degenerate faces, flipped normals, thin walls, self-intersections |
| **compare_meshes** | Compare two meshes: volume diff, surface area diff, Hausdorff distance |
| **generate_report** | Generate comprehensive analysis report (summary or detailed) |

---

## Architecture

```
AI Agent (Claude/Cursor/ChatGPT)
  |
  v
MCP Protocol
  |
  v
huhb3d-mcp Server
  |
  +-- analyze_mesh()      -> trimesh + numpy
  +-- check_3d_printability() -> trimesh + custom rules
  +-- compute_geometry()  -> trimesh + numpy
  +-- detect_defects()    -> trimesh + custom checks
  +-- compare_meshes()    -> trimesh + scipy
  +-- generate_report()   -> combines all above
```

---

## Also Includes: C++ 3D Engine + LLM Agent

Beyond the MCP Server, this project also contains:

- **C++17 3D geometry engine** with BVH acceleration, STL parsing, OpenGL rendering
- **C++ native LLM Function Calling** implementation (EmbodiedAIAgent)
- **Synthetic data pipeline** for robotics 6DoF pose estimation
- **Grasp semantic labeling** for robot pick-and-place

See [mcp_server/README.md](mcp_server/README.md) for MCP Server details.

---

## Project Structure

```
mcp_server/           -- MCP Server (pip install huhb3d-mcp)
  server.py           -- 6 MCP tools for 3D analysis
  pyproject.toml      -- Package config
  config_example.json -- Claude Desktop config
src/                  -- C++ 3D engine
  core/               -- BVH, STL parser, Geometry API, LLM client
  render/             -- OpenGL renderer + ImGui
  agent/              -- AI Agent controller
app.py                -- Streamlit data generation UI
api/                  -- FastAPI REST API
```

---

## License

MIT License -- free for personal and commercial use.