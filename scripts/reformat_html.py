import sys
from bs4 import BeautifulSoup
from pathlib import Path

def reformat(file_path):
    path = Path(file_path)
    if not path.exists():
        print(f"File {file_path} not found.")
        sys.exit(1)
    
    print(f"Reading {file_path}...")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    soup = BeautifulSoup(content, 'html.parser')
    formatted_html = soup.prettify()
    
    print(f"Writing formatted HTML to {file_path}...")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(formatted_html)
    print("Done.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = "reference/comsol.html"
    
    reformat(target)
