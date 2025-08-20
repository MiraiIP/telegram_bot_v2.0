# rag/document_loader.py
import os
import json # Убедитесь, что json импортирован
from PyPDF2 import PdfReader
from docx import Document
from io import BytesIO
# Предполагается, что extract_images_from_pdf возвращает (image_paths, ocr_text_combined)
# Если она возвращает список словарей, нужно адаптировать
from rag.utils import extract_images_from_pdf
from rag.rag_engine import add_document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from pathlib import Path
# Убедитесь, что PIL.Image и pytesseract импортированы, если используете их напрямую
# from PIL import Image
# import pytesseract

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
        # Для текущего utils.py image_paths будет списком путей
        image_paths = []
        # Для текущего utils.py ocr_texts_combined будет одной строкой
        ocr_texts_combined = ""

        if filename.lower().endswith(".pdf"):
            reader = PdfReader(filepath)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    full_text += f"\n[Страница {page_num + 1}]\n{text}\n"

            # Исправленный вызов: получаем два значения
            image_paths, ocr_texts_combined = extract_images_from_pdf(filepath)
            # Добавляем OCR текст из utils.py в основной текст
            if ocr_texts_combined.strip():
                 full_text += f"\n[Текст со скриншотов из PDF]:\n{ocr_texts_combined}\n"
            # ВАЖНО: В текущей версии utils.py метаданные изображений (page_num, order) не возвращаются.
            # Они просто сохраняются в файлы, и возвращаются пути.
            # Поэтому images_metadata будет содержать только пути. Нужно создать базовые метаданные.
            images_metadata = []
            for idx, path in enumerate(image_paths):
                 # Создаем базовые метаданные, так как utils.py их не предоставляет
                 images_metadata.append({
                     "page_num": 0, # utils.py не предоставляет номер страницы PDF для изображений
                     "order": idx,
                     "img_path": path,
                     "caption": f"Изображение {idx + 1} из {filename}",
                     "ocr_text": "OCR выполнен при извлечении (см. общий текст выше)" # OCR уже добавлен в full_text
                 })


        elif filename.lower().endswith(".docx"):
            doc = Document(filepath)
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            images_metadata = [] # Для DOCX мы собираем метаданные напрямую

            for i, rel in enumerate(doc.part.rels.values()):
                if "image" in rel.target_ref:
                    try:
                        image = rel._target
                        img_data = image.blob
                        # Используем Path для более надежного создания имени файла
                        safe_filename = Path(filename).stem
                        img_path = f"{MEDIA_DIR}/{safe_filename}_img_{i}.jpg"
                        with open(img_path, "wb") as f:
                            f.write(img_data)

                        # pil_img = Image.open(BytesIO(img_data)) # Если импортировали Image
                        # ocr_text = pytesseract.image_to_string(pil_img, lang='eng+rus').strip() # Если импортировали pytesseract
                        # Пока используем заглушку, так как OCR в utils.py для DOCX не реализован
                        ocr_text = "OCR для DOCX изображений выполняется отдельно (не реализовано в этом примере)"

                        if True: # Добавляем изображение даже без OCR текста
                            full_text += f"\n[Изображение DOCX {i + 1}]: Сохранено как {img_path}\n" # Опционально: добавить в текст

                        images_metadata.append({
                            "page_num": 0, # DOCX не имеет строгой структуры страниц для изображений
                            "order": i,
                            "img_path": img_path,
                            "caption": f"Изображение {i + 1} из {filename}",
                            "ocr_text": ocr_text # Или пустая строка, если не выполняли OCR
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
                    "images": json.dumps(images_metadata) # Сохраняем все метаданные изображений
                }
                add_document(f"{filename}_chunk_{i}", chunk, metadata)

    print("✅ Документы загружены с сохранением изображений (пути и базовые метаданные).")
