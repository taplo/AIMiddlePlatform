"""List all registered routes on 123 API."""
import sys

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"
_, out, _ = run(hk, """curl -s http://localhost:8000/openapi.json | python3 -c "
import sys, json
spec = json.load(sys.stdin)
for path, methods in sorted(spec.get('paths', {}).items()):
    for method in methods:
        print(f'{method.upper():6s} {path}')
" 2>&1""", 15)
print(out)
