"""Portable task instructions; no credentials or agent-specific installation."""
from pathlib import Path
import json
import os
import shlex
import sys
from .errors import AppError
from .security import AUTH_PATTERN
from .utils import normalize_api_base_url

KIT = Path(__file__).with_name('agent_kit')


def task_prompt(value, *, data_root=None, locale='zh-CN'):
    base = normalize_api_base_url(value.get('base_url', ''), allow_insecure=True)
    models = value.get('models')
    if not isinstance(models, list) or not 2 <= len(models) <= 32 or any(
            not isinstance(m, str) or not m.strip() or len(m) > 256 or '\n' in m for m in models):
        raise AppError('invalid_models')
    if AUTH_PATTERN.search(base + ' '.join(models)):
        raise AppError('credential_in_configuration')
    mode = value.get('mode')
    if mode not in ('gpt', 'claude', 'chat'):
        raise AppError('invalid_mode')
    application = KIT.parent.parent.resolve()
    output = Path(data_root or application/'meow_runs').resolve()/'baseline-work'
    quote = lambda text: "'"+str(text).replace("'", "''")+"'" if os.name=='nt' else shlex.quote(str(text))
    commands = (("Set-Location -LiteralPath "+quote(application)+"\n& ") if os.name=='nt' else ("cd "+quote(application)+"\n")) + quote(sys.executable)+' -X utf8 -B -m gpt56_vnext.baseline_cli --help'
    inputs = json.dumps({'api_url':base,'protocol':mode,'model_aliases':models},ensure_ascii=False,indent=2)
    replacements={'{{APP_ROOT}}':str(application),'{{PYTHON}}':sys.executable,'{{KIT_PATH}}':str(KIT.resolve()),
                  '{{OUTPUT_ROOT}}':str(output),'{{COMMANDS}}':commands,'{{INPUTS}}':inputs}
    prompt=(KIT/('TASK_EN.md' if locale=='en' else 'TASK.md')).read_text(encoding='utf-8')
    for token,text in replacements.items():prompt=prompt.replace(token,text)
    return {'prompt':prompt}
