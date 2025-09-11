from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY", None)
FOLDER_ID = os.getenv("FOLDER_ID", None)


class Config(BaseSettings):
    """Конфигурация для системы Code Review."""

    # OpenAI-совместимый endpoint для YandexGPT
    OPENAI_COMPAT_BASE_URL: str = "https://llm.api.cloud.yandex.net/v1"

    # Две модели: лёгкая и тяжёлая
    BASE_LLM_MODEL: str = f"gpt://{FOLDER_ID}/yandexgpt-lite"

    CODE_LLM_MODEL: str = f"gpt://{FOLDER_ID}/gpt-oss-120b/latest"

    # Ключ
    OLLAMA_API_KEY: str = API_KEY

    # Рабочая директория
    WORKSPACE_DIR: str = os.path.join(os.path.dirname(__file__), "code_review_workspace")

    # Настройки Docker
    USE_DOCKER: bool = False
    DOCKER_IMAGE: str | None = None

    # Стоимость токенов
    TOKEN_INPUT_COST: float = 0.0002
    TOKEN_OUTPUT_COST: float = 0.0002

    # Настройки review
    MAX_REVIEW_RETRIES: int = 3
    ENABLE_TEST_EXECUTION: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
