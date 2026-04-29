import os
import psycopg2
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
load_dotenv()

# LOAD

loader = PyPDFLoader("DODI-6490.pdf")
pages = loader.load()

print(f"Loaded {len(pages)} pages")
print(pages[0].page_content[:500])  # peek at the first page

# CHUNK

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
    length_function=len,
)

chunks = splitter.split_documents(pages)

print(f"Created {len(chunks)} chunks from {len(pages)} pages")
print(f"\n--- Chunk 0 ---\n{chunks[0].page_content}")
print(f"\n--- Chunk 1 ---\n{chunks[1].page_content}")

# EMBED

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
# Embed just one chunk to see what comes back
test_embedding = embeddings.embed_query(chunks[0].page_content)

print(f"Embedding dimensions: {len(test_embedding)}")
print(f"First 10 values: {test_embedding[:10]}")

# STORE

# Connect to your local pgvector instance
conn = psycopg2.connect(
    host="localhost",
    port=5433,
    database="docintel",
    user="postgres",
    password="docintel"
)
conn.autocommit = True
cur = conn.cursor()

# Enable pgvector and create the table
cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
cur.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id SERIAL PRIMARY KEY,
        content TEXT NOT NULL,
        source VARCHAR(255),
        page_number INTEGER,
        chunk_index INTEGER,
        embedding vector(1536)
    )
""")

# Clear old data if re-running
cur.execute("DELETE FROM document_chunks")

# Embed all chunks and insert
print(f"Embedding and storing {len(chunks)} chunks...")

for i, chunk in enumerate(chunks):
    embedding = embeddings.embed_query(chunk.page_content)
    cur.execute(
        """INSERT INTO document_chunks 
           (content, source, page_number, chunk_index, embedding) 
           VALUES (%s, %s, %s, %s, %s)""",
        (
            chunk.page_content,
            chunk.metadata.get("source", "unknown"),
            chunk.metadata.get("page", 0),
            i,
            str(embedding)
        )
    )
    if (i + 1) % 25 == 0:
        print(f"  ...{i + 1}/{len(chunks)}")

print(f"Done. Stored {len(chunks)} chunks.")

cur.close()
conn.close()