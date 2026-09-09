import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from nico.comprehensive_manifest_navigation_v1 import _rewrite_local_page_labels


def test_subset_encoded_spanish_page_labels_are_removed_without_changing_evidence():
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    cmap = DecodedStreamObject()
    cmap.set_data(b"1 beginbfchar\n<03> <00e1>\nendbfchar")
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        NameObject("/ToUnicode"): cmap,
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    content = DecodedStreamObject()
    content.set_data(
        b"BT /F1 10 Tf 1 0 0 1 48 700 Tm (Evidence refers to P\\003gina 20) Tj ET\n"
        b"BT /F1 7 Tf 1 0 0 1 500 27 Tm (P\\003gina 20) Tj ET\n"
        b"BT /F1 7 Tf 1 0 0 1 230 16 Tm (P\\003gina del documento 12 de 30) Tj ET\n"
    )
    page[NameObject("/Contents")] = content
    original = io.BytesIO()
    writer.write(original)
    original_bytes = original.getvalue()
    reader = PdfReader(io.BytesIO(original_bytes))
    assert reader.pages[0].extract_text().splitlines()[-2:] == ["Página 20", "Página del documento 12 de 30"]
    updated = PdfWriter(clone_from=reader)
    _rewrite_local_page_labels(updated.pages[0], updated)
    result = io.BytesIO()
    updated.write(result)
    assert PdfReader(io.BytesIO(result.getvalue())).pages[0].extract_text().strip() == "Evidence refers to Página 20"
    assert original.getvalue() == original_bytes


def test_source_architecture_limit_is_localized_without_losing_its_boundary():
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    source = "JavaScript/TypeScript observations use bounded lexical matching; dynamic imports, aliases, and computed calls can be absent."
    result = _translate_presentation(source)
    assert result == "Las observaciones de JavaScript/TypeScript usan coincidencias léxicas acotadas; pueden omitir importaciones dinámicas, alias y llamadas calculadas."
