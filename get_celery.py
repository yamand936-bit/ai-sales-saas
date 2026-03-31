import os
import subprocess

cmd = ['journalctl', '-u', 'ai-sales-celery', '-S', '22:20:00', '-U', '22:35:00', '--no-pager']
res = subprocess.run(cmd, capture_output=True, text=True)
print("--- CELERY LOGS ---")
print(res.stdout)
if res.stderr:
    print("--- ERRORS ---")
    print(res.stderr)
