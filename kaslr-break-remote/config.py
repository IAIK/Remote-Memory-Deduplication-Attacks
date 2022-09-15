import yaml
from voluptuous import Schema, Optional, Required, Any, Invalid
from addict import Dict


config_schema = Schema({
    Optional('host'): Any(str),
    Optional('port'): int,
    Optional('device'): Any(str),
    Optional('monitor_traffic'): Any(bool),
    Optional('kernel_text_mapping'): Any(str),
    Optional('backend'): Any('requests', 'aiohttp', 'httpx'),
    Optional('http_version'): Any('http', 'http2'),
    Optional('pages'): Any([Schema({
        Required('file'): Any(str),
    })]),
    Optional('binary_pages'): Any([Schema({
        Required('file'): Any(str),
        Required('offsets'): Any(-1, [int])
    })]),
})


def load_config_file(path):
    try:
        config = yaml.safe_load(open(path))
    except Exception:
        raise
    pass

    try:
        config = config_schema(config)
    except Exception:
        raise

    return Dict(config)
