import os
import re

def audit_values_files(root_dir):
    pattern = re.compile(r'extraResources: \[\]\s*\n\s*#\s+data:', re.MULTILINE)
    
    results = []
    for root, dirs, files in os.walk(root_dir):
        # Skip subcharts inside 'charts' directories as per workflow rules
        if '/charts/' in root:
            continue
            
        for file in files:
            if file == 'values.yaml':
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if pattern.search(content):
                            results.append(file_path)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    
    return results

if __name__ == "__main__":
    helm_dir = "helm"
    if os.path.exists(helm_dir):
        found_files = audit_values_files(helm_dir)
        if found_files:
            print("Found files with the incorrect extraResources pattern:")
            for f in found_files:
                print(f"- {f}")
        else:
            print("No files found with the incorrect pattern.")
    else:
        print(f"Directory '{helm_dir}' not found.")
