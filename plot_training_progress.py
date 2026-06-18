import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "topology_segmentation"

epochs = list(range(1, 12))
train_loss = [1.8375, 1.7409, 1.7301, 1.7266, 1.7322, 1.7261, 1.7303, 1.7205, 1.7229, 1.7262, 1.6996]
train_acc = [0.3140, 0.3304, 0.3301, 0.3481, 0.3514, 0.3591, 0.3630, 0.3642, 0.3673, 0.3682, 0.3684]

val_epochs = [5, 10]
val_loss = [1.4623, 1.7016]
val_miou = [0.0665, 0.0300]
val_pixacc = [0.5391, 0.2384]

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Huhb3D Topology Segmentation - U-Net Training Progress\n(Epoch 11/50, Training in Progress)', fontsize=14, fontweight='bold')

ax1 = axes[0, 0]
ax1.plot(epochs, train_loss, 'b-o', label='Train Loss', markersize=4)
ax1.plot(val_epochs, val_loss, 'r-s', label='Val Loss', markersize=6)
ax1.set_xlabel('Epoch')
ax1.set_ylabel('Loss')
ax1.set_title('Training & Validation Loss')
ax1.legend()
ax1.grid(True, alpha=0.3)
ax1.set_ylim(1.4, 2.0)

ax2 = axes[0, 1]
ax2.plot(epochs, [a * 100 for a in train_acc], 'b-o', label='Train Accuracy', markersize=4)
ax2.plot(val_epochs, [a * 100 for a in val_pixacc], 'r-s', label='Val Pixel Accuracy', markersize=6)
ax2.set_xlabel('Epoch')
ax2.set_ylabel('Accuracy (%)')
ax2.set_title('Pixel Accuracy')
ax2.legend()
ax2.grid(True, alpha=0.3)
ax2.set_ylim(0, 70)

ax3 = axes[1, 0]
ax3.plot(val_epochs, [m * 100 for m in val_miou], 'r-s', label='Val mIoU', markersize=8)
ax3.axhline(y=10, color='g', linestyle='--', alpha=0.5, label='Target: 10%')
ax3.axhline(y=30, color='orange', linestyle='--', alpha=0.5, label='Good: 30%')
ax3.set_xlabel('Epoch')
ax3.set_ylabel('mIoU (%)')
ax3.set_title('Validation mIoU (Key Metric)')
ax3.legend()
ax3.grid(True, alpha=0.3)
ax3.set_ylim(0, 40)

ax4 = axes[1, 1]
ax4.axis('off')
info_text = (
    "Training Configuration\n"
    "─────────────────────\n"
    f"Model: U-Net (31M params)\n"
    f"Input: RGB(3ch) + Depth(1ch)\n"
    f"Output: 16 classes (15 topo + BG)\n"
    f"Train: 1600 frames | Val: 400\n"
    f"Batch: 4 | LR: 1e-3 | Optim: Adam\n"
    f"Image size: 400x300\n"
    f"Device: CUDA\n\n"
    "Current Status (Epoch 11)\n"
    "─────────────────────\n"
    f"Train Loss: 1.6996 ↓\n"
    f"Train Acc: 36.8% ↑\n"
    f"Best Val mIoU: 6.65% (Epoch 5)\n\n"
    "Diagnosis\n"
    "─────────────────────\n"
    "⚠ Val mIoU dropped at Epoch 10\n"
    "⚠ Possible overfitting\n"
    "⚠ Class imbalance: Boss dominates\n"
    "→ Need: class weights / focal loss\n"
    "→ Need: more diverse training data"
)
ax4.text(0.05, 0.95, info_text, transform=ax4.transAxes, fontsize=9,
         verticalalignment='top', fontfamily='monospace',
         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
plt.savefig(str(OUTPUT_DIR / "training_progress.png"), dpi=150, bbox_inches='tight')
print(f"Training progress chart saved to {OUTPUT_DIR / 'training_progress.png'}")
