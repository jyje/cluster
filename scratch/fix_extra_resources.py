import os
import re

def fix_extra_resources(root_dir):
    # Pattern to match 'extraResources: []' and any subsequent comments until the next empty line or non-comment line
    # We want to replace it with the standard pattern
    
    target_pattern = re.compile(r'(# -- Extra resources to deploy with the chart\s*\n)?extraResources: \[\](\s*\n\s*#.*)*', re.MULTILINE)
    
    standard_replacement = """# -- Extra resources to deploy with the chart
extraResources: []
# - apiVersion: v1
#   kind: ConfigMap
#   metadata:
#     name: example-configmap
#   data:
#     example-key: example-value
"""

    found_files = []
    for root, dirs, files in os.walk(root_dir):
        if '/charts/' in root:
            continue
            
        for file in files:
            if file == 'values.yaml':
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if 'extraResources:' in content:
                        # We only want to fix it if it's the 'extraResources: []' pattern
                        # and check if it already matches the standard exactly
                        new_content = target_pattern.sub(standard_replacement, content)
                        
                        if new_content != content:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                            found_files.append(file_path)
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
    
    return found_files

if __name__ == "__main__":
    helm_dir = "helm"
    if os.path.exists(helm_dir):
        fixed_files = fix_extra_resources(helm_dir)
        if fixed_files:
            print("Fixed the extraResources pattern in the following files:")
            for f in fixed_files:
                print(f"- {f}")
        else:
            print("No files needed fixing.")
    else:
        print(f"Directory '{helm_dir}' not found.")
