# Forward Deployed AI Engineer — 1-Week Technical Prep

> Goal: Be ready for an async take-home project and an engineer-led interview within ~7 days.
> Approach: Build ONE project that exercises the core skills from the job posting. Not DRP, but close enough to get hackathon reps too.

---

## 0. Key Intel: LeapfrogAI

Defense Unicorns already has an open-source AI platform called **LeapfrogAI** (github.com/defenseunicorns/leapfrogai). This is almost certainly what the Forward Deployed AI Engineer role works with or alongside. Critical detail: **LeapfrogAI uses gRPC internally** — the API server communicates with LLM backends and embedding models via gRPC, and exposes an OpenAI-compatible HTTP API to users. It also uses vector databases for RAG.

This means: whatever you build should follow this same architectural pattern. HTTP API on the outside, gRPC between internal services, vector search for RAG. That's not a guess — it's how their actual product works.

---

## 1. The Practice Project: **DocIntel**

A document intelligence service that ingests PDFs, stores them as embeddings, and answers questions about them with citations. Domain-agnostic but naturally applicable to DoD policy documents, medical regulations, or any dense reference material.

### Why this project

- Exercises RAG end-to-end (the #1 skill in the job description)
- Uses gRPC between services (matches LeapfrogAI's internal architecture)
- Uses Python for AI + TypeScript for the API layer (matches the job's required languages)
- Containerizable (Docker, ready for K8s)
- Small enough to build in a week, complex enough to be interesting
- Easily repurposed: swap in DoD health policy docs and it becomes DRP's policy assistant

### Architecture

```
Client (curl / simple web UI)
        │
        │ HTTP (OpenAI-compatible API format)
        ▼
┌──────────────────────────────┐
│   API Gateway (TypeScript)    │
│   Express / Fastify           │
│                                │
│   POST /v1/documents          │  ← upload + ingest
│   POST /v1/chat/completions   │  ← query with RAG
│   GET  /v1/documents          │  ← list ingested docs
└──────────┬───────────────────┘
           │ gRPC
           ▼
┌──────────────────────────────┐
│   RAG Service (Python)        │
│   FastAPI + gRPC server       │
│                                │
│   IngestDocument()            │  ← chunk, embed, store
│   Query()                     │  ← retrieve + generate (streaming)
│   ListDocuments()             │  ← metadata
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│   PostgreSQL + pgvector       │
│                                │
│   documents (metadata)        │
│   chunks (text + embedding)   │
└──────────────────────────────┘
```

### .proto definition

```protobuf
syntax = "proto3";

package docintel;

service DocumentIntelligence {
  // Ingest a document: chunk it, embed it, store it
  rpc IngestDocument (IngestRequest) returns (IngestResponse);

  // Query across ingested documents with RAG
  rpc Query (QueryRequest) returns (stream QueryResponse);

  // List ingested documents
  rpc ListDocuments (ListRequest) returns (DocumentList);
}

message IngestRequest {
  string filename = 1;
  bytes content = 2;        // raw PDF bytes
  string doc_type = 3;      // optional category tag
}

message IngestResponse {
  string document_id = 1;
  int32 chunks_created = 2;
  string status = 3;
}

message QueryRequest {
  string question = 1;
  repeated string document_ids = 2;   // empty = search all
  int32 max_chunks = 3;               // top-k for retrieval
}

message QueryResponse {
  string token = 1;                   // streamed token
  repeated SourceChunk sources = 2;   // populated on final message
  bool done = 3;
}

message SourceChunk {
  string document_id = 1;
  string document_name = 2;
  string chunk_text = 3;
  float similarity_score = 4;
}

message ListRequest {
  string doc_type = 1;    // optional filter
}

message DocumentList {
  repeated DocumentMeta documents = 1;
}

message DocumentMeta {
  string document_id = 1;
  string filename = 2;
  string doc_type = 3;
  int32 chunk_count = 4;
  string ingested_at = 5;
}
```

---

## 2. Day-by-Day Plan

### Day 1: RAG pipeline in Python (no gRPC yet, just get it working)

**Goal:** Ingest a PDF, chunk it, embed it, store in pgvector, query it.

- Set up a Python project with `uv` or `pip`
- Install: `langchain`, `langchain-community`, `pgvector`, `psycopg2`, `pypdf`
- Spin up Postgres with pgvector: `docker run -e POSTGRES_PASSWORD=dev -p 5432:5432 pgvector/pgvector:pg16`
- Write a script that:
  1. Reads a PDF (use any ~20 page document — a public DoD instruction is perfect practice)
  2. Splits it into chunks (~500 tokens each, 100 token overlap)
  3. Embeds each chunk using OpenAI `text-embedding-3-small` (or Anthropic if preferred)
  4. Stores chunks + embeddings in pgvector
  5. Takes a question, embeds it, runs similarity search, retrieves top-5 chunks
  6. Sends chunks + question to an LLM, gets an answer with source citations
- Test with 3–5 questions. Verify citations point to real sections.

**Deliverable:** Working CLI — `python query.py "What dental class blocks deployment?"` → answer + source

---

### Day 2: Wrap RAG in a gRPC server

**Goal:** The Python RAG pipeline becomes a gRPC service.

- Install: `grpcio`, `grpcio-tools`
- Write `docintel.proto` (use the definition above)
- Generate Python stubs: `python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. docintel.proto`
- Implement `DocumentIntelligenceServicer`:
  - `IngestDocument` — takes PDF bytes, runs the chunking/embedding pipeline
  - `Query` — runs retrieval, then streams LLM response token by token
  - `ListDocuments` — returns metadata from the documents table
- Test with `grpcurl` or a quick Python client script

**Deliverable:** Running gRPC server on port 50051. Can ingest and query via gRPC client.

---

### Day 3: TypeScript API gateway

**Goal:** An HTTP API that proxies to the Python gRPC service.

- Set up Express/Fastify project in TypeScript
- Install: `@grpc/grpc-js`, `@grpc/proto-loader`
- Load the same `.proto` file, create a gRPC client
- Implement HTTP endpoints:
  - `POST /v1/documents` — accepts multipart file upload, calls `IngestDocument` via gRPC
  - `POST /v1/chat/completions` — accepts JSON body, calls `Query` via gRPC, streams response back as SSE (Server-Sent Events)
  - `GET /v1/documents` — calls `ListDocuments` via gRPC
- Make the API format loosely match OpenAI's (this is what LeapfrogAI does — makes migration easy)

**Deliverable:** `curl -X POST http://localhost:3000/v1/chat/completions -d '{"question":"..."}'` → streamed answer

---

### Day 4: Containerize everything

**Goal:** `docker compose up` runs the full stack.

- Write `Dockerfile` for the Python RAG service (multi-stage: builder + runtime)
- Write `Dockerfile` for the TypeScript API gateway
- Write `docker-compose.yml` with three services: postgres (pgvector), rag-service, api-gateway
- Ensure the gRPC connection works between containers (service names as hostnames)
- Test: `docker compose up`, then curl the API gateway

**Deliverable:** One command spins up the entire system. Anyone can clone and run it.

---

### Day 5: Polish, documentation, and a simple UI

**Goal:** Make it presentable for an async submission.

- Write a solid `README.md`:
  - What it does (one paragraph)
  - Architecture diagram (ASCII or Mermaid)
  - How to run (`docker compose up`)
  - How to ingest a document (`curl` example)
  - How to query (`curl` example)
  - Design decisions and tradeoffs (why gRPC, why pgvector, why streaming)
  - What you'd change with more time
- Optional: simple HTML page that lets you upload a PDF and ask questions (doesn't need to be pretty, just functional)
- Clean up code: consistent naming, error handling, type safety, comments where non-obvious

**Deliverable:** A GitHub repo you'd be proud to share.

---

### Day 6: Study for the live interview

**Goal:** Be ready to walk through your project and answer depth questions.

Topics to prep:

**RAG depth:**
- What's the difference between naive RAG and advanced RAG (re-ranking, query decomposition, HyDE)?
- How would you evaluate RAG quality? (relevance, faithfulness, answer correctness)
- What happens when chunks are too big? Too small?
- How would you handle a document update (re-ingest, versioning)?

**gRPC depth:**
- Why gRPC over REST for internal services? (binary serialization, streaming, type safety, code generation)
- What's Protocol Buffers? How does it compare to JSON?
- Unary vs. server-streaming vs. client-streaming vs. bidirectional — when to use each?
- How does gRPC handle errors? (status codes, metadata)

**Containerization depth:**
- Multi-stage Docker builds — why?
- How would you deploy this to Kubernetes? (deployments, services, configmaps)
- What would a Helm chart look like for this project?
- How would you handle secrets (API keys) in a container?

**Defense Unicorns specific:**
- How does LeapfrogAI work? (OpenAI-compatible API, gRPC to model backends, self-hosted LLMs)
- How would this project be packaged with Zarf for an airgapped deployment?
- What changes if you can't call OpenAI's API? (self-hosted models via LeapfrogAI, Ollama, vLLM)

**The "why" questions (these are coming):**
- "Why did you choose pgvector over a dedicated vector DB like Pinecone or Weaviate?"
  → Fewer moving parts. Postgres is already in the stack. pgvector is good enough for <100k documents. In a DoD environment, fewer dependencies = easier ATO.
- "Why a separate Python service instead of doing everything in TypeScript?"
  → Python has the strongest LLM/ML ecosystem (LangChain, LlamaIndex, sentence-transformers). TypeScript is better for HTTP APIs and frontend. Polyglot services connected by gRPC is a clean separation.
- "How would you handle PHI/sensitive data in this system?"
  → Self-hosted models (no data leaving the enclave), encryption at rest, audit logging on every query, RBAC on document access, no PHI in logs.

---

### Day 7: Buffer / extend

If you finish early or if the take-home has specific requirements you didn't anticipate, this day is buffer. Otherwise, use it to:

- Add basic auth / API key protection to the gateway
- Add structured logging (useful talking point for production readiness)
- Write a few unit tests for the chunking logic
- Try deploying to a local k3d cluster (stretch goal)

---

## 3. Tools & Accounts You Need

Set these up before Day 1:

- [ ] OpenAI API key (for embeddings + completions) — or Anthropic API key
- [ ] Docker Desktop running
- [ ] Python 3.11+ installed
- [ ] Node.js 20+ installed
- [ ] `grpcurl` installed (`brew install grpcurl`) — for testing gRPC services
- [ ] pgvector Docker image pulled (`docker pull pgvector/pgvector:pg16`)
- [ ] A GitHub repo created for the project
- [ ] A test PDF — grab DoDI 6490.03 or any public DoD policy document

---

## 4. From DocIntel → DRP Policy Assistant

After the interview process, converting DocIntel into DRP's policy assistant is straightforward:

| DocIntel | DRP Policy Assistant |
|---|---|
| Generic document ingestion | Pre-loaded with DoDI 6490.03, DAFI 48-122, dental readiness standards |
| Standalone API | Embedded in the provider review view |
| CLI / curl interface | Chat panel in the DRP UI |
| Any user | Scoped to provider role with audit logging |

The Python RAG service stays identical. The Express gateway merges into DRP's existing Express backend. The frontend gets a chat component in the provider view. ~4–6 hours of integration work.

---

## 5. What This Demonstrates to the Interview Panel

| Job Requirement | What You Show |
|---|---|
| "Architect, build, deploy agentic GenAI systems" | End-to-end RAG with streaming, containerized |
| "APIs, data processing ETL pipelines" | Document ingestion pipeline, embedding generation |
| "RAG and context engineering" | Chunking strategy, retrieval, prompt construction with sources |
| "Strong backend engineering in Python or TypeScript" | Both, working together via gRPC |
| "Work in cloud, on-prem, edge/air-gapped environments" | Docker-based, no external dependencies except the LLM API (discuss self-hosting as the airgap answer) |
| "Prototype and deploy systems leveraging UDS" | Discuss Zarf packaging, LeapfrogAI compatibility |
| "Codify reusable patterns" | Clean architecture, proto definitions, documented tradeoffs |
| "Communicate effectively with technical and non-technical stakeholders" | README quality, architectural clarity, your presentation of it |
