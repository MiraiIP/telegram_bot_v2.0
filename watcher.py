# watcher.py
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from rag.document_loader import load_documents_from_folder
import time
import os
from pathlib import Path

DOCUMENTS_DIR = "documents"
CHROMA_DIR = "chroma_db"
PROCESSED_DIR = "processed"

class DocumentHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        self.process(event)

    def on_created(self, event):
        if event.is_directory:
            return
        self.process(event)

    def process(self, event):
        src_path = event.src_path
        if src_path.lower().endswith((".pdf", ".docx", ".doc")):
            print(f"🔄 Обнаружено изменение: {src_path}")
            time.sleep(1)  # Дать файлу полностью записаться

            # Удаляем метку обработки, чтобы перезагрузить
            filename = Path(src_path).name
            processed_flag = Path(PROCESSED_DIR) / f"{filename}.processed"
            if processed_flag.exists():
                processed_flag.unlink()

            # Перезагружаем
            self.rebuild_db()

    def rebuild_db(self):
        """Переиндексировать все документы"""
        print("🔄 Перестройка базы знаний...")
        # Удаляем старую Chroma
        if Path(CHROMA_DIR).exists():
            import shutil
            shutil.rmtree(CHROMA_DIR)

        # Пересоздаём processed
        proc = Path(PROCESSED_DIR)
        if proc.exists():
            shutil.rmtree(proc)
        proc.mkdir()

        # Перезагружаем
        load_documents_from_folder(DOCUMENTS_DIR)
        print("✅ База знаний обновлена.")

def start_watcher():
    event_handler = DocumentHandler()
    observer = Observer()
    observer.schedule(event_handler, DOCUMENTS_DIR, recursive=False)
    observer.start()
    print(f"👀 Слежение за папкой: {DOCUMENTS_DIR}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 Слежение остановлено.")
    observer.join()

if __name__ == "__main__":
    Path(PROCESSED_DIR).mkdir(exist_ok=True)
    start_watcher()