import os
import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --- 1. Architect Agent ---
class ArchitectureIssue(BaseModel):
    issue: str
    proposed_structure: str
    refactoring_steps: List[str]

class ArchitectOutput(BaseModel):
    architecture_issues: List[ArchitectureIssue] = Field(description="Architecture issues found")

# --- 2. Development Agent ---
class CodeSnippet(BaseModel):
    code_snippet: str
    explanation: str
    integration_steps: List[str]

class DevelopmentOutput(BaseModel):
    snippets: List[CodeSnippet] = Field(description="Production-ready Python code snippets")

# --- 3. Security Agent ---
class SecurityVulnerability(BaseModel):
    vulnerability: str
    location: str
    risk_level: str = Field(description="High/Medium/Low")
    fix: str = Field(description="Exact technical solution")

class SecurityOutput(BaseModel):
    vulnerabilities: List[SecurityVulnerability] = Field(description="Detected OWASP or other vulnerabilities")

# --- 4. QA Agent ---
class TestCase(BaseModel):
    test_case: str
    expected_result: str
    actual_risk: str
    fix_suggestion: str

class QAOutput(BaseModel):
    test_cases: List[TestCase] = Field(description="Test cases validating functionality and edge cases")

# --- 5. Performance Agent ---
class Bottleneck(BaseModel):
    bottleneck: str
    impact: str
    optimization_solution: str

class PerformanceOutput(BaseModel):
    bottlenecks: List[Bottleneck] = Field(description="Performance bottlenecks and optimizations")

# --- Master Coordinator ---
class MasterCoordinatorOutput(BaseModel):
    final_unified_response: str = Field(description="Final unified response")
    summary_of_contributions: str = Field(description="Summary of each agent's contribution")
    final_decision: str = Field(description="Final decision")

class MultiAgentSystem:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    def _call_agent(self, system_prompt: str, user_prompt: str, response_format: type[BaseModel]) -> BaseModel:
        try:
            response = client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=response_format,
            )
            return response.choices[0].message.parsed
        except Exception as e:
            logger.error(f"Error calling agent: {e}")
            raise

    def run_architect_agent(self, request: str) -> ArchitectOutput:
        system = (
            "Name: Architect Agent\n"
            "Role: System architecture and structure design\n"
            "Instructions:\n"
            "- Analyze backend structure and enforce scalable architecture\n"
            "- Refactor monolithic patterns into modular systems (Flask Blueprints)\n"
            "- Prevent tight coupling\n"
            "- Design clean separation of concerns"
        )
        return self._call_agent(system, request, ArchitectOutput)

    def run_development_agent(self, request: str, architect_output: ArchitectOutput) -> DevelopmentOutput:
        system = (
            "Name: Development Agent\n"
            "Role: Code generation and refactoring\n"
            "Instructions:\n"
            "- Write production-ready Python code\n"
            "- Follow best practices (clean code, modular design)\n"
            "- Optimize performance\n"
            "- Never write insecure code"
        )
        user_prompt = f"Request: {request}\n\nArchitect Plan:\n{architect_output.model_dump_json()}"
        return self._call_agent(system, user_prompt, DevelopmentOutput)

    def run_security_agent(self, request: str, dev_output: DevelopmentOutput) -> SecurityOutput:
        system = (
            "Name: Security Agent\n"
            "Role: Security auditing and vulnerability detection\n"
            "Instructions:\n"
            "- Detect OWASP vulnerabilities\n"
            "- Analyze authentication, authorization, webhooks\n"
            "- Check token storage and encryption\n"
            "- Identify payment and API risks"
        )
        user_prompt = f"Request: {request}\n\nCode to Audit:\n{dev_output.model_dump_json()}"
        return self._call_agent(system, user_prompt, SecurityOutput)

    def run_qa_agent(self, request: str, dev_output: DevelopmentOutput, sec_output: SecurityOutput) -> QAOutput:
        system = (
            "Name: QA Agent\n"
            "Role: Testing and validation\n"
            "Instructions:\n"
            "- Simulate real user scenarios\n"
            "- Detect bugs and edge cases\n"
            "- Validate consistency between modules"
        )
        user_prompt = f"Request: {request}\n\nCode:\n{dev_output.model_dump_json()}\n\nSec Audit:\n{sec_output.model_dump_json()}"
        return self._call_agent(system, user_prompt, QAOutput)

    def run_performance_agent(self, request: str, dev_output: DevelopmentOutput) -> PerformanceOutput:
        system = (
            "Name: Performance Agent\n"
            "Role: Optimization and scaling\n"
            "Instructions:\n"
            "- Detect bottlenecks\n"
            "- Optimize database queries\n"
            "- Improve async processing (Celery)\n"
            "- Reduce API/token cost"
        )
        user_prompt = f"Request: {request}\n\nCode:\n{dev_output.model_dump_json()}"
        return self._call_agent(system, user_prompt, PerformanceOutput)

    def run_master_coordinator(
        self, 
        request: str, 
        arch: ArchitectOutput, 
        dev: DevelopmentOutput, 
        sec: SecurityOutput, 
        qa: QAOutput, 
        perf: PerformanceOutput
    ) -> MasterCoordinatorOutput:
        system = (
            "Name: Master Coordinator\n"
            "Role: Orchestrates all agents\n"
            "Instructions:\n"
            "- Break down user requests into tasks\n"
            "- Assign tasks to relevant agents\n"
            "- Merge outputs into one final result\n"
            "- Resolve conflicts between agents\n"
            "- Ensure consistency and correctness\n"
            "Currently, agents have completed their tasks. Your job is merging them"
        )
        user_prompt = (
            f"Original Request: {request}\n\n"
            f"Architect: {arch.model_dump_json()}\n"
            f"Dev: {dev.model_dump_json()}\n"
            f"Sec: {sec.model_dump_json()}\n"
            f"QA: {qa.model_dump_json()}\n"
            f"Perf: {perf.model_dump_json()}"
        )
        return self._call_agent(system, user_prompt, MasterCoordinatorOutput)

    def process_request(self, request: str) -> MasterCoordinatorOutput:
        """
        Executes the full Multi-Agent Workflow:
        1. Architect Agent
        2. Development Agent
        3. Security Agent
        4. QA Agent
        5. Performance Agent
        6. Master Coordinator
        """
        logger.info("Starting Multi-Agent Workflow")
        
        logger.info("1/6 Architect Agent...")
        arch_out = self.run_architect_agent(request)
        
        logger.info("2/6 Development Agent...")
        dev_out = self.run_development_agent(request, arch_out)
        
        logger.info("3/6 Security Agent...")
        sec_out = self.run_security_agent(request, dev_out)
        
        logger.info("4/6 QA Agent...")
        qa_out = self.run_qa_agent(request, dev_out, sec_out)
        
        logger.info("5/6 Performance Agent...")
        perf_out = self.run_performance_agent(request, dev_out)
        
        logger.info("6/6 Master Coordinator merging...")
        final_out = self.run_master_coordinator(request, arch_out, dev_out, sec_out, qa_out, perf_out)
        
        logger.info("Workflow Complete")
        return final_out
