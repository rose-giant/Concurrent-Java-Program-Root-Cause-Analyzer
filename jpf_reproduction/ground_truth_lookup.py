"""
Reproduces the exact problem-name matching rule described in the CONCUR
README: "Problem name matching between prompts.csv and ground_truth.csv
strips trailing ' M1', ' M2', ' M3' suffixes from the prompt title and
matches on the base name up to and including the first '.'"
"""

import csv
import re


def get_base_problem_name(prompt_title: str) -> str:
    base_name = re.sub(r"\s+M\d+$", "", prompt_title).strip()
    dot_pos = base_name.find(".")
    if dot_pos != -1:
        base_name = base_name[: dot_pos + 1]
    return base_name


def load_ground_truth(path: str) -> dict:
    """Returns {problem_name: {"ground_truth": str, "max_depth": str}}"""
    gt_map = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["Problem Name"].strip()
            if name:
                gt_map[name] = {
                    "ground_truth": row.get("Ground-truth", "").strip(),
                    "max_depth": row.get("Max Depth", "").strip(),
                }
    return gt_map


def lookup_max_depth(prompt_title: str, gt_map: dict, default: str = "300") -> str:
    """
    CONCUR multiplies the CSV's Max Depth by 10 at runtime
    (per README: "The max_depth value from ground_truth.csv is
    multiplied by 10 before being passed to JPF.")
    """
    base_name = get_base_problem_name(prompt_title)
    entry = gt_map.get(base_name)
    if entry and entry["max_depth"]:
        try:
            return str(int(entry["max_depth"]) * 10)
        except ValueError:
            return default
    return default
