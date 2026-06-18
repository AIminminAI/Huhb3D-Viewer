"""
Huhb3D CAD Feature Recognition API — 测试脚本
=================================================
自动测试 API 的所有端点：
  1. 健康检查
  2. 特征类型列表
  3. 抓取方式列表
  4. 上传 STEP 文件分析
  5. 批量文件分析

用法:
    python api/test_api.py
    python api/test_api.py --url http://localhost:8000
    python api/test_api.py --url https://hgodwarrior-huhb3d-cad-feature-api.hf.space
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = str(Path(__file__).parent.parent)


def test_health(base_url: str):
    """测试健康检查端点。"""
    import urllib.request
    import urllib.error

    url = f"{base_url}/health"
    print(f"\n[测试] GET /health")
    print(f"  请求: {url}")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  状态: {resp.status}")
            print(f"  响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
            assert data.get("status") == "healthy", "健康检查失败"
            print("  [通过] 健康检查正常")
            return True
    except Exception as e:
        print(f"  [失败] 健康检查异常: {e}")
        return False


def test_feature_types(base_url: str):
    """测试特征类型列表端点。"""
    import urllib.request

    url = f"{base_url}/features/types"
    print(f"\n[测试] GET /features/types")
    print(f"  请求: {url}")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  状态: {resp.status}")
            total = data.get("total", 0)
            types = data.get("feature_types", [])
            print(f"  特征类型数量: {total}")
            for t in types:
                print(f"    - {t['name']}: {t['description']}")
            assert total == 15, f"特征类型数量应为 15，实际为 {total}"
            print("  [通过] 特征类型列表正确")
            return True
    except Exception as e:
        print(f"  [失败] 特征类型列表异常: {e}")
        return False


def test_grasp_methods(base_url: str):
    """测试抓取方式列表端点。"""
    import urllib.request

    url = f"{base_url}/grasp/methods"
    print(f"\n[测试] GET /grasp/methods")
    print(f"  请求: {url}")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  状态: {resp.status}")
            total = data.get("total", 0)
            methods = data.get("grasp_methods", [])
            print(f"  抓取方式数量: {total}")
            for m in methods:
                print(f"    - {m['name']}: {m['description']}")
            assert total == 8, f"抓取方式数量应为 8，实际为 {total}"
            print("  [通过] 抓取方式列表正确")
            return True
    except Exception as e:
        print(f"  [失败] 抓取方式列表异常: {e}")
        return False


def test_pricing(base_url: str):
    """测试定价信息端点。"""
    import urllib.request

    url = f"{base_url}/pricing"
    print(f"\n[测试] GET /pricing")
    print(f"  请求: {url}")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  状态: {resp.status}")
            plans = data.get("plans", [])
            print(f"  套餐数量: {len(plans)}")
            for plan in plans:
                print(f"    - {plan['name']} ({plan['tier']}): {plan['price']}")
            assert len(plans) == 3, f"套餐数量应为 3，实际为 {len(plans)}"
            print("  [通过] 定价信息正确")
            return True
    except Exception as e:
        print(f"  [失败] 定价信息异常: {e}")
        return False


def test_analyze(base_url: str, step_file: str, api_key: str = None):
    """测试 STEP 文件分析端点。"""
    import urllib.request
    import mimetypes

    url = f"{base_url}/analyze"
    print(f"\n[测试] POST /analyze")
    print(f"  请求: {url}")
    print(f"  文件: {step_file}")

    if not os.path.exists(step_file):
        print(f"  [跳过] STEP 文件不存在: {step_file}")
        return None

    # 构建 multipart/form-data 请求
    filename = os.path.basename(step_file)
    with open(step_file, "rb") as f:
        file_content = f.read()

    # 手动构建 multipart 请求体
    boundary = "----Huhb3DTestBoundary123456"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + file_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if api_key:
        headers["X-API-Key"] = api_key
        print(f"  API Key: {api_key}")

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  状态: {resp.status}")

            # 打印分析结果摘要
            if data.get("success"):
                faces = data.get("faces", [])
                summary = data.get("summary", {})
                strategy = data.get("recommended_grasp_strategy", {})
                model_info = data.get("model_info", {})

                print(f"  === 分析结果 ===")
                print(f"  文件名: {model_info.get('filename')}")
                print(f"  文件大小: {model_info.get('file_size')} bytes")
                print(f"  解析耗时: {model_info.get('parse_time_seconds')}s")
                print(f"  总面数: {summary.get('total_faces')}")
                print(f"  总面积: {summary.get('total_area')} mm²")
                print(f"  类别统计: {json.dumps(summary.get('category_counts', {}), ensure_ascii=False)}")

                # 包围盒
                bbox = summary.get("bounding_box", {})
                dims = bbox.get("dimensions", [])
                if dims:
                    print(f"  包围盒尺寸: {dims[0]} x {dims[1]} x {dims[2]} mm")

                # 最优抓取策略
                print(f"  === 推荐抓取策略 ===")
                print(f"  方法: {strategy.get('method')}")
                print(f"  置信度: {strategy.get('confidence')}")
                print(f"  接近方向: {strategy.get('approach_direction')}")
                print(f"  目标面: {strategy.get('target_faces')}")

                # 打印前 5 个面的信息
                print(f"  === 面详情（前 5 个）===")
                for face in faces[:5]:
                    print(f"    面 {face['face_id']}: "
                          f"类型={face['geom_type']}, "
                          f"类别={face['category']}, "
                          f"面积={face['area']:.2f}mm², "
                          f"抓取={face['grasp_method']} "
                          f"(置信度={face['grasp_confidence']})")

                if len(faces) > 5:
                    print(f"    ... 还有 {len(faces) - 5} 个面")

                print("  [通过] STEP 文件分析成功")
                return True
            else:
                print(f"  [失败] 分析失败: {data.get('error')}")
                return False

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [失败] HTTP 错误 {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"  [失败] 分析异常: {e}")
        return False


def test_analyze_batch(base_url: str, step_files: list, api_key: str = None):
    """测试批量文件分析端点。"""
    import urllib.request

    url = f"{base_url}/analyze/batch"
    print(f"\n[测试] POST /analyze/batch")
    print(f"  请求: {url}")
    print(f"  文件数: {len(step_files)}")

    # 过滤存在的文件
    existing_files = [f for f in step_files if os.path.exists(f)]
    if not existing_files:
        print(f"  [跳过] 没有 STEP 文件可用于批量测试")
        return None

    # 只取前 2 个文件进行测试
    test_files = existing_files[:2]
    print(f"  实际测试文件: {[os.path.basename(f) for f in test_files]}")

    # 构建 multipart 请求体
    boundary = "----Huhb3DBatchBoundary789012"
    body_parts = []

    for step_file in test_files:
        filename = os.path.basename(step_file)
        with open(step_file, "rb") as f:
            file_content = f.read()

        part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + file_content + "\r\n".encode("utf-8")
        body_parts.append(part)

    body = b"".join(body_parts) + f"--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if api_key:
        headers["X-API-Key"] = api_key
        print(f"  API Key: {api_key}")

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  状态: {resp.status}")
            print(f"  总文件数: {data.get('total_files')}")
            results = data.get("results", [])

            for i, result in enumerate(results):
                success = result.get("success", False)
                filename = result.get("filename", f"file_{i}")
                if success:
                    faces_count = len(result.get("faces", []))
                    strategy = result.get("recommended_grasp_strategy", {})
                    print(f"  [{i+1}] {filename}: 成功, {faces_count} 个面, "
                          f"推荐策略={strategy.get('method')}")
                else:
                    print(f"  [{i+1}] {filename}: 失败, {result.get('error')}")

            print("  [通过] 批量分析完成")
            return True

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  [失败] HTTP 错误 {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"  [失败] 批量分析异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Huhb3D CAD Feature Recognition API 测试脚本"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API 基础 URL (默认: http://localhost:8000)"
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API 密钥 (可选, 开源版本无需密钥)"
    )
    parser.add_argument(
        "--step-file",
        default=None,
        help="指定 STEP 文件路径（默认自动查找 original_models/step/ 下的文件）"
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    api_key = args.api_key

    print("=" * 60)
    print("  Huhb3D CAD Feature Recognition API — 自动测试")
    print("=" * 60)
    print(f"  API 地址: {base_url}")
    print(f"  API Key:  {api_key}")
    print()

    # 查找 STEP 文件
    step_dir = os.path.join(PROJECT_ROOT, "original_models", "step")
    if args.step_file:
        step_files = [args.step_file]
    elif os.path.exists(step_dir):
        step_files = [
            os.path.join(step_dir, f)
            for f in sorted(os.listdir(step_dir))
            if f.endswith((".step", ".stp"))
        ]
    else:
        step_files = []

    if step_files:
        print(f"  可用 STEP 文件: {len(step_files)} 个")
        print(f"  第一个文件: {os.path.basename(step_files[0])}")
    else:
        print("  [警告] 未找到 STEP 文件，将跳过分析测试")

    print()

    # 执行测试
    results = {}

    # 1. 健康检查
    results["health"] = test_health(base_url)

    # 2. 特征类型列表
    results["features/types"] = test_feature_types(base_url)

    # 3. 抓取方式列表
    results["grasp/methods"] = test_grasp_methods(base_url)

    # 4. (pricing endpoint removed in open-source version)

    # 5. 单文件分析
    if step_files:
        results["analyze"] = test_analyze(base_url, step_files[0], api_key=api_key)

        # 6. 批量分析
        results["analyze/batch"] = test_analyze_batch(
            base_url, step_files, api_key=api_key
        )

    # 汇总结果
    print()
    print("=" * 60)
    print("  测试结果汇总")
    print("=" * 60)

    passed = 0
    failed = 0
    skipped = 0

    for name, result in results.items():
        if result is True:
            status = "通过"
            passed += 1
        elif result is False:
            status = "失败"
            failed += 1
        else:
            status = "跳过"
            skipped += 1
        print(f"  {name:25s}: {status}")

    print()
    print(f"  通过: {passed} | 失败: {failed} | 跳过: {skipped}")
    print()

    if failed > 0:
        print("  [!] 存在失败的测试，请检查上方输出")
        sys.exit(1)
    else:
        print("  [OK] 所有测试通过！")


if __name__ == "__main__":
    main()
