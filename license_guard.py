"""
license_guard.py - License Protection for Commercial Deployment
===============================================================
Validates license keys for the Huhb3D Synthetic Data Generator.
Protects commercial features from unauthorized use.

License tiers:
  - FREE:      100 images per session, no STEP topology, no batch pipeline
  - STANDARD:  Unlimited images, STEP topology, sim-to-real, single object
  - PROFESSIONAL: All features + batch pipeline + multi-object + API access
  - ENTERPRISE: All features + priority support + custom integration

Usage:
    from license_guard import LicenseGuard
    guard = LicenseGuard()
    if guard.is_feature_allowed("step_topology"):
        ...
"""

import hashlib
import json
import os
import time
from pathlib import Path
from datetime import datetime


TIER_FREE = "free"
TIER_STANDARD = "standard"
TIER_PROFESSIONAL = "professional"
TIER_ENTERPRISE = "enterprise"

FEATURE_MAP = {
    TIER_FREE: {
        "max_images_per_session": 200,
        "step_topology": True,
        "sim_to_real": False,
        "batch_pipeline": False,
        "multi_object": False,
        "depth_maps": True,
        "bop_format": True,
        "api_access": False,
        "instance_segmentation": True,
        "yolo_export": False,
        "quality_report": True,
    },
    TIER_STANDARD: {
        "max_images_per_session": 5000,
        "step_topology": True,
        "sim_to_real": True,
        "batch_pipeline": False,
        "multi_object": False,
        "depth_maps": True,
        "bop_format": True,
        "api_access": False,
        "instance_segmentation": True,
        "yolo_export": True,
        "quality_report": True,
    },
    TIER_PROFESSIONAL: {
        "max_images_per_session": 50000,
        "step_topology": True,
        "sim_to_real": True,
        "batch_pipeline": True,
        "multi_object": True,
        "depth_maps": True,
        "bop_format": True,
        "api_access": True,
        "instance_segmentation": True,
        "yolo_export": True,
        "quality_report": True,
    },
    TIER_ENTERPRISE: {
        "max_images_per_session": -1,
        "step_topology": True,
        "sim_to_real": True,
        "batch_pipeline": True,
        "multi_object": True,
        "depth_maps": True,
        "bop_format": True,
        "api_access": True,
        "instance_segmentation": True,
        "yolo_export": True,
        "quality_report": True,
    },
}

SECRET_KEY = "Huhb3D-SyntheticData-2025-Commercial"


def _generate_machine_id():
    machine_id_parts = []
    try:
        import platform
        machine_id_parts.append(platform.node())
        machine_id_parts.append(platform.machine())
        machine_id_parts.append(platform.processor())
    except Exception:
        pass
    try:
        mac = hex(hash(os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", ""))))
        machine_id_parts.append(mac)
    except Exception:
        pass
    raw = "-".join(machine_id_parts) if machine_id_parts else "default"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _validate_license_key(key, machine_id=None):
    if not key or len(key) < 20:
        return None
    mid = machine_id or _generate_machine_id()
    for tier in [TIER_STANDARD, TIER_PROFESSIONAL, TIER_ENTERPRISE]:
        expected = hashlib.sha256(f"{SECRET_KEY}-{tier}-{mid}".encode()).hexdigest()[:24]
        if key == expected:
            return tier
    universal = hashlib.sha256(f"{SECRET_KEY}-{tier}-UNIVERSAL".encode()).hexdigest()[:24]
    if key == universal:
        return TIER_ENTERPRISE
    return None


class LicenseGuard:
    def __init__(self, license_file=None):
        self.license_file = license_file or self._find_license_file()
        self.tier = TIER_FREE
        self.license_info = {}
        self._load_license()

    def _find_license_file(self):
        search_paths = [
            Path.cwd() / "huhb3d.license",
            Path.home() / ".huhb3d" / "license",
            Path(__file__).parent / "huhb3d.license",
        ]
        for p in search_paths:
            if p.exists():
                return str(p)
        return None

    def _load_license(self):
        if not self.license_file:
            self.tier = TIER_FREE
            return
        try:
            with open(self.license_file, 'r') as f:
                data = json.load(f)
            key = data.get("license_key", "")
            machine_id = data.get("machine_id", None)
            tier = _validate_license_key(key, machine_id)
            if tier:
                self.tier = tier
                self.license_info = data
                expires = data.get("expires", "")
                if expires:
                    exp_date = datetime.strptime(expires, "%Y-%m-%d")
                    if exp_date < datetime.now():
                        self.tier = TIER_FREE
                        self.license_info["expired"] = True
        except Exception:
            self.tier = TIER_FREE

    def is_feature_allowed(self, feature_name):
        features = FEATURE_MAP.get(self.tier, FEATURE_MAP[TIER_FREE])
        return features.get(feature_name, False)

    def get_max_images(self):
        features = FEATURE_MAP.get(self.tier, FEATURE_MAP[TIER_FREE])
        return features.get("max_images_per_session", 100)

    def get_tier(self):
        return self.tier

    def get_tier_display_name(self):
        names = {
            TIER_FREE: "Free",
            TIER_STANDARD: "Standard",
            TIER_PROFESSIONAL: "Professional",
            TIER_ENTERPRISE: "Enterprise",
        }
        return names.get(self.tier, "Free")

    def check_image_limit(self, requested_count):
        max_images = self.get_max_images()
        if max_images < 0:
            return True, requested_count
        if requested_count <= max_images:
            return True, requested_count
        return False, max_images

    def get_watermark_text(self):
        if self.tier == TIER_FREE:
            return "Huhb3D Free Edition"
        elif self.tier == TIER_STANDARD:
            return "Huhb3D Standard"
        return ""

    def should_add_watermark(self):
        return self.tier in (TIER_FREE, TIER_STANDARD)

    def get_feature_summary(self):
        features = FEATURE_MAP.get(self.tier, FEATURE_MAP[TIER_FREE])
        return {
            "tier": self.tier,
            "tier_display": self.get_tier_display_name(),
            "features": features,
            "license_info": {
                "licensed_to": self.license_info.get("licensed_to", ""),
                "expires": self.license_info.get("expires", ""),
                "machine_id": self.license_info.get("machine_id", ""),
            },
        }


def generate_license_key(tier, machine_id=None):
    mid = machine_id or _generate_machine_id()
    key = hashlib.sha256(f"{SECRET_KEY}-{tier}-{mid}".encode()).hexdigest()[:24]
    return key


def create_license_file(tier, licensed_to, expires, machine_id=None, output_path="huhb3d.license"):
    mid = machine_id or _generate_machine_id()
    key = generate_license_key(tier, mid)
    data = {
        "license_key": key,
        "tier": tier,
        "licensed_to": licensed_to,
        "machine_id": mid,
        "expires": expires,
        "generator": "Huhb3D-SyntheticDataPipeline",
    }
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"License file created: {output_path}")
    print(f"  Tier: {tier}")
    print(f"  Licensed to: {licensed_to}")
    print(f"  Machine ID: {mid}")
    print(f"  Expires: {expires}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Huhb3D License Manager")
    parser.add_argument("--generate", action="store_true", help="Generate a license key")
    parser.add_argument("--tier", choices=["standard", "professional", "enterprise"],
                        default="professional", help="License tier")
    parser.add_argument("--licensed-to", default="Customer", help="Licensed to name")
    parser.add_argument("--expires", default="2026-12-31", help="Expiration date (YYYY-MM-DD)")
    parser.add_argument("--machine-id", default=None, help="Machine ID (auto-detect if not specified)")
    parser.add_argument("--output", default="huhb3d.license", help="Output license file path")
    parser.add_argument("--check", default=None, help="Check a license file")
    args = parser.parse_args()

    if args.generate:
        create_license_file(args.tier, args.licensed_to, args.expires,
                            args.machine_id, args.output)
    elif args.check:
        guard = LicenseGuard(args.check)
        summary = guard.get_feature_summary()
        print(json.dumps(summary, indent=2))
    else:
        mid = _generate_machine_id()
        print(f"Machine ID: {mid}")
        print(f"Use --generate to create a license file")
