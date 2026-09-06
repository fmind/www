"""Closed, display-ordered article tag vocabulary."""

from www.models import Tag


def validate_tag_vocabulary(tags: tuple[Tag, ...]) -> None:
    """Reject malformed tag metadata before helpers derive lookup state."""
    seen: set[str] = set()
    for index, tag in enumerate(tags):
        if not tag.name.strip():
            raise ValueError(f"tag name must not be empty at index {index}")
        if tag.name != tag.name.strip():
            raise ValueError(f"tag name must be trimmed at index {index}: {tag.name!r}")
        if tag.name in seen:
            raise ValueError(f"duplicate tag name: {tag.name!r}")
        if not tag.description.strip():
            raise ValueError(f"tag description must not be empty for {tag.name!r}")
        if tag.description != tag.description.strip():
            raise ValueError(f"tag description must be trimmed for {tag.name!r}")
        seen.add(tag.name)


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
validate_tag_vocabulary(TAGS)
_TAG_ORDER = {tag.name: index for index, tag in enumerate(TAGS)}


def tag_names() -> tuple[str, ...]:
    return tuple(tag.name for tag in TAGS)


def tag_order(name: str) -> int:
    return _TAG_ORDER.get(name, len(TAGS))


def is_tag(name: str) -> bool:
    return name in _TAG_ORDER


def sort_tags(tags: tuple[str, ...] | list[str] | set[str]) -> tuple[str, ...]:
    return tuple(sorted(tags, key=lambda name: (tag_order(name), name)))
