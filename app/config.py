"""
Config loader for loong-kb
"""
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / 'config.yaml'

_config = None

def load_config():
    global _config
    if _config is not None:
        return _config
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            _config = yaml.safe_load(f) or {}
    except Exception:
        _config = {}
    return _config

def reload_config():
    """Force reload config from disk"""
    global _config
    _config = None
    return load_config()

def get_server_config():
    cfg = load_config()
    server = cfg.get('server', {})
    return {
        'host': server.get('host', '0.0.0.0'),
        'port': server.get('port', 5001),
    }

def get_minimax_config():
    cfg = load_config()
    mm = cfg.get('minimax', {})
    return {
        'api_key': mm.get('api_key', ''),
        'base_url': mm.get('base_url', 'https://api.minimaxi.com/anthropic'),
        'model': mm.get('model', 'MiniMax-M2.7'),
    }

def get_dify_defaults():
    cfg = load_config()
    dify = cfg.get('dify', {})
    return {
        'api_url': dify.get('api_url', ''),
        'api_key': dify.get('api_key', ''),
    }