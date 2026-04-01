import py_compile
import subprocess

files = subprocess.check_output(['git', 'ls-files', '*.py']).decode('utf-8').split()
errors = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except Exception as e:
        errors.append(str(e))

if errors:
    print("ERRORS FOUND:")
    for e in errors: print(e)
else:
    print("NO SYNTAX ERRORS")
