# Setup
- create python virtual environment
    - python3 -m venv venv
    - source venv/bin/activate
- using Open AI API
    - https://platform.openai.com/api-keys
- using local postgres in docker container (this will be our database)
    - make sure docker desktop is running then run:
        - docker run -d \
            --name docintel-db \
            -e POSTGRES_PASSWORD=docintel \
            -e POSTGRES_DB=docintel \
            -p 5433:5432 \
            pgvector/pgvector:pg16
        - this gets Postgres 16 with pgvector extension pre-installed, accessible at localhost:5433
        - verify with `docker ps`
- install dependencies
    - pip install langchain langchain-community langchain-openai langchain-text-splitters pgvector psycopg2-binary pypdf tiktoken
    - dependency breakdown:
        - langchain — orchestration framework for LLM apps. Connects the pieces together.
        - langchain-openai — OpenAI-specific wrappers for embeddings and chat completions
        - langchain-text-splitters — utilities for chunking text intelligently
        - pgvector — Python client for the pgvector Postgres extension
        - psycopg2-binary — Python Postgres driver
        - pypdf — reads PDF files into text
        - tiktoken — OpenAI's tokenizer, so you can chunk by token count instead of character count
- set Open AI API key
    - export OPENAI_API_KEY="0Wjnysh_8jAAk9ju0wIQyMaV03vhEdHxXvzwPEdIiPo9K6EHZUGr3ZchzvfhBjVZqIyQXNmvxT3BlbkFJ5PY8mGKUZ1L70RU42OrC8Azv2_s1RLNEdfyc2WGTQfpaktOXwsexPRGLpxLEX3MHHMN2WVz1wA"

# Build RAG pipeline
FLOW: PDF → load text → split into chunks → embed each chunk → store in Postgres → done

- Ingest
    - create ingest.py to load PDF and extract the text
- Chunk
    - add chunk logic to ingest.py after loader
        - Chunk size — how many tokens per chunk? Too small and you lose context. Too big and you dilute the signal. 500 tokens is a solid starting point for policy documents.
        - Overlap — chunks should overlap slightly so you don't cut a sentence in half and lose meaning. 100 tokens is typical.
- Embed
    - add embedding logic to ingest.py after chunk logic
    - converts each chunk from human-readable text into a vector — a list of numbers that represents the meaning of that text
- Store 
    - add logic to ingest.py to store embeddings in pgvector 
    - Column decisions worth understanding:
        - content — the actual text, for displaying in citations
        - source — filename, so you can trace back to the original document
        - page_number — for citations ("see page 12")
        - chunk_index — ordering, so you could reconstruct surrounding context if needed
        - embedding vector(1536) — the pgvector column type, must match the embedding dimensions

# Query
    User question → embed the question → similarity search in pgvector → top chunks → send to LLM with context → answer
- Ingest
    - create query.py
- Embed
    - create embeddings of query
- Similarity Search
    - compare document embeddings to query
- Prompt
    - send context(content from db) and query to LLM
    - print LLM response
