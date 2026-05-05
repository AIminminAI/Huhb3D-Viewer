#include "DocumentRetriever.h"
#include <iostream>
#include <algorithm>
#include <cctype>
#include <locale>

namespace hhb {
namespace rag {

DocumentRetriever::DocumentRetriever() : initialized_(false) {
}

DocumentRetriever::~DocumentRetriever() {
}

bool DocumentRetriever::initialize() {
    chunks_.clear();
    
    // 加载 README.md 文档
    addDocument("README.md", "README.md");
    
    // 加载其他可能的文档
    // addDocument("docs/manual.md", "Manual");
    
    initialized_ = true;
    std::cout << "DocumentRetriever initialized with " << chunks_.size() << " chunks" << std::endl;
    return true;
}

bool DocumentRetriever::addDocument(const std::string& filePath, const std::string& source) {
    std::ifstream file(filePath);
    if (!file.is_open()) {
        std::cout << "Warning: Could not open document: " << filePath << std::endl;
        return false;
    }
    
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string content = buffer.str();
    
    splitIntoChunks(content, source);
    
    file.close();
    return true;
}

void DocumentRetriever::splitIntoChunks(const std::string& content, const std::string& source) {
    std::istringstream stream(content);
    std::string line;
    std::string currentChunk;
    int lineNumber = 0;
    int chunkSize = 0;
    const int maxChunkLines = 10;
    
    while (std::getline(stream, line)) {
        lineNumber++;
        currentChunk += line + "\n";
        chunkSize++;
        
        // 当块达到一定行数或遇到空行时，保存块
        if (chunkSize >= maxChunkLines || line.empty()) {
            if (!currentChunk.empty() && chunkSize > 2) {
                DocumentChunk chunk;
                chunk.content = currentChunk;
                chunk.source = source;
                chunk.line_number = lineNumber - chunkSize;
                chunks_.push_back(chunk);
            }
            currentChunk.clear();
            chunkSize = 0;
        }
    }
    
    // 保存最后一个块
    if (!currentChunk.empty() && chunkSize > 0) {
        DocumentChunk chunk;
        chunk.content = currentChunk;
        chunk.source = source;
        chunk.line_number = lineNumber - chunkSize;
        chunks_.push_back(chunk);
    }
}

std::vector<std::string> DocumentRetriever::tokenize(const std::string& text) const {
    std::vector<std::string> tokens;
    std::string token;
    
    for (char c : text) {
        if (std::isalnum(static_cast<unsigned char>(c))) {
            token += std::tolower(static_cast<unsigned char>(c));
        } else if (!token.empty()) {
            tokens.push_back(token);
            token.clear();
        }
    }
    
    if (!token.empty()) {
        tokens.push_back(token);
    }
    
    return tokens;
}

double DocumentRetriever::calculateSimilarity(const std::vector<std::string>& queryTokens,
                                             const std::vector<std::string>& chunkTokens) const {
    if (queryTokens.empty() || chunkTokens.empty()) {
        return 0.0;
    }
    
    // 计算查询词在块中出现的次数
    int matchCount = 0;
    for (const auto& queryToken : queryTokens) {
        for (const auto& chunkToken : chunkTokens) {
            if (chunkToken.find(queryToken) != std::string::npos ||
                queryToken.find(chunkToken) != std::string::npos) {
                matchCount++;
                break;
            }
        }
    }
    
    // 返回相似度分数
    return static_cast<double>(matchCount) / static_cast<double>(queryTokens.size());
}

bool DocumentRetriever::needsDocumentRetrieval(const std::string& query) const {
    // 定义软件操作相关的关键词
    std::vector<std::string> softwareKeywords = {
        "如何", "怎么", "导出", "导入", "打开", "保存", "加载",
        "操作", "使用", "功能", "设置", "配置", "快捷键",
        "导出stl", "导出obj", "导入stl", "加载模型",
        "软件", "系统", "界面", "菜单", "按钮",
        "帮助", "教程", "文档", "说明"
    };
    
    std::string lowerQuery = query;
    std::transform(lowerQuery.begin(), lowerQuery.end(), lowerQuery.begin(),
                   [](unsigned char c){ return std::tolower(c); });
    
    for (const auto& keyword : softwareKeywords) {
        if (lowerQuery.find(keyword) != std::string::npos) {
            return true;
        }
    }
    
    return false;
}

std::string DocumentRetriever::retrieve(const std::string& query, int maxChunks) const {
    if (chunks_.empty()) {
        return "";
    }
    
    // 对查询进行分词
    std::vector<std::string> queryTokens = tokenize(query);
    if (queryTokens.empty()) {
        return "";
    }
    
    // 计算每个块与查询的相似度
    std::vector<std::pair<double, size_t>> scores;
    for (size_t i = 0; i < chunks_.size(); ++i) {
        std::vector<std::string> chunkTokens = tokenize(chunks_[i].content);
        double similarity = calculateSimilarity(queryTokens, chunkTokens);
        scores.push_back({similarity, i});
    }
    
    // 按相似度排序
    std::sort(scores.begin(), scores.end(),
              [](const auto& a, const auto& b) { return a.first > b.first; });
    
    // 构建检索结果
    std::stringstream result;
    result << "\n\n[检索到的相关文档片段]\n";
    
    int count = 0;
    for (const auto& score : scores) {
        if (count >= maxChunks || score.first <= 0.1) {
            break;
        }
        
        const auto& chunk = chunks_[score.second];
        result << "\n--- 来源: " << chunk.source << " (行 " << chunk.line_number << ") ---\n";
        result << chunk.content << "\n";
        count++;
    }
    
    return result.str();
}

} // namespace rag
} // namespace hhb