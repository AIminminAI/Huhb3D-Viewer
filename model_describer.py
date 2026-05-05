import os
import base64
import json
import requests
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

class ModelDescriber:
    def __init__(self, api_key):
        self.api_key = api_key
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = None
        self.descriptions = []
        self.filenames = []
        self.load_vector_store()
    
    def load_vector_store(self):
        """加载向量存储"""
        if os.path.exists('vector_store.index') and os.path.exists('metadata.json'):
            self.index = faiss.read_index('vector_store.index')
            with open('metadata.json', 'r') as f:
                data = json.load(f)
                self.descriptions = data['descriptions']
                self.filenames = data['filenames']
            print("Vector store loaded successfully")
        else:
            self.index = faiss.IndexFlatL2(384)  # 384是all-MiniLM-L6-v2的维度
            print("Created new vector store")
    
    def save_vector_store(self):
        """保存向量存储"""
        faiss.write_index(self.index, 'vector_store.index')
        metadata = {
            'descriptions': self.descriptions,
            'filenames': self.filenames
        }
        with open('metadata.json', 'w') as f:
            json.dump(metadata, f)
        print("Vector store saved successfully")
    
    def encode_image(self, image_path):
        """编码图像为base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def describe_model(self, image_paths):
        """使用多模态模型描述模型"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请简要描述这个3D模型的形状、结构和可能的用途。描述要简洁明了，不超过100字。"
                        }
                    ]
                }
            ],
            "max_tokens": 150
        }
        
        # 添加图像
        for image_path in image_paths:
            if os.path.exists(image_path):
                base64_image = self.encode_image(image_path)
                payload["messages"][0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/ppm;base64,{base64_image}"
                    }
                })
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"Error: {response.status_code}, {response.text}")
            return "无法描述模型"
    
    def add_to_vector_store(self, model_name, description):
        """添加描述到向量存储"""
        # 编码描述
        embedding = self.model.encode([description])[0]
        
        # 添加到向量索引
        self.index.add(np.array([embedding]))
        
        # 添加元数据
        self.descriptions.append(description)
        self.filenames.append(model_name)
        
        # 保存向量存储
        self.save_vector_store()
        
        print(f"Added model '{model_name}' to vector store")
    
    def search_similar(self, query, k=5):
        """搜索相似的模型描述"""
        # 编码查询
        query_embedding = self.model.encode([query])[0]
        
        # 搜索
        distances, indices = self.index.search(np.array([query_embedding]), k)
        
        # 返回结果
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.filenames):
                results.append({
                    'filename': self.filenames[idx],
                    'description': self.descriptions[idx],
                    'distance': distances[0][i]
                })
        
        return results

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python model_describer.py <api_key> <model_name> <view1> <view2> <view3>")
        sys.exit(1)
    
    api_key = sys.argv[1]
    model_name = sys.argv[2]
    view1 = sys.argv[3]
    view2 = sys.argv[4]
    view3 = sys.argv[5]
    
    describer = ModelDescriber(api_key)
    
    # 描述模型
    description = describer.describe_model([view1, view2, view3])
    print(f"Model description: {description}")
    
    # 添加到向量存储
    describer.add_to_vector_store(model_name, description)
    
    # 测试搜索
    print("\nTesting search...")
    results = describer.search_similar("3D model")
    for result in results:
        print(f"- {result['filename']}: {result['description']} (distance: {result['distance']:.4f})")