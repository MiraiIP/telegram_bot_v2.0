# rag/document_loader.py
import os
import json
from PyPDF2 import PdfReader
from docx import Document
from io import BytesIO
from rag.utils import extract_images_from_pdf
from rag.rag_engine import add_document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "documents")
MEDIA_DIR = os.getenv("MEDIA_DIR", "media")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=64,
    separators=["\n\n", "\n", ". ", " ", ""]
)

def load_documents_from_folder(folder_path=DOCUMENTS_DIR):
    for filename in os.listdir(folder_path):
        filepath = os.path.join(folder_path, filename)
        if not os.path.isfile(filepath):
            continue

        full_text = ""
        images_metadata = []

        if filename.lower().endswith(".pdf"):
            reader = PdfReader(filepath)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    full_text += f"\n[Страница {page_num + 1}]\n{text}\n"

            # Извлечение изображений из PDF
            image_data, ocr_texts_combined = extract_images_from_pdf(filepath)
            if ocr_texts_combined.strip():
                full_text += f"\n[Текст со скриншотов из PDF]:\n{ocr_texts_combined}\n"
            
            images_metadata = image_data

        elif filename.lower().endswith(".docx"):
            doc = Document(filepath)
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            images_metadata = []

            for i, rel in enumerate(doc.part.rels.values()):
                if "image" in rel.target_ref:
                    try:
                        image = rel._target
                        img_data = image.blob
                        safe_filename = Path(filename).stem
                        img_path = f"{MEDIA_DIR}/{safe_filename}_img_{i}.jpg"
                        with open(img_path, "wb") as f:
                            f.write(img_data)

                        # OCR для изображений DOCX
                        from PIL import Image
                        import pytesseract
                        
                        pil_img = Image.open(BytesIO(img_data))
                        ocr_text = pytesseract.image_to_string(pil_img, lang='eng+rus').strip()
                        
                        images_metadata.append({
                            "page_num": 0,
                            "order": i,
                            "img_path": img_path,
                            "caption": f"Изображение {i + 1} из {filename}",
                            "ocr_text": ocr_text
                        })
                    except Exception as e:
                        print(f"DOCX image error for {filename} image {i}: {e}")

        # Обрабатываем документ, если есть текст
        if full_text.strip():
            chunks = text_splitter.split_text(full_text)
            for i, chunk in enumerate(chunks):
                # Преобразуем список метаданных изображений в JSON строку для хранения в Chroma
                metadata = {
                    "source": filename,
                    "source_path": filepath,
                    "images": json.dumps(images_metadata)
                }
                add_document(f"{filename}_chunk_{i}", chunk, metadata)

    print("✅ Документы загружены с сохранением изображений (пути и базовые метаданные).")