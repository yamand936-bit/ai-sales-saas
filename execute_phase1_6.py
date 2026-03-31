import os
import subprocess

def run_cmd(cmd):
    print(f"\n> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

files_to_delete = [
    "clear_token.py",
    "diag_webhook.py",
    "execute_ssh_check.py",
    "execute_test.py",
    "fetch_diagnostic.py",
    "generate_ssh.py",
    "get_logs.py",
    "get_token.py",
    "get_user_actions.py",
    "git_push.py",
    "inject_debug.py",
    "investigate_webhook.py",
    "re_register_webhooks.py",
    "remote_deploy.py",
    "restore_nginx.py",
    "restore_static.py",
    "run_py_db_update.py",
    "sync_files.py",
    "update_service.py",
    "infra_deploy.py",
    "rebuild_ai.py",
    "upgrade_providers.py"
]

print("========================================")
print("STEP 1 — DELETE INFECTED FILES")
print("========================================")

for file in files_to_delete:
    if os.path.exists(file):
        os.remove(file)
        print(f"Deleted {file} from disk")
        run_cmd(f"git rm --cached {file}")
    else:
        # Check inside scripts/ as moved during phase 1
        inner_path = os.path.join("scripts", file)
        if os.path.exists(inner_path):
            os.remove(inner_path)
            print(f"Deleted {inner_path} from disk")
            run_cmd(f"git rm --cached {inner_path}")
        else:
            print(f"{file} not found")

print("\n========================================")
print("STEP 2 — FIX ADMIN PASSWORD")
print("========================================")
print("Modified in src/main.py via replace_file_content.")

print("\n========================================")
print("STEP 3 — VERIFY NO HARDCODED PASSWORDS")
print("========================================")
run_cmd('powershell -Command "git grep -n \'password=\'"')
run_cmd('powershell -Command "git grep -n \'root\'"')
run_cmd('powershell -Command "git grep -n \'157.173\'"')

print("\n========================================")
print("STEP 4 — PURGE HISTORY")
print("========================================")

# Generate filter command dynamically
filter_cmd = "git filter-repo"
for file in files_to_delete:
    filter_cmd += f" --path {file} --path scripts/{file}"
filter_cmd += " --invert-paths --force"

run_cmd(filter_cmd)

print("\n========================================")
print("STEP 5 — COMMIT & FORCE PUSH")
print("========================================")
run_cmd('git remote add origin https://github.com/yamand936-bit/ai-sales-saas.git') # restore origin
run_cmd("git add -A")
run_cmd('git commit -m "SECURITY: purge all credentials"')
run_cmd("git push origin main --force")

print("\n========================================")
print("STEP 6 — VERIFY CLEAN")
print("========================================")
run_cmd("git log --all --full-history -- get_logs.py")
