import ast
import glob
import os

for path in glob.glob('c:/PROGRAMMING/MAYA/agents/*_agent.py'):
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    print('='*40)
    print(os.path.basename(path))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name):
                if target.id == 'PLUGIN_INFO':
                    try:
                        val = ast.literal_eval(node.value)
                        print(f'Name: {val.get("agent_name")}')
                        print(f'Desc: {val.get("description")}')
                    except Exception as e:
                        print(f'Error evaluating PLUGIN_INFO: {e}')
                elif target.id == '_REQUIRED_PARAMS':
                    try:
                        val = ast.literal_eval(node.value)
                        print('Actions & Params:')
                        for k, v in val.items():
                            print(f'  - {k}: {v}')
                    except Exception as e:
                        print(f'Error evaluating _REQUIRED_PARAMS: {e}')
