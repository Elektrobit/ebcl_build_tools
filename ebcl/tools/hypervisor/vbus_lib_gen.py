import pydevicetree
from pathlib import Path

class DTSLibConverter:
    def __init__(self, dts: Path):
        self.tree = pydevicetree.Devicetree.parseFile(dts)
        
    def to_yaml(self):
        print(self.tree.all_nodes())
