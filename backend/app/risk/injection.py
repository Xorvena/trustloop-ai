"""Heuristic prompt-injection detector for UNTRUSTED text (product descriptions, merchant content).

This is a tripwire for risk scoring and UI warnings, not the defense itself. The real defense is
architectural: untrusted text never reaches a component that can move money, and the LLM has no tools.
"""
import re

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("instruction_override", re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|all|earlier|system)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?|polic(?:y|ies))\b", re.I)),
    ("forced_purchase", re.compile(r"\b(immediately|now|instantly|automatically)\b[^.\n]{0,30}\b(buy|purchase|pay|checkout|order)\b", re.I)),
    ("role_hijack", re.compile(r"\b(you are now|act as|new instructions?|system prompt|developer mode|jailbreak)\b", re.I)),
    ("policy_bypass", re.compile(r"\b(bypass|skip|disable|waive)\b[^.\n]{0,30}\b(approval|limit|budget|polic(?:y|ies)|check|review)\b", re.I)),
    ("credential_exfil", re.compile(r"\b(reveal|print|send|leak)\b[^.\n]{0,30}\b(api[ _-]?key|secret|token|password|credentials?)\b", re.I)),
    ("tool_invocation", re.compile(r"\b(call|invoke|execute|run)\b[^.\n]{0,20}\b(capture|payment|paypal|transfer|tool|function)\b", re.I)),
]


def detect(text: str) -> list[str]:
    if not text:
        return []
    return [name for name, pat in PATTERNS if pat.search(text)]
