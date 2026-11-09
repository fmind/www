"""Closed, display-ordered article tag vocabulary."""

from www.models import Tag

TAGS = (
    Tag("Agent", "AI agents, agent platforms, and agent protocols."),
    Tag("Coding", "Coding agents, agentic development workflows, and developer tooling."),
    Tag("LLM", "Language models, prompting, multimodality, and model serving."),
    Tag("RAG", "Retrieval and context strategies for grounding model answers."),
    Tag("MLOps", "Pipelines, packaging, monitoring, and the practice of shipping ML."),
    Tag("Cloud", "Google Cloud, Vertex AI, Kubernetes, and platform infrastructure."),
    Tag("Python", "Python tooling, packaging, and code design."),
    Tag("Project", "Open-source tools and products released to the community."),
    Tag("Demo", "Hands-on builds, experiments, and end-to-end walkthroughs."),
    Tag("Guide", "Courses, tutorials, and principles for practitioners."),
)
_TAG_ORDER = {tag.name: index for index, tag in enumerate(TAGS)}


def tag_names() -> tuple[str, ...]:
    return tuple(tag.name for tag in TAGS)


def tag_order(name: str) -> int:
    return _TAG_ORDER.get(name, len(TAGS))


def is_tag(name: str) -> bool:
    return name in _TAG_ORDER


def sort_tags(tags: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    return tuple(sorted(tags, key=lambda name: (tag_order(name), name)))
