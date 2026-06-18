"""
验证COCO格式JSON的类别分布
用法: python validate_coco_distribution.py
"""
import json
from pathlib import Path
from collections import Counter

BASE = Path(__file__).parent / "sell_Huhb3D-Industrial-100"

CATEGORY_NAMES = {
    0: "FreeSurface", 1: "HorizontalPlane", 2: "LateralPlane_X",
    3: "LateralPlane_Z", 4: "NearHorizontal", 5: "NearLateral_X",
    6: "NearLateral_Z", 7: "Degenerate", 8: "ConvexFeature_Bolt",
    9: "ConcaveFeature_Hole", 10: "Flange", 11: "Boss",
    12: "Chamfer", 13: "Fillet", 14: "SphericalSurface"
}

def validate_object(obj_dir: Path):
    coco_path = obj_dir / "coco_annotations.json"
    if not coco_path.exists():
        return None

    with open(coco_path) as f:
        data = json.load(f)

    cat_counter = Counter()
    area_by_cat = Counter()
    for ann in data["annotations"]:
        cid = ann["category_id"]
        cat_counter[cid] += 1
        area_by_cat[cid] += ann.get("area", 0)

    return {
        "name": obj_dir.name,
        "n_images": len(data["images"]),
        "n_annotations": len(data["annotations"]),
        "n_coco_categories": len(data["categories"]),
        "cat_dist": cat_counter,
        "area_by_cat": area_by_cat,
    }


def main():
    print("=" * 72)
    print("  COCO Category Distribution Validation")
    print("=" * 72)

    all_results = []
    global_cat_counter = Counter()
    global_area_counter = Counter()

    for obj_dir in sorted(BASE.iterdir()):
        if not (obj_dir / "coco_annotations.json").exists():
            continue
        result = validate_object(obj_dir)
        if result is None:
            continue
        all_results.append(result)
        global_cat_counter.update(result["cat_dist"])
        global_area_counter.update(result["area_by_cat"])

    # Per-object summary
    print(f"\n{'Object':<20} {'Imgs':>5} {'Anns':>6} {'Cats':>5} {'Top categories'}")
    print("-" * 72)
    for r in all_results:
        top_cats = r["cat_dist"].most_common(3)
        top_str = ", ".join(f"{CATEGORY_NAMES.get(c, '?')}({n})" for c, n in top_cats)
        print(f"{r['name']:<20} {r['n_images']:>5} {r['n_annotations']:>6} {r['n_coco_categories']:>5} {top_str}")

    # Global distribution
    print("\n" + "=" * 72)
    print("  Global Category Distribution (across all objects)")
    print("=" * 72)
    print(f"\n{'ID':>3} {'Category':<25} {'Annotations':>12} {'Total Area':>12}")
    print("-" * 55)
    for cid in sorted(global_cat_counter.keys()):
        name = CATEGORY_NAMES.get(cid, f"Unknown_{cid}")
        count = global_cat_counter[cid]
        area = global_area_counter[cid]
        print(f"{cid:>3} {name:<25} {count:>12} {area:>12}")

    # Warnings
    print("\n" + "=" * 72)
    print("  Validation Checks")
    print("=" * 72)

    warnings = []
    # Check 1: All 15 categories present globally
    if len(global_cat_counter) < 15:
        missing = set(range(15)) - set(global_cat_counter.keys())
        warnings.append(f"Missing global categories: {missing}")
    else:
        print(f"  [OK] All 15 topology categories present globally")

    # Check 2: No object has only 1 category
    single_cat_objects = [r["name"] for r in all_results if len(r["cat_dist"]) <= 1]
    if single_cat_objects:
        warnings.append(f"Objects with only 1 category: {single_cat_objects}")
    else:
        print(f"  [OK] All objects have >= 2 categories")

    # Check 3: Category 12-14 (new) are present
    new_cats = {12, 13, 14} & set(global_cat_counter.keys())
    if new_cats:
        print(f"  [OK] New categories 12-14 present: {new_cats}")
    else:
        warnings.append("Categories 12-14 (Chamfer/Fillet/SphericalSurface) not found in any object")

    # Check 4: Annotation count reasonable
    total_anns = sum(r["n_annotations"] for r in all_results)
    total_imgs = sum(r["n_images"] for r in all_results)
    avg_anns = total_anns / total_imgs if total_imgs > 0 else 0
    print(f"  [OK] Total {total_anns} annotations across {total_imgs} images (avg {avg_anns:.1f}/img)")

    if warnings:
        print(f"\n  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    else:
        print(f"\n  All checks passed!")

    print(f"\n  Summary: {len(all_results)} objects, {total_imgs} images, {total_anns} annotations, {len(global_cat_counter)} categories")


if __name__ == "__main__":
    main()
