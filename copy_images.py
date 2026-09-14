from pathlib import Path
import shutil

src_root = Path(r'c:\Users\noras\Documents\Nora UBC APSC\2025W\CPSC538\FreeRTOS\Documentation')

pairs = [
    (src_root / 'SRP' / 'pictures', Path(r'c:\Users\noras\Documents\GitHub\Portfolio\Other Media\CPSC538G\SRP')),
    (src_root / 'CBS' / 'pictures', Path(r'c:\Users\noras\Documents\GitHub\Portfolio\Other Media\CPSC538G\CBS')),
]

for src, dst in pairs:
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob('*')):
        if path.is_file():
            shutil.copy2(path, dst / path.name)

print('finished')
