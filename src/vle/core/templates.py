"""Small, strict package-resource prompt template renderer."""

from importlib import resources
import re


class TemplateContractError(ValueError):
    pass


_PLACEHOLDER = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def load_template(package: str, name: str) -> str:
    return resources.files(package).joinpath(name).read_text(encoding="utf-8")


def render_template(template: str, *, allowed: set[str], values: dict[str, object]) -> str:
    """Render inert ``{{identifier}}`` placeholders with a checked contract.

    Prompt files are deliberately data, rather than executable templates. This
    renderer does not support formatting expressions, attribute access, or
    includes, which makes prompt experiments predictable and reviewable.
    """
    template_without_placeholders = _PLACEHOLDER.sub("", template)
    if "{" in template_without_placeholders or "}" in template_without_placeholders:
        raise TemplateContractError("Template contains an invalid placeholder; use {{identifier}}")

    fields = set(_PLACEHOLDER.findall(template))
    undeclared = fields - allowed
    if undeclared:
        raise TemplateContractError(f"Template uses undeclared placeholders: {sorted(undeclared)}")
    missing = fields - values.keys()
    if missing:
        raise TemplateContractError(f"Template is missing values for: {sorted(missing)}")
    unused = values.keys() - fields
    if unused:
        raise TemplateContractError(f"Template received unused values: {sorted(unused)}")

    return _PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), template)
