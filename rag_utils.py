import os
import logging
from pathlib import Path
from typing import List
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

def create_qdrant_collection(collection_name: str):
    """Qdrant mein ek nayi almari (collection) banate hain vectors rakhne ke liye"""
    client = QdrantClient(url=QDRANT_URL)
    
    # Dekh lete hain pehle se toh nahi hai
    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)
    
    if not exists:
        logger.info(f"Nayi Qdrant collection ban rahi hai: {collection_name}")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
        )
        return True
    return False

def index_pdfs_to_collection(collection_name: str, file_paths: List[str]):
    """PDFs ko read karke aur tukde-tukde karke Qdrant mein daalte hain (Gyan Ka Sagar)"""
    if not GOOGLE_API_KEY:
        raise ValueError("Bhai, GOOGLE_API_KEY toh daal do!")
        
    embedding_model = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    
    all_chunks = []
    for file_path in file_paths:
        logger.info(f"File index ho rahi hai: {file_path}")
        loader = PyPDFLoader(file_path=file_path)
        docs = loader.load()
        chunks = text_splitter.split_documents(docs)
        all_chunks.extend(chunks)
        
    if not all_chunks:
        logger.warning("PDF mein kuch kaam ka nahi mila bhai.")
        return 0
        
    logger.info(f"Uploading {len(all_chunks)} chunks to: {collection_name}")
    
    QdrantVectorStore.from_documents(
        documents=all_chunks,
        embedding=embedding_model,
        url=QDRANT_URL,
        collection_name=collection_name
    )
    
    return len(all_chunks)

def list_qdrant_collections():
    """Saari collections ki list nikaalte hain"""
    client = QdrantClient(url=QDRANT_URL)
    collections = client.get_collections().collections
    return [c.name for c in collections]
