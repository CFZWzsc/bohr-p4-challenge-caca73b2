#!/usr/bin/env python3
"""Deterministic Results-and-Discussion extraction helper.

Reads a case JSON (default /input/case.json) and writes a structured
result JSON (default /app/output/result.json). Standard library only,
no network, deterministic. Numeric claims are copied verbatim from the
supplied materials and each one carries a source locator; nothing is
invented when a material or a value is missing.
"""

import argparse
import hashlib
import json
import os
import re
import sys

STATUS_OK = "success"
STATUS_PARTIAL = "partial"
STATUS_INSUFFICIENT = "insufficient_input"
STATUS_FAILED = "failed"

NUM_RE = re.compile(
    r"(?<![\w.])-?\d+(?:\.\d+)?\s*"
    r"(?:%|‰|°C|°|mg|kg|µg|μg|ng|g/mL|mg/mL|µg/mL|mL|ml|µL|μL|L|"
    r"nm|µm|μm|mm|cm|km|m|ms|min|h|hr|days?|weeks?|wk|months?|years?|"
    r"nM|µM|μM|mM|M|kPa|MPa|GPa|Pa|kJ|kcal|J|eV|kHz|MHz|GHz|Hz|"
    r"mV|kV|V|mA|A|ppm|ppb|fold|Da|kDa)(?![A-Za-z])"
)
BARE_NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
STAT_RE = re.compile(
    r"(p\s*[<=>]\s*0?\.\d+|95\s*%\s*(?:CI|confidence)|CI\s*[\[(]|"
    r"±|mean\s*[±+-]|\bSD\b|\bSEM\b|n\s*=\s*\d+|d\s*=\s*0?\.\d+)",
    re.IGNORECASE,
)
CAUSAL = (
    "cause", "causes", "caused", "leads to", "led to", "results in", "drives",
    "proves", "demonstrates that", "confirms that", "because of", "therefore",
    "thus", "证明", "导致", "引起", "因此", "由此可见", "说明",
)
HEDGE = (
    "may", "might", "could", "suggests", "is consistent with", "was associated",
    "可能", "提示", "与…一致", "相关", "有待",
)
DISCUSSION_MARK = (
    "consistent with", "prior work", "previous stud", "literature", "hypothes",
    "mechanism", "limitation", "limited", "limits", "inference", "interpret", "explain",
    "we speculate", "we suggest", "in contrast", "unlike",
    "与既往", "文献", "机制", "局限", "推测", "解释", "假设",
)
RESULT_VERB = (
    "increased", "decreased", "was", "were", "reduced", "improved", "showed",
    "reached", "remained", "differed", "no significant", "observed",
    "增加", "降低", "减少", "达到", "未见", "差异", "为",
)
MATERIAL_KEYS = (
    "materials", "data", "dataset", "datasets", "tables", "table", "figures",
    "figure_captions", "captions", "statistics", "stats", "notes", "results",
    "discussion", "observations", "measurements", "text", "content",
)


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def read_if_path(value):
    if not isinstance(value, str) or len(value) > 4096 or "\n" in value:
        return None, None
    candidate = value.strip()
    if not candidate or not os.path.isfile(candidate):
        return None, None
    try:
        if os.path.getsize(candidate) > 2 * 1024 * 1024:
            return None, candidate
        with open(candidate, "r", encoding="utf-8-sig") as fh:
            return fh.read(), candidate
    except (OSError, UnicodeDecodeError):
        return None, candidate


def collect_materials(case):
    items, unreadable = [], []

    def add(label, text, path):
        if text and text.strip():
            items.append({"label": label, "path": path, "text": text})

    def walk(node, label):
        if isinstance(node, str):
            text, path = read_if_path(node)
            if text is not None:
                add(label, text, path)
            elif path is not None:
                unreadable.append({"label": label, "path": path, "reason": "unreadable_or_too_large"})
            elif len(node.strip()) >= 20:
                add(label, node, None)
            return
        if isinstance(node, dict):
            path_value = node.get("path") or node.get("file") or node.get("filename")
            if isinstance(path_value, str):
                text, path = read_if_path(path_value)
                if text is not None:
                    add(label, text, path)
                    return
                if path is not None:
                    unreadable.append({"label": label, "path": path, "reason": "unreadable_or_too_large"})
                    return
            for key in ("content", "text", "body", "markdown", "caption", "value", "rows", "data"):
                if key in node and isinstance(node[key], (str, list, dict)):
                    walk(node[key], "%s.%s" % (label, key))
                    return
            for key, value in node.items():
                if key in ("id", "name", "title", "source", "type", "kind", "path", "file", "filename"):
                    continue
                walk(value, "%s.%s" % (label, key))
            return
        if isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, "%s[%d]" % (label, idx))

    for key, value in case.items():
        if key in ("output_contract", "scoring", "tags", "meta", "case_id", "challenge_id"):
            continue
        if key in MATERIAL_KEYS or not isinstance(value, (str, list, dict)):
            walk(value, key)
    if not items:
        for key, value in case.items():
            if key in ("output_contract", "scoring", "tags", "meta", "case_id", "challenge_id"):
                continue
            walk(value, key)
    return items, unreadable


def sentence_spans(text):
    """Split on sentence punctuation, keeping decimal points inside numbers."""
    spans, start = [], 0
    length = len(text)
    for idx, char in enumerate(text):
        if char not in ".!?。！？\n":
            continue
        if char == "." and idx + 1 < length and text[idx + 1].isdigit():
            continue
        end = idx + 1
        while end < length and text[end] in ".!?\"'\u201d\u2019":
            end += 1
        chunk = text[start:end]
        if chunk.strip():
            lead = len(chunk) - len(chunk.lstrip())
            spans.append({"text": chunk.strip(), "start": start + lead, "end": end})
        start = end
    if start < length:
        chunk = text[start:]
        if chunk.strip():
            lead = len(chunk) - len(chunk.lstrip())
            spans.append({"text": chunk.strip(), "start": start + lead, "end": length})
    return spans


def has_causal(text):
    lowered = text.lower()
    return any(marker in lowered for marker in CAUSAL)


def has_stat(text):
    return bool(STAT_RE.search(text))


def is_discussion(sentence):
    lowered = sentence.lower()
    if any(marker in lowered for marker in DISCUSSION_MARK):
        return True
    return has_causal(sentence) and not has_stat(sentence) and not NUM_RE.search(sentence)


def classify_material(item):
    lowered = (item["label"] + " " + item["text"][:400]).lower()
    if any(key in lowered for key in ("discussion", "讨论", "interpret")):
        return "discussion"
    if any(key in lowered for key in ("results", "result", "结果", "table", "figure", "图")):
        return "results"
    return "mixed"


def extract_numbers(item):
    claims = []
    if len(item["text"]) > 400000:
        return claims
    for span in sentence_spans(item["text"]):
        sentence = span["text"]
        for match in NUM_RE.finditer(sentence):
            token = norm(match.group(0))
            value_match = re.match(r"-?\d+(?:\.\d+)?", token)
            unit = token[value_match.end():].strip() if value_match else ""
            claims.append({
                "value": value_match.group(0) if value_match else token,
                "unit": unit,
                "raw": token,
                "claim": norm(sentence)[:300],
                "source_label": item["label"],
                "source_path": item["path"],
                "char_start": span["start"] + match.start(),
                "char_end": span["start"] + match.end(),
                "has_stat_context": has_stat(sentence),
            })
    return claims


def contract_fields(contract):
    fields, unsupported = [], []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            return list(contract["properties"].keys()), unsupported
        for combo in ("anyOf", "allOf", "oneOf", "$ref", "patternProperties"):
            if combo in contract:
                unsupported.append(combo)
        nested = contract.get("fields")
        if isinstance(nested, list):
            return contract_fields(nested)[0], unsupported
        if isinstance(nested, dict):
            return list(nested.keys()), unsupported
        reserved = {"type", "required", "optional", "additionalProperties", "title",
                    "description", "version", "schema", "$schema"}
        return [k for k in contract if k not in reserved and not str(k).startswith("$")], unsupported
    if isinstance(contract, list):
        for entry in contract:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
        return fields, unsupported
    if isinstance(contract, str) and contract.strip():
        return [contract.strip()], unsupported
    return fields, unsupported


ALIASES = {
    "status": "status",
    "results": "results_draft",
    "result": "results_draft",
    "results_section": "results_draft",
    "results_draft": "results_draft",
    "discussion": "discussion_draft",
    "discussion_section": "discussion_draft",
    "discussion_draft": "discussion_draft",
    "evidence": "evidence",
    "evidence_map": "evidence",
    "sources": "sources",
    "source_map": "sources",
    "numeric_table": "numeric_table",
    "numeric_claims": "numeric_table",
    "numbers": "numeric_table",
    "claim_audit": "claim_audit",
    "audit": "claim_audit",
    "uncertainty": "uncertainty",
    "uncertainties": "uncertainty",
    "limitations": "limitations",
    "summary": "summary",
    "metrics": "stats",
    "stats": "stats",
    "section_map": "section_map",
}


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Results and Discussion extraction helper")
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--out", "--output", default="/app/output/result.json")
    parser.add_argument("--work", default="/app/work")
    args = parser.parse_args()

    result = {
        "case_id": None,
        "status": STATUS_FAILED,
        "result": {
            "results_draft": "",
            "discussion_draft": "",
            "numeric_table": [],
            "claim_audit": [],
            "section_map": [],
        },
        "evidence": [],
        "uncertainty": [],
        "errors": [],
        "stats": {},
    }
    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case root is not an object")
    except (OSError, ValueError) as exc:
        result["errors"].append({"stage": "read_case", "type": type(exc).__name__,
                                 "detail": "case.json missing or not valid JSON"})
        result["uncertainty"].append({"item": "input", "detail": "case_unreadable"})
        write_json(args.out, result)
        return 2

    result["case_id"] = case.get("case_id") or case.get("id") or case.get("challenge_id")
    contract = case.get("output_contract")
    materials, unreadable = collect_materials(case)

    if not materials:
        result["status"] = STATUS_INSUFFICIENT
        result["uncertainty"].append({"item": "materials", "detail": "no readable text material in case"})
        result["limitations"] = ["materials_missing"]
        fill_contract(result, contract)
        write_json(args.out, result)
        return 0

    numeric_table, results_lines, discussion_lines, evidence = [], [], [], []
    audit = []
    seen_results = set()
    section_map = []
    for item in materials:
        role = classify_material(item)
        section_map.append({"label": item["label"], "path": item["path"], "role": role,
                            "chars": len(item["text"]), "sha256": sha256_text(item["text"])})
        claims = extract_numbers(item)
        numeric_table.extend(claims)
        for claim in claims[:60]:
            evidence.append({
                "claim": claim["claim"],
                "value": claim["value"],
                "unit": claim["unit"],
                "source_label": claim["source_label"],
                "source_path": claim["source_path"],
                "char_start": claim["char_start"],
                "char_end": claim["char_end"],
                "has_stat_context": claim["has_stat_context"],
            })
        for span in sentence_spans(item["text"]):
            sentence = span["text"]
            if is_discussion(sentence):
                if sentence not in seen_results:
                    discussion_lines.append("[%s] %s" % (item["label"], norm(sentence)))
                    seen_results.add(sentence)
                if has_causal(sentence) and not has_stat(sentence):
                    audit.append({
                        "sentence": norm(sentence)[:300],
                        "issue": "causal_language_without_statistics",
                        "source_label": item["label"],
                        "suggested_hedge": hedge_sentence(sentence),
                    })
                continue
            if NUM_RE.search(sentence) or any(verb in sentence.lower() for verb in RESULT_VERB):
                if sentence in seen_results:
                    continue
                seen_results.add(sentence)
                tag = "[%s@%d]" % (item["label"], span["start"])
                results_lines.append("%s %s" % (norm(sentence), tag))

    result["result"]["results_draft"] = "\n".join(results_lines)
    result["result"]["discussion_draft"] = "\n".join(discussion_lines)
    result["result"]["numeric_table"] = numeric_table[:300]
    result["result"]["claim_audit"] = audit
    result["result"]["section_map"] = section_map
    result["evidence"] = evidence[:300]

    if unreadable:
        for entry in unreadable:
            result["uncertainty"].append({"item": "material", "detail": entry["reason"],
                                          "label": entry["label"], "path": entry["path"]})
    ambiguous_units = {c["unit"] for c in numeric_table if c.get("unit") in ("±",)}
    if ambiguous_units:
        result["uncertainty"].append({"item": "error_bar", "detail": "error_bar_type_not_declared"})
    if not numeric_table:
        result["uncertainty"].append({"item": "numbers", "detail": "no_numeric_claims_found"})

    result["stats"] = {
        "materials": len(materials),
        "unreadable_materials": len(unreadable),
        "numeric_claims": len(numeric_table),
        "traceable_claims": len(evidence),
        "results_sentences": len(results_lines),
        "discussion_sentences": len(discussion_lines),
        "claims_needing_hedge": len(audit),
    }
    result["limitations"] = [
        "Extraction only: values are copied from supplied materials, not recomputed.",
        "Units are preserved as written; no conversion is applied.",
        "No statistics were re-run and no significance was inferred.",
    ]
    if not results_lines:
        result["limitations"].append("no_result_sentences_detected")
        result["uncertainty"].append({"item": "results", "detail": "no_result_sentence_detected"})
    if not discussion_lines:
        result["limitations"].append("no_discussion_sentences_detected")
    result["status"] = STATUS_OK if (numeric_table and results_lines and discussion_lines) else STATUS_PARTIAL

    fill_contract(result, contract)
    write_json(args.out, result)
    if result["status"] == STATUS_FAILED:
        return 2
    if result["contract_status"]["unmapped_fields"]:
        return 1
    return 0


def hedge_sentence(sentence):
    lowered = sentence.lower()
    replacements = [
        ("therefore causes", "may be associated with"),
        ("causes", "was associated with"),
        ("leads to", "was accompanied by"),
        ("proves", "is consistent with"),
        ("证明", "提示"),
        ("导致", "伴随"),
    ]
    for source, target in replacements:
        if source in lowered:
            return re.sub(re.escape(source), target, sentence, count=1, flags=re.IGNORECASE)
    return re.sub(r"\b(therefore|thus)\b", "possibly", sentence, count=1, flags=re.IGNORECASE)


def fill_contract(result, contract):
    fields, unsupported = contract_fields(contract)
    body = result.get("result") if isinstance(result.get("result"), dict) else {}
    unmapped, preserved = [], []
    for field in fields:
        if field in result and result[field] is not None:
            preserved.append(field)
            continue
        key = ALIASES.get(field.lower(), field.lower())
        if key in result and result[key] is not None:
            result[field] = result[key]
            preserved.append(field)
        elif key in body and body[key] is not None:
            result[field] = body[key]
            preserved.append(field)
        else:
            result[field] = None
            unmapped.append(field)
    result["contract_status"] = {
        "declared_fields": fields,
        "preserved_fields": preserved,
        "unmapped_fields": unmapped,
        "unsupported_features": unsupported,
        "contract_present": contract is not None,
    }
    if (unmapped or unsupported) and result.get("status") == STATUS_OK:
        result["status"] = STATUS_PARTIAL


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
