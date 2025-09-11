import json
import os
import re
import logging
from typing import Dict, Any, Optional
import argparse
import sys
import time

from src.llm.config import Config
from src.llm.config import (
    ArchitectureReviewResult,
    QualityReviewResult, 
    TesterResult,
    ReviewResults
)
from src.llm.loggers import UnifiedLogger, TokenTracker

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
        self.tester_agent = ConversableAgent(
            name="Тестировщик",
            system_message="""
        Вы — эксперт по тестированию ПО на любых языках. Ваша задача — сгенерировать автотесты и краткое резюме покрытия.

        СТРОГИЕ ПРАВИЛА:
        - НЕ исправляйте и НЕ оценивайте код студента.
        - Никаких советов/рекомендаций — только тесты и краткое резюме.
        - НИКАКИХ сетевых запросов или внешних сервисов.
        - Тесты должны быть самодостаточными и запускаться стандартным инструментом для целевого языка/стека.
        - Для Python: все импорты тестируемого кода — только внутри тестовых функций.
        - Для других языков: аналогично — подключения модулей/пакетов/юнитов делайте внутри конкретных тест-кейсов.
        - Если нет нужного раннера/SDK/зависимости — помечайте тест как SKIPPED/IGNORED (механизмом данного фреймворка).

        ФУНКЦИИ:
        - Создание автотестов для всех публичных функций/методов/API (насколько это возможно).
        - Тестирование нормальных сценариев, граничных случаев и некорректных входов.
        - Локальные подключения тестируемых модулей внутри каждого теста.
        - Самодостаточные тесты под типичный раннер языка:
        - Python → pytest
        - JavaScript/TypeScript → Jest (или Vitest)
        - Go → go test
        - Java/Kotlin → JUnit (Gradle/Maven)
        - C/C++ → CTest/GoogleTest (CMake)
        - Rust → cargo test
        - C# → dotnet test (xUnit/NUnit)

        Если стек явно угадывается из файлов/структуры — используйте соответствующий раннер. Иначе выберите наиболее типичный.

        ПРОВЕРКА ЗАВИСИМОСТЕЙ:
        - В начале каждого теста выполняйте проверку критичных зависимостей и инструмента тестирования.
        - Если зависимость/инструмент недоступны — корректно пометьте тест как SKIPPED/IGNORED с сообщением вида:
        - Python (pytest): pytest.skip("Отсутствует зависимость: <dep>")
        - Jest: test.skip("Отсутствует зависимость: <dep>", () => {})
        - Go: t.Skip("Отсутствует зависимость: <dep>")
        - JUnit: Assumptions.assumeTrue(false, "Отсутствует зависимость: <dep>")
        и т.д. — по канонам выбранного фреймворка.

        ГЕНЕРАЦИЯ ТЕСТОВ:
        1) Определите тестируемые публичные сущности (функции/методы/эндпоинты/CLI).
        2) Для каждой — сделайте набор тестов: нормальные случаи, границы, ошибки/исключения.
        3) Все подключения тестируемого кода — внутри конкретных тестов.
        4) Запрет на глобальные хелперы, которые мутируют код студента. Можно создавать только тестовые фикстуры/данные.
        5) Если нужен дополнительный файл (конфиг, фикстуры, package.json, Cargo.toml, CMakeLists.txt и т.п.) — добавьте его в поле "archive".

        ОБЯЗАТЕЛЬНЫЙ ВЫХОД (ТОЛЬКО валидный JSON, без markdown):
        {
        "agent": "tester",
        "role": "tester",
        "archive": null | [
            {"path": "tests/test_sample.py", "content": "<полный текст>"},
            {"path": "jest.config.js", "content": "<полный текст>"},
            {"path": "Cargo.toml", "content": "<полный текст>"}
        ],
        "root": null,
        "summary": {
            "issue_counts": {"major": 0, "minor": 0},
            "highlights": [
            "Создано X тестов для Y сущностей",
            "Покрыты граничные случаи для Z",
            "Добавлены проверки ошибок/исключений",
            "Протестированы основные сценарии использования"
            ]
        },
        "issues": [],
        "test_code": "<ПОЛНЫЙ КОД/СКРИПТ ОСНОВНОГО ТЕСТОВОГО ФАЙЛА ДЛЯ ВЫБРАННОГО РАННЕРА>"
        }

        ТРЕБОВАНИЯ:
        - Всегда заполняйте "test_code" полным содержимым основного файла тестов (например: tests/test_all.py, tests/main.test.ts, *_test.go, src/test/java/.../AllTests.java).
        - Если нужны доп. файлы — положите их в "archive" (список объектов {path, content}). Пути относительные, совместимые с типичным запуском.
        - "issues" — всегда пустой массив.
        - "highlights" — 3–5 коротких пунктов, отражающих покрытие.

        ПРИМЕР СТРУКТУРЫ (концептуально):
        - Python/pytest:
        - test_code: полный tests/test_all.py
        - archive (опц.): pytest.ini, conftest.py
        - JS/Jest:
        - test_code: полный tests/main.test.ts
        - archive (опц.): package.json (scripts.test="jest"), jest.config.js
        - Go:
        - test_code: полный pkg/thing/thing_test.go
        - archive (опц.): go.mod
        - Java/JUnit:
        - test_code: полный src/test/java/.../AllTests.java (или отдельный класс)
        - archive (опц.): build.gradle / pom.xml (с подключённым junit)

        ЗАПРЕЩЕНО:
        - Любые правки/оценки кода студента.
        - Сетевые вызовы.
        - Глобальные импорты/линковка тестируемого кода (делайте это внутри конкретных тестов).

        ФОРМАТ HIGHLIGHTS:
        - Кол-во тестов и протестированных сущностей.
        - Какие типы тестов добавлены (границы, ошибки, happy-path).
        - Особые сценарии (параметризация, property-based, таблиц. тесты — если применимо).
        - Краткий вывод об охвате.

        Выводите ТОЛЬКО валидный JSON по указанной схеме.
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
        
    
    def _invoke_agent(self, agent: ConversableAgent, prompt: str, max_retries: int = None, *, expected_kind: str, filename: str = "student_code.py") -> dict:
        if max_retries is None:
            max_retries = self.config.MAX_REVIEW_RETRIES
        agent.reset()

        def _need_fallback(msg: str) -> Optional[str]:
            if not msg:
                return "empty response"
            m = re.search(r"(cannot\s+review|can[’']?t\s+review|не\s+могу\s+(проанализировать|оценить)|unsupported|not\s+supported)", msg, re.IGNORECASE)
            if m:
                return msg.strip()[:500]
            return None

        for attempt in range(max_retries):
            logger.info(f"Вызов {agent.name}, попытка {attempt + 1}/{max_retries}")
            temp_user_proxy = self._create_fresh_user_proxy()
            last_message = ""
            try:
                if attempt > 0:
                    time.sleep(1)
                chat_result = temp_user_proxy.initiate_chat(
                    recipient=agent, message=prompt, max_turns=1, clear_history=True, silent=False,
                )
                if hasattr(chat_result, "chat_history") and chat_result.chat_history:
                    for msg in reversed(chat_result.chat_history):
                        content = (msg.get("content") or "").strip()
                        sender = msg.get("name", msg.get("role", ""))
                        if sender != "Оркестратор" and content:
                            last_message = content
                            break
            except Exception as e:
                logger.warning(f"Ошибка в чате с {agent.name}: {e}")
                time.sleep(2)
                try:
                    response = agent.generate_reply([{"role": "user", "content": prompt}])
                    last_message = response if response else ""
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {agent.name}: {fallback_error}")
                    last_message = ""

            # токены/лог
            self.token_tracker.track_agent_call(agent_name=agent.name, input_text=prompt, output_text=last_message)
            self.logger._write_raw(f"\n=== OUTPUT <- {agent.name} ===\n{last_message}\n")

            # 1) если явное "не могу" — сразу структурный fallback
            fb_reason = _need_fallback(last_message)
            if fb_reason:
                logger.info(f"{agent.name}: unsupported -> fallback")
                return self._fallback_payload(expected_kind, filename, fb_reason)

            # 2) попытка вытащить JSON
            if last_message:
                json_data = self._extract_json(last_message)
                if json_data:
                    return json_data
                logger.warning(f"No valid JSON from {agent.name}")

            # 3) ретрай с ужесточением
            if attempt < max_retries - 1:
                prompt = f"ВЕРНИТЕ ТОЛЬКО JSON!\n{prompt}"
                time.sleep(2)

        # 4) окончательный структурный fallback
        logger.error(f"{agent.name}: returning fallback after {max_retries} attempts")
        return self._fallback_payload(expected_kind, filename, "no valid JSON")

        
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

    def _to_autoreview(
        self,
        *,
        filename: str,
        arch: Optional[dict],
        quality: Optional[dict],
        tester: Optional[dict],
        archive_name: Optional[str] = None,
        root_dir: Optional[str] = None,
    ) -> dict:
        """Собирает целевой JSON-формат 'autoreview' из ответов агентов."""
        positives = (arch or {}).get("positives") or []
        issues_arch = (arch or {}).get("issues") or []
        issues_qual = (quality or {}).get("issues") or []
        issues = [*issues_arch, *issues_qual]

        # Счётчики: считаем critical как major (как в твоём примере)
        major = 0
        minor = 0
        for it in issues:
            sev = (it.get("severity") or "").lower()
            if sev in ("critical", "major"):
                major += 1
            else:
                minor += 1

        overall_parts = []
        if arch and arch.get("overall"):
            overall_parts.append(str(arch["overall"]).strip())
        if quality and quality.get("overall"):
            overall_parts.append(str(quality["overall"]).strip())
        overall = " | ".join(p for p in overall_parts if p)

        return {
            "agent": "autoreview",
            "role": "reviewer",
            "name": "AutoReview",
            "archive": archive_name,               # нет имени — оставь None или подставь своё
            "root": root_dir,                      # можно проставить имя репы/корня
            "summary": {
                "issue_counts": {"major": major, "minor": minor},
                "highlights": (tester or {}).get("summary", {}).get("highlights") or []
            },
            "overall": overall,
            "positives": positives,
            "issues": issues
        }


    def review_code(
            self,
            code: str,
            filename: str = "student_code.py",
            run_tests: bool = True,
            repo_dir: Optional[str] = None,
        ) -> ReviewResults:
        """Основной метод code review с улучшенной изоляцией агентов."""
        logger.info("Начало code review")
        self.logger.log_phase_start("Code Review", 1)
        
        # Save code
        self._save_code(code, filename, repo_dir)
        
        # Initialize results
        results = ReviewResults(filename=filename)
        
        # Base prompt for all agents
        base_prompt = f"""
        Проанализируйте следующий код и верните результат в требуемом JSON формате.
        
        Файл: {filename}
        
        КОД:
        ```
        {code}
        ```
        
        ВЕРНИТЕ ТОЛЬКО JSON В ВАШЕМ ФОРМАТЕ!
        """
        
        # 1. Architecture review
        logger.info("=" * 50)
        logger.info("Запуск архитектурного анализа")
        logger.info("=" * 50)
        
        arch_json = self._invoke_agent(self.architecture_reviewer, base_prompt, expected_kind="architecture", filename=filename)
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
        
        quality_json = self._invoke_agent(self.quality_reviewer, base_prompt, expected_kind="quality", filename=filename)
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
        
        test_json = self._invoke_agent(self.tester_agent, base_prompt, expected_kind="tester", filename=filename)
        if test_json:
            try:
                results.testing_results = TesterResult(**test_json)
                self.logger.log_agent_action("Тестировщик", "Анализ завершен", "Успешно")

                if run_tests and self.config.ENABLE_TEST_EXECUTION:
                    raw_code = getattr(results.testing_results, "test_code", None)
                    lang_hint = None  # агент может положить это в test_json.get("runner", {}).get("language")
                    # для Python санитайзим, для остальных — как есть
                    safe_code = (self._sanitize_test_code(raw_code, filename)
                                if raw_code and (lang_hint == "python" or filename.endswith(".py"))
                                else (raw_code or ""))
                    test_exec_results = self._run_tests(
                        test_result_json=test_json,
                        test_code=safe_code,
                        main_filename=filename,
                        repo_dir=repo_dir
                    )
                    results.test_execution = test_exec_results

                # убираем тестовый код из итогового JSON
                results.testing_results.test_code = None
                    
            except ValidationError as e:
                logger.error(f"Ошибка валидации testing review: {e}")
                self.logger.log_error("Тестировщик", str(e))
        
        # End session
        self.logger.log_session_end()
        self.token_tracker.log_session_summary()
        
        root_dir = None
        
        if repo_dir:
            try:
                root_dir = os.path.basename(os.path.abspath(repo_dir))
            except Exception:
                root_dir = None

        autoreview = self._to_autoreview(
            filename=filename,
            arch=arch_json or {},
            quality=quality_json or {},
            tester=test_json or {},
            archive_name=None,      # сюда можешь подставить имя zip, если знаешь
            root_dir=root_dir,
        )

        # Завершаем сессию логов/токенов как раньше
        self.logger.log_session_end()
        self.token_tracker.log_session_summary()

        # Возвращаем ПЛОСКИЙ dict вместо Pydantic
        return autoreview
        
    def _fallback_payload(self, kind: str, filename: str, reason: str) -> dict:
        reason = (reason or "Unsupported or unrecognized content").strip()
        if kind == "architecture":
            return {
                "agent": "АрхитекторРевьюер",
                "role": "reviewer",
                "name": "Архитектор-аналитик",
                "overall": f"Невозможно проанализировать файл: {reason}",
                "positives": [],
                "issues": []
            }
        if kind == "quality":
            return {
                "agent": "КачествоРевьюер",
                "role": "reviewer",
                "name": "Эксперт по качеству",
                "overall": f"Невозможно оценить качество файла: {reason}",
                "issues": []
            }
        if kind == "tester":
            return {
                "agent": "tester",
                "role": "tester",
                "archive": [],
                "root": None,
                "summary": {
                    "issue_counts": {"major": 0, "minor": 0},
                    "highlights": [
                        f"Файл {filename} не поддержан для автотестов",
                        f"Причина: {reason}",
                        "Тесты помечены как SKIPPED"
                    ]
                },
                "issues": [],
                "test_code": ""
            }
        # дефолт — безопасная заглушка
        return {"agent": kind, "role": "reviewer", "issues": []}


    def _save_code(self, code: str, filename: str, repo_dir: Optional[str] = None) -> str:
        base_dir = repo_dir or self.config.WORKSPACE_DIR
        filepath = os.path.join(base_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        logger.info(f"Код сохранен: {filepath}")
        return filepath
    def _run_tests(
        self,
        test_result_json: dict,
        test_code: str,
        main_filename: str,
        repo_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Универсальный запуск тестов.
        - Записывает archive (если есть).
        - Определяет стек/раннер по archive/имёнам/содержимому.
        - Если агент дал явную команду — используем её.
        - Если запуск не возможен — помечаем skipped.
        """
        base_dir = repo_dir or self.config.WORKSPACE_DIR
        os.makedirs(base_dir, exist_ok=True)

        # 1) Записать archive
        created_files = []
        archive = test_result_json.get("archive") or []
        for item in archive:
            try:
                rel_path = os.path.normpath(item.get("path", "")).lstrip(os.sep)
                if not rel_path or ".." in rel_path.split(os.sep):
                    continue
                dst = os.path.join(base_dir, rel_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(item.get("content", ""))
                created_files.append(dst)
            except Exception as e:
                logger.warning(f"Не удалось записать архивный файл {item.get('path')}: {e}")

        # 2) Определить язык/раннер
        def _has(*names: str) -> bool:
            return any(os.path.exists(os.path.join(base_dir, n)) for n in names)

        def _any_ext(patterns) -> bool:
            for root, _, files in os.walk(base_dir):
                for fn in files:
                    if any(fn.endswith(ext) for ext in patterns):
                        return True
            return False

        # если агент прислал runner.command — используем его
        runner_cfg = (test_result_json.get("runner") or {}) if isinstance(test_result_json, dict) else {}
        cmd = (runner_cfg.get("command") or "").strip()
        language_hint = (runner_cfg.get("language") or "").strip().lower()

        # 3) Сохранить основной тестовый файл (если есть)
        test_path = None
        if test_code:
            # Выбор пути по подсказке/детекции
            if language_hint == "python" or main_filename.endswith(".py"):
                tests_dir = os.path.join(base_dir, "tests")
                os.makedirs(tests_dir, exist_ok=True)
                test_filename = f"test_{os.path.basename(main_filename)}"
                test_path = os.path.join(tests_dir, test_filename)
            elif language_hint in ("javascript", "typescript") or _any_ext((".js", ".mjs", ".cjs", ".ts", ".tsx")):
                tests_dir = os.path.join(base_dir, "tests")
                os.makedirs(tests_dir, exist_ok=True)
                ext = ".test.ts" if _any_ext((".ts", ".tsx")) else ".test.js"
                test_path = os.path.join(tests_dir, f"main{ext}")
            elif language_hint == "go" or _any_ext((".go",)):
                # в Go имя файла должно заканчиваться на _test.go
                pkg_dir = base_dir
                test_path = os.path.join(pkg_dir, "autogen_test.go")
            elif language_hint in ("java", "kotlin") or _has("pom.xml", "build.gradle", "build.gradle.kts"):
                test_root = os.path.join(base_dir, "src", "test", "java")
                os.makedirs(test_root, exist_ok=True)
                test_path = os.path.join(test_root, "AutogenTests.java")
            elif language_hint == "rust" or _has("Cargo.toml"):
                tests_dir = os.path.join(base_dir, "tests")
                os.makedirs(tests_dir, exist_ok=True)
                test_path = os.path.join(tests_dir, "autogen_tests.rs")
            elif language_hint in ("c#", "dotnet") or _any_ext((".csproj",)):
                test_root = os.path.join(base_dir, "Tests")
                os.makedirs(test_root, exist_ok=True)
                test_path = os.path.join(test_root, "AutogenTests.cs")
            else:
                # дефолт — pytest
                tests_dir = os.path.join(base_dir, "tests")
                os.makedirs(tests_dir, exist_ok=True)
                test_filename = f"test_{os.path.basename(main_filename)}"
                test_path = os.path.join(tests_dir, test_filename)

            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_code)
            created_files.append(test_path)
            logger.info(f"Тесты сохранены: {test_path}")

        # 4) Если команда не задана агентом — подбираем
        if not cmd:
            if language_hint == "python" or (test_path and test_path.endswith(".py")):
                cmd = f"python -m pytest {test_path if test_path else 'tests'} -q -q --maxfail=1 --disable-warnings"
            elif language_hint in ("javascript", "typescript") or _has("package.json"):
                # предпочитаем jest, иначе node --test (Node>=18)
                if _has("node_modules/.bin/jest") or '"jest"' in open(os.path.join(base_dir, "package.json"), "r", encoding="utf-8").read() if _has("package.json") else False:
                    cmd = "npx jest --runInBand"
                else:
                    # node встроенный тест-раннер
                    target = test_path or "tests"
                    cmd = f"node --test {target}"
            elif language_hint == "go" or _any_ext((".go",)):
                cmd = "go test ./..."
            elif language_hint in ("java", "kotlin") or _has("pom.xml"):
                cmd = "mvn -q -e -DskipITs test"
            elif _has("build.gradle", "build.gradle.kts"):
                cmd = "gradle test || ./gradlew test"
            elif language_hint == "rust" or _has("Cargo.toml"):
                cmd = "cargo test"
            elif language_hint in ("c#", "dotnet") or _any_ext((".csproj",)):
                cmd = "dotnet test --nologo"
            else:
                # fallback — pytest
                target = test_path if (test_path and test_path.endswith(".py")) else "tests"
                cmd = f"python -m pytest {target} -q -q --maxfail=1 --disable-warnings"

        # 5) Запустить
        try:
            exit_code, output = self.user_proxy.execute_code_blocks([("sh", cmd)], work_dir=base_dir)
            # Успех: код 0 → прошли, >0 → упали
            success = (exit_code == 0)
            status = "PASSED" if success else "FAILED"
            return {
                "success": success,
                "status": status,
                "exit_code": exit_code,
                "output": output,
                "command": cmd,
                "test_file": os.path.relpath(test_path, base_dir) if test_path else None,
            }
        except Exception as e:
            # Невозможно запустить раннер → считаем SKIPPED (как просили)
            reason = f"runner_unavailable: {e.__class__.__name__}: {e}"
            logger.warning(f"Тесты пропущены: {reason}")
            return {
                "success": True,          # не валим пайплайн
                "status": "SKIPPED",
                "skipped": True,
                "reason": reason,
                "command": cmd or None,
                "exit_code": 0,
                "output": "",
                "test_file": os.path.relpath(test_path, base_dir) if test_path else None,
            }


    
    def _save_results(self, results: ReviewResults):
        """Сохранение результатов."""
        output_file = os.path.join(self.config.WORKSPACE_DIR, "multiagent.json")
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

# вверху файла после импорта Config и CodeReviewManager
from typing import Optional

_REVIEWER_SINGLETON: Optional["CodeReviewManager"] = None

def init_reviewer(config: Optional["Config"] = None, **overrides) -> "CodeReviewManager":
    """
    Инициализирует CodeReviewManager.
    Параметры из overrides (например, WORKSPACE_DIR, ENABLE_TEST_EXECUTION, USE_DOCKER)
    применяются к Config, если такие поля существуют.
    """
    cfg = config or Config()
    for key, value in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return CodeReviewManager(cfg)

def get_reviewer_singleton(config: Optional["Config"] = None, **overrides) -> "CodeReviewManager":
    """Ленивая выдача одного инстанса на процесс (удобно для Flask)."""
    global _REVIEWER_SINGLETON
    if _REVIEWER_SINGLETON is None:
        _REVIEWER_SINGLETON = init_reviewer(config, **overrides)
    return _REVIEWER_SINGLETON


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
