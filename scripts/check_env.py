import sys

sys.path.insert(0, "scripts")
from ssh_helper import run

hk = "123"
_, out, _ = run(hk, "cat /home/taplo/AIMiddlePlatform/.env 2>&1", 10)
print(out)
