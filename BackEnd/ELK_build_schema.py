import requests
import json
import re
from typing import List, Dict, Optional

ES_URL = "http://192.168.111.162:9200"
SKIP_KEYWORD = True          # bỏ field .keyword
BATCH = 50                   # số field / batch khi msearch
TIMEOUT = 60
OUT_FILE = "ELK_schema.json"
# Nếu cần auth: ("user", "pass") hoặc None
AUTH = None  # ("elastic", "changeme")

# ---------- flatten mapping (unchanged) ----------
def flatten_properties(props, prefix=""):
    fields = []
    for name, val in props.items():
        path = f"{prefix}.{name}" if prefix else name
        fields.append(path)

        if isinstance(val, dict) and "fields" in val:
            for sub in val["fields"].keys():
                fields.append(f"{path}.{sub}")

        if isinstance(val, dict) and "properties" in val:
            fields += flatten_properties(val["properties"], path)

    return fields

# ---------- get all fields from mapping ----------
def get_all_fields(es_url: str, index_pattern: str) -> List[str]:
    """
    index_pattern can be a pattern like 'windows-*', '.ds-filebeat-*', or a comma-separated list of indices.
    """
    url = f"{es_url.rstrip('/')}/{index_pattern}/_mapping"
    r = requests.get(url, timeout=TIMEOUT, auth=AUTH)
    r.raise_for_status()
    mapping = r.json()

    fields = set()

    for idx, body in mapping.items():
        mappings = body.get("mappings", {})
        props = mappings.get("properties")

        if props:
            for f in flatten_properties(props):
                if SKIP_KEYWORD and ".keyword" in f:
                    continue
                fields.add(f)
        else:
            stack = [body]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if "properties" in node:
                        for f in flatten_properties(node["properties"]):
                            if SKIP_KEYWORD and ".keyword" in f:
                                continue
                            fields.add(f)
                    for v in node.values():
                        if isinstance(v, dict):
                            stack.append(v)
                        elif isinstance(v, list):
                            for it in v:
                                if isinstance(it, dict):
                                    stack.append(it)

    return sorted(fields)

# ---------- build _msearch payload ----------
def build_msearch_payload(fields: List[str]) -> str:
    lines = []
    for f in fields:
        lines.append(json.dumps({}))    # header
        lines.append(json.dumps({
            "query": {"exists": {"field": f}},
            "size": 0
        }))
    return "\n".join(lines) + "\n"

# ---------- check which fields actually have data ----------
def filter_fields_that_exist(es_url: str, index_pattern: str, fields: List[str], batch: int) -> List[str]:
    url = f"{es_url.rstrip('/')}/{index_pattern}/_msearch"
    headers = {"Content-Type": "application/x-ndjson"}

    result = []

    for i in range(0, len(fields), batch):
        chunk = fields[i:i + batch]
        payload = build_msearch_payload(chunk)

        r = requests.post(url, data=payload, headers=headers, timeout=TIMEOUT, auth=AUTH)
        r.raise_for_status()
        resp = r.json()

        responses = resp.get("responses", [])
        for fname, rsp in zip(chunk, responses):
            # some ES versions respond differently; handle safely
            hits = rsp.get("hits", {})
            total = hits.get("total", 0)
            if isinstance(total, dict):
                total = total.get("value", 0)

            # also some responses might include "error" key for a given query - skip those
            if isinstance(total, int) and total > 0:
                result.append(fname)

    return result

# ---------- index listing & normalization ----------
COMMON_ALIAS = {
    "winlogbeat": "windows",
    "windows": "windows",
    "filebeat": "filebeat",
    "metricbeat": "metricbeat",
    "auditbeat": "auditbeat",
    "zeek": "zeek",
    "suricata": "suricata",
    "packetbeat": "packetbeat",
    "panw": "panw",
    "cisco": "cisco",
    "iis": "windows",
    "syslog": "syslog",
}

RE_DS_PREFIX = re.compile(r'^\.ds-')
RE_VERSION_SEG = re.compile(r'-(?:\d+\.)+\d+(?:-|$)')    # -8.14.3- or -8.14.3$
RE_DATE_PATTERNS = [
    re.compile(r'\{\%.*?\%\}'),                          # {%time%} or similar
    re.compile(r'\d{4}[.\-]\d{2}[.\-]\d{2}'),            # 2025.01.01 or 2025-01-01
    re.compile(r'^\*$'),                                 # wildcard
]

def list_indices(es_url: str, pattern: Optional[str] = None) -> List[str]:
    url = f"{es_url.rstrip('/')}/_cat/indices?h=index&format=json"
    r = requests.get(url, timeout=TIMEOUT, auth=AUTH)
    r.raise_for_status()
    arr = r.json()
    indices = [item["index"] for item in arr if "index" in item]
    if pattern:
        # simple contains match (fast). If you want glob semantics, change here.
        indices = [i for i in indices if pattern in i]
    return indices

def normalize_index_name(index: str) -> str:
    original = index
    name = index.lstrip('.')

    # datastream pattern: .ds-<name>-<version>-...
    if index.startswith(".ds-") or name.startswith("ds-"):
        # remove .ds- prefix then take tokens
        name_no_ds = RE_DS_PREFIX.sub('', index).lstrip('.')
        tokens = [t for t in re.split(r'[-_.]', name_no_ds) if t]
        if tokens:
            base = tokens[0].lower()
            base = RE_VERSION_SEG.sub('', base)
            return COMMON_ALIAS.get(base, base)

    # remove version segments like -8.14.3-
    name = RE_VERSION_SEG.sub('-', name)

    tokens = re.split(r'[-_.]', name)
    tokens = [t for t in tokens if t]
    if not tokens:
        return original

    # prefer an alphabetic token
    for t in tokens:
        tl = t.lower()
        if tl and not tl.isdigit() and tl not in ('ds',):
            if any(p.search(tl) for p in RE_DATE_PATTERNS):
                continue
            if tl in COMMON_ALIAS:
                return COMMON_ALIAS[tl]
            return tl

    # fallback
    base_lower = tokens[0].lower()
    base_clean = re.sub(r'[^a-zA-Z0-9]+$', '', base_lower)
    return COMMON_ALIAS.get(base_clean, base_clean or original)

def group_indices_by_normalized_name(es_url: str, pattern: Optional[str] = None) -> Dict[str, List[str]]:
    indices = list_indices(es_url, pattern)
    groups: Dict[str, List[str]] = {}
    for idx in indices:
        group = normalize_index_name(idx)
        groups.setdefault(group, []).append(idx)
    return groups

# ---------- main orchestration: run per group ----------
def process_all_groups(es_url: str):
    print("Listing indices and grouping...")
    groups = group_indices_by_normalized_name(es_url)

    final_out: Dict[str, List[str]] = {}

    for group_name, indices in groups.items():
        print(f"\nProcessing group '{group_name}' with {len(indices)} indices (sample: {indices[:3]})")

        # try pattern "<group>-*"
        tried_patterns = []
        success_fields = []

        pattern1 = f"{group_name}-*"
        tried_patterns.append(pattern1)

        try:
            print(f"  Trying mapping pattern: {pattern1}")
            fields = get_all_fields(es_url, pattern1)
            if not fields:
                # try datastream pattern ".ds-<group>-*"
                pattern2 = f".ds-{group_name}-*"
                tried_patterns.append(pattern2)
                print(f"  No fields found for {pattern1}, trying datastream pattern: {pattern2}")
                fields = get_all_fields(es_url, pattern2)

            # fallback: use comma-separated list of indices (limited size to avoid very long URL)
            if not fields:
                # limit to 100 indices to avoid huge request URL
                join_list = indices if len(indices) <= 100 else indices[:100]
                pattern3 = ",".join(join_list)
                tried_patterns.append(f"(indices list, {len(join_list)} items)")
                print(f"  Still empty => trying explicit indices list (first {len(join_list)})")
                fields = get_all_fields(es_url, pattern3)

            if not fields:
                print(f"  WARNING: No mapping/fields found for group {group_name} using patterns: {tried_patterns}")
                final_out[group_name] = []
                continue

            print(f"  Found {len(fields)} candidate fields (after mapping)")

            # filter fields that actually have data
            # reuse the same best-effort pattern to run _msearch; prefer pattern1 if it returned mapping
            # choose pattern_for_search in order of success above
            pattern_for_search = None
            for p in [pattern1, f".ds-{group_name}-*", ",".join(indices[:100])]:
                try:
                    # quick mapping test: if get_all_fields with p returns something, pick it
                    test_fields = get_all_fields(es_url, p)
                    if test_fields:
                        pattern_for_search = p
                        break
                except Exception:
                    continue
            if pattern_for_search is None:
                # fallback to indices list
                pattern_for_search = ",".join(indices[:100])

            print(f"  Using pattern for existence check: {pattern_for_search}")

            used_fields = filter_fields_that_exist(es_url, pattern_for_search, fields, BATCH)
            print(f"  {len(used_fields)} fields actually have data for group '{group_name}'")
            final_out[group_name] = sorted(used_fields)
        except requests.HTTPError as e:
            print(f"  HTTP error while processing {group_name}: {e}")
            final_out[group_name] = []
        except Exception as e:
            print(f"  Unexpected error while processing {group_name}: {e}")
            final_out[group_name] = []

    return final_out

if __name__ == "__main__":
    out = process_all_groups(ES_URL)
    print("\nResult summary:")
    print(json.dumps(out, indent=2, ensure_ascii=False))

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\nSaved output to {OUT_FILE}")
