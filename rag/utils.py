# rag/utils.py
from PyPDF2 import PdfReader
from PIL import Image
import io
import pytesseract
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))
MEDIA_DIR.mkdir(exist_ok=True)

def extract_text_from_image(image):
    try:
        return pytesseract.image_to_string(image, lang='eng+rus').strip()
    except Exception as e:
        print(f"OCR ошибка: {e}")
        return ""

def extract_images_from_pdf(pdf_path):
    images_data = []
    reader = PdfReader(pdf_path)
    pdf_name = Path(pdf_path).stem

    for page_num, page in enumerate(reader.pages):
        if "/XObject" not in page["/Resources"]:
            continue

        xobj = page["/Resources"]["/XObject"].get_object()
        image_counter = 0

        for obj_name, obj in xobj.items():
            obj = obj.get_object()
            if obj["/Subtype"] != "/Image":
                continue

            size = (obj["/Width"], obj["/Height"])
            data = obj.get_data()
            img_key = f"{pdf_name}_page{page_num}_{image_counter}"
            img_path = str(MEDIA_DIR / f"{img_key}.jpg")

            try:
                if obj.get("/Filter") == "/FlateDecode":
                    image = Image.frombytes("RGB", size, data)
                    image.save(img_path, "JPEG")
                elif obj.get("/Filter") == "/DCTDecode":
                    with open(img_path, "wb") as f:
                        f.write(data)
                else:
                    continue

                ocr_text = extract_text_from_image(Image.open(img_path))
                images_data.append({
                    "page_num": page_num,
                    "order": image_counter,
                    "img_path": img_path,
                    "caption": f"Скриншот со стр. {page_num + 1}",
                    "ocr_text": ocr_text
                })
                image_counter += 1

            except Exception as e:
                print(f"Ошибка при обработке изображения: {e}")

    return images_data