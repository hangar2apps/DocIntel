# DocIntel — Document Intelligence Service

Upload PDFs. Ask questions. Get answers grounded in your documents with source citations.

DocIntel is a RAG (Retrieval-Augmented Generation) service that ingests PDF documents, splits them into searchable chunks, and answers natural language questions using only the content of your documents. No hallucination — every answer is grounded in the source material and includes citations.

---

## Architecture

```
Browser UI
      │ HTTP (JSON)
      ▼
Express Gateway (TypeScript, port 3000)
      │ gRPC (Protocol Buffers)
      ▼
RAG Service (Python, port 50051)
      │ SQL
      ▼
PostgreSQL + pgvector (port 5432)
      │
      ▼
OpenAI API (embeddings + chat completions)
```

**Why two backend services?**

The TypeScript gateway handles HTTP and serves as the public API. The Python service handles the AI/ML work — PDF parsing, text chunking, embedding generation, vector search, and LLM orchestration. Python has a stronger ecosystem for this (LangChain, pypdf, etc.). They communicate over gRPC, which gives type-safe contracts, binary serialization, and native streaming support.

**Why gRPC between services?**

REST would work fine here, but gRPC was chosen intentionally:
- The `.proto` file is a single source of truth for the API contract between services
- Binary serialization (Protocol Buffers) is smaller and faster than JSON
- Native streaming support — when token-by-token LLM streaming is added, gRPC handles it without bolting on WebSockets
- This mirrors the architecture used by Defense Unicorns' LeapfrogAI platform

**Why pgvector instead of a dedicated vector database?**

Fewer moving parts. Postgres is already in the stack for storing document metadata. pgvector adds vector search as an extension rather than introducing a whole new database (Pinecone, Weaviate, etc.). For document sets under 100k chunks, pgvector performs well and keeps the infrastructure simple.

---

## How It Works

### Ingestion
1. You upload a PDF
2. The Python service extracts the text using pypdf
3. Text is split into ~500 character chunks with 100 character overlap
4. Each chunk is converted to a 1536-dimension vector using OpenAI's text-embedding-3-small model
5. Chunks and their vectors are stored in PostgreSQL with pgvector

### Querying
1. You ask a question in plain English
2. The question is converted to a vector using the same embedding model
3. pgvector finds the 5 most similar chunks using cosine similarity
4. Those chunks are sent to GPT-4o-mini as context along with your question
5. The LLM generates an answer using only the provided context
6. The answer and source citations are returned to you

---

## Quick Start

### Prerequisites
- Docker Desktop installed and running
- An OpenAI API key

### Run it

```bash
git clone <repo-url>
cd docintel

export OPENAI_API_KEY="your-key-here"
docker compose up --build
```

Three containers start up:
- PostgreSQL + pgvector on port 5432
- Python RAG service on port 50051
- TypeScript gateway on port 3000

### Use it

**Option 1: Open the UI**

Open ui.html in your browser. Upload a PDF in the sidebar, then ask questions in the chat.

**Option 2: Use curl**

Upload a document:
```bash
curl -X POST http://localhost:3000/v1/documents \
  -H "Content-Type: application/json" \
  -d "{\"filename\": \"my-doc.pdf\", \"content\": \"$(base64 -i ./my-doc.pdf)\", \"doc_type\": \"policy\"}"
```

Ask a question:
```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"question": "What does this document say about X?"}'
```

List ingested documents:
```bash
curl http://localhost:3000/v1/documents
```

### Stop it

```bash
docker compose down
```

---

## API Reference

### POST /v1/documents
Upload and ingest a PDF document.

Request:
```json
{
  "filename": "my-doc.pdf",
  "content": "<base64-encoded PDF>",
  "doc_type": "policy"
}
```

Response:
```json
{
  "document_id": "5a89de7e-43d9-4955-97e6-0c384504ee55",
  "chunks_created": 150,
  "status": "complete"
}
```

### POST /v1/chat/completions
Ask a question across ingested documents.

Request:
```json
{
  "question": "When are health assessments required?",
  "max_chunks": 5
}
```

Response:
```json
{
  "answer": "Health assessments are required at specific intervals...",
  "sources": [
    {
      "document_name": "DODI-6490.pdf",
      "chunk_text": "relevant text from the document...",
      "similarity_score": 0.7263
    }
  ],
  "done": true
}
```

### GET /v1/documents
List all ingested documents.

Response:
```json
[
  {
    "document_id": "5a89de7e-43d9-4955-97e6-0c384504ee55",
    "filename": "DODI-6490.pdf",
    "doc_type": "policy",
    "chunk_count": 150,
    "ingested_at": ""
  }
]
```

---

## Project Structure

```
docintel/
├── docker-compose.yml          # Runs all three services
├── Dockerfile                  # Python RAG service container
├── docintel.proto              # gRPC service contract
├── docintel_pb2.py             # Generated message classes (don't edit)
├── docintel_pb2_grpc.py        # Generated service stubs (don't edit)
├── server.py                   # Python gRPC server (RAG pipeline)
├── requirements.txt            # Python dependencies
├── ui.html                     # Browser interface
├── gateway/
│   ├── Dockerfile              # TypeScript gateway container
│   ├── server.ts               # Express HTTP server + gRPC client
│   ├── docintel.proto          # Copy of the proto (for Node client)
│   ├── package.json
│   └── tsconfig.json
├── ingest.py                   # Standalone ingestion script (reference)
└── query.py                    # Standalone query script (reference)
```

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Gateway | TypeScript, Express | HTTP API, familiar ecosystem |
| RAG Service | Python, LangChain | Best LLM/ML tooling ecosystem |
| Communication | gRPC, Protocol Buffers | Type-safe contracts, streaming, binary serialization |
| Database | PostgreSQL + pgvector | Vector search without a separate database |
| Embeddings | OpenAI text-embedding-3-small | 1536 dimensions, good balance of quality and cost |
| LLM | GPT-4o-mini | Fast, cheap, good enough for grounded Q&A |
| Containers | Docker, Docker Compose | Portable, reproducible, one-command setup |

---

## What I'd Change With More Time

**Token-by-token streaming.** Right now the LLM generates the full answer before returning it. With gRPC streaming wired up (the proto already supports it), the answer would appear word-by-word in the UI like ChatGPT.

**Better chunking.** The current splitter cuts on character count. A smarter approach would split on section headings, paragraph boundaries, or semantic meaning — preserving the document's logical structure.

**Document metadata.** Track doc_type, ingested_at, and page numbers per chunk so citations can reference specific pages.

**Authentication.** API key or token-based auth on the gateway. Required for any real deployment.

**Self-hosted models.** Replace OpenAI with locally-running models (via LeapfrogAI or Ollama) so no data leaves the environment. Critical for classified or airgapped deployments.

**Re-ranking.** After vector search retrieves the top chunks, run a second pass with a cross-encoder model to re-rank by relevance. Improves answer quality significantly.

**Helm chart and Zarf package.** Package for Kubernetes deployment via UDS. The Dockerfiles are ready — it's just writing the K8s manifests and bundling with Zarf for airgapped delivery.