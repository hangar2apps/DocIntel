import grpc
import psycopg2
import docintel_pb2 # stubs interface
import docintel_pb2_grpc # router
import io
import uuid
import os
from pypdf import PdfReader
from concurrent import futures
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from dotenv import load_dotenv
load_dotenv()

# inherit the skeleton class from the auto-generated file 
class DocumentIntelligenceServicer(docintel_pb2_grpc.DocumentIntelligenceServicer):
    # on server start up, create one embedding client, one LLM client, and one database connection
    # then every request reuses them
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5433")),
            database=os.environ.get("DB_NAME", "docintel"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", "docintel")
        )

        cur = self.conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR(255),
                content TEXT NOT NULL,
                source VARCHAR(255),
                page_number INTEGER,
                chunk_index INTEGER,
                embedding vector(1536)
            )
        """)
        self.conn.commit()
        cur.close()

    def Query(self, request, context):
        # request.question has the question string
        
        # EMBED
        query_embedding = self.embeddings.embed_query(request.question)

        # CONNNECT TO DB
        cur = self.conn.cursor()


        # SIMILARITY SEARCH
        cur.execute("""
            SELECT content, source, 1 - (embedding <=> %s) AS similarity
            FROM document_chunks
            ORDER BY embedding <=> %s
            LIMIT %s
        """, (str(query_embedding), str(query_embedding), request.max_chunks or 5))

        results = cur.fetchall()
        cur.close()


        # Build context from retrieved chunks
        sources = []
        context_parts = []
        for content, source, similarity in results:
            context_parts.append(content)
            sources.append(docintel_pb2.SourceChunk(
                document_name=source,
                chunk_text=content[:200],
                similarity_score=similarity
            ))

        context_str = "\n\n---\n\n".join(context_parts)


        # Build the prompt
        prompt = f"""Answer the following question using the provided context. 
        If the context only partially answers the question, provide what you can and note what's missing.

        CONTEXT:
        {context_str}

        QUESTION: {request.question}

        ANSWER:"""

        # Send to LLM
        response = self.llm.invoke(prompt)

        # 5. Yield the response back to the caller
        yield docintel_pb2.QueryResponse(
            token=response.content,
            sources=sources,
            done=True
        )

    def IngestDocument(self, request, context):
        # interface has the following parameters
        # request.filename
        # request.content - this is the pdf in bytes
        # request.doc_type
        print('gn2 Ingest')

        # CHUNK
        reader = PdfReader(io.BytesIO(request.content))
        text = ""
        for page in reader.pages:
            text += page.extract_text()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            length_function=len,
        )

        chunks = splitter.split_text(text)
        print(f"Created {len(chunks)} chunks from {len(text)} text")

        # EMBED and SAVE to db
        doc_id = str(uuid.uuid4())

        cur = self.conn.cursor()

        for i, chunk in enumerate(chunks):
            embedding = self.embeddings.embed_query(chunk)
            cur.execute(
                """INSERT INTO document_chunks 
                (document_id, content, source, chunk_index, embedding) 
                VALUES (%s, %s, %s, %s, %s)""",
                (
                    doc_id,
                    chunk,
                    request.filename,
                    i,
                    str(embedding)
                )
            )
            if (i + 1) % 25 == 0:
                print(f"  ...{i + 1}/{len(chunks)}")

        print(f"Done. Stored {len(chunks)} chunks.")

        # explicitly commiting after all inserts are done
        self.conn.commit()
        cur.close()




        return docintel_pb2.IngestResponse(
            document_id=doc_id,
            chunks_created=len(chunks),
            status='complete'
        )

    def ListDocuments(self, request, context):
        print('gn2 ListDocuments')

        # CONNNECT TO DB
        cur = self.conn.cursor()


        # SELECT DOCUMENT LIST
        cur.execute("""
            SELECT document_id, source, COUNT(*) as chunk_count
            FROM document_chunks
            GROUP BY document_id, source
        """)

        results = cur.fetchall()
        cur.close()

        documents = []

        for doc_id, source, chunk_count in results:
            documents.append(docintel_pb2.DocumentMeta(
                document_id = doc_id,
                filename = source,
                doc_type =  '',  # would need to create a separate table and store doc_type id during ingestion
                chunk_count = chunk_count,
                ingested_at = '' # would need to create a new column and set at time of ingestion
            ))

        print(documents)

        return docintel_pb2.DocumentList(documents=documents)
           



def serve():
    # creates a gRPC server with thread pool that can handle 10 requests simultaneously
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    # registers the service class with the server. its like app.use('/api', router) telling the server 'when request come in, use this class to handle them
    # DocumentIntelligenceServicer() creates an instance of the class (which calls __init__, setting up the embeddings, LLC, and database connection)
    docintel_pb2_grpc.add_DocumentIntelligenceServicer_to_server(
        DocumentIntelligenceServicer(), server
    )
    # listens on port 50051 on all network interfaces
    # "insecure" means no TLS, production would use add_secure_port
    # Transportation Layer Security(TLS) - the S in HTTPS. encrypts the data flowing between client and server
    server.add_insecure_port('[::]:50051')
    # start the server, print confirmation, then block
    server.start()
    print("DocIntel gRPC server running on port 50051")
    # keeps the process alive and listening. same as app.listen()
    server.wait_for_termination()

# Standard Python convention. This means "only run serve() if this file is executed directly". If someone imports server.py from another file, it wont auto-start the server.
if __name__ == '__main__':
    serve()