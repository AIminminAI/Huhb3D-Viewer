import json
import os
import sys
import time
from pathlib import Path

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
except ImportError:
    print("ERROR: PyTorch is not installed.")
    print("Install with: pip install torch torchvision")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("ERROR: NumPy is not installed.")
    print("Install with: pip install numpy")
    sys.exit(1)

try:
    import cv2
except ImportError:
    print("ERROR: OpenCV is not installed.")
    print("Install with: pip install opencv-python")
    sys.exit(1)

from topology_segmentation_task import (
    TopologySegmentationDataset,
    evaluate_segmentation,
    visualize_segmentation,
    CATEGORY_NAMES,
    NUM_CLASSES,
    IGNORE_INDEX,
    IMAGE_WIDTH,
    IMAGE_HEIGHT,
)

DATASET_DIR = Path(__file__).parent / "sell_Huhb3D-Industrial-100"
OUTPUT_DIR = Path(__file__).parent / "topology_segmentation"

BATCH_SIZE = 4
LEARNING_RATE = 1e-4
NUM_EPOCHS = 30
TARGET_SIZE = (400, 300)
VALIDATION_FREQ = 3
NUM_WORKERS = 0


class DoubleConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)


class DownBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.pool = nn.MaxPool2d(2)
        self.conv = DoubleConv(in_ch, out_ch)

    def forward(self, x):
        x = self.pool(x)
        x = self.conv(x)
        return x


class UpBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.up = nn.ConvTranspose2d(in_ch, in_ch // 2, kernel_size=2, stride=2)
        self.conv = DoubleConv(in_ch, out_ch)

    def forward(self, x, skip):
        x = self.up(x)
        diff_h = skip.size(2) - x.size(2)
        diff_w = skip.size(3) - x.size(3)
        x = nn.functional.pad(x, [diff_w // 2, diff_w - diff_w // 2,
                                   diff_h // 2, diff_h - diff_h // 2])
        x = torch.cat([skip, x], dim=1)
        x = self.conv(x)
        return x


class TopologyUNet(nn.Module):
    def __init__(self, in_channels=4, num_classes=NUM_CLASSES):
        super().__init__()
        self.inc = DoubleConv(in_channels, 64)
        self.down1 = DownBlock(64, 128)
        self.down2 = DownBlock(128, 256)
        self.down3 = DownBlock(256, 512)
        self.down4 = DownBlock(512, 1024)
        self.up1 = UpBlock(1024, 512)
        self.up2 = UpBlock(512, 256)
        self.up3 = UpBlock(256, 128)
        self.up4 = UpBlock(128, 64)
        self.outc = nn.Conv2d(64, num_classes, kernel_size=1)

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)
        x = self.outc(x)
        return x


def train_one_epoch(model, dataloader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    total_pixels = 0
    correct_pixels = 0
    for batch_idx, (inputs, targets) in enumerate(dataloader):
        inputs = inputs.to(device)
        targets = targets.to(device)
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * inputs.size(0)
        pred = outputs.argmax(dim=1)
        valid = targets != IGNORE_INDEX
        correct_pixels += (pred[valid] == targets[valid]).sum().item()
        total_pixels += valid.sum().item()

    avg_loss = total_loss / max(len(dataloader.dataset), 1)
    pixel_acc = correct_pixels / max(total_pixels, 1)
    return avg_loss, pixel_acc


def validate(model, dataloader, criterion, device):
    model.eval()
    total_loss = 0.0
    all_preds = []
    all_targets = []
    with torch.no_grad():
        for inputs, targets in dataloader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            total_loss += loss.item() * inputs.size(0)
            pred = outputs.argmax(dim=1)
            all_preds.append(pred.cpu().numpy())
            all_targets.append(targets.cpu().numpy())

    avg_loss = total_loss / max(len(dataloader.dataset), 1)
    all_preds = np.concatenate([p.flatten() for p in all_preds])
    all_targets = np.concatenate([t.flatten() for t in all_targets])
    metrics = evaluate_segmentation(all_preds, all_targets, NUM_CLASSES, IGNORE_INDEX)
    return avg_loss, metrics


def save_prediction_comparison(model, dataset, device, output_dir, num_samples=5):
    model.eval()
    pred_dir = output_dir / "topology_predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)

    indices = list(range(min(num_samples, len(dataset))))
    for idx in indices:
        inputs, gt = dataset[idx]
        with torch.no_grad():
            input_batch = inputs.unsqueeze(0).to(device)
            output = model(input_batch)
            pred = output.argmax(dim=1).squeeze(0).cpu().numpy()

        gt_np = gt.numpy()
        gt_vis = visualize_segmentation(gt_np)
        pred_vis = visualize_segmentation(pred)

        if gt_vis is not None and pred_vis is not None:
            gt_vis_bgr = cv2.cvtColor(gt_vis, cv2.COLOR_RGB2BGR)
            pred_vis_bgr = cv2.cvtColor(pred_vis, cv2.COLOR_RGB2BGR)
            h, w = gt_vis_bgr.shape[:2]
            border = np.ones((h, 3, 3), dtype=np.uint8) * 128
            combined = np.concatenate([gt_vis_bgr, border, pred_vis_bgr], axis=1)
            cv2.imwrite(str(pred_dir / f"comparison_{idx:04d}.png"), combined)


def main():
    print("=" * 60)
    print("Topology Segmentation - U-Net Baseline Training")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    print(f"\nDataset directory: {DATASET_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Learning rate: {LEARNING_RATE}")
    print(f"Epochs: {NUM_EPOCHS}")
    print(f"Target size: {TARGET_SIZE}")

    print("\nLoading training dataset...")
    train_dataset = TopologySegmentationDataset(
        DATASET_DIR, split="train", train_ratio=0.8,
        target_size=TARGET_SIZE, augment=True,
    )
    print(f"Training samples: {len(train_dataset)}")

    print("Loading validation dataset...")
    val_dataset = TopologySegmentationDataset(
        DATASET_DIR, split="val", train_ratio=0.8,
        target_size=TARGET_SIZE, augment=False,
    )
    print(f"Validation samples: {len(val_dataset)}")

    if len(train_dataset) == 0:
        alt_dir = Path(__file__).parent / "sell_Huhb3D-Industrial-100"
        print(f"\nPrimary dataset empty, trying alternative: {alt_dir}")
        if alt_dir.exists():
            train_dataset = TopologySegmentationDataset(
                alt_dir, split="train", train_ratio=0.8,
                target_size=TARGET_SIZE, augment=True,
            )
            val_dataset = TopologySegmentationDataset(
                alt_dir, split="val", train_ratio=0.8,
                target_size=TARGET_SIZE, augment=False,
            )
            print(f"Training samples: {len(train_dataset)}")
            print(f"Validation samples: {len(val_dataset)}")

    if len(train_dataset) == 0:
        print("ERROR: No training data found. Check dataset directory.")
        sys.exit(1)

    train_loader = DataLoader(
        train_dataset, batch_size=BATCH_SIZE, shuffle=True,
        num_workers=NUM_WORKERS, pin_memory=True if device.type == "cuda" else False,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=NUM_WORKERS, pin_memory=True if device.type == "cuda" else False,
    )

    model = TopologyUNet(in_channels=4, num_classes=NUM_CLASSES).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nModel: TopologyUNet")
    print(f"Total parameters: {total_params:,}")
    print(f"Trainable parameters: {trainable_params:,}")

    class_weights = torch.ones(NUM_CLASSES, dtype=torch.float32)
    class_weights[0] = 5.0
    class_weights[1] = 20.0
    class_weights[2] = 15.0
    class_weights[3] = 10.0
    class_weights[4] = 30.0
    class_weights[5] = 25.0
    class_weights[6] = 30.0
    class_weights[7] = 30.0
    class_weights[8] = 20.0
    class_weights[9] = 20.0
    class_weights[10] = 15.0
    class_weights[11] = 3.0
    class_weights[12] = 20.0
    class_weights[13] = 25.0
    class_weights[14] = 25.0
    class_weights[15] = 1.0
    class_weights = class_weights.to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights, ignore_index=IGNORE_INDEX)
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=5)

    best_miou = 0.0
    training_log = []

    print("\nStarting training...")
    for epoch in range(1, NUM_EPOCHS + 1):
        start_time = time.time()
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device)
        elapsed = time.time() - start_time

        log_entry = {
            "epoch": epoch,
            "train_loss": round(train_loss, 6),
            "train_pixel_accuracy": round(train_acc, 6),
            "learning_rate": optimizer.param_groups[0]["lr"],
            "elapsed_seconds": round(elapsed, 2),
        }

        if epoch % VALIDATION_FREQ == 0 or epoch == NUM_EPOCHS:
            val_loss, val_metrics = validate(model, val_loader, criterion, device)
            log_entry["val_loss"] = round(val_loss, 6)
            log_entry["val_mIoU"] = round(val_metrics["mIoU"], 6)
            log_entry["val_pixel_accuracy"] = round(val_metrics["pixel_accuracy"], 6)
            log_entry["val_fw_IoU"] = round(val_metrics["frequency_weighted_IoU"], 6)

            per_class_str = {}
            for cls_id, iou_val in val_metrics["per_class_IoU"].items():
                name = CATEGORY_NAMES.get(cls_id, f"Class_{cls_id}")
                per_class_str[name] = round(iou_val, 6) if iou_val is not None else None
            log_entry["val_per_class_IoU"] = per_class_str

            scheduler.step(val_loss)

            print(f"Epoch {epoch:3d}/{NUM_EPOCHS} | "
                  f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f} | "
                  f"Val Loss: {val_loss:.4f} | Val mIoU: {val_metrics['mIoU']:.4f} | "
                  f"Val PixAcc: {val_metrics['pixel_accuracy']:.4f} | "
                  f"Time: {elapsed:.1f}s")

            if val_metrics["mIoU"] > best_miou:
                best_miou = val_metrics["mIoU"]
                best_model_path = OUTPUT_DIR / "topology_unet_best.pth"
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "best_miou": best_miou,
                    "num_classes": NUM_CLASSES,
                    "in_channels": 4,
                }, str(best_model_path))
                print(f"  -> Best model saved (mIoU={best_miou:.4f})")
        else:
            print(f"Epoch {epoch:3d}/{NUM_EPOCHS} | "
                  f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f} | "
                  f"Time: {elapsed:.1f}s")

        training_log.append(log_entry)

    log_path = OUTPUT_DIR / "topology_training_log.json"
    with open(str(log_path), 'w', encoding='utf-8') as f:
        json.dump({
            "config": {
                "batch_size": BATCH_SIZE,
                "learning_rate": LEARNING_RATE,
                "num_epochs": NUM_EPOCHS,
                "target_size": list(TARGET_SIZE),
                "num_classes": NUM_CLASSES,
                "ignore_index": IGNORE_INDEX,
                "dataset_dir": str(DATASET_DIR),
                "device": str(device),
                "total_params": total_params,
            },
            "best_miou": round(best_miou, 6),
            "training_log": training_log,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nTraining log saved: {log_path}")

    print("\nGenerating prediction visualizations...")
    save_prediction_comparison(model, val_dataset, device, OUTPUT_DIR, num_samples=10)

    print("\n" + "=" * 60)
    print(f"Training complete. Best mIoU: {best_miou:.4f}")
    print(f"Model: {OUTPUT_DIR / 'topology_unet_best.pth'}")
    print(f"Log: {log_path}")
    print(f"Predictions: {OUTPUT_DIR / 'topology_predictions'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
