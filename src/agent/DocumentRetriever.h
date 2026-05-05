#pragma once

#include <string>
#include <vector>
#include <map>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <cctype>

namespace hhb {
namespace rag {

struct DocumentChunk {
    std::string content;
    std::string source;
    int line_number;
};

class DocumentRetriever {
public:
    DocumentRetriever();
    ~DocumentRetriever();
    
    // 初始化文档检索索引
    bool initialize();
    
    // 添加文档到索引
    bool addDocument(const std::string& filePath, const std::string& source = "unknown");
    
    // 检索相关文档片段
    std::string retrieve(const std::string& query, int maxChunks = 3) const;
    
    // 检查是否需要检索文档（基于查询关键词）
    bool needsDocumentRetrieval(const std::string& query) const;
    
private:
    // 分词处理
    std::vector<std::string> tokenize(const std::string& text) const;
    
    // 计算文本相似度（简单基于词频）
    double calculateSimilarity(const std::vector<std::string>& queryTokens, 
                               const std::vector<std::string>& chunkTokens) const;
    
    // 将长文档分割成小块
    void splitIntoChunks(const std::string& content, const std::string& source);
    
    std::vector<DocumentChunk> chunks_;
    bool initialized_;
};

} // namespace rag
} // namespace hhb