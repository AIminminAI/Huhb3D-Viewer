# Huhb3D CNC Quick Quote API Documentation

## Overview

Huhb3D CNC Quick Quote API provides instant CNC machining quotes from STEP files.
Upload a STEP/STP file, specify material and quantity, get a complete quote in seconds.

**Base URL**: `https://hgodwarrior-huhb3d-manufacturability-audit.hf.space`

## Quick Start

```python
from gradio_client import Client

client = Client("https://hgodwarrior-huhb3d-manufacturability-audit.hf.space/")

# Get a quote
result = client.predict(
    step_file="/path/to/your/part.stp",
    material="铝合金6061",
    quantity=10,
    api_name="/predict"
)

# result = [summary_markdown, detail_markdown, json_string]
import json
data = json.loads(result[2])
print(f"Single piece price: ¥{data['cost_breakdown']['pricing']['per_part_price_cny']}")
print(f"Total price: ¥{data['cost_breakdown']['pricing']['total_price_cny']}")
```

## API Pricing

| Plan | Price | Calls | Best For |
|------|-------|-------|----------|
| Free | $0 | 5/day | Testing |
| Pay-per-call | $0.50/call | Unlimited | Low volume |
| Starter | $19/month | 100 calls/month | Small shops |
| Professional | $49/month | 500 calls/month | Medium shops |
| Enterprise | $149/month | Unlimited | Platforms |

## Supported Materials

| Material | Price/kg (CNY) | Density (g/cm³) | Machinability |
|----------|---------------|-----------------|---------------|
| 铝合金6061 | 28 | 2.70 | Excellent |
| 铝合金7075 | 55 | 2.81 | Good |
| 不锈钢304 | 22 | 7.93 | Moderate |
| 不锈钢316 | 35 | 7.99 | Moderate |
| 碳钢45# | 8 | 7.85 | Good |
| 黄铜H62 | 45 | 8.50 | Excellent |
| 紫铜T2 | 65 | 8.96 | Good |
| PEEK | 350 | 1.32 | Good |
| 尼龙PA6 | 30 | 1.14 | Excellent |
| 亚克力PMMA | 25 | 1.18 | Excellent |

## Response Format

```json
{
  "source_file": "bracket.stp",
  "part_info": {
    "dimensions_mm": [100.5, 50.2, 25.0],
    "total_faces": 24,
    "total_entities": 156
  },
  "manufacturability": {
    "score": 85,
    "grade": "B",
    "issues": {
      "issues": [],
      "summary": {
        "total_issues": 0,
        "errors": 0,
        "warnings": 0,
        "infos": 0,
        "difficulty": "简单"
      }
    }
  },
  "process_plan": {
    "primary_process": "CNC铣削+钻削",
    "machine_type": "3轴CNC加工中心",
    "setup_count": 2,
    "operations": [...],
    "estimated_total_time_min": 15.0,
    "estimated_setup_time_min": 20
  },
  "cost_breakdown": {
    "material": {
      "name": "铝合金6061",
      "weight_kg": 0.034,
      "cost_cny": 0.95
    },
    "pricing": {
      "quantity": 10,
      "per_part_material_cny": 0.95,
      "per_part_machining_cny": 45.00,
      "per_part_setup_cny": 40.00,
      "per_part_total_cost_cny": 85.95,
      "profit_margin": "40%",
      "per_part_price_cny": 120.33,
      "total_price_cny": 1203.30
    },
    "price_range": {
      "low_cny": 96.26,
      "high_cny": 156.43
    }
  }
}
```

## Integration Examples

### Python (requests)
```python
import requests

# Upload and get quote
with open("part.stp", "rb") as f:
    files = {"file": f}
    data = {"material": "铝合金6061", "quantity": 10}
    response = requests.post(
        "https://hgodwarrior-huhb3d-manufacturability-audit.hf.space/api/predict",
        files=files, data=data
    )
```

### JavaScript (fetch)
```javascript
const formData = new FormData();
formData.append('file', stepFile);
formData.append('material', '铝合金6061');
formData.append('quantity', '10');

fetch('https://hgodwarrior-huhb3d-manufacturability-audit.hf.space/api/predict', {
  method: 'POST',
  body: formData
})
.then(res => res.json())
.then(data => console.log(data));
```

## Use Cases

1. **CNC Machine Shops**: Quick pre-screening of customer RFQs
2. **Manufacturing Platforms**: Embed in your quoting workflow (like Xometry/Protolabs)
3. **Mechanical Engineers**: Check DFM before sending to manufacturer
4. **Procurement Teams**: Validate supplier quotes against estimates

## Rate Limits

| Plan | Rate Limit |
|------|-----------|
| Free | 5 calls/day |
| Pay-per-call | 60 calls/hour |
| Starter | 120 calls/hour |
| Professional | 300 calls/hour |
| Enterprise | No limit |

## Contact

- GitHub: https://github.com/AIminminAI/Huhb3D-Viewer
- Email: See GitHub profile
