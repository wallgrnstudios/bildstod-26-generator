"""Create review-only image-brief suggestions with a local open model.

The drafter never changes the image catalog. It writes a separate state file
that an editor must explicitly turn into a resolved, generation-ready brief.
"""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
DEFAULT_MODEL = "qwen3:1.7b"


def load_records(path):
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "records": {}}
    data = json.loads(path.read_text())
    if data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("records"), dict):
        raise ValueError("Invalid brief-draft state")
    return data


def candidates(resolutions, existing, limit, include_conventions=False):
    """Choose unresolved semantic decisions first; existing drafts are immutable."""
    kinds = {"open_question"}
    if include_conventions:
        kinds.add("convention_proposal")
    rows = [row for row in resolutions if row.get("resolution") in kinds
            and existing.get(row["id"], {}).get("status") != "needs_editorial_review"]
    rows.sort(key=lambda row: (row["resolution"] != "open_question", row["id"]))
    return rows[:limit]


def prompt_for(row):
    source = {
        "id": row["id"], "term_sv": row["text_sv"], "kind": row["resolution"],
        "meaning_sv": row["meaning_sv"],
        "question_or_proposal_sv": row.get("question_sv", row.get("proposal_sv", "")),
        "options_sv": row.get("options_sv", []),
        "existing_visual_proposal_en": row.get("proposal_visual_en", ""),
        "contrast_terms_sv": row.get("contrast_terms_sv", []),
    }
    return """/no_think
You are drafting a proposal for a Swedish preschool visual-support editor.
Do not decide that it is approved. Do not create a sentence illustration.
Suggest exactly one atomic, observable image meaning. If the word is too ambiguous, set safe_to_generate to false.
Use English only in visual_prompt_en. Do not mention style, text in the image, brand names, scenery or a reference image.
Return JSON only with these fields: safe_to_generate (boolean), meaning_sv (string), visual_prompt_en (string), must_show_sv (array of 1-3 strings), must_not_show_sv (array of 1-4 strings), contrast_terms_sv (array of strings), review_question_sv (string).
Input:
""" + json.dumps(source, ensure_ascii=False)


def parse_suggestion(output):
    """Accept only the small review schema, including model output with thinking text."""
    cleaned = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return JSON")
    value = json.loads(cleaned[start:end + 1])
    required = {"safe_to_generate", "meaning_sv", "visual_prompt_en", "must_show_sv",
                "must_not_show_sv", "contrast_terms_sv", "review_question_sv"}
    if set(value) != required or not isinstance(value["safe_to_generate"], bool):
        raise ValueError("Model returned an invalid brief schema")
    for key in ("meaning_sv", "visual_prompt_en", "review_question_sv"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError("Missing text field: " + key)
    for key in ("must_show_sv", "must_not_show_sv", "contrast_terms_sv"):
        if not isinstance(value[key], list) or not all(isinstance(x, str) and x.strip() for x in value[key]):
            raise ValueError("Invalid list field: " + key)
    if not 1 <= len(value["must_show_sv"]) <= 3 or not 1 <= len(value["must_not_show_sv"]) <= 4:
        raise ValueError("Unbounded visual requirements")
    if len(value["visual_prompt_en"].split()) > 110:
        raise ValueError("Draft prompt is too long")
    return value


def ask_model(row, model=DEFAULT_MODEL, runner=subprocess.run):
    result = runner(["ollama", "run", "--format", "json", model, prompt_for(row)], text=True, capture_output=True,
                    timeout=120, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Local model failed")
    return parse_suggestion(result.stdout)


def draft(resolutions, state, limit, include_conventions=False, ask=ask_model, model=DEFAULT_MODEL):
    selected = candidates(resolutions, state["records"], limit, include_conventions)
    for row in selected:
        try:
            suggestion = ask(row, model=model)
            status = "needs_editorial_review"
            error = None
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            suggestion = None
            status = "model_error"
            error = str(exc)
        state["records"][row["id"]] = {
            "source_id": row["id"], "term_sv": row["text_sv"], "source_resolution": row["resolution"],
            "status": status, "created_at": datetime.now(timezone.utc).isoformat(),
            "model": model, "suggestion": suggestion, "error": error,
        }
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "run"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--include-conventions", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    if not 1 <= args.limit <= 25:
        raise SystemExit("--limit must be between 1 and 25")
    resolutions = json.loads((ROOT / "catalog/school/concept-resolutions.json").read_text())
    state_path = args.state / "brief-drafts.json"
    state = load_records(state_path)
    selected = candidates(resolutions, state["records"], args.limit, args.include_conventions)
    if args.command == "plan":
        print(json.dumps({"count": len(selected), "ids": [row["id"] for row in selected]}, ensure_ascii=False))
        return
    draft(resolutions, state, args.limit, args.include_conventions, model=args.model)
    args.state.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"created": len(selected), "state": str(state_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
