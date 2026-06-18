# Huhb3D MCP Server - 3D Mesh Quality Inspector for AI Agents

> **NOT a CAD tool.** This is a 3D model quality inspector designed for robotics and 3D printing workflows. It analyzes existing mesh files — it does not create or modify geometry.

## What It Does

Huhb3D MCP Server exposes 3D mesh analysis capabilities through the Model Context Protocol (MCP), allowing AI agents (Claude, Cursor, etc.) to inspect and validate 3D models via natural language.

Typical use cases:
- "Is this STL file watertight enough for 3D printing?"
- "Compare these two mesh files and tell me the differences"
- "Find all defects in this OBJ model"
- "Generate a quality report for this GLB file"

## Installation

```bash
pip install huhb3d-mcp
```

Or using uvx (recommended for MCP clients):

```bash
uvx huhb3d-mcp
```

## Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

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

### Cursor

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

## Available Tools

### 1. `analyze_mesh`

Analyze a 3D mesh file with specified analysis types.

```
Analysis types: watertight, volume, surface_area, bounding_box, euler_number, thickness, defects
```

**Example prompt:** "Analyze C:/models/part.stl for watertightness and volume"

### 2. `check_3d_printability`

Check if a model is suitable for 3D printing (FDM or SLA).

**Example prompt:** "Check if C:/models/robot_arm.stl is printable on an FDM printer"

### 3. `compute_geometry`

Compute geometric metrics for a mesh.

```
Metrics: volume, surface_area, centroid, moment_of_inertia, principal_axes, convex_hull_volume, compactness
```

**Example prompt:** "Compute the centroid and moment of inertia for C:/models/bracket.obj"

### 4. `detect_defects`

Detect mesh defects with severity levels.

**Example prompt:** "Find all defects in C:/models/scan.glb"

### 5. `compare_meshes`

Compare two mesh files and return difference metrics.

**Example prompt:** "Compare C:/models/original.stl and C:/models/modified.stl"

### 6. `generate_report`

Generate a comprehensive analysis report (summary or detailed).

**Example prompt:** "Generate a detailed report for C:/models/gear.stl"

## Supported File Formats

- STL (ASCII and Binary)
- OBJ
- GLB / GLTF

## Disclaimer

This tool is a **mesh quality inspector**, not a CAD application. It reads and analyzes 3D model files but does not create, edit, or modify geometry. It is designed for quality assurance in robotics and 3D printing workflows.
