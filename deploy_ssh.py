import pexpect
import sys

def main():
    print("Connecting to VPS...")
    child = pexpect.spawn('ssh root@157.173.101.114 "cd /opt/ai-sales-saas && git pull origin main && sudo systemctl restart ai-sales-saas && journalctl -u ai-sales-saas -n 30 --no-pager"', encoding='utf-8')
    
    try:
        i = child.expect(['assword:', 'yes/no', pexpect.EOF, pexpect.TIMEOUT], timeout=10)
        if i == 0:
            child.sendline('6373IQecDW')
        elif i == 1:
            child.sendline('yes')
            child.expect('assword:', timeout=10)
            child.sendline('6373IQecDW')
        
        # Read the output sequentially
        while True:
            try:
                line = child.readline()
                if not line: break
                print(line.strip())
            except pexpect.EOF:
                break
                
        child.close()
        sys.exit(child.exitstatus if child.exitstatus is not None else 0)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
