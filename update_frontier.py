#!/usr/bin/env python3
"""
Auto-update AI frontier data for the knowledge tree.
Fetches latest papers from Semantic Scholar (primary) + arXiv (fallback) and trending GitHub repos.
Runs daily via GitHub Actions.
"""
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import time

ARXIV_API = 'http://export.arxiv.org/api/query?'
SEMANTIC_SCHOLAR_API = 'https://api.semanticscholar.org/graph/v1/paper/search'
GITHUB_TRENDING = 'https://api.github.com/search/repositories'

SEARCH_QUERIES = [
    'AI agent RAG',
    '3D Gaussian Splatting',
    'YOLO object detection',
    'domain adaptation sim-to-real',
    'GraphRAG knowledge graph',
    'MCP model context protocol'
]


def fetch_with_retry(url, headers, max_retries=3, timeout=30):
    """Fetch URL with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                print(f'  Retry {attempt+1}/{max_retries} after {wait}s: {e}')
                time.sleep(wait)
            else:
                raise


def fetch_semantic_scholar(max_results=12):
    """Fetch recent papers from Semantic Scholar API (more reliable than arXiv)."""
    papers = []
    seen_titles = set()

    for query in SEARCH_QUERIES[:4]:  # Limit to 4 queries to avoid rate limiting
        try:
            params = urllib.parse.urlencode({
                'query': query,
                'limit': min(5, max_results // len(SEARCH_QUERIES[:4]) + 1),
                'fields': 'title,authors,year,externalIds,url,abstract,publicationDate',
                'year': '2025-',
                'sort': 'publicationDate:desc'
            })
            url = f'{SEMANTIC_SCHOLAR_API}?{params}'

            data = fetch_with_retry(url, {
                'User-Agent': 'Synth3D-AI-Frontier/1.0',
                'Accept': 'application/json'
            }, timeout=30)

            results = json.loads(data.decode())

            for item in results.get('data', []):
                title = item.get('title', '').strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                authors_list = item.get('authors', [])[:3]
                authors = ', '.join(a.get('name', '') for a in authors_list)
                if len(item.get('authors', [])) > 3:
                    authors += ' et al.'

                abstract = (item.get('abstract') or '')[:180]
                if abstract:
                    abstract += '...'

                pub_date = item.get('publicationDate', '')[:10]
                arxiv_id = (item.get('externalIds') or {}).get('ArXiv', '')
                link = f'https://arxiv.org/abs/{arxiv_id}' if arxiv_id else item.get('url', '')

                # Determine tag
                tag = 'new'
                tag_label = '🆕 论文'
                title_lower = title.lower()
                if any(kw in title_lower for kw in ['agent', 'react', 'multi-agent', 'mcp']):
                    tag = 'hot'
                    tag_label = '🔥 热点'
                elif any(kw in title_lower for kw in ['3d gaussian', 'splatting', 'nerf']):
                    tag = 'trending'
                    tag_label = '📈 趋势'

                papers.append({
                    'tag': tag,
                    'tagLabel': tag_label,
                    'title': f'[论文] {title}',
                    'desc': f'{authors} ({pub_date})\n{abstract}',
                    'link': link,
                    'linkText': '📄 全文 →',
                    'date': pub_date or datetime.now().strftime('%Y-%m-%d'),
                    'type': 'paper'
                })

            time.sleep(1)  # Rate limit between queries

        except Exception as e:
            print(f'Warning: Semantic Scholar query "{query}" failed: {e}')

    return papers[:max_results]


def fetch_arxiv_papers(max_results=10):
    """Fallback: Fetch recent papers from arXiv."""
    query = 'all:"AI agent" OR all:"RAG" OR all:"3D Gaussian" OR all:"YOLO" OR all:"domain adaptation"'
    cat_query = 'cat:cs.AI OR cat:cs.CV OR cat:cs.LG'

    url = f'{ARXIV_API}search_query={urllib.parse.quote(f"({query}) AND ({cat_query}")}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}'

    papers = []
    try:
        data = fetch_with_retry(url, {
            'User-Agent': 'Huhb3D-Frontier/1.0 (https://github.com/AIminminAI/Huhb3D-Viewer)'
        }, timeout=60)
        tree = ET.fromstring(data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for entry in tree.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip()[:200] + '...'
            link = entry.find('atom:id', ns).text.strip()
            published = entry.find('atom:published', ns).text.strip()[:10]
            authors = ', '.join(a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)[:3])
            if len(entry.findall('atom:author', ns)) > 3:
                authors += ' et al.'

            tag = 'new'
            tag_label = '🆕 论文'
            title_lower = title.lower()
            if any(kw in title_lower for kw in ['agent', 'react', 'multi-agent', 'mcp']):
                tag = 'hot'
                tag_label = '🔥 热点'
            elif any(kw in title_lower for kw in ['3d gaussian', 'splatting', 'nerf']):
                tag = 'trending'
                tag_label = '📈 趋势'

            papers.append({
                'tag': tag,
                'tagLabel': tag_label,
                'title': f'[论文] {title}',
                'desc': f'{authors} ({published})\n{summary}',
                'link': link,
                'linkText': '📄 arXiv全文 →',
                'date': published,
                'type': 'paper'
            })
    except Exception as e:
        print(f'Warning: arXiv fetch failed: {e}')

    return papers


def fetch_github_trending(max_results=8):
    """Fetch trending AI repos from GitHub."""
    query = 'AI agent RAG LLM computer vision'
    url = f'{GITHUB_TRENDING}?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={max_results}'

    repos = []
    try:
        data = fetch_with_retry(url, {
            'User-Agent': 'Synth3D-AI-Frontier/1.0',
            'Accept': 'application/vnd.github.v3+json'
        })
        items = json.loads(data.decode()).get('items', [])
        for item in items:
            repos.append({
                'tag': 'trending',
                'tagLabel': '📈 开源',
                'title': f'[开源] {item["name"]}',
                'desc': f'⭐ {item["stargazers_count"]:,} stars | {item.get("description", "")[:150]}',
                'link': item['html_url'],
                'linkText': '🔗 GitHub →',
                'date': item['created_at'][:10],
                'type': 'repo'
            })
    except Exception as e:
        print(f'Warning: GitHub fetch failed: {e}')

    return repos


def main():
    # Try Semantic Scholar first, fall back to arXiv
    print('Fetching papers from Semantic Scholar...')
    papers = fetch_semantic_scholar(12)
    if len(papers) < 5:
        print(f'Only got {len(papers)} papers, trying arXiv fallback...')
        arxiv_papers = fetch_arxiv_papers(10)
        existing_titles = {p['title'] for p in papers}
        for p in arxiv_papers:
            if p['title'] not in existing_titles:
                papers.append(p)
                existing_titles.add(p['title'])

    print(f'Got {len(papers)} papers total')

    print('Fetching GitHub trending repos...')
    repos = fetch_github_trending(8)
    print(f'Got {len(repos)} repos')

    # Load existing data
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'frontier-data.json')
    existing = {'items': [], 'lastUpdate': ''}
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            pass

    # Merge: new items + existing (dedup by link)
    existing_links = {item['link'] for item in existing.get('items', [])}
    new_items = [item for item in (papers + repos) if item['link'] not in existing_links]
    all_items = new_items + existing.get('items', [])

    # Remove items older than 30 days
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    all_items = [item for item in all_items if item.get('date', '9999-99-99') >= cutoff]

    # Keep max 30 items
    all_items = all_items[:30]

    # Ensure docs directory exists
    os.makedirs(os.path.dirname(data_file), exist_ok=True)

    # Save
    output = {
        'items': all_items,
        'lastUpdate': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'totalPapers': len([i for i in all_items if i['type'] == 'paper']),
        'totalRepos': len([i for i in all_items if i['type'] == 'repo'])
    }

    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'Updated frontier data: {len(new_items)} new, {len(all_items)} total')
    print(f'  Papers: {output["totalPapers"]}, Repos: {output["totalRepos"]}')
    print(f'  Last update: {output["lastUpdate"]}')


if __name__ == '__main__':
    main()
