"""Deterministic question and image-prompt policy for 3D-printable creations."""

from __future__ import annotations

from .contracts import CreativeBrief, PromptPackage


def response_language(message: str, brief: CreativeBrief | None = None) -> str:
    """Use the caller's written language; short follow-ups inherit the brief."""
    source = message.strip() or " ".join(
        value for value in (getattr(brief, "subject", None), getattr(brief, "style", None), getattr(brief, "product_type", None)) if value
    )
    return "zh" if any("\u4e00" <= character <= "\u9fff" for character in source) else "en"


def complete_brief(brief: CreativeBrief, language: str) -> CreativeBrief:
    """Fill every printable-prompt field without asking the caller to choose a type."""
    if language == "zh":
        subject = brief.subject_zh or brief.subject or "用户请求的三维打印对象"
        style = brief.style_zh or brief.style or "简洁产品设计风格"
        product_type = brief.product_type_zh or brief.product_type or "桌面摆件"
        details = brief.details_zh or brief.details or "自动优化为结构完整、适合熔融沉积成型打印的设计"
        return CreativeBrief(
            subject=subject,
            style=style,
            product_type=product_type,
            details=details,
            subject_zh=subject,
            style_zh=style,
            product_type_zh=product_type,
            details_zh=details,
        )
    return CreativeBrief(
        subject=brief.subject or "the requested 3D-printable object",
        style=brief.style or "clean product design",
        product_type=brief.product_type or "desk figurine",
        details=brief.details or "automatically optimized as a complete FDM-printable design",
    )


def build_prompt_package(brief: CreativeBrief, language: str) -> PromptPackage:
    """Expand every input into explicit printable Image2 instructions."""
    brief = complete_brief(brief, language)
    if language == "zh":
        subject = brief.subject_zh or brief.subject
        style = brief.style_zh or brief.style
        product_type = brief.product_type_zh or brief.product_type
        details = brief.details_zh or brief.details or "未提供其他要求"
    else:
        subject = brief.subject
        style = brief.style
        product_type = brief.product_type
        details = brief.details or "No additional requirements supplied"
    if language == "zh":
        constraints = [
            "单一完整主体，所有肢体、配件和底座必须完整入镜。",
            "正面或轻微三分之四产品视角，主体居中，四周保留明显空白。",
            "使用大块连续实体、稳定比例和清晰轮廓；适合封闭实体与熔融沉积成型打印。",
            "避免薄片、悬空碎件、脆弱尖端、细长连接和复杂无支撑结构。",
            "使用纯白不透明背景，平面且明确的少量色彩，不依赖环境或纹理细节。",
        ]
        positive = (
            f"主体：{subject}。成品类型：{product_type}。视觉风格：{style}。"
            f"用户要求：{details}。单一完整主体，清晰可辨的外轮廓，正面或轻微三分之四产品视角，"
            "居中构图，完整底座，体块连续而扎实，适合多色熔融沉积成型三维打印。"
        )
        negative = (
            "不要文字、数字、字母、标识、水印、标签、边框、场景、额外对象或人物；"
            "不要裁切、遮挡、边缘贴合、透明背景、渐变、照片级复杂纹理、强景深或强运动模糊；"
            "不要细线、悬浮零件、脆弱尖端、断开的部件、复杂无支撑悬垂或不可打印内部结构。"
        )
        image2 = "\n".join((
            "为 Image2 生成一张 1024×1024 的 3D 打印概念参考图。",
            f"正面要求：{positive}",
            "打印约束：" + " ".join(constraints),
            f"负面要求：{negative}",
            "输出仅包含该主体与纯白背景；主体必须完全可见。",
        ))
    else:
        constraints = [
            "Show one complete subject; every limb, accessory, and the base must stay inside the frame.",
            "Use a front or slight three-quarter product view, centered with generous margin on every side.",
            "Use substantial connected volumes, stable proportions, and a clear silhouette suitable for a watertight FDM model.",
            "Avoid thin sheets, floating fragments, fragile tips, long narrow joins, and complex unsupported geometry.",
            "Use an opaque pure-white background and a deliberate limited palette; do not rely on environmental or texture detail.",
        ]
        positive = (
            f"Subject: {subject}. Product type: {product_type}. Visual style: {style}. "
            f"User requirements: {details}. One complete subject with a readable silhouette, front or slight three-quarter "
            "product view, centered composition, complete base, substantial connected forms, and a multicolor FDM-printable design."
        )
        negative = (
            "No text, numbers, letters, logos, watermarks, labels, frames, scenery, extra objects, or people; "
            "no crop, occlusion, edge contact, transparent background, gradients, photorealistic complex textures, strong depth of field, or motion blur; "
            "no thin wires, floating parts, fragile points, disconnected pieces, unsupported overhangs, or unprintable internal geometry."
        )
        image2 = "\n".join((
            "Generate one 1024x1024 Image2 concept reference for a 3D-printable object.",
            f"Positive requirements: {positive}",
            "Print constraints: " + " ".join(constraints),
            f"Negative requirements: {negative}",
            "Return only the complete subject on an opaque pure-white background.",
        ))
    return PromptPackage(
        language=language,
        positive_prompt=positive,
        negative_prompt=negative,
        print_constraints=constraints,
        image2_prompt=image2,
    )


def build_print_aware_image_prompt(brief: CreativeBrief, language: str) -> str:
    return build_prompt_package(brief, language).image2_prompt


def build_display_presentations(brief: CreativeBrief, language: str) -> tuple[str, str]:
    """Return one-language display copy for an automatically completed brief."""
    brief = complete_brief(brief, language)
    values = (
        (brief.subject_zh or brief.subject, brief.style_zh or brief.style, brief.product_type_zh or brief.product_type, brief.details_zh or brief.details)
        if language == "zh"
        else (brief.subject, brief.style, brief.product_type, brief.details)
    )
    presentation = " · ".join(value for value in values if value)
    return presentation, presentation
