# rag/rag_engine.py
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from dotenv import load_dotenv
import os
import json

load_dotenv()

CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Инициализация
embedding = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
llm = OllamaLLM(model="llama3:8b-instruct-q4_K_M")

vectorstore = None


def get_vectorstore():
    global vectorstore
    if vectorstore is None:
        vectorstore = Chroma(
            persist_directory=CHROMA_DIR,
            embedding_function=embedding
        )
    return vectorstore


def add_document(doc_id: str, text: str, meta dict):
    """
    Добавляет документ в векторное хранилище
    :param doc_id: Уникальный ID
    :param text: Текст документа
    :param meta Метаданные (источник, изображения и т.д.)
    """
    vs = get_vectorstore()
    vs.add_texts([text], metadatas=[metadata], ids=[doc_id])
    # Сохранение автоматическое — .persist() не нужно


def query_rag(question: str, top_k=3):
    """
    Выполняет RAG-поиск и возвращает ответ с изображениями
    """
    vs = get_vectorstore()
    results = vs.similarity_search(question, k=top_k)

    context_parts = []
    all_images = []

    for res in results:
        context_parts.append(res.page_content)
        if res.metadata.get("images"):
            try:
                imgs = json.loads(res.metadata["images"])
                all_images.extend(imgs)
            except Exception as e:
                print(f"Ошибка парсинга images: {e}")

    # Уникальные изображения
    seen = set()
    unique_images = []
    for img in all_images:
        path = img.get("img_path")
        if path and path not in seen:
            seen.add(path)
            unique_images.append(img)

    # Сортировка по странице и порядку
    sorted_images = sorted(unique_images, key=lambda x: (x.get("page_num", 999), x.get("order", 0)))

    # Формируем промпт
    prompt = f"""
Ты — помощник по документации. Отвечай кратко, по делу.
Если есть скриншоты — укажи: "Вот скриншоты из инструкции:"

Вопрос: {question}
Контекст: {" ".join(context_parts)}

Инструкция:
- Ответь на вопрос.
- Если есть изображения — верни их в порядке появления.
- Формат: JSON с полями "answer", "images".

Пример:
{{
  "answer": "Нажмите F12.",
  "images": [
    {{"img_path": "media/manual_page5_0.jpg", "caption": "Кнопка F12"}}
  ]
}}
"""

    try:
        response = llm.invoke(prompt)
        import re
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            data["images"] = data.get("images", [])[:3]  # макс. 3 скрина
            return data
        return {"answer": response[:500], "images": []}
    except Exception as e:
        return {"answer": f"Ошибка генерации: {e}", "images": []}