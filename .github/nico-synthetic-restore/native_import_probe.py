import sys,types
from pathlib import Path
root=Path(__file__).resolve().parent/'native-source'
pkg=types.ModuleType('nico');pkg.__path__=[str(root/'nico')];sys.modules['nico']=pkg
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_run_record import create_comprehensive_run_record
print('native_modules_imported',len([x for x in sys.modules if x.startswith('nico.')]))
