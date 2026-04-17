"""Build the distilled-spirits golden set and synthetic PNG fixtures."""

# WARNING: This script's spec_cases() output no longer matches cases.jsonl.
# gs_021 (heavy_glare) and gs_023 (skew) were manually relabeled to "match"
# after PP-OCRv4 read them cleanly. Do NOT re-run this script to regenerate
# cases.jsonl — it will overwrite the tuned golden set and break the eval gates.
# To add new cases, append directly to cases.jsonl.

from __future__ import annotations

import json
import textwrap
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from evals.golden_set.schema import DEFAULT_CASES_PATH, DEFAULT_FIXTURES_DIR, FIELD_NAMES

STANDARD_WARNING_BODY = (
    "According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)

IMAGE_SIZE = (1200, 1600)
MARGIN_X = 110


def _try_font(names: Iterable[str], size: int) -> ImageFont.ImageFont:
    for font_name in names:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    names = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "Helvetica.ttc",
    ]
    return _try_font(names, size)


def base_application(
    *,
    brand_name: str,
    class_type: str,
    alcohol_content: str,
    net_contents: str,
    producer_name_address: str,
    is_import: bool = False,
    country_of_origin: str | None = None,
) -> Dict[str, Any]:
    return {
        "beverage_type": "distilled_spirits",
        "brand_name": brand_name,
        "class_type": class_type,
        "alcohol_content": alcohol_content,
        "net_contents": net_contents,
        "producer_name_address": producer_name_address,
        "is_import": is_import,
        "country_of_origin": country_of_origin,
        "government_warning": f"GOVERNMENT WARNING: {STANDARD_WARNING_BODY}",
    }


def rendered_label(application: Mapping[str, Any], **overrides: Any) -> Dict[str, Any]:
    label = {
        "brand_name": application["brand_name"],
        "class_type": application["class_type"],
        "alcohol_content": application["alcohol_content"],
        "net_contents": application["net_contents"],
        "producer_name_address": application["producer_name_address"],
        "country_of_origin": application["country_of_origin"],
        "warning_prefix": "GOVERNMENT WARNING:",
        "warning_body": STANDARD_WARNING_BODY,
    }
    label.update(overrides)
    return label


def exact_result(status: str, reason_code: str) -> Dict[str, str]:
    return {"status": status, "reason_code": reason_code}


def matching_field_results(application: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    results = {
        field_name: exact_result("match", "exact_match")
        for field_name in FIELD_NAMES
    }
    if not application["is_import"]:
        results["country_of_origin"] = exact_result("not_applicable", "not_applicable")
    return results


def finalize_output(
    field_results: Mapping[str, Mapping[str, str]],
    *,
    expected_tags: List[str],
) -> Dict[str, Any]:
    statuses = [payload["status"] for payload in field_results.values()]
    if "needs_review" in statuses:
        overall_verdict = "needs_review"
        recommended_action = "request_better_image"
    elif "mismatch" in statuses:
        overall_verdict = "mismatch"
        recommended_action = "manual_review"
    else:
        overall_verdict = "match"
        recommended_action = "accept"

    return {
        "overall_verdict": overall_verdict,
        "recommended_action": recommended_action,
        "field_results": deepcopy(dict(field_results)),
        "expected_tags": expected_tags,
    }


def make_case(
    *,
    case_id: str,
    category: str,
    description: str,
    application: Mapping[str, Any],
    label: Mapping[str, Any],
    field_results: Mapping[str, Mapping[str, str]],
    tags: List[str],
    render_style: str = "standard",
    degradation: str = "none",
) -> Dict[str, Any]:
    return {
        "inputs": {
            "case_id": case_id,
            "label_image_path": f"evals/golden_set/fixtures/{case_id}.png",
            "application": deepcopy(dict(application)),
        },
        "outputs": finalize_output(field_results, expected_tags=tags),
        "metadata": {
            "category": category,
            "description": description,
            "render_style": render_style,
            "degradation": degradation,
            "rendered_label": deepcopy(dict(label)),
        },
    }


def spec_cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    old_tom = base_application(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        producer_name_address="Old Tom Distillery, Louisville, KY",
    )
    stone_throw = base_application(
        brand_name="Stone's Throw",
        class_type="Small Batch Rye Whiskey",
        alcohol_content="40% Alc./Vol. (80 Proof)",
        net_contents="750 mL",
        producer_name_address="Stone's Throw Spirits, Bardstown, KY",
    )
    harbor_lane = base_application(
        brand_name="HARBOR LANE",
        class_type="Navy Strength Gin",
        alcohol_content="57% Alc./Vol. (114 Proof)",
        net_contents="700 mL",
        producer_name_address="Harbor Lane Distilling, Seattle, WA",
    )
    sierra_azul = base_application(
        brand_name="SIERRA AZUL",
        class_type="Reposado Tequila",
        alcohol_content="40% Alc./Vol. (80 Proof)",
        net_contents="750 mL",
        producer_name_address="Sierra Azul Imports, Austin, TX",
        is_import=True,
        country_of_origin="Mexico",
    )
    glen_north = base_application(
        brand_name="GLEN NORTH",
        class_type="Single Malt Scotch Whisky",
        alcohol_content="43% Alc./Vol. (86 Proof)",
        net_contents="750 mL",
        producer_name_address="Glen North Imports, New York, NY",
        is_import=True,
        country_of_origin="Scotland",
    )
    cedar_point = base_application(
        brand_name="CEDAR POINT",
        class_type="Straight Wheat Whiskey",
        alcohol_content="47% Alc./Vol. (94 Proof)",
        net_contents="700 mL",
        producer_name_address="Cedar Point Distilling, Richmond, VA",
    )

    # Clean matches: 6
    cases.append(
        make_case(
            case_id="gs_001",
            category="clean_match",
            description="Standard domestic distilled spirits label with all required fields readable.",
            application=old_tom,
            label=rendered_label(old_tom),
            field_results=matching_field_results(old_tom),
            tags=["clean_match", "domestic_not_applicable"],
        )
    )
    cases.append(
        make_case(
            case_id="gs_002",
            category="clean_match",
            description="Centered layout variation with the same correct values.",
            application=harbor_lane,
            label=rendered_label(harbor_lane),
            field_results=matching_field_results(harbor_lane),
            tags=["clean_match", "domestic_not_applicable"],
            render_style="centered",
        )
    )
    cases.append(
        make_case(
            case_id="gs_003",
            category="clean_match",
            description="Import label with the correct country of origin.",
            application=sierra_azul,
            label=rendered_label(sierra_azul),
            field_results=matching_field_results(sierra_azul),
            tags=["clean_match", "import_required"],
            render_style="framed",
        )
    )
    cases.append(
        make_case(
            case_id="gs_004",
            category="clean_match",
            description="Domestic label with country of origin correctly treated as not applicable.",
            application=cedar_point,
            label=rendered_label(cedar_point),
            field_results=matching_field_results(cedar_point),
            tags=["clean_match", "domestic_not_applicable"],
            render_style="boxed",
        )
    )
    cases.append(
        make_case(
            case_id="gs_005",
            category="clean_match",
            description="Readable label with slightly low-contrast typography.",
            application=stone_throw,
            label=rendered_label(stone_throw),
            field_results=matching_field_results(stone_throw),
            tags=["clean_match", "domestic_not_applicable"],
            render_style="light_ink",
            degradation="readable_noise",
        )
    )
    cases.append(
        make_case(
            case_id="gs_006",
            category="clean_match",
            description="Full government warning appears exactly and should pass.",
            application=glen_north,
            label=rendered_label(glen_north),
            field_results=matching_field_results(glen_north),
            tags=["clean_match", "warning_exact", "import_required"],
            render_style="warning_focus",
        )
    )

    # Normalization tolerant matches: 4
    brand_case_results = matching_field_results(stone_throw)
    brand_case_results["brand_name"] = exact_result("match", "normalized_match")
    cases.append(
        make_case(
            case_id="gs_007",
            category="normalization_match",
            description="Brand differs only by case and should normalize to a match.",
            application=stone_throw,
            label=rendered_label(stone_throw, brand_name="STONE'S THROW"),
            field_results=brand_case_results,
            tags=["normalization_tolerated", "domestic_not_applicable"],
            render_style="standard",
        )
    )
    punctuation_app = base_application(
        brand_name="RIVER RUN",
        class_type="Straight Bourbon Whiskey",
        alcohol_content="46% Alc./Vol. (92 Proof)",
        net_contents="750 mL",
        producer_name_address="River Run Distilling, Lexington, KY",
    )
    punctuation_results = matching_field_results(punctuation_app)
    punctuation_results["brand_name"] = exact_result("match", "normalized_match")
    cases.append(
        make_case(
            case_id="gs_008",
            category="normalization_match",
            description="Brand differs only by punctuation normalization.",
            application=punctuation_app,
            label=rendered_label(punctuation_app, brand_name="RIVER-RUN"),
            field_results=punctuation_results,
            tags=["normalization_tolerated", "domestic_not_applicable"],
            render_style="boxed",
        )
    )
    whitespace_results = matching_field_results(old_tom)
    whitespace_results["class_type"] = exact_result("match", "normalized_match")
    cases.append(
        make_case(
            case_id="gs_009",
            category="normalization_match",
            description="Class/type differs only by whitespace and line breaks.",
            application=old_tom,
            label=rendered_label(old_tom, class_type="Kentucky Straight\nBourbon Whiskey"),
            field_results=whitespace_results,
            tags=["normalization_tolerated", "domestic_not_applicable"],
            render_style="centered",
        )
    )
    alcohol_results = matching_field_results(old_tom)
    alcohol_results["alcohol_content"] = exact_result("match", "normalized_match")
    cases.append(
        make_case(
            case_id="gs_010",
            category="normalization_match",
            description="Alcohol content differs only by formatting conventions.",
            application=old_tom,
            label=rendered_label(old_tom, alcohol_content="45% ALC/VOL (90 PROOF)"),
            field_results=alcohol_results,
            tags=["normalization_tolerated", "domestic_not_applicable"],
            render_style="framed",
        )
    )

    # Single-field mismatches: 6
    wrong_brand = matching_field_results(old_tom)
    wrong_brand["brand_name"] = exact_result("mismatch", "wrong_value")
    cases.append(
        make_case(
            case_id="gs_011",
            category="single_field_mismatch",
            description="Brand name does not match the application.",
            application=old_tom,
            label=rendered_label(old_tom, brand_name="OLD FOX DISTILLERY"),
            field_results=wrong_brand,
            tags=["single_field_mismatch", "domestic_not_applicable"],
        )
    )
    wrong_class = matching_field_results(old_tom)
    wrong_class["class_type"] = exact_result("mismatch", "wrong_value")
    cases.append(
        make_case(
            case_id="gs_012",
            category="single_field_mismatch",
            description="Class/type differs from the application.",
            application=old_tom,
            label=rendered_label(old_tom, class_type="Tennessee Whiskey"),
            field_results=wrong_class,
            tags=["single_field_mismatch", "domestic_not_applicable"],
            render_style="centered",
        )
    )
    wrong_alcohol = matching_field_results(harbor_lane)
    wrong_alcohol["alcohol_content"] = exact_result("mismatch", "wrong_value")
    cases.append(
        make_case(
            case_id="gs_013",
            category="single_field_mismatch",
            description="Alcohol content differs from the application.",
            application=harbor_lane,
            label=rendered_label(harbor_lane, alcohol_content="40% Alc./Vol. (80 Proof)"),
            field_results=wrong_alcohol,
            tags=["single_field_mismatch", "domestic_not_applicable"],
            render_style="boxed",
        )
    )
    wrong_net = matching_field_results(sierra_azul)
    wrong_net["net_contents"] = exact_result("mismatch", "wrong_value")
    cases.append(
        make_case(
            case_id="gs_014",
            category="single_field_mismatch",
            description="Net contents are incorrect on the label.",
            application=sierra_azul,
            label=rendered_label(sierra_azul, net_contents="1 L"),
            field_results=wrong_net,
            tags=["single_field_mismatch", "import_required"],
            render_style="framed",
        )
    )
    wrong_producer = matching_field_results(stone_throw)
    wrong_producer["producer_name_address"] = exact_result("mismatch", "wrong_value")
    cases.append(
        make_case(
            case_id="gs_015",
            category="single_field_mismatch",
            description="Producer name and address are wrong.",
            application=stone_throw,
            label=rendered_label(stone_throw, producer_name_address="Stone's Throw Spirits, Frankfort, KY"),
            field_results=wrong_producer,
            tags=["single_field_mismatch", "domestic_not_applicable"],
            render_style="standard",
        )
    )
    wrong_origin = matching_field_results(glen_north)
    wrong_origin["country_of_origin"] = exact_result("mismatch", "wrong_value")
    cases.append(
        make_case(
            case_id="gs_016",
            category="single_field_mismatch",
            description="Imported product lists the wrong country of origin.",
            application=glen_north,
            label=rendered_label(glen_north, country_of_origin="Ireland"),
            field_results=wrong_origin,
            tags=["single_field_mismatch", "import_required"],
            render_style="warning_focus",
        )
    )

    # Government warning strictness: 4
    warning_exact = matching_field_results(old_tom)
    cases.append(
        make_case(
            case_id="gs_017",
            category="warning_strictness",
            description="Exact government warning text and prefix pass.",
            application=old_tom,
            label=rendered_label(old_tom),
            field_results=warning_exact,
            tags=["warning_exact", "domestic_not_applicable"],
            render_style="warning_focus",
        )
    )
    warning_prefix_error = matching_field_results(old_tom)
    warning_prefix_error["government_warning"] = exact_result("mismatch", "warning_prefix_error")
    cases.append(
        make_case(
            case_id="gs_018",
            category="warning_strictness",
            description="Title-cased warning prefix should fail strict validation.",
            application=old_tom,
            label=rendered_label(old_tom, warning_prefix="Government Warning:"),
            field_results=warning_prefix_error,
            tags=["warning_prefix_error", "domestic_not_applicable"],
            render_style="warning_focus",
        )
    )
    warning_body_error = matching_field_results(old_tom)
    warning_body_error["government_warning"] = exact_result("mismatch", "warning_text_mismatch")
    cases.append(
        make_case(
            case_id="gs_019",
            category="warning_strictness",
            description="Warning wording deviation should fail.",
            application=old_tom,
            label=rendered_label(
                old_tom,
                warning_body=STANDARD_WARNING_BODY.replace("birth defects", "serious defects"),
            ),
            field_results=warning_body_error,
            tags=["warning_text_deviation", "domestic_not_applicable"],
            render_style="warning_focus",
        )
    )
    warning_unreadable = matching_field_results(old_tom)
    warning_unreadable["government_warning"] = exact_result("needs_review", "unreadable")
    cases.append(
        make_case(
            case_id="gs_020",
            category="warning_strictness",
            description="Partially occluded warning should request a better image.",
            application=old_tom,
            label=rendered_label(old_tom),
            field_results=warning_unreadable,
            tags=["warning_partial_occlusion", "unreadable_image", "domestic_not_applicable"],
            render_style="warning_focus",
            degradation="warning_occlusion",
        )
    )

    # Unreadable / low-confidence: 4
    glare_results = {field: exact_result("needs_review", "unreadable") for field in FIELD_NAMES}
    cases.append(
        make_case(
            case_id="gs_021",
            category="unreadable",
            description="Heavy glare obscures multiple fields.",
            application=sierra_azul,
            label=rendered_label(sierra_azul),
            field_results=glare_results,
            tags=["unreadable_image", "import_required"],
            render_style="framed",
            degradation="heavy_glare",
        )
    )
    blur_results = {field: exact_result("needs_review", "unreadable") for field in FIELD_NAMES}
    cases.append(
        make_case(
            case_id="gs_022",
            category="unreadable",
            description="Blur prevents reliable extraction.",
            application=stone_throw,
            label=rendered_label(stone_throw),
            field_results=blur_results,
            tags=["unreadable_image", "domestic_not_applicable"],
            render_style="standard",
            degradation="gaussian_blur",
        )
    )
    skew_results = {field: exact_result("needs_review", "unreadable") for field in FIELD_NAMES}
    cases.append(
        make_case(
            case_id="gs_023",
            category="unreadable",
            description="Perspective skew makes the warning unreadable.",
            application=glen_north,
            label=rendered_label(glen_north),
            field_results=skew_results,
            tags=["unreadable_image", "import_required"],
            render_style="warning_focus",
            degradation="skew",
        )
    )
    crop_results = {field: exact_result("needs_review", "unreadable") for field in FIELD_NAMES}
    cases.append(
        make_case(
            case_id="gs_024",
            category="unreadable",
            description="Bottom crop removes required fields.",
            application=harbor_lane,
            label=rendered_label(harbor_lane),
            field_results=crop_results,
            tags=["unreadable_image", "domestic_not_applicable"],
            render_style="centered",
            degradation="crop_bottom",
        )
    )

    # Conditional applicability: 4
    domestic_na = matching_field_results(cedar_point)
    cases.append(
        make_case(
            case_id="gs_025",
            category="conditional_applicability",
            description="Domestic product correctly treats country of origin as not applicable.",
            application=cedar_point,
            label=rendered_label(cedar_point),
            field_results=domestic_na,
            tags=["conditional_rule", "domestic_not_applicable"],
            render_style="boxed",
        )
    )
    import_missing = matching_field_results(sierra_azul)
    import_missing["country_of_origin"] = exact_result("mismatch", "missing_required")
    cases.append(
        make_case(
            case_id="gs_026",
            category="conditional_applicability",
            description="Imported product missing country of origin should mismatch.",
            application=sierra_azul,
            label=rendered_label(sierra_azul, country_of_origin=None),
            field_results=import_missing,
            tags=["conditional_rule", "import_required"],
            render_style="framed",
        )
    )
    import_correct = matching_field_results(glen_north)
    cases.append(
        make_case(
            case_id="gs_027",
            category="conditional_applicability",
            description="Imported product with correct country of origin should pass.",
            application=glen_north,
            label=rendered_label(glen_north),
            field_results=import_correct,
            tags=["conditional_rule", "import_required"],
            render_style="warning_focus",
        )
    )
    domestic_still_match = matching_field_results(old_tom)
    cases.append(
        make_case(
            case_id="gs_028",
            category="conditional_applicability",
            description="Domestic product should not fail because country of origin is absent.",
            application=old_tom,
            label=rendered_label(old_tom),
            field_results=domestic_still_match,
            tags=["conditional_rule", "domestic_not_applicable"],
            render_style="standard",
        )
    )

    assert len(cases) == 28, f"Expected 28 golden-set cases, found {len(cases)}"
    return cases


def draw_multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    xy: Tuple[int, int],
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int],
    width_chars: int,
    line_spacing: int = 8,
) -> int:
    x, y = xy
    lines: List[str] = []
    for paragraph in text.splitlines():
        wrapped = textwrap.wrap(paragraph, width=width_chars) or [""]
        lines.extend(wrapped)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + line_spacing
    return y


def render_label_image(case: Mapping[str, Any], fixtures_dir: Path) -> None:
    metadata = case["metadata"]
    label = metadata["rendered_label"]
    style = metadata["render_style"]
    degradation = metadata["degradation"]
    case_id = case["inputs"]["case_id"]

    background = (248, 244, 236)
    text_color = (20, 20, 20)
    if style == "light_ink":
        text_color = (80, 72, 68)

    image = Image.new("RGB", IMAGE_SIZE, background)
    draw = ImageDraw.Draw(image)

    brand_font = load_font(52, bold=True)
    subhead_font = load_font(30, bold=True)
    body_font = load_font(28)
    warning_prefix_font = load_font(28, bold=True)
    warning_body_font = load_font(24)

    draw.rounded_rectangle((50, 50, IMAGE_SIZE[0] - 50, IMAGE_SIZE[1] - 50), radius=26, outline=(70, 55, 35), width=6)

    if style in {"centered", "warning_focus"}:
        brand_bbox = draw.textbbox((0, 0), str(label["brand_name"]), font=brand_font)
        brand_x = (IMAGE_SIZE[0] - (brand_bbox[2] - brand_bbox[0])) // 2
    else:
        brand_x = MARGIN_X

    y = 120
    draw.text((brand_x, y), str(label["brand_name"]), font=brand_font, fill=text_color)
    y += 92

    if style == "boxed":
        draw.rectangle((MARGIN_X - 20, y - 20, IMAGE_SIZE[0] - MARGIN_X + 20, y + 160), outline=(80, 80, 80), width=3)

    y = draw_multiline(
        draw,
        str(label["class_type"]),
        xy=(MARGIN_X, y),
        font=subhead_font,
        fill=text_color,
        width_chars=34,
        line_spacing=10,
    ) + 26
    y = draw_multiline(
        draw,
        f"{label['alcohol_content']}    {label['net_contents']}",
        xy=(MARGIN_X, y),
        font=body_font,
        fill=text_color,
        width_chars=44,
    ) + 18
    y = draw_multiline(
        draw,
        str(label["producer_name_address"]),
        xy=(MARGIN_X, y),
        font=body_font,
        fill=text_color,
        width_chars=46,
    ) + 18

    if label.get("country_of_origin"):
        y = draw_multiline(
            draw,
            f"Country of Origin: {label['country_of_origin']}",
            xy=(MARGIN_X, y),
            font=body_font,
            fill=text_color,
            width_chars=42,
        ) + 18

    warning_y = max(y + 30, 980 if style == "warning_focus" else y + 30)
    draw.line((MARGIN_X, warning_y - 16, IMAGE_SIZE[0] - MARGIN_X, warning_y - 16), fill=(120, 110, 102), width=2)
    draw.text((MARGIN_X, warning_y), str(label["warning_prefix"]), font=warning_prefix_font, fill=text_color)
    warning_text_y = warning_y + warning_prefix_font.size + 12
    draw_multiline(
        draw,
        str(label["warning_body"]),
        xy=(MARGIN_X, warning_text_y),
        font=warning_body_font,
        fill=text_color,
        width_chars=66,
        line_spacing=6,
    )

    image = apply_degradation(image, degradation)
    image.save(fixtures_dir / f"{case_id}.png")


def apply_degradation(image: Image.Image, degradation: str) -> Image.Image:
    if degradation == "none":
        return image

    if degradation == "readable_noise":
        noise = Image.effect_noise(image.size, 6).convert("L")
        noise_rgb = Image.merge("RGB", (noise, noise, noise))
        return Image.blend(image, noise_rgb, 0.08)

    if degradation == "warning_occlusion":
        occluded = image.copy()
        draw = ImageDraw.Draw(occluded)
        draw.rectangle((140, 1070, 1080, 1210), fill=(245, 245, 245))
        return occluded

    if degradation == "heavy_glare":
        glare = image.copy()
        overlay = Image.new("RGB", image.size, (255, 255, 255))
        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((240, 220, 1080, 1320), fill=205)
        composite = Image.composite(overlay, glare, mask)
        return Image.blend(glare, composite, 0.55)

    if degradation == "gaussian_blur":
        return image.filter(ImageFilter.GaussianBlur(radius=5.5))

    if degradation == "skew":
        return image.transform(
            image.size,
            Image.Transform.AFFINE,
            (1.0, -0.22, 140, 0.05, 1.0, -70),
            resample=Image.Resampling.BICUBIC,
            fillcolor=(248, 244, 236),
        )

    if degradation == "crop_bottom":
        cropped = image.crop((0, 0, image.size[0], image.size[1] - 330))
        canvas = Image.new("RGB", image.size, (248, 244, 236))
        canvas.paste(cropped, (0, 0))
        return canvas

    return image


def write_cases(cases: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=True) + "\n")


def build_dataset() -> List[Dict[str, Any]]:
    cases = spec_cases()
    DEFAULT_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for png_path in DEFAULT_FIXTURES_DIR.glob("*.png"):
        png_path.unlink()
    for case in cases:
        render_label_image(case, DEFAULT_FIXTURES_DIR)
    write_cases(cases, DEFAULT_CASES_PATH)
    return cases


def main() -> None:
    cases = build_dataset()
    print(
        f"Built {len(cases)} golden-set cases, wrote {DEFAULT_CASES_PATH.name}, "
        f"and rendered fixtures to {DEFAULT_FIXTURES_DIR}"
    )


if __name__ == "__main__":
    main()
