from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pydantic import ConfigDict

class ArchitectureReviewResult(BaseModel):
    agent: str
    role: str
    name: str
    overall: str
    positives: List[Dict[str, Any]]
    issues: List[Dict[str, Any]]

class QualityReviewResult(BaseModel):
    agent: str
    role: str
    name: str
    overall: str
    issues: List[Dict[str, Any]]

class TestCaseResult(BaseModel):
    name: str
    status: str                  # "passed" | "failed" | "skipped" | ...
    message: Optional[str] = None

class TestExecution(BaseModel):
    language: Optional[str] = None
    success: bool
    exit_code: Optional[int] = None
    output: Optional[str] = None
    test_file: Optional[str] = None
    error: Optional[str] = None
    tests: Optional[List[TestCaseResult]] = None  # ← список кейсов из одного файла

class TesterResult(BaseModel):
    agent: str
    role: str
    archive: Optional[str] = None
    root: Optional[str] = None
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    test_code: Optional[str] = None 

class ReviewResults(BaseModel):
    model_config = ConfigDict(validate_assignment=True) 
    filename: str
    architecture_review: Optional[ArchitectureReviewResult] = None
    quality_review: Optional[QualityReviewResult] = None
    testing_results: Optional[TesterResult] = None
    test_execution: Optional[TestExecution] = None  
