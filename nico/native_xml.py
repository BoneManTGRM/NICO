"""Reject native XML declarations before entity expansion, regardless of encoding."""
from xml.etree import ElementTree as ET


class _DeclarationRejectedTreeBuilder(ET.TreeBuilder):
    def __init__(self, declaration_error):
        super().__init__()
        self.declaration_error = declaration_error

    def doctype(self, name, pubid, system):
        raise ValueError(self.declaration_error)


def parse_native_xml(raw, *, declaration_error):
    """Keep ordinary XML encoding support and reject DTDs before parsing entities."""
    parser = ET.XMLParser(target=_DeclarationRejectedTreeBuilder(declaration_error))
    return ET.fromstring(raw, parser=parser)
