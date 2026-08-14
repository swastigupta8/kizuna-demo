#!/usr/bin/env python3
"""
Calls the deployed Kizuna API with this repo's docker-compose.yml, writes a
markdown PR comment, and exits non-zero if the score is below threshold —
that non-zero exit is what actually fails the GitHub check.

Uses only the standard library on purpose: no pip install step needed in CI,
which keeps the workflow fast and removes an entire category of "works on my
machine, fails in CI" dependency drift.
"""

import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

API_URL = os.environ["KIZUNA_API_URL"].rstrip("/")
REPO = os.environ["GITHUB_REPOSITORY"]
THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "75"))
COMPOSE_PATH = os.environ.get("COMPOSE_PATH", "docker-compose.yml")
COMMENT_PATH = os.environ.get("KIZUNA_COMMENT_PATH", "kizuna_comment.md")


def main() -> None:
    with open(COMPOSE_PATH, encoding="utf-8") as f:
        compose_yaml = f.read()

    result = call_kizuna(compose_yaml)
    comment = format_comment(result, THRESHOLD)

    with open(COMMENT_PATH, "w", encoding="utf-8") as f:
        f.write(comment)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"overall_score={result['overall_score']}\n")

    print(comment)

    if result["overall_score"] < THRESHOLD:
        print(
            f"Resilience score {result['overall_score']} is below threshold {THRESHOLD}",
            file=sys.stderr,
        )
        sys.exit(1)


def call_kizuna(compose_yaml: str) -> dict:
    payload = json.dumps({"repo": REPO, "compose_yaml": compose_yaml}).encode()
    request = urllib.request.Request(
        f"{API_URL}/api/v1/score",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def format_comment(result: dict, threshold: float) -> str:
    lines = [
        f"### Kizuna Resilience Check — **{result['overall_score']}/100**",
        "",
        "| Sub-score | Value |",
        "|---|---|",
        f"| Blast Radius | {result['blast_radius_score']} |",
        f"| Recovery | {result['recovery_score']} |",
        f"| Redundancy | {result['redundancy_score']} |",
        f"| Degradation | {result['degradation_score']} |",
        "",
    ]

    if result["findings"]:
        lines.append("**Findings:**")
        for finding in result["findings"]:
            fix = f" — _{finding['remediation']}_" if finding.get("remediation") else ""
            lines.append(f"- `{finding['severity']}` **{finding['node_id']}**: {finding['message']}{fix}")
    else:
        lines.append("No findings — clean bill of health.")

    lines.append("")
    if result["overall_score"] < threshold:
        lines.append(f"❌ **This PR would fail the resilience gate** (threshold: {threshold}).")
    else:
        lines.append(f"✅ Passes the resilience gate (threshold: {threshold}).")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
