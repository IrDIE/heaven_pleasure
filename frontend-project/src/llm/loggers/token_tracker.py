"""Simple token usage tracking for LLM calls."""

import os
import logging
from datetime import datetime
from typing import Dict, Optional


class TokenTracker:
    """Простая система отслеживания токенов и стоимости."""
    
    def __init__(self, workspace_dir: str, input_cost: float = 0.0, output_cost: float = 0.0):
        self.workspace_dir = workspace_dir
        self.input_cost = input_cost  # Стоимость за входящий токен
        self.output_cost = output_cost  # Стоимость за исходящий токен
        self.session_start_time = datetime.now()
        
        # Статистика по агентам
        self.agent_stats = {}
        
        # Лог-файл
        self.log_file = os.path.join(workspace_dir, "tokens_usage.log")
        self._initialize_log()
    
    def _initialize_log(self):
        """Инициализация лог-файла."""
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"Token Usage Log\n")
            f.write(f"Started: {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Input cost: {self.input_cost:.6f} | Output cost: {self.output_cost:.6f}\n")
            f.write("="*60 + "\n\n")
    
    def estimate_tokens(self, text: str) -> int:
        """Оценка количества токенов в тексте."""
        if not text:
            return 0
        
        # Простая оценка: ~4 символа = 1 токен
        # Для русского текста может быть ~3.5 символа = 1 токен
        return max(len(text) // 4, len(text.split()))
    
    def track_agent_call(self, 
                        agent_name: str, 
                        input_text: str = "", 
                        output_text: str = "",
                        input_tokens: Optional[int] = None,
                        output_tokens: Optional[int] = None):
        """Отслеживание вызова агента."""
        
        # Оцениваем токены если не переданы
        input_tokens = input_tokens or self.estimate_tokens(input_text)
        output_tokens = output_tokens or self.estimate_tokens(output_text)
        
        # Инициализируем статистику агента если нужно
        if agent_name not in self.agent_stats:
            self.agent_stats[agent_name] = {
                "input": 0,
                "output": 0,
                "calls": 0,
                "cost": 0.0
            }
        
        # Обновляем статистику
        stats = self.agent_stats[agent_name]
        stats["input"] += input_tokens
        stats["output"] += output_tokens
        stats["calls"] += 1
        
        # Рассчитываем стоимость
        call_cost = (input_tokens * self.input_cost + 
                    output_tokens * self.output_cost)
        stats["cost"] += call_cost
        
        # Логируем
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = (f"[{timestamp}] {agent_name}: "
                    f"in={input_tokens}, out={output_tokens}, "
                    f"cost={call_cost:.4f}")
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
        
        logging.getLogger(__name__).debug(log_entry)
    
    def get_agent_summary(self, agent_name: str) -> Dict:
        """Получить статистику по агенту."""
        if agent_name not in self.agent_stats:
            return {"input": 0, "output": 0, "calls": 0, "cost": 0.0}
        
        return self.agent_stats[agent_name].copy()
    
    def get_total_summary(self) -> Dict:
        """Получить общую статистику."""
        total = {
            "total_input": 0,
            "total_output": 0,
            "total_calls": 0,
            "total_cost": 0.0
        }
        
        for stats in self.agent_stats.values():
            total["total_input"] += stats["input"]
            total["total_output"] += stats["output"]
            total["total_calls"] += stats["calls"]
            total["total_cost"] += stats["cost"]
        
        total["total_tokens"] = total["total_input"] + total["total_output"]
        
        return total
    
    def log_session_summary(self) -> Dict:
        """Записать итоговую сводку."""
        duration = datetime.now() - self.session_start_time
        summary = self.get_total_summary()
        
        # Формируем отчет
        report = [
            "\n" + "="*60,
            "SESSION SUMMARY",
            "="*60,
            f"Duration: {str(duration).split('.')[0]}",
            f"Total calls: {summary['total_calls']}",
            f"Total tokens: {summary['total_tokens']} "
            f"(in: {summary['total_input']}, out: {summary['total_output']})",
            f"Total cost: {summary['total_cost']:.4f}",
            "",
            "By agent:"
        ]
        
        # Детализация по агентам
        for name, stats in sorted(self.agent_stats.items()):
            if stats["calls"] > 0:
                report.append(
                    f"  {name}: {stats['calls']} calls, "
                    f"{stats['input']+stats['output']} tokens, "
                    f"cost: {stats['cost']:.4f}"
                )
        
        report.append("="*60)
        
        # Записываем в файл
        report_text = "\n".join(report)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(report_text + "\n")
        
        # Логируем основную информацию
        logging.getLogger(__name__).info(
            f"Token usage: {summary['total_tokens']} tokens, "
            f"cost: {summary['total_cost']:.4f}"
        )
        
        return summary
    
    def reset(self):
        """Сброс статистики."""
        self.agent_stats.clear()
        self.session_start_time = datetime.now()
        self._initialize_log()