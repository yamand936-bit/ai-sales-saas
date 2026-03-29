import paramiko
import sys
import time

def main():
    print("Connecting to 157.173.101.114 via Paramiko...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname='157.173.101.114', username='root', password='6373IQecDW', timeout=10)
        print("Authenticated successfully.")
        
        commands = [
            "cd /opt/ai-sales-saas || cd /root/ai-sales-saas",
            "git pull origin main",
            "sudo systemctl restart ai-sales-saas",
            "journalctl -u ai-sales-saas -n 30 --no-pager"
        ]
        
        full_command = " && ".join(commands)
        print(f"Executing: {full_command}")
        
        stdin, stdout, stderr = client.exec_command(full_command)
        
        out = stdout.read().decode('utf-8')
        err = stderr.read().decode('utf-8')
        
        print("\n--- STDOUT ---\n", out)
        if err:
            print("\n--- STDERR ---\n", err)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        client.close()

if __name__ == '__main__':
    main()
