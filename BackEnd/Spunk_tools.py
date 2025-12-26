from crewai.tools import tool
import json
import time
import os
import uuid
from typing import Dict, List, Any, Optional, Union
import splunklib.client
from dotenv import load_dotenv
load_dotenv()
def generate_unique_filename():
    """Generate a unique filename with timestamp and UUID."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    session_id = str(uuid.uuid4())[:8]
    return f"log_{timestamp}_{session_id}.json"

def get_splunk_connection() -> splunklib.client.Service:
    """
    Get a connection to the Splunk service.
    
    Returns:
        splunklib.client.Service: Connected Splunk service
    """
    try:
        # conf = load_config_splunk()
        username = os.getenv("SPLUNK_USERNAME", "admin")

        print(f"🔌 Connecting to Splunk at {os.getenv("SPLUNK_SCHEME")}://{os.getenv("SPLUNK_HOST")}:{os.getenv("SPLUNK_PORT")} as {username}")
        verify_ssl = os.getenv("VERIFY_SSL")
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() == "true"
        # Connect to Splunk
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

@tool("Get_index_SPLUNK")
def Get_index_SPLUNK() -> list:
    """
    Docstring for Get_index_SPLUNK
    Get list of indexes from Splunk schema JSON file.
    Returns:
    - List of index names
    """
    filepath = "./docs/Splunk_schema.json"
    with open (filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data_index = list(data["indexes"].keys())
    return data_index

@tool("Get_sources_fields_SPLUNK")
def Get_sources_fields_SPLUNK(index_name: str) -> dict:
    """
    Docstring for Get_sources_fields_SPLUNK
    Get list of sources and their fields for a given index from Splunk schema JSON file.
    Arguments:
    - index_name: name of the index
    Returns:
    - Dict of sources and their fields for the specified index
    """
    filepath = "./docs/Splunk_schema.json"
    with open (filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if index_name in data["indexes"]:
        return data["indexes"][index_name]["source"]
    else:
        return {}
    
@tool("Search_Splunk")
def search_splunk(search_query: str, max_results: int = 100):
    """
    Execute a Splunk search query and return the results.

    Args:
        search_query: The search query to execute
        earliest_time: Start time for the search (default: None, to be set by the query)
        latest_time: End time for the search (default: now)
        max_results: Maximum number of results to return (default: 100)

    Returns:
        List of search results
    """
    if not search_query.startswith("search "):
        search_query = f"search {search_query}"

    print(f"🔍 Executing Splunk search...{search_query}")
    if not search_query:
        raise ValueError("Search query cannot be empty")

    try:
        service = get_splunk_connection()

        # Create the search job
        kwargs_search = {
            "preview": False,
            "exec_mode": "blocking"
        }

        job = service.jobs.create(search_query, **kwargs_search)
        
        # Get the results
        result_stream = job.results(output_mode='json', count=max_results)
        results_data = json.loads(result_stream.read().decode('utf-8'))
        #save results to a file
        out = {"query": search_query}
        os.makedirs('logs', exist_ok=True)
        filename = generate_unique_filename()
        filepath = os.path.join('logs', filename)
        data = results_data.get('results', [])
        if not data:
            print("No results found for the query")
            return "No data found"
        else:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Search completed successfully. Results saved to {filepath}")
            out["saved_file"] = filepath
            return json.dumps(out, ensure_ascii=False)

    except Exception as e:
        raise ValueError(f"Search failed: {str(e)}")