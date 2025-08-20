# rag/rag_engine.py
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from dotenv import load_dotenv
import os
import json
import re

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


def add_document(doc_id: str, text: str, metadata: dict):
    """
    Добавляет документ в векторное хранилище
    :param doc_id: Уникальный ID
    :param text: Текст документа
    :param metadata: Метаданные (источник, изображения и т.д.)
    """
    vs = get_vectorstore()
    vs.add_texts([text], metadatas=[metadata], ids=[doc_id])


def extract_link_from_text(text):
    """Извлекает ссылку из текста документа"""
    # Ищем URL в конце документа
    url_pattern = r'https?://[^\s/$.?#].[^\s]*'
    urls = re.findall(url_pattern, text)
    return urls[-1] if urls else ""


def query_rag(question: str, top_k=3):
    """
    Выполняет RAG-поиск и возвращает ответ с изображениями
    """
    vs = get_vectorstore()
    results = vs.similarity_search_with_score(question, k=top_k)

    context_parts = []
    all_images = []
    source_files = set()
    links = []
    best_result = None
    best_score = float('inf')

    for res, score in results:
        context_parts.append(res.page_content)
        if res.metadata.get("images"):
            try:
                imgs = json.loads(res.metadata["images"])
                all_images.extend(imgs)
            except Exception as e:
                print(f"Ошибка парсинга images: {e}")
                
        # Сохраняем источник документа
        source = res.metadata.get("source")
        if source:
            source_files.add(source)
            
        # Извлекаем ссылки из текста
        link = extract_link_from_text(res.page_content)
        if link:
            links.append(link)
            
        # Находим наиболее релевантный результат
        if score < best_score:
            best_score = score
            best_result = res

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

    # Формируем промпт с более подробной инструкцией
    context_text = "\n\n---\n\n".join(context_parts)
    
    prompt = f"""
Ты — помощник по корпоративной документации. Твоя задача — дать полный и понятный ответ на вопрос сотрудника, 
основываясь на предоставленных инструкциях.

Вопрос сотрудника: {question}

Инструкции:
{context_text}

Требования к ответу:
1. Дай развернутый ответ, объясни по шагам, что нужно сделать
2. Если в инструкции есть список шагов, перечисли их
3. Если есть изображения, укажи: "Вот скриншоты из инструкции:"
4. Всегда указывай источник документа
5. Если в конце документа есть ссылка на полную инструкцию, добавь её в ответ как "Подробнее: [ссылка]"
6. Формат ответа: JSON с полями "answer", "images", "source", "link_to_document"

Пример:
{{
  "answer": "Для решения проблемы выполните следующие шаги:\\n1. Откройте приложение...\\n2. Перейдите в настройки...\\n3. Отключите энергосберегающий режим",
  "images": [
    {{"img_path": "media/manual_page5_0.jpg", "caption": "Настройки приложения"}}
  ],
  "source": "Установка Ростелеком ВАТС.docx",
  "link_to_document": "https://fotonmotor.bitrix24.ru/~Qo10p"
}}
"""

    try:
        response = llm.invoke(prompt)
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            # Ограничиваем количество изображений до 3
            data["images"] = data.get("images", [])[:3]
            # Если в ответе нет ссылки, используем найденную в документе
            if not data.get("link_to_document") and links:
                data["link_to_document"] = links[0]
            return data
        else:
            # Если не удалось распарсить JSON, возвращаем текст как есть
            return {
                "answer": response[:1000], 
                "images": sorted_images[:3] if sorted_images else [], 
                "source": best_result.metadata.get("source", "") if best_result else "",
                "link_to_document": links[0] if links else ""
            }
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        return {
            "answer": "Извините, не удалось сформировать ответ. Попробуйте переформулировать вопрос.", 
            "images": sorted_images[:3] if sorted_images else [], 
            "source": best_result.metadata.get("source", "") if best_result else "",
            "link_to_document": links[0] if links else ""
        }