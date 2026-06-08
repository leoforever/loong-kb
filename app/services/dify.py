"""
Dify API integration service
All KBs share the same Dify connection config from config.yaml
"""
import requests
import logging
from app.config import get_dify_defaults

logger = logging.getLogger(__name__)


class DifyKBService:
    """Calls external Dify knowledge base API for retrieval and Q&A"""

    def __init__(self, dataset_id):
        cfg = get_dify_defaults()
        base = cfg['api_url'].rstrip('/')
        self.api_key = cfg['api_key']
        self.dataset_id = dataset_id
        # Strip /v1 from base if present to avoid double /v1 in paths
        if base.endswith('/v1'):
            self.api_url = base[:-3]  # remove trailing /v1
        else:
            self.api_url = base
        logger.info(f"[Dify] Init | api_url={self.api_url} | dataset_id={dataset_id}")
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        })

    def _post(self, path, json=None, timeout=30):
        url = f'{self.api_url}{path}'
        logger.debug(f"[Dify] POST {url}")
        try:
            resp = self.session.post(url, json=json, timeout=timeout)
            logger.info(f"[Dify] Response {resp.status_code} for {path}")
            if resp.status_code >= 400:
                logger.error(f"[Dify] API error {resp.status_code}: {resp.text[:300]}")
            return resp
        except requests.exceptions.Timeout:
            logger.error(f"[Dify] Timeout calling {url}")
            raise
        except Exception as e:
            logger.error(f"[Dify] Request failed for {url}: {e}")
            raise

    def _get(self, path, params=None, timeout=30):
        url = f'{self.api_url}{path}'
        logger.debug(f"[Dify] GET {url}")
        try:
            resp = self.session.get(url, params=params, timeout=timeout)
            logger.info(f"[Dify] Response {resp.status_code} for GET {path}")
            if resp.status_code >= 400:
                logger.error(f"[Dify] API error {resp.status_code}: {resp.text[:300]}")
            return resp
        except requests.exceptions.Timeout:
            logger.error(f"[Dify] Timeout calling {url}")
            raise
        except Exception as e:
            logger.error(f"[Dify] Request failed for {url}: {e}")
            raise

    def list_documents(self, page=1, page_size=100):
        """
        获取知识库下的所有文档列表（自动翻页）。
        Dify API: GET /v1/datasets/{dataset_id}/documents
        返回 {'documents': [...], 'total': int}
        """
        all_docs = []
        current_page = page
        has_more = True

        while has_more:
            try:
                resp = self._get(
                    f'/v1/datasets/{self.dataset_id}/documents',
                    params={'page': current_page, 'page_size': page_size}
                )
                if resp.status_code != 200:
                    return {'error': f'HTTP {resp.status_code}: {resp.text[:200]}'}

                data = resp.json()
                docs = data.get('data', [])
                has_more = data.get('has_more', False)

                for doc in docs:
                    all_docs.append({
                        'id': doc.get('id', ''),
                        'name': doc.get('name', '未知文件'),
                        'type': doc.get('data_source_type', 'document'),
                        'indexing_status': doc.get('indexing_status', ''),
                        'display_status': doc.get('display_status', ''),
                        'word_count': doc.get('word_count', 0),
                        'char_count': doc.get('tokens', 0),
                        'created_at': doc.get('created_at', ''),
                        'error': doc.get('error'),
                    })

                logger.info(f"[Dify] list_documents | dataset={self.dataset_id} | page={current_page} | fetched={len(docs)} | has_more={has_more}")
                current_page += 1
                if current_page > 50:
                    break

            except Exception as e:
                logger.error(f"[Dify] list_documents failed: {e}")
                return {'error': str(e)}

        logger.info(f"[Dify] list_documents | dataset={self.dataset_id} | total={len(all_docs)}")
        return {'documents': all_docs, 'total': len(all_docs)}

    def retrieve(self, query, top_k=5, search_method='semantic_search', reranking_enable=False):
        """
        Retrieve relevant chunks from Dify knowledge base.
        search_method: 'semantic_search', 'keyword_search', or 'hybrid_search'
        reranking_enable: whether to enable Dify reranking (only for semantic/hybrid)
        Returns list of {'content': str, 'score': float}
        """
        payload = {
            'query': query,
            'retrieval_model': {
                'search_method': search_method,
                'top_k': top_k,
                'reranking_enable': reranking_enable,
                'score_threshold_enabled': False,
                'score_threshold': 0.0,
            }
        }
        logger.info(f"[Dify] Retrieve | dataset={self.dataset_id} | query='{query[:50]}' | top_k={top_k}")

        resp = self._post(f'/v1/datasets/{self.dataset_id}/retrieve', json=payload)
        if resp.status_code != 200:
            err = f'HTTP {resp.status_code}: {resp.text[:200]}'
            logger.error(f"[Dify] Retrieve failed: {err}")
            return {'error': err}

        data = resp.json()
        records = data.get('records', [])
        logger.info(f"[Dify] Retrieved {len(records)} chunks from dataset {self.dataset_id}")

        results = []
        for item in records:
            # Dify v1.x API: content nested in segment, score at top level
            segment = item.get('segment', {})
            content = segment.get('content', '') or item.get('content', '')
            doc_name = (item.get('document') or {}).get('name', '') if isinstance(item.get('document'), dict) else ''
            results.append({
                'content': content,
                'score': item.get('score', 0.0),
                'doc_name': doc_name,
                'segment_id': segment.get('id', '') or item.get('id', ''),
            })
        return {'results': results, 'total': len(results)}

    def chat(self, query, conversation_id=None, user='loong-kb'):
        """
        Send a chat message to Dify app (if configured as chat app).
        Falls back to retrieval + LLM answer.
        """
        logger.info(f"[Dify] Chat | dataset={self.dataset_id} | query='{query[:50]}'")
        retrieve_result = self.retrieve(query, top_k=5)
        if 'error' in retrieve_result:
            logger.error(f"[Dify] Chat retrieve error: {retrieve_result['error']}")
            return retrieve_result

        chunks = [r['content'] for r in retrieve_result['results']]
        if not chunks:
            logger.warn(f"[Dify] Chat no chunks found for query: {query[:50]}")
            return {'answer': '抱歉，未找到相关知识。', 'chunks': []}

        context = '\n\n---\n\n'.join(chunks)
        return {
            'answer': None,
            'chunks': chunks,
            'context': context,
            'retrieve_result': retrieve_result,
        }


def build_dify_service(kb_config):
    """Factory: build DifyKBService from a kb_config row (dict or sqlite3.Row)"""
    if hasattr(kb_config, 'get'):
        dataset_id = kb_config.get('dify_dataset_id', '')
    else:
        dataset_id = kb_config['dify_dataset_id']
    return DifyKBService(dataset_id=dataset_id)