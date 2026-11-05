"""Synthetic image interoperability; no customer artifacts or external I/O."""
import io

from PIL import Image
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def test_png_and_jpeg_embed_with_original_dimensions_in_reportlab_pdf():
    pdf = io.BytesIO()
    document = canvas.Canvas(pdf, pagesize=(200, 200))
    expected = [("PNG", (7, 5), (220, 30, 50)),
                ("JPEG", (11, 9), (20, 170, 80))]
    for format_name, dimensions, color in expected:
        encoded = io.BytesIO()
        with Image.new("RGB", dimensions, color) as source:
            source.save(encoded, format=format_name)
        encoded.seek(0)
        image = ImageReader(encoded)
        assert image.getSize() == dimensions
        document.drawImage(image, 20, 20, width=dimensions[0], height=dimensions[1])
        document.showPage()
    document.save()

    reader = PdfReader(io.BytesIO(pdf.getvalue()))
    assert len(reader.pages) == len(expected)
    for page, (_, dimensions, _) in zip(reader.pages, expected):
        objects = page["/Resources"]["/XObject"].get_object()
        images = [value.get_object() for value in objects.values()
                  if value.get_object().get("/Subtype") == "/Image"]
        assert len(images) == 1
        assert (images[0]["/Width"], images[0]["/Height"]) == dimensions
        assert images[0]["/ColorSpace"] == "/DeviceRGB"
        assert images[0]["/BitsPerComponent"] == 8
        decoded = list(page.images)
        assert len(decoded) == 1
        assert decoded[0].image.size == dimensions
