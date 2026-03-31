import os
import sys
import subprocess
import shutil
import glob

def run_cmd(cmd, ignore_error=False, shell=True):
    print(f"\n> {cmd}")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=shell)
        print(result.stdout)
        if result.returncode != 0 and not ignore_error:
            print(f"COMMAND FAILED WITH CODE {result.returncode}")
    except Exception as e:
        print(f"EXCEPTION EXECUTING COMMAND: {e}")

def print_tree(startpath, max_level=2):
    print(f"\n> tree -L {max_level}")
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        if level > max_level - 1:
            del dirs[:]
            continue
        indent = ' ' * 4 * (level)
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f"{subindent}{f}")

def main():
    root = r"C:\Users\yaman\.gemini\antigravity\playground\ai-sales-saas"
    
    if not os.path.exists(root):
        print(f"CRITICAL ERROR: Directory {root} does NOT exist.")
        return
        
    os.chdir(root)
    
    print("========================================")
    print("STEP 0 — VERIFY DIRECTORY")
    print("========================================")
    run_cmd("cmd /c cd")
    run_cmd("git remote -v")
    
    print("\n========================================")
    print("STEP 1 — CREATE .gitignore")
    print("========================================")
    gitignore_content = """__pycache__/
*.pyc
*.db
.env
*.log
trace.*
temp_*
scripts/
*.sqlite3
"""
    with open(".gitignore", "w", encoding="utf-8") as f:
        f.write(gitignore_content)
    print("Created .gitignore")
    
    print("\n========================================")
    print("STEP 2 — REMOVE SENSITIVE FILES")
    print("========================================")
    run_cmd("git rm --cached saas.db", ignore_error=True)
    run_cmd("git rm --cached .env", ignore_error=True)
    run_cmd("git rm --cached db_logs.txt", ignore_error=True)
    run_cmd("git rm --cached trace.log", ignore_error=True)
    
    files_to_delete = ["saas.db", ".env", "db_logs.txt", "trace.log", "test_login.html"]
    for filepat in ["temp_script_*.js"]:
        files_to_delete.extend(glob.glob(filepat))
    for f in files_to_delete:
        if os.path.exists(f):
            os.remove(f)
            print(f"Deleted {f}")
        else:
            print(f"Skipped {f} (not found)")
            
    print("\n========================================")
    print("STEP 3 — CLEAN ROOT SCRIPTS")
    print("========================================")
    os.makedirs("scripts", exist_ok=True)
    patterns = ["check_*.py", "deploy_*.py", "fix_*.py", "patch_*.py", "refactor_*.py", "upload_*.py", "migrate_*.py", "test_*.py", "find_*.py"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                shutil.move(f, os.path.join("scripts", os.path.basename(f)))
                print(f"Moved {f} to scripts/")
                
    print("\n========================================")
    print("STEP 4 — REMOVE __pycache__")
    print("========================================")
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d))
                print(f"Deleted {os.path.join(dirpath, d)}")
    
    run_cmd('powershell -Command "git ls-files -i -c --exclude-standard | Select-String \'__pycache__\' | ForEach-Object { git rm --cached `$_ }"', ignore_error=True)
    
    print("\n========================================")
    print("STEP 5 — CREATE PYTHON VERSION")
    print("========================================")
    with open(".python-version", "w", encoding="utf-8") as f:
        f.write("3.11\n")
    print("Created .python-version")
    
    print("\n========================================")
    print("STEP 6 — COMMIT")
    print("========================================")
    run_cmd("git add .")
    run_cmd('git commit -m "Phase 1: cleanup correct repo"')
    
    print("\n========================================")
    print("STEP 7 — PUSH")
    print("========================================")
    run_cmd("git push origin main")
    
    print("\n========================================")
    print("STEP 8 — PROOF")
    print("========================================")
    run_cmd("git status")
    run_cmd("git log -1")
    print_tree(root, 2)

if __name__ == "__main__":
    main()
