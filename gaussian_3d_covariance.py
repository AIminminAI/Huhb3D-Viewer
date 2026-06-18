#!/usr/bin/env python3
"""
3D Gaussian Covariance Derivation for 3D Gaussian Splatting.

This module implements the complete mathematical pipeline from first principles:
    Rotation (quaternion) + Scale → 3D Covariance → 2D Projection → Rendering

This is THE core math of 3DGS that interviewers will ask about.
If you can derive this from scratch, you truly understand 3DGS.

Key question: "How does 3DGS represent each Gaussian?"
Answer: Each Gaussian is parameterized by:
    - Position μ (3D): center of the Gaussian
    - Rotation q (quaternion, 4D): orientation of the ellipsoid
    - Scale s (3D): size along each axis
    - Opacity α (scalar): transparency
    - Color SH (48D): spherical harmonics for view-dependent color

The covariance matrix Σ is DERIVED from rotation and scale:
    Σ = R * S * S^T * R^T
where R is the rotation matrix from quaternion, S is the diagonal scale matrix.

Why not parameterize Σ directly?
    - Σ must be positive semi-definite (PSD) — hard to enforce during optimization
    - R * S * S^T * R^T is ALWAYS PSD by construction
    - Fewer parameters: 4+3=7 (quaternion+scale) vs 6 (upper triangle of 3x3 symmetric)

Reference: 3D Gaussian Splatting for Real-Time Radiance Field Rendering (Kerbl et al., SIGGRAPH 2023)
"""

import numpy as np
import math
from typing import Tuple, Optional


# ========== Step 1: Quaternion → Rotation Matrix ==========

def quaternion_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """Convert unit quaternion to 3x3 rotation matrix.

    Quaternion convention: q = [w, x, y, z] where w is the scalar part.
    Must be unit quaternion: ||q|| = 1

    Derivation (Euler-Rodrigues formula):
        R = I + 2w*[v]× + 2*[v]×²
    where v = [x,y,z] is the vector part and [v]× is the skew-symmetric matrix.

    Expanded:
        R = [[1-2(y²+z²),  2(xy-wz),   2(xz+wy) ],
             [2(xy+wz),    1-2(x²+z²), 2(yz-wx)  ],
             [2(xz-wy),    2(yz+wx),   1-2(x²+y²)]]

    Args:
        q: Quaternion [w, x, y, z], shape (4,)

    Returns:
        3x3 rotation matrix
    """
    # Normalize
    q = q / (np.linalg.norm(q) + 1e-8)
    w, x, y, z = q

    R = np.array([
        [1 - 2*(y*y + z*z),  2*(x*y - w*z),      2*(x*z + w*y)],
        [2*(x*y + w*z),      1 - 2*(x*x + z*z),  2*(y*z - w*x)],
        [2*(x*z - w*y),      2*(y*z + w*x),       1 - 2*(x*x + y*y)]
    ])

    return R


# ========== Step 2: Scale + Rotation → 3D Covariance ==========

def compute_3d_covariance(scale: np.ndarray, rotation_q: np.ndarray) -> np.ndarray:
    """Compute 3D covariance matrix from scale and rotation.

    This is the CORE derivation of 3DGS:

    Σ = R * S * S^T * R^T

    where:
        S = diag(sx, sy, sz) — diagonal scale matrix
        R = rotation matrix from quaternion
        S^T = S (diagonal, so symmetric)

    Step by step:
        1. M = R * S  (rotate the scaled axes)
        2. Σ = M * M^T  (outer product gives covariance)

    Why this works:
        - S defines the ellipsoid axes (in local frame)
        - R rotates the ellipsoid to world orientation
        - Σ = M * M^T is always PSD (positive semi-definite)
        - Eigenvalues of Σ = s_i² (squared scales)
        - Eigenvectors of Σ = columns of R (rotation axes)

    Args:
        scale: [sx, sy, sz] scale factors, shape (3,)
        rotation_q: [w, x, y, z] quaternion, shape (4,)

    Returns:
        3x3 covariance matrix (symmetric, PSD)
    """
    R = quaternion_to_rotation_matrix(rotation_q)
    S = np.diag(scale)

    # M = R * S
    M = R @ S

    # Σ = M * M^T (this is ALWAYS positive semi-definite)
    Sigma = M @ M.T

    return Sigma


# ========== Step 3: 3D → 2D Projection (EWA Splatting) ==========

def project_3d_to_2d_covariance(Sigma: np.ndarray, view_matrix: np.ndarray,
                                  focal_x: float, focal_y: float,
                                  mean_3d: np.ndarray) -> Tuple[np.ndarray, float]:
    """Project 3D covariance to 2D screen-space covariance.

    This is the EWA (Elliptical Weighted Average) splatting step from
    Zwicker et al. (2001), adapted for 3DGS.

    Derivation:
        1. Transform to camera space: Σ_cam = W * Σ * W^T
           where W is the 3x3 rotation part of the view matrix
        2. Project to 2D: Σ_2d = J * Σ_cam * J^T
           where J is the Jacobian of the projective transformation
        3. Low-pass filter: Σ_2d += σ_screen² * I
           (anti-aliasing: ensure minimum Gaussian size)

    The Jacobian J accounts for perspective projection:
        For a point (tx, ty, tz) in camera space:
        J = [[fx/tz,  0,     -fx*tx/tz²],
             [0,      fy/tz, -fy*ty/tz²]]

    This is where the "splatting" happens: a 3D ellipsoid becomes a 2D ellipse.

    Args:
        Sigma: 3x3 covariance in world space
        view_matrix: 4x4 view (world-to-camera) matrix
        focal_x, focal_y: Camera focal lengths in pixels
        mean_3d: 3D position of the Gaussian center

    Returns:
        (Sigma_2d, depth) where Sigma_2d is 2x2 and depth is tz
    """
    # Extract rotation part of view matrix
    W = view_matrix[:3, :3]

    # Transform to camera space
    t = W @ mean_3d + view_matrix[:3, 3]  # Camera-space position
    tz = t[2]

    if tz < 0.1:  # Behind camera or too close
        return np.zeros((2, 2)), tz

    tx, ty = t[0], t[1]

    # Jacobian of perspective projection
    J = np.array([
        [focal_x / tz,  0.0,           -focal_x * tx / (tz * tz)],
        [0.0,           focal_y / tz,  -focal_y * ty / (tz * tz)]
    ])

    # Full transformation: Σ_cam = W * Σ * W^T, then Σ_2d = J * Σ_cam * J^T
    Sigma_cam = W @ Sigma @ W.T
    Sigma_2d = J @ Sigma_cam @ J.T

    # Low-pass filter for anti-aliasing (ensure minimum Gaussian size)
    # This prevents infinitely thin Gaussians when viewed edge-on
    sigma_screen = 0.3  # pixels
    Sigma_2d[0, 0] += sigma_screen * sigma_screen
    Sigma_2d[1, 1] += sigma_screen * sigma_screen

    return Sigma_2d, tz


# ========== Step 4: 2D Covariance → Rendering ==========

def compute_2d_gaussian_power(x: float, y: float, mean_2d: np.ndarray,
                                Sigma_2d: np.ndarray) -> float:
    """Compute the Gaussian power (un-normalized) at a 2D point.

    This is what gets rendered for each pixel:
        power = exp(-0.5 * d^T * Σ_2d^{-1} * d)
    where d = (x, y) - mean_2d

    The inverse of a 2x2 matrix:
        Σ^{-1} = 1/det(Σ) * [[Σ22, -Σ12], [-Σ12, Σ11]]

    This is computed for EVERY pixel that the Gaussian covers,
    which is why 3DGS uses tile-based rasterization for efficiency.

    Args:
        x, y: Pixel coordinates
        mean_2d: 2D mean (projected center), shape (2,)
        Sigma_2d: 2x2 covariance in screen space

    Returns:
        Gaussian power in [0, 1]
    """
    dx = x - mean_2d[0]
    dy = y - mean_2d[1]

    # Invert 2x2 covariance
    det = Sigma_2d[0, 0] * Sigma_2d[1, 1] - Sigma_2d[0, 1] * Sigma_2d[1, 0]
    if det < 1e-8:
        return 0.0

    inv_det = 1.0 / det
    inv_Sigma = np.array([
        [Sigma_2d[1, 1] * inv_det, -Sigma_2d[0, 1] * inv_det],
        [-Sigma_2d[1, 0] * inv_det, Sigma_2d[0, 0] * inv_det]
    ])

    # Mahalanobis distance squared
    d = np.array([dx, dy])
    mahal_sq = d @ inv_Sigma @ d

    return math.exp(-0.5 * mahal_sq)


# ========== Complete Pipeline Demo ==========

def demo_full_pipeline():
    """Demonstrate the complete 3DGS covariance pipeline with numerical examples."""

    print("=" * 70)
    print("  3D Gaussian Covariance Derivation — Complete Pipeline")
    print("=" * 70)

    # Define a 3D Gaussian
    position = np.array([1.0, 2.0, 5.0])  # 3D center
    scale = np.array([0.1, 0.2, 0.05])     # Scale along each axis
    rotation_q = np.array([0.9, 0.1, 0.3, 0.2])  # Quaternion
    rotation_q = rotation_q / np.linalg.norm(rotation_q)  # Normalize
    opacity = 0.8

    print(f"\n--- Input Parameters ---")
    print(f"Position μ: {position}")
    print(f"Scale s:    {scale}")
    print(f"Rotation q: {rotation_q} (normalized)")
    print(f"Opacity α:  {opacity}")

    # Step 1: Quaternion → Rotation Matrix
    print(f"\n--- Step 1: Quaternion → Rotation Matrix ---")
    R = quaternion_to_rotation_matrix(rotation_q)
    print(f"R =")
    for row in R:
        print(f"  [{row[0]:8.5f} {row[1]:8.5f} {row[2]:8.5f}]")
    print(f"det(R) = {np.linalg.det(R):.6f} (should be 1.0)")
    print(f"R^T * R = I? max error = {np.max(np.abs(R.T @ R - np.eye(3))):.2e}")

    # Step 2: Scale + Rotation → 3D Covariance
    print(f"\n--- Step 2: Scale + Rotation → 3D Covariance ---")
    Sigma = compute_3d_covariance(scale, rotation_q)
    print(f"Σ = R * S * S^T * R^T =")
    for row in Sigma:
        print(f"  [{row[0]:8.5f} {row[1]:8.5f} {row[2]:8.5f}]")

    # Verify properties
    eigenvalues = np.linalg.eigvalsh(Sigma)
    print(f"\nEigenvalues: {eigenvalues}")
    print(f"Expected (s²): {scale**2}")
    print(f"All positive (PSD)? {all(eigenvalues >= -1e-8)}")
    print(f"Symmetric? max|Σ-Σ^T| = {np.max(np.abs(Sigma - Sigma.T)):.2e}")

    # Step 3: Project to 2D
    print(f"\n--- Step 3: 3D → 2D Projection ---")
    # Simple view matrix (camera at origin, looking along +Z)
    focal_x, focal_y = 800.0, 800.0  # pixels
    view_matrix = np.eye(4)

    Sigma_2d, depth = project_3d_to_2d_covariance(
        Sigma, view_matrix, focal_x, focal_y, position
    )

    print(f"Camera-space depth tz: {depth:.3f}")
    print(f"Σ_2d =")
    print(f"  [{Sigma_2d[0,0]:8.3f} {Sigma_2d[0,1]:8.3f}]")
    print(f"  [{Sigma_2d[1,0]:8.3f} {Sigma_2d[1,1]:8.3f}]")

    # Eigenvalues of 2D covariance → ellipse axes
    eig_2d = np.linalg.eigvalsh(Sigma_2d)
    print(f"2D ellipse semi-axes: {np.sqrt(eig_2d):.2f} pixels")

    # Step 4: Render a pixel
    print(f"\n--- Step 4: Render a Pixel ---")
    mean_2d = np.array([focal_x * position[0] / depth, focal_y * position[1] / depth])
    print(f"Projected center: ({mean_2d[0]:.1f}, {mean_2d[1]:.1f}) pixels")

    # Compute power at center and nearby pixels
    power_center = compute_2d_gaussian_power(mean_2d[0], mean_2d[1], mean_2d, Sigma_2d)
    power_offset = compute_2d_gaussian_power(mean_2d[0] + 5, mean_2d[1], mean_2d, Sigma_2d)
    print(f"Power at center: {power_center:.6f}")
    print(f"Power at +5px:   {power_offset:.6f}")
    print(f"Alpha-blended:   {opacity * power_center:.6f}")

    # Summary
    print(f"\n{'='*70}")
    print(f"  Summary: 7 parameters → 3D covariance → 2D ellipse → pixel color")
    print(f"{'='*70}")
    print(f"""
Key interview answers:
Q: "How is 3DGS covariance derived?"
A: Σ = R * diag(s) * diag(s)^T * R^T, where R comes from quaternion,
   s from scale parameters. This is always PSD by construction.

Q: "Why not parameterize Σ directly?"
A: Direct Σ needs 6 parameters (upper triangle of 3x3 symmetric),
   but enforcing PSD constraint during optimization is hard.
   R+S gives 7 parameters but guarantees PSD.

Q: "How is 3D projected to 2D?"
A: EWA splatting: Σ_2d = J * W * Σ * W^T * J^T
   where W=view rotation, J=perspective Jacobian.
   A 3D ellipsoid becomes a 2D ellipse.

Q: "What's the low-pass filter for?"
A: Anti-aliasing. Adding σ_screen²*I ensures minimum Gaussian size,
   preventing infinitely thin ellipses when viewed edge-on.
""")


if __name__ == '__main__':
    demo_full_pipeline()
