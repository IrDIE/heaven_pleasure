from pydantic_settings import BaseSettings
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import os


class Config(BaseSettings):
    """Конфигурация для системы Code Review."""
    
    # LLM настройки
    OLLAMA_BASE_URL: str = "http://192.168.31.49:11434/v1"
    OLLAMA_API_KEY: str = "ollama"
    
    # Модели для разных задач
    CODE_LLM_MODEL: str = "qwen2.5-coder"  # Для архитектуры и качества кода
    GENERAL_LLM_MODEL: str = "qwen2.5"  # Для общего анализа
    DATA_EXTRACTION_MODEL: str = "qwen2.5"  # Для тестировщика
    
    # Рабочая директория
    WORKSPACE_DIR: str = os.path.join(os.path.dirname(__file__), "code_review_workspace")

    
    # Настройки Docker для тестов
    USE_DOCKER: bool = False  # Для code review обычно не нужен
    DOCKER_IMAGE: Optional[str] = None
    
    # Стоимость токенов (опционально)
    TOKEN_INPUT_COST: float = 0.0  # Можно установить 0 если не важно
    TOKEN_OUTPUT_COST: float = 0.0
    
    # Настройки review
    MAX_REVIEW_RETRIES: int = 3  # Попытки получить валидный ответ от агента
    ENABLE_TEST_EXECUTION: bool = True  # Запускать ли тесты после создания
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"