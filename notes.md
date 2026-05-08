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

# Build RAG pipeline (these are just for learning. all will be done in server.py until big enough to justify separate files)
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
        - use vscode database extension to interact graphically

# Query (these are just for learning. all will be done in server.py until big enough to justify separate files)
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

# gRPC server

- Install dependencies
    - pip install grpcio grpcio-tools
    - dependencies breakdown
        - grpcio - the Python gRPC runtime
        - grpcio-tools - the code generator that turns a .proto file into Python stubs
- Create .proto file in root
    - it should do three things
        - Ingest a document - takes a file, returns a confirmation
        - Query - takes a question, returns an answer with sources
        - List documents - returns what's been ingested
- Generate Python stubs
    python -m grpc_tools.protoc \
        -I. \
        --python_out=. \
        --grpc_python_out=. \
        docintel.proto
    - -I. -> looks for proto files in the current directory
    - --python_out=. -> generate the message classes (the data structure)
    - --grpc_python_out=. -> generate the service stubs (the server/client code)
    - once ran should get two files
        - docintel_pb2.py - the message classes
        - docintel_pbs_grpc.py - the server/client stubs
        - DO NOT EDIT THESE FILES. If proto changes, regenerate them.
- Build Server
    - Create server.py
    - Import the generated stubs
    - Create a class that implements the service methods (like route handlers)
    - Create routes based on .proto (gRPC interface)
    - Start the server on a port (in venv)
    - Create client.py to test server by sending question over gRPC
    - run client.py (in venv, new terminal)

# Frontend
- Browser cannot speak gRPC natively. HTTP layer is needed. needs to do the following:
    - Accepts normal HTTP requests (JSON in, JSON out)
    - Translates them into gRPC calls to your Python service
    - Returns the results as HTTP responses
- Create Express server
    - mkdir gateway
    - cd gateway
    - npm init -y
    - npm install express @grpc/grpc-js @grpc/proto-loader cors
        - @grpc/grpc-js -> node.js rpc client (like grpcio in python)
        - @grpc/proto-loader -> reads .proto file and generates types at runtime (no separate code generation step like python)
        - cors -> so a browser can hit the server
        - ts-node -> runs TS directly without separate compile step
    - npm install -D typescript @types/express @types/node ts-node @types/cors
    - npx tsc --init
- Copy docintel.proto into gateway/
- Build server
    - Load proto file
    - Create gRPC client pointing to python server
    - Build routes
        - Query POST route
            - uses stream to get data back in pieces over time 
        - Document (ingest) POST route
            - normal req, res
        - Document GET route
            - normal req, res

# Containerize (Docker)
- will need 3 Dockerfiles
    - Python RAG service
    - TypeScript gateway
    - Postgres
        - already installed the Docker image, so no Dockerfile needed
- will need docker-compose.yml to wire them all together
- make database host configurable in server.py and server.ts 
- Create Dockerfiles
    - Python RAG service
        - generate requirements.txt from within venv
            - pip freeze > requirements.txt
            - this captures every package installed so the Docker container installs the same ones
        - in root (where server.py lives), create Dockerfile for Python service
    - Typescript Gateway
        - in gateway root (where server.ts lives) created Dockerfile
- Create docker-compose.yml in project root
- Kill running container (run anywhere)
    - docker stop docintel-db
- Set api key (run anywhere)
    - export OPENAI_API_KEY="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"
- Build docker containers (need to be in directory where docker-compose.yml is)
    - docker compose up --build
- Test
    - test the list endpoint to make sure the table creation on startup worked
        - curl http://localhost:3000/v1/documents
        - should return []
    - test ingest and query to prove that full contanierized pipeline works (run in directory where pdf is or point to pdf)
        - curl -X POST http://localhost:3000/v1/documents \
  -H "Content-Type: application/json" \
  -d "{\"filename\": \"DODI-6490.pdf\", \"content\": \"$(base64 -i ./DODI-6490.pdf)\", \"doc_type\": \"policy\"}"
        - should return {"document_id":"3bac28e8-3b98-490e-a0a8-28a87c2e0061","chunks_created":150,"status":"complete"}%  
        - curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"question": "When are deployment health assessments required?"}'
        - should get back object with question and answer

# User Interface
  - basic page that hits the gateway (http://localhost:3000)
        

# Helpful commands
- start container
    export OPENAI_API_KEY="their-key" (need to do this with new terminal)
    docker compose up --build
- stop container
    - docker stop docintel-db <- (container name)
        - stops individual containers
    - docker compose down
        - stops and removes all containers defined in docker-compose.yml
        - also removes the docker network created
- example questions
    - When are deployment health assessments required?