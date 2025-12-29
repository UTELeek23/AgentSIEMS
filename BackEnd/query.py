import requests, json
import os
from dotenv import load_dotenv
from crewai.tools import tool
import logging
import sys
from datetime import datetime
from qdrant_client import QdrantClient

# logging.basicConfig(level=logging.INFO)

load_dotenv()
ES_URL = os.getenv("ELK_HOST", "http://localhost:9200") 
TIMEOUT = 30

def get_jina_embedding(text):
    url = 'https://api.jina.ai/v1/embeddings'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.getenv("JINA_API_KEY")
    }
    data = {
        "model": "jina-embeddings-v4",
        "task": "retrieval.query",
        "input": text
    }

    response = requests.post(url, json=data, headers=headers)
    # Parse the JSON response and extract the embedding values
    embedding_data = response.json()
    # Extract the actual embedding vector from the response
    if 'data' in embedding_data and len(embedding_data['data']) > 0:
        return embedding_data['data'][0]['embedding']
    else:
        raise ValueError("Failed to get valid embedding from Jina API")

@tool("Get_index_ELK")
def Get_index_ELK() -> list:
    """
    Docstring for Get_index_ELK
    Get list of indexes from ELK schema JSON file.
    Returns:
    - List of index names
    """
    filepath = "./docs/ELK_schema.json"
    with open (filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data_index = list(data["indexes"].keys())
    return data_index

@tool("Get_fields_index_ELK")
def Get_fields_index_ELK(index_name: str) -> list:
    """
    Docstring for Get_fields_index_ELK
    Get list of fields for a given index from ELK schema JSON file.
    Arguments:
    - index_name: name of the index
    Returns:
    - List of field names for the specified index
    """
    filepath = "./docs/ELK_schema.json"
    with open (filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    fields_index = data["indexes"].get(index_name, {})
    return fields_index

@tool("Query_Elasticsearch")
def Query_Elasticsearch(index_pattern: str, query_body: dict, size=10, from_=0, sort=None,
             only_source=False, source_includes=None) -> dict:
    """
    Run an Elasticsearch search query.

    Rules for index_pattern normalization (simple, deterministic):
      - If index_pattern contains a comma, treat it as multiple patterns and normalize each piece.
      - If a piece already contains '*' anywhere, leave it as-is (do not append).
      - If a piece ends with '-*', leave it as-is.
      - If a piece contains 'filebeat' (case-insensitive), replace that piece with '.ds-filebeat-*'.
      - Otherwise, append '-*' to the piece.

    Behavior:
      - Do NOT attempt to check index existence on the cluster.
      - If results exist, save the full ES response to logs/elk_log_{YYYYmmddTHHMMSS}.json.
      - Return a dict {"index_pattern": <used_pattern>, "query_body": <query_body>} (and "saved_file" if saved).
    """
    try:
        print(f"Running Elasticsearch query on index pattern: {index_pattern}")
        print(f"Query body: {json.dumps(query_body)}")

        # Normalize index pattern pieces (comma separated handling)
        def normalize_piece(piece: str) -> str:
            p = piece.strip()
            if not p:
                return p
            low = p.lower()
            # if it already contains wildcard anywhere, keep as-is
            if "*" in p:
                # special-case: if it's 'filebeat' with wildcard already, still map to .ds-filebeat-*?
                # follow rule: if contains 'filebeat' anywhere, prefer datastream form
                if "filebeat" in low:
                    return ".ds-filebeat-*"
                return p
            # if piece contains 'filebeat' token -> set datastream pattern
            if "filebeat" in low:
                return ".ds-filebeat-*"
            # if already endswith '-*' (should be covered by '*' check but keep safe)
            if p.endswith("-*"):
                return p
            # otherwise append '-*'
            return p + "-*"

        # if comma-separated list, normalize each part
        parts = [part for part in index_pattern.split(",")]
        normalized_parts = [normalize_piece(part) for part in parts if part.strip() != ""]

        # join back; if only one part, used_pattern is that part (no trailing comma)
        used_pattern = ",".join(normalized_parts) if normalized_parts else index_pattern

        print(f"Normalized index pattern to: {used_pattern}")

        # build request
        url = f"{ES_URL.rstrip('/')}/{used_pattern}/_search"
        params = {}
        if only_source:
            params["filter_path"] = "hits.hits._source"

        body = {
            "query": query_body,
            "size": size,
            "from": from_
        }
        if sort:
            body["sort"] = sort
        if source_includes:
            body["_source"] = {"includes": source_includes}

        headers = {"Content-Type": "application/json"}
        
        print("=" * 60)
        print("🔍 ELASTICSEARCH QUERY EXECUTION")
        print("=" * 60)
        print(f"📌 URL: {url}")
        print(f"📌 Index Pattern: {used_pattern}")
        print(f"📌 Query Size: {size}")
        print(f"📌 Query Body:")
        print(json.dumps(query_body, indent=2))
        print("-" * 60)
        
        resp = requests.post(url, params=params, data=json.dumps(body), headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        # Get total hits for logging
        hits_total = data.get("hits", {}).get("total", {})
        if isinstance(hits_total, dict):
            total_count = hits_total.get("value", 0)
        else:
            total_count = hits_total or 0
        
        print(f"✅ Response received!")
        print(f"📊 Total Hits: {total_count}")
        print(f"⏱️  Took: {data.get('took', 'N/A')} ms")
        print("-" * 60)

        # check results presence
        has_results = False
        if only_source:
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                for h in hits:
                    if h.get("_source") is not None:
                        has_results = True
                        break
        else:
            hits_info = data.get("hits", {}).get("total")
            if isinstance(hits_info, dict):
                total = hits_info.get("value", 0)
            else:
                try:
                    total = int(hits_info or 0)
                except Exception:
                    total = 0
            if total > 0:
                has_results = True

        # save response if have results
        saved_file = None
        if has_results:
            try:
                os.makedirs("logs", exist_ok=True)
                ts = datetime.now().strftime("%Y%m%dT%H%M%S")
                filename = f"logs/elk_log_{ts}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"Saved Elasticsearch response to {filename}")
                saved_file = filename
            except Exception as e:
                print(f"Warning: failed to save ES response to logs: {e}")

        out = {"index_pattern": used_pattern, "query": query_body}
        if saved_file:
            out["saved_file"] = saved_file
            print(f"💾 Results saved to: {saved_file}")
        else:
            print("⚠️  No results found - file not saved")
        print("=" * 60)
        print(f"📤 Output: {json.dumps(out, ensure_ascii=False)}")
        print("=" * 60)
        return json.dumps(out, ensure_ascii=False)

    except requests.HTTPError as e:
        print(f"HTTP error executing Query_Elasticsearch: {e}")
        return {"error": "http_error", "detail": str(e), "index_pattern": used_pattern, "query_body": query_body}
    except Exception as e:
        print(f"Error executing Query_Elasticsearch: {e}")
        return {"error": "exception", "detail": str(e), "index_pattern": index_pattern, "query_body": query_body}

@tool("QdrantSearch_ELK")
def QdrantSearch_ELK(query_text: str, top_k: int = 3) -> dict:
    """
    Perform a vector search on Qdrant for ELK documents based on the query text.

    Arguments:
    - query_text: The text query to search for.
    - top_k: The number of top results to return.

    Returns:
    - A dictionary containing the search results from Qdrant.
    """
    COLLECTION_NAME = "ELK-doc-v1"
    qdrant_url = "http://192.168.111.162:6333"  # Replace with your Qdrant URL
    # qdrant_api_key = os.getenv("QDRANT_API_KEY")
    client = QdrantClient(url=qdrant_url)
    q = get_jina_embedding(query_text)
    try:
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=q,
            limit=top_k,
            score_threshold=0.35
        )
        return results
    except TypeError:
        # fallback signature difference
        results = client.query_points(collection_name=COLLECTION_NAME, query=q, limit=top_k)
        return results
    except Exception as e:
        print(f"[ERROR] Error during Qdrant search: {e}.")
        return {"error": "qdrant_search_error", "detail": str(e)}
# print(Get_fields_index_ELK("windows"))
# result_sources = Query_Elasticsearch(
#     index_pattern=".ds-filebeat",
#     query_body={
#   "bool": {
#     "must": [
#       {
#         "term": {
#           "destination.ip": "192.168.111.162"
#         }
#       },
#       {
#         "term": {
#           "destination.port": 3000
#         }
#       },
#       {
#         "range": {
#           "@timestamp": {
#             "gte": "now-5h",
#             "lte": "now"
#           }
#         }
#       }
#     ]
#   }
# }
# ,
#     only_source=True, size=100
# )



# print(result_sources)
# # with open("es_query_result.json", "w", encoding="utf-8") as f:
#     json.dump(result_sources, f, indent=2, ensure_ascii=False)

# # result_sources là list các dict chỉ chứa _source
# print(json.dumps(result_sources, indent=2, ensure_ascii=False))
