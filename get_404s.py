def find_404s():
    output = []
    with open('/var/log/nginx/access.log', 'r') as f:
        for line in f:
            if ' 404 ' in line:
                output.append(line.strip())
    
    print("--- LAST 20 404 ERRORS ---")
    for l in output[-20:]:
        print(l)

if __name__ == '__main__':
    find_404s()
