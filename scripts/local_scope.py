"""Trusted local controller CLI. No network and no model service.

Do not expose the CLI, its arguments, shell or host filesystem to a model.
Only dispatch JSON from a trusted adapter; this is not OS process isolation.
"""
import argparse
import json
from pathlib import Path
import sys

from scoped_tools import Scope, _parse


def main(argv=None):
    parser = argparse.ArgumentParser(description='本机受限工具：不联网，不调用模型。')
    parser.add_argument('action', choices=['init', 'call', 'verify'])
    parser.add_argument('--directory', required=True, help='可信控制程序指定的本轮目录')
    parser.add_argument('--assets', help='仅初始化时由可信控制程序提供的输入 JSON')
    args = parser.parse_args(argv)
    try:
        if args.action == 'init':
            if not args.assets:
                raise ValueError('--assets is required for init')
            scope = Scope.create(args.directory, _parse(Path(args.assets).read_bytes()))
            result = {'session_id':scope.session_id, 'status':'initialized', 'model_called':False}
        else:
            if args.assets:
                raise ValueError('resume cannot replace assets')
            scope = Scope.resume(args.directory)
            if args.action == 'call':
                result = scope.dispatch(sys.stdin.buffer.read(1_000_001))
            else:
                result = {'session_id':scope.session_id, 'status':'records_consistent',
                          'events':scope.sequence, 'closed':scope.closed, 'model_called':False}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status':'blocked', 'error':str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
