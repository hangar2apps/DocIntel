import os
import psycopg2
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv()


query = 'When are deployment health assessments required?'

# EMBED

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
test_embedding = embeddings.embed_query(query)

print(f"Embedding dimensions: {len(test_embedding)}")
print(f"First 10 values: {test_embedding[:10]}")

# CONNNECT TO DB

conn = psycopg2.connect(
    host="localhost",
    port=5433,
    database="docintel",
    user="postgres",
    password="docintel"
)
conn.autocommit = True
cur = conn.cursor()


# SIMILARITY SEARCH
cur.execute("""
    SELECT content, page_number, 1 - (embedding <=> %s) AS similarity
    FROM document_chunks
    ORDER BY embedding <=> %s
    LIMIT 5
""", (str(test_embedding), str(test_embedding)))

results = cur.fetchall()

# for content, page, similarity in results:
#     print(f"\n--- Page {page} | Similarity: {similarity:.4f} ---")
#     print(content[:300])


# Build context from retrieved chunks
context = "\n\n---\n\n".join([
    f"[Page {page}]: {content}" 
    for content, page, similarity in results
])

print(f"Context length: {len(context)}")
print(context[:500])

# Build the prompt
prompt = f"""Answer the following question using the provided context. 
If the context only partially answers the question, provide what you can and note what's missing.
Include the page number(s) where you found relevant information.

CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""

# Send to LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
response = llm.invoke(prompt)

print(f"\n{'='*60}")
print(f"Question: {query}")
print(f"{'='*60}")
print(response.content)










cur.close()
conn.close()