#!/usr/bin/env python3
"""
IBL Split-Sum Precomputation for PBR Rendering.

The split-sum approximation (Karis 2013, Epic Games) factorizes the PBR specular
integral into two independent parts that can be precomputed:

    ∫ L(ωi) * fr(ωi, ωo) * cos(θ) dωi  ≈  PrefilteredColor * BRDF_LUT

Part 1: Prefiltered Environment Map
    - Convolve environment map with GGX NDF at different roughness levels
    - Stored as mipmap chain (roughness 0→1 = base level→max mipmap)
    - At runtime: sample prefiltered map with reflection vector + roughness

Part 2: BRDF Integration LUT (2D texture)
    - Precompute ∫ fr * cos(θ) dωi for all (NdotV, roughness) combinations
    - Stored as 2D texture: R=scale, B=bias (for Fresnel-Schlick F0*scale+bias)
    - At runtime: sample LUT with (NdotV, roughness) and apply to F0

Why this matters:
    - Without IBL: ambient = vec3(0.2) * albedo (flat, unrealistic)
    - With IBL: ambient = proper environment reflections (metallic surfaces reflect environment)
    - This is what separates "demo PBR" from "production PBR"

Reference: Real Shading in Unreal Engine 4 (Karis, SIGGRAPH 2013)
"""

import numpy as np
from typing import Tuple, Optional
import math
import struct


# ========== GGX Distribution ==========

def ggx_ndf(n_dot_h: float, alpha: float) -> float:
    """GGX/Trowbridge-Reitz Normal Distribution Function.

    D(h) = α² / (π * ((n·h)² * (α² - 1) + 1)²)

    Args:
        n_dot_h: cos(θ) between normal and half-vector
        alpha: roughness parameter (α = roughness²)
    """
    a2 = alpha * alpha
    denom = n_dot_h * n_dot_h * (a2 - 1.0) + 1.0
    return a2 / (math.pi * denom * denom)


def ggx_importance_sample(xi: Tuple[float, float], alpha: float) -> Tuple[float, float, float]:
    """Importance sample GGX distribution for Monte Carlo integration.

    Given uniform random numbers (ξ1, ξ2), generate a microfacet half-vector
    that follows the GGX distribution. This dramatically reduces variance
    compared to uniform hemisphere sampling.

    Derivation:
        θ = arctan(α * sqrt(ξ1 / (1 - ξ1)))
        φ = 2π * ξ2

    Args:
        xi: Tuple of two uniform random numbers in [0, 1)
        alpha: Roughness parameter

    Returns:
        (x, y, z) direction on hemisphere
    """
    phi = 2.0 * math.pi * xi[1]
    cos_theta = math.sqrt((1.0 - xi[0]) / (1.0 + (alpha * alpha - 1.0) * xi[0]))
    sin_theta = math.sqrt(1.0 - cos_theta * cos_theta)

    x = sin_theta * math.cos(phi)
    y = sin_theta * math.sin(phi)
    z = cos_theta

    return (x, y, z)


# ========== Part 1: Prefiltered Environment Map ==========

def prefilter_environment_map(env_map: np.ndarray, num_mip_levels: int = 5,
                               samples_per_pixel: int = 1024) -> list:
    """Prefilter environment map for different roughness levels.

    For each mipmap level (roughness 0→1):
        Convolve environment map with GGX NDF at that roughness
        using importance sampling for efficient Monte Carlo integration.

    Args:
        env_map: HDR environment map (H, W, 3) float32
        num_mip_levels: Number of roughness levels (mipmap chain)
        samples_per_pixel: Monte Carlo samples per pixel

    Returns:
        List of prefiltered maps, one per mipmap level
    """
    h, w = env_map.shape[:2]
    mipmaps = [env_map.copy()]

    for mip in range(1, num_mip_levels):
        roughness = mip / (num_mip_levels - 1)
        alpha = roughness * roughness

        # Downsample resolution for this mip level
        mip_w = max(1, w >> mip)
        mip_h = max(1, h >> mip)
        prefiltered = np.zeros((mip_h, mip_w, 3), dtype=np.float32)

        for y in range(mip_h):
            for x in range(mip_w):
                # Map pixel to spherical coordinates
                u = (x + 0.5) / mip_w
                v = (y + 0.5) / mip_h
                theta = v * math.pi  # polar
                phi = u * 2 * math.pi  # azimuthal

                # Normal direction
                nx = math.sin(theta) * math.cos(phi)
                ny = math.sin(theta) * math.sin(phi)
                nz = math.cos(theta)

                # Monte Carlo integration with importance sampling
                color = np.zeros(3, dtype=np.float64)
                total_weight = 0.0

                for s in range(samples_per_pixel):
                    # Low-discrepancy sequence (Hammersley)
                    xi = hammersley_2d(s, samples_per_pixel)

                    # Importance sample GGX
                    hx, hy, hz = ggx_importance_sample(xi, alpha)

                    # Transform half-vector to world space (simplified: assume normal = z-up)
                    # In production, use tangent frame based on normal
                    lx = 2.0 * (nx * hx * nz + ny * hy) - nz * hx + nx * hz
                    ly = 2.0 * (ny * hx * nz + ny * hy) - nz * hy + ny * hz
                    lz = 2.0 * (nz * hx * nz + ny * hy) - nz * hz + nz * hz

                    # Simplified: just use the half-vector direction
                    l_dot_n = max(hz, 0.0)  # Approximate

                    if l_dot_n > 0.0:
                        # Sample environment map
                        sample_phi = math.atan2(hy, hx)
                        sample_theta = math.acos(np.clip(hz, -1, 1))
                        su = (sample_phi / (2 * math.pi) + 0.5) % 1.0
                        sv = sample_theta / math.pi

                        # Bilinear sample from environment map
                        env_color = bilinear_sample(env_map, su, sv)

                        # Weight by NDF * (n·l)
                        n_dot_h = max(nz, 0.0)
                        d = ggx_ndf(n_dot_h, alpha)
                        weight = d * l_dot_n

                        color += env_color * weight
                        total_weight += weight

                if total_weight > 0:
                    prefiltered[y, x] = (color / total_weight).astype(np.float32)

        mipmaps.append(prefiltered)
        print(f"  Mip level {mip}: roughness={roughness:.2f}, size={mip_w}x{mip_h}")

    return mipmaps


# ========== Part 2: BRDF Integration LUT ==========

def compute_brdf_lut(size: int = 256, num_samples: int = 1024) -> np.ndarray:
    """Compute BRDF integration LUT for split-sum approximation.

    For each (NdotV, roughness) pair, integrate:
        ∫ fr(ωi, ωo, α) * cos(θi) dωi

    Result stored as 2D texture:
        R channel: scale factor for F0
        G channel: bias factor for F0
        Final Fresnel = F0 * scale + bias

    This is the key insight from Karis 2013: the BRDF integration
    depends only on (NdotV, roughness), not on the environment,
    so it can be precomputed once and reused for any environment map.

    Args:
        size: LUT resolution (size x size)
        num_samples: Monte Carlo samples per pixel

    Returns:
        BRDF LUT (size, size, 2) float32: R=scale, G=bias
    """
    lut = np.zeros((size, size, 2), dtype=np.float32)

    for y in range(size):
        roughness = (y + 0.5) / size
        alpha = max(roughness * roughness, 1e-4)  # Avoid division by zero

        for x in range(size):
            n_dot_v = (x + 0.5) / size
            # View direction (in tangent space, normal = z-up)
            vx = math.sqrt(1.0 - n_dot_v * n_dot_v)
            vy = 0.0
            vz = n_dot_v

            scale = 0.0
            bias = 0.0

            for s in range(num_samples):
                xi = hammersley_2d(s, num_samples)
                hx, hy, hz = ggx_importance_sample(xi, alpha)

                # Light direction: L = 2*(V·H)*H - V
                v_dot_h = vx * hx + vy * hy + vz * hz
                lx = 2.0 * v_dot_h * hx - vx
                ly = 2.0 * v_dot_h * hy - vy
                lz = 2.0 * v_dot_h * hz - vz

                n_dot_l = max(lz, 0.0)
                n_dot_h = max(hz, 0.0)

                if n_dot_l > 0.0:
                    # Geometry function (Smith)
                    g1 = smith_ggx(n_dot_v, alpha)
                    g2 = smith_ggx(n_dot_l, alpha)
                    g = g1 * g2

                    # Visibility term
                    vis = g / (4.0 * n_dot_v * n_dot_l + 1e-5)

                    # Fresnel-Schlick with F0=1 (to extract scale and bias)
                    f = pow(1.0 - v_dot_h, 5.0)

                    # Accumulate
                    # F0 * scale + bias = F0 * (1-f)*vis*n_dot_l + f*vis*n_dot_l
                    scale += (1.0 - f) * vis * n_dot_l
                    bias += f * vis * n_dot_l

            scale /= num_samples
            bias /= num_samples

            lut[y, x, 0] = scale
            lut[y, x, 1] = bias

    return lut


def smith_ggx(n_dot_v: float, alpha: float) -> float:
    """Smith's geometry function (Schlick-GGX approximation).

    G₁(v) = n·v / (n·v * (1-k) + k)
    where k = α/2 for IBL (different from direct lighting where k = (α+1)²/8)
    """
    k = alpha / 2.0
    return n_dot_v / (n_dot_v * (1.0 - k) + k)


# ========== Utility Functions ==========

def hammersley_2d(index: int, num_samples: int) -> Tuple[float, float]:
    """Generate 2D Hammersley point for low-discrepancy sampling.

    Uses radical inverse (Van der Corput sequence) for the first dimension.
    Second dimension is simply index/N.
    """
    return (index / num_samples, radical_inverse_vdc(index))


def radical_inverse_vdc(n: int) -> float:
    """Van der Corput sequence (base 2 radical inverse).

    Reverses the bits of n and interprets as a fraction.
    This produces a low-discrepancy sequence that covers [0,1) uniformly.
    """
    result = 0.0
    bit = 0.5
    while n > 0:
        if n & 1:
            result += bit
        n >>= 1
        bit *= 0.5
    return result


def bilinear_sample(image: np.ndarray, u: float, v: float) -> np.ndarray:
    """Bilinear sampling from image at normalized coordinates (u, v)."""
    h, w = image.shape[:2]
    x = u * w - 0.5
    y = v * h - 0.5

    x0 = int(math.floor(x)) % w
    x1 = (x0 + 1) % w
    y0 = int(math.floor(y)) % h
    y1 = (y0 + 1) % h

    fx = x - math.floor(x)
    fy = y - math.floor(y)

    c00 = image[y0, x0]
    c10 = image[y0, x1]
    c01 = image[y1, x0]
    c11 = image[y1, x1]

    return (c00 * (1-fx) * (1-fy) + c10 * fx * (1-fy) +
            c01 * (1-fx) * fy + c11 * fx * fy)


def save_lut_as_raw(lut: np.ndarray, output_path: str):
    """Save BRDF LUT as raw float32 binary for OpenGL texture upload."""
    import os
    lut.tofile(output_path)
    print(f"BRDF LUT saved: {output_path} ({lut.shape}, {os.path.getsize(output_path)} bytes)")


def save_lut_as_header(lut: np.ndarray, output_path: str, var_name: str = "brdf_lut"):
    """Save BRDF LUT as C header for embedding in render_manager.cpp."""
    import os
    h, w, c = lut.shape
    with open(output_path, 'w') as f:
        f.write(f"// Auto-generated BRDF LUT ({w}x{h}, {c} channels)\n")
        f.write(f"// Usage: Upload as GL_RG32F texture, sample with (NdotV, roughness)\n")
        f.write(f"static const float {var_name}[{h}][{w}][{c}] = {{\n")
        for y in range(h):
            f.write("  {\n")
            for x in range(w):
                f.write(f"    {{{lut[y,x,0]:.6f}f, {lut[y,x,1]:.6f}f}}")
                if x < w - 1:
                    f.write(",")
                f.write("\n")
            f.write("  }")
            if y < h - 1:
                f.write(",")
            f.write("\n")
        f.write("};\n")
    print(f"BRDF LUT header saved: {output_path}")


# ========== Main ==========

def main():
    import os

    print("=" * 60)
    print("IBL Split-Sum Precomputation")
    print("=" * 60)

    # Part 1: BRDF LUT
    print("\n[1/2] Computing BRDF Integration LUT...")
    lut_size = 256
    lut = compute_brdf_lut(size=lut_size, num_samples=1024)

    output_dir = "ibl_output"
    os.makedirs(output_dir, exist_ok=True)

    # Save as raw binary
    save_lut_as_raw(lut, f"{output_dir}/brdf_lut_{lut_size}.raw")

    # Save as C header
    save_lut_as_header(lut, f"{output_dir}/brdf_lut.h")

    # Print statistics
    print(f"\n  LUT statistics:")
    print(f"    Scale (R): min={lut[:,:,0].min():.4f}, max={lut[:,:,0].max():.4f}, mean={lut[:,:,0].mean():.4f}")
    print(f"    Bias  (G): min={lut[:,:,1].min():.4f}, max={lut[:,:,1].max():.4f}, mean={lut[:,:,1].mean():.4f}")

    # Part 2: Prefiltered Environment Map (demo with gradient)
    print("\n[2/2] Generating demo prefiltered environment map...")
    # Create a simple gradient environment map for demonstration
    env_map = np.zeros((128, 256, 3), dtype=np.float32)
    for y in range(128):
        for x in range(256):
            env_map[y, x] = [
                (x / 256) * 2.0,  # R: horizontal gradient
                (1 - y / 128) * 3.0,  # G: vertical gradient (sky)
                0.5  # B: constant
            ]

    mipmaps = prefilter_environment_map(env_map, num_mip_levels=5, samples_per_pixel=256)
    print(f"  Generated {len(mipmaps)} mipmap levels")

    # Save prefiltered maps
    for i, mipmap in enumerate(mipmaps):
        path = f"{output_dir}/prefiltered_mip{i}.raw"
        mipmap.tofile(path)

    print(f"\n{'='*60}")
    print("IBL Precomputation Complete!")
    print("=" * 60)
    print("""
To integrate with render_manager.cpp:
1. Upload brdf_lut.raw as GL_RG32F texture (256x256)
2. Upload prefiltered mipmaps as cubemap mipmap chain
3. In fragment shader:
   // Replace ambient term with IBL
   vec3 F = FresnelSchlick(max(dot(N, V), 0.0), F0);
   vec2 brdf = texture(brdfLUT, vec2(max(dot(N, V), 0.0), roughness)).rg;
   vec3 specularIBL = textureLod(prefilteredMap, R, roughness * MAX_MIP).rgb;
   vec3 specular = specularIBL * (F * brdf.x + brdf.y);
   vec3 ambient = specular * ao;  // Replace vec3(0.2) * albedo
""")


if __name__ == '__main__':
    import os
    main()
