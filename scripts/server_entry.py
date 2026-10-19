"""Entry point used by PyInstaller to freeze the Vision backend (vision-server.exe)."""
import multiprocessing

from vision.main import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    run()
