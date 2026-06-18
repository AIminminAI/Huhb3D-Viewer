import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from step_topology_parser import parse_step_topology

DATASET_DIR = Path(__file__).parent / "sell_Huhb3D-Industrial-100"
SOURCE_STEP_DIR = Path(__file__).parent / "original_models" / "step"
LINEAR_DEFLECTION = 0.01

step_files = sorted(SOURCE_STEP_DIR.glob("*.step"))
print(f"Found {len(step_files)} STEP files")

for i, step_path in enumerate(step_files, 1):
    obj_name = step_path.stem
    topology_hd_dir = DATASET_DIR / obj_name / "topology_hd"
    
    if (topology_hd_dir / "topology_labels.json").exists():
        print(f"[{i}/{len(step_files)}] {obj_name}: already exists, skipping")
        continue
    
    print(f"[{i}/{len(step_files)}] {obj_name}: parsing with deflection={LINEAR_DEFLECTION}")
    try:
        success = parse_step_topology(
            str(step_path),
            str(topology_hd_dir),
            linear_deflection=LINEAR_DEFLECTION,
            angular_deflection=0.5
        )
        if success:
            print(f"  OK")
        else:
            print(f"  FAILED")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\nDone! All high-resolution topology files generated.")
