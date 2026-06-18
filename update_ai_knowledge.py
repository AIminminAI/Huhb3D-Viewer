#!/usr/bin/env python3
"""
Auto-update AI knowledge points for the knowledge tree.
Fetches latest AI concepts from multiple sources and maps them to project modules.
Runs weekly via GitHub Actions.

Sources:
- Hugging Face Blog (https://huggingface.co/blog)
- Anthropic Research (https://www.anthropic.com/research)
- OpenAI Cookbook (https://cookbook.openai.com/)
- LangChain Blog (https://blog.langchain.dev/)
- Semantic Scholar API (latest papers)

WeChat public account articles cannot be directly fetched via API.
Use RSS feeds and blog APIs as alternatives.
"""
import json
import urllib.request
import urllib.parse
import time
import os
import re
from datetime import datetime, timedelta

SOURCES = [
    {
        'name': 'Hugging Face Blog',
        'url': 'https://huggingface.co/api/blog',
        'type': 'json',
        'keywords': ['agent', 'RAG', 'GraphRAG', 'MCP', 'embedding', 'rerank', 'LLM', 'vision']
    },
    {
        'name': 'LangChain Blog',
        'url': 'https://blog.langchain.dev/rss/',
        'type': 'rss',
        'keywords': ['agent', 'RAG', 'GraphRAG', 'MCP', 'tool', 'memory', 'context']
    }
]

# Map keywords to project knowledge tree modules
KEYWORD_MODULE_MAP = {
    'agent': 'ai', 'react': 'ai', 'multi-agent': 'ai', 'orchestrat': 'ai',
    'rag': 'ai', 'graphrag': 'ai', 'retrieval': 'ai', 'rerank': 'ai',
    'mcp': 'ai', 'function calling': 'ai', 'tool': 'ai',
    'memory': 'ai', 'vector': 'ai', 'embedding': 'ai', 'faiss': 'ai',
    'context': 'ai', 'prompt': 'ai', 'cot': 'ai', 'chain-of-thought': 'ai',
    'yolo': 'cv', 'detection': 'cv', 'segmentation': 'cv', 'instance': 'cv',
    '3d gaussian': 'render', 'splatting': 'render', 'pbr': 'render', 'rendering': 'render',
    'domain adaptation': 'cv', 'sim-to-real': 'cv', 'active learning': 'cv',
    'dann': 'cv', 'tta': 'cv'
}

def fetch_with_retry(url, headers=None, max_retries=2, timeout=20):
    """Fetch URL with retry."""
    if headers is None:
        headers = {'User-Agent': 'Synth3D-AI-Knowledge/1.0'}
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                raise

def fetch_hf_blog(max_items=5):
    """Fetch latest Hugging Face blog posts."""
    items = []
    try:
        data = fetch_with_retry('https://huggingface.co/api/blog')
        posts = json.loads(data.decode())
        for post in posts[:max_items]:
            title = post.get('title', '')
            url = 'https://huggingface.co/blog/' + post.get('slug', '')
            date = post.get('publishedAt', '')[:10]

            # Determine module
            title_lower = title.lower()
            modules = set()
            for kw, mod in KEYWORD_MODULE_MAP.items():
                if kw in title_lower:
                    modules.add(mod)

            if not modules:
                modules = {'ai'}  # Default to AI

            items.append({
                'title': title,
                'url': url,
                'date': date,
                'source': 'Hugging Face Blog',
                'modules': list(modules),
                'type': 'blog'
            })
    except Exception as e:
        print(f'Warning: HF Blog fetch failed: {e}')
    return items

def fetch_langchain_blog(max_items=5):
    """Fetch latest LangChain blog posts via RSS."""
    items = []
    try:
        data = fetch_with_retry('https://blog.langchain.dev/rss/')
        # Simple RSS parsing
        text = data.decode('utf-8', errors='ignore')
        # Extract items using regex (simple approach)
        item_pattern = re.compile(r'<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<pubDate>(.*?)</pubDate>.*?</item>', re.DOTALL)
        matches = item_pattern.findall(text)
        for title, url, pub_date in matches[:max_items]:
            title = title.strip()
            # Clean HTML entities
            title = re.sub(r'&[a-zA-Z]+;', ' ', title)

            title_lower = title.lower()
            modules = set()
            for kw, mod in KEYWORD_MODULE_MAP.items():
                if kw in title_lower:
                    modules.add(mod)
            if not modules:
                modules = {'ai'}

            items.append({
                'title': title,
                'url': url.strip(),
                'date': pub_date.strip()[:16],
                'source': 'LangChain Blog',
                'modules': list(modules),
                'type': 'blog'
            })
    except Exception as e:
        print(f'Warning: LangChain Blog fetch failed: {e}')
    return items

def fetch_semantic_scholar_trending(max_items=5):
    """Fetch trending AI papers from Semantic Scholar."""
    items = []
    queries = ['AI agent RAG', 'GraphRAG knowledge graph', 'MCP model context protocol']
    for query in queries[:2]:
        try:
            params = urllib.parse.urlencode({
                'query': query,
                'limit': 3,
                'fields': 'title,year,url,publicationDate,citationCount',
                'year': '2025-',
                'sort': 'citationCount:desc'
            })
            url = f'https://api.semanticscholar.org/graph/v1/paper/search?{params}'
            data = fetch_with_retry(url, timeout=15)
            results = json.loads(data.decode())
            for item in results.get('data', []):
                title = item.get('title', '').strip()
                if not title:
                    continue
                title_lower = title.lower()
                modules = set()
                for kw, mod in KEYWORD_MODULE_MAP.items():
                    if kw in title_lower:
                        modules.add(mod)
                if not modules:
                    modules = {'ai'}

                items.append({
                    'title': title,
                    'url': item.get('url', ''),
                    'date': item.get('publicationDate', '')[:10],
                    'source': 'Semantic Scholar',
                    'modules': list(modules),
                    'type': 'paper',
                    'citations': item.get('citationCount', 0)
                })
            time.sleep(1)
        except Exception as e:
            print(f'Warning: Semantic Scholar query "{query}" failed: {e}')
    return items[:max_items]

def main():
    print('Fetching AI knowledge updates...')

    all_items = []
    all_items.extend(fetch_hf_blog(5))
    all_items.extend(fetch_langchain_blog(5))
    all_items.extend(fetch_semantic_scholar_trending(5))

    print(f'Fetched {len(all_items)} items total')

    # Load existing data
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'ai-knowledge-updates.json')
    existing = {'items': [], 'lastUpdate': ''}
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            pass

    # Merge (dedup by url)
    existing_urls = {item['url'] for item in existing.get('items', [])}
    new_items = [item for item in all_items if item['url'] not in existing_urls]
    all_items_merged = new_items + existing.get('items', [])

    # Remove items older than 60 days
    cutoff = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    all_items_merged = [item for item in all_items_merged if item.get('date', '9999') >= cutoff]

    # Keep max 50 items
    all_items_merged = all_items_merged[:50]

    # Ensure docs directory exists
    os.makedirs(os.path.dirname(data_file), exist_ok=True)

    # Save
    output = {
        'items': all_items_merged,
        'lastUpdate': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'totalNew': len(new_items),
        'totalItems': len(all_items_merged)
    }

    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'Updated AI knowledge: {len(new_items)} new, {len(all_items_merged)} total')
    print(f'  Last update: {output["lastUpdate"]}')

    # Also generate a summary of modules affected
    module_counts = {}
    for item in all_items_merged:
        for mod in item.get('modules', []):
            module_counts[mod] = module_counts.get(mod, 0) + 1
    print(f'  Module coverage: {module_counts}')

if __name__ == '__main__':
    main()
