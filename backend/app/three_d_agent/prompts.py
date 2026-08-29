"""Deterministic question and image-prompt policy for 3D-printable creations."""

from __future__ import annotations

from .contracts import ClarificationQuestion, CreativeBrief


_QUESTION_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "subject",
        "这件作品要表现哪个单一主体？",
        ("动物", "人物", "动漫角色", "机械模型", "日常物品", "其他"),
    ),
    (
        "style",
        "希望主体采用哪种视觉风格？",
        ("Q版", "动漫", "写实", "极简", "低多边形", "中国风", "其他"),
    ),
    (
        "product_type",
        "最终要制作成哪种 3D 打印作品？",
        ("手办", "桌面摆件", "挂件", "钥匙扣", "手机支架", "盲盒角色", "其他"),
    ),
)


def clarification_questions(brief: CreativeBrief) -> list[ClarificationQuestion]:
    """Return stable questions for each required creative decision still missing."""
    return [
        ClarificationQuestion(field=field, prompt=prompt, options=list(options))
        for field, prompt, options in _QUESTION_SPECS
        if not getattr(brief, field)
    ]


def build_print_aware_image_prompt(brief: CreativeBrief) -> str:
    """Build a constrained image prompt suitable for image-to-3D printing."""
    if not brief.is_complete:
        missing = ", ".join(brief.missing_fields)
        raise ValueError(f"Cannot build an image prompt without: {missing}")

    lines = [f"Create a {brief.style} {brief.product_type} depicting {brief.subject}."]
    if brief.details:
        lines.append(f"Additional user requirements: {brief.details}.")
    lines.extend(
        (
            "Show exactly one complete centered subject in a straight-on product view, with generous white margin on every side.",
            "Use a pure white background and a flat, deliberate palette of no more than four solid colors; no gradients, textures, transparency, or complex shading.",
            "The entire subject must be visibly inside the frame: include every extremity, ear, horn, tail, wing, accessory, attachment, and the complete base with clear surrounding margin.",
            "Never crop, clip, cut off, hide beyond the frame, or push any part of the subject against an image edge.",
            "Keep the silhouette, proportions, and stable geometry clean and suitable for a watertight 3D model.",
            "Use substantial connected forms with clear depth; avoid thin parts, floating details, fragile protrusions, and complex unsupported geometry.",
            "Do not include text, letters, numbers, logos, labels, captions, watermarks, frames, scenery, or additional objects.",
        )
    )
    return "\n".join(lines)
