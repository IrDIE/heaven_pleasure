import json
import os
import re
import logging
from typing import Dict, Any
import argparse
import sys
import time

from config import Config
from config import (
    ArchitectureReviewResult,
    QualityReviewResult, 
    TesterResult,
    ReviewResults
)
from loggers import UnifiedLogger, TokenTracker

from pydantic import ValidationError
from autogen import ConversableAgent, UserProxyAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CodeReviewManager:
    def __init__(self, config: Config):
        self.config = config
        os.makedirs(config.WORKSPACE_DIR, exist_ok=True)
        
        # Логгеры
        self.logger = UnifiedLogger(config.WORKSPACE_DIR)
        self.token_tracker = TokenTracker(
            config.WORKSPACE_DIR, 
            config.TOKEN_INPUT_COST, 
            config.TOKEN_OUTPUT_COST
        )
        
        llm_config_base = {
            "config_list": [{
                "model": config.BASE_LLM_MODEL,                  
                "base_url": config.OPENAI_COMPAT_BASE_URL,        
                "api_key": config.OLLAMA_API_KEY,                
                "api_type": "openai",
            }],
            "temperature": 0.1,
            "timeout": 120,
        }

        llm_config_code = {
            "config_list": [{
                "model": config.CODE_LLM_MODEL,                  
                "base_url": config.OPENAI_COMPAT_BASE_URL,        
                "api_key": config.OLLAMA_API_KEY,                
                "api_type": "openai",
            }],
            "temperature": 0.0,
            "timeout": 120,
        }


        # Улучшенные промпты для агентов

        # Агент архитектурного анализа
        self.architecture_reviewer = ConversableAgent(
            name="АрхитекторРевьюер",
            system_message="""
            Вы — эксперт по архитектуре и структуре кода. Анализируете общую структуру, паттерны и принципы.

            СТРОГИЕ ПРАВИЛА:
            - НЕ решайте задачу за студента
            - НЕ исправляйте код напрямую
            - ТОЛЬКО анализируйте и указывайте на проблемы с ТОЧНЫМ местоположением
            - ТОЛЬКО русский язык
            - ОБЯЗАТЕЛЬНО возвращайте JSON в указанном формате

            ОБЛАСТИ АНАЛИЗА:
            - Архитектурные паттерны и принципы SOLID
            - Структура проекта и организация модулей
            - Разделение ответственности между компонентами
            - Соблюдение принципов чистого кода
            - Масштабируемость и поддерживаемость

            ОБЯЗАТЕЛЬНЫЙ ФОРМАТ JSON:
            {
                "agent": "АрхитекторРевьюер",
                "role": "reviewer",
                "name": "Архитектор-аналитик",
                "overall": "Общая оценка архитектуры одним предложением",
                "positives": [
                    {
                        "message": "Что сделано хорошо в архитектуре",
                        "file": "student_code.py",
                        "line": номер_строки
                    }
                ],
                "issues": [
                    {
                        "id": "ARCH-XXX-001",
                        "severity": "critical|major|minor",
                        "type": "architecture|structure|patterns|maintainability",
                        "file": "student_code.py",
                        "line": номер_строки,
                        "message": "Краткое описание архитектурной проблемы",
                        "recommendations": [
                            "Конкретная рекомендация по архитектуре 1",
                            "Конкретная рекомендация по архитектуре 2"
                        ]
                    }
                ]
            }

            ОПРЕДЕЛЕНИЕ НОМЕРА СТРОКИ:
            Внимательно проанализируйте код и найдите ТОЧНЫЙ номер строки:
            1. Пронумеруйте все строки кода от 1 до последней
            2. Для проблем в функциях/классах - укажите строку с определением (def/class)
            3. Для проблем в выражениях - укажите строку с первым вхождением проблемного кода
            4. Для архитектурных проблем - укажите строку начала соответствующего блока
            5. НЕ используйте 1 по умолчанию - найдите реальную строку!

            УРОВНИ СЕРЬЕЗНОСТИ:
            - critical: критические архитектурные недочеты (нарушение SOLID, отсутствие разделения ответственности)
            - major: серьезные проблемы структуры (плохая организация, сложность поддержки)
            - minor: мелкие недочеты организации кода

            ТИПЫ ПРОБЛЕМ:
            - architecture: фундаментальные архитектурные проблемы
            - structure: проблемы структуры и организации
            - patterns: неправильное использование паттернов проектирования
            - maintainability: проблемы поддерживаемости кода

            ЗАПРЕЩЕНО:
            - Давать готовые решения
            - Переписывать код
            - Решать логические задачи вместо студента
            - Использовать номер строки 1 без анализа

            Требования к выводу:
            - Верните ТОЛЬКО валидный JSON-объект без markdown оформления
            - Все поля обязательны, пустые массивы вместо отсутствующих данных
            - Максимум 10 issues
            - Номер строки должен быть найден через анализ кода, не по умолчанию
            """,
            llm_config=llm_config_base
        )

        # Агент анализа качества кода        
        self.quality_reviewer = ConversableAgent(
            name="КачествоРевьюер",
            system_message="""
            Вы — эксперт по качеству кода, стилю и best practices. Анализируете техническое качество реализации.

            СТРОГИЕ ПРАВИЛА:
            - НЕ решайте задачу за студента
            - НЕ показывайте исправленный код
            - ТОЛЬКО указывайте на недостатки с ТОЧНЫМ местоположением
            - ТОЛЬКО русский язык
            - ОБЯЗАТЕЛЬНО возвращайте JSON в указанном формате

            ОБЛАСТИ АНАЛИЗА:
            - Соблюдение стандартов кодирования (PEP 8)
            - Качество именования переменных и функций  
            - Обработка ошибок и исключений
            - Производительность и оптимизация
            - Читаемость и документирование кода
            - Безопасность кода

            ОБЯЗАТЕЛЬНЫЙ ФОРМАТ JSON:
            {
                "agent": "КачествоРевьюер",
                "role": "reviewer",
                "name": "Эксперт по качеству",
                "overall": "Общая оценка качества кода одним предложением",
                "issues": [
                    {
                        "id": "QUAL-XXX-001",
                        "severity": "critical|major|minor",
                        "type": "style|naming|performance|security|readability|error_handling",
                        "file": "student_code.py",
                        "line": номер_строки,
                        "message": "Краткое описание проблемы качества",
                        "recommendations": [
                            "Конкретная рекомендация по улучшению качества 1",
                            "Конкретная рекомендация по улучшению качества 2"
                        ]
                    }
                ]
            }

            ОПРЕДЕЛЕНИЕ НОМЕРА СТРОКИ:
            Тщательно анализируйте код построчно:
            1. Нумеруйте строки от 1 до конца файла
            2. Для проблем стиля - укажите строку с нарушением
            3. Для проблем именования - строку с объявлением переменной/функции
            4. Для проблем производительности - строку с неэффективным кодом
            5. Для проблем безопасности - строку с уязвимым кодом
            6. НЕ используйте 1 как значение по умолчанию!

            УРОВНИ СЕРЬЕЗНОСТИ:
            - critical: критические проблемы (уязвимости безопасности, серьезные ошибки обработки исключений)
            - major: серьезные нарушения стандартов (PEP 8, производительность)
            - minor: мелкие недочеты стиля и читаемости

            ТИПЫ ПРОБЛЕМ:
            - style: нарушения стиля кода (PEP 8)
            - naming: проблемы именования переменных/функций
            - performance: неэффективный код
            - security: проблемы безопасности
            - readability: проблемы читаемости и документации
            - error_handling: неправильная обработка ошибок

            ЗАПРЕЩЕНО:
            - Показывать исправленные версии кода
            - Давать конкретные решения алгоритмических проблем
            - Писать код вместо студента
            - Использовать произвольные номера строк

            Требования к выводу:
            - Верните ТОЛЬКО валидный JSON-объект без markdown оформления
            - Все поля обязательны
            - Максимум 10 issues
            - Каждый номер строки должен соответствовать реальной проблеме в коде
            """,
            llm_config=llm_config_base
        )

        # Агент тестирования
        self.tester_agent = ConversableAgent(
            name="Тестировщик",
            system_message="""
            Вы — эксперт по тестированию кода. Ваша задача — сгенерировать unit-тесты и предоставить краткое резюме покрытия.

            СТРОГИЕ ПРАВИЛА:
            - НЕ исправляйте и НЕ оценивайте код студента
            - НЕ включайте исправленный код студента - только тесты
            - ВСЕ ИМПОРТЫ ИЗ ТЕСТИРУЕМОГО МОДУЛЯ — ТОЛЬКО ВНУТРИ ТЕСТОВЫХ ФУНКЦИЙ
            - ПРОВЕРЯЙТЕ ЗАВИСИМОСТИ: try: importlib.import_module(dep) except Exception: pytest.skip(f"Отсутствует зависимость: {dep}")
            - НИКАКИХ сетевых запросов или внешних вызовов
            - Если зависимость отсутствует — тест помечается как SKIPPED

            ФУНКЦИИ:
            - Создание unit-тестов для всех публичных функций/методов
            - Тестирование граничных случаев и некорректных входов
            - Локальные импорты внутри каждого теста
            - Самодостаточные тесты для pytest

            ОБЯЗАТЕЛЬНЫЙ ФОРМАТ JSON:
            {
                "agent": "tester",
                "role": "tester",
                "archive": null,
                "root": null,
                "summary": {
                    "issue_counts": { "major": 0, "minor": 0 },
                    "highlights": [
                        "Создано X тестов для Y функций",
                        "Покрыты граничные случаи для функции Z",
                        "Добавлены тесты на обработку ошибок",
                        "Протестированы основные сценарии использования"
                    ]
                },
                "issues": [],
                "test_code": "# ПОЛНЫЙ КОД ТЕСТОВ\nimport pytest\nimport importlib\n\n# Ваши тесты здесь..."
            }

            ГЕНЕРАЦИЯ HIGHLIGHTS:
            Создайте 3-5 кратких описаний того, что покрывают тесты:
            - Количество созданных тестов и протестированных функций
            - Какие типы тестов добавлены (граничные случаи, ошибки, нормальные сценарии)
            - Особые случаи тестирования (если есть)
            - Общий охват функциональности

            ПРОЦЕСС:
            1. Определите все тестируемые публичные функции/методы
            2. Для каждой создайте тесты: нормальные случаи, граничные, ошибки
            3. В каждом тесте: проверка зависимостей → локальный импорт → тесты
            4. Сформируйте highlights с описанием покрытия
            5. Поместите весь код в поле test_code

            СТРУКТУРА ТЕСТОВ:
            ```python
            import pytest
            import importlib

            def test_function_name_normal_case():
                # Проверка зависимостей
                try:
                    importlib.import_module('required_module')
                except ImportError:
                    pytest.skip("Отсутствует зависимость: required_module")
                
                # Локальный импорт
                from student_code import function_name
                
                # Тесты
                assert function_name(input) == expected_output
            ```

            ЗАПРЕЩЕНО:
            - Любые issues, советы, оценки, рекомендации
            - Исправления кода студента
            - Глобальные импорты тестируемого кода

            Требования к выводу:
            - ТОЛЬКО валидный JSON без markdown оформления
            - Обязательные highlights с описанием тестового покрытия
            - Полный код тестов в поле test_code
            - issues всегда пустой массив
            """,
            llm_config=llm_config_code
        )

        # User proxy
        code_execution_config = {
            "work_dir": config.WORKSPACE_DIR,
            "use_docker": config.DOCKER_IMAGE if config.USE_DOCKER else False,
        }
        
        self.user_proxy = UserProxyAgent(
            name="Оркестратор",
            human_input_mode="NEVER",
            code_execution_config=code_execution_config,
            is_termination_msg=self._is_termination_msg,
            max_consecutive_auto_reply=1,
            default_auto_reply="",
        )
    
    def _is_termination_msg(self, msg: dict) -> bool:
        content = (msg.get("content") or "").strip()

        if "tool_calls" in str(msg):
            return False
        if content == "TERMINATE":
            return True

        return False

    
    def _extract_json(self, content: str) -> dict:
        """Извлечение JSON из текста."""
        if not content:
            return {}
        
        # JSON в markdown
        markdown_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', content)
        if markdown_match:
            try:
                return json.loads(markdown_match.group(1))
            except:
                pass
        
        # Обычный JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass
        
        return {}
    
    def _create_fresh_user_proxy(self):
        """Create a fresh user proxy for each agent interaction."""
        code_execution_config = {
            "work_dir": self.config.WORKSPACE_DIR,
            "use_docker": self.config.DOCKER_IMAGE if self.config.USE_DOCKER else False,
        }
        
        return UserProxyAgent(
            name="Оркестратор",
            human_input_mode="NEVER",
            code_execution_config=code_execution_config,
            is_termination_msg=self._is_termination_msg,
            max_consecutive_auto_reply=1,
            default_auto_reply="",
        )
        
 
    def _invoke_agent(self, agent: ConversableAgent, prompt: str, max_retries: int = None) -> dict:
        """Вызов агента и получение JSON ответа с улучшенной изоляцией."""
        if max_retries is None:
            max_retries = self.config.MAX_REVIEW_RETRIES
        
        # Reset agent before starting
        agent.reset()
        
        for attempt in range(max_retries):
            logger.info(f"Вызов {agent.name}, попытка {attempt + 1}/{max_retries}")
            
            # Create fresh user proxy for this specific interaction
            temp_user_proxy = self._create_fresh_user_proxy()
            
            try:
                # Add small delay to prevent overwhelming Ollama
                if attempt > 0:
                    time.sleep(1)
                
                logger.info(f"Initiating chat with {agent.name}")
                
                chat_result = temp_user_proxy.initiate_chat(
                    recipient=agent,
                    message=prompt,
                    max_turns=1,
                    clear_history=True,
                    silent=False,
                )
                
                logger.info(f"Chat completed for {agent.name}")
                
                # Extract response
                last_message = ""
                if hasattr(chat_result, "chat_history") and chat_result.chat_history:
                    for msg in reversed(chat_result.chat_history):
                        content = msg.get("content", "").strip()
                        sender = msg.get("name", msg.get("role", ""))
                        
                        if sender != "Оркестратор" and content:
                            last_message = content
                            break
                
                logger.info(f"Extracted message length: {len(last_message)}")
                
            except Exception as e:
                logger.warning(f"Ошибка в чате с {agent.name}: {e}")
                
                # Fallback with delay
                time.sleep(2)
                
                try:
                    logger.info(f"Trying fallback for {agent.name}")
                    response = agent.generate_reply([{"role": "user", "content": prompt}])
                    last_message = response if response else ""
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {agent.name}: {fallback_error}")
                    last_message = ""
            
            # Track tokens
            self.token_tracker.track_agent_call(
                agent_name=agent.name,
                input_text=prompt,
                output_text=last_message
            )
            self.logger._write_raw(f"\n=== OUTPUT <- {agent.name} ===\n{last_message}\n")
            
            # Extract JSON
            if last_message:
                json_data = self._extract_json(last_message)
                if json_data:
                    logger.info(f"Successfully extracted JSON from {agent.name}")
                    return json_data
                else:
                    logger.warning(f"No valid JSON found in response from {agent.name}")
            
            # Retry with simplified prompt
            if attempt < max_retries - 1:
                prompt = f"ВЕРНИТЕ ТОЛЬКО JSON!\n{prompt}"
                logger.info(f"Retrying with simplified prompt for {agent.name}")
                time.sleep(2)  # Longer delay before retry
        
        logger.error(f"Failed to get valid response from {agent.name} after {max_retries} attempts")
        return {}
        
    def _sanitize_test_code(self, code: str, module_name: str) -> str:
        """Заменяет реальные переводы строк внутри '...' и "..." на \\n.
        Трёхкавычные строки не трогаем. Экранирование \\ учитываем."""
        in_str = False
        quote = None
        triple = False
        esc = False
        i = 0
        n = len(code)
        out = []

        def starts_triple(s, idx, q):
            return idx + 2 < n and s[idx] == q and s[idx + 1] == q and s[idx + 2] == q

        while i < n:
            ch = code[i]

            if not in_str:
                if ch in ("'", '"'):
                    # начало строки
                    if starts_triple(code, i, ch):
                        in_str, quote, triple, esc = True, ch, True, False
                        out.append(ch * 3)
                        i += 3
                    else:
                        in_str, quote, triple, esc = True, ch, False, False
                        out.append(ch)
                        i += 1
                else:
                    out.append(ch)
                    i += 1
            else:
                if triple:
                    # ищем конец трёхкавычной
                    if ch == quote and i + 2 < n and code[i + 1] == quote and code[i + 2] == quote:
                        out.append(quote * 3)
                        i += 3
                        in_str, quote, triple, esc = False, None, False, False
                    else:
                        out.append(ch)
                        i += 1
                else:
                    if esc:
                        out.append(ch)
                        i += 1
                        esc = False
                    elif ch == "\\":
                        out.append("\\")
                        i += 1
                        esc = True
                    elif ch == "\n":
                        out.append("\\n")
                        i += 1
                    elif ch == quote:
                        out.append(quote)
                        i += 1
                        in_str, quote, triple, esc = False, None, False, False
                    else:
                        out.append(ch)
                        i += 1
        o = "".join(out)
        module_name = module_name.replace('.py', '')
        pattern = re.compile(rf"^(?:from\s+{re.escape(module_name)}\s+import\s+\*.*|import\s+{re.escape(module_name)}.*)$",
                            flags=re.MULTILINE)
        cleaned = re.sub(pattern, "", o)
        return cleaned

    

    def review_code(self, code: str, filename: str = "student_code.py", run_tests: bool = True) -> ReviewResults:
        """Основной метод code review с улучшенной изоляцией агентов."""
        logger.info("Начало code review")
        self.logger.log_phase_start("Code Review", 1)
        
        # Save code
        self._save_code(code, filename)
        
        # Initialize results
        results = ReviewResults(filename=filename)
        
        # Base prompt for all agents
        base_prompt = f"""
        Проанализируйте следующий код и верните результат в требуемом JSON формате.
        
        Файл: {filename}
        
        КОД:
        ```python
        {code}
        ```
        
        ВЕРНИТЕ ТОЛЬКО JSON В ВАШЕМ ФОРМАТЕ!
        """
        
        # 1. Architecture review
        logger.info("=" * 50)
        logger.info("Запуск архитектурного анализа")
        logger.info("=" * 50)
        
        arch_json = self._invoke_agent(self.architecture_reviewer, base_prompt)
        if arch_json:
            try:
                results.architecture_review = ArchitectureReviewResult(**arch_json)
                self.logger.log_agent_action("АрхитекторРевьюер", "Анализ завершен", "Успешно")
            except ValidationError as e:
                logger.error(f"Ошибка валидации архитектурного review: {e}")
                self.logger.log_error("АрхитекторРевьюер", str(e))
        
        # 2. Quality review
        logger.info("=" * 50)
        logger.info("Запуск анализа качества")
        logger.info("=" * 50)
        
        quality_json = self._invoke_agent(self.quality_reviewer, base_prompt)
        if quality_json:
            try:
                results.quality_review = QualityReviewResult(**quality_json)
                self.logger.log_agent_action("КачествоРевьюер", "Анализ завершен", "Успешно")
            except ValidationError as e:
                logger.error(f"Ошибка валидации quality review: {e}")
                self.logger.log_error("КачествоРевьюер", str(e))
        
        # 3. Testing
        logger.info("=" * 50)
        logger.info("Запуск тестирования")
        logger.info("=" * 50)
        
        test_json = self._invoke_agent(self.tester_agent, base_prompt)
        if test_json:
            try:
                results.testing_results = TesterResult(**test_json)
                self.logger.log_agent_action("Тестировщик", "Анализ завершен", "Успешно")
                
                # Run tests if code exists
                if run_tests and self.config.ENABLE_TEST_EXECUTION:
                    raw_code = getattr(results.testing_results, "test_code", None)
                    if raw_code:
                        safe_code = self._sanitize_test_code(raw_code, filename)
                        test_exec_results = self._run_tests(safe_code, filename)
                        results.test_execution = test_exec_results
                
                # Remove test code from results
                results.testing_results.test_code = None
                    
            except ValidationError as e:
                logger.error(f"Ошибка валидации testing review: {e}")
                self.logger.log_error("Тестировщик", str(e))
        
        # Save and output results
        self._save_results(results)
        self._print_summary(results)
        
        # End session
        self.logger.log_session_end()
        self.token_tracker.log_session_summary()
        
        return results
    def _save_code(self, code: str, filename: str) -> str:
        """Сохранение кода."""
        filepath = os.path.join(self.config.WORKSPACE_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        logger.info(f"Код сохранен: {filepath}")
        return filepath
    
    def _run_tests(self, test_code: str, main_filename: str) -> Dict[str, Any]:
        """Запуск тестов."""
        test_filename = f"test_{main_filename}"
        test_path = os.path.join(self.config.WORKSPACE_DIR, test_filename)
        
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        
        logger.info(f"Тесты сохранены: {test_path}")
        
        # Команда запуска
        test_command = f"cd {self.config.WORKSPACE_DIR} && python -m pytest {test_filename} -v --tb=short"
        
        try:
            exit_code, output = self.user_proxy.execute_code_blocks([("sh", test_command)])
            
            test_results = {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "output": output,
                "test_file": test_filename
            }
            
            if exit_code == 0:
                logger.info("Тесты пройдены успешно")
                self.logger.log_success("Все тесты пройдены")
            else:
                logger.warning(f"Тесты провалены с кодом {exit_code}")
                self.logger.log_error("Тесты", f"Провалены с кодом {exit_code}")
            
            return test_results
            
        except Exception as e:
            logger.error(f"Ошибка при запуске тестов: {e}")
            return {"success": False, "error": str(e), "test_file": test_filename}
    
    def _save_results(self, results: ReviewResults):
        """Сохранение результатов."""
        output_file = os.path.join(self.config.WORKSPACE_DIR, "review_results.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results.model_dump(exclude_none=True), f, ensure_ascii=False, indent=2)
        logger.info(f"Результаты сохранены: {output_file}")

    def _print_summary(self, results: ReviewResults):
        """Логирование сводки через UnifiedLogger."""

        self.logger.log_phase_start("Code Review Summary", 99)
        self.logger.log_agent_action("System", f"Файл: {results.filename}")

        # Архитектурный review
        if results.architecture_review:
            r = results.architecture_review
            self.logger.log_agent_action(
                "АрхитекторРевьюер",
                "Архитектурный анализ",
                f"Общая оценка: {r.overall} | Позитивных: {len(r.positives)} | Проблем: {len(r.issues)}"
            )

        # Quality review
        if results.quality_review:
            r = results.quality_review
            self.logger.log_agent_action(
                "КачествоРевьюер",
                "Анализ качества",
                f"Общая оценка: {r.overall} | Проблем: {len(r.issues)}"
            )

        # Testing (анализ JSON от агента)
        if results.testing_results:
            r = results.testing_results
            major = r.summary.get("issue_counts", {}).get("major", 0)
            minor = r.summary.get("issue_counts", {}).get("minor", 0)
            self.logger.log_agent_action(
                "Тестировщик",
                "Тестирование",
                f"Major: {major}, Minor: {minor}, Test code: {'Да' if r.test_code else 'Нет'}"
            )

        # Выполнение тестов (результаты раннера)
        if results.test_execution:
            te = results.test_execution
            status = "PASSED" if te.success else "FAILED"
            details = f"Файл: {te.test_file} | Код: {te.exit_code}"
            self.logger.log_agent_action("Runner", f"Tests {status}", details)

            if te.tests:
                total = len(te.tests)
                passed = sum(1 for t in te.tests if t.status == "passed")
                failed = sum(1 for t in te.tests if t.status == "failed")
                skipped = sum(1 for t in te.tests if t.status == "skipped")
                self.logger.log_agent_action(
                    "Runner",
                    "Подробности",
                    f"Всего: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}"
                )
                for t in te.tests:
                    if t.status == "failed":
                        msg = f"{t.name}: {t.message}" if t.message else t.name
                        self.logger.log_error("Runner", f"Тест упал: {msg}")

        self.logger.log_session_end()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Запуск мультиагентного code review.")
    parser.add_argument(
        "-f", "--file",
        help="Путь к анализируемому .py файлу. Если не задан, используется небольшой пример.",
        default=None,
    )
    parser.add_argument(
        "--filename",
        help="Имя файла при сохранении в рабочей папке.",
        default="student_code.py",
    )
    parser.add_argument(
        "--no-run-tests",
        help="Не выполнять автозапуск сгенерированных тестов.",
        action="store_true",
    )
    args = parser.parse_args()

    # Конфигурация проекта (ожидается, что класс Config заполнит все нужные поля)
    config = Config()

    # Загрузка кода
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as fh:
                code_text = fh.read()
        except OSError as err:
            print(f"Ошибка чтения файла: {err}", file=sys.stderr)
            sys.exit(2)
    else:
        # Минимальный пример, если файл не передан
        code_text = (
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
        )

    # Запуск обзора
    manager = CodeReviewManager(config)
    results = manager.review_code(
        code=code_text,
        filename=args.filename,
        run_tests=not args.no_run_tests,
    )

    # Код выхода: провал тестов -> 1, иначе 0
    failed_tests = bool(results.test_execution) and not getattr(results.test_execution, "success", False)

    sys.exit(1 if failed_tests else 0)
