"""
MiniMax LLM service - loads config from config.yaml via app.config
"""
import requests
import logging
import json
from app.config import get_minimax_config

logger = logging.getLogger(__name__)


def _extract_text_from_content(content_list):
    """Extract text from MiniMax content list which may include thinking/text blocks"""
    for item in content_list:
        if isinstance(item, dict):
            if item.get('type') == 'text':
                return item.get('text', '')
    return ''


def generate_answer(context_chunks, query, model=None):
    """
    Use MiniMax to generate an answer based on retrieved knowledge base chunks.
    Returns the generated answer text.
    """
    mm_cfg = get_minimax_config()
    api_key = mm_cfg['api_key']
    base_url = mm_cfg['base_url']
    default_model = mm_cfg['model']
    model = model or default_model

    if not api_key:
        logger.error("[MiniMax] API key not configured")
        return 'MiniMax API Key 未配置，请检查 config.yaml', None

    context_text = "\n\n".join(context_chunks)
    logger.info(f"[MiniMax] generate_answer | model={model} | query='{query[:50]}' | chunks={len(context_chunks)}")

    system_prompt = f"""你是一个专业的技术助手。请根据提供的知识库内容回答用户的问题。

回答规则：
1. 如果知识库中有相关的内容，请基于内容进行回答
2. 如果知识库中没有相关信息，请明确告知用户"根据现有知识库无法回答该问题"
3. 回答要准确、简洁、有条理
4. 在回答的开头注明参考来源

知识库内容：
{context_text}"""

    try:
        resp = requests.post(
            f'{base_url}/v1/messages',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'anthropic-dangerous-direct-browser-access': 'true',
            },
            json={
                'model': model,
                'max_tokens': 2048,
                'system': system_prompt,
                'messages': [
                    {'role': 'user', 'content': f"问题：{query}\n\n请根据上面的知识库内容回答问题。"}
                ]
            },
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error(f"[MiniMax] API error {resp.status_code}: {resp.text[:300]}")
            return f'LLM 调用失败：HTTP {resp.status_code}', None

        result = resp.json()
        answer = _extract_text_from_content(result.get('content', []))
        if not answer:
            answer = 'MiniMax 返回内容为空'
        logger.info(f"[MiniMax] Answer generated, length={len(answer)}")
        return answer, result
    except Exception as e:
        logger.error(f"[MiniMax] Request failed: {e}")
        return f'LLM 调用异常：{str(e)}', None


def generate_answer_stream(context_chunks, query, model=None):
    """
    Streaming generator: yields chunks as they arrive from MiniMax SSE stream.
    Yields dicts: {'type': 'text', 'content': '...'} or {'type': 'error', 'content': '...'}
    """
    mm_cfg = get_minimax_config()
    api_key = mm_cfg['api_key']
    base_url = mm_cfg['base_url']
    default_model = mm_cfg['model']
    model = model or default_model

    if not api_key:
        logger.error("[MiniMax] API key not configured for streaming")
        yield {'type': 'error', 'content': 'MiniMax API Key 未配置，请检查 config.yaml'}
        return

    context_text = "\n\n".join(context_chunks)
    logger.info(f"[MiniMax] stream | model={model} | query='{query[:50]}' | chunks={len(context_chunks)}")

    system_prompt = f"""你是一个专业的技术助手。请根据提供的知识库内容回答用户的问题。

回答规则：
1. 如果知识库中有相关的内容，请基于内容进行回答
2. 如果知识库中没有相关信息，请明确告知用户"根据现有知识库无法回答该问题"
3. 回答要准确、简洁、有条理
4. 在回答的开头注明参考来源

知识库内容：
{context_text}"""

    try:
        resp = requests.post(
            f'{base_url}/v1/messages',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'anthropic-dangerous-direct-browser-access': 'true',
            },
            json={
                'model': model,
                'max_tokens': 2048,
                'system': system_prompt,
                'stream': True,
                'messages': [
                    {'role': 'user', 'content': f"问题：{query}\n\n请根据上面的知识库内容回答问题。"}
                ]
            },
            timeout=120,
            stream=True,
        )

        if resp.status_code != 200:
            logger.error(f"[MiniMax] Stream error {resp.status_code}: {resp.text[:300]}")
            yield {'type': 'error', 'content': f'LLM 调用失败：HTTP {resp.status_code}'}
            return

        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8', errors='replace')
                if line.startswith('data: '):
                    data_str = line[6:].strip()
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        # MiniMax SSE: content_block_delta with delta.type=text_delta
                        if data.get('type') == 'content_block_delta':
                            delta = data.get('delta', {})
                            if delta.get('type') == 'text_delta':
                                text = delta.get('text', '')
                                if text:
                                    yield {'type': 'text', 'content': text}
                        elif data.get('type') == 'error':
                            msg = data.get('error', {}).get('message', 'Unknown error')
                            logger.error(f"[MiniMax] Stream error: {msg}")
                            yield {'type': 'error', 'content': msg}
                    except json.JSONDecodeError:
                        continue

    except Exception as e:
        logger.error(f"[MiniMax] Stream failed: {e}")
        yield {'type': 'error', 'content': f'LLM 调用异常：{str(e)}'}