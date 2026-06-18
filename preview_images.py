"""Generate HTML preview page for product images."""
import base64
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()


def generate_preview(image_dir: Path, output_path: Path, title: str = "Image Preview"):
    images = sorted(image_dir.glob("*.png")) + sorted(image_dir.glob("*.jpg"))
    if not images:
        print(f"No images found in {image_dir}")
        return

    print(f"Found {len(images)} images")

    cards = []
    for img_path in images:
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = img_path.suffix.lstrip(".")
        mime = f"image/{'jpeg' if ext == 'jpg' else 'png'}"
        cards.append(f"""
        <div class="card">
            <h3>{img_path.name}</h3>
            <img src="data:{mime};base64,{b64}" alt="{img_path.name}" />
            <p class="meta">{img_path.stat().st_size / 1024:.1f} KB</p>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #c9d1d9; padding: 20px; }}
h1 {{ text-align: center; padding: 20px 0; color: #58a6ff;
     font-size: 1.5em; border-bottom: 1px solid #21262d; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
        gap: 20px; max-width: 1400px; margin: 0 auto; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
        padding: 16px; }}
.card h3 {{ color: #58a6ff; margin-bottom: 10px; font-size: 0.95em; }}
.card img {{ width: 100%; border-radius: 4px; }}
.card .meta {{ color: #8b949e; font-size: 0.8em; margin-top: 8px; }}
.footer {{ text-align: center; color: #484f58; margin-top: 30px; font-size: 0.8em; }}
</style>
</head>
<body>
<h1>{title} ({len(images)} images)</h1>
<div class="grid">
{''.join(cards)}
</div>
<div class="footer">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Preview saved: {output_path}")
    print(f"Open in browser: file:///{output_path.as_posix()}")


if __name__ == "__main__":
    generate_preview(
        SCRIPT_DIR / "product_images",
        SCRIPT_DIR / "product_images_preview.html",
        "Huhb3D Product Images"
    )

    # Also generate preview for vis_output
    vis_dir = SCRIPT_DIR / "vis_output"
    if vis_dir.exists():
        generate_preview(
            vis_dir,
            SCRIPT_DIR / "vis_output_preview.html",
            "Huhb3D Dataset Samples (RGB / Mask / Depth)"
        )
