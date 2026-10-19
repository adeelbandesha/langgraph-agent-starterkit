import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.state import AgentNode, PipelineState, Specification
from src.utils.llm import invoke_structured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a senior requirements analyst. Turn the user's feature request into a precise \
functional specification for a single, self-contained Python 3.11+ module.

- Capture what was asked for; do not invent extra features.
- Resolve ambiguity with sensible defaults and record each one under assumptions.
- Every functional requirement and acceptance criterion must be objectively testable.
- Prefer the standard library unless the request clearly needs a third-party package.
- Define the public interface concretely: exact CLI usage or function and class signatures."""


def build_analyst(llm: BaseChatModel) -> AgentNode:
    def analyst(state: PipelineState) -> PipelineState:
        logger.info("Analysing feature request")
        specification = invoke_structured(
            llm,
            Specification,
            [SystemMessage(SYSTEM_PROMPT), HumanMessage(state["prompt"])],
            agent="analyst",
        )
        logger.info(
            "Specification ready: %r with %d requirements and %d acceptance criteria",
            specification.title,
            len(specification.functional_requirements),
            len(specification.acceptance_criteria),
        )
        logger.debug("Specification:\n%s", specification.to_markdown())
        return {"specification": specification, "active_node": "analyst"}

    return analyst
