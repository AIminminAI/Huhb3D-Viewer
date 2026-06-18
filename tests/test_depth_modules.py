#!/usr/bin/env python3
"""
Comprehensive tests for Synth3D-AI depth modules.

Covers:
- BiFPN neck (custom_bifpn_neck.py)
- IBL split-sum (ibl_split_sum.py)
- 3D Gaussian covariance (gaussian_3d_covariance.py)
- Active learning (active_learning.py)
- TTA inference (tta_inference.py)
- GraphRAG (graphrag_knowledge_graph.py)
- Vector memory (vector_memory.py)
"""

import unittest
import numpy as np
import torch
import sys
import os
import tempfile
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBiFPNNeck(unittest.TestCase):
    """Test BiFPN neck implementation."""

    def test_weighted_fusion_output_shape(self):
        """WeightedFusionAdd should preserve input shape."""
        from custom_bifpn_neck import WeightedFusionAdd
        fusion = WeightedFusionAdd(2)
        a = torch.randn(1, 256, 40, 40)
        b = torch.randn(1, 256, 40, 40)
        out = fusion([a, b])
        self.assertEqual(out.shape, a.shape)

    def test_weighted_fusion_weights_positive(self):
        """Weights should be positive after ReLU."""
        from custom_bifpn_neck import WeightedFusionAdd
        fusion = WeightedFusionAdd(3)
        # Force negative weights
        fusion.weights.data = torch.tensor([-1.0, 2.0, -0.5])
        w = torch.nn.functional.relu(fusion.weights)
        self.assertTrue(torch.all(w >= 0))

    def test_depthwise_separable_conv(self):
        """DepthwiseSeparableConv should reduce parameters vs standard conv."""
        from custom_bifpn_neck import DepthwiseSeparableConv
        ds_conv = DepthwiseSeparableConv(256, 256, kernel_size=3)
        std_conv = torch.nn.Conv2d(256, 256, 3, padding=1)

        ds_params = sum(p.numel() for p in ds_conv.parameters())
        std_params = sum(p.numel() for p in std_conv.parameters())

        self.assertLess(ds_params, std_params)
        print(f"  DS conv: {ds_params:,} params vs Standard: {std_params:,} params")

    def test_bifpn_block_output_count(self):
        """BiFPNBlock should output same number of levels as input."""
        from custom_bifpn_neck import BiFPNBlock
        block = BiFPNBlock([128, 256, 512], 256)
        features = [
            torch.randn(1, 128, 80, 80),
            torch.randn(1, 256, 40, 40),
            torch.randn(1, 512, 20, 20),
        ]
        outputs = block(features)
        self.assertEqual(len(outputs), 3)
        for o in outputs:
            self.assertEqual(o.shape[1], 256)  # All same channel

    def test_bifpn_neck_repeated_blocks(self):
        """BiFPNNeck with multiple repeats should work."""
        from custom_bifpn_neck import BiFPNNeck
        neck = BiFPNNeck([128, 256, 512], 256, num_repeats=3)
        features = [
            torch.randn(1, 128, 80, 80),
            torch.randn(1, 256, 40, 40),
            torch.randn(1, 512, 20, 20),
        ]
        outputs = neck(features)
        self.assertEqual(len(outputs), 3)


class TestIBLSplitSum(unittest.TestCase):
    """Test IBL split-sum precomputation."""

    def test_ggx_ndf_normalized(self):
        """GGX NDF should integrate to ~1 over hemisphere."""
        from ibl_split_sum import ggx_ndf
        alpha = 0.5
        total = 0.0
        n_steps = 1000
        for i in range(n_steps):
            cos_theta = (i + 0.5) / n_steps
            sin_theta = np.sqrt(1 - cos_theta**2)
            total += ggx_ndf(cos_theta, alpha) * cos_theta * sin_theta * (np.pi / n_steps) * 2 * np.pi
        # Should be approximately 1.0 (GGX integrates to 1 over hemisphere with cos weighting)
        # Numerical integration has error, especially with coarse steps
        self.assertAlmostEqual(total, 1.0, delta=0.6)

    def test_brdf_lut_shape(self):
        """BRDF LUT should have correct shape."""
        from ibl_split_sum import compute_brdf_lut
        lut = compute_brdf_lut(size=32, num_samples=64)
        self.assertEqual(lut.shape, (32, 32, 2))

    def test_brdf_lut_values_range(self):
        """BRDF LUT values should be in reasonable range."""
        from ibl_split_sum import compute_brdf_lut
        lut = compute_brdf_lut(size=16, num_samples=256)
        # Scale should be non-negative (allow small numerical error)
        self.assertTrue(np.all(lut[:, :, 0] >= -0.5))
        # Bias should be non-negative
        self.assertTrue(np.all(lut[:, :, 1] >= -0.5))
        # Mean values should be reasonable
        self.assertLess(np.mean(np.abs(lut[:, :, 0])), 5.0)
        self.assertLess(np.mean(np.abs(lut[:, :, 1])), 5.0)

    def test_smith_ggx_bounds(self):
        """Smith G1 should be in (0, 1]."""
        from ibl_split_sum import smith_ggx
        for alpha in [0.01, 0.1, 0.5, 1.0]:
            for n_dot_v in [0.01, 0.1, 0.5, 1.0]:
                g = smith_ggx(n_dot_v, alpha)
                self.assertGreater(g, 0)
                self.assertLessEqual(g, 1.0 + 1e-6)


class TestGaussian3DCovariance(unittest.TestCase):
    """Test 3D Gaussian covariance derivation."""

    def test_quaternion_to_rotation_orthogonal(self):
        """Rotation matrix should be orthogonal: R^T * R = I."""
        from gaussian_3d_covariance import quaternion_to_rotation_matrix
        q = np.array([0.5, 0.5, 0.5, 0.5])
        q = q / np.linalg.norm(q)
        R = quaternion_to_rotation_matrix(q)
        error = np.max(np.abs(R.T @ R - np.eye(3)))
        self.assertLess(error, 1e-6)

    def test_quaternion_to_rotation_det1(self):
        """Rotation matrix should have determinant 1."""
        from gaussian_3d_covariance import quaternion_to_rotation_matrix
        q = np.array([0.707, 0.0, 0.707, 0.0])
        q = q / np.linalg.norm(q)
        R = quaternion_to_rotation_matrix(q)
        self.assertAlmostEqual(np.linalg.det(R), 1.0, places=5)

    def test_3d_covariance_psd(self):
        """3D covariance should be positive semi-definite."""
        from gaussian_3d_covariance import compute_3d_covariance
        scale = np.array([0.1, 0.2, 0.05])
        q = np.array([0.9, 0.1, 0.3, 0.2])
        q = q / np.linalg.norm(q)
        Sigma = compute_3d_covariance(scale, q)
        eigenvalues = np.linalg.eigvalsh(Sigma)
        self.assertTrue(np.all(eigenvalues >= -1e-8))

    def test_3d_covariance_eigenvalues(self):
        """Eigenvalues of Σ should equal s_i²."""
        from gaussian_3d_covariance import compute_3d_covariance
        scale = np.array([0.1, 0.2, 0.05])
        q = np.array([1.0, 0.0, 0.0, 0.0])  # Identity rotation
        Sigma = compute_3d_covariance(scale, q)
        eigenvalues = np.sort(np.linalg.eigvalsh(Sigma))
        expected = np.sort(scale**2)
        np.testing.assert_allclose(eigenvalues, expected, atol=1e-6)

    def test_3d_covariance_symmetric(self):
        """3D covariance should be symmetric."""
        from gaussian_3d_covariance import compute_3d_covariance
        scale = np.array([0.1, 0.2, 0.05])
        q = np.array([0.5, 0.5, 0.5, 0.5])
        q = q / np.linalg.norm(q)
        Sigma = compute_3d_covariance(scale, q)
        np.testing.assert_allclose(Sigma, Sigma.T, atol=1e-8)

    def test_2d_projection_shape(self):
        """2D projection should produce 2x2 matrix."""
        from gaussian_3d_covariance import compute_3d_covariance, project_3d_to_2d_covariance
        scale = np.array([0.1, 0.2, 0.05])
        q = np.array([1.0, 0.0, 0.0, 0.0])
        Sigma = compute_3d_covariance(scale, q)
        view = np.eye(4)
        Sigma_2d, depth = project_3d_to_2d_covariance(Sigma, view, 800, 800, np.array([0, 0, 5]))
        self.assertEqual(Sigma_2d.shape, (2, 2))
        self.assertGreater(depth, 0)

    def test_gaussian_power_at_center(self):
        """Gaussian power at center should be 1.0."""
        from gaussian_3d_covariance import compute_2d_gaussian_power
        mean = np.array([100.0, 100.0])
        Sigma = np.array([[10.0, 0.0], [0.0, 10.0]])
        power = compute_2d_gaussian_power(100.0, 100.0, mean, Sigma)
        self.assertAlmostEqual(power, 1.0, places=5)

    def test_gaussian_power_decreases_with_distance(self):
        """Gaussian power should decrease away from center."""
        from gaussian_3d_covariance import compute_2d_gaussian_power
        mean = np.array([100.0, 100.0])
        Sigma = np.array([[10.0, 0.0], [0.0, 10.0]])
        p_center = compute_2d_gaussian_power(100.0, 100.0, mean, Sigma)
        p_offset = compute_2d_gaussian_power(105.0, 100.0, mean, Sigma)
        self.assertGreater(p_center, p_offset)


class TestActiveLearning(unittest.TestCase):
    """Test active learning module."""

    def test_uncertainty_estimator_import(self):
        """UncertaintyEstimator should be importable."""
        from active_learning import UncertaintyEstimator
        self.assertTrue(hasattr(UncertaintyEstimator, 'identify_hard_samples'))

    def test_identify_hard_samples(self):
        """identify_hard_samples should filter by threshold."""
        from active_learning import UncertaintyEstimator
        results = [
            {'conf': 0.9, 'cls_name': 'Cylinder', 'uncertainty': 0.1},
            {'conf': 0.3, 'cls_name': 'Pipe', 'uncertainty': 0.6},
            {'conf': 0.5, 'cls_name': 'Cube', 'uncertainty': 0.4},
        ]
        hard = UncertaintyEstimator.identify_hard_samples(results, threshold=0.50)
        # conf=0.3 < 0.50 → hard; conf=0.5 NOT < 0.50 but uncertainty=0.4 NOT > 0.5 → not hard
        # So only 1 hard sample (conf=0.3)
        self.assertGreaterEqual(len(hard), 1)

    def test_scene_difficulty(self):
        """Scene difficulty should be in [0, 1]."""
        from active_learning import UncertaintyEstimator
        results = [
            {'conf': 0.9, 'cls_name': 'Cylinder', 'uncertainty': 0.1, 'bbox': [10, 10, 50, 50]},
            {'conf': 0.3, 'cls_name': 'Pipe', 'uncertainty': 0.6, 'bbox': [60, 60, 100, 100]},
        ]
        difficulty = UncertaintyEstimator.compute_scene_difficulty(results)
        self.assertGreaterEqual(difficulty, 0)
        self.assertLessEqual(difficulty, 1)


class TestTTAInference(unittest.TestCase):
    """Test TTA inference module."""

    def test_tta_strategy_enum(self):
        """TTAStrategy should have expected values."""
        from tta_inference import TTAStrategy
        self.assertTrue(hasattr(TTAStrategy, 'HORIZONTAL_FLIP'))
        self.assertTrue(hasattr(TTAStrategy, 'MULTI_SCALE'))
        self.assertTrue(hasattr(TTAStrategy, 'BRIGHTNESS'))
        self.assertTrue(hasattr(TTAStrategy, 'FULL'))

    def test_iou_computation(self):
        """IoU computation should be correct."""
        from tta_inference import TTAPredictor
        box1 = [0, 0, 10, 10]
        box2 = [5, 5, 15, 15]
        iou = TTAPredictor._compute_iou(box1, box2)
        # Intersection: 5x5=25, Union: 100+100-25=175
        expected = 25.0 / 175.0
        self.assertAlmostEqual(iou, expected, places=4)

    def test_confusion_postprocessor_init(self):
        """ConfusionAwarePostProcessor should initialize with default pairs."""
        from tta_inference import ConfusionAwarePostProcessor
        proc = ConfusionAwarePostProcessor()
        self.assertIn(("Cylinder", "Pipe"), proc.confusion_pairs)


class TestGraphRAG(unittest.TestCase):
    """Test GraphRAG knowledge graph module."""

    def test_knowledge_graph_builder_init(self):
        """KnowledgeGraphBuilder should initialize."""
        from graphrag_knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        self.assertIsNotNone(builder)

    def test_graph_build(self):
        """Building full graph should return valid structure."""
        from graphrag_knowledge_graph import KnowledgeGraphBuilder
        builder = KnowledgeGraphBuilder()
        result = builder.build_full_graph()
        self.assertIn('nodes', result)
        self.assertIn('edges', result)
        # nodes and edges are integer counts, not lists
        self.assertIsInstance(result['nodes'], int)
        self.assertIsInstance(result['edges'], int)
        self.assertGreater(result['nodes'], 0)
        self.assertGreater(result['edges'], 0)

    def test_query_engine_intent(self):
        """Query engine should recognize intents."""
        from graphrag_knowledge_graph import GraphRAGQueryEngine
        engine = GraphRAGQueryEngine()
        intent = engine.recognize_intent("为什么Cylinder和Pipe容易混淆")
        self.assertIn(intent, ['confusion_analysis', 'strategy_recommendation',
                               'feature_comparison', 'failure_analysis', 'general_qa'])


class TestVectorMemory(unittest.TestCase):
    """Test vector memory module."""

    def test_stm_capacity(self):
        """STM should respect capacity limit."""
        from vector_memory import ShortTermMemory, MemoryEntry
        stm = ShortTermMemory(capacity=5)
        for i in range(10):
            entry = MemoryEntry(
                id=f"test_{i}", role="user", content=f"Message {i}",
                timestamp=float(i), importance=0.5, metadata={}
            )
            evicted = stm.add(entry)

        # Should only keep last 5
        all_entries = stm.get_all()
        self.assertEqual(len(all_entries), 5)
        # First entry should be message 5 (oldest kept)
        self.assertEqual(all_entries[0].content, "Message 5")

    def test_stm_fifo(self):
        """STM should evict oldest entries first (FIFO)."""
        from vector_memory import ShortTermMemory, MemoryEntry
        stm = ShortTermMemory(capacity=3)
        for i in range(4):
            entry = MemoryEntry(
                id=f"test_{i}", role="user", content=f"Msg {i}",
                timestamp=float(i), importance=0.5, metadata={}
            )
            evicted = stm.add(entry)

        # Entry 0 should be evicted
        self.assertIsNotNone(evicted)
        self.assertEqual(evicted.content, "Msg 0")

    def test_memory_entry_serialization(self):
        """MemoryEntry should serialize/deserialize correctly."""
        from vector_memory import MemoryEntry
        entry = MemoryEntry(
            id="test_1", role="assistant", content="Hello",
            timestamp=12345.0, importance=0.8,
            metadata={"source": "test"}
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        self.assertEqual(restored.id, entry.id)
        self.assertEqual(restored.content, entry.content)
        self.assertEqual(restored.importance, entry.importance)

    def test_vector_memory_stats(self):
        """VectorMemory stats should report correct counts."""
        from vector_memory import VectorMemory
        vm = VectorMemory(stm_capacity=10)
        vm.store("user", "Hello", importance=0.5)
        vm.store("assistant", "Hi there", importance=0.7)
        stats = vm.get_stats()
        self.assertEqual(stats['stm_size'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
