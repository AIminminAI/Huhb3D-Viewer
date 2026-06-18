# STEP-AI-Analyzer

**The first open-source STEP file + AI intelligent analysis toolkit.**

Upload a STEP file -> Pure Python parsing -> Feed to LLM -> Intelligent analysis report

[English](#features) | [中文](#功能介绍)

## Features

- **STEP File Parsing**: Pure Python regex parsing, no OpenCASCADE/cadquery dependency
- **AI Feature Recognition**: LLM-powered manufacturing feature identification
- **AI DFM Audit**: AI-driven Design for Manufacturing review
- **AI Process Recommendation**: AI-suggested machining processes and tooling
- **AI Cost Estimation**: AI-powered CNC machining cost estimation
- **AI Q&A**: Natural language questions about your STEP file
- **Offline Mode**: Basic analysis without LLM (degraded accuracy)
- **Any LLM**: Works with DeepSeek, OpenAI, or any OpenAI-compatible API

## Why This Project?

| Existing Tools | What They Do | What's Missing |
|---------------|-------------|----------------|
| STEP-LLM (2026) | Text -> STEP generation | STEP -> Text understanding |
| text-to-cad (2026) | Agent skills for CAD | Not a standalone tool |
| STEP3-VL-10B (2026) | 2D drawing recognition | No 3D STEP analysis |
| Drawlink (Germany) | STEP Reader API | No AI, enterprise pricing |
| Dashnode | CNC quoting | Commercial, closed-source |

**STEP-AI-Analyzer fills the gap**: The first open-source tool that combines lightweight STEP parsing with AI-powered intelligent analysis.

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Set environment variables for LLM access:

```bash
# DeepSeek (recommended, cheap: 1 CNY = 1M tokens)
export LLM_API_KEY="your-deepseek-api-key"
export LLM_BASE_URL="https://api.deepseek.com"
export LLM_MODEL="deepseek-chat"

# Or OpenAI
export LLM_API_KEY="your-openai-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o"

# Or any OpenAI-compatible API (e.g., local Ollama)
export LLM_API_KEY="ollama"
export LLM_BASE_URL="http://localhost:11434/v1"
export LLM_MODEL="qwen2.5"
```

### Run

```bash
python app.py
```

Open http://localhost:7860 in your browser.

### Deploy to HuggingFace Spaces

1. Create a new Gradio Space on HuggingFace
2. Upload `app.py` and `requirements.txt`
3. Set `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` as Space secrets
4. Your Space is live!

## API Usage

```python
from app import _parse_step_text, _build_step_summary, ai_feature_recognition

# Parse STEP file
topology = _parse_step_text("model.stp")

# Get summary for LLM
summary = _build_step_summary(topology)

# AI analysis
features = ai_feature_recognition(topology)
```

## Architecture

```
STEP File
    |
    v
Pure Python Parser (regex-based, no OpenCASCADE)
    |
    v
Structured Data (faces, dimensions, topology)
    |
    v
LLM API (DeepSeek/OpenAI/any compatible)
    |
    v
Intelligent Analysis Report
```

## Comparison with Competitors

| Feature | STEP-AI-Analyzer | Drawlink | Dashnode | Kubotek Revision |
|---------|-----------------|----------|----------|------------------|
| Open Source | Yes | No | No | No |
| AI-Powered | Yes | No | Partial | No |
| No OpenCASCADE | Yes | No | No | No |
| Free Deployment | Yes (HF Space) | No | No | No |
| Natural Language Q&A | Yes | No | No | No |
| Price | Free | Enterprise | Enterprise | Enterprise |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- GitHub: [AIminminAI/Huhb3D-Viewer](https://github.com/AIminminAI/Huhb3D-Viewer)

## Citation

If you use this tool in your research, please cite:

```bibtex
@software{step-ai-analyzer,
  title = {STEP-AI-Analyzer: Open-Source STEP File AI Analysis Toolkit},
  author = {Huhb3D},
  year = {2026},
  url = {https://github.com/AIminminAI/Huhb3D-Viewer}
}
```

---

## 功能介绍

**第一个开源的 STEP文件 + AI智能分析 工具包。**

上传 STEP 文件 -> 纯Python解析 -> 喂给LLM -> 智能分析报告

### 功能

- **STEP文件解析**：纯Python正则解析，无需OpenCASCADE/cadquery
- **AI特征识别**：LLM驱动的制造特征识别
- **AI可制造性审核**：AI驱动的DFM审核
- **AI工艺推荐**：AI推荐的加工工艺和刀具
- **AI成本估算**：AI驱动的CNC加工成本估算
- **AI问答**：关于STEP文件的自然语言问答
- **离线模式**：无LLM时提供基础分析（精度降低）
- **任意LLM**：支持DeepSeek、OpenAI或任何OpenAI兼容API

### 快速开始

```bash
pip install -r requirements.txt

# 配置DeepSeek API（推荐，1元=100万tokens）
set LLM_API_KEY=your-api-key
set LLM_BASE_URL=https://api.deepseek.com
set LLM_MODEL=deepseek-chat

python app.py
```

浏览器打开 http://localhost:7860
