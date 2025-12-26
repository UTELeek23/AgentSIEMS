import splunklib.client
from typing import Dict, Any
import json
from dotenv import load_dotenv
import os
load_dotenv()


def get_splunk_connection() -> splunklib.client.Service:
    """
    Get a connection to the Splunk service.
    
    Returns:
        splunklib.client.Service: Connected Splunk service
    """
    try:
        # conf = load_config_splunk()
        username = os.getenv("SPLUNK_USERNAME", "admin")
        
        print(f"🔌 Connecting to Splunk at {os.getenv('SPLUNK_SCHEME')}://{os.getenv('SPLUNK_HOST')}:{os.getenv('SPLUNK_PORT')} as {username}")
        verify_ssl = os.getenv("VERIFY_SSL")
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() == "true"

        service = splunklib.client.connect(
            host=os.getenv("SPLUNK_HOST"),
            port=os.getenv("SPLUNK_PORT"),
            username=username,
            password=os.getenv("SPLUNK_PASSWORD"),
            scheme=os.getenv("SPLUNK_SCHEME"),
            verify=verify_ssl
        )
        
        print(f"Connected to Splunk successfully")
        return service
    except Exception as e:
        print(f"Failed to connect to Splunk: {str(e)}")
        raise


def get_indexes_and_sources(timerange: str) -> Dict[str, Any]:
    """
    Get a list of all indexes and their sources.

    This endpoint gathers:
    - All indexes
    - All sources inside each index
    - Event counts for each source

    Returns:
        Dict[str, Any]
    """
    try:
        service = get_splunk_connection()
        print("Fetching indexes and sources...")
        
        # Get list of indexes
        indexes = [index.name for index in service.indexes]
        print(f"Found {len(indexes)} indexes")
        
        # Search for sources across all indexes
        search_query = """
        | tstats count WHERE index=* BY index, source
        | stats count BY index, source
        | sort - count
        """
        
        kwargs_search = {
            "earliest_time": timerange,
            "latest_time": "now",
            "preview": False,
            "exec_mode": "blocking"
        }
        
        print("Executing search for sources...")
        job = service.jobs.create(search_query, **kwargs_search)
        
        result_stream = job.results(output_mode='json')
        results_data = json.loads(result_stream.read().decode('utf-8'))
        
        # Process results
        sources_by_index = {}
        for result in results_data.get('results', []):
            index = result.get('index', '')
            source = result.get('source', '')
            count = result.get('count', '0')
            
            if index not in sources_by_index:
                sources_by_index[index] = []
            
            sources_by_index[index].append({
                'source': source,
                'count': count
            })
        
        response = {
            'indexes': indexes,
            'sources': sources_by_index,
            'metadata': {
                'total_indexes': len(indexes),
                'total_sources': sum(len(s) for s in sources_by_index.values()),
                'search_time_range': timerange,
            }
        }
        
        print(f" Successfully retrieved indexes and sources")
        return response
        
    except Exception as e:
        print(f" Error getting indexes and sources: {str(e)}")
        raise



def get_fields(index: str, source: str, time_range: str) -> str:
    """
    Retrieve a list of fields available for an index + source.
    """
    try:
        fields = []
        service = get_splunk_connection()

        # CHANGED: sourcetype -> source
        query = f'search index="{index}" source="{source}" earliest={time_range} | head 100 | fieldsummary'
        print(f"Executing Splunk query: {query}")

        job = service.jobs.create(query, exec_mode="blocking")
        results_stream = job.results(output_mode="json", count=0)
        results_data = json.loads(results_stream.read().decode("utf-8"))
        
        if not results_data.get("results"):
            return json.dumps({"fields": []})
        else:
            for result in results_data["results"]:
                fields.append(result.get("field", ""))
            
            response = {
                'fields': fields,
            }
            return json.dumps(response, indent=2)
    except Exception as e:
        print(f" Error in get_fields: {str(e)}")
        return json.dumps({"fields": []})



def build_schema_json(time_range: str = "-7d", save_path: str = "docs/splunk_schema.json") -> Dict[str, dict]:
    try:
        print("🚀 Fetching indexes and sources...")
        index_data = get_indexes_and_sources(time_range)
        indexes = index_data.get("indexes", [])
        sources_by_index = index_data.get("sources", {})

        schema = {"indexes": {}}

        total_count = sum(len(v) for v in sources_by_index.values())
        print(f"Total index/source combinations to process: {total_count}")

        processed = 0

        for index in indexes:
            schema["indexes"][index] = {"source": {}}
            sources = sources_by_index.get(index, [])

            for src_obj in sources:
                source = src_obj["source"]
                processed += 1
                print(f"Processing {processed}/{total_count}: {index}/{source}")

                try:
                    result = get_fields(index, source, time_range)
                    field_data = json.loads(result)

                    schema["indexes"][index]["source"][source] = {
                        "fields": field_data.get("fields", [])
                    }

                except Exception as e:
                    print(f"⚠️ Error for {index}/{source}: {str(e)}")
                    schema["indexes"][index]["source"][source] = {"fields": []}

        # -------------------------------
        # 🚨 REMOVE EMPTY INDEXES & SOURCES
        # -------------------------------
        cleaned_indexes = {}

        for index, idx_obj in schema["indexes"].items():
            sources = idx_obj.get("source", {})

            # remove sources with zero fields
            cleaned_sources = {
                src: data for src, data in sources.items()
                if data.get("fields") and len(data.get("fields")) > 0
            }

            if cleaned_sources:
                cleaned_indexes[index] = {"source": cleaned_sources}

        schema["indexes"] = cleaned_indexes

        # Save file
        with open(save_path, "w") as f:
            json.dump(schema, f, indent=2)

        print(f"✅ Schema saved to {save_path}")
        return schema

    except Exception as e:
        print(f"❌ Failed to build schema: {str(e)}")
        return {}


if __name__ == "__main__":
    build_schema_json(time_range="-30d")