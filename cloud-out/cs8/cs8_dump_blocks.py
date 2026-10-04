import sys, json, subprocess
from pathlib import Path
repo=Path(sys.argv[1]); base=sys.argv[2]; module=sys.argv[3]; measure=json.load(open(sys.argv[4]))
src=subprocess.run(["git","-C",str(repo),"show",f"{base}:{module}"],capture_output=True,text=True,check=True).stdout.splitlines()
for i,b in enumerate(measure[module]["per_block"],1):
    print(f"===== #{i} L{b['start']}-{b['end']} {b['kind']} {b['qualname']} tokens={b['tokens']} markers={b['markers']} dates={b['dates']}")
    for ln in range(b['start'],b['end']+1):
        print(f"{ln:5d}| {src[ln-1]}")
