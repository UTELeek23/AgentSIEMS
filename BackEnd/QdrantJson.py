import os
from qdrant_client import QdrantClient
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from dotenv import load_dotenv
from qdrant_client.models import VectorParams, Distance
from qdrant_client.models import PointStruct
import uuid
import requests
load_dotenv()
# print(os.getenv("JINA_API_KEY"))
def get_jina_embedding(text):
    url = 'https://api.jina.ai/v1/embeddings'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.getenv("JINA_API_KEY")
    }
    data = {
        "model": "jina-embeddings-v4",
        "task": "retrieval.passage",
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

# Setup Qdrant client
COLLECTION_NAME = "ELK-doc-v1"
doc_converter = DocumentConverter(allowed_formats=[InputFormat.JSON_DOCLING])  # Allow PDF format
qdrant_url = "http://192.168.111.162:6333"  # Replace with your Qdrant URL
# qdrant_api_key = os.getenv("QDRANT_API_KEY")
client = QdrantClient(url=qdrant_url)
# client.set_model("sentence-transformers/all-MiniLM-L6-v2")

# Define the folder where PDFs are stored
pdf_folder = "./docs/"
# Initialize documents and metadata lists
documents, metadatas = [], []
points = []
# Loop through all PDFs in the folder and process them
for filename in os.listdir(pdf_folder):
    if filename.endswith(".pdf"):
        pdf_path = os.path.join(pdf_folder, filename)
        print(f"Processing {pdf_path}")

        result = doc_converter.convert(pdf_path)

        # Chunk the converted document
        for chunk in HybridChunker().chunk(result.document):
            print("chunk", chunk)
            # embedding_result = openai_client.embeddings.create(
            #     input=chunk.text, model=embedding_model
            # )
            vector = get_jina_embedding(chunk.text)
            documents.append(chunk.text)
            metadatas.append(chunk.meta.export_json_dict())
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": chunk.text,
                        "metadata": chunk.meta.export_json_dict(),
                    },
                )
            )
print("points", points)
client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=2048, distance=Distance.COSINE),
)
client.upsert(collection_name=COLLECTION_NAME, points=points)