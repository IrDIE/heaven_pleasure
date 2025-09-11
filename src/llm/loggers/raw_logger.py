"""Unified logger that combines raw AutoGen output with formatted workflow logging."""

import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional


class UnifiedLogger:
    """Объединенный логгер для AutoGen с поддержкой raw и formatted логирования."""
    
    def __init__(self, workspace_dir: str, enable_raw: bool = True):
        self.workspace_dir = workspace_dir
        self.enable_raw = enable_raw
        self.session_start_time = datetime.now()
        
        # Основной workflow лог
        self.workflow_log = os.path.join(workspace_dir, "agents_workflow.log")
        
        # Raw AutoGen лог (опционально)
        if enable_raw:
            self.raw_log = os.path.join(workspace_dir, "autogen_raw_output.log")
            self._setup_raw_logger()
        
        self._initialize_logs()
    
    def _initialize_logs(self):
        """Инициализация лог-файлов."""
        header = f"""
================================================================================
AUTOGEN MULTI-AGENT SYSTEM LOG
Started: {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}
Workspace: {self.workspace_dir}
================================================================================

"""
        # Workflow лог
        with open(self.workflow_log, "w", encoding="utf-8") as f:
            f.write(header)
        
        # Raw лог
        if self.enable_raw:
            with open(self.raw_log, "w", encoding="utf-8") as f:
                f.write(header)
    
    def _setup_raw_logger(self):
        """Настройка raw логгера для AutoGen."""
        self.raw_logger = logging.getLogger("autogen_raw")
        self.raw_logger.setLevel(logging.DEBUG)
        self.raw_logger.handlers.clear()
        self.raw_logger.propagate = False
        
        # File handler для raw логов
        file_handler = logging.FileHandler(self.raw_log, mode='a', encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
        self.raw_logger.addHandler(file_handler)
    
    def _write_workflow(self, message: str):
        """Запись в workflow лог."""
        with open(self.workflow_log, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    
    def _write_raw(self, message: str):
        """Запись в raw лог."""
        if self.enable_raw:
            self.raw_logger.info(message)
    
    # === Методы из FancyLogger (workflow logging) ===
    
    def log_agent_action(self, agent_name: str, action: str, details: str = ""):
        """Логирует действие агента."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] {agent_name}: {action}"
        if details:
            entry += f" | {details[:100]}"
        
        self._write_workflow(entry)
        self._write_raw(f"AGENT ACTION: {agent_name} - {action}")
        logging.getLogger(__name__).info(entry)
    
    def log_phase_start(self, phase_name: str, phase_number: int):
        """Логирует начало фазы."""
        entry = f"\n{'='*50}\nPHASE {phase_number}: {phase_name}\n{'='*50}"
        self._write_workflow(entry)
        self._write_raw(f"=== PHASE {phase_number}: {phase_name} ===")
        logging.getLogger(__name__).info(f"Phase {phase_number}: {phase_name}")
    
    def log_error(self, agent_name: str, error_msg: str):
        """Логирует ошибку."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] ERROR - {agent_name}: {error_msg[:200]}"
        
        self._write_workflow(entry)
        self._write_raw(f"ERROR [{agent_name}]: {error_msg}")
        logging.getLogger(__name__).error(f"{agent_name}: {error_msg[:100]}")
    
    def log_success(self, message: str):
        """Логирует успех."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] SUCCESS: {message}"
        
        self._write_workflow(entry)
        self._write_raw(f"SUCCESS: {message}")
        logging.getLogger(__name__).info(f"Success: {message}")
    
    def log_test_results(self, iteration: int, exit_code: int, test_logs: str, dependencies: List[str] = None):
        """Логирует результаты тестов."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        status = "PASSED" if exit_code == 0 else "FAILED"
        
        # Анализ логов
        stats = self._analyze_test_logs(test_logs)
        
        entry = f"[{timestamp}] Test iteration {iteration}: {status} (exit: {exit_code})"
        if stats['passed'] or stats['failed']:
            entry += f" | Passed: {stats['passed']}, Failed: {stats['failed']}"
        
        self._write_workflow(entry)
        
        # Логируем ошибки
        if stats['errors']:
            for error in stats['errors'][:2]:
                self._write_workflow(f"  - {error[:100]}")
        
        # Raw лог с полными деталями
        if self.enable_raw and test_logs:
            self._write_raw(f"\n--- TEST OUTPUT (iteration {iteration}) ---")
            self._write_raw(test_logs[:1000])  # Первые 1000 символов
        
        logging.getLogger(__name__).info(f"Tests {iteration}: {status}")
    
    def log_improvement_cycle(self, iteration: int, max_iterations: int, action: str, details: str = ""):
        """Логирует цикл улучшений."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        entry = f"[{timestamp}] Improvement {iteration}/{max_iterations}: {action}"
        if details:
            entry += f" | {details[:100]}"
        
        self._write_workflow(entry)
        self._write_raw(f"IMPROVEMENT CYCLE {iteration}/{max_iterations}: {action}")
    
    def log_docker_setup(self, dependencies: List[str], docker_enabled: bool):
        """Логирует настройку Docker."""
        mode = "Docker" if docker_enabled else "Local"
        entry = f"Test environment: {mode} | Dependencies: {len(dependencies)}"
        
        self._write_workflow(entry)
        self._write_raw(f"DOCKER SETUP: {mode}, {dependencies}")
    
    # === Методы из AutoGenRawLogger (raw logging) ===
    
    def log_chat_initiation(self, initiator: str, recipient: str, message: str):
        """Логирует начало чата."""
        if self.enable_raw:
            self._write_raw(f"\n{'='*60}")
            self._write_raw(f"CHAT: {initiator} -> {recipient}")
            self._write_raw(f"Message: {message[:500]}")
            self._write_raw('='*60)
        
        self._write_workflow(f"Chat started: {initiator} -> {recipient}")
    
    def log_chat_history(self, chat_history: List[Dict], context: str = ""):
        """Логирует историю чата."""
        if not chat_history:
            return
        
        self._write_workflow(f"Chat history ({context}): {len(chat_history)} messages")
        
        if self.enable_raw:
            self._write_raw(f"\n--- CHAT HISTORY {context} ---")
            for i, msg in enumerate(chat_history):
                role = msg.get('role', msg.get('name', 'unknown'))
                content = msg.get('content', '')[:500]  # Ограничиваем длину
                self._write_raw(f"[{i+1}] {role}: {content}")
            self._write_raw('-'*60)
    
    def log_tool_call(self, agent_name: str, tool_name: str, tool_input: str, tool_output: str):
        """Логирует вызов инструмента."""
        self._write_workflow(f"Tool call: {agent_name} -> {tool_name}")
        
        if self.enable_raw:
            self._write_raw(f"\nTOOL CALL: {tool_name}")
            self._write_raw(f"Agent: {agent_name}")
            self._write_raw(f"Input: {tool_input[:200]}")
            self._write_raw(f"Output: {tool_output[:200]}")
    
    def log_session_end(self):
        """Завершение сессии."""
        duration = datetime.now() - self.session_start_time
        footer = f"\n{'='*50}\nSession ended. Duration: {str(duration).split('.')[0]}\n{'='*50}"
        
        self._write_workflow(footer)
        if self.enable_raw:
            self._write_raw(footer)
    
    # === Вспомогательные методы ===
    
    def _analyze_test_logs(self, test_logs: str) -> Dict[str, Any]:
        """Анализ логов тестов."""
        stats = {'passed': 0, 'failed': 0, 'errors': []}
        
        if not test_logs:
            return stats
        
        # Ищем статистику pytest
        failed_match = re.search(r'(\d+)\s+failed', test_logs)
        passed_match = re.search(r'(\d+)\s+passed', test_logs)
        
        if failed_match:
            stats['failed'] = int(failed_match.group(1))
        if passed_match:
            stats['passed'] = int(passed_match.group(1))
        
        # Извлекаем ошибки
        for line in test_logs.split('\n'):
            if any(x in line for x in ['FAILED', 'AssertionError', 'Error:']):
                stats['errors'].append(line.strip())
                if len(stats['errors']) >= 3:
                    break
        
        return stats
    
    # === Обратная совместимость ===
    
    # Эти методы для совместимости с кодом, использующим AutoGenRawLogger
    def log_agent_response(self, agent_name: str, response: str):
        """Для совместимости с AutoGenRawLogger."""
        self.log_agent_action(agent_name, "Response", response[:100])
    
    @property
    def raw_log_file(self):
        """Для совместимости - возвращает путь к raw логу."""
        return self.raw_log if self.enable_raw else self.workflow_log


# Классы-обертки для обратной совместимости
class FancyLogger(UnifiedLogger):
    """Алиас для совместимости с существующим кодом."""
    def __init__(self, workspace_dir: str):
        super().__init__(workspace_dir, enable_raw=False)


class AutoGenRawLogger(UnifiedLogger):
    """Алиас для совместимости с существующим кодом."""
    def __init__(self, workspace_dir: str):
        super().__init__(workspace_dir, enable_raw=True)